import pytest

from vlsi_viewer import config
from vlsi_viewer.cli import parse_args


def test_defaults():
    args = parse_args(["--cell_info", "cell.json", "--block_info", "a.json"])
    assert args.cell_info == "cell.json"
    assert args.block_info == ["a.json"]
    assert args.min_instances == config.DEFAULT_MIN_INST_COUNT
    assert args.include_macros is False
    assert args.compare_block_info is None
    assert args.cache_dir is None
    assert args.force is False
    assert args.verbose is False


def test_multiple_blocks_and_flags():
    args = parse_args([
        "--cell_info", "cell.json",
        "--block_info", "a.json", "b.json", "c.json",
        "--compare_block_info", "a2.json", "b2.json",
        "--min-instances", "0",
        "--include-macros",
        "--cache-dir", "/tmp/cache",
        "--force",
        "--verbose",
    ])
    assert args.block_info == ["a.json", "b.json", "c.json"]
    assert args.compare_block_info == ["a2.json", "b2.json"]
    assert args.min_instances == 0
    assert args.include_macros is True
    assert args.cache_dir == "/tmp/cache"
    assert args.force is True
    assert args.verbose is True


def test_required_flags():
    with pytest.raises(SystemExit):
        parse_args([])
    with pytest.raises(SystemExit):
        parse_args(["--cell_info", "cell.json"])  # missing --block_info


def test_version_flag():
    with pytest.raises(SystemExit):
        parse_args(["--version"])
