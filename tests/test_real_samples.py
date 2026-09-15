"""The vendored real files, parsed and measured as they were the first time.

Everything else under `sample_data/` is synthesized, so a parser can be plausible and wrong at
the same time: this project's worst parser bug — nine of ten routing layers coming out with
`spacing == 0.0`, because their rules live in a `SPACINGTABLE` block — was invisible against the
generated sample and only appeared when a real tech LEF was read. These tests keep that
checkable. `sample_data/real/PROVENANCE.md` records where each file came from, its revision, its
licence and its sha256; the numbers asserted here are the ones measured from those exact bytes.

Not a replacement for the unit tests in `test_tech_lef.py` and `test_def_nets.py`: those pin
shapes the real files do *not* contain (`WIDTH` written before a `SPACINGTABLE`, glued `*`
coordinates, negative coordinates), and pointing them here would delete that coverage while
still passing.
"""
import contextlib
import io
import json
import os

import numpy as np
import pytest

from vlsi_viewer.metal import (SCOPE_ALL, SCOPE_POWER, SCOPE_SIGNAL, MetalData, build_metal)
from vlsi_viewer.parsers import TlefParser
from vlsi_viewer.parsers.DEF import DefParser
from vlsi_viewer.parsers.convert import cell_info_from_lef, instance_info_from_def
from vlsi_viewer.parsers.routing import ShapeStream, TechRouting, parse_def

SAMPLE = "sample_data/real"
NANGATE = f"{SAMPLE}/nangate45"
TECH = f"{NANGATE}/NangateOpenCellLibrary.tech.lef"
CELLS = f"{NANGATE}/NangateOpenCellLibrary.macro.mod.lef"
GCD = f"{NANGATE}/gcd_nangate45.def"
ASAP7 = f"{SAMPLE}/asap7/asap7_tech_4x_201209.lef"
SKY130 = f"{SAMPLE}/sky130/sky130_fd_sc_hd.tlef"

ALL_FILES = (TECH, CELLS, GCD, ASAP7, SKY130)

# A 32.74 um die binned at 1 um. The default 10 um would give a 4x4 map, which says nothing.
GRID = 1.0
DIE = 32.74

# pitch, width, spacing and f = (W + S) / P, read off the real file. metal2 is the interesting
# row: its tracks are further apart than its own rules require, so a full layer would otherwise
# read as 0.737 utilised.
NANGATE_LAYERS = [
    ("metal1", "HORIZONTAL", 0.14, 0.07, 0.065, 0.964),
    ("metal2", "VERTICAL", 0.19, 0.07, 0.07, 0.737),
    ("metal3", "HORIZONTAL", 0.14, 0.07, 0.07, 1.000),
    ("metal4", "VERTICAL", 0.28, 0.14, 0.14, 1.000),
    ("metal5", "HORIZONTAL", 0.28, 0.14, 0.14, 1.000),
    ("metal6", "VERTICAL", 0.28, 0.14, 0.14, 1.000),
    ("metal7", "HORIZONTAL", 0.80, 0.40, 0.40, 1.000),
    ("metal8", "VERTICAL", 0.80, 0.40, 0.40, 1.000),
    ("metal9", "HORIZONTAL", 1.60, 0.80, 0.80, 1.000),
    ("metal10", "VERTICAL", 1.60, 0.80, 0.80, 1.000),
]


def _quiet(function, *args, **kwargs):
    """Both parsers print unconditionally; nothing here asserts on their chatter."""
    with contextlib.redirect_stdout(io.StringIO()):
        return function(*args, **kwargs)


@pytest.fixture(scope="module")
def tech():
    return _quiet(TechRouting.read, [TECH])


@pytest.fixture(scope="module")
def cells():
    """One parse of the cell LEF, shared - `build_metal` re-reads it internally, uncached."""
    return _quiet(cell_info_from_lef, [CELLS])


@pytest.fixture(scope="module")
def gcd_metal(cells):
    """The routed design through the whole metric - the slow part, and nothing mutates it."""
    data = _quiet(build_metal, [GCD], [CELLS], [TECH], grid_size=GRID)
    yield data
    data.set_scope(SCOPE_ALL)          # other tests switch it; leave it as they found it


@pytest.fixture(scope="module")
def every_layer(gcd_metal):
    return gcd_metal.group_kind([layer.name for layer in gcd_metal.layers])


# -- the files themselves -------------------------------------------------------------

def test_the_real_files_are_committed():
    for path in ALL_FILES:
        assert os.path.exists(path), f"{path} is missing; see {SAMPLE}/PROVENANCE.md"
        assert os.path.getsize(path) > 1000, f"{path} looks truncated"


def test_the_vendored_files_are_the_bytes_provenance_records():
    """The `sha256` and size in `PROVENANCE.md`, checked against the files themselves.

    That record is the only thing making "these are the upstream bytes" verifiable, and it is
    what `.gitattributes`' `-text` pin exists to keep true across platforms. Parsed from the
    document rather than repeated here, so the two cannot drift apart.
    """
    import hashlib
    import re

    text = open(f"{SAMPLE}/PROVENANCE.md", encoding="utf-8").read()
    sections = re.findall(
        r"^## `(?P<path>[^`]+)` — (?P<size>[\d,]+) B\n(?P<body>.*?)(?=^## |\Z)",
        text, re.S | re.M)
    assert len(sections) == len(ALL_FILES), "PROVENANCE.md should describe every file"
    for path, size, body in sections:
        digest = re.search(r"sha256 \| `([0-9a-f]{64})`", body)
        assert digest, path
        with open(f"{SAMPLE}/{path}", "rb") as handle:
            data = handle.read()
        assert len(data) == int(size.replace(",", "")), path
        assert hashlib.sha256(data).hexdigest() == digest.group(1), path


def test_the_real_files_are_pure_ascii():
    """`DefParser` opens the DEF with no encoding argument, so the locale decides.

    On a cp936 Windows box a single non-ASCII byte raises `UnicodeDecodeError`; on a UTF-8 CI it
    would silently decode as mojibake instead. Upstream is ASCII, so assert it stays that way
    rather than leaving an environment-dependent crash to be discovered later.
    """
    for path in ALL_FILES:
        with open(path, "rb") as handle:
            worst = max(handle.read())
        assert worst < 128, f"{path} has a non-ASCII byte {worst}"


# -- the tech LEF ---------------------------------------------------------------------

def test_the_stack_is_22_blocks_of_which_10_route():
    raw = _quiet(TlefParser, TECH).layers
    assert len(raw) == 22
    assert [name for name, layer in raw.items() if layer.type == "ROUTING"] == \
        [name for name, _d, *_rest in NANGATE_LAYERS]


def test_every_layer_matches_its_published_rules(tech):
    for name, direction, pitch, width, spacing, _f in NANGATE_LAYERS:
        layer = tech[name]
        assert (layer.direction, layer.pitch, layer.width, layer.spacing) == \
            pytest.approx((direction, pitch, width, spacing)), name


def test_no_routing_layer_comes_out_with_zero_spacing(tech):
    """The bug this file exists for: the rules of nine layers live in a SPACINGTABLE block.

    A parser that reads only `SPACING` statements leaves them all at 0.0, which switches off the
    metric's spacing expansion without producing an error of any kind.
    """
    assert [layer.name for layer in tech.layers if layer.spacing <= 0] == []
    assert tech["metal1"].spacing == pytest.approx(0.065)     # the one plain clause


def test_the_pitch_factor_is_why_capacity_is_normalised(tech):
    """`(W + S) / P` is 1.000 on most layers, so the interesting rows are the exceptions.

    On this library metal2's tracks are 0.19 apart against rules totalling 0.14, and without the
    normalisation a *fully* utilised metal2 would read 0.737.
    """
    for name, _direction, _pitch, _width, _spacing, factor in NANGATE_LAYERS:
        assert MetalData.pitch_factor(tech[name]) == pytest.approx(factor, abs=5e-4), name
    assert MetalData.pitch_factor(tech["metal2"]) == pytest.approx(0.14 / 0.19)


def test_every_routing_layer_is_usable(tech):
    assert len(tech.layers) == 10
    assert len(tech.usable) == 10
    assert len(tech.horizontal) + len(tech.vertical) == 10


# -- the cell LEF ---------------------------------------------------------------------

def test_the_cell_library_has_no_block_macro(cells):
    """Which is what keeps the gcd run free of the stranded-cell warning.

    `_macro_area` only counts hard macros, so one appearing here would remove capacity where
    there is wiring and the gcd assertions below would fail with a message about macros rather
    than a pointer to this file.
    """
    assert any(not spec["is_macro"] for spec in cells.values())
    assert [name for name, spec in cells.items() if spec["is_macro"]] == []
    assert cells["AND2_X1"]["size_x"] > 0


def test_the_class_modifiers_are_not_read_as_class_names():
    """`CLASS CORE SPACER ;` is a CORE cell. Reading the whole string as the class name made
    every filler, antenna and welltap cell a hard macro - 8 cells here, and a macro takes
    capacity away from the layers it blocks."""
    with open(CELLS, encoding="utf-8") as handle:
        text = handle.read()
    for modifier in ("CORE SPACER", "CORE ANTENNACELL", "CORE WELLTAP"):
        assert f"CLASS {modifier} ;" in text, modifier
    assert "CLASS BLOCK ;" not in text


def test_the_cell_lef_carries_real_obstructions():
    """107 real `OBS` blocks, 1554 rectangles - and every one of them on `metal1`.

    These are standard cells, so what they declare is where their own pins may not be
    approached rather than a keep-out region. The metal-density mode asks for obstructions
    only of cells whose CLASS is not CORE, so none of this geometry removes any capacity -
    which the gcd assertions below depend on and would fail on if the rule changed.
    """
    from vlsi_viewer.parsers.LEF import LefParser

    with open(CELLS, encoding="utf-8") as handle:
        assert handle.read().count("\n  OBS") == 107

    macros = _quiet(LefParser, [CELLS]).getMacros()
    declared = {name: macro.obstructions() for name, macro in macros.items()
                if macro.obstructions()}
    assert len(declared) == 107
    assert {layer for obs in declared.values() for layer in obs} == {"metal1"}
    assert sum(len(rects) for obs in declared.values() for rects in obs.values()) == 1554
    assert declared["AND2_X1"]["metal1"][0] == pytest.approx((0.235, 0.84, 0.305, 1.25))
    assert macros["ANTENNA_X1"].obstructions() == {}      # 28 cells declare none


# -- the routed DEF -------------------------------------------------------------------

def test_the_parser_reads_every_declared_net():
    """A section the parser stopped early in would silently drop wiring from the map.

    `build_metal` does not surface this: the declared-vs-parsed mismatch is a `logging.warning`,
    not one of `MetalData.warnings`.
    """
    parser = _quiet(DefParser, GCD, parse_net=True, parse_specialnet=True, parse_ndr=True)
    assert parser.declared_nets == parser.n_nets == 497
    assert parser.declared_special_nets == parser.n_special_nets == 2


def test_the_def_is_the_size_it_declares():
    routing = _quiet(parse_def, GCD)
    assert routing.db_unit == 2000
    assert len(routing.components) == 734
    assert len(routing.tracks) == 20
    assert not routing.ndrs                         # the flow removes non-default rules
    xs = [point[0] for point in routing.boundary]
    assert (min(xs), max(xs)) == pytest.approx((0.0, DIE))


def test_the_map_is_the_die_at_the_requested_grid(gcd_metal):
    assert gcd_metal.top_name == "gcd"
    assert gcd_metal.extent == pytest.approx((0.0, 0.0, DIE, DIE))
    assert (gcd_metal.rows, gcd_metal.cols) == (33, 33)
    assert [name for name, _pts in gcd_metal.boundary_polys] == ["gcd"]


def test_the_real_build_warns_about_nothing(gcd_metal):
    """One line that covers five checks: a cell type missing from the LEF, a shape on a layer
    the tech LEF does not define, an unusable layer, a degenerate shape, and wire where the
    model says there is no room. It only means anything because the cell LEF is passed in -
    without it the missing-cell check never runs at all."""
    assert gcd_metal.warnings == []


def test_capacity_is_the_die_area_times_the_pitch_factor(gcd_metal):
    """Hand-derivable, and it ties four things together: the database unit, the die area, the
    pitch factor, and macro blocking (there is none here, so the whole die is routable)."""
    for layer in gcd_metal.layers:
        factor = MetalData.pitch_factor(layer)
        assert gcd_metal.capacity(layer).sum() == pytest.approx(DIE ** 2 * factor, rel=1e-9), \
            layer.name
    cell = gcd_metal.cell_detail(10, 10, "L:metal2")
    assert cell["capacity"] == pytest.approx(GRID ** 2 * (0.14 / 0.19), rel=1e-9)


def test_the_design_uses_the_lower_metals_and_leaves_the_upper_ones_empty(gcd_metal):
    """A routed standard-cell block concentrates on the thin layers; asserting the *ordering*
    is what a synthetic constant cannot fake."""
    means = {layer.name: gcd_metal.layer_util(layer) for layer in gcd_metal.layers}
    busiest = max(means, key=means.get)
    assert busiest in ("metal1", "metal2", "metal3")
    assert means["metal2"] == pytest.approx(0.2527, abs=0.01)
    for name in ("metal7", "metal8", "metal9", "metal10"):
        assert means[name] == 0.0, name


def test_power_and_signal_are_separable(gcd_metal, every_layer):
    """The two SPECIALNETS are a real power grid; merged with signal it would read as a hotspot."""
    gcd_metal.set_scope(SCOPE_SIGNAL)
    signal = gcd_metal.heat(every_layer)
    gcd_metal.set_scope(SCOPE_POWER)
    power = gcd_metal.heat(every_layer)
    gcd_metal.set_scope(SCOPE_ALL)
    assert 0 < float(power.max()) < float(signal.max()) <= 1.0

    # The identity holds on the consumed areas, not on the heat: `heat` divides and then clips,
    # so a congested cell would break the sum there.
    ix, iy = np.unravel_index(int(np.argmax(signal)), signal.shape)
    both = gcd_metal.cell_detail(int(ix), int(iy), every_layer)
    assert 0.0 < both["util"] <= 1.0
    merged = {}
    for scope in (SCOPE_SIGNAL, SCOPE_POWER):
        gcd_metal.set_scope(scope)
        merged[scope] = gcd_metal.cell_detail(int(ix), int(iy), every_layer)["consumed"]
    gcd_metal.set_scope(SCOPE_ALL)
    assert both["consumed"] == pytest.approx(sum(merged.values()))


def test_a_macro_would_take_capacity_away_from_the_layers_it_blocks(cells, tech):
    """The reason `is_macro` has to be right, in one number: no cell in this library is a macro,
    so every layer's capacity is the whole die times its pitch factor. Reading `CORE SPACER` as
    a class name breaks this identity on the bottom layers."""
    assert not any(spec["is_macro"] for spec in cells.values())
    assert tech["metal1"].width > 0


def test_the_via_points_contribute_no_area():
    """Half of all parsed segments are via points, and this file has both forms.

    2,438 are a single point plus a via name with no width field at all; 66 are the zero-width
    `+ SHAPE STRIPE` form. Give either the half-width end extension a real wire gets and every
    via becomes a phantom square — on the power grid, the most visible thing on the map.
    """
    from vlsi_viewer.metal import _GridSink

    tech = _quiet(TechRouting.read, [TECH])
    stream = ShapeStream(tech, _GridSink((0.0, 0.0, DIE, DIE), GRID))
    _quiet(parse_def, GCD, stream=stream)
    with contextlib.redirect_stdout(io.StringIO()):
        stream.flush()
    assert stream.n_via == 2504
    assert stream.n_unknown_layer == 0
    assert stream.n_usable_layer_missing == 0
    assert stream.n_degenerate == 0
    assert stream.n_polygon_edge == 0            # no POLYGON in this revision
    assert stream.n_jog == 5


def test_the_real_file_yields_the_same_shapes_with_the_keyword_lookahead_restored():
    """The tokeniser's keyword rejection moved out of the pattern and into `__scan_tokens`.

    The pattern used to carry a ~40-keyword negative lookahead so that `+ SHAPE STRIPE` could
    not read `SHAPE` as a via name; that lookahead was retried at every character of every
    tail, and it never actually protected the token stream - rejecting `SHAPE` at its first
    character let the engine match `HAPE` one character later. This parses the real routed DEF
    both ways and asserts the shapes and every counter are identical, which is the claim the
    change rests on.
    """
    import re

    from vlsi_viewer.metal import _GridSink
    from vlsi_viewer.parsers.DEF.compiledRe import CompiledRe

    previous = CompiledRe.re_wire_token
    restored = re.compile(
        rf'{CompiledRe.WIRE_VIRTUAL}|{CompiledRe.WIRE_RECT}|{CompiledRe.WIRE_POINT}'
        rf'|(?P<via>{CompiledRe.NOT_KEYWORD}{CompiledRe.NAME})'
        rf'(?:\s+(?P<via_orient>{CompiledRe.ORIENT_CODE}))?')
    shape = []
    try:
        for pattern in (previous, restored):
            CompiledRe.re_wire_token = pattern
            tech = _quiet(TechRouting.read, [TECH])
            sink = _GridSink((0.0, 0.0, DIE, DIE), GRID)
            stream = ShapeStream(tech, sink)
            _quiet(parse_def, GCD, stream=stream)
            with contextlib.redirect_stdout(io.StringIO()):
                stream.flush()
            shape.append((stream.n_via, stream.n_jog, stream.n_degenerate,
                          stream.n_unknown_layer, stream.n_usable_layer_missing,
                          stream.n_polygon_edge, stream.n_emitted,
                          sum(float(grid.sum()) for grid in sink.grids().values())))
    finally:
        # Restoring on the way out rather than after the loop: a tokeniser pattern swapped into
        # a module-level name and left there parses every later test with the wrong pattern, and
        # the failures land thirty files away from the cause.
        CompiledRe.re_wire_token = previous
    assert shape[0] == shape[1]


def test_the_design_routes_across_a_star_reuse_coordinate():
    """`( 52630 55580 ) ( 53770 * )` — a real coordinate reuse, in the spaced form tools write.

    The glued forms quoted in some tutorials (`(1760*)`) do not occur here; that handling is
    defensive, and the unit tests keep it that way.
    """
    with open(GCD, encoding="utf-8") as handle:
        text = handle.read()
    assert ") ( 53770 * )" in text
    assert "(1760*)" not in text and "(*703600)" not in text


# -- physical mode, through the converter ---------------------------------------------

@pytest.fixture(scope="module")
def gcd_physical(tmp_path_factory, cells):
    """Physical mode sits behind the JSON conversion, so this is the real user path."""
    from vlsi_viewer.physical import build_physical

    directory = tmp_path_factory.mktemp("real")
    (directory / "cells.json").write_text(json.dumps(cells))
    (directory / "gcd.json").write_text(json.dumps(_quiet(instance_info_from_def, GCD)))
    return _quiet(build_physical, [str(directory / "gcd.json")], str(directory / "cells.json"),
                  grid_size=3.0)


def test_the_placed_design_reaches_physical_mode(gcd_physical, gcd_metal):
    assert gcd_physical.top_name == "gcd"
    assert gcd_physical.extent == pytest.approx(gcd_metal.extent)   # both modes agree on the die
    assert [name for name, _pts in gcd_physical.boundary_polys] == ["gcd"]
    assert gcd_physical.density.max() <= 1.0 + 1e-9
    assert gcd_physical.density.min() >= 0.0
    occupied = gcd_physical.density[gcd_physical.density > 0]
    assert occupied.size > 0.9 * gcd_physical.density.size     # fully placed, unlike a floorplan


# -- the other two PDKs ---------------------------------------------------------------

def test_the_modern_node_tech_lef_parses():
    """ASAP7: ten 7 nm-class layers, and the one real layer whose two pitches differ.

    `M2` is `DIRECTION HORIZONTAL` with `PITCH 0.180 0.144`, so its pitch is the *y* value -
    the distance between its own horizontal tracks - and `0.072 + 0.072` equals it exactly,
    giving the usual factor of 1.0. Reading the x value instead made it 0.8, which is what
    this test asserted until the direction rule went in.

    Both LEF values are pinned below, so "the factor is 1.0" cannot be confused with "the
    LEF stopped declaring a pitch".
    """
    parsed = _quiet(TlefParser, ASAP7).layers
    assert (parsed["M2"].pitch_x, parsed["M2"].pitch_y) == pytest.approx((0.180, 0.144))
    assert parsed["M2"].direction == "HORIZONTAL"

    tech = _quiet(TechRouting.read, [ASAP7])
    assert [layer.name for layer in tech.layers] == \
        ["M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9", "Pad"]
    assert len(tech.usable) == 10
    assert tech["M2"].pitch == pytest.approx(0.144)
    assert MetalData.pitch_factor(tech["M2"]) == pytest.approx(1.0)


def test_no_real_layer_comes_out_with_a_negative_spacing():
    """A spacing is a distance, so it cannot be negative - and it was.

    A quoted `LEF58_SPACINGTABLE` payload used to be scanned as the layer's own table, and
    the `PRL` breakpoints in one are negative numbers, so a real design's M5 came out at
    -0.2 and only escaped the GUI by way of the `spacing <= 0` fallback.

    Deliberately *not* asserted: `spacing <= pitch`. ASAP7's `Pad` declares an 8 um spacing
    against a 0.32 pitch, both straight from its LEF - it is a pad plane, not a track
    system, and its `PITCH` is the distance between pads. Asserting the track relation would
    fail on a file that is not wrong.
    """
    for path in (TECH, ASAP7, SKY130):
        tech = _quiet(TechRouting.read, [path])
        for layer in tech.layers:
            assert layer.spacing >= 0, (layer.name, layer)


def test_the_differently_named_stack_parses():
    """sky130 names its layers `li1`, `met1`…`met5` - names the metric code has never seen, and
    the reason nothing may assume an `M<digit>` pattern."""
    tech = _quiet(TechRouting.read, [SKY130])
    assert [layer.name for layer in tech.layers] == \
        ["li1", "met1", "met2", "met3", "met4", "met5"]
    assert MetalData.pitch_factor(tech["li1"]) == pytest.approx(0.34 / 0.46, abs=5e-4)
    assert MetalData.pitch_factor(tech["met1"]) == pytest.approx(0.28 / 0.34, abs=5e-4)


def test_the_wrong_tech_lef_is_loud_about_it():
    """The negative control the gcd assertions lack: nothing there proves the tech LEF was used.

    Every layer of this DEF is named `metal*`, none of which exists in the sky130 stack, so the
    metric has to say so rather than quietly producing a map with no metal in it.
    """
    data = _quiet(build_metal, [GCD], [CELLS], [SKY130], grid_size=GRID)
    assert any("does not define" in warning for warning in data.warnings), data.warnings
    assert data.heat(data.group_kind([layer.name for layer in data.layers])).max() == 0.0
