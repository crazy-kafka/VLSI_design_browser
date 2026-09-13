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
"""
from __future__ import annotations

import gzip
import logging
import re
from concurrent.futures import ProcessPoolExecutor
from typing import Dict, Iterator, List, NamedTuple, Optional, Tuple

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


class Chunk(NamedTuple):
    """A piece of a worker's share: whole statements, and everything needed to parse them."""

    design: str
    header: List[str]              # VERSION, UNITS, DIEAREA and the rule table
    sections: List[Tuple[str, int, List[str]]]   # (section, net count, lines), in file order
    tech: TechRouting
    frame: object
    min_segment: object
    extent: Tuple[float, float, float, float]
    grid_size: float


class Reader:
    """Streams a DEF's net statements, keeping the header they need.

    Streaming rather than accumulating, because a chip-level DEF's statements are gigabytes of
    text and a list of them is exactly what this cannot hold. ``preamble`` and ``rules`` are
    complete once :meth:`statements` has finished - everything before the first wiring section
    is read on the way in.
    """

    def __init__(self, path: str, cancel=None):
        self.path = path
        self.cancel = cancel
        self.preamble: List[str] = []
        self.rules: List[str] = []
        self.lines = 0
        self.design = ""
        self._declared: Dict[str, int] = {}
        self._found: Dict[str, int] = {}

    def statements(self) -> Iterator[Tuple[str, List[str]]]:
        """Yield ``(section, lines)`` for every net statement, in file order."""
        pending: List[str] = []
        section: Optional[str] = None
        skipping = False
        in_rules = False
        for line in self._lines():
            if line.startswith("END "):
                if pending:
                    logger.warning("parallel: dropping an unterminated statement at %r",
                                   line.strip())
                    pending = []
                if in_rules:
                    self.rules.append(line)
                in_rules = skipping = False
                section = None
                continue
            name = line.split(maxsplit=1)[0] if line.strip() else ""
            if name in _SECTIONS:
                if pending:
                    logger.warning("parallel: dropping an unterminated statement before %s",
                                   name)
                    pending = []
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
                pending.append(line)
                if ";" in line:
                    if _NET.match(pending[0]):
                        self._found[section] = self._found.get(section, 0) + 1
                        yield section, pending
                    pending = []
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


def _chunks(reader: Reader, chunk_statements: int, index: int, stride: int,
            tech, frame, min_segment, extent, grid_size) -> Iterator[Chunk]:
    """Group a worker's share of the statements into chunks the parser can take in one go.

    A share is every ``stride``-th statement; within a chunk they are grouped by section,
    because a parsed chunk is one DEF text and a DEF holds its sections in turn. Order inside
    a section does not matter - a statement carries everything the parser needs to read it.
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
                     tech, frame, min_segment, extent, grid_size)

    for position, (section, lines) in enumerate(reader.statements()):
        if position % stride != index:
            continue
        by_section.setdefault(section, []).extend(lines)
        counts[section] = counts.get(section, 0) + 1
        held += 1
        if held >= chunk_statements:
            yield chunk()
            by_section, counts, held = {}, {}, 0
    if held:
        yield chunk()


def parse_chunk(chunk: Chunk):
    """Parse one chunk into grids. Runs in a worker process, so it takes nothing on trust."""
    text = list(chunk.header)
    for section, nets, lines in chunk.sections:
        text.append(f"{section} {nets} ;\n")
        text.extend(lines)
        text.append(f"END {section}\n")
    text.append("END DESIGN\n")
    sink = _GridSink(chunk.extent, chunk.grid_size)
    stream = ShapeStream(chunk.tech, sink, frame=chunk.frame, min_segment=chunk.min_segment)
    routing = parse_def(chunk.design, stream=stream, skip_components=True, lines=text)
    stream.flush()
    counters = {name: getattr(stream, attribute) for name, attribute in SHAPE_COUNTERS}
    return counters, routing.stats, sink.grids(), len(routing.ndrs)


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
    grids and counters come back, so the traffic is a megabyte per worker rather than the
    file.
    """
    (path, design, tech, frame, min_segment, extent, grid_size, index, stride,
     chunk_statements) = task
    reader = Reader(path)
    reader.design = design
    totals = {name: 0 for name, _attribute in SHAPE_COUNTERS}
    stats: Dict = {"forms": 0, "points": 0, "lines": 0, "statement_lines_max": 0,
                   "statement_chars_max": 0, "points_max": 0, "layers_used": set()}
    grids: Dict = {}
    sink = _GridSink(extent, grid_size)
    ndrs = 0
    chunks = _chunks(reader, chunk_statements, index, stride, tech, frame, min_segment,
                     extent, grid_size)
    for chunk in chunks:
        counters, chunk_stats, chunk_grids, chunk_ndrs = parse_chunk(chunk)
        for name, value in counters.items():
            totals[name] += value
        fold_stats(stats, chunk_stats)
        sink.add_grids(chunk_grids)
        ndrs = max(ndrs, chunk_ndrs)
    # Every worker reads the whole file, so any of them could report its length; only one does,
    # and the caller sums it across blocks rather than across workers.
    stats["lines"] = reader.lines if index == 0 else 0
    reader.check_counts()
    return totals, stats, sink.grids(), {"ndrs": ndrs}


def parse_parallel(path: str, design: str, tech: TechRouting, frame, min_segment, extent,
                   grid_size: float, sink: _GridSink, jobs: int,
                   chunk_statements: int = DEFAULT_CHUNK_STATEMENTS, text_stats: Dict = None,
                   cancel=None) -> Tuple[Dict, Dict, dict]:
    """Stream one DEF's wiring into ``sink`` across ``jobs`` processes.

    Returns the counters, the input characterisation and a header parse, the same things the
    sequential path folds into its totals - so a caller can swap one for the other.
    """
    tasks = [(path, design, tech, frame, min_segment, extent, grid_size, index, jobs,
              chunk_statements) for index in range(jobs)]
    totals = {name: 0 for name, _attribute in SHAPE_COUNTERS}
    stats: Dict = text_stats if text_stats is not None else {
        "forms": 0, "points": 0, "lines": 0, "statement_lines_max": 0,
        "statement_chars_max": 0, "points_max": 0, "layers_used": set()}
    note = {"ndrs": 0}
    # Spawn, not fork: the parent holds the instance table and the grids, and a forked worker
    # would inherit both.
    with ProcessPoolExecutor(max_workers=jobs) as pool:
        for counters, worker_stats, grids, worker_note in pool.map(_worker, tasks):
            for name, value in counters.items():
                totals[name] += value
            fold_stats(stats, worker_stats)
            stats["lines"] = stats.get("lines", 0) + worker_stats["lines"]
            sink.add_grids(grids)
            note["ndrs"] = max(note["ndrs"], worker_note["ndrs"])
    return totals, stats, note
