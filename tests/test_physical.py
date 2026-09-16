import json

import pytest

from vlsi_viewer.physical import build_physical


def _cell(path, cell_name, area, size_x, size_y, leakage=1.0, dynamic=2.0, **extra):
    d = {"area": area, "size_x": size_x, "size_y": size_y,
         "leakage_power": leakage, "dynamic_power": dynamic}
    d.update(extra)
    path.write_text(json.dumps({cell_name: d}))


def _block(tmp_path, name, instances, boundary, fname=None):
    p = tmp_path / (fname or f"{name}.json")
    p.write_text(json.dumps({"top_name": name, "instances": instances,
                             "boundary": boundary}))
    return str(p)


def test_flat_cell_density(tmp_path):
    cell = tmp_path / "cell.json"
    _cell(cell, "C1", area=4, size_x=2, size_y=2, leakage=1.0)
    b = _block(tmp_path, "TOP",
               {"c": {"cell_name": "C1", "location_x": 0, "location_y": 0,
                      "leakage_power": 1.0, "dynamic_power": 2.0}},
               boundary=[(0, 0), (20, 20)])
    pd_ = build_physical([b], str(cell), grid_size=4.0)
    assert pd_.rows == 5 and pd_.cols == 5
    assert pd_.density[0, 0] == pytest.approx(4 / 16)
    assert pd_.leakage[0, 0] == pytest.approx(1.0)
    assert pd_.dynamic[0, 0] == pytest.approx(2.0)


def test_nested_block_placement(tmp_path):
    cell = tmp_path / "cell.json"
    _cell(cell, "C1", area=4, size_x=2, size_y=2, leakage=1.0)
    top = _block(tmp_path, "TOP", {"b": {"cell_name": "B", "location_x": 4, "location_y": 0}},
                 boundary=[(0, 0), (20, 20)], fname="top.json")
    sub = _block(tmp_path, "B", {"c": {"cell_name": "C1", "location_x": 0, "location_y": 0}},
                 boundary=[(0, 0), (6, 6)], fname="sub.json")
    pd_ = build_physical([top, sub], str(cell), grid_size=4.0)
    # cell global box = [4, 0, 6, 2] -> grid cell (1, 0)
    assert pd_.density[0, 1] == pytest.approx(4 / 16)
    assert pd_.density[0, 0] == 0.0


def test_nested_rotated_block(tmp_path):
    cell = tmp_path / "cell.json"
    _cell(cell, "C1", area=4, size_x=2, size_y=2, leakage=1.0)
    top = _block(tmp_path, "TOP", {"b": {"cell_name": "B", "location_x": 4, "location_y": 0,
                                         "orient": "W"}},
                 boundary=[(0, 0), (20, 20)], fname="top.json")
    sub = _block(tmp_path, "B", {"c": {"cell_name": "C1", "location_x": 0, "location_y": 0}},
                 boundary=[(0, 0), (6, 6)], fname="sub.json")
    pd_ = build_physical([top, sub], str(cell), grid_size=4.0)
    # W rotation maps the 2x2 cell to global box [2, 0, 4, 2] -> grid cell (0, 0)
    assert pd_.density[0, 0] == pytest.approx(4 / 16)
    assert pd_.density[0, 1] == 0.0


def test_cell_box_crosses_grid_boundary(tmp_path):
    cell = tmp_path / "cell.json"
    _cell(cell, "C1", area=9, size_x=3, size_y=3, leakage=1.0)
    b = _block(tmp_path, "TOP", {"c": {"cell_name": "C1", "location_x": 3, "location_y": 3}},
               boundary=[(0, 0), (8, 8)])
    pd_ = build_physical([b], str(cell), grid_size=4.0)
    # 3x3 cell at [3,3,6,6] overlaps all four 4x4 grid cells
    for ix in (0, 1):
        for iy in (0, 1):
            assert pd_.density[iy, ix] > 0.0
    assert abs(pd_.density.sum() - 9 / 16) < 1e-9  # area preserved / grid_area


def test_nested_rotated_block_two_levels(tmp_path):
    """A rotated parent composed with a translated child block must place the
    leaf cell correctly (frames applied innermost-first)."""
    cell = tmp_path / "cell.json"
    _cell(cell, "C1", area=4, size_x=2, size_y=2)
    top = _block(tmp_path, "TOP",
                 {"b": {"cell_name": "B", "location_x": 10, "location_y": 10, "orient": "W"}},
                 boundary=[(0, 0), (40, 40)], fname="top.json")
    sub = _block(tmp_path, "B",
                 {"s": {"cell_name": "S", "location_x": 5, "location_y": 5}},
                 boundary=[(0, 0), (10, 10)], fname="sub.json")
    leaf = _block(tmp_path, "S",
                  {"c": {"cell_name": "C1", "location_x": 0, "location_y": 0}},
                  boundary=[(0, 0), (10, 10)], fname="leaf.json")
    pd_ = build_physical([top, sub, leaf], str(cell), grid_size=10.0)
    # S occupies B-local [5,7]x[5,7]; B's W frame maps (x,y) -> (10-y, 10+x),
    # so the 2x2 cell lands at global [3,5]x[15,17].
    assert pd_.boxes[0][0] == pytest.approx(3.0)
    assert pd_.boxes[0][1] == pytest.approx(15.0)
    assert pd_.boxes[0][2] == pytest.approx(5.0)
    assert pd_.boxes[0][3] == pytest.approx(17.0)


def test_ulvt_density_grid(tmp_path):
    """The ULVT density grid counts only is_ULVT cells (area / bin area)."""
    import json as _json
    cell = tmp_path / "cell.json"
    cell.write_text(_json.dumps({
        "U": {"area": 4, "size_x": 2, "size_y": 2, "is_ULVT": True},
        "S": {"area": 4, "size_x": 2, "size_y": 2, "is_SVT": True},
    }))
    b = _block(tmp_path, "TOP",
               {"u": {"cell_name": "U", "location_x": 0, "location_y": 0},
                "s": {"cell_name": "S", "location_x": 10, "location_y": 0}},
               boundary=[(0, 0), (20, 20)])
    pd_ = build_physical([b], str(cell), grid_size=4.0)
    assert pd_.density[0, 0] == pytest.approx(4 / 16)   # ULVT cell
    assert pd_.ulvt[0, 0] == pytest.approx(4 / 16)
    assert pd_.density[0, 2] == pytest.approx(4 / 16)   # SVT cell at x=10
    assert pd_.ulvt[0, 2] == 0.0                        # SVT excluded from ulvt


def test_path_tagging_and_hierarchy_density(tmp_path):
    import json as _json
    cell = tmp_path / "cell.json"
    cell.write_text(_json.dumps({
        "M": {"area": 4, "size_x": 2, "size_y": 2, "is_macro": True},
        "S": {"area": 4, "size_x": 2, "size_y": 2, "is_SVT": True},
    }))
    b = _block(tmp_path, "TOP",
               {"m": {"cell_name": "M", "location_x": 0, "location_y": 0},
                "s": {"cell_name": "S", "location_x": 5, "location_y": 0}},
               boundary=[(0, 0), (20, 20)])
    pd_ = build_physical([b], str(cell), grid_size=4.0)
    # boxes carry their full hierarchy path and macro flag
    paths = {box[7] for box in pd_.boxes}
    assert paths == {"TOP/m", "TOP/s"}
    macro_flags = {box[7]: box[8] for box in pd_.boxes}
    assert macro_flags["TOP/m"] is True and macro_flags["TOP/s"] is False
    # slice-based path access returns exactly that hierarchy's boxes
    assert len(pd_.boxes_for("TOP")) == 2
    assert len(pd_.boxes_for("TOP/m")) == 1
    # density = non_macro_area / (contour_area - macro_area); both in [0,1]
    d = pd_.density_for("TOP")
    assert 0.0 <= d <= 1.0


def test_slice_for_excludes_path_extending_sibling(tmp_path):
    """`TOP/cpu` must not include the sibling `TOP/cpu_aux`."""
    import json as _json
    cell = tmp_path / "cell.json"
    cell.write_text(_json.dumps({"C1": {"area": 4, "size_x": 2, "size_y": 2}}))
    b = _block(tmp_path, "TOP",
               {"cpu": {"cell_name": "C1", "location_x": 0, "location_y": 0},
                "cpu_aux": {"cell_name": "C1", "location_x": 10, "location_y": 0}},
               boundary=[(0, 0), (30, 20)])
    pd_ = build_physical([b], str(cell), grid_size=4.0)
    assert {box[7] for box in pd_.boxes} == {"TOP/cpu", "TOP/cpu_aux"}
    assert len(pd_.boxes_for("TOP/cpu")) == 1
    assert len(pd_.boxes_for("TOP/cpu_aux")) == 1
    assert len(pd_.boxes_for("TOP")) == 2


def test_negative_contour_gap_rejected(tmp_path):
    cell = tmp_path / "cell.json"
    _cell(cell, "C1", area=4, size_x=2, size_y=2)
    b = _block(tmp_path, "TOP", {"c": {"cell_name": "C1"}},
               boundary=[(0, 0), (10, 10)])
    with pytest.raises(ValueError, match="contour gap"):
        build_physical([b], str(cell), grid_size=4.0, contour_gap=-1.0)


def test_density_nan_not_one_when_undefined(tmp_path):
    """Density must be NaN (not 1.0) when there is no non-macro area."""
    import json as _json
    import math
    cell = tmp_path / "cell.json"
    cell.write_text(_json.dumps({"M": {"area": 4, "size_x": 2, "size_y": 2, "is_macro": True}}))
    b = _block(tmp_path, "TOP",
               {"m": {"cell_name": "M", "location_x": 0, "location_y": 0}},
               boundary=[(0, 0), (20, 20)])
    pd_ = build_physical([b], str(cell), grid_size=4.0)
    assert math.isnan(pd_.density_for("TOP"))  # all-macro -> no non-macro area


def test_density_clamped_to_one(tmp_path):
    """Two fully-overlapping cells produce raw density 2.0; the grid clamps it
    to exactly 1.0 so fully-packed bins render white (not red/white noise)."""
    cell = tmp_path / "cell.json"
    _cell(cell, "C1", area=4, size_x=2, size_y=2)
    b = _block(tmp_path, "TOP",
               {"a": {"cell_name": "C1", "location_x": 0, "location_y": 0},
                "b": {"cell_name": "C1", "location_x": 0, "location_y": 0}},
               boundary=[(0, 0), (2, 2)])
    pd_ = build_physical([b], str(cell), grid_size=2.0)
    assert pd_.density.max() == 1.0
    assert pd_.density.min() >= 0.0


def test_multiple_top_blocks_error(tmp_path):
    cell = tmp_path / "cell.json"
    _cell(cell, "C1", area=4, size_x=2, size_y=2)
    a = _block(tmp_path, "A", {"c": {"cell_name": "C1"}}, boundary=[(0, 0), (5, 5)], fname="a.json")
    c2 = _block(tmp_path, "C", {"c": {"cell_name": "C1"}}, boundary=[(0, 0), (5, 5)], fname="c.json")
    with pytest.raises(ValueError, match="exactly one top-level"):
        build_physical([a, c2], str(cell))


def test_missing_top_boundary_error(tmp_path):
    cell = tmp_path / "cell.json"
    _cell(cell, "C1", area=4, size_x=2, size_y=2)
    p = tmp_path / "top.json"
    p.write_text(json.dumps({"top_name": "A", "instances": {"c": {"cell_name": "C1"}}}))
    with pytest.raises(ValueError, match="boundary"):
        build_physical([str(p)], str(cell))


def test_boundary_polys_collected(tmp_path):
    cell = tmp_path / "cell.json"
    _cell(cell, "C1", area=4, size_x=2, size_y=2)
    top = _block(tmp_path, "TOP", {"b": {"cell_name": "B", "location_x": 10, "location_y": 0}},
                 boundary=[(0, 0), (20, 20)], fname="top.json")
    sub = _block(tmp_path, "B", {"c": {"cell_name": "C1", "location_x": 0, "location_y": 0}},
                 boundary=[(0, 0), (6, 6)], fname="sub.json")
    pd_ = build_physical([top, sub], str(cell))
    names = {n for n, _ in pd_.boundary_polys}
    assert names == {"TOP", "B"}
    # sub-block boundary translated to global: starts at (10, 0)
    sub_poly = dict(pd_.boundary_polys)["B"]
    assert min(x for x, _ in sub_poly) == 10.0


@pytest.mark.parametrize("where", ["cell", "instance"])
def test_physical_only_is_density_only(tmp_path, where):
    """Physical-only area is real area: it raises density and nothing else.

    Three builds of the same design - the filler present and ordinary, present and
    physical-only, and absent altogether - pin down each surface independently: the
    density grid must match the "ordinary" build, while leakage, dynamic, ULVT,
    boxes_for, the contour and Density% must all match the "absent" build.
    """
    FILL_SIZE = 4  # 2x2 -> exactly one quarter of a 4.0 grid bin

    def build(mode):
        fill = {"area": FILL_SIZE, "size_x": 2, "size_y": 2, "is_ULVT": True}
        if mode == "physical" and where == "cell":
            fill["is_physical_only"] = True
        cell = tmp_path / f"cell_{mode}.json"
        cell.write_text(json.dumps({"C1": {"area": 4, "size_x": 2, "size_y": 2},
                                    "FILL": fill}))
        inst = {"c1": {"cell_name": "C1", "location_x": 0, "location_y": 0,
                       "leakage_power": 1.0, "dynamic_power": 2.0}}
        if mode != "absent":
            f1 = {"cell_name": "FILL", "location_x": 4, "location_y": 0,
                  "leakage_power": 5.0, "dynamic_power": 7.0}
            if mode == "physical" and where == "instance":
                f1["is_physical_only"] = True
            inst["f1"] = f1
        b = _block(tmp_path, "TOP", inst, boundary=[(0, 0), (20, 20)],
                   fname=f"top_{mode}.json")
        return build_physical([b], str(cell), grid_size=4.0)

    ordinary, physical, absent = build("ordinary"), build("physical"), build("absent")

    # density keeps the filler's area (bin (0, 1) spans x 4..8)
    assert physical.density[0, 1] == pytest.approx(FILL_SIZE / 16)
    assert physical.density[0, 1] == pytest.approx(ordinary.density[0, 1])
    assert absent.density[0, 1] == pytest.approx(0.0)

    # the other three grids drop it entirely
    for kind in ("leakage", "dynamic", "ulvt"):
        assert getattr(ordinary, kind)[0, 1] > 0.0, f"{kind} should see the filler"
        assert getattr(physical, kind)[0, 1] == pytest.approx(0.0), kind
        assert getattr(physical, kind)[0, 1] == pytest.approx(getattr(absent, kind)[0, 1]), kind

    # hierarchy surfaces exclude it: only the contour tree and Density% are affected
    assert len(ordinary.boxes_for("TOP")) == 2
    assert len(physical.boxes_for("TOP")) == 1
    assert len(physical.boxes_for("TOP")) == len(absent.boxes_for("TOP"))
    assert physical.contour_for("TOP") == absent.contour_for("TOP")
    assert physical.density_for("TOP") == pytest.approx(absent.density_for("TOP"))


# -- pin density ---------------------------------------------------------------
#
# The one grid that is not built from the boxes: it walks every placement again, transforms
# each cell's own pin geometry, and counts one point per pin. What it must get right is the
# placement rule - DEF puts the *lower-left corner of the oriented bounding box* at the
# instance's location (LEF/DEF reference), so a macro-local pin has to be rotated and then
# shifted by that corner before it lands where the view draws the cell.

ORIENTS = ("N", "S", "W", "E", "FN", "FS", "FW", "FE")


def _pin_design(tmp_path, size=(4.0, 2.0), pin=(1.0, 0.5)):
    """One ``size`` cell with a single pin at ``pin``, placed once per orientation.

    The placements sit 20 um apart along x on a 4 um grid, so each instance's box covers a
    column range of its own: a pin that landed outside its box would be counted against a
    different instance, or against none.
    """
    cell = tmp_path / "pin_cell.json"
    cell.write_text(json.dumps({"P1": {"area": size[0] * size[1], "size_x": size[0],
                                       "size_y": size[1], "leakage_power": 1.0,
                                       "dynamic_power": 2.0}}))
    inst = {}
    for i, orient in enumerate(ORIENTS):
        inst[f"u{i}"] = {"cell_name": "P1", "location_x": 20.0 * i, "location_y": 0.0,
                         "orient": orient, "leakage_power": 1.0, "dynamic_power": 2.0}
    b = _block(tmp_path, "TOP", inst, boundary=[(0, 0), (170, 20)])
    return b, str(cell), {"P1": [pin]}


def test_pin_offsets_follow_the_placement_rule():
    """The eight offsets that move a macro-local pin point onto the placed box.

    Zero for the three orientations whose rotation leaves the local lower-left corner at the
    origin, and the macro's own extent for the rest - for W it is the height, for E the width.
    """
    import numpy as np
    from vlsi_viewer.physical import _PIN_ORIENTS, _pin_offsets

    offx, offy = _pin_offsets(np.array([4.0]), np.array([2.0]))
    got = {o: (float(offx[i][0]), float(offy[i][0])) for i, o in enumerate(_PIN_ORIENTS)}
    assert got == {"N": (0.0, 0.0), "S": (4.0, 2.0), "W": (2.0, 0.0), "E": (0.0, 4.0),
                   "FN": (4.0, 0.0), "FS": (0.0, 2.0), "FW": (0.0, 0.0), "FE": (2.0, 4.0)}


def test_pin_density_counts_one_point_per_placed_pin(tmp_path):
    b, cell, pins = _pin_design(tmp_path)
    data = build_physical([b], cell, grid_size=4.0, pins=pins)
    assert data.has_pins
    assert data._pins is None            # built on first use, not while loading

    grid = data.heat("pins")
    assert data._pins is not None        # ... and kept
    assert grid.sum() == 8               # one point per placement, in every orientation

    # Every counted point falls inside the box the density map draws for its own instance.
    # The boxes come from the box pass, so this is an independent check of the transform: a
    # pin placed one macro extent away - the failure mode of ignoring the offset - lands in a
    # neighbouring instance's columns, or outside the die entirely.
    boxes = data.boxes_for("TOP")
    for i in range(len(ORIENTS)):
        x0, y0, x1, y1 = (float(v) for v in boxes[i])
        ix0, ix1 = int(x0 // 4.0), int((x1 - 1e-9) // 4.0)
        iy0, iy1 = int(y0 // 4.0), int((y1 - 1e-9) // 4.0)
        assert grid[iy0:iy1 + 1, ix0:ix1 + 1].sum() == 1, ORIENTS[i]


def test_pin_density_of_a_reused_sub_block(tmp_path):
    """A block placed twice contributes its instances twice, through their placement frames."""
    cell = tmp_path / "sub_cell.json"
    cell.write_text(json.dumps({"P1": {"area": 8.0, "size_x": 4.0, "size_y": 2.0,
                                       "leakage_power": 1.0, "dynamic_power": 2.0}}))
    top = _block(tmp_path, "TOP",
                 {"b1": {"cell_name": "B", "location_x": 0, "location_y": 0},
                  "b2": {"cell_name": "B", "location_x": 40, "location_y": 0}},
                 boundary=[(0, 0), (80, 20)], fname="top.json")
    sub = _block(tmp_path, "B",
                 {"p": {"cell_name": "P1", "location_x": 0, "location_y": 0},
                  "q": {"cell_name": "P1", "location_x": 8, "location_y": 0}},
                 boundary=[(0, 0), (12, 2)], fname="sub.json")
    data = build_physical([top, sub], str(cell), grid_size=4.0, pins={"P1": [(1.0, 0.5)]})
    grid = data.heat("pins")
    assert grid.sum() == 4                       # two instances, two placements
    # sub-block 1 puts pins at x = 1 and x = 9 -> grid columns 0 and 2; sub-block 2 at 41, 49
    assert [(ix, int(round(float(grid[0, ix])))) for ix in (0, 2, 10, 12)] == [
        (0, 1), (2, 1), (10, 1), (12, 1)]


def test_a_source_without_pins_offers_no_pin_map(tmp_path):
    """The json path: no pin geometry exists to count, so the map is not offered."""
    b, cell, _pins = _pin_design(tmp_path)
    data = build_physical([b], cell, grid_size=4.0)
    assert not data.has_pins
    with pytest.raises(KeyError):
        data.heat("pins")


def test_pin_density_under_a_rotated_sub_block(tmp_path):
    """The leaf's orientation composes *inside* its block's, not the other way round.

    A pin goes through its cell's orientation, then the placement, then the block's frame. The
    two orders differ by a rotation of the placement point, which is exactly what this pins:
    the block is W at (40, 0), its cell is N at (0, 0) with a pin at (1.0, 0.5), so the pin
    lands at (39.5, 1.0) - and the box the density map draws for that same instance is
    [38, 40] x [0, 4].
    """
    cell = tmp_path / "rot_cell.json"
    cell.write_text(json.dumps({"P1": {"area": 8.0, "size_x": 4.0, "size_y": 2.0,
                                       "leakage_power": 1.0, "dynamic_power": 2.0}}))
    top = _block(tmp_path, "TOP",
                 {"b": {"cell_name": "B", "location_x": 40.0, "location_y": 0.0,
                        "orient": "W"}},
                 boundary=[(0, 0), (80, 20)], fname="top.json")
    sub = _block(tmp_path, "B",
                 {"p": {"cell_name": "P1", "location_x": 0.0, "location_y": 0.0}},
                 boundary=[(0, 0), (12, 2)], fname="sub.json")

    data = build_physical([top, sub], str(cell), grid_size=4.0, pins={"P1": [(1.0, 0.5)]})
    grid = data.heat("pins")
    assert grid.sum() == 1
    assert grid[0, 9] == 1.0            # (39.5, 1.0) on a 4 um grid
    x0, y0, x1, y1 = (float(v) for v in data.boxes_for("TOP")[0])
    assert (x0, y0, x1, y1) == (38.0, 0.0, 40.0, 4.0)
