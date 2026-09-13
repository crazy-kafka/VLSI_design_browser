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
import os

import numpy as np
import pytest

from vlsi_viewer import parallel
from vlsi_viewer.metal import SCOPE_ALL, build_metal

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


def _build(jobs, monkeypatch=None, chunk=None):
    """The committed sub-block, built with the pool or without it."""
    if chunk is not None:
        monkeypatch.setattr(parallel, "DEFAULT_CHUNK_STATEMENTS", chunk)
    with contextlib.redirect_stdout(io.StringIO()):
        return build_metal([os.path.join(SAMPLE, "sub.def")],
                           [os.path.join(SAMPLE, "cells.lef")],
                           [os.path.join(SAMPLE, "tech.lef")],
                           grid_size=10.0, jobs=jobs)


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
    return Reader(path)


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
        for chunk in _chunks(_reader(path), 10 ** 6, index, 2, None, None, None, EXTENT, 10.0):
            held += sum(len(lines) for _section, _nets, lines in chunk.sections)
    assert held == total


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
    chunks = list(_chunks(_reader(str(path)), 1, 0, 1, tech, None, None,
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
