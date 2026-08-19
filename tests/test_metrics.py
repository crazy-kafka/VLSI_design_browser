import os

import numpy as np
import pandas as pd
import pytest

from vlsi_viewer.metrics import build_design, load_or_build
from vlsi_viewer import schema


def test_hierarchy_nodes_and_roots(design):
    nodes = set(design.hier.index)
    assert nodes == {"TOP", "TOP/MACROA", "TOP/MACROA/UNIT1", "TOP/UNIT2"}
    assert design.roots == ["TOP"]


def test_depths_and_parents(design):
    h = design.hier
    assert h.loc["TOP", "depth"] == 1
    assert h.loc["TOP", "parent"] == ""
    assert h.loc["TOP/MACROA", "depth"] == 2
    assert h.loc["TOP/MACROA", "parent"] == "TOP"
    assert h.loc["TOP/MACROA/UNIT1", "parent"] == "TOP/MACROA"


def test_children_map(design):
    assert set(design.children["TOP"]) == {"TOP/MACROA", "TOP/UNIT2"}
    assert design.children["TOP/MACROA"] == ["TOP/MACROA/UNIT1"]
    assert design.children.get("TOP/MACROA/UNIT1") in ([], None)


def _mv(design, path, key):
    return design.metric_values().loc[path, key]


def test_std_metrics_unit1(design):
    # TOP/MACROA/UNIT1 has inv(1.0)+buf(2.0)+dff_x2(3.0)+dff_x1(4.0)
    assert _mv(design, "TOP/MACROA/UNIT1", "count") == 4
    assert _mv(design, "TOP/MACROA/UNIT1", "area") == pytest.approx(10.0)
    assert _mv(design, "TOP/MACROA/UNIT1", "ulvt_ratio") == pytest.approx(0.7)
    assert _mv(design, "TOP/MACROA/UNIT1", "mb_ratio") == pytest.approx(2 / 3)
    assert _mv(design, "TOP/MACROA/UNIT1", "d1d2_ratio") == pytest.approx(0.5)
    assert _mv(design, "TOP/MACROA/UNIT1", "bi_count") == 2
    assert _mv(design, "TOP/MACROA/UNIT1", "bi_area") == pytest.approx(3.0)


def test_flatten_top(design):
    # TOP aggregates all 5 counted leaves (excludes macro, physical-only, missing).
    assert _mv(design, "TOP", "count") == 5
    assert _mv(design, "TOP", "area") == pytest.approx(11.5)
    assert _mv(design, "TOP", "ulvt_ratio") == pytest.approx(7 / 11.5)
    assert _mv(design, "TOP", "mb_ratio") == pytest.approx(2 / 3)
    assert _mv(design, "TOP", "d1d2_ratio") == pytest.approx(0.4)
    assert _mv(design, "TOP", "bi_count") == 2
    assert _mv(design, "TOP", "bi_area") == pytest.approx(3.0)


def test_intermediate_flatten_macroa(design):
    # TOP/MACROA has no direct leaves; flatten equals its only child's aggregate.
    assert _mv(design, "TOP/MACROA", "count") == 4
    assert _mv(design, "TOP/MACROA", "area") == pytest.approx(10.0)


def test_division_by_zero_is_nan(design):
    # TOP/UNIT2 has no registers -> MB ratio undefined.
    assert pd.isna(_mv(design, "TOP/UNIT2", "mb_ratio"))


def test_macro_excluded_from_std(design):
    # SRAM is a macro and must not inflate std metrics.
    assert _mv(design, "TOP/UNIT2", "area") == pytest.approx(1.5)
    assert _mv(design, "TOP/UNIT2", "count") == 1


def test_macro_columns(design):
    mv = design.metric_values(include_macros=True)
    assert mv.loc["TOP", "macro_count"] == 1
    assert mv.loc["TOP", "macro_area"] == pytest.approx(100.0)
    assert mv.loc["TOP/UNIT2", "macro_count"] == 1
    assert mv.loc["TOP/MACROA", "macro_count"] == 0
    # std metric_values() excludes macro columns.
    assert "macro_count" not in design.metric_values().columns


def test_missing_cells_reported(design):
    assert design.missing_cells == ["UNKNOWN"]


def test_metric_registry_columns(design):
    assert [m.key for m in schema.STD_METRICS] == [
        "area", "count", "ulvt_ratio", "mb_ratio", "d1d2_ratio", "bits",
        "ckb_count", "icg_count", "pul_count", "bi_count", "bi_area",
    ]
    assert [m.key for m in schema.MACRO_METRICS] == ["macro_count", "macro_area"]


def test_new_metrics(tmp_path):
    import json

    cell = {
        "PULSE": {"area": 1.0, "is_pulse_latch": True},
        "CLKBUF": {"area": 1.0, "is_buffer": True, "is_clock_cell": True},
        "CLKINV": {"area": 1.0, "is_inverter": True, "is_clock_cell": True},
        "BUF": {"area": 1.0, "is_buffer": True},
        "ICG": {"area": 1.0, "is_integrated_clock_gating_cell": True},
        "AND": {"area": 1.0, "is_combinational_cell": True},
    }
    inst = {"top_name": "TOP", "instances": {
        "a/pulse": {"cell_name": "PULSE"},
        "b/clkbuf": {"cell_name": "CLKBUF"},
        "c/clkinv": {"cell_name": "CLKINV"},
        "d/buf": {"cell_name": "BUF"},
        "e/icg": {"cell_name": "ICG"},
        "f/and": {"cell_name": "AND"},
    }}
    (tmp_path / "cell_info.json").write_text(json.dumps(cell))
    (tmp_path / "instance_info.json").write_text(json.dumps(inst))
    design = build_design([str(tmp_path / "instance_info.json")], str(tmp_path / "cell_info.json"))
    mv = design.metric_values()
    assert mv.loc["TOP", "pul_count"] == 1
    assert mv.loc["TOP", "ckb_count"] == 2   # CLKBUF + CLKINV (BUF is not a clock cell)
    assert mv.loc["TOP", "icg_count"] == 1


def test_gradient_range_defaults_and_validation():
    assert schema.gradient_range("ulvt_ratio") == (0.0, 0.35)
    assert schema.gradient_range("mb_ratio") == (0.5, 0.9)
    assert schema.gradient_range("d1d2_ratio") == (0.55, 0.9)
    # compare-mode Δrel columns default to [-0.5, 0.5]
    assert schema.gradient_range("area_rel") == (-0.5, 0.5)
    assert schema.gradient_range("ulvt_ratio_rel") == (-0.5, 0.5)
    assert schema.gradient_range("unknown") == (0.0, 1.0)
    try:
        schema.set_gradient_range("ulvt_ratio", 0.1, 0.5)
        assert schema.gradient_range("ulvt_ratio") == (0.1, 0.5)
        # ranges may be negative now (diff deltas)
        schema.set_gradient_range("ulvt_ratio", -0.3, 0.4)
        assert schema.gradient_range("ulvt_ratio") == (-0.3, 0.4)
        with pytest.raises(ValueError):
            schema.set_gradient_range("ulvt_ratio", 0.8, 0.2)  # min > max
    finally:
        schema.set_gradient_range("ulvt_ratio", 0.0, 0.35)


def test_formatting():
    assert schema.format_metric("count", 12345) == "12,345"
    assert schema.format_metric("area", 12.5) == "12.50"
    assert schema.format_metric("percent", 0.1234) == "12.34%"
    assert schema.format_metric("percent", float("nan")) == "—"
    assert schema.format_metric("count", None) == "—"


def test_diff_values():
    assert schema.diff_values("count", 100, 130) == (30, pytest.approx(0.3))
    d_abs, d_rel = schema.diff_values("percent", 0.10, 0.15)
    assert d_abs == pytest.approx(5.0)
    assert d_rel == pytest.approx(0.5)
    assert schema.diff_values("count", 0, 5) == (5, None)
    assert schema.diff_values("count", None, 5) == (None, None)


def test_pickle_round_trip(sample_dir, tmp_path):
    inst = os.path.join(sample_dir, "instance_info.json")
    cell = os.path.join(sample_dir, "cell_info.json")
    cache = str(tmp_path / "cache")

    d1 = load_or_build([inst], cell, cache_dir=cache)
    d2 = load_or_build([inst], cell, cache_dir=cache)  # cache hit
    assert sorted(d2.missing_cells) == sorted(d1.missing_cells)
    assert list(d2.hier.index) == list(d1.hier.index)
    pd.testing.assert_frame_equal(d1.hier, d2.hier)
    # force rebuild bypasses cache
    d3 = load_or_build([inst], cell, cache_dir=cache, force=True)
    pd.testing.assert_frame_equal(d1.hier, d3.hier)


def test_bar_series():
    from vlsi_viewer.model import bar_series

    idx = pd.Index(["TOP", "TOP/A", "TOP/B"])
    counts = pd.Series([100.0, 40.0, 60.0], index=idx)
    bar = bar_series(counts, ["TOP"], "count")
    assert bar.loc["TOP"] == pytest.approx(1.0)
    assert bar.loc["TOP/A"] == pytest.approx(0.4)
    assert bar.loc["TOP/B"] == pytest.approx(0.6)

    pct = pd.Series([0.7, 0.2, 1.5], index=idx)
    bar_pct = bar_series(pct, ["TOP"], "percent")
    assert bar_pct.loc["TOP/A"] == pytest.approx(0.2)
    assert bar_pct.loc["TOP/B"] == pytest.approx(1.0)  # clipped

    zero = pd.Series([0.0, 0.0], index=pd.Index(["TOP", "TOP/A"]))
    bar_zero = bar_series(zero, ["TOP"], "area")
    assert pd.isna(bar_zero.loc["TOP"])
