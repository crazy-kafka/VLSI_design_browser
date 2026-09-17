"""The wiring pass across processes: whole statements in, the same grids out.

The pool exists for one reason - a chip-level read takes hours - and it is only usable if it
produces what the single-threaded read produces. That is what these tests are: the same
counters, the same characterisation, and the same grids to within the rounding of a different
summation order.

The block cutter gets its own test, because it is where a parallel reader breaks first. A
statement is where the parser's state lives - a `*` coordinate reuses the last point used *in
that statement* - so a block may only be cut between statements, and every statement must land
in exactly one block.
"""
import contextlib
import io
import logging
import os
import signal
import threading

import numpy as np
import pytest

from vlsi_viewer import parallel
from vlsi_viewer.metal import SCOPE_ALL, build_metal
from vlsi_viewer.parsers import DefParser

SAMPLE = "sample_data/metal"


def _force_pool(monkeypatch, chunk=None):
    """Let the pool run on a fixture this small.

    `build_metal` sizes the pool to the input, and `sub.def` is 2 MB - far less than a worker is
    worth - so without this the equivalence tests below would compare a sequential build with a
    sequential build: green, and testing nothing about the pool.
    """
    monkeypatch.setattr(parallel, "BYTES_PER_WORKER", 0)
    if chunk is not None:
        monkeypatch.setattr(parallel, "DEFAULT_CHUNK_STATEMENTS", chunk)


def _build(jobs, monkeypatch=None, chunk=None, **kwargs):
    """The committed sub-block, built with the pool or without it."""
    if chunk is not None:
        monkeypatch.setattr(parallel, "DEFAULT_CHUNK_STATEMENTS", chunk)
    with contextlib.redirect_stdout(io.StringIO()):
        return build_metal([os.path.join(SAMPLE, "sub.def")],
                           [os.path.join(SAMPLE, "cells.lef")],
                           [os.path.join(SAMPLE, "tech.lef")],
                           grid_size=10.0, jobs=jobs, **kwargs)


def _heat(data, layers):
    data.set_scope(SCOPE_ALL)
    return np.asarray(data.heat(data.group_kind(layers)), dtype=np.float64)


def test_the_pool_produces_the_same_map_as_one_process(tmp_path, monkeypatch):
    """The claim the whole feature rests on, at a chunk size that exercises several chunks."""
    _force_pool(monkeypatch, chunk=250)
    sequential = _build(1)
    pooled = _build(3, monkeypatch)
    layers = [layer.name for layer in sequential.layers]
    kind = sequential.group_kind(layers)
    assert pooled.totals == sequential.totals
    assert pooled.stats["forms"] == sequential.stats["forms"]
    assert pooled.stats["points"] == sequential.stats["points"]
    assert pooled.stats["layers_used"] == sequential.stats["layers_used"]
    # Summation order differs, so the totals agree to float32 rounding rather than exactly:
    # measured at 1.1e-7 relative on this fixture. The absolute floor is for cells that are
    # empty in one run and hold a rounded crumb in the other - well under any real area, which
    # a bin of 10 um holds a hundred of.
    assert np.allclose(_heat(pooled, layers), _heat(sequential, layers), rtol=1e-6, atol=1e-6)
    assert pooled.max_util(kind) == pytest.approx(sequential.max_util(kind), rel=1e-6)


def test_a_trimmed_build_is_the_same_across_processes(monkeypatch):
    """The trimmed stack has to reach the workers, and the count is what proves it does.

    Comparing the pooled build with the sequential one cannot see a stream that does not know
    which layers were left out: both paths would miss it and still agree. What a worker would
    get wrong is only the diagnostics - its share of the out-of-range wiring would be reported
    as a layer the LEF does not define, and the parent sums that into a user-facing warning.
    """
    _force_pool(monkeypatch, chunk=250)
    sequential = _build(1, min_layer=4, max_layer=6)
    pooled = _build(3, monkeypatch, min_layer=4, max_layer=6)
    assert sequential.totals["filtered"] > 0
    assert sequential.totals["unknown"] == 0
    assert pooled.totals == sequential.totals
    assert [layer.name for layer in pooled.layers] == ["M4", "M5", "M6"]


def test_the_reported_input_size_does_not_depend_on_the_worker_count(monkeypatch):
    """Every worker reads the whole file, so a summary line must not multiply or divide it."""
    _force_pool(monkeypatch, chunk=250)
    sequential = _build(1)
    pooled = _build(3, monkeypatch)
    assert pooled.stats["lines"] == sequential.stats["lines"]
    assert pooled.stats["forms"] == sequential.stats["forms"]


def test_a_small_def_is_parsed_in_one_process():
    """`--jobs` is a cap: a pool's startup is not worth it for a couple of megabytes."""
    from vlsi_viewer.parallel import effective_workers

    path = os.path.join(SAMPLE, "sub.def")
    assert effective_workers([path], 8) == 1
    assert effective_workers([path], 1) == 1
    assert effective_workers([path, path], 8) == 1
    # ... and a DEF big enough to pay for them gets them, up to the caller's cap.
    assert effective_workers([path], 8, bytes_per_worker=0) == 8
    assert effective_workers([path], 3, bytes_per_worker=1 << 20) == 3
    assert effective_workers([path], 0) == 1                 # clamped, not zero workers


def test_a_gzipped_def_is_sized_by_what_it_decompresses_to(tmp_path):
    """A `.gz`'s size on disk is not the work - every worker decompresses the whole thing."""
    import gzip

    from vlsi_viewer.parallel import input_size

    text = "VERSION 5.8 ;\n" * 20000
    plain = tmp_path / "plain.def"
    plain.write_text(text)
    packed = tmp_path / "packed.def.gz"
    with gzip.open(packed, "wt") as handle:
        handle.write(text)
    with gzip.open(packed, "rb") as handle:
        decompressed = len(handle.read())
    assert input_size(str(plain)) == plain.stat().st_size
    assert input_size(str(packed)) == decompressed
    assert input_size(str(packed)) > os.path.getsize(packed) * 10


def _statements(path):
    """Every net statement in a DEF, as the parser reads them: from '-' to ';'.

    Only inside the wiring sections: a `NONDEFAULTRULES` rule also begins with '-', and the
    cutter is not asked to carry those (every block gets the whole rule table in its header).
    """
    out = []
    pending = []
    wiring = False
    for line in open(path):
        word = line.split(maxsplit=1)[0] if line.strip() else ""
        if word == "END":
            wiring = False
        elif word in ("NETS", "SPECIALNETS"):
            wiring = True
        elif word in ("COMPONENTS", "NONDEFAULTRULES", "PINS", "VIAS", "TRACKS"):
            wiring = False
        if not wiring:
            continue
        if pending or line.lstrip().startswith("-"):
            pending.append(line)
            if ";" in line:
                out.append("".join(pending))
                pending = []
    return out


EXTENT = (0.0, 0.0, 520.0, 400.0)


def _reader(path, **kwargs):
    from vlsi_viewer.parallel import Reader
    return Reader(path, **kwargs)


def test_every_statement_is_read_once_and_stays_whole():
    """The reader's invariant: no statement split, dropped, duplicated or reordered.

    A split statement is the failure that would not look like one - the coordinates would still
    parse, the map would still draw, and the wire would be in the wrong place.
    """
    path = os.path.join(SAMPLE, "sub.def")
    reader = _reader(path)
    got = "".join(line for _section, lines in reader.statements() for line in lines)
    assert got == "".join(_statements(path))              # same text, same order
    assert reader.design == "SUB"
    # The same number the parser reports for the same file, so a summary line does not depend
    # on which path produced it - the trailing `END DESIGN` belongs to no statement.
    from vlsi_viewer.parsers import DefParser

    with contextlib.redirect_stdout(io.StringIO()):
        parsed = DefParser(path, parse_net=True, parse_specialnet=True, parse_ndr=True)
    assert reader.lines == parsed.getStats()["lines"]
    # The header has to be enough to parse a chunk on its own: units, and the rule table -
    # without the rules a net naming one silently falls back to the layer defaults.
    header = "".join(reader.preamble) + "".join(reader.rules)
    assert "UNITS DISTANCE MICRONS" in header
    assert "NONDEFAULTRULES" in header


def test_two_workers_cover_the_statements_between_them():
    """Striding is the whole load-balancing scheme; a lost statement would be invisible."""
    from vlsi_viewer.parallel import _chunks

    path = os.path.join(SAMPLE, "sub.def")
    total = sum(len(lines) for _section, lines in _reader(path).statements())
    held = 0
    for index in (0, 1):
        for chunk in _chunks(_reader(path, stride=2, index=index), 10 ** 6, None, None, None,
                             EXTENT, 10.0):
            held += sum(len(lines) for _section, _nets, lines in chunk.sections)
    assert held == total


def test_a_worker_reads_only_its_own_share(tmp_path):
    """The partition, as an equivalence rather than as "still works".

    A worker used to keep every statement's lines and hand fifteen sixteenths of them back
    unread; the stride moved into the reader, so the share each one *sees* has to be the share
    it used to *use* - same positions, same order, and every statement read exactly once across
    the workers.
    """
    path = tmp_path / "many.def"
    path.write_text("""\
DESIGN many ;
UNITS DISTANCE MICRONS 1000 ;
DIEAREA ( 0 0 ) ( 10000 10000 ) ;
COMPONENTS 1 ;
- u1 INV + PLACED ( 0 0 ) N ;
END COMPONENTS
NETS 6 ;
- n0 ( u1 A ) + ROUTED M1 ( 0 0 ) ( 100 0 ) ;
- n1 ( u1 A ) + ROUTED M1 ( 0 100 ) ( 100 100 ) ;
- n2 ( u1 A ) + ROUTED M1 ( 0 200 ) ( 100 200 ) ;
- n3 ( u1 A ) + ROUTED M1 ( 0 300 ) ( 100 300 ) ;
- n4 ( u1 A ) + ROUTED M1 ( 0 400 ) ( 100 400 ) ;
- n5 ( u1 A ) + ROUTED M1 ( 0 500 ) ( 100 500 ) ;
END NETS
END DESIGN
""")
    whole = [lines[0].split()[1] for _section, lines in _reader(str(path)).statements()]
    assert whole == ["n0", "n1", "n2", "n3", "n4", "n5"]
    for stride in (2, 3):
        shares = [[lines[0].split()[1]
                   for _section, lines in _reader(str(path), stride=stride, index=index)
                   .statements()]
                  for index in range(stride)]
        assert shares == [[name for position, name in enumerate(whole)
                           if position % stride == index] for index in range(stride)]
        assert sorted(name for share in shares for name in share) == sorted(whole)


def test_a_statement_no_one_keeps_is_still_counted(tmp_path, caplog):
    """`check_counts` compares declared against read, and it must not depend on the stride.

    The counter is what catches a parser that stops early - the failure that reads part of a
    design and says nothing - so a worker that is skipping statements still has to count them.
    """
    path = tmp_path / "short.def"
    path.write_text("""\
DESIGN short ;
UNITS DISTANCE MICRONS 1000 ;
DIEAREA ( 0 0 ) ( 1000 1000 ) ;
NETS 9 ;
- n1 ( u1 A ) + ROUTED M1 ( 100 200 ) ( 400 200 ) ;
- n2 ( u1 A ) + ROUTED M1 ( 100 300 ) ( 400 300 ) ;
END NETS
END DESIGN
""")
    reader = _reader(str(path), stride=2, index=1)      # keeps the *second* of two statements
    with caplog.at_level("WARNING", logger="vlsi_viewer.parallel"):
        assert len(list(reader.statements())) == 1
        reader.check_counts()
    assert any("declares 9 net(s) but 2 were read" in record.getMessage()
               for record in caplog.records)


def test_a_worker_that_skips_a_giant_statement_does_not_hold_it(tmp_path):
    """The statement the real design has exactly one of, and what a wide pool was going to cost.

    A power net of 200,000 lines is one statement, so it belongs to exactly one worker - but
    every worker used to build the list of it before the stride was consulted, and then
    fifteen of sixteen threw it away. The measurement has to be of a *giant* statement: with
    short ones the whole list is a few kilobytes and the difference is invisible, which is what
    the first version of this test showed.
    """
    import tracemalloc

    form = "  NEW M1 0 + SHAPE STRIPE ( 1000 2000 ) via1_2\n"
    path = tmp_path / "giant.def"
    path.write_text("DESIGN giant ;\nUNITS DISTANCE MICRONS 1000 ;\n"
                    "DIEAREA ( 0 0 ) ( 10000 10000 ) ;\nCOMPONENTS 1 ;\n"
                    "- u1 INV + PLACED ( 0 0 ) N ;\nEND COMPONENTS\nSPECIALNETS 1 ;\n"
                    "- VDD + USE POWER\n" + form * 200_000
                    + "  ;\nEND SPECIALNETS\nEND DESIGN\n")

    def read(index):
        tracemalloc.start()
        held = sum(len(lines)
                   for _section, lines in _reader(str(path), stride=2, index=index).statements())
        _current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return held, peak

    kept_lines, kept_peak = read(0)              # this worker owns the giant statement
    skipped_lines, skipped_peak = read(1)        # this one is told to skip it
    assert kept_lines == 200_002       # the net's own line, its 200,000 forms, its ';'
    assert skipped_lines == 0
    assert skipped_peak < kept_peak / 10         # it never builds the list at all


def test_a_chunk_holds_one_section_at_a_time(tmp_path):
    """A parsed chunk is one DEF text, and a DEF holds its sections in turn."""
    from vlsi_viewer.parsers.routing import TechRouting
    from vlsi_viewer.parallel import _chunks

    path = tmp_path / "mixed.def"
    path.write_text("""\
VERSION 5.8 ;
DESIGN mixed ;
UNITS DISTANCE MICRONS 1000 ;
DIEAREA ( 0 0 ) ( 1000 1000 ) ;
SPECIALNETS 1 ;
- VDD + USE POWER
  NEW M1 400 ( 100 100 ) ( 900 100 ) ;
END SPECIALNETS
NETS 2 ;
- n1 ( u1 A )
  + ROUTED M1 ( 100 200 ) ( 400 200 ) ;
- n2 ( u1 B )
  + ROUTED M1 ( 100 300 ) ( 400 300 ) ;
END NETS
END DESIGN
""")
    tech_path = tmp_path / "tech.lef"
    tech_path.write_text(open(os.path.join(SAMPLE, "tech.lef")).read())
    with contextlib.redirect_stdout(io.StringIO()):
        tech = TechRouting.read([str(tech_path)])
    # One statement per chunk, so each chunk shows exactly what it holds.
    chunks = list(_chunks(_reader(str(path)), 1, tech, None, None,
                          (0.0, 0.0, 1000.0, 1000.0), 10.0))
    assert [(section, nets) for chunk in chunks
            for section, nets, _lines in chunk.sections] == [("SPECIALNETS", 1),
                                                            ("NETS", 1), ("NETS", 1)]


def test_a_section_that_declares_more_than_it_holds_is_reported(tmp_path, caplog):
    """The check the sequential path makes, kept: part of a design is not a design."""
    path = tmp_path / "short.def"
    path.write_text("""\
VERSION 5.8 ;
DESIGN short ;
UNITS DISTANCE MICRONS 1000 ;
DIEAREA ( 0 0 ) ( 1000 1000 ) ;
NETS 9 ;
- n1 ( u1 A )
  + ROUTED M1 ( 100 200 ) ( 400 200 ) ;
END NETS
END DESIGN
""")
    reader = _reader(str(path))
    with caplog.at_level("WARNING", logger="vlsi_viewer.parallel"):
        list(reader.statements())
        reader.check_counts()
    assert any("declares 9 net(s) but 1 were read" in record.getMessage()
               for record in caplog.records)


# -- stopping the workers ------------------------------------------------------------

def test_the_cli_configuration_builds_a_pooled_run(monkeypatch):
    """`--jobs N` with the cancel the CLI really passes: `stop.is_set`.

    That bound method of a `threading.Event` cannot be pickled, and the task tuple carried it, so
    every `--jobs` run from the CLI died at the first worker with
    `error: cannot pickle '_thread.lock' object`. This is that configuration, inverted.
    """
    _force_pool(monkeypatch)
    stop = threading.Event()
    sequential = _build(1)
    pooled = _build(3, monkeypatch, cancel=stop.is_set)
    assert pooled.totals == sequential.totals
    assert not [warning for warning in pooled.warnings if "stopped early" in warning]


def test_a_cancel_means_the_same_thing_on_both_paths(monkeypatch):
    """Same input, an already-set cancel, one process against three.

    The sequential path cancels at the parser's heartbeat and the pooled one in each worker's
    reader; both have to leave a map that still exists and a warning that says why it is empty.
    """
    monkeypatch.setattr(DefParser, "HEARTBEAT_SECONDS", 0)
    _force_pool(monkeypatch)
    sequential = _build(1, cancel=lambda: True)
    pooled = _build(3, monkeypatch, cancel=lambda: True)
    for data in (sequential, pooled):
        assert any("stopped early" in warning for warning in data.warnings)
        assert data.totals["emitted"] == 0          # nothing was measured...
        assert data.rows > 0 and data.cols > 0      # ...but there is still a map to look at
    layers = [layer.name for layer in sequential.layers]
    assert np.allclose(_heat(pooled, layers), _heat(sequential, layers))


class _CountingFlag:
    """A stop signal that flips on the k-th read, so a partial run is deterministic.

    A clock-based cancel would make the assertions depend on how far a worker happened to get,
    which is the flakiness a salvage test cannot afford. This object stands in for the shared
    byte: it is callable like the real one, and it counts the reads the reader makes of it.
    """

    def __init__(self, after):
        self.after = after
        self.reads = 0

    def _read(self):
        self.reads += 1
        return self.reads > self.after

    __call__ = _read
    is_set = _read

    def set(self):
        self.after = -1                 # what the parent does when the flag is already up

    def close(self):
        pass

    def destroy(self):
        pass


def test_a_stopped_worker_keeps_what_it_measured(monkeypatch, caplog):
    """The salvage, at the level it lives: workers stopped in the middle of the file.

    What a partial run reports has to be a *prefix* of the full run's. Every shape adds
    positively, so the returned grid must be a cellwise minorant of the complete one and must not
    be empty - and that is the invariant no counter can show, because folding a chunk's grids
    without its counters, or twice, still counts coherently and still looks plausible.
    """
    lines = sum(1 for _ in open(os.path.join(SAMPLE, "sub.def")))
    flag = _CountingFlag(after=lines // 2)
    monkeypatch.setattr(parallel._Flag, "create", classmethod(lambda cls: flag))
    _force_pool(monkeypatch, chunk=200)
    full = _build(1)
    with caplog.at_level("WARNING", logger="vlsi_viewer.parallel"):
        partial = _build(3, monkeypatch, cancel=lambda: False)
    layers = [layer.name for layer in full.layers]
    kept, whole = _heat(partial, layers), _heat(full, layers)
    assert 0 < partial.totals["emitted"] < full.totals["emitted"]
    assert (kept > 0).any()
    assert (kept <= whole + 1e-9).all()
    assert any("stopped early" in warning for warning in partial.warnings)
    # A partial read makes the declared and found counts disagree; that is not a defect in the
    # design, so it must not be reported as one.
    assert not [record for record in caplog.records if "declares" in record.getMessage()]


def test_a_cancel_between_blocks_keeps_the_block_already_read(monkeypatch):
    """Two blocks, driven by progress rather than by a clock.

    The first block is complete before the flag can go up - the predicate only becomes true once
    the second block has announced itself - so TOP's 9 shapes must survive a cancel that stops SUB
    dead. Both come out of the same pool, which is what the block loop is for.
    """
    _force_pool(monkeypatch)
    seen = []

    def cancel():
        # "reading routing in SUB" - not the bare "reading routing", which is announced once
        # before the block loop and would cancel the first block instead of the second.
        return sum("reading routing in" in message for message in seen) >= 2

    with contextlib.redirect_stdout(io.StringIO()):
        data = build_metal([os.path.join(SAMPLE, "top.def"), os.path.join(SAMPLE, "sub.def")],
                           [os.path.join(SAMPLE, "cells.lef")],
                           [os.path.join(SAMPLE, "tech.lef")], grid_size=10.0, jobs=3,
                           cancel=cancel, on_progress=seen.append)
    assert any("stopped early" in warning for warning in data.warnings)
    assert data.totals["emitted"] == 9              # TOP's ring, and none of SUB's wiring


def test_the_workers_are_told_not_to_hear_the_interrupt():
    """^C belongs to the parent, the only process that can decide what to keep.

    A worker that takes the interrupt either dies - a broken pool, and the map is discarded - or
    re-raises KeyboardInterrupt in the parent past the `except Cancelled` this path exists for.
    The pool's initializer installs the ignore, as the stdlib does for its own helpers.
    """
    previous = signal.getsignal(signal.SIGINT)
    try:
        parallel.ignore_interrupts()
        assert signal.getsignal(signal.SIGINT) is signal.SIG_IGN
    finally:
        signal.signal(signal.SIGINT, previous)


def test_the_pool_is_built_with_that_initializer(monkeypatch):
    """The wiring, not just the function: an initializer that is never passed protects nothing."""
    import concurrent.futures

    seen = {}
    real = concurrent.futures.ProcessPoolExecutor

    class Recorder(real):
        def __init__(self, *args, **kwargs):
            seen.update(kwargs)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(concurrent.futures, "ProcessPoolExecutor", Recorder)
    _force_pool(monkeypatch)
    _build(3, monkeypatch)
    assert seen.get("initializer") is parallel.ignore_interrupts


# -- the log a worker writes ---------------------------------------------------------

def _beat_record():
    return logging.LogRecord("vlsi_viewer.parallel", logging.WARNING, __file__, 1,
                             "parallel: %s declares %d net(s)", ("f.def", 3), None)


def test_a_worker_tags_every_line_it_prints():
    """Eight workers share one stdout: a line has to say which worker wrote it.

    The pool's output is mostly the parser's own heartbeat, and without a tag the only thing
    telling two workers apart was the numbers inside the text itself.
    """
    puts = parallel._tagged_puts(3)
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        puts("Read DEF 1,308,204 lines")
        puts("End DEF parsing in 69.0185s", flush=True)      # the heartbeat passes flush
    assert captured.getvalue().splitlines() == ["[w3] Read DEF 1,308,204 lines",
                                                "[w3] End DEF parsing in 69.0185s"]


def test_a_worker_tags_the_records_it_logs():
    """The same tag on records that go through `logging`, or the two styles disagree."""
    formatted = parallel._worker_formatter(3).format(_beat_record())
    assert formatted.startswith("[w3] WARNING vlsi_viewer.parallel: ")
    assert formatted.endswith("declares 3 net(s)")


def test_a_worker_tags_what_it_writes(tmp_path):
    """The whole path in one process: `_worker` down to the parser's own line.

    The pool cannot be asked this - its workers are separate processes, and on a spawned platform
    their output is not the test's stdout at all. Running one worker here is what makes the tag
    observable, and it is the only test that would notice `_worker` forgetting to install it.
    Four nets read at stride four, index three, leave this worker exactly one statement - so the
    line it writes is the whole of its output and can be asserted exactly.
    """
    from vlsi_viewer.parallel import _Flag, _worker
    from vlsi_viewer.parsers.routing import TechRouting

    path = tmp_path / "one.def"
    path.write_text("""\
VERSION 5.8 ;
DESIGN one ;
UNITS DISTANCE MICRONS 1000 ;
DIEAREA ( 0 0 ) ( 1000 1000 ) ;
NETS 4 ;
- n1 ( u1 A ) + ROUTED M1 ( 100 200 ) ( 400 200 ) ;
- n2 ( u1 A ) + ROUTED M1 ( 100 300 ) ( 400 300 ) ;
- n3 ( u1 A ) + ROUTED M1 ( 100 400 ) ( 400 400 ) ;
- n4 ( u1 A ) + ROUTED M1 ( 100 500 ) ( 400 500 ) ;
END NETS
END DESIGN
""")
    tech_path = tmp_path / "tech.lef"
    tech_path.write_text(open(os.path.join(SAMPLE, "tech.lef")).read())
    with contextlib.redirect_stdout(io.StringIO()):
        tech = TechRouting.read([str(tech_path)])
    # (path, design, tech, frames, min_segment, extent, grid_size, index, stride,
    #  chunk_statements, flag, ranges, header, geometry_prefix) - the last three are `None`
    # without byte ranges and without a dump to write geometry into.
    flag = _Flag.create()
    task = (str(path), "one", tech, None, None, EXTENT, 10.0, 3, 4, 1, flag, None, None, None)
    root = logging.getLogger()
    handlers = root.handlers[:]          # `_worker` installs its own, as it must in a child
    try:
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            _worker(task)
    finally:
        root.handlers[:] = handlers
        flag.destroy()
    lines = captured.getvalue().splitlines()
    assert lines[0] == "[w3] Load DEF file one"
    assert lines[1].startswith("[w3] End DEF parsing in ")
    # Nothing this worker writes escapes the tag, whichever of the two paths it came from.
    assert all(line.startswith("[w3] ") for line in lines)


# -- byte-range work units (the prototype, off by default) ----------------------------

GCD = "sample_data/real/nangate45/gcd_nangate45.def"


def _first_lines(path):
    return [lines[0] for _section, lines in _reader(path).statements()]


def test_the_scan_finds_the_same_statements_the_reader_does(tmp_path):
    """The scan's offsets are only useful if they agree with the reader, statement for statement.

    Compared on a DEF of each shape the repository has: the generated block, a routed netlist
    whose statements run over several lines, and deliberately awkward text - blank lines, indented
    statements, a record whose coordinates wrap.
    """
    from vlsi_viewer.parallel import scan_work_units

    awkward = tmp_path / "awkward.def"
    awkward.write_text("""\
VERSION 5.8 ;
DESIGN awk ;
UNITS DISTANCE MICRONS 1000 ;
DIEAREA ( 0 0 ) ( 10000 10000 ) ;
NONDEFAULTRULES 1 ;
- WIDE
  + LAYER M1 WIDTH 200 SPACING 200
  ;
END NONDEFAULTRULES
COMPONENTS 1 ;
- u1 BUF + PLACED ( 0 0 ) N ;
END COMPONENTS
NETS 3 ;

    - n1 ( u1 A )
      + ROUTED M1 ( 100 100 ) ( 900 100 ) ;
- n2 ( u1 A ) + ROUTED M1 ( 100 200 ) ( 900 200 )
  ( 900 300 )
  ;
- n3 ( u1 A ) WIDE
  + ROUTED M1 ( 100 400 ) ( 900 400 ) ;
END NETS
END DESIGN
""")
    for path in (os.path.join(SAMPLE, "sub.def"), os.path.join(SAMPLE, "top.def"), GCD,
                 str(awkward)):
        units = scan_work_units(path)
        with open(path, "rb") as handle:
            firsts = []
            for offset in units.starts:
                handle.seek(offset)
                # Normalised the way the readers normalise it: they read text, and a fixture
                # written on Windows carries CRLF that neither of them hands on.
                firsts.append(handle.readline().decode().replace("\r\n", "\n"))
        assert firsts == _first_lines(path), path


def test_the_scan_reads_the_header_the_reader_would_have_read():
    """The three things that fail silently when a reader starts mid-file."""
    from vlsi_viewer.parallel import Reader, scan_work_units

    for path in (os.path.join(SAMPLE, "sub.def"), GCD):
        whole = _reader(path)
        list(whole.statements())
        units = scan_work_units(path)
        assert units.preamble == whole.preamble
        assert units.rules == whole.rules
        assert units.design == whole.design
        assert units.declared == whole._declared
        assert units.found == whole._found
        assert units.lines == whole.lines
        # And that a reader handed them has no reason to read the head of the file at all.
        ranged = Reader(path, ranges=[(0, units.size, None)], header=units)
        list(ranged.statements())
        assert ranged.preamble == whole.preamble and ranged.rules == whole.rules
        assert ranged._declared == whole._declared


def test_the_ranges_partition_the_file_at_statement_starts():
    """Whole statements, in order, with nothing left over - the property the whole idea rests on."""
    from vlsi_viewer.parallel import pack_ranges, scan_work_units

    path = os.path.join(SAMPLE, "sub.def")
    units = scan_work_units(path)
    for jobs in (1, 2, 3, 8):
        shares = pack_ranges(units, jobs)
        assert len(shares) == jobs
        pairs = [piece for share in shares for piece in share]
        assert pairs[0][0] == 0 and pairs[-1][1] == units.size
        assert all(pairs[i][1] == pairs[i + 1][0] for i in range(len(pairs) - 1))
        # A cut is a statement start, never a byte inside one - which is what protects a
        # statement's `*` state and keeps the giant statement whole.
        assert all(start in set(units.starts) or start == 0 for start, _end, _s in pairs)
        assert all(end == units.size or end in set(units.starts) for _start, end, _s in pairs)


def test_every_statement_lands_in_exactly_one_share():
    """The partition is disjoint and complete, and each share reads in file order."""
    from vlsi_viewer.parallel import Reader, pack_ranges, scan_work_units

    path = os.path.join(SAMPLE, "sub.def")
    units = scan_work_units(path)
    seen = []
    for share in pack_ranges(units, 3):
        seen += [lines[0] for _section, lines in
                 Reader(path, ranges=share, header=units).statements()]
    assert seen == _first_lines(path)          # same statements, same order, each exactly once


def test_a_byte_range_pool_produces_the_same_map_as_one_process(monkeypatch):
    """The claim the whole change rests on, at a chunk size that exercises several chunks."""
    _force_pool(monkeypatch, chunk=250)
    sequential = _build(1)
    strided = _build(3, monkeypatch)
    monkeypatch.setattr(parallel, "RANGE_WORK_UNITS", True)
    ranged = _build(3, monkeypatch)
    assert ranged.totals == sequential.totals == strided.totals
    assert ranged.stats["forms"] == sequential.stats["forms"]
    assert ranged.stats["points"] == sequential.stats["points"]
    assert ranged.stats["lines"] == sequential.stats["lines"]
    assert ranged.stats["layers_used"] == sequential.stats["layers_used"]
    layers = [layer.name for layer in sequential.layers]
    assert np.allclose(_heat(ranged, layers), _heat(sequential, layers), rtol=1e-6, atol=1e-6)


def test_a_scan_that_miscounts_is_caught_rather_than_measured(monkeypatch):
    """The safety net, and the only test that can show it is a net at all.

    A boundary in the wrong place would measure fewer statements and report that as a smaller
    number - so what the readers actually parsed is compared against what the scan counted, and
    a scan that disagrees must fail the run rather than quietly under-report it. The corruption
    here stands in for the whole family: any divergence ends in the same comparison.
    """
    _force_pool(monkeypatch, chunk=250)
    monkeypatch.setattr(parallel, "RANGE_WORK_UNITS", True)
    real = parallel.scan_work_units

    def lossy(path):
        units = real(path)
        section = next(iter(units.found))
        return units._replace(found=dict(units.found, **{section: units.found[section] - 1}))

    monkeypatch.setattr(parallel, "scan_work_units", lossy)
    with pytest.raises(ValueError, match="disagree"):
        _build(2, monkeypatch)


def test_a_gzipped_def_is_unpacked_once_and_removed_again(tmp_path, monkeypatch):
    """The `.gz` path: seekable after one decompression, and the copy does not outlive the run."""
    import gzip

    _force_pool(monkeypatch, chunk=250)
    monkeypatch.setattr(parallel, "RANGE_WORK_UNITS", True)
    body = open(os.path.join(SAMPLE, "sub.def")).read()
    packed = tmp_path / "sub.def.gz"
    with gzip.open(str(packed), "wt", newline="\n") as handle:
        handle.write(body)
    with contextlib.redirect_stdout(io.StringIO()):
        data = build_metal([str(packed)], [os.path.join(SAMPLE, "cells.lef")],
                           [os.path.join(SAMPLE, "tech.lef")], grid_size=10.0, jobs=2,
                           work_dir=str(tmp_path))
    assert data.totals["emitted"] > 0
    assert not (tmp_path / "sub.def.unpacked").exists()
