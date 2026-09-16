"""The `metal` subcommand.

No Qt anywhere: these exercise argument parsing and the pre-window error path, which is
where a CLI's mistakes actually live. `_run_metal` builds the grids before creating a
QApplication, so an unreadable input exits with a message and a status code and never
reaches a window.
"""
import pytest

from vlsi_viewer import config
from vlsi_viewer.cli import main, parse_args

SAMPLE = "sample_data/metal"
METAL_ARGS = ["metal", "--def", f"{SAMPLE}/top.def", "--lef", f"{SAMPLE}/cells.lef",
              "--tech-lef", f"{SAMPLE}/tech.lef"]


def test_metal_keeps_only_the_options_it_reads():
    """`--verbose` is read for every subcommand; the pipeline group is not read for metal."""
    args = parse_args(METAL_ARGS)
    assert args.verbose is False
    for attribute in ("min_instances", "include_macros", "cache_dir", "force"):
        assert not hasattr(args, attribute), attribute


def test_metal_defaults():
    args = parse_args(METAL_ARGS)
    assert args.cmd == "metal"
    assert args.def_files == [f"{SAMPLE}/top.def"]
    assert args.lef == [f"{SAMPLE}/cells.lef"]
    assert args.tech_lef == [f"{SAMPLE}/tech.lef"]
    assert args.grid_size == config.DEFAULT_METAL_GRID_SIZE == 10.0
    assert args.macro_block_layers == config.DEFAULT_MACRO_BLOCK_LAYERS == 4
    assert args.min_segment_length is None      # each layer's track pitch
    assert args.top is None
    assert args.verbose is False


def test_the_layer_range_defaults_to_the_whole_stack():
    args = parse_args(METAL_ARGS)
    assert args.min_layer is None and args.max_layer is None


def test_the_layer_range_parses_in_both_spellings():
    """Hyphens for the group's other flags, underscores for the two `build_metal` takes."""
    assert parse_args(METAL_ARGS + ["--min-layer", "2", "--max-layer", "11"]).min_layer == 2
    underscored = parse_args(METAL_ARGS + ["--min_layer", "2", "--max_layer", "11"])
    assert (underscored.min_layer, underscored.max_layer) == (2, 11)


def test_the_layer_range_reaches_the_builder(monkeypatch, capsys):
    """A flag the CLI parses and then drops looks exactly like a flag that works.

    `sample_data/metal/quickstart.py` had one of those - its `--check` path discarded the
    arguments it did not know - so the wiring is pinned rather than assumed.
    """
    seen = {}

    def fake(def_paths, lef_paths, tech_paths, **kwargs):
        seen.update(kwargs)
        raise ValueError("recorded")

    monkeypatch.setattr("vlsi_viewer.metal.build_metal", fake)
    assert main(METAL_ARGS + ["--min_layer", "2", "--max_layer", "11"]) == 1
    assert (seen["min_layer"], seen["max_layer"]) == (2, 11)
    assert "recorded" in capsys.readouterr().err


@pytest.mark.parametrize("extra", [["--min-layer", "0"], ["--min-layer", "5", "--max-layer", "3"],
                                   ["--max-layer", "99"]])
def test_a_range_past_the_stack_errors_without_a_traceback(extra, capsys):
    """`--min-layer 0` is the trap: `layers[lo - 1:hi]` is `layers[-1:hi]`, which is empty.

    An empty stack does not fail where the mistake is - it fails when the window asks for its
    first map - so the range is refused up front and reported like any other bad input.
    """
    assert main(METAL_ARGS + extra) == 1
    err = capsys.readouterr().err
    assert "error:" in err and "layer range" in err
    assert "Traceback" not in err


def test_the_help_says_how_the_range_is_counted(capsys):
    """The number is a stack position, and the fallback counts from the bottom of the whole
    stack - neither is guessable from the flag's name."""
    with pytest.raises(SystemExit):
        parse_args(METAL_ARGS + ["--help"])
    # Unwrapped: argparse breaks the help to the terminal width, so a phrase can carry a
    # newline in the middle of it.
    out = " ".join(capsys.readouterr().out.split())
    assert "1-based position in the stack" in out
    assert "reported as filtered" in out
    assert "bottom layers of the whole stack" in out


def test_metal_flags():
    args = parse_args(METAL_ARGS + ["--grid-size", "2.5", "--macro-block-layers", "0",
                                    "--min-segment-length", "0", "--top", "CORE",
                                    "--verbose"])
    assert args.grid_size == 2.5
    assert args.macro_block_layers == 0
    assert args.min_segment_length == 0.0
    assert args.top == "CORE"
    assert args.verbose is True


def test_metal_accepts_several_defs_and_tech_lefs():
    args = parse_args(["metal", "--def", "a.def", "b.def", "--lef", "c.lef",
                       "--tech-lef", "t1.lef", "t2.lef"])
    assert args.def_files == ["a.def", "b.def"]
    assert args.tech_lef == ["t1.lef", "t2.lef"]


@pytest.mark.parametrize("missing", ["--lef", "--tech-lef"])
def test_metal_requires_its_lefs(missing):
    """The LEFs are not optional even with dbs: the layer table and the blockage are rebuilt
    from them on every run, so a db can never stand in for either."""
    argv = [a for a in METAL_ARGS]
    index = argv.index(missing)
    del argv[index:index + 2]
    with pytest.raises(SystemExit):
        parse_args(argv)


def test_metal_needs_a_def_or_a_db(capsys):
    """`--def` moved from argparse to a run-time check, because a db-only run has none."""
    argv = [a for a in METAL_ARGS if a not in ("--def", f"{SAMPLE}/top.def")]
    args = parse_args(argv)
    assert args.def_files is None
    assert main(argv) == 1
    assert "needs --def, --db, or both" in capsys.readouterr().err


def test_dump_only_needs_somewhere_to_dump(capsys):
    assert main(METAL_ARGS + ["--dump_only"]) == 1
    assert "--dump_only needs --dump-db" in capsys.readouterr().err


@pytest.mark.parametrize("extra", [
    ["--compare_def", "x.def"],
    ["--compare_verilog", "x.v"],
    ["--physical_mode"],
    ["--contour_gap", "2.0"],
    ["--out", "somewhere"],
    # The JSON pipeline's options: metal converts no JSON, builds no tree and caches
    # nothing, so these were accepted and ignored - and their help text described a
    # hierarchy filter for a mode with no hierarchy.
    ["--min-instances", "10"],
    ["--include-macros"],
    ["--cache-dir", "somewhere"],
    ["--force"],
])
def test_metal_has_no_compare_no_physical_mode_no_contour_gap(extra):
    """Absent flags rather than runtime rejections, as the other modes do it.

    A routing map has nothing to compare against and no instance boxes to contour, so the
    capability is expressed by the flag simply not existing.
    """
    with pytest.raises(SystemExit):
        parse_args(METAL_ARGS + extra)


def test_metal_is_required_to_choose_a_command():
    with pytest.raises(SystemExit):
        parse_args([])


def test_an_unreadable_def_errors_without_a_window(capsys):
    """The error path has to work before Qt exists, or a bad path opens a blank window."""
    code = main(["metal", "--def", "does/not/exist.def", "--lef", f"{SAMPLE}/cells.lef",
                 "--tech-lef", f"{SAMPLE}/tech.lef"])
    assert code == 1
    assert "error:" in capsys.readouterr().err


def test_two_unrelated_defs_are_reported_not_drawn(capsys):
    """Two independent DEFs have no single coordinate system, and the CLI says so."""
    code = main(["metal", "--def", f"{SAMPLE}/top.def", f"{SAMPLE}/orphan.def",
                 "--lef", f"{SAMPLE}/cells.lef", "--tech-lef", f"{SAMPLE}/tech.lef"])
    assert code == 1
    err = capsys.readouterr().err
    assert "exactly one top-level" in err
    assert "ORPHAN" in err and "TOP" in err
