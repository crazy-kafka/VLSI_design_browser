"""CLI parsing for the three input flows.

The flags are now grouped under subcommands (``json`` / ``verilog`` / ``def``), so the
bare-flags form is a usage error - the tests below pin both that break and the shape of
each subcommand.
"""
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


def test_resolve_inputs_def_converts_to_json(tmp_path):
    """`def` must produce the very JSON the `json` subcommand would have taken."""
    from vlsi_viewer.loader import load_block, load_cell_info

    args = parse_args(["def", "--def", f"{SAMPLE}/core.def", "--lef", f"{SAMPLE}/cells.lef",
                       "--out", str(tmp_path)])
    cell_info, blocks, compare = resolve_inputs(args)
    assert compare is None
    assert cell_info == str(tmp_path / "cells.lef.cell_info.json")
    assert blocks == [str(tmp_path / "core.def.instance_info.json")]

    name, df, boundary = load_block(blocks[0])
    assert name == "core" and boundary is not None and len(df) > 0
    assert len(load_cell_info(cell_info)) == 20


def test_resolve_inputs_verilog_and_compare(tmp_path):
    args = parse_args(["verilog", "--verilog", f"{SAMPLE}/core.v",
                       "--compare_verilog", f"{SAMPLE}/core.v",
                       "--lef", f"{SAMPLE}/cells.lef", "--top", "core",
                       "--out", str(tmp_path)])
    cell_info, blocks, compare = resolve_inputs(args)
    assert len(blocks) == 1 and len(compare) == 1
    # distinct names, so a core.v and a core.def in one directory cannot collide
    assert blocks[0].endswith("core.v.instance_info.json")
    assert compare[0].endswith("core.v.instance_info.json")
    assert cell_info.endswith("cells.lef.cell_info.json")


def test_resolve_inputs_json_passes_through():
    args = parse_args(JSON_ARGS)
    assert resolve_inputs(args) == ("cell.json", ["a.json"], None)


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
