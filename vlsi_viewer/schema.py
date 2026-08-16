"""Declarative schema: input attribute specs and the metric registry.

Adding a new input attribute or a new metric is a one-place change here:
- new attribute -> append one :class:`AttrSpec` to ``INSTANCE_ATTRS`` or ``CELL_ATTRS``.
- new metric     -> append one :class:`MetricSpec` to ``METRICS`` (its compute
  function reads raw aggregate columns produced by ``metrics.py``).
"""
from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class AttrSpec:
    """One input attribute: name, type, and the missing-value default."""
    name: str
    type: str          # "bool" | "int" | "float" | "str"
    default: object


# instance_info.json value fields (key = leaf_instance_name).
INSTANCE_ATTRS = [
    AttrSpec("cell_name", "str", None),  # join key; None => missing cell
    AttrSpec("dynamic_power", "float", 0.0),
    AttrSpec("leakage_power", "float", 0.0),
    AttrSpec("orient", "str", ""),
    AttrSpec("location_x", "float", 0.0),
    AttrSpec("location_y", "float", 0.0),
    AttrSpec("is_physical_only", "bool", False),
]

# cell_info.json value fields (key = cell_name).
CELL_ATTRS = [
    AttrSpec("area", "float", 0.0),
    AttrSpec("size_x", "float", 0.0),
    AttrSpec("size_y", "float", 0.0),
    AttrSpec("is_combinational_cell", "bool", False),
    AttrSpec("is_pulse_latch", "bool", False),
    AttrSpec("is_register_cell", "bool", False),
    AttrSpec("register_bit_count", "int", 0),
    AttrSpec("drive_size", "int", 0),
    AttrSpec("is_SVT", "bool", False),
    AttrSpec("is_LVT", "bool", False),
    AttrSpec("is_ULVT", "bool", False),
    AttrSpec("is_sram", "bool", False),
    AttrSpec("is_macro", "bool", False),
    AttrSpec("is_buffer", "bool", False),
    AttrSpec("is_inverter", "bool", False),
    AttrSpec("is_clock_cell", "bool", False),
    AttrSpec("is_integrated_clock_gating_cell", "bool", False),
]


def _ratio(num: pd.Series, den: pd.Series) -> pd.Series:
    """Divide two series, mapping inf/NaN from 0/0 or x/0 to NaN."""
    with np.errstate(divide="ignore", invalid="ignore"):
        r = num / den
    return r.replace([np.inf, -np.inf], np.nan)


# Raw aggregate columns (produced by metrics._flatten) that metrics read from.
def _m_area(g):    return g["area"]
def _m_count(g):   return g["count"]
def _m_ulvt(g):    return _ratio(g["ulvt_area"], g["area"])
def _m_mb(g):      return _ratio(g["mb_bits"], g["reg_bits"])
def _m_d1d2(g):    return _ratio(g["d1d2_count"], g["count"])
def _m_bi_count(g): return g["bi_count"]
def _m_bi_area(g): return g["bi_area"]
def _m_macro_count(g): return g["macro_count"]
def _m_macro_area(g):  return g["macro_area"]


@dataclass(frozen=True)
class MetricSpec:
    """One metric: how it is identified, labelled, formatted, and computed."""
    key: str
    label: str
    kind: str          # "count" | "area" | "percent"
    is_macro: bool
    compute: Callable[[pd.DataFrame], pd.Series]


METRICS = [
    MetricSpec("area", "Area", "area", False, _m_area),
    MetricSpec("count", "Count", "count", False, _m_count),
    MetricSpec("ulvt_ratio", "ULVT%", "percent", False, _m_ulvt),
    MetricSpec("mb_ratio", "MB%", "percent", False, _m_mb),
    MetricSpec("d1d2_ratio", "D1D2%", "percent", False, _m_d1d2),
    MetricSpec("bi_count", "B/I Cnt", "count", False, _m_bi_count),
    MetricSpec("bi_area", "B/I Area", "area", False, _m_bi_area),
    MetricSpec("macro_count", "Macro Cnt", "count", True, _m_macro_count),
    MetricSpec("macro_area", "Macro Area", "area", True, _m_macro_area),
]

STD_METRICS = [m for m in METRICS if not m.is_macro]
MACRO_METRICS = [m for m in METRICS if m.is_macro]

_METRIC_BY_KEY = {m.key: m for m in METRICS}


def metric_by_key(key: str) -> MetricSpec:
    return _METRIC_BY_KEY[key]


def format_metric(kind: str, value) -> str:
    """Render a metric scalar for display. NaN/inf/None -> em dash."""
    if value is None:
        return "—"
    try:
        if pd.isna(value) or np.isinf(value):
            return "—"
    except (TypeError, ValueError):
        pass
    if kind == "percent":
        return f"{value * 100:.2f}%"
    if kind == "area":
        return f"{value:,.2f}"
    return f"{int(value):,}"


def diff_values(kind: str, v1, v2):
    """Return ``(delta_abs, delta_rel)`` for two versions of a metric.

    ``delta_abs`` is in native units, except percent metrics use percentage
    points. ``delta_rel`` is a fraction (None when v1 is zero or either side
    is undefined).
    """
    if v1 is None or v2 is None:
        return (None, None)
    try:
        if pd.isna(v1) or pd.isna(v2) or np.isinf(v1) or np.isinf(v2):
            return (None, None)
    except (TypeError, ValueError):
        pass
    d = v2 - v1
    d_abs = d * 100.0 if kind == "percent" else d
    if v1 == 0:
        return (d_abs, None)
    return (d_abs, (v2 - v1) / v1)


def format_delta_abs(kind: str, value) -> str:
    """Render a signed absolute delta (percent metrics -> percentage points)."""
    if value is None:
        return "—"
    try:
        if pd.isna(value) or np.isinf(value):
            return "—"
    except (TypeError, ValueError):
        pass
    if kind == "count":
        return f"{int(value):+,}"
    if kind == "area":
        return f"{value:+,.2f}"
    return f"{value:+.2f}pt"


def format_delta_rel(value) -> str:
    """Render a signed relative delta as a percentage."""
    if value is None:
        return "—"
    try:
        if pd.isna(value) or np.isinf(value):
            return "—"
    except (TypeError, ValueError):
        pass
    return f"{value * 100:+.2f}%"
