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
