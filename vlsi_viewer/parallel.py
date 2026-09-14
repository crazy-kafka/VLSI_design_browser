"""The wiring pass across processes, for designs whose read takes longer than lunch.

The routing read is per-net and per-shape work with no dependency between nets, and each
layer's grid is independent, so it divides cleanly: workers take every ``jobs``-th net
statement and the parent sums what they return.

**Every worker reads the file itself, and that is the whole design.** The first version of this
had the parent cut the DEF into blocks and hand the text to the workers; measured on a
5 M-line input it came out *slower* than a single process (53 s against 44 s, and flat from two
workers up), because a chip-level DEF is gigabytes and shipping it through a pipe costs more
than parsing it. Reading the file in every worker costs one line-level scan each - a few
microseconds a line against the tens a parsed shape costs - and sends only per-layer grids
back, a megabyte or two per worker.

The price is honest and bounded: the file is scanned once per worker, so the sequential
fraction is the read, not the parse. For a design whose parse is hours, that is the 2 % the
arithmetic wants.

**A statement is cut whole, and carries the section it came from.** That is where the parser's
state lives: a ``*`` coordinate reuses the last point used *in that statement*, and a net's
``+ USE`` and ``+ NONDEFAULTRULE`` clauses are read from it. Cutting anywhere else changes what
the coordinates mean.

Statements are independent of each other, so a worker taking every ``jobs``-th one is the same
work as taking a contiguous share - which is why there is no block bookkeeping here, just a
stride. The parent sums the grids afterwards, so a float sum comes out in a different order
than a single-threaded run and its last bits can differ.

**`--jobs` is a cap, not an instruction** (see `effective_workers`): a worker costs a spawned
interpreter plus a full scan of the file, so an input of a few megabytes is parsed in one process
whatever the caller asked for.

**A cancel cannot be shipped to the workers, so the parent turns it into a byte.** A task argument
is deserialised *into* the child, where a copy of the caller's flag could never observe the
parent's `set()` - and the CLI's own cancel is a bound method of a `threading.Event`, which pickle
refuses outright. So the parent keeps the callable, raises one byte of shared memory when it says
so, and the byte is what crosses. A worker that sees it *keeps what it measured*: it hands its
partial sink back rather than raising, because the geometry read so far is the whole reason to stop
early instead of killing the job.

A caller on Windows must guard its entry point (``if __name__ == "__main__":``), because the
workers are spawned and re-import the calling module: without the guard, a script that builds this
way re-runs itself once per worker.
"""
from __future__ import annotations

import gzip
import logging
import os
import re
import signal
import struct
import threading
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import shared_memory
from typing import Dict, Iterator, List, NamedTuple, Optional, Sequence, Tuple

from .metal import _GridSink
from .parsers import Cancelled
from .parsers.routing import SHAPE_COUNTERS, ShapeStream, TechRouting, parse_def

logger = logging.getLogger(__name__)

# The sections that hold net statements, and every other section a DEF can open. Anything at
# column 0 that is not one of these is a preamble statement (`VERSION`, `UNITS`, `DIEAREA`).
_WIRING_SECTIONS = ("SPECIALNETS", "NETS")
_SECTIONS = _WIRING_SECTIONS + (
    "COMPONENTS", "PINS", "BLOCKAGES", "FILLS", "REGIONS", "STYLES", "SCANCHAINS", "GROUPS",
    "VIAS", "TRACKS", "NONDEFAULTRULES", "PROPERTYDEFINITIONS")
# A net statement begins with '- name'; this is the parser's own test for one.
_NET = re.compile(r"^\s*-\s+\S")
# Statements a worker holds before parsing them, so its memory is a few megabytes rather than
# the file. Bigger is faster and uses more; this is the same order as the streaming batch.
DEFAULT_CHUNK_STATEMENTS = 50000
# What a worker has to be worth. Its fixed cost is a spawned interpreter re-importing numpy,
# pandas and shapely plus a full scan of the file - a second or so - and parsing runs at roughly
# 0.1 us per uncompressed byte of DEF, so a worker needs a few megabytes of input before starting
# one pays. Deliberately conservative: this only ever lowers the worker count, and being wrong
# the safe way costs wall clock rather than correctness.
BYTES_PER_WORKER = 8 << 20
# How often the parent re-reads the caller's `cancel` while the workers run. The workers read the
# shared byte themselves - once per input line - so this is only the delay between the caller's
# flag going up and the byte moving, and it is already far inside the 30 s heartbeat the
# sequential path settles for. Named because a test may want it shorter.
CANCEL_POLL_SECONDS = 0.5


def input_size(path: str) -> int:
    """A DEF's *uncompressed* size, which is the work, not what it occupies on disk.

    A gzipped DEF's `st_size` is its compressed size - a 200 MB `.gz` is a 2 GB DEF - and every
    worker also decompresses the whole thing, so sizing on that would under-provision exactly the
    inputs that need the pool most. gzip's trailer carries the uncompressed length (modulo 2^32,
    and for the last member of a concatenated file), which is enough for the sizes asked about
    here.
    """
    size = os.path.getsize(path)
    if not str(path).endswith(".gz"):
        return size
    try:
        with open(path, "rb") as handle:
            handle.seek(max(0, size - 4))
            trailer = struct.unpack("<I", handle.read(4))[0]
    except (OSError, struct.error):                     # pragma: no cover - defensive
        return size
    # The trailer is the length modulo 2^32, so a DEF larger than 4 GB comes back as its
    # remainder - smaller than the compressed file it came from, which is impossible, and
    # the tell that it wrapped. Report the compressed size in that case: it is the floor of
    # the truth rather than a number that is wrong by gigabytes.
    return trailer if trailer >= size else size


def effective_workers(paths: Sequence[str], jobs: int, bytes_per_worker=None) -> int:
    """How many processes to use: ``jobs`` at most, fewer when the input is small.

    ``--jobs`` is a cap rather than an instruction, because a pool's startup is a second or two
    and pays back only from the file being big enough - a 2 MB sample run eight ways spends
    longer starting interpreters than parsing. ``bytes_per_worker`` is a parameter so a test can
    force the pool on a fixture that is deliberately small; monkeypatching the module constant
    would not reach the default, which is bound when this is defined.
    """
    jobs = max(1, int(jobs))
    per_worker = BYTES_PER_WORKER if bytes_per_worker is None else bytes_per_worker
    total = sum(input_size(path) for path in paths)
    return max(1, min(jobs, total // max(1, per_worker) + 1))


class Chunk(NamedTuple):
    """A piece of a worker's share: whole statements, and everything needed to parse them."""

    design: str
    header: List[str]              # VERSION, UNITS, DIEAREA and the rule table
    sections: List[Tuple[str, int, List[str]]]   # (section, net count, lines), in file order
    tech: TechRouting
    frames: Tuple                 # one per placement of the block, in the parent's frame
    min_segment: object
    extent: Tuple[float, float, float, float]
    grid_size: float


class Reader:
    """Streams a DEF's net statements, keeping the header they need.

    Streaming rather than accumulating, because a chip-level DEF's statements are gigabytes of
    text and a list of them is exactly what this cannot hold. ``preamble`` and ``rules`` are
    complete once :meth:`statements` has finished - everything before the first wiring section
    is read on the way in.

    **A reader keeps every ``stride``-th statement, the one at position ``index``.** Which
    statements those are is decided from a statement's *first* line, before its lines are
    accumulated: the alternative - yielding everything and letting the caller discard what it
    does not want - costs a list of every statement's lines in every worker, and one of those
    statements is a power net of 58 M lines. The partition is the same either way, so a worker
    reads exactly the statements it used to use; the stride defaults to 1, which keeps every
    statement.
    """

    def __init__(self, path: str, cancel=None, index: int = 0, stride: int = 1):
        self.path = path
        self.cancel = cancel
        self.index = int(index)
        self.stride = max(1, int(stride))
        self.preamble: List[str] = []
        self.rules: List[str] = []
        self.lines = 0
        self.design = ""
        self._declared: Dict[str, int] = {}
        self._found: Dict[str, int] = {}

    def statements(self) -> Iterator[Tuple[str, List[str]]]:
        """Yield ``(section, lines)`` for each of this reader's net statements, in file order."""
        pending: List[str] = []
        first = ""
        open_statement = False
        keeping = False
        is_net = False
        # Counts net statements, exactly as the caller's enumerate did when it filtered their
        # yields - so moving the filter here does not move which worker gets which statement.
        position = -1
        section: Optional[str] = None
        skipping = False
        in_rules = False
        for line in self._lines():
            if line.startswith("END "):
                # `open_statement` rather than `pending`: a statement nobody buffered still
                # ended without its ';', and that is worth saying.
                if open_statement:
                    logger.warning("parallel: dropping an unterminated statement at %r",
                                   line.strip())
                    pending = []
                    open_statement = False
                if in_rules:
                    self.rules.append(line)
                in_rules = skipping = False
                section = None
                continue
            name = line.split(maxsplit=1)[0] if line.strip() else ""
            if name in _SECTIONS:
                if open_statement:
                    logger.warning("parallel: dropping an unterminated statement before %s",
                                   name)
                    pending = []
                    open_statement = False
                in_rules = name == "NONDEFAULTRULES"
                section = name if name in _WIRING_SECTIONS else None
                skipping = not in_rules and section is None
                if in_rules:
                    # The section's own header line, or the parser never opens it and a net
                    # naming a rule falls back to the layer defaults - which moves geometry
                    # while leaving every counter identical.
                    self.rules.append(line)
                elif section is not None:
                    count = re.search(r"\d+", line)
                    self._declared[section] = int(count.group()) if count else 0
                continue
            if in_rules:
                self.rules.append(line)
            elif section is not None:
                if not open_statement:
                    # The first line decides everything: a net statement opens with '- name',
                    # and only net statements take a position.
                    first = line
                    open_statement = True
                    keeping = False
                    is_net = bool(_NET.match(first))
                    if is_net:
                        position += 1
                        keeping = position % self.stride == self.index
                if keeping:
                    pending.append(line)
                if ";" in line:
                    if is_net:
                        # Counted whether or not this worker keeps it: `check_counts` compares
                        # the section's declared count against every statement read from it,
                        # and that must not depend on how many workers are reading.
                        self._found[section] = self._found.get(section, 0) + 1
                        if keeping:
                            yield section, pending
                    pending, open_statement = [], False
            elif not skipping:
                if name == "DESIGN":
                    words = line.split()
                    self.design = words[1] if len(words) > 1 else self.design
                self.preamble.append(line)

    def _lines(self):
        """The file's lines, stopping at the design's end and counting what it yields.

        `END DESIGN` is not counted: nothing after it is a statement, and leaving it out keeps
        this count equal to the parser's own - a summary line should not depend on how many
        workers read the file.
        """
        self.lines = 0
        with self._open() as handle:
            for line in handle:
                if line.startswith("END ") and line.split()[1] == "DESIGN":
                    return
                if self.cancel is not None and self.cancel():
                    raise Cancelled(f"stopped after {self.lines:,} line(s)")
                self.lines += 1
                yield line

    def _open(self):
        if str(self.path).endswith(".gz"):
            return gzip.open(self.path, "rt")
        return open(self.path, "r")

    def check_counts(self) -> None:
        """Report a section that declares more than it holds - the check the sequential path
        makes, kept: silently measuring part of a design is the failure it exists for."""
        for section, expected in self._declared.items():
            if expected and self._found.get(section, 0) != expected:
                logger.warning("parallel: %s declares %d net(s) but %d were read; wiring the "
                               "parser did not reach is not counted", section, expected,
                               self._found.get(section, 0))


def _chunks(reader: Reader, chunk_statements: int,
            tech, frames, min_segment, extent, grid_size) -> Iterator[Chunk]:
    """Group the statements this worker owns into chunks the parser can take in one go.

    Which statements those are is the reader's business (every ``stride``-th one, from
    ``index``); within a chunk they are grouped by section, because a parsed chunk is one DEF
    text and a DEF holds its sections in turn. Order inside a section does not matter - a
    statement carries everything the parser needs to read it.
    """
    by_section: Dict[str, List[str]] = {}
    counts: Dict[str, int] = {}
    held = 0
    header: List[str] = []

    def chunk() -> Chunk:
        # The header is read lazily, on the first chunk: the reader fills it on its way to the
        # first statement, so it is only complete once iteration has started.
        if not header:
            header.extend(reader.preamble)
            header.extend(reader.rules)
        return Chunk(reader.design, header,
                     [(s, counts[s], by_section[s]) for s in _WIRING_SECTIONS
                      if s in by_section],
                     tech, frames, min_segment, extent, grid_size)

    for section, lines in reader.statements():
        by_section.setdefault(section, []).extend(lines)
        counts[section] = counts.get(section, 0) + 1
        held += 1
        if held >= chunk_statements:
            yield chunk()
            by_section, counts, held = {}, {}, 0
    if held:
        yield chunk()


class _Flag:
    """The stop signal a worker can read: one byte of shared memory.

    The caller's `cancel` cannot cross a process boundary - a deserialised copy in another address
    space can never see the parent's `set()` - so the parent is the only thing that reads it, and
    what travels is this. One byte, because the reader consults it once per input line and every
    alternative costs far more per read than that line does: ~2.7 us for a `multiprocessing.Event`
    - which cannot be passed as a task argument at all, `Condition objects should only be shared
    between processes through inheritance` - 29.5 us for a manager proxy, and 54.8 us for the
    `stat` behind a sentinel file.

    Defined at module level on purpose: a class from `__main__` cannot be unpickled by a spawned
    worker, and that failure kills the worker rather than the task - which the parent reports as
    `BrokenProcessPool`, a worse error than the one this exists to fix.
    """

    __slots__ = ("_shm",)

    def __init__(self, shm):
        self._shm = shm

    @classmethod
    def create(cls) -> "_Flag":
        return cls(shared_memory.SharedMemory(create=True, size=1))

    def is_set(self) -> bool:
        return self._shm.buf[0] != 0

    # The parsers ask `cancel()` - the reader per line, the parser at its heartbeat - so the stop
    # signal has to be callable. Answering both spellings is what keeps those call sites, and the
    # sequential path that still passes a real callable into the same parameter, untouched.
    __call__ = is_set

    def set(self) -> None:
        self._shm.buf[0] = 1

    def close(self) -> None:
        """Drop this process's mapping. A worker's copy, at the end of its task."""
        self._shm.close()

    def destroy(self) -> None:
        """Release the segment itself - only once no task carrying it can still be running.

        On POSIX every attach registers with the resource tracker and only `unlink` unregisters,
        so unlinking early is what produces the "leaked shared_memory objects" noise; on Windows
        there is no tracker and `unlink` is a no-op, the block going when the last handle does.
        """
        self._shm.close()
        self._shm.unlink()


def ignore_interrupts() -> None:
    """Run in each worker process: let the parent own ^C.

    A pool's workers are in the parent's process group (POSIX) and share its console (Windows), so
    a terminal ^C reaches them too - where it either kills the worker, turning a graceful stop into
    `BrokenProcessPool` with the map discarded, or re-raises `KeyboardInterrupt` in the parent past
    the `except Cancelled` that this whole path exists to serve. Installed as the pool's
    `initializer`, which runs first thing in each worker's main thread; the stdlib does the same
    for its own long-lived helpers (`resource_tracker.main`, the manager server).
    """
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def _watch(cancel, flag: _Flag, done: threading.Event) -> None:
    """Raise `flag` as soon as the caller's `cancel` says so, until `done` is set.

    A thread rather than a check in the loop, because the parent is blocked waiting for results -
    and the workers, which are the ones doing the work, cannot read the caller's callable at all.
    """
    while not done.wait(CANCEL_POLL_SECONDS):
        if cancel():
            flag.set()
            return


def parse_chunk(chunk: Chunk, cancel=None):
    """Parse one chunk into grids. Runs in a worker process, so it takes nothing on trust.

    A cancel is not an error here: the parser stops at a line boundary and everything it had
    already measured is still in the stream's pending batch and in the sink. Flushing *before* the
    counters are read is what keeps the two in step - the stream counts a shape when it queues it
    and hands the whole batch over in `flush()` - so a stopped chunk comes back partial and
    consistent rather than losing everything it read.
    """
    text = list(chunk.header)
    for section, nets, lines in chunk.sections:
        text.append(f"{section} {nets} ;\n")
        text.extend(lines)
        text.append(f"END {section}\n")
    text.append("END DESIGN\n")
    sink = _GridSink(chunk.extent, chunk.grid_size)
    stream = ShapeStream(chunk.tech, sink, frames=chunk.frames,
                         min_segment=chunk.min_segment)
    routing = None
    try:
        routing = parse_def(chunk.design, stream=stream, skip_components=True, lines=text,
                            cancel=cancel)
    except Cancelled:
        pass
    stream.flush()
    counters = {name: getattr(stream, attribute) for name, attribute in SHAPE_COUNTERS}
    if routing is None:
        # No rule table from a parse that stopped early, and its size is only ever an info line.
        return counters, {}, sink.grids(), 0, True
    return counters, routing.stats, sink.grids(), len(routing.ndrs), False


def fold_stats(text_stats: Dict, stats: Dict) -> None:
    """Fold one chunk's input characterisation into the running one.

    Maxima are maxima, layer names are a union, counters add. Line counts are the exception and
    come from each worker's own scan: every chunk re-reads the header, so summing what a parser
    saw would count the preamble once per chunk.
    """
    for key in ("forms", "points"):
        text_stats[key] += stats.get(key, 0)
    for key in ("statement_lines_max", "statement_chars_max", "points_max"):
        text_stats[key] = max(text_stats[key], stats.get(key, 0))
    text_stats["layers_used"] |= set(stats.get("layers_used", ()))


def _worker(task):
    """One worker: read the file, keep this worker's share, parse it in chunks.

    Reading the whole file in every worker is deliberate - see the module docstring. Only the
    grids and counters come back, so the traffic is a megabyte per worker rather than the file.
    A worker that is told to stop returns what it read and says so in its note, rather than
    raising: the caller folds those partial grids like any others.
    """
    (path, design, tech, frames, min_segment, extent, grid_size, index, stride,
     chunk_statements, flag) = task
    # A `_Flag` is callable, and the parsers only ever ask `cancel()`, so everything below this
    # line is the same whether the stop signal came from another process or from this one.
    cancel = flag
    reader = Reader(path, cancel=cancel, index=index, stride=stride)
    reader.design = design
    totals = {name: 0 for name, _attribute in SHAPE_COUNTERS}
    stats: Dict = {"forms": 0, "points": 0, "lines": 0, "statement_lines_max": 0,
                   "statement_chars_max": 0, "points_max": 0, "layers_used": set()}
    grids: Dict = {}
    sink = _GridSink(extent, grid_size)
    ndrs = 0
    stopped = 0
    chunks = _chunks(reader, chunk_statements, tech, frames, min_segment, extent, grid_size)
    try:
        for chunk in chunks:
            counters, chunk_stats, chunk_grids, chunk_ndrs, chunk_stopped = parse_chunk(
                chunk, cancel=cancel)
            for name, value in counters.items():
                totals[name] += value
            fold_stats(stats, chunk_stats)
            sink.add_grids(chunk_grids)
            ndrs = max(ndrs, chunk_ndrs)
            if chunk_stopped:
                # Folded once, then out: carrying on would add geometry that no counter accounts
                # for, which is the kind of wrong map that still looks plausible.
                stopped = 1
                break
    except Cancelled:
        # The reader's per-line check fires *between* chunks, with earlier ones already banked,
        # so the stop is caught here rather than being allowed to take that work with it.
        stopped = 1
    # Every worker reads the whole file, so any of them could report its length; only one does,
    # and the caller sums it across blocks rather than across workers.
    stats["lines"] = reader.lines if index == 0 else 0
    if not stopped:
        # A partial read makes the declared and found counts disagree, and every stopped worker
        # would report that as a defect in someone else's file. The sequential path never reaches
        # its equivalent check under a cancel either, so this is parity rather than suppression.
        reader.check_counts()
    if flag is not None:
        flag.close()              # this process's mapping; the parent owns the segment
    return totals, stats, sink.grids(), {"ndrs": ndrs, "stopped": stopped}


def parse_parallel(path: str, design: str, tech: TechRouting, frames, min_segment, extent,
                   grid_size: float, sink: _GridSink, jobs: int,
                   chunk_statements: Optional[int] = None, text_stats: Dict = None,
                   cancel=None, pool=None) -> Tuple[Dict, Dict, dict]:
    """Stream one DEF's wiring into ``sink`` across ``jobs`` processes.

    Returns the counters, the input characterisation and a header parse, the same things the
    sequential path folds into its totals - so a caller can swap one for the other. ``frames`` is
    the block's placements: the statements are split across workers, and each worker's chunks
    place their share under all of them.

    ``cancel`` stays in this process. It is read once here - before any worker exists, which is
    what makes an already-set cancel behave the same way twice - and then by a watcher thread for
    as long as they run; what crosses to the workers is the shared byte in its place.

    A cancel is *reported*, not raised: the totals returned alongside ``note["stopped"]`` are what
    the workers had measured when they were cut short, and ``note["interrupted"]`` says the caller
    asked to stop - which it may want to do even when every worker finished before noticing, with
    another block still to come. Raising here instead would hand back a sink holding geometry that
    no counter describes, which is a worse answer than either. A pool the caller brings has to be
    built with ``initializer=ignore_interrupts``, or a terminal ^C kills its workers instead.
    """
    # Resolved here rather than as a default argument, which would be bound when this was
    # defined and so ignore a caller - or a test - that sets the module constant.
    if chunk_statements is None:
        chunk_statements = DEFAULT_CHUNK_STATEMENTS
    flag = None
    watcher = None
    done = None
    if cancel is not None:
        flag = _Flag.create()
        if cancel():
            flag.set()                   # already asked for: nothing to watch, nothing to race
        else:
            done = threading.Event()
            watcher = threading.Thread(target=_watch, args=(cancel, flag, done),
                                       name="metal-cancel", daemon=True)
            watcher.start()
    tasks = [(path, design, tech, tuple(frames), min_segment, extent, grid_size, index, jobs,
              chunk_statements, flag) for index in range(jobs)]
    totals = {name: 0 for name, _attribute in SHAPE_COUNTERS}
    stats: Dict = text_stats if text_stats is not None else {
        "forms": 0, "points": 0, "lines": 0, "statement_lines_max": 0,
        "statement_chars_max": 0, "points_max": 0, "layers_used": set()}
    note = {"ndrs": 0, "stopped": 0, "interrupted": False}

    def drain(pool) -> None:
        for counters, worker_stats, grids, worker_note in pool.map(_worker, tasks):
            for name, value in counters.items():
                totals[name] += value
            fold_stats(stats, worker_stats)
            stats["lines"] = stats.get("lines", 0) + worker_stats["lines"]
            sink.add_grids(grids)
            note["ndrs"] = max(note["ndrs"], worker_note["ndrs"])
            note["stopped"] += worker_note["stopped"]

    try:
        if pool is not None:
            drain(pool)
        else:
            # A caller that brings its own pool shares one across the whole build - a hierarchy of
            # several blocks then pays for one set of interpreters instead of one per block.
            with ProcessPoolExecutor(max_workers=jobs, initializer=ignore_interrupts) as own:
                drain(own)
        # Read before the flag goes, and true even if every worker finished first: the caller
        # asked to stop, and there may be another block to come.
        note["interrupted"] = note["stopped"] > 0 or (flag is not None and flag.is_set())
    finally:
        if done is not None:
            done.set()
            watcher.join()               # before destroy(): it must not touch a closed mapping
        if flag is not None:
            flag.destroy()
    return totals, stats, note
