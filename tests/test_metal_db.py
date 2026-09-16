"""The metal mode's intermediate db: dump, reuse, and every way a db is refused.

The centrepiece is equivalence: a map rebuilt from dbs must be the *same map*, not a similar one -
so the grids are compared with `array_equal` and the counters exactly. Everything else here is a
refusal that has to happen for the right reason, because a db that is used when it should not be is
a wrong map that loads fast, which is the one outcome worth refusing.
"""
import contextlib
import io
import os
import shutil

import numpy as np
import pytest

from vlsi_viewer import metal_db
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


def test_the_sub_block_dump_workflow(tmp_path):
    """The parallel-dump path: a top-only dump, then each sub-block dumped against the parent's
    *db* rather than the parent's DEF - and the two together equal the one-shot build.

    This is what the remembered components are for: a top dumped alone cannot know which of its
    components are blocks, so it records the candidates' local placements and the resolution
    happens here, when the sub-block's DEF arrives.
    """
    dbs = tmp_path / "dbs"
    whole = _build([TOP, SUB])
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


def test_a_bare_sub_dump_is_refused_rather_than_drawn_in_the_wrong_place(tmp_path):
    """A sub-block dumped with no parent records the placement it saw - its own origin - and the
    run that has the parent refuses it by name, instead of stacking its wiring at (0, 0)."""
    dbs = tmp_path / "dbs"
    _build([SUB], dump_db=str(dbs))                       # no parent: SUB is its own root
    with contextlib.redirect_stdout(io.StringIO()):
        again = build_metal([TOP], [CELLS], [TECH], grid_size=10.0, db_paths=_db_paths(dbs))
    assert again.reused == []
    assert any("SUB" in warning and "not counted" in warning for warning in again.warnings)


def test_an_unreadable_db_is_reported_and_ignored(tmp_path):
    """A truncated or foreign file is a reason to parse, not a crash and not a silent skip."""
    dbs = tmp_path / "dbs"
    dbs.mkdir()
    (dbs / "top.def.db").write_bytes(b"not an npz at all")
    fresh = _build([TOP, SUB])
    again = _build([TOP, SUB], db_paths=_db_paths(dbs))
    assert again.reused == []
    assert any("ignoring db" in warning for warning in again.warnings)
    assert again.totals == fresh.totals


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
    db = metal_db.load(str(dbs / "top.def.db"))
    db.header["format"] = metal_db.DB_FORMAT + 1
    metal_db.save(str(dbs / "top.def.db"), db)

    again = _build([TOP, SUB], db_paths=_db_paths(dbs))
    assert "TOP" not in again.reused and "SUB" in again.reused


def test_dump_only_writes_the_dbs_and_returns_without_a_window(tmp_path):
    """The point of the flag: several designs dumped side by side, none of them opening a GUI."""
    dbs = tmp_path / "dbs"
    code = main(["metal", "--def", TOP, SUB, "--lef", CELLS, "--tech-lef", TECH,
                 "--dump-db", str(dbs), "--dump-only"])
    assert code == 0
    assert sorted(os.listdir(str(dbs))) == ["sub.def.db", "top.def.db"]
