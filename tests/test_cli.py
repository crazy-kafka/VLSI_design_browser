import pytest

from vlsi_viewer import config
from vlsi_viewer.cli import parse_args


def test_defaults():
    args = parse_args(["inst.json", "cell.json"])
    assert args.instance_info == "inst.json"
    assert args.cell_info == "cell.json"
    assert args.min_instances == config.DEFAULT_MIN_INST_COUNT
    assert args.include_macros is False
    assert args.compare is None
    assert args.cache_dir is None
    assert args.force is False


def test_flags():
    args = parse_args([
        "inst.json", "cell.json",
        "--compare", "i2.json", "c2.json",
        "--min-instances", "0",
        "--include-macros",
        "--cache-dir", "/tmp/cache",
        "--force",
    ])
    assert args.compare == ["i2.json", "c2.json"]
    assert args.min_instances == 0
    assert args.include_macros is True
    assert args.cache_dir == "/tmp/cache"
    assert args.force is True


def test_positionals_required():
    with pytest.raises(SystemExit):
        parse_args([])
    with pytest.raises(SystemExit):
        parse_args(["only_one.json"])


def test_version_flag():
    with pytest.raises(SystemExit):
        parse_args(["--version"])
