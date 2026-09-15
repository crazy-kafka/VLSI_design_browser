"""The metal-density metric, against hand arithmetic.

These are the numbers a user reads off the map, so each is computed by hand in the test
rather than being taken from a previous run of the same code.

One correction to the worked example in the plan: it computed an 8 um wire's keep-out as
`(8 + 0.1) x 0.2`, dropping the end extension. The DEF reference gives regular wiring a
default extension of *half the wire width* at each end, and the implementation applies it, so
the footprint is `(8 + 0.1 + 0.1) x 0.2`. The difference is 1.2 % on that wire and it is the
spec-correct value.
"""
import contextlib
import io

import numpy as np
import pytest

from vlsi_viewer.metal import (SCOPE_ALL, SCOPE_POWER, SCOPE_SIGNAL, MetalData, build_metal)

# M3 is the wire layer: pitch 0.2 = width 0.1 + spacing 0.1, so f = 1.0 and the arithmetic is
# the plain one. M4 and M5 exist for the multi-layer cases.
TECH = """\
LAYER M3
  TYPE ROUTING ;
  WIDTH 0.1 ;
  SPACING 0.1 ;
  PITCH 0.2 ;
  DIRECTION HORIZONTAL ;
END M3
LAYER M4
  TYPE ROUTING ;
  WIDTH 0.1 ;
  SPACING 0.1 ;
  PITCH 0.2 ;
  DIRECTION VERTICAL ;
END M4
LAYER M5
  TYPE ROUTING ;
  WIDTH 0.1 ;
  SPACING 0.1 ;
  PITCH 0.2 ;
  DIRECTION HORIZONTAL ;
END M5
LAYER VIA3
  TYPE CUT ;
  WIDTH 0.1 ;
END VIA3
"""

MACRO_LEF = """\
MACRO SRAM
  CLASS BLOCK ;
  SIZE 4 BY 4 ;
  SYMMETRY X Y ;
END SRAM
MACRO INV
  CLASS CORE ;
  SIZE 1 BY 1 ;
END INV
"""

DIE = "DIEAREA ( 0 0 ) ( 10000 10000 ) ;\n"


def _write(path, text):
    path.write_text(text)
    return str(path)


def _macro_lef(obs=None, size=(4.0, 4.0), klass="BLOCK", name="SRAM"):
    """A one-cell macro LEF, optionally declaring ``OBS``: layer -> (x0, y0, x1, y1) rects."""
    out = [f"MACRO {name}", f"  CLASS {klass} ;", f"  SIZE {size[0]:g} BY {size[1]:g} ;",
           "  SYMMETRY X Y ;"]
    if obs:
        out.append("  OBS")
        for layer, rects in obs:
            out.append(f"    LAYER {layer} ;")
            out.extend("      RECT " + " ".join(f"{value:g}" for value in rect) + " ;"
                       for rect in rects)
        out.append("  END")
    out += [f"END {name}", ""]
    return "\n".join(out)


def _build(tmp_path, def_body, macro_lef=False, macro_lef_text=None, **kwargs):
    tech = _write(tmp_path / "tech.lef", TECH)
    if macro_lef_text is not None:
        lef = [_write(tmp_path / "cells.lef", macro_lef_text)]
    else:
        lef = [_write(tmp_path / "cells.lef", MACRO_LEF)] if macro_lef else []
    body = ("VERSION 5.8 ;\nDESIGN d ;\nUNITS DISTANCE MICRONS 1000 ;\n"
            + DIE + def_body + "END DESIGN\n")
    path = _write(tmp_path / "d.def", body)
    with contextlib.redirect_stdout(io.StringIO()):
        return build_metal([path], lef, [tech], **kwargs)


def _nets(statements):
    return "COMPONENTS 0 ;\nEND COMPONENTS\nNETS %d ;\n%sEND NETS\n" % (
        len(statements), "".join(statements))


def _one_horizontal_wire(x0=1000, x1=9000, y=5000, layer="M3"):
    return f"- n1 ( PIN A ) + ROUTED {layer} ( {x0} {y} ) ( {x1} {y} ) ;\n"


# -- the single-layer number ---------------------------------------------------------

def test_one_wire_matches_hand_arithmetic(tmp_path):
    """D = (length + width + spacing) x (width + spacing) for a minimum-width wire.

    Extension is half the width at each end, and the keep-out adds half the spacing on every
    side, so an 8 um wire on M3 covers `(8 + 0.05 + 0.05 + 0.05 + 0.05) x (0.05 + 0.05 +
    0.05 + 0.05)` = 8.2 x 0.2 = 1.64 um^2.
    """
    data = _build(tmp_path, _nets([_one_horizontal_wire()]), grid_size=10.0)
    detail = data.cell_detail(0, 0, "L:M3")
    assert detail["consumed"] == pytest.approx((8.0 + 0.1 + 0.1) * (0.1 + 0.1))
    # Capacity is the die area times f, and f is 1.0 for this layer.
    assert detail["capacity"] == pytest.approx(100.0)
    assert detail["util"] == pytest.approx(0.0164)


def test_thirty_wires_give_the_documented_utilisation(tmp_path):
    """The plan's worked example, with the end extension accounted for.

    Thirty 8 um wires across a 10 um cell consume 30 x 1.64 = 49.2 um^2 of the 100 um^2 of
    track-pitch area, so the cell reads 0.492. Tracks confirm it: 50 tracks of 10 um is 500
    track-um available, and 30 wires of 8 um is 240 used, which is the same 0.48 within the
    end extension's contribution.
    """
    wires = [_one_horizontal_wire(y=500 + i * 300) for i in range(30)]
    data = _build(tmp_path, _nets(wires), grid_size=10.0)
    detail = data.cell_detail(0, 0, "L:M3")
    assert detail["consumed"] == pytest.approx(30 * 1.64)
    assert detail["util"] == pytest.approx(0.492)


def test_utilisation_is_clipped_at_one(tmp_path):
    """Wires packed closer than their spacing rule overlap, and must not exceed 1.0.

    Over-counting in a saturated region is the intended conservative direction - it is what
    makes a DRC-risk area read as over-subscribed - but the *displayed* value still has to
    stay in range for the colour ramp.
    """
    wires = [_one_horizontal_wire(y=500 + i * 20) for i in range(400)]
    data = _build(tmp_path, _nets(wires), grid_size=10.0)
    assert data.cell_detail(0, 0, "L:M3")["consumed"] > 100.0
    assert data.heat("L:M3").max() == pytest.approx(1.0)


# -- capacity normalisation ---------------------------------------------------------

def test_pitch_factor_normalises_a_layer_whose_pitch_exceeds_its_rules(tmp_path):
    """Nangate45's metal2 is W+S = 0.14 against a 0.19 pitch, and sky130's met1 0.28/0.34.

    Without the factor a fully-utilised layer reads (W+S)/P - 0.74 and 0.82 respectively -
    so the same wiring would look less congested on those layers than it is.
    """
    tech = """\
LAYER M9
  TYPE ROUTING ;
  WIDTH 0.07 ;
  SPACING 0.07 ;
  PITCH 0.19 ;
  DIRECTION HORIZONTAL ;
END M9
"""
    body = ("VERSION 5.8 ;\nDESIGN d ;\nUNITS DISTANCE MICRONS 1000 ;\n" + DIE
            + _nets(["- n1 ( PIN A ) + ROUTED M9 ( 0 5000 ) ( 10000 5000 ) ;\n"])
            + "END DESIGN\n")
    path = _write(tmp_path / "d.def", body)
    with contextlib.redirect_stdout(io.StringIO()):
        data = build_metal([path], [], [_write(tmp_path / "tech.lef", tech)], grid_size=10.0)

    detail = data.cell_detail(0, 0, "L:M9")
    assert detail["layers"][0]["pitch_factor"] == pytest.approx(0.14 / 0.19)
    assert detail["capacity"] == pytest.approx(100.0 * 0.14 / 0.19)


def test_a_fully_utilised_layer_reads_one(tmp_path):
    """The property the whole metric rests on: every track used reads exactly 1.0.

    Wires span the full cell width and sit on every track - one per 0.2 um pitch - so their
    keep-out rectangles tile the cell and the consumed area equals the capacity. (The wires
    run to the die edge and are clipped there, so each covers exactly the 10 um cell width.)
    """
    wires = [_one_horizontal_wire(x0=0, x1=10000, y=100 + i * 200) for i in range(50)]
    data = _build(tmp_path, _nets(wires), grid_size=10.0)
    detail = data.cell_detail(0, 0, "L:M3")
    assert detail["consumed"] == pytest.approx(100.0)
    assert detail["capacity"] == pytest.approx(100.0)
    assert detail["util"] == pytest.approx(1.0)


# -- macros: the layer-count fallback ------------------------------------------------
#
# The MACRO_LEF above declares no OBS, which is the case the flag exists for: a library that
# does not say what its macros obstruct cannot be judged from data, so the bottom N layers of
# the whole footprint are taken as blocked and reported as a guess.

def _macro_body():
    return """\
COMPONENTS 1 ;
- m1 SRAM + PLACED ( 0 0 ) N ;
END COMPONENTS
""" + _nets([])


def test_a_macro_without_obs_blocks_the_bottom_layers_it_is_told_to(tmp_path):
    """The fallback: no OBS, so `--macro-block-layers` decides. Two layers here, so M5 - the
    third - must be whole, or the whole point of the flag goes missing."""
    data = _build(tmp_path, _macro_body(), macro_lef=True, grid_size=10.0,
                  macro_block_layers=2)
    assert data.cell_detail(0, 0, "L:M3")["capacity"] == pytest.approx(100.0 - 16.0)
    assert data.cell_detail(0, 0, "L:M5")["capacity"] == pytest.approx(100.0)
    assert data.blockage["fallback_cells"] == 1


def test_the_fallback_depth_can_be_turned_off(tmp_path):
    data = _build(tmp_path, _macro_body(), macro_lef=True, grid_size=10.0,
                  macro_block_layers=0)
    assert data.cell_detail(0, 0, "L:M3")["capacity"] == pytest.approx(100.0)
    assert data.blocked_layers == []


# -- macros: real OBS geometry -------------------------------------------------------

def test_obs_says_which_layers_block_and_the_flag_does_not(tmp_path):
    """A macro that obstructs M4 alone, with the flag asking for the bottom two.

    The OBS is the fact and the flag is the guess, so M3 must be whole and M4 must not be -
    the exact inverse of what a layer count produces.
    """
    lef = _macro_lef(obs=[("M4", [(0.0, 0.0, 4.0, 4.0)])])
    data = _build(tmp_path, _macro_body(), macro_lef_text=lef, grid_size=10.0,
                  macro_block_layers=2)
    assert data.cell_detail(0, 0, "L:M3")["capacity"] == pytest.approx(100.0)
    assert data.cell_detail(0, 0, "L:M4")["capacity"] == pytest.approx(100.0 - 16.0)
    assert data.cell_detail(0, 0, "L:M5")["capacity"] == pytest.approx(100.0)
    assert [data.layers[index].name for index in data.blocked_layers] == ["M4"]


def test_obs_still_blocks_when_the_fallback_is_switched_off(tmp_path):
    """`--macro-block-layers 0` cancels the guess, not the geometry."""
    lef = _macro_lef(obs=[("M4", [(0.0, 0.0, 4.0, 4.0)])])
    data = _build(tmp_path, _macro_body(), macro_lef_text=lef, grid_size=10.0,
                  macro_block_layers=0)
    assert data.cell_detail(0, 0, "L:M4")["capacity"] == pytest.approx(100.0 - 16.0)


def test_obs_blocks_only_what_it_covers(tmp_path):
    """A quarter of the macro below the cell in question takes a quarter of one cell.

    The old model removed the whole macro footprint from the whole cells it touched, so a
    partial obstruction could not be expressed at all.
    """
    lef = _macro_lef(obs=[("M4", [(0.0, 0.0, 2.0, 4.0)])])       # half the 4 x 4 macro
    data = _build(tmp_path, _macro_body(), macro_lef_text=lef, grid_size=10.0)
    # The macro is placed in the corner of a 10 x 10 die, so its left half covers the left
    # 2 um of cell (0, 0): 2 x 4 = 8 um^2 of the cell's 100.
    assert data.cell_detail(0, 0, "L:M4")["capacity"] == pytest.approx(100.0 - 8.0)


def test_a_tile_field_of_obstructions_blocks(tmp_path):
    """A memory compiler writes a block area as tessellated rectangles, each a small part of
    the macro. Judging the rectangles one at a time would discard the whole blockage; judging
    what they cover together keeps it - and keeps it as *rectangles*, not as a bounding box.
    """
    tiled = [(x * 1.0, y * 1.0, x * 1.0 + 1.0, y * 1.0 + 1.0)
             for x in range(4) for y in range(4)]
    lef = _macro_lef(obs=[("M4", tiled)])
    data = _build(tmp_path, _macro_body(), macro_lef_text=lef, grid_size=10.0)
    assert data.cell_detail(0, 0, "L:M4")["capacity"] == pytest.approx(100.0 - 16.0)


def test_a_tile_field_with_hairline_gaps_blocks_the_same_way(tmp_path):
    """The same coverage written with 0.05 um between the tiles.

    Nothing can route a 0.05 um channel - every routing layer of every PDK measured here has a
    pitch above 0.14 um - so the gap is a tessellation artifact and the layer is as blocked as
    it is above.
    """
    tiled = [(x * 1.05, y * 1.05, x * 1.05 + 1.0, y * 1.05 + 1.0)
             for x in range(4) for y in range(4)]
    lef = _macro_lef(obs=[("M4", tiled)])
    data = _build(tmp_path, _macro_body(), macro_lef_text=lef, grid_size=10.0)
    assert data.cell_detail(0, 0, "L:M4")["capacity"] == pytest.approx(100.0 - 16.0)


def test_pin_access_bites_are_not_a_keep_out(tmp_path):
    """Two 0.1 um obstructions on M4, an eighth of a percent of the macro. A macro declaring
    those is telling us where its pins are, not that the layer is blocked."""
    lef = _macro_lef(obs=[("M4", [(1.0, 1.0, 1.1, 1.1), (3.0, 3.0, 3.1, 3.1)])])
    data = _build(tmp_path, _macro_body(), macro_lef_text=lef, grid_size=10.0)
    assert data.cell_detail(0, 0, "L:M4")["capacity"] == pytest.approx(100.0)
    assert data.blockage["ignored_layers"] == {"M4": 1}


def test_a_macro_whose_obstructions_are_all_negligible_blocks_nothing(tmp_path):
    """Declared, judged, and found not to be a keep-out. The fallback must *not* re-engage -
    the LEF spoke; it just did not say anything that removes capacity."""
    lef = _macro_lef(obs=[("M4", [(1.0, 1.0, 1.1, 1.1)])])
    data = _build(tmp_path, _macro_body(), macro_lef_text=lef, grid_size=10.0,
                  macro_block_layers=2)
    assert data.blocked_layers == []
    assert data.blockage["fallback_cells"] == 0
    assert data.blockage["ignored_cells"] == ["SRAM"]


def test_a_ring_obstruction_is_rasterised_as_rects_not_as_its_box(tmp_path):
    """Four thin bars around the edge: 25 % of the macro, and the middle is open.

    Its bounding box is the whole macro, so a shortcut that blocked the box would take all 16
    um^2 of the corner cell. The bars are 0.5 um wide, so the corner cell loses 0.5 x 0.5.
    """
    ring = [(0.0, 0.0, 4.0, 0.5), (0.0, 3.5, 4.0, 4.0),
            (0.0, 0.5, 0.5, 3.5), (3.5, 0.5, 4.0, 3.5)]
    lef = _macro_lef(obs=[("M4", ring)])
    data = _build(tmp_path, _macro_body(), macro_lef_text=lef, grid_size=10.0)
    # The bars cover 4x4 - 3x3 = 7 um^2 of the corner cell's 100. Blocking the bounding box
    # instead would take all 16.
    assert data.cell_detail(0, 0, "L:M4")["capacity"] == pytest.approx(100.0 - 7.0)


def test_obstructions_follow_the_placement_and_its_orientation(tmp_path):
    """An obstruction offset inside the macro has to land where the cell's geometry lands.

    This is the case the old extents-swap shortcut could not express at all - it knew only the
    macro's outline - and a `W` placement is where the two differ, because the true DEF
    transform puts the cell to the *minus*-x side of its placed origin.
    """
    # A 2 x 2 obstruction in the macro's own corner, a quarter of the 4 x 4 macro - above the
    # size rule, so what is under test here is the transform and not the filter.
    lef = _macro_lef(obs=[("M4", [(0.0, 0.0, 2.0, 2.0)])])
    body = """\
COMPONENTS 1 ;
- m1 SRAM + PLACED ( 5000 5000 ) W ;
END COMPONENTS
""" + _nets([])
    data = _build(tmp_path, body, macro_lef_text=lef, grid_size=1.0)
    # W maps a local point (x, y) to (5 - y, 5 + x), so the obstruction's image is
    # x in [3, 5], y in [5, 7] - to the *minus*-x side of the placed origin, which is where
    # the true DEF transform puts a W-placed cell.
    for ix, iy in ((3, 5), (4, 5), (3, 6), (4, 6)):
        assert data.cell_detail(ix, iy, "L:M4")["capacity"] == pytest.approx(0.0), (ix, iy)
    # ... and not on the other side, which is where getting the composition wrong puts it.
    for ix, iy in ((5, 5), (6, 5), (5, 6), (7, 7)):
        assert data.cell_detail(ix, iy, "L:M4")["capacity"] == pytest.approx(1.0), (ix, iy)


# -- groups ------------------------------------------------------------------------

def test_a_group_is_capacity_weighted_not_a_sum(tmp_path):
    """Summing two layers would double the number; the answer is sum(D)/sum(C).

    With a macro blocking only the bottom layer, the two layers have different capacities,
    which is what makes the weighting visible rather than collapsing to a plain mean.
    """
    body = """\
COMPONENTS 1 ;
- m1 SRAM + PLACED ( 0 0 ) N ;
END COMPONENTS
NETS 2 ;
- n1 ( PIN A ) + ROUTED M3 ( 1000 2000 ) ( 9000 2000 ) ;
- n2 ( PIN B ) + ROUTED M5 ( 1000 6000 ) ( 9000 6000 ) ;
END NETS
"""
    data = _build(tmp_path, body, macro_lef=True, grid_size=10.0, macro_block_layers=1)
    detail = data.cell_detail(0, 0, data.group_kind(["M3", "M5"]))

    blocked = detail["layers"][0]
    free = detail["layers"][1]
    assert blocked["capacity"] == pytest.approx(84.0)
    assert free["capacity"] == pytest.approx(100.0)
    assert blocked["consumed"] == pytest.approx(free["consumed"])

    weighted = (blocked["consumed"] + free["consumed"]) / (84.0 + 100.0)
    naive_mean = (blocked["util"] + free["util"]) / 2
    assert detail["util"] == pytest.approx(weighted)
    assert weighted != pytest.approx(naive_mean)          # the two really do differ here
    assert detail["util"] < blocked["util"] + free["util"]  # and it is not a sum


def test_group_of_one_equals_that_layer(tmp_path):
    data = _build(tmp_path, _nets([_one_horizontal_wire()]), grid_size=10.0)
    single = data.heat("L:M3")
    group = data.heat(data.group_kind(["M3"]))
    np.testing.assert_allclose(single, group)


def test_group_kind_is_canonical(tmp_path):
    data = _build(tmp_path, _nets([_one_horizontal_wire()]), grid_size=10.0)
    assert data.group_kind(["M5", "M3"]) == data.group_kind(["M3", "M5"])
    np.testing.assert_allclose(data.heat(data.group_kind(["M5", "M3"])),
                               data.heat(data.group_kind(["M3", "M5"])))


def test_an_unknown_layer_selects_nothing(tmp_path):
    data = _build(tmp_path, _nets([_one_horizontal_wire()]), grid_size=10.0)
    assert data.layers_of("L:NOPE") == []
    assert data.heat("L:NOPE").max() == 0.0


def test_an_unknown_kind_is_rejected(tmp_path):
    data = _build(tmp_path, _nets([_one_horizontal_wire()]), grid_size=10.0)
    with pytest.raises(ValueError):
        data.heat("nonsense")


# -- scope -------------------------------------------------------------------------

def test_signal_and_power_are_separable_and_all_is_their_sum(tmp_path):
    """Merging them makes a region under a power stripe read as a routing hotspot."""
    body = """\
COMPONENTS 0 ;
END COMPONENTS
SPECIALNETS 1 ;
- VDD + USE POWER
  + ROUTED M3 200 ( 1000 2000 ) ( 9000 2000 ) ;
END SPECIALNETS
NETS 1 ;
- sig ( PIN A ) + USE SIGNAL + ROUTED M3 ( 1000 6000 ) ( 9000 6000 ) ;
END NETS
"""
    data = _build(tmp_path, body, grid_size=10.0)
    data.set_scope(SCOPE_SIGNAL)
    signal = data.cell_detail(0, 0, "L:M3")["consumed"]
    data.set_scope(SCOPE_POWER)
    power = data.cell_detail(0, 0, "L:M3")["consumed"]
    data.set_scope(SCOPE_ALL)
    everything = data.cell_detail(0, 0, "L:M3")["consumed"]

    assert signal > 0 and power > 0
    assert everything == pytest.approx(signal + power)
    assert data.heat("L:M3").max() > max(
        _scoped_max(data, SCOPE_SIGNAL), _scoped_max(data, SCOPE_POWER))


def _scoped_max(data, scope):
    data.set_scope(scope)
    return float(data.heat("L:M3").max())


def test_an_unknown_scope_is_rejected(tmp_path):
    data = _build(tmp_path, _nets([_one_horizontal_wire()]), grid_size=10.0)
    with pytest.raises(ValueError):
        data.set_scope("bogus")


# -- a range of the stack ------------------------------------------------------------

def test_trimming_to_a_range_measures_the_kept_layers_identically(tmp_path):
    """The oracle for the feature: a trimmed run is the untrimmed run, restricted.

    Two macros, one of each kind - SRAM declares OBS on M5, ROM declares none and so falls
    back to the layer count - because that fallback is where the two runs could part company.
    Anchored to the *measured* part it would block M4/M5 instead of M3/M4, so M4, a layer the
    range keeps, would lose 16 um^2 for a reason nobody asked for.
    """
    lef = _macro_lef(obs=[("M5", [(0.0, 0.0, 4.0, 4.0)])]) + _macro_lef(name="ROM")
    body = """\
COMPONENTS 2 ;
- m1 SRAM + PLACED ( 0 0 ) N ;
- m2 ROM + PLACED ( 5000 5000 ) N ;
END COMPONENTS
""" + _nets([_one_horizontal_wire(x0=1000, x1=9000, y=1000, layer="M3"),
             _one_horizontal_wire(x0=1000, x1=9000, y=1000, layer="M4"),
             _one_horizontal_wire(x0=1000, x1=9000, y=1000, layer="M5")])
    full = _build(tmp_path, body, macro_lef_text=lef, grid_size=5.0, macro_block_layers=2)
    trimmed = _build(tmp_path, body, macro_lef_text=lef, grid_size=5.0, macro_block_layers=2,
                     min_layer=2, max_layer=3)

    assert [layer.name for layer in trimmed.layers] == ["M4", "M5"]
    assert trimmed.totals["filtered"] > 0            # M3's wire, counted rather than lost
    assert full.totals["filtered"] == 0
    assert full.blockage["fallback_layers"] == trimmed.blockage["fallback_layers"] == 2
    for name in ("M4", "M5"):
        for ix, iy in ((0, 0), (1, 1)):
            left = trimmed.cell_detail(ix, iy, f"L:{name}")
            right = full.cell_detail(ix, iy, f"L:{name}")
            assert left["consumed"] == pytest.approx(right["consumed"]), (name, ix, iy)
            assert left["capacity"] == pytest.approx(right["capacity"]), (name, ix, iy)
            assert left["util"] == pytest.approx(right["util"]), (name, ix, iy)
    assert [layer.name for layer in full.layers] == ["M3", "M4", "M5"]


def test_the_macro_fallback_still_names_where_it_landed(tmp_path):
    """A range above the fallback leaves it blocking nothing, and the summary says so.

    The flag's own text promises "the bottom N layers"; with `--min-layer 3` on this stack
    the bottom two are both outside the range, so a capacity that is not missing has to be
    distinguishable from one that is.
    """
    data = _build(tmp_path, _macro_body(), macro_lef=True, grid_size=10.0,
                  macro_block_layers=2, min_layer=3)
    assert [layer.name for layer in data.layers] == ["M5"]
    assert data.blockage["fallback_layer_names"] == []
    assert data.blocked_layers == []
    assert data.cell_detail(0, 0, "L:M5")["capacity"] == pytest.approx(100.0)


def test_the_fallback_names_the_kept_layers_it_does_reach(tmp_path):
    """The other half: a depth of 2 with the range starting at 2 reaches M4 alone."""
    data = _build(tmp_path, _macro_body(), macro_lef=True, grid_size=10.0,
                  macro_block_layers=2, min_layer=2)
    assert data.blockage["fallback_layer_names"] == ["M4"]
    assert [data.layers[index].name for index in data.blocked_layers] == ["M4"]
    assert data.cell_detail(0, 0, "L:M4")["capacity"] == pytest.approx(100.0 - 16.0)
    assert data.cell_detail(0, 0, "L:M5")["capacity"] == pytest.approx(100.0)


@pytest.mark.parametrize("kwargs", [{"min_layer": 0}, {"min_layer": 1, "max_layer": 0},
                                    {"min_layer": 4}, {"max_layer": 4},
                                    {"min_layer": 3, "max_layer": 2}])
def test_a_range_outside_the_stack_is_refused(tmp_path, kwargs):
    """Refused before anything is built, so the CLI reports it instead of the window."""
    with pytest.raises(ValueError, match="layer range"):
        _build(tmp_path, _nets([_one_horizontal_wire()]), **kwargs)


def test_the_stack_note_says_the_range_a_trimmed_build_measured(tmp_path):
    """`9 layers` reads as a short stack; `layers M4..M5 (2 of 3)` reads as a range."""
    full = _build(tmp_path, _nets([_one_horizontal_wire()]), grid_size=10.0)
    assert full.stack_note == "3 layers"
    trimmed = _build(tmp_path, _nets([_one_horizontal_wire()]), grid_size=10.0,
                     min_layer=2, max_layer=3)
    assert trimmed.stack_note == "layers M4..M5 (2 of 3)"


# -- robustness --------------------------------------------------------------------

def test_no_nan_anywhere(tmp_path):
    """`heatmap.grid_to_image` has no NaN handling: a NaN paints garbage pixels.

    A cell with no capacity - entirely under a macro, on a blocked layer - must read 0.0.
    """
    body = """\
COMPONENTS 1 ;
- m1 SRAM + PLACED ( 0 0 ) N ;
- m2 SRAM + PLACED ( 0 0 ) N ;
END COMPONENTS
""" + _nets([_one_horizontal_wire()])
    data = _build(tmp_path, body, macro_lef=True, grid_size=10.0, macro_block_layers=3)
    for kind in [data.group_kind([layer.name for layer in data.layers])] + \
                [data.layer_kind(layer) for layer in data.layers]:
        grid = data.heat(kind)
        assert np.isfinite(grid).all()
        assert grid.min() >= 0.0 and grid.max() <= 1.0


def test_a_design_with_no_routing_at_all_is_all_zero(tmp_path):
    data = _build(tmp_path, _nets([]), grid_size=10.0)
    assert data.heat("L:M3").max() == 0.0
    assert data.mean_util("L:M3") == 0.0


def test_cell_detail_reconciles_with_the_rendered_pixel(tmp_path):
    """The readout exists so a user can check the colour; it must equal what is drawn."""
    wires = [_one_horizontal_wire(y=500 + i * 400) for i in range(12)]
    data = _build(tmp_path, _nets(wires), grid_size=10.0)
    detail = data.cell_detail(0, 0, "L:M3")
    assert detail["util"] == pytest.approx(float(data.heat("L:M3")[0, 0]), abs=1e-6)


def test_cell_detail_out_of_range_is_rejected(tmp_path):
    data = _build(tmp_path, _nets([_one_horizontal_wire()]), grid_size=10.0)
    with pytest.raises(IndexError):
        data.cell_detail(99, 0, "L:M3")


def test_two_unrelated_defs_are_rejected(tmp_path):
    """Two independent designs have no single coordinate system, so there is nothing to draw."""
    tech = _write(tmp_path / "tech.lef", TECH)
    first = _write(tmp_path / "a.def", "DESIGN A ;\nUNITS DISTANCE MICRONS 1000 ;\n" + DIE
                  + _nets([_one_horizontal_wire()]) + "END DESIGN\n")
    second = _write(tmp_path / "b.def", "DESIGN B ;\nUNITS DISTANCE MICRONS 1000 ;\n" + DIE
                    + _nets([_one_horizontal_wire()]) + "END DESIGN\n")
    with contextlib.redirect_stdout(io.StringIO()):
        with pytest.raises(ValueError, match="exactly one top-level"):
            build_metal([first, second], [], [tech], grid_size=10.0)


def _bbox(points):
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return (min(xs), min(ys), max(xs), max(ys))


def test_a_sub_block_outline_is_drawn_where_the_block_is(tmp_path):
    """A sub-block's boundary is written in its own frame, exactly as its wiring is.

    Returned raw - which is what this did - one rectangle is drawn at the origin no matter
    how many times the block is placed, so the map shows an outline in a corner the block is
    not in. The outlines are free hierarchy feedback once they are placed correctly.
    """
    tech = _write(tmp_path / "tech.lef", TECH)
    sub = _write(tmp_path / "sub.def",
                 "DESIGN SUB ;\nUNITS DISTANCE MICRONS 1000 ;\n"
                 "DIEAREA ( 0 0 ) ( 4000 2000 ) ;\n" + _nets([]) + "END DESIGN\n")
    top = _write(tmp_path / "top.def",
                 "DESIGN TOP ;\nUNITS DISTANCE MICRONS 1000 ;\n" + DIE
                 + "COMPONENTS 2 ;\n"
                 "- u1 SUB + SOURCE DIST + PLACED ( 0 0 ) N ;\n"
                 "- u2 SUB + SOURCE DIST + PLACED ( 5000 5000 ) N ;\n"
                 "END COMPONENTS\n" + _nets([]) + "END DESIGN\n")
    with contextlib.redirect_stdout(io.StringIO()):
        data = build_metal([top, sub], [], [tech], grid_size=10.0)

    named = {}
    for name, points in data.boundary_polys:
        named.setdefault(name, []).append(_bbox(points))
    assert sorted(named) == ["SUB", "TOP"]
    assert sorted(named["SUB"]) == [(0.0, 0.0, 4.0, 2.0), (5.0, 5.0, 9.0, 7.0)]
    assert named["TOP"] == [(0.0, 0.0, 10.0, 10.0)]


def test_a_rotated_sub_block_outline_turns_with_it(tmp_path):
    """A quarter turn swaps the outline's extents, which a bounding-box shortcut would miss.

    Vertex-by-vertex is what keeps this true, and what keeps a rectilinear outline
    rectilinear rather than collapsed to its box.
    """
    tech = _write(tmp_path / "tech.lef", TECH)
    sub = _write(tmp_path / "sub.def",
                 "DESIGN SUB ;\nUNITS DISTANCE MICRONS 1000 ;\n"
                 "DIEAREA ( 0 0 ) ( 4000 2000 ) ;\n" + _nets([]) + "END DESIGN\n")
    top = _write(tmp_path / "top.def",
                 "DESIGN TOP ;\nUNITS DISTANCE MICRONS 1000 ;\n" + DIE
                 + "COMPONENTS 1 ;\n"
                 "- u1 SUB + SOURCE DIST + PLACED ( 5000 5000 ) W ;\n"
                 "END COMPONENTS\n" + _nets([]) + "END DESIGN\n")
    with contextlib.redirect_stdout(io.StringIO()):
        data = build_metal([top, sub], [], [tech], grid_size=10.0)

    outline = next(points for name, points in data.boundary_polys if name == "SUB")
    assert len(outline) == 4
    # 4 x 2 becomes 2 x 4, anchored at the placed origin as DEF defines it.
    assert _bbox(outline) == pytest.approx((3.0, 5.0, 5.0, 9.0))


def test_a_missing_boundary_is_rejected(tmp_path):
    tech = _write(tmp_path / "tech.lef", TECH)
    path = _write(tmp_path / "d.def", "DESIGN d ;\nUNITS DISTANCE MICRONS 1000 ;\n"
                  + _nets([_one_horizontal_wire()]) + "END DESIGN\n")
    with contextlib.redirect_stdout(io.StringIO()):
        with pytest.raises(ValueError, match="boundary"):
            build_metal([path], [], [tech], grid_size=10.0)


def test_a_tech_lef_with_no_routing_layers_is_rejected(tmp_path):
    tech = _write(tmp_path / "tech.lef", "LAYER poly\n  TYPE MASTERSLICE ;\nEND poly\n")
    path = _write(tmp_path / "d.def", "DESIGN d ;\nUNITS DISTANCE MICRONS 1000 ;\n" + DIE
                  + _nets([_one_horizontal_wire()]) + "END DESIGN\n")
    with contextlib.redirect_stdout(io.StringIO()):
        with pytest.raises(ValueError, match="ROUTING"):
            build_metal([path], [], [tech], grid_size=10.0)


def test_grid_size_must_be_positive(tmp_path):
    with pytest.raises(ValueError, match="grid size"):
        _build(tmp_path, _nets([]), grid_size=0.0)


# -- a virtual connection is not metal, an inline rectangle is -----------------------

def test_a_virtual_connection_costs_nothing_and_an_inline_rect_costs_its_area(tmp_path):
    """The reference's Example 7-12, measured, with the arithmetic done by hand.

    On M3 (width 0.1, spacing 0.1, so the keep-out adds 0.05 on every side), and placed away
    from the die edge - which clips, and would leave a shape that straddles it contributing
    only its inner half:

        wire (1,3)-(6,3)   (5 + 0.05 + 0.05 + 0.05 + 0.05) x 0.2 = 5.2 x 0.2 = 1.04 um^2
        RECT (5,4)-(7,6)   2.1 x 2.1                             =           4.41
        wire (8,4)-(8,9)   (5 + 0.05 + 0.05 + 0.05 + 0.05) x 0.2 = 5.2 x 0.2 = 1.04
                                                                  total        6.49

    The virtual connection (6,3)-(8,4) appears in none of those terms: it is a graph edge with
    no area, and it is not a diagonal because it is not a shape at all. That pair of points is
    exactly what the parser used to measure as a full-width wire, and a real design's millions
    of them are the "45-degree shapes" a run reported on layers whose design rules forbid 45
    degrees.
    """
    data = _build(tmp_path, _nets(["- n1 ( PIN A ) + ROUTED M3 ( 1000 3000 ) ( 6000 3000 ) "
                                   "VIRTUAL ( 8000 4000 ) RECT ( -3000 0 -1000 2000 ) "
                                   "( 8000 9000 ) ;\n"]), grid_size=10.0)
    detail = data.cell_detail(0, 0, "L:M3")
    assert detail["consumed"] == pytest.approx(1.04 + 4.41 + 1.04)
    assert detail["util"] == pytest.approx(0.0649)
    assert data.totals["virtual"] == 1
    assert data.totals["diagonals"] == 0
    assert data.totals["emitted"] == 3          # the two wires and the rectangle
