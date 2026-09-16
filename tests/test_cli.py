"""CLI parsing for the three input flows.

The flags are now grouped under subcommands (``json`` / ``verilog`` / ``def``), so the
bare-flags form is a usage error - the tests below pin both that break and the shape of
each subcommand.
"""
import json

import pytest

from vlsi_viewer import config
from vlsi_viewer.cli import parse_args, resolve_inputs

SAMPLE = "sample_data/eda"
JSON_ARGS = ["json", "--cell_info", "cell.json", "--block_info", "a.json"]
VERILOG_ARGS = ["verilog", "--verilog", "core.v", "--lef", "cells.lef", "--top", "core"]
DEF_ARGS = ["def", "--def", "core.def", "--lef", "cells.lef"]


def test_json_defaults():
    args = parse_args(JSON_ARGS)
    assert args.cmd == "json"
    assert args.cell_info == "cell.json"
    assert args.block_info == ["a.json"]
    assert args.min_instances == config.DEFAULT_MIN_INST_COUNT
    assert args.include_macros is False
    assert args.compare_block_info is None
    assert args.cache_dir is None
    assert args.force is False
    assert args.verbose is False
    assert args.grid_size == config.DEFAULT_GRID_SIZE
    assert args.contour_gap is None
    assert args.physical_mode is False


def test_json_multiple_blocks_and_flags():
    args = parse_args([
        "json",
        "--cell_info", "cell.json",
        "--block_info", "a.json", "b.json", "c.json",
        "--compare_block_info", "a2.json", "b2.json",
        "--min-instances", "0",
        "--include-macros",
        "--cache-dir", "/tmp/cache",
        "--force",
        "--verbose",
        "--grid_size", "5.0",
        "--contour_gap", "12.0",
    ])
    assert args.block_info == ["a.json", "b.json", "c.json"]
    assert args.compare_block_info == ["a2.json", "b2.json"]
    assert args.min_instances == 0
    assert args.include_macros is True
    assert args.cache_dir == "/tmp/cache"
    assert args.force is True
    assert args.verbose is True
    assert args.grid_size == 5.0
    assert args.contour_gap == 12.0


def test_json_required_flags():
    with pytest.raises(SystemExit):
        parse_args(["json"])
    with pytest.raises(SystemExit):
        parse_args(["json", "--cell_info", "cell.json"])  # missing --block_info


def test_version_flag():
    with pytest.raises(SystemExit):
        parse_args(["--version"])


def test_subcommand_is_required():
    """Breaking change: the flags moved under subcommands, so bare flags now fail."""
    with pytest.raises(SystemExit):
        parse_args([])
    with pytest.raises(SystemExit):
        parse_args(["--cell_info", "cell.json", "--block_info", "a.json"])


def test_verilog_subcommand():
    args = parse_args(VERILOG_ARGS + ["--compare_verilog", "v2.v"])
    assert args.cmd == "verilog"
    assert args.verilog == ["core.v"]
    assert args.lef == ["cells.lef"]
    assert args.top == "core"
    assert args.compare_verilog == ["v2.v"]
    assert args.compare_top is None       # falls back to --top
    assert args.out is None
    assert args.verbose is False

    with pytest.raises(SystemExit):
        parse_args(["verilog", "--verilog", "core.v"])   # missing --lef and --top


def test_verilog_has_no_physical_mode():
    """A netlist has no placement, so the flag is absent rather than rejected later."""
    with pytest.raises(SystemExit):
        parse_args(VERILOG_ARGS + ["--physical_mode"])
    with pytest.raises(SystemExit):
        parse_args(VERILOG_ARGS + ["--grid_size", "2.0"])


def test_def_subcommand():
    args = parse_args(DEF_ARGS + ["--physical_mode", "--grid_size", "2.0"])
    assert args.cmd == "def"
    assert args.def_files == ["core.def"]     # dest is not `def`: that is a keyword
    assert args.physical_mode is True
    assert args.grid_size == 2.0
    assert args.top is None              # falls back to the DEF DESIGN name

    # physical and compare stay mutually exclusive, as in the json flow
    with pytest.raises(SystemExit):
        parse_args(DEF_ARGS + ["--physical_mode", "--compare_def", "v2.def"])
    assert parse_args(DEF_ARGS + ["--compare_def", "v2.def"]).compare_def == ["v2.def"]


def test_resolve_inputs_def_returns_in_memory_data(tmp_path):
    """`def` converts to the very structures the `json` subcommand reads - in memory."""
    from vlsi_viewer.loader import load_block, load_cell_info

    args = parse_args(["def", "--def", f"{SAMPLE}/core.def", "--lef", f"{SAMPLE}/cells.lef"])
    cells, blocks, compare, pins = resolve_inputs(args)
    assert compare is None
    assert isinstance(cells, dict) and isinstance(blocks[0], dict)
    # The def flow is the one that can carry pin geometry, for the pin-density map. The
    # sample LEF's rails are already out of it: USE POWER/GROUND never reaches this table.
    assert pins and set(pins) <= set(cells)
    assert all(centres for centres in pins.values())

    name, df, boundary = load_block(blocks[0])
    assert name == "core" and boundary is not None and len(df) > 0
    assert len(load_cell_info(cells)) == 20


def test_no_file_is_written_without_out(tmp_path):
    """A def/verilog run must leave the input directory exactly as it found it."""
    import os

    before = _tree(SAMPLE)
    for argv in (["def", "--def", f"{SAMPLE}/core.def", "--lef", f"{SAMPLE}/cells.lef"],
                 ["verilog", "--verilog", f"{SAMPLE}/core.v",
                  "--lef", f"{SAMPLE}/cells.lef", "--top", "core"]):
        resolve_inputs(parse_args(argv))
    assert _tree(SAMPLE) == before
    assert not [p for p in _tree(SAMPLE) if p.endswith(".json")]


def _block_name(top, compare=False):
    """``<top>.instance_info.json`` / ``<top>.instance_info.compare.json`` - the rule.

    The name follows the design's top cell, not the input file.
    """
    return f"{top}.instance_info" + (".compare" if compare else "") + ".json"


# Per flow: the CLI arguments, and the name the instance JSON is dumped under. Both
# flows produce a design whose top is `core`.
OUT_FLOWS = {
    "def": (["def", "--def", f"{SAMPLE}/core.def", "--lef", f"{SAMPLE}/cells.lef"],
            _block_name("core")),
    "verilog": (["verilog", "--verilog", f"{SAMPLE}/core.v",
                 "--lef", f"{SAMPLE}/cells.lef", "--top", "core"],
                _block_name("core")),
}


@pytest.mark.parametrize("flow", sorted(OUT_FLOWS))
def test_out_dump_is_a_faithful_copy(tmp_path, flow):
    """`--out` must write the converted structures exactly, not an approximation.

    Both the cell library and the block are checked for content equality with the
    in-memory data, and then loaded back to confirm the dumped *pair* reproduces the
    same design - which is the point of dumping them at all.
    """
    import pandas as pd

    from vlsi_viewer.loader import load_block, load_cell_info
    from vlsi_viewer.metrics import build_design

    argv, block_name = OUT_FLOWS[flow]
    cells, blocks, _compare, _pins = resolve_inputs(parse_args(argv + ["--out", str(tmp_path)]))

    cell_path = tmp_path / "cell_info.json"
    block_path = tmp_path / block_name
    assert cell_path.exists() and block_path.exists()
    assert json.loads(cell_path.read_text(encoding="utf-8")) == cells
    assert json.loads(block_path.read_text(encoding="utf-8")) == blocks[0]

    load_block(str(block_path))
    load_cell_info(str(cell_path))
    from_memory = build_design(blocks, cells)
    from_disk = build_design([str(block_path)], str(cell_path))
    pd.testing.assert_frame_equal(from_memory.hier, from_disk.hier)
    assert from_memory.roots == from_disk.roots


@pytest.mark.parametrize("flow", sorted(OUT_FLOWS))
def test_compare_dump_keeps_both_sides(tmp_path, flow):
    """Neither side of a diff may be lost, even when both name the same top cell.

    A diff's two sides are normally the *same* file name in different directories
    (`v1/core.def` against `v2/core.def`) and describe the same design, so both infer the
    top `core`; only the `.compare` suffix keeps them apart.
    """
    import os
    import shutil

    argv, block_name = OUT_FLOWS[flow]
    flag = "--def" if flow == "def" else "--verilog"
    source = argv[argv.index(flag) + 1]

    v1, v2 = tmp_path / "v1", tmp_path / "v2"
    v1.mkdir(), v2.mkdir()
    for directory in (v1, v2):
        shutil.copyfile(source, directory / os.path.basename(source))

    out = tmp_path / "out"
    argv = [a.replace(source, str(v1 / os.path.basename(source))) for a in argv]
    argv += (["--compare_def", str(v2 / os.path.basename(source))] if flow == "def"
             else ["--compare_verilog", str(v2 / os.path.basename(source))])
    resolve_inputs(parse_args(argv + ["--out", str(out)]))

    assert (out / block_name).exists()
    assert (out / _block_name("core", compare=True)).exists()
    assert len(os.listdir(out)) == 3      # both blocks, plus the one shared cell library


def test_merged_lefs_write_one_cell_dump(tmp_path):
    """Several LEF files are ONE library, so `--out` writes a single `cell_info.json`."""
    import os
    import shutil

    second = tmp_path / "extra.lef"
    shutil.copyfile(f"{SAMPLE}/cells.lef", second)
    out = tmp_path / "out"
    resolve_inputs(parse_args([
        "def", "--def", f"{SAMPLE}/core.def",
        "--lef", f"{SAMPLE}/cells.lef", str(second), "--out", str(out)]))
    assert sorted(os.listdir(out)) == ["cell_info.json", _block_name("core")]


def test_merged_verilog_files_write_one_dump(tmp_path):
    """Several Verilog files are ONE netlist, so `--out` writes one block file."""
    import os
    import shutil

    second = tmp_path / "extra.v"
    shutil.copyfile(f"{SAMPLE}/core.v", second)
    out = tmp_path / "out"
    _cells, blocks, _compare, _pins = resolve_inputs(parse_args([
        "verilog", "--verilog", f"{SAMPLE}/core.v", str(second),
        "--lef", f"{SAMPLE}/cells.lef", "--top", "core", "--out", str(out)]))
    assert len(blocks) == 1
    assert sorted(os.listdir(out)) == ["cell_info.json", _block_name("core")]


def test_block_dump_is_named_after_the_top_cell(tmp_path):
    """The name follows the design, not the input file.

    In def mode the top is inferred from the DEF `DESIGN` statement; `--top` overrides it,
    and so overrides the dump name with it.
    """
    import os

    for extra, top in (([], "core"), (["--top", "renamed"], "renamed")):
        out = tmp_path / f"out_{top}"
        resolve_inputs(parse_args([
            "def", "--def", f"{SAMPLE}/core.def", "--lef", f"{SAMPLE}/cells.lef"]
            + extra + ["--out", str(out)]))
        assert sorted(os.listdir(out)) == ["cell_info.json", _block_name(top)]


def test_dump_warns_when_two_inputs_share_an_output_name(tmp_path, caplog):
    """Two same-named DEFs are separate blocks, so their dumps must not be silent."""
    import logging
    import os
    import shutil

    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    for directory in (a, b):
        shutil.copyfile(f"{SAMPLE}/core.def", directory / "core.def")

    with caplog.at_level(logging.WARNING, logger="vlsi_viewer.cli"):
        resolve_inputs(parse_args([
            "def", "--def", str(a / "core.def"), str(b / "core.def"),
            "--lef", f"{SAMPLE}/cells.lef", "--out", str(tmp_path / "out")]))
    assert any("same output name" in r.message for r in caplog.records)


def test_resolve_inputs_verilog_multi_file_is_one_design(tmp_path):
    args = parse_args(["verilog", "--verilog", f"{SAMPLE}/core.v",
                       f"{SAMPLE}/core.v",      # the same netlist twice
                       "--compare_verilog", f"{SAMPLE}/core.v",
                       "--lef", f"{SAMPLE}/cells.lef", "--top", "core"])
    cells, blocks, compare, pins = resolve_inputs(args)
    assert pins is None          # verilog has no LEF geometry to take pins from
    # several files make ONE design, so one block here and one in the compare set
    assert len(blocks) == 1 and len(compare) == 1
    assert set(blocks[0]["instances"]) == set(compare[0]["instances"])


def _tree(root):
    """Relative paths of every file under ``root``."""
    import os

    return {os.path.relpath(os.path.join(dirpath, name), root)
            for dirpath, _dirnames, filenames in os.walk(root)
            for name in filenames}


def test_resolve_inputs_json_passes_through():
    args = parse_args(JSON_ARGS)
    assert resolve_inputs(args) == ("cell.json", ["a.json"], None, None)


def test_quickstart_shortcuts_are_valid():
    """Every quickstart shortcut must parse, and its sample files must exist."""
    import os

    import quickstart

    for name in quickstart.SHORTCUTS:
        argv = quickstart.argv_for(name)
        parse_args(argv)          # raises SystemExit if a shortcut drifts from the CLI
        sources = [a for a in argv if a.endswith((".json", ".def", ".v", ".lef"))]
        assert sources, argv
        for path in sources:
            assert os.path.exists(path), f"{name}: missing sample {path}"
