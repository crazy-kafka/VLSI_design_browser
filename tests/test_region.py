"""Pure region-selection logic: tile snapping and region-restricted metrics."""
import json

import pytest

from vlsi_viewer import schema
from vlsi_viewer.metrics import RAW_COLS, build_design
from vlsi_viewer.model import view_for_region
from vlsi_viewer.physical import build_physical
from vlsi_viewer.region import RegionData, RegionSelection, selection_from_points


def _design_and_physical(tmp_path):
    cell = tmp_path / "cell.json"
    cell.write_text(json.dumps({
        "C1": {"area": 4, "size_x": 2, "size_y": 2,
               "is_inverter": True, "drive_size": 1},
        "C2": {"area": 3, "size_x": 2, "size_y": 2, "is_register_cell": True,
               "register_bit_count": 2, "drive_size": 4, "is_ULVT": True},
        "M1": {"area": 100, "size_x": 10, "size_y": 10, "is_macro": True},
        "TAP": {"area": 0.5, "size_x": 1, "size_y": 1, "is_physical_only": True},
    }))
    top = tmp_path / "top.json"
    top.write_text(json.dumps({
        "top_name": "TOP", "boundary": [[0, 0], [20, 20]],
        "instances": {
            "u1": {"cell_name": "SUB", "location_x": 0, "location_y": 0},
            "u2": {"cell_name": "SUB", "location_x": 10, "location_y": 0},
            "edge": {"cell_name": "C1", "location_x": 4, "location_y": 0},
            "m": {"cell_name": "M1", "location_x": 12, "location_y": 12},
            "t": {"cell_name": "TAP", "location_x": 5, "location_y": 5},
        },
    }))
    sub = tmp_path / "sub.json"
    sub.write_text(json.dumps({
        "top_name": "SUB", "boundary": [[0, 0], [10, 10]],
        "instances": {
            "a": {"cell_name": "C1", "location_x": 0, "location_y": 0},
            "b": {"cell_name": "C2", "location_x": 3, "location_y": 0},
        },
    }))
    paths = [str(top), str(sub)]
    return build_design(paths, str(cell)), build_physical(
        paths, str(cell), grid_size=4.0)


EXTENT = (0.0, 0.0, 20.0, 20.0)


def _select(px0, py0, px1, py1):
    return selection_from_points(px0, py0, px1, py1, EXTENT, 4.0, 5, 5)


def test_selection_from_a_click_is_one_tile():
    s = _select(1, 1, 1, 1)
    assert s.rect == (0.0, 0.0, 4.0, 4.0)
    assert (s.col0, s.row0, s.col1, s.row1) == (0, 0, 0, 0)
    assert s.tile_count == 1


def test_selection_drag_is_inclusive():
    s = _select(0, 0, 8, 8)
    assert (s.col0, s.col1) == (0, 2)
    assert s.rect == (0.0, 0.0, 12.0, 12.0)
    assert s.tile_count == 9


def test_selection_includes_the_tile_under_a_boundary_endpoint():
    # The drag ends exactly on the x=4 line, so tile 1 is included; documented behaviour.
    s = _select(0, 0, 4, 4)
    assert (s.col0, s.col1, s.row0, s.row1) == (0, 1, 0, 1)
    assert s.rect == (0.0, 0.0, 8.0, 8.0)


def test_selection_clamps_at_the_tile_grid_edge():
    s = _select(18, 18, 25, 25)
    assert (s.col0, s.col1, s.row0, s.row1) == (4, 4, 4, 4)
    assert s.rect == (16.0, 16.0, 20.0, 20.0)


def test_selection_entirely_outside_is_none():
    assert _select(25, 25, 30, 30) is None
    assert _select(20, 20, 20, 20) is None


def test_selection_from_outside_clamps_into_the_grid():
    s = _select(-5, -5, 1, 1)
    assert s.rect == (0.0, 0.0, 4.0, 4.0)


def test_selection_of_the_whole_die():
    s = _select(0, 0, 20, 20)
    assert (s.col0, s.col1, s.row0, s.row1) == (0, 4, 0, 4)
    assert s.tile_count == 25


def test_region_stats_intersect_and_apportion(tmp_path):
    design, physical = _design_and_physical(tmp_path)
    region = RegionData(physical, design, _select(0, 0, 3, 3))

    got = region.stats("TOP")
    assert set(got) == set(RAW_COLS)
    # u1/a is fully inside; u1/b straddles x=4 and contributes half its area and bits.
    assert got["count"] == 2
    assert got["area"] == pytest.approx(4.0 + 3.0 * 0.5)
    assert got["ulvt_area"] == pytest.approx(3.0 * 0.5)
    assert got["bi_area"] == pytest.approx(4.0)
    assert got["bi_count"] == 1
    assert got["reg_bits"] == pytest.approx(1.0)
    assert got["mb_bits"] == pytest.approx(1.0)
    assert got["d1d2_count"] == 1
    assert got["macro_count"] == 0
    assert got["macro_area"] == pytest.approx(0.0)


def test_region_excludes_boxes_that_only_touch_the_edge(tmp_path):
    design, physical = _design_and_physical(tmp_path)
    region = RegionData(physical, design, _select(0, 0, 3, 3))
    # TOP/edge starts at x=4, the selection's right edge: zero overlap, not counted.
    assert region.stats("TOP")["count"] == 2


def test_region_excludes_physical_only_instances(tmp_path):
    design, physical = _design_and_physical(tmp_path)
    # Tile (1,1) contains only the TAP instance.
    region = RegionData(physical, design, _select(4, 4, 5, 5))
    assert region.selected_count == 0
    assert region.stats("TOP") is None
    assert region.any_selected("TOP") is False


def test_region_macro_stats(tmp_path):
    design, physical = _design_and_physical(tmp_path)
    # Tile (3,3) is [12,12,16,16], a quarter of the 10x10 macro: area 16.
    region = RegionData(physical, design, _select(12, 12, 12.1, 12.1))
    got = region.stats("TOP")
    assert got["macro_count"] == 1
    assert got["macro_area"] == pytest.approx(16.0)
    assert got["count"] == 0
    # u2's boxes are at y=0..2, outside this tile.
    assert region.any_selected("TOP/u2") is False


def test_region_filters_children_to_the_selected_subtree(tmp_path):
    design, physical = _design_and_physical(tmp_path)
    region = RegionData(physical, design, _select(0, 0, 3, 3))
    assert region.any_selected("TOP/u1") is True
    assert region.any_selected("TOP/u2") is False


def test_region_whole_die_matches_the_design_metrics(tmp_path):
    """A selection containing every box must reproduce the main tree's metrics."""
    design, physical = _design_and_physical(tmp_path)
    full = RegionSelection(rect=(-10.0, -10.0, 30.0, 30.0),
                           col0=0, row0=0, col1=4, row1=4)
    region = RegionData(physical, design, full)
    mv = design.metric_values(include_macros=True)
    for path in design.hier.index:
        got = region.metric_values(path)
        for m in schema.METRICS:
            assert got[m.key] == pytest.approx(
                float(mv.loc[path, m.key]), nan_ok=True)


def test_region_prefetch_fills_the_metric_cache(tmp_path):
    design, physical = _design_and_physical(tmp_path)
    region = RegionData(physical, design, _select(0, 0, 3, 3))
    region.prefetch(["TOP", "TOP/u1", "TOP/u2"])
    assert region.metric_values("TOP")["area"] == pytest.approx(5.5)
    assert region.metric_values("TOP/u2") == {}
    assert region.summary_text().startswith("1 × 1 tiles")


def test_region_view_columns_follow_schema_metrics(tmp_path):
    """A metric added to the registry must appear in the region tree automatically."""
    design, physical = _design_and_physical(tmp_path)
    region = RegionData(physical, design, _select(0, 0, 3, 3))
    view = view_for_region(region)
    assert [c.label for c in view.columns] == [m.label for m in schema.STD_METRICS]
    with_macros = view_for_region(region, include_macros=True)
    assert [c.label for c in with_macros.columns] == [m.label for m in schema.METRICS]


def test_region_view_filters_roots_children_and_series(tmp_path):
    design, physical = _design_and_physical(tmp_path)
    region = RegionData(physical, design, _select(0, 0, 3, 3))
    view = view_for_region(region)

    assert view.roots == ["TOP"]
    assert view.children.get("TOP") == ["TOP/u1"]
    assert view.children.get("TOP/u1") == []
    assert view.counts.get("TOP") == 2
    assert view.counts.get("missing", 0) == 0

    area = view.columns[0]
    assert area.label == "Area"
    assert area.series.get("TOP") == pytest.approx(5.5)
    assert area.series.get("TOP/u2", None) is None
    assert area.series.get("missing", "d") == "d"
    # Bars are normalized by the region root total, not the whole design.
    assert area.bar.get("TOP") == pytest.approx(1.0)
    assert area.bar.get("TOP/u1") == pytest.approx(1.0)


def test_region_zero_area_box_does_not_divide_by_zero(tmp_path):
    cell = tmp_path / "cell.json"
    cell.write_text(json.dumps({
        "Z": {"area": 1, "size_x": 0, "size_y": 1},
    }))
    top = tmp_path / "top.json"
    top.write_text(json.dumps({
        "top_name": "TOP", "boundary": [[0, 0], [8, 8]],
        "instances": {"z": {"cell_name": "Z", "location_x": 1, "location_y": 1}},
    }))
    paths = [str(top)]
    design = build_design(paths, str(cell))
    physical = build_physical(paths, str(cell), grid_size=4.0)
    selection = selection_from_points(0, 0, 1, 1, (0, 0, 8, 8), 4.0, 2, 2)
    region = RegionData(physical, design, selection)
    got = region.stats("TOP")
    assert got["count"] == 1
    assert got["area"] == pytest.approx(0.0)
