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
import io
import logging
import os
import re
import shutil
import signal
import struct
import threading
import time
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import shared_memory
from typing import Dict, Iterator, List, NamedTuple, Optional, Sequence, Tuple

from .metal import _GridSink, resident_mb
from .parsers import Cancelled
from .parsers.routing import (LAYER_COLUMNS, PER_PLACEMENT_COLUMNS, SHAPE_COUNTERS,
                              ShapeStream, TechRouting, parse_def)

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
# Byte codes for the scan below. Indexing a `bytes` gives an int here, and slicing it to compare
# against a one-byte literal allocates a string per line - which measured as a third of the pass.
_CAP_A, _CAP_Z, _DASH, _SPACE = ord("A"), ord("Z"), ord("-"), (32, 9)
# Whether the pool splits the file by byte range (one scan in the parent, each worker reading only
# its own share) instead of by statement count (every worker scanning the whole file and keeping
# one statement in `jobs`). Both produce the same map; the difference is what they cost. Off while
# the change is being evaluated - see `dev_plan/metal_work_units_eval.md` - and a constant rather
# than a flag so a test and the benchmark can run both splits in one process, the way
# `BYTES_PER_WORKER` and `DEFAULT_CHUNK_STATEMENTS` are set.
RANGE_WORK_UNITS = False
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


class WorkUnits(NamedTuple):
    """Where every wiring statement starts, and what a reader beginning mid-file cannot see."""

    starts: List[int]                 # byte offset of each statement's first line, in file order
    sections: List[str]               # the wiring section each of those starts is in
    preamble: List[str]
    rules: List[str]
    design: str
    declared: Dict[str, int]          # the section's own count, from its header line
    found: Dict[str, int]             # statements per wiring section, counted as `_found` is
    lines: int                        # lines before `END DESIGN`, counted as `Reader._lines` does
    size: int                         # the file as it was when this was taken
    mtime: float
    odd_endings: bool = False         # a `\r` that is not part of `\r\n`


def scan_work_units(path: str) -> WorkUnits:
    """Read a DEF once, in binary, and record where its wiring statements start.

    Binary because the offsets are what a worker seeks to; the readers still read text. The win
    this pass has to earn is that it runs *once*, in the parent, where the per-line statement logic
    each worker runs costs 0.742 us/line (measured) - so it decodes a line only where a statement
    or a section could begin, and inside a statement it tests for one byte. On a real DEF most
    lines are inside a statement, which is why that matters.

    The classification has to agree with `Reader.statements` exactly: the same rule table, the same
    declared counts, the same statement starts. The two are compared over the committed fixtures in
    the tests rather than kept in step by hand, and `parse_parallel` compares the statement counts
    a worker actually found against this pass's own - so a divergence shows up as a failed run
    rather than as a quietly smaller number.
    """
    starts: List[int] = []
    sections: List[str] = []
    preamble: List[str] = []
    rules: List[str] = []
    declared: Dict[str, int] = {}
    found: Dict[str, int] = {}
    design = ""
    lines = 0
    offset = 0
    section: Optional[str] = None
    skipping = False
    in_rules = False
    open_statement = False
    is_net = False
    odd = False
    with open(path, "rb") as handle:
        for raw in handle:
            if raw.startswith(b"END DESIGN"):
                break
            lines += 1
            if lines == 1:
                # A lone CR is a line ending to text mode and not to this binary scan. Checked on
                # the first line only: a file's line endings are consistent, and the scan for one
                # costs 0.17 us/line - three times the rest of this pass put together, measured.
                # A file that mixes them is caught by `parse_parallel`'s own guard, which compares
                # the statements the readers found against the ones this scan counted.
                odd = b"\r" in (raw[:-2] if raw.endswith(b"\r\n") else raw)
            if open_statement and not (_CAP_A <= raw[0] <= _CAP_Z):
                # The case this pass exists for: inside a statement the only thing that decides
                # anything is whether the line ends it, and on a real DEF most lines are inside
                # one. No decode, no split, one membership test on bytes.
                if b";" in raw:
                    open_statement = False
                    if is_net:
                        found[section] = found.get(section, 0) + 1
                offset += len(raw)
                continue
            if (_CAP_A <= raw[0] <= _CAP_Z
                    or (not open_statement and raw[0] in _SPACE)):
                # Capital-initial lines can end a statement early, open a section or extend the
                # preamble; an indented line can open a statement, which real tools indent. Both
                # are rare compared with the lines above, which is what makes decoding them here
                # affordable.
                line = raw.decode()
                name = line.split(maxsplit=1)[0] if line.strip() else ""
                if line.startswith("END "):
                    if in_rules:
                        rules.append(line)
                    section, in_rules, skipping = None, False, False
                    open_statement = False
                    offset += len(raw)
                    continue
                if name in _SECTIONS:
                    open_statement = False
                    in_rules = name == "NONDEFAULTRULES"
                    section = name if name in _WIRING_SECTIONS else None
                    skipping = not in_rules and section is None
                    if in_rules:
                        rules.append(line)
                    elif section is not None:
                        count = re.search(r"\d+", line)
                        declared[section] = int(count.group()) if count else 0
                    offset += len(raw)
                    continue
                if in_rules:
                    rules.append(line)
                    offset += len(raw)
                    continue
                if not open_statement and section is None and not skipping:
                    if name == "DESIGN":
                        words = line.split()
                        design = words[1] if len(words) > 1 else design
                    preamble.append(line)
                    offset += len(raw)
                    continue
                # Anything else capital-initial is either a continuation of an open statement or
                # a line inside a section, and falls through to the same handling as any other.
            if in_rules:
                rules.append(raw.decode())
            elif section is not None:
                if not open_statement:
                    # `- name`, or an indented one, which is how real tools write a net statement.
                    stripped = raw.lstrip()
                    dashed = raw[0] == _DASH or (bool(stripped) and stripped[0] == _DASH)
                    is_net = bool(dashed and _NET.match(raw.decode()))
                    if is_net:
                        starts.append(offset)
                        sections.append(section)
                    open_statement = True
                if b";" in raw:
                    open_statement = False
                    if is_net:
                        found[section] = found.get(section, 0) + 1
            elif not skipping:
                preamble.append(raw.decode())
            offset += len(raw)
    info = os.stat(path)
    return WorkUnits(starts, sections, preamble, rules, design, declared, found, lines,
                     info.st_size, info.st_mtime, odd)


def pack_ranges(units: WorkUnits, jobs: int) -> List[List[Tuple[int, Optional[str], str]]]:
    """Cut the statements into ``jobs`` shares of roughly equal bytes, whole statements only.

    Cuts land on statement starts alone, so a statement is never split - which is what makes the
    giant power net safe to hand to one worker, and also why it cannot be balanced away: it lands
    in whichever share is emptiest at that point and dominates that worker's time.

    Each share carries the wiring section it begins in, because a share that starts in the middle
    of one has no header to tell it: the section that owns those statements lies before the cut.
    """
    shares: List[List[Tuple[int, Optional[str], str]]] = [[] for _ in range(jobs)]
    target = max(1.0, units.size / max(1, jobs))
    index = 0
    start, section = 0, None
    for offset, next_section in zip(units.starts, units.sections):
        if index < jobs - 1 and offset - start >= target:
            shares[index].append((start, offset, section))
            index, start, section = index + 1, offset, next_section
    shares[index].append((start, units.size, section))
    return shares


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

    def __init__(self, path: str, cancel=None, index: int = 0, stride: int = 1,
                 ranges=None, header: Optional[WorkUnits] = None):
        self.path = path
        self.cancel = cancel
        self.index = int(index)
        self.stride = max(1, int(stride))
        # A reader given ranges starts mid-file and cannot read these for itself: `preamble`,
        # `rules`, the declared counts and the design name come from the caller's scan. Left empty
        # they would fail *quietly* - no rule table means a net naming a non-default rule falls
        # back to the layer defaults, and no declared count means `check_counts` compares nothing
        # against nothing and passes.
        self.ranges = None if ranges is None else [tuple(piece) for piece in ranges]
        self.preamble: List[str] = list(header.preamble) if header is not None else []
        self.rules: List[str] = list(header.rules) if header is not None else []
        self.lines = 0
        self.design = header.design if header is not None else ""
        self._declared: Dict[str, int] = dict(header.declared) if header is not None else {}
        self._found: Dict[str, int] = {}
        # The whole file's line count, which only the scan can know once a reader starts mid-file.
        self.scanned_lines = header.lines if header is not None else 0

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
                if in_rules and self.ranges is None:
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
                if self.ranges is None:
                    # The section's own header line, or the parser never opens it and a net
                    # naming a rule falls back to the layer defaults - which moves geometry
                    # while leaving every counter identical. A reader with ranges takes all of
                    # this from the scan instead: it sees only its own share of the file, and a
                    # partial rule table or a partial declared count is worse than none.
                    if in_rules:
                        self.rules.append(line)
                    elif section is not None:
                        count = re.search(r"\d+", line)
                        self._declared[section] = int(count.group()) if count else 0
                continue
            if in_rules:
                if self.ranges is None:
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
                        # With ranges the worker was handed the statements it owns, so the stride
                        # has nothing left to decide.
                        keeping = (True if self.ranges is not None
                                   else position % self.stride == self.index)
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
            elif not skipping and self.ranges is None:
                if name == "DESIGN":
                    words = line.split()
                    self.design = words[1] if len(words) > 1 else self.design
                self.preamble.append(line)

    def _lines(self):
        """The file's lines, stopping at the design's end and counting what it yields.

        `END DESIGN` is not counted: nothing after it is a statement, and leaving it out keeps
        this count equal to the parser's own - a summary line should not depend on how many
        workers read the file.

        In range mode this counts only what *this* reader was given, and the whole file's count is
        the scan's - `scanned_lines` - because no worker sees more than its own share of the file.
        """
        self.lines = 0
        source = self._range_lines() if self.ranges is not None else self._file_lines()
        for line in source:
            if line.startswith("END ") and line.split()[1] == "DESIGN":
                return
            if self.cancel is not None and self.cancel():
                raise Cancelled(f"stopped after {self.lines:,} line(s)")
            self.lines += 1
            yield line

    def _file_lines(self):
        """The whole file, one line per iteration of the file iterator.

        Which is the fastest way to get lines out of a text file in Python: it is implemented in
        C, and reading blocks here to split them in Python was measured *slower* at every block
        size tried (0.24-0.31 µs/line against 0.22 on the sample, 0.16-0.19 against 0.14 on a
        file at the real design's line length), because the block path adds a generator layer and
        a per-line scan on top of the work the iterator already does.
        """
        with self._open() as handle:
            for line in handle:
                yield line

    def _range_lines(self):
        """This reader's own byte ranges, decoded as the whole-file reader would decode them.

        The offsets come from `scan_work_units` and every one of them is a line start, so a
        multi-byte character can never be cut in half. `io.TextIOWrapper` decodes with the same
        default encoding and applies the same newline translation as the `open()` in `_open()`,
        which is what keeps the two readings of the same file identical.

        A share cut inside a section has no header to say which section it is - the one that owns
        its statements lies before the cut - so the scan's answer is handed back as a header line
        at the start of that share. The classification consumes it and the parser never sees it.
        """
        with open(self.path, "rb") as handle:
            for start, end, seed in self.ranges:
                if seed is not None:
                    yield f"{seed} 0 ;\n"
                handle.seek(start)
                stream = io.TextIOWrapper(io.BytesIO(handle.read(end - start)))
                try:
                    for line in stream:
                        yield line
                finally:
                    stream.detach()

    def _open(self):
        if str(self.path).endswith(".gz"):
            return gzip.open(self.path, "rt")
        return open(self.path, "r")

    def check_counts(self) -> None:
        """Report a section that declares more than it holds - the check the sequential path
        makes, kept: silently measuring part of a design is the failure it exists for."""
        warn_on_counts(self._declared, self._found)


def warn_on_counts(declared: Dict[str, int], found: Dict[str, int]) -> None:
    """The same check, callable with a scan's counts as well as a reader's.

    A byte-range reader only ever sees its own share, so the declared-versus-found comparison has
    to be made by whoever read the whole file - and the wording has to be one wording, or the two
    places come to describe the same defect differently.
    """
    for section, expected in declared.items():
        if expected and found.get(section, 0) != expected:
            logger.warning("parallel: %s declares %d net(s) but %d were read; wiring the "
                           "parser did not reach is not counted", section, expected,
                           found.get(section, 0))


def _work_units(path: str, work_dir: Optional[str] = None):
    """The statement scan, on a file a worker can seek into.

    A `.gz` cannot be seeked, so it is decompressed once - to ``work_dir``, the current directory
    by default - and the uncompressed file is what both the scan and the workers use. The caller
    removes it; the sequential path keeps reading the `.gz` directly and never comes here.

    Returns ``(path_for_workers, units, temporary_path)``.
    """
    if not str(path).endswith(".gz"):
        return path, scan_work_units(path), None
    work_dir = work_dir or "."
    uncompressed = input_size(path)
    free = shutil.disk_usage(work_dir).free
    if free < uncompressed + (64 << 20):
        raise ValueError(
            f"{work_dir} has {free / 1e9:.1f} GB free, and {os.path.basename(str(path))} "
            f"decompresses to {uncompressed / 1e9:.1f} GB; point the work directory at a "
            f"filesystem with room")
    temporary = os.path.join(work_dir, os.path.basename(str(path))[:-3] + ".unpacked")
    logger.info("parallel: decompressing %s to %s (%d MB) so workers can read byte ranges",
                os.path.basename(str(path)), temporary, round(uncompressed / 1e6))
    with gzip.open(path, "rb") as source, open(temporary, "wb") as target:
        shutil.copyfileobj(source, target, 8 << 20)
    return temporary, scan_work_units(temporary), temporary


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


def parse_chunk(chunk: Chunk, cancel=None, puts=None):
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
                            cancel=cancel, puts=puts)
    except Cancelled:
        pass
    stream.flush()
    counters = {name: getattr(stream, attribute) for name, attribute in SHAPE_COUNTERS}
    if routing is None:
        # No rule table from a parse that stopped early, and its size is only ever an info line.
        return counters, {}, sink.grids(), 0, True, layer_stats_of(stream)
    return counters, routing.stats, sink.grids(), len(routing.ndrs), False, layer_stats_of(stream)


def new_layer_stats() -> Dict:
    """An empty per-layer bundle, in the shape `merge_layer_stats` takes.

    Three parts rather than one because the stream keys them differently, and it is right to: the
    rows are positional - a list per layer, because the shapes that fill them are on the per-shape
    path - while filtered shapes and unattributed vias have no index to be keyed by and stay under
    their layer's *name*.
    """
    return {"rows": [], "filtered_by_layer": {}, "via_points_by_layer": {}, "via_unattributed": 0}


def layer_stats_of(stream) -> Dict:
    """One stream's per-layer numbers, ready to merge into a running total."""
    return {"rows": [list(row) for row in stream.by_layer],
            "filtered_by_layer": dict(stream.filtered_by_layer),
            "via_points_by_layer": dict(stream.via_points_by_layer),
            "via_unattributed": stream.n_via_unattributed}


def merge_layer_stats(target: Dict, source: Dict, placements: int = 1) -> None:
    """Add one chunk's, worker's or block's per-layer numbers into another's.

    ``placements`` scales the columns whose counters are counted once per *parse* - see
    `PER_PLACEMENT_COLUMNS`, which is `PER_PLACEMENT_COUNTERS` in another shape. It belongs to the
    caller that knows how many times the block is placed: the per-block merge in `build_metal`,
    never a worker folding the chunks it read from one parse.

    The rows are widened rather than indexed into: a target that has seen fewer layers than the
    source is the normal case when the first contributor is a chunk of a trimmed stack.
    """
    while len(target["rows"]) < len(source["rows"]):
        target["rows"].append([0] * len(LAYER_COLUMNS))
    for row, other in zip(target["rows"], source["rows"]):
        for index, value in enumerate(other):
            row[index] += value * (placements if index in PER_PLACEMENT_COLUMNS else 1)
    for key in ("filtered_by_layer", "via_points_by_layer"):
        for name, count in source[key].items():
            target[key][name] = target[key].get(name, 0) + count
    target["via_unattributed"] += source["via_unattributed"]


def fold_stats(text_stats: Dict, stats: Dict) -> None:
    """Fold one chunk's input characterisation into the running one.

    Maxima are maxima, layer names are a union, counters add. Line counts are the exception and
    come from each worker's own scan: every chunk re-reads the header, so summing what a parser
    saw would count the preamble once per chunk.
    """
    for key in ("forms", "points", "rects"):
        # `.get` on the accumulator too: a caller's dictionary predates whatever counters a
        # later revision of the parser reports, and folding one it has never heard of should
        # add a key rather than raise eight processes deep.
        text_stats[key] = text_stats.get(key, 0) + stats.get(key, 0)
    for key in ("statement_lines_max", "statement_chars_max", "points_max"):
        text_stats[key] = max(text_stats[key], stats.get(key, 0))
    text_stats["layers_used"] |= set(stats.get("layers_used", ()))


def _tagged_puts(index: int):
    """A `print` for one worker: the same line, with the worker it came from in front.

    Eight workers share one stdout, and the parser's progress lines are most of what a pooled
    run writes - so without this the only thing telling two workers apart is the numbers
    inside the text.
    """

    def puts(text, **kwargs):
        print(f"[w{index}] {text}", **kwargs)

    return puts


def _worker_formatter(index: int) -> logging.Formatter:
    """The same tag for records that go through `logging` rather than `puts`."""
    return logging.Formatter(f"[w{index}] %(levelname)s %(name)s: %(message)s")


def _tag_logging(index: int) -> None:
    """Give this worker's own log records its tag.

    The handler is *replaced* rather than added to: under `fork` a worker inherits the parent's,
    and a second one would print every record twice.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(_worker_formatter(index))
    logging.getLogger().handlers[:] = [handler]


def _worker(task):
    """One worker: read the file, keep this worker's share, parse it in chunks.

    Reading the whole file in every worker is deliberate - see the module docstring. Only the
    grids and counters come back, so the traffic is a megabyte per worker rather than the file.
    A worker that is told to stop returns what it read and says so in its note, rather than
    raising: the caller folds those partial grids like any others.
    """
    (path, design, tech, frames, min_segment, extent, grid_size, index, stride,
     chunk_statements, flag, ranges, header) = task
    # A `_Flag` is callable, and the parsers only ever ask `cancel()`, so everything below this
    # line is the same whether the stop signal came from another process or from this one.
    cancel = flag
    # Everything this worker writes says so: the parser's progress lines through `puts`, and its
    # own log records through the handler the second call installs.
    puts = _tagged_puts(index)
    _tag_logging(index)
    started = time.perf_counter()
    reader = Reader(path, cancel=cancel, index=index, stride=stride, ranges=ranges,
                    header=header)
    reader.design = design
    totals = {name: 0 for name, _attribute in SHAPE_COUNTERS}
    stats: Dict = {"forms": 0, "points": 0, "lines": 0, "statement_lines_max": 0,
                   "statement_chars_max": 0, "points_max": 0, "rects": 0,
                   "layers_used": set()}
    grids: Dict = {}
    sink = _GridSink(extent, grid_size)
    ndrs = 0
    stopped = 0
    layers = new_layer_stats()
    chunks = _chunks(reader, chunk_statements, tech, frames, min_segment, extent, grid_size)
    try:
        for chunk in chunks:
            (counters, chunk_stats, chunk_grids, chunk_ndrs, chunk_stopped,
             chunk_layers) = parse_chunk(chunk, cancel=cancel, puts=puts)
            merge_layer_stats(layers, chunk_layers)
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
    # and the caller sums it across blocks rather than across workers. With ranges no worker has
    # read the whole file, so the length is the scan's and no worker reports one.
    if header is not None:
        # The total is the scan's, and exactly one worker reports it: the caller sums this field
        # across workers, and every worker knowing the same total would multiply it.
        stats["lines"] = header.lines if index == 0 else 0
    else:
        stats["lines"] = reader.lines if index == 0 else 0
    if not stopped and ranges is None:
        # A partial read makes the declared and found counts disagree, and every stopped worker
        # would report that as a defect in someone else's file. The sequential path never reaches
        # its equivalent check under a cancel either, so this is parity rather than suppression.
        # With ranges this worker holds only its share, and the check belongs to the parent, which
        # saw every statement's start.
        reader.check_counts()
    if flag is not None:
        flag.close()              # this process's mapping; the parent owns the segment
    return totals, stats, sink.grids(), {
        "ndrs": ndrs, "stopped": stopped,
        # What this worker cost and what it read, for sizing a pool rather than guessing at it.
        "seconds": time.perf_counter() - started,
        "rss_mb": resident_mb()[0],
        "read_bytes": (sum(end - start for start, end, _seed in ranges) if ranges
                       else input_size(path)),
        "layers": layers,
        # Handed back so the parent can compare the statements actually read against the ones its
        # own scan found - a divergence between the two would otherwise be a silently smaller
        # measurement rather than a failed run.
        "found": dict(reader._found)}


def parse_parallel(path: str, design: str, tech: TechRouting, frames, min_segment, extent,
                   grid_size: float, sink: _GridSink, jobs: int,
                   chunk_statements: Optional[int] = None, text_stats: Dict = None,
                   cancel=None, pool=None, work_dir: Optional[str] = None) -> Tuple[Dict, Dict, dict]:
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
    # One scan here, or a scan in every worker: either way the workers read `read_path`.
    read_path, units, temporary = (path, None, None)
    if RANGE_WORK_UNITS and jobs > 1:
        read_path, units, temporary = _work_units(path, work_dir)
        if units.odd_endings:
            # A lone CR is a line ending to text mode and not to this binary scan, so the offsets
            # would cut in the wrong places. Rare enough to read the long way rather than support.
            logger.warning("parallel: %s has a line ending this scan cannot place; every worker "
                           "will read the whole file, as before",
                           os.path.basename(str(path)))
            units = None
            if temporary is not None:
                os.unlink(temporary)
            read_path, temporary = path, None

    def task_for(index: int, share) -> Tuple:
        return (read_path, design, tech, tuple(frames), min_segment, extent, grid_size, index,
                jobs, chunk_statements, flag, share, units)

    if units is None:
        tasks = [task_for(index, None) for index in range(jobs)]
    else:
        warn_on_counts(units.declared, units.found)
        shares = pack_ranges(units, jobs)
        tasks = [task_for(index, shares[index]) for index in range(jobs)]
    totals = {name: 0 for name, _attribute in SHAPE_COUNTERS}
    stats: Dict = text_stats if text_stats is not None else {
        "forms": 0, "points": 0, "lines": 0, "statement_lines_max": 0,
        "statement_chars_max": 0, "points_max": 0, "layers_used": set()}
    note = {"ndrs": 0, "stopped": 0, "interrupted": False, "found": {}, "read_bytes": 0,
            "worker_seconds": [], "worker_rss_mb": [], "layers": new_layer_stats()}

    def drain(pool) -> None:
        for counters, worker_stats, grids, worker_note in pool.map(_worker, tasks):
            for name, value in counters.items():
                totals[name] += value
            fold_stats(stats, worker_stats)
            stats["lines"] = stats.get("lines", 0) + worker_stats["lines"]
            sink.add_grids(grids)
            note["ndrs"] = max(note["ndrs"], worker_note["ndrs"])
            note["stopped"] += worker_note["stopped"]
            # What each worker cost and read, so a pool can be sized from a measurement rather
            # than from a guess - and the statements it found, so a scan that put a statement
            # boundary in the wrong place is caught here rather than measuring fewer statements.
            note["worker_seconds"].append(worker_note["seconds"])
            note["worker_rss_mb"].append(worker_note["rss_mb"])
            note["read_bytes"] += worker_note["read_bytes"]
            merge_layer_stats(note["layers"], worker_note["layers"])
            for section, count in worker_note["found"].items():
                note["found"][section] = note["found"].get(section, 0) + count

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
        if units is not None and not note["stopped"] and note["found"] != units.found:
            # The scan and the readers have to agree about where statements begin. If they do not,
            # some statement straddles a range boundary and is being measured as two - which is a
            # smaller number, not an error, unless it is said out loud.
            raise ValueError(
                f"the statement scan and the readers disagree about {read_path}: the scan found "
                f"{units.found}, the readers {note['found']}")
    finally:
        if done is not None:
            done.set()
            watcher.join()               # before destroy(): it must not touch a closed mapping
        if flag is not None:
            flag.destroy()
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError as exc:       # pragma: no cover - best effort
                logger.warning("parallel: could not remove the decompressed copy %s (%s)",
                               temporary, exc)
    return totals, stats, note
