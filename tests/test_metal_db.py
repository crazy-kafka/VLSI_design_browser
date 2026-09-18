"""The metal mode's intermediate db: dump, reuse, replay, and every way a db is refused.

The centrepiece is equivalence: a map rebuilt from dbs must be the *same map*, not a similar one -
so the grids are compared with `array_equal` and the counters exactly. Everything else here is a
refusal that has to happen for the right reason, because a db that is used when it should not be is
a wrong map that loads fast, which is the one outcome worth refusing.

A db carries two flavours of itself. The *grids* are the block rasterised on the run's own frame
and grid, and they are bound to both, so they are only usable by a run that matches on every input
that shaped them. The *shapes* are the block's own geometry, stored as the parser read it and
before any frame touched it, so a run with different frames, a different die or a different grid
can rasterise them itself. A db written before the second flavour exists - the v1 npz below - has
only the first, and its refusals are the ones the geometry section replaced.
"""
import contextlib
import io
import json
import os
import shutil
from typing import Dict

import numpy as np
import pytest

from vlsi_viewer import metal_db, parallel
from vlsi_viewer.cli import main
from vlsi_viewer.metal import build_metal

SAMPLE = "sample_data/metal"
TOP = f"{SAMPLE}/top.def"
SUB = f"{SAMPLE}/sub.def"
CELLS = f"{SAMPLE}/cells.lef"
TECH = f"{SAMPLE}/tech.lef"


def _build(def_paths, db_paths=None, dump_db=None, **kwargs):
    """One metal build, with the parser's own progress prints kept out of the test output."""
    with contextlib.redirect_stdout(io.StringIO()):
        return build_metal(list(def_paths), [CELLS], [TECH], grid_size=10.0,
                           db_paths=db_paths, dump_db=dump_db, **kwargs)


def _force_pool(monkeypatch):
    """Let the pool run on a fixture this small.

    `--jobs` is a cap rather than an instruction, and a 2 MB sample is one worker's worth - so
    without this a pooled dump would silently be a sequential one, and the test would compare the
    sequential path with itself.
    """
    monkeypatch.setattr(parallel, "BYTES_PER_WORKER", 0)


def _same_map(one, other, exact=True):
    """Every number a db is supposed to reproduce: the counters, the layer rows, the text stats
    and the grids.

    ``exact`` is the stronger claim a replay of the same shapes in the same order makes - the same
    arithmetic on the same values - and it holds on this sample. A *pooled* dump is the case that
    only promises closeness: its workers read statements in a different order, so the sums over a
    grid cell land in a different order too.
    """
    assert one.totals == other.totals
    assert one.layer_stats == other.layer_stats
    assert one.stats == other.stats
    assert set(one._grids) == set(other._grids)
    for key, grid in other._grids.items():
        got, want = np.asarray(one._grids[key]), np.asarray(grid)
        if exact:
            assert np.array_equal(got, want), key
        else:
            assert np.allclose(got, want, rtol=1e-6, atol=1e-6), key


def _as_v1(path, **edits):
    """Rewrite a dumped db in the container dumps used before the record stream: an npz.

    The old writer stored the header and one compressed array per grid, which is the whole reason
    the geometry section exists - there was nowhere in the file to put a shape. So this is both
    the compatibility fixture and the fixture for every refusal that now only applies to a db with
    no shapes to replay. ``edits`` changes header fields, for the tests that want a db this build
    must refuse.
    """
    db = metal_db.load(str(path))
    header = {key: value for key, value in db.header.items()
              if key not in ("index", "geometry")}
    header.update(edits)
    payload = {"header": np.array(json.dumps(header))}
    for (layer, scope), grid in db.grids.items():
        payload[f"grid__{layer}__{scope}"] = np.asarray(grid, dtype=np.float32)
    if db.components is not None:
        payload["components"] = np.asarray(db.components)
    with open(str(path), "wb") as handle:
        np.savez_compressed(handle, **payload)


@pytest.fixture(scope="module")
def whole():
    """One full build of both sample DEFs, shared by the tests that need a reference map.

    It is the slow part of this file - a build is ~0.7 s, and seven tests wanted the same one and
    threw it away. Nothing mutates it: every test that edits a DEF or a db edits a copy under
    `tmp_path`, which is why one build can serve them all.
    """
    return _build([TOP, SUB])


def _db_paths(directory):
    return [os.path.join(str(directory), name)
            for name in sorted(os.listdir(str(directory)))]


def _sample_pair(tmp_path):
    """The committed two-DEF sample, copied so a test can edit one of them in place."""
    for path in (TOP, SUB):
        shutil.copy(path, tmp_path / os.path.basename(path))
    return [str(tmp_path / "top.def"), str(tmp_path / "sub.def")]


def _layers_of(data):
    return [(layer.name, layer.direction, layer.width, layer.spacing, layer.pitch,
             layer.usable) for layer in data.layers]


def test_the_db_name_follows_the_def(tmp_path):
    """``A.def.gz`` -> ``A.def.db``, which is the name the user asked for and the one the tool
    has to write: `np.savez` appends its own extension to a name it is given."""
    assert metal_db.db_path_for("/a/b/gcd.def.gz", "/out") == os.path.join("/out", "gcd.def.db")
    assert metal_db.db_path_for("A.def", "/out") == os.path.join("/out", "A.def.db")
    assert metal_db.db_path_for("A.def.gz.gz", "/out") == os.path.join("/out", "A.def.gz.db")


def test_a_db_rebuilds_the_same_map(tmp_path):
    """The db is a copy, not a re-derivation: every number comes back exactly.

    Nothing is parsed on the second run - no DEF, no components pass - so this is also the test
    that a block can be measured from a db alone.
    """
    dbs = tmp_path / "dbs"
    first = _build([TOP, SUB], dump_db=str(dbs))
    assert sorted(os.listdir(str(dbs))) == ["sub.def.db", "top.def.db"]

    again = _build([], db_paths=_db_paths(dbs))
    assert again.reused == ["TOP", "SUB"]              # both came from a db
    assert again.totals == first.totals
    assert again.layer_stats == first.layer_stats
    assert again.stats == first.stats
    assert _layers_of(again) == _layers_of(first)
    assert again.boundary_polys == first.boundary_polys
    assert set(again._grids) == set(first._grids)
    for key, grid in first._grids.items():
        assert np.array_equal(np.asarray(again._grids[key]), np.asarray(grid)), key
    # The capacity is rebuilt from the live LEFs and the stored boundary; it has to agree.
    for layer in first.layers:
        assert np.array_equal(np.asarray(again.capacity(layer)),
                              np.asarray(first.capacity(layer))), layer.name
    kind = first.kinds()[0][0]
    assert again.cell_detail(3, 3, kind) == first.cell_detail(3, 3, kind)
    assert again.warnings == first.warnings


def test_only_the_def_that_changed_is_parsed_again(tmp_path, caplog):
    """The user's case: dump once, edit one DEF, and the rest of the design is not read.

    The edit is a power stripe on the top's own wiring, so the sub-block's placement - and with
    it the sub-block's db - stays valid. A re-parse is the *asked for* outcome here, so it is a
    log line rather than a warning: nothing is wrong, the DEF simply changed.
    """
    defs = _sample_pair(tmp_path)
    dbs = tmp_path / "dbs"
    _build(defs, dump_db=str(dbs))

    top = tmp_path / "top.def"
    text = top.read_text()
    assert "( 140000 60000 )" in text
    top.write_text(text.replace("( 140000 60000 )", "( 150000 60000 )"))

    fresh = _build(defs)                                  # what the edited design measures to
    with caplog.at_level("INFO", logger="vlsi_viewer.metal"):
        again = _build(defs, db_paths=_db_paths(dbs))
    assert again.reused == ["SUB"]                        # TOP's db was refused, SUB's was not
    assert any("db for TOP not used" in record.getMessage()
               and "the DEF changed" in record.getMessage() for record in caplog.records)
    assert again.totals == fresh.totals
    for key, grid in fresh._grids.items():
        assert np.array_equal(np.asarray(again._grids[key]), np.asarray(grid)), key


def test_a_db_only_run_says_which_blocks_wiring_is_missing(tmp_path):
    """Coverage, checked against what the dbs themselves record: half a design is drawn as half
    a design, not as a whole one with quiet holes in it.

    The missing block cannot be seen at all - the walk only descends into blocks it knows - so
    the warning is the only trace, and it has to say the name is wiring rather than footprint.
    """
    dbs = tmp_path / "dbs"
    whole = _build([TOP, SUB], dump_db=str(dbs))
    os.unlink(str(dbs / "sub.def.db"))

    partial = _build([], db_paths=_db_paths(dbs))
    assert partial.reused == ["TOP"]
    assert any("SUB" in warning and "sub-block" in warning for warning in partial.warnings)
    assert sum(float(grid.sum()) for grid in partial._grids.values()) < \
        sum(float(grid.sum()) for grid in whole._grids.values())


def test_a_changed_lef_refuses_every_db(tmp_path):
    """The db is DEF-derived only, so the LEFs decide nothing until they are re-read - and then
    they decide whether the db still applies at all."""
    dbs = tmp_path / "dbs"
    _build([TOP, SUB], dump_db=str(dbs))

    tech = tmp_path / "tech.lef"
    shutil.copy(TECH, tech)
    with open(str(tech), "a", encoding="utf-8") as handle:
        handle.write("\n# touched\n")

    with contextlib.redirect_stdout(io.StringIO()):
        again = build_metal([TOP, SUB], [CELLS], [str(tech)], grid_size=10.0,
                            db_paths=_db_paths(dbs))
    assert again.reused == []
    assert again.totals == _build([TOP, SUB]).totals


@pytest.mark.parametrize("dumped_range, asked_range", [
    ((2, 4), (None, None)),      # dumped a range, asked for the whole stack
    ((None, None), (2, 4)),      # dumped the whole stack, asked for a range
])
def test_a_layer_range_that_differs_refuses_the_db(tmp_path, caplog, dumped_range, asked_range):
    """Both directions, because both draw something wrong: the first leaves layers unmeasured
    and rendering as 0 %, the second re-derives counts the db does not carry."""
    dbs = tmp_path / "dbs"
    _build([TOP, SUB], dump_db=str(dbs),
           min_layer=dumped_range[0], max_layer=dumped_range[1])
    fresh = _build([TOP, SUB], min_layer=asked_range[0], max_layer=asked_range[1])
    with caplog.at_level("INFO", logger="vlsi_viewer.metal"):
        again = _build([TOP, SUB], db_paths=_db_paths(dbs),
                       min_layer=asked_range[0], max_layer=asked_range[1])
    assert again.reused == []
    # The range is a recorded parameter, so the params check is what refuses it - and the advice
    # differs by direction: a whole-stack db answers a range through the layer checkboxes.
    refused = " ".join(record.getMessage() for record in caplog.records)
    assert "min_layer is" in refused or "max_layer is" in refused
    assert ("checkboxes" in refused) == (dumped_range == (None, None))
    assert again.totals == fresh.totals


def test_the_sub_block_dump_workflow(tmp_path, whole):
    """The parallel-dump path: a top-only dump, then each sub-block dumped against the parent's
    *db* rather than the parent's DEF - and the two together equal the one-shot build.

    This is what the remembered components are for: a top dumped alone cannot know which of its
    components are blocks, so it records the candidates' local placements and the resolution
    happens here, when the sub-block's DEF arrives.
    """
    dbs = tmp_path / "dbs"
    _build([TOP], dump_db=str(dbs))                       # the top alone: SUB is not a block yet
    assert sorted(os.listdir(str(dbs))) == ["top.def.db"]

    # SUB dumped in its own run, placed by the parent's db and never reading top.def.
    _build([SUB], db_paths=[str(dbs / "top.def.db")], dump_db=str(dbs))
    assert sorted(os.listdir(str(dbs))) == ["sub.def.db", "top.def.db"]

    again = _build([], db_paths=_db_paths(dbs))
    assert again.reused == ["TOP", "SUB"]
    assert again.totals == whole.totals
    for key, grid in whole._grids.items():
        assert np.array_equal(np.asarray(again._grids[key]), np.asarray(grid)), key
    assert again.top_name == whole.top_name
    assert again.rows == whole.rows and again.cols == whole.cols


def test_a_bare_sub_dump_is_placed_by_the_design_that_loads_it(tmp_path, whole):
    """The 09-17 workflow: a sub-block dumped with no parent at all, then assembled by a design.

    Its db records the placement the dumping run saw - its own origin - so its *grids* are
    unusable here. Its shapes are not: they were stored in the sub-block's own coordinates, and
    the run that knows where the sub-block goes rasterises them under its own frames. Before the
    geometry section this was a refusal by name, because the alternative was drawing the
    sub-block's wiring at (0, 0).
    """
    dbs = tmp_path / "dbs"
    _build([SUB], dump_db=str(dbs))                       # no parent: SUB is its own root
    # The premises, so the pass below cannot be vacuous: the dump really was written for one
    # placement at the block's own origin, and it really holds fewer shapes than the design that
    # places it four times. `emitted` and three layer columns are counted per *placement*, so a
    # replay has to move them - and `_same_map` compares all of them against the one-shot parse,
    # which is where a missing rescale would show as a summary saying one and a table saying four.
    sub_db = metal_db.load(str(dbs / "sub.def.db"))
    assert [tuple(frame)[0] for frame in sub_db.frames] == ["N"]
    assert sub_db.header["totals"]["emitted"] < whole.totals["emitted"]

    again = _build([TOP], db_paths=_db_paths(dbs))
    assert again.reused == [] and again.replayed == ["SUB"]
    assert again.warnings == []
    _same_map(again, whole)
    assert again.cell_detail(3, 3, whole.kinds()[0][0]) == whole.cell_detail(3, 3, whole.kinds()[0][0])


def test_the_hierarchy_dumps_and_assembles_across_processes(tmp_path, monkeypatch, whole):
    """The hierarchical case, end to end: two blocks, two independent dump jobs, each with a pool
    and neither naming a parent - then one run over the two dbs with no DEFs at all.

    This is what the geometry section is for. The sub-block's dump is pooled, so its body is
    written by workers as they flush their own batches and merged by the parent; it is standalone,
    so its placement is its own origin; and the design that loads it places it four times at four
    different orientations. Its grids cannot serve that, so the replay has to - and the map has to
    come out the same one the one-shot parse makes.
    """
    _force_pool(monkeypatch)
    dbs = tmp_path / "dbs"
    _build([SUB], dump_db=str(dbs), jobs=2)              # the sub-block alone, pooled
    assert sorted(os.listdir(str(dbs))) == ["sub.def.db"]
    _build([TOP], dump_db=str(dbs), jobs=2)              # the top alone, its own job
    assert sorted(os.listdir(str(dbs))) == ["sub.def.db", "top.def.db"]

    # Nothing was dropped between the counters and the file: every shape the parse counted as
    # emitted is in the body, once per placement. It is the one check that the workers' parts and
    # the parent's merge together hold the whole block - and it is made against a number counted
    # by a different path than the one that wrote the file.
    sub_db = metal_db.load(str(dbs / "sub.def.db"))
    stored = sum(sub_db.header["geometry"].values())
    assert stored * len(sub_db.frames) == sub_db.header["totals"]["emitted"]

    again = _build([], db_paths=_db_paths(dbs))
    assert again.reused == ["TOP"]                       # the root: same frames, its grids stand
    assert again.replayed == ["SUB"]                     # dumped elsewhere: its shapes replayed
    assert again.warnings == whole.warnings
    _same_map(again, whole, exact=False)                 # a pooled dump sums in another order
    assert again.top_name == whole.top_name
    assert again.rows == whole.rows and again.cols == whole.cols
    kind = whole.kinds()[0][0]
    assert again.cell_detail(3, 3, kind) == whole.cell_detail(3, 3, kind)


def test_a_dump_passes_through_the_dbs_it_reused(tmp_path):
    """A dump directory holds one db per block, whichever way the block got there.

    A block that came out of a db is *copied*, not re-derived: its db already holds what this run
    would write, shapes included - and those shapes are not in this process to rewrite, so writing
    the live grids over it would throw away the half that makes it loadable by the next design.
    """
    first = tmp_path / "first"
    second = tmp_path / "second"
    _build([TOP, SUB], dump_db=str(first))
    again = _build([TOP, SUB], db_paths=_db_paths(first), dump_db=str(second))
    assert sorted(again.reused) == ["SUB", "TOP"]
    assert sorted(os.listdir(str(second))) == ["sub.def.db", "top.def.db"]
    for name in ("sub.def.db", "top.def.db"):
        assert (second / name).read_bytes() == (first / name).read_bytes(), name


def test_a_cancelled_build_writes_no_db(tmp_path, monkeypatch):
    """A prefix of a measurement must not become a db: it would load fast and draw the wrong map.

    The stop is forced by making the parse raise, because a 40 k-line sample finishes before the
    parser's heartbeat would ever look at a cancel flag - and a cancel that arrives too late to
    stop anything is a complete build, which *should* be dumpable.
    """
    from vlsi_viewer.parsers import Cancelled
    from vlsi_viewer import metal

    def stop(*_args, **_kwargs):
        raise Cancelled("stopped")

    monkeypatch.setattr(metal, "parse_def", stop)
    dbs = tmp_path / "dbs"
    data = _build([TOP, SUB], dump_db=str(dbs))
    assert not os.path.exists(str(dbs)) or not os.listdir(str(dbs))
    assert any("no db written" in warning for warning in data.warnings)


def test_a_version_from_another_build_is_refused(tmp_path):
    """The format has a version, and a db that is not this format is a refusal rather than a
    guess about what its numbers mean."""
    dbs = tmp_path / "dbs"
    _build([TOP, SUB], dump_db=str(dbs))
    _as_v1(dbs / "top.def.db", format=metal_db.DB_FORMAT + 1)

    again = _build([TOP, SUB], db_paths=_db_paths(dbs))
    assert "TOP" not in again.reused and "SUB" in again.reused


def test_an_old_style_db_still_loads_and_is_still_refused_by_placement(tmp_path, whole):
    """Both halves of keeping the v1 reader, on a v1 db.

    A db written before the geometry section is an npz with grids and no shapes, so every check it
    passed then still applies to it. It loads and rebuilds exactly as it did - and one whose
    placement belongs to another design is refused by name rather than drawn at (0, 0), which is
    the refusal the geometry section replaced for the container that has shapes in it.
    """
    dbs = tmp_path / "dbs"
    _build([TOP, SUB], dump_db=str(dbs))
    for name in ("top.def.db", "sub.def.db"):
        _as_v1(dbs / name)

    again = _build([TOP, SUB], db_paths=_db_paths(dbs))
    assert again.reused == ["TOP", "SUB"] and again.replayed == []
    assert again.warnings == []
    _same_map(again, whole)

    # The second half: the same v1 file, dumped by a run that had no parent to place it.
    other = tmp_path / "other"
    _build([SUB], dump_db=str(other))
    _as_v1(other / "sub.def.db")
    top_only = _build([TOP])
    partial = _build([TOP], db_paths=[str(other / "sub.def.db")])
    assert partial.reused == [] and partial.replayed == []
    assert any("SUB" in warning and "not counted" in warning for warning in partial.warnings)
    _same_map(partial, top_only)


def test_a_truncated_db_is_reported_and_the_others_still_work(tmp_path, whole):
    """A file the reader cannot make sense of is a reason to parse, not a crash and not a silent
    skip: it finds no footer where it expects one, says so by name, and that DEF is read again.

    Truncation stands for the whole family - a foreign file and a half-written one fail in the
    same place, on the header the reader looks for - so what is left to pin is the consequence,
    which is why this test also checks the db *beside* the broken one still loads: a run handed a
    directory of dbs parses only what it has to.
    """
    dbs = tmp_path / "dbs"
    _build([TOP, SUB], dump_db=str(dbs))
    path = dbs / "top.def.db"
    data = path.read_bytes()
    path.write_bytes(data[: len(data) // 2])

    again = _build([TOP, SUB], db_paths=_db_paths(dbs))
    assert again.reused == ["SUB"]
    assert any("ignoring db top.def.db" in warning for warning in again.warnings)
    assert again.totals == whole.totals
    for key, grid in whole._grids.items():
        assert np.array_equal(np.asarray(again._grids[key]), np.asarray(grid)), key


def test_the_container_round_trips_every_record_kind(tmp_path):
    """The body is a record stream, so every kind of shape survives it: rectangles, diagonals
    (four coordinates and a half width) and polygons, whose ring is variable length - one record
    holding one shape, however many vertices it has."""
    part = str(tmp_path / "unit.part0")
    writer = metal_db.SectionWriter(part)
    writer.batch("rects", "M1", "signal",
                 np.array([[1, 2, 3, 4], [5, 6, 7, 8]], dtype=np.int32))
    writer.batch("diagonals", "M2", "power", np.array([[1, 2, 3, 4, 5]], dtype=np.int32))
    writer.batch("polygons", "M3", "signal",
                 np.array([0, 0, 10, 0, 10, 10, 0, 10], dtype=np.int32))
    writer.close()
    assert writer.counts == {"rects": 2, "diagonals": 1, "polygons": 1}
    # A second worker's part, appended to the same record name: the parent's merge is this, and
    # the batches of one name have to come back in the order they were written - a grid sums over
    # neighbouring shapes, and the order they are summed in is the order they were flushed in.
    second = str(tmp_path / "unit.part1")
    more = metal_db.SectionWriter(second)
    more.batch("rects", "M1", "signal", np.array([[9, 9, 9, 9]], dtype=np.int32))
    more.close()

    path = str(tmp_path / "unit.db")
    metal_db.write(path, header={"format": metal_db.DB_FORMAT, "block": "X", "frames": []},
                   grids={("M1", "signal"): np.zeros((2, 3), dtype=np.float32)},
                   parts=[part, second])
    db = metal_db.load(path)
    # Batch for batch, in the order they were written: one record per flush for the kinds the
    # stream buffers, and one per ring for a polygon, which has no batch of its own.
    got: Dict = {}
    for kind, layer, scope, packed in db.geometry():
        got.setdefault((kind, layer, scope), []).append(packed.tolist())
    assert got == {("rects", "M1", "signal"): [[[1, 2, 3, 4], [5, 6, 7, 8]], [[9, 9, 9, 9]]],
                   ("diagonals", "M2", "power"): [[[1, 2, 3, 4, 5]]],
                   ("polygons", "M3", "signal"): [[0, 0, 10, 0, 10, 10, 0, 10]]}
    # What was stored, as the header records it - the number a caller reads to know whether a db
    # can stand in for a parse at all, before reading a byte of its body.
    assert db.header["geometry"] == {"rects": 3, "diagonals": 1, "polygons": 1}
    assert db.has_geometry and np.array_equal(np.asarray(db.grids[("M1", "signal")]),
                                              np.zeros((2, 3), dtype=np.float32))


def test_the_replay_is_refused_when_the_shapes_are_no_longer_the_ones_wanted(tmp_path, caplog):
    """`min_segment` decided which shapes were stored, so a db written under a different one has
    the wrong shapes in it - and no amount of live rasterising puts the missing ones back.

    A re-parse, not a warning: the DEF is in the run and nothing is wrong with it, which is the
    same reading `min_layer` and `max_layer` get. What makes it a refusal at all is that the
    stored shapes are *shorter* than the ones this run wants, not that they are stale.
    """
    dbs = tmp_path / "dbs"
    _build([SUB], dump_db=str(dbs))
    fresh = _build([TOP, SUB], min_segment=1.0)
    with caplog.at_level("INFO", logger="vlsi_viewer.metal"):
        again = _build([TOP, SUB], db_paths=_db_paths(dbs), min_segment=1.0)
    assert again.reused == [] and again.replayed == []
    assert any("db for SUB not used" in record.getMessage()
               and "min_segment is" in record.getMessage() for record in caplog.records)
    assert again.warnings == []
    _same_map(again, fresh)


def test_a_changed_macro_lef_replays_the_stored_shapes(tmp_path):
    """The macro LEFs decide the blockage, which is recomputed live - so a db is still usable for
    its shapes when they change, and the map matches what the live LEFs say."""
    dbs = tmp_path / "dbs"
    _build([TOP, SUB], dump_db=str(dbs))

    cells = tmp_path / "cells.lef"
    shutil.copy(CELLS, cells)
    with open(str(cells), "a", encoding="utf-8") as handle:
        handle.write("\n# touched\n")

    with contextlib.redirect_stdout(io.StringIO()):
        fresh = build_metal([TOP, SUB], [str(cells)], [TECH], grid_size=10.0)
        again = build_metal([TOP, SUB], [str(cells)], [TECH], grid_size=10.0,
                            db_paths=_db_paths(dbs))
    assert again.reused == [] and again.replayed == ["TOP", "SUB"]
    _same_map(again, fresh)


def test_dump_only_writes_the_dbs_and_returns_without_a_window(tmp_path):
    """The point of the flag: several designs dumped side by side, none of them opening a GUI."""
    dbs = tmp_path / "dbs"
    code = main(["metal", "--def", TOP, SUB, "--lef", CELLS, "--tech-lef", TECH,
                 "--dump-db", str(dbs), "--dump-only"])
    assert code == 0
    assert sorted(os.listdir(str(dbs))) == ["sub.def.db", "top.def.db"]


def _one_sub_at_the_origin(tmp_path):
    """The sample's top, with its single sub-block placed at ( 0 0 ) N.

    That is the frame a standalone dump of the sub-block records, which is what makes this the
    09-17 run-2 case: the frame check cannot tell "placed at the design's origin" from "written as
    its own root", so only the grid geometry can refuse the db.
    """
    lines = (tmp_path / "top.def").read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("COMPONENTS"))
    end = next(i for i, line in enumerate(lines) if line.startswith("END COMPONENTS"))
    lines[start:end + 1] = ["COMPONENTS 1 ;",
                            "- u0 SUB + SOURCE DIST + PLACED ( 0 0 ) N ;",
                            "END COMPONENTS"]
    (tmp_path / "top.def").write_text("\n".join(lines) + "\n")
    return str(tmp_path / "top.def")


def test_a_standalone_dump_takes_the_replay_when_its_grids_do_not_fit(tmp_path, caplog):
    """The 09-17 run 2: the db passes every check but its grids are its own die's.

    Before the geometry comparison, `Bins.add_grid` raised `grid is (52, 40), this grid's is
    (62, 62)` mid-build - an error about the rasteriser for a problem with the db. Then it became
    a refusal; now the grids are refused *and the stored shapes are used*, because the die and the
    frame are properties of the run that rasterises and not of the shapes. What it must draw is
    what parsing both DEFs draws.
    """
    _sample_pair(tmp_path)
    top = _one_sub_at_the_origin(tmp_path)
    sub = str(tmp_path / "sub.def")
    dbs = tmp_path / "dbs"
    _build([top], dump_db=str(dbs))                    # the top alone: SUB is a candidate, at (0,0)
    _build([sub], dump_db=str(dbs))                    # SUB alone: its own root at (0,0)

    live = _build([top, sub])
    with caplog.at_level("INFO", logger="vlsi_viewer.metal"):
        again = _build([], db_paths=_db_paths(dbs))    # no exception, no warning, no re-parse
    assert again.reused == ["TOP"] and again.replayed == ["SUB"]
    assert again.warnings == []
    _same_map(again, live)
    # Said out loud, because a run that quietly re-rasterised a block would look like one that had
    # simply been slow - and the fast path was declined for a reason the user can act on.
    said = " ".join(record.getMessage() for record in caplog.records)
    assert "grids do not match this run" in said and "this run's is" in said
    assert "replaying its stored shapes" in said


def test_mismatch_compares_the_grid_and_the_die(tmp_path):
    """The unit behind that refusal: same cell count over a shifted die is still a refusal."""
    dbs = tmp_path / "dbs"
    _build([TOP, SUB], dump_db=str(dbs))
    db = metal_db.load(str(dbs / "top.def.db"))
    params = db.header["params"]
    same = (db.header["rows"], db.header["cols"], db.header["extent"])

    assert metal_db.mismatch(db, params=params, geometry=same) is None
    wrong_cells = metal_db.mismatch(db, params=params,
                                    geometry=(same[0] + 1, same[1], same[2]))
    assert wrong_cells and "this run's is" in wrong_cells
    shifted = list(same[2])
    shifted[2] += 10.0
    wrong_die = metal_db.mismatch(db, params=params,
                                  geometry=(same[0], same[1], tuple(shifted)))
    assert wrong_die and "this run's is" in wrong_die
