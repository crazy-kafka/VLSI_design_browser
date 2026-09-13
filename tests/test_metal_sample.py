"""The committed metal sample.

Loaded by path, the way `tests/test_sample_generator.py` loads the physical generator, so a
standalone script under `sample_data/` can be tested without being a package. Nothing here
regenerates the files: `verify()` only reads them, and a test that rewrote the sample would
be testing the writer rather than the artefact that ships.
"""
import importlib.util
import os

import pytest

SAMPLE = "sample_data/metal"
GENERATOR = os.path.join(SAMPLE, "generate_metal.py")

FILES = ("tech.lef", "cells.lef", "sub.def", "top.def", "orphan.def")


@pytest.fixture(scope="module")
def generator():
    spec = importlib.util.spec_from_file_location("generate_metal", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_sample_files_are_committed():
    for name in FILES:
        path = os.path.join(SAMPLE, name)
        assert os.path.exists(path), f"{name} is missing from the sample"
        assert os.path.getsize(path) > 200, f"{name} looks empty"


def test_generator_verify_passes(generator, capsys):
    """The generator's own verification, which re-parses the sample through the real path.

    It asserts the awkward tech-LEF shapes parse to the values written, that the macro and
    pitch-factor capacity rules hold, and that the map has a spread of values rather than
    being flat or saturated - the checks that a flat sample would slip past if only
    min/max were asserted.
    """
    generator.verify()
    printed = capsys.readouterr().out
    assert "verify: OK" in printed


# The committed sample, counted end to end. A golden of the whole vector rather than one
# counter, so a future fast path is judged on everything it produces at once - the numbers
# below were measured, and the two fixtures differ in shape: `sub.def` is signal wiring with
# jogs, `top.def` is a power grid with a filled ring.
SAMPLE_SHAPES = {
    "sub.def": {"vias": 0, "jogs": 135, "degenerate": 0, "unknown": 0, "unusable": 0,
                "polygon_edges": 0, "emitted": 19817, "rects": 19817, "polygons": 0,
                "area_um2": 84491.294890},
    "top.def": {"vias": 0, "jogs": 0, "degenerate": 0, "unknown": 0, "unusable": 0,
                "polygon_edges": 3, "emitted": 9, "rects": 8, "polygons": 1,
                "area_um2": 15242.880000},
}


@pytest.mark.parametrize("name", sorted(SAMPLE_SHAPES))
def test_the_committed_sample_produces_exactly_these_shapes(name):
    """Every counter and the geometry itself, for both committed DEFs."""
    import contextlib
    import io

    from vlsi_viewer.parsers.routing import ShapeStream, TechRouting, parse_def

    class Collect:
        def __init__(self):
            self.rects = []
            self.polygons = []

        def add_rects(self, layer_index, scope, x0, y0, x1, y1):
            for index in range(x0.size):
                self.rects.append((float(x1[index]) - float(x0[index])) *
                                  (float(y1[index]) - float(y0[index])))

        def add_diagonal(self, *args):
            pass

        def add_polygon(self, layer_index, scope, ring):
            self.polygons.append(ring)

    with contextlib.redirect_stdout(io.StringIO()):
        tech = TechRouting.read([os.path.join(SAMPLE, "tech.lef")])
        sink = Collect()
        stream = ShapeStream(tech, sink)
        parse_def(os.path.join(SAMPLE, name), stream=stream)
        stream.flush()
    from vlsi_viewer.parsers.routing import SHAPE_COUNTERS

    expected = SAMPLE_SHAPES[name]
    got = {key: getattr(stream, attribute) for key, attribute in SHAPE_COUNTERS}
    got.update(rects=len(sink.rects), polygons=len(sink.polygons),
               area_um2=sum(sink.rects))
    assert got == pytest.approx(expected, rel=1e-9)


def test_the_tech_lef_carries_the_awkward_shapes(generator):
    """Each one corresponds to a parser bug found in a real file; losing one loses the test."""
    text = generator.tech_lef_text()
    assert text.count("SPACING 0.07 ;") >= 1          # M2's unqualified default
    assert "SPACING 0.90 RANGE" in text               # the widest clause, written last
    assert "SPACINGTABLE" in text                     # M6's table
    assert "MINWIDTH" in text and "  WIDTH 0.20 ;" not in text.split("LAYER M7")[1].split(
        "END M7")[0]                                  # M7 has no WIDTH of its own
    assert "DIRECTION VERTICAL;" in text              # M8: no space before the semicolon
    assert "TYPE CUT" in text and "TYPE OVERLAP" in text


def test_the_top_def_instantiates_the_sub_four_times(generator, tmp_path):
    """The hierarchy is what makes frame composition for wires part of the sample."""
    text = open(os.path.join(SAMPLE, "top.def")).read()
    assert text.count(" SUB + SOURCE DIST + PLACED") == 4
    orientations = {line.rsplit(")", 1)[1].strip().rstrip(";")
                    for line in text.splitlines() if " SUB " in line and "PLACED" in line}
    assert len(orientations) == 4, orientations


def test_no_duplicate_component_names(generator):
    """Duplicate names are merged silently by the parser, and the count check is the only
    thing that notices - so the sample must not rely on that never happening."""
    for name in ("sub.def", "top.def"):
        names = [line.split()[1] for line in open(os.path.join(SAMPLE, name))
                 if line.startswith("- ") and " + SOURCE " in line]
        assert len(names) == len(set(names)), f"{name} has duplicate component names"


# -- the sample's own quick start ---------------------------------------------------

@pytest.fixture(scope="module")
def quickstart():
    spec = importlib.util.spec_from_file_location(
        "metal_quickstart", os.path.join(SAMPLE, "quickstart.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_quickstart_sample_files_are_complete(quickstart):
    assert quickstart.missing_files() == []


def test_quickstart_argv_parses_against_the_real_cli(quickstart):
    """The shortcut must not drift from the flags the CLI actually accepts.

    It delegates rather than carrying its own copy of the four required inputs, so this is
    the check that the delegation is wired to something real.
    """
    from vlsi_viewer.cli import parse_args

    args = parse_args(quickstart.sample_argv())
    assert args.cmd == "metal"
    assert len(args.def_files) == 2            # the top block and the sub-block
    assert args.tech_lef and args.lef
    for path in args.def_files + args.lef + args.tech_lef:
        assert os.path.exists(path), path


def test_quickstart_extra_flags_reach_the_cli(quickstart):
    from vlsi_viewer.cli import parse_args

    args = parse_args(quickstart.sample_argv(["--grid-size", "5"]))
    assert args.grid_size == 5.0


def test_quickstart_help_does_not_need_the_sample(quickstart, capsys):
    with pytest.raises(SystemExit) as exit_info:
        quickstart.main(["--help"])
    assert exit_info.value.code == 0
    assert "quickstart" in capsys.readouterr().out


def test_quickstart_check_reports_the_map(quickstart, capsys):
    """`--check` is the non-GUI path: the numbers, so a DEF can be triaged without a window."""
    assert quickstart.main(["--check"]) == 0
    printed = capsys.readouterr().out
    assert "layer" in printed and "pitch" in printed
    assert "horizontal layers" in printed and "vertical layers" in printed
    assert "cell(s) carry wire" not in printed      # the sample must have no warnings
