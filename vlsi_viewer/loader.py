"""Load ``instance_info.json`` blocks and ``cell_info.json`` into typed DataFrames.

``instance_info.json`` (new format)::

    {"top_name": "block_A", "instances": {"rel/path/leaf": {attrs...}}}

Leaf paths are relative to ``top_name``. Missing attributes are filled with
defaults and coerced per the attribute schema in :mod:`vlsi_viewer.schema`.
"""
import json
import logging

import pandas as pd

from . import schema

logger = logging.getLogger(__name__)

_DTYPE = {"bool": "bool", "int": "int64", "float": "float64", "str": "object"}


def _coerce(value, attr_type):
    if attr_type == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in ("true", "1", "yes")
        return bool(value)
    if attr_type == "int":
        return int(value)
    if attr_type == "float":
        return float(value)
    return str(value)


def _apply_spec(attrs, spec):
    """Return ``spec``'s value from the ``attrs`` dict, defaulted + coerced."""
    if not isinstance(attrs, dict) or attrs.get(spec.name) is None:
        return spec.default
    return _coerce(attrs[spec.name], spec.type)


def _cast(df, specs):
    for spec in specs:
        if spec.name in df.columns:
            df[spec.name] = df[spec.name].astype(_DTYPE[spec.type])
    return df


def _parse_boundary(raw):
    """Validate a block boundary -> list of (x, y) points, or None.

    Two points are expanded to a 4-point rectangle. Otherwise the points must
    form a rectilinear polygon (axis-aligned edges, non-degenerate).
    """
    if raw is None:
        return None
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        raise ValueError("boundary must be a list of 2 or more (x, y) points")
    pts = []
    for p in raw:
        if not isinstance(p, (list, tuple)) or len(p) != 2:
            raise ValueError(f"invalid boundary point: {p!r}")
        pts.append((float(p[0]), float(p[1])))

    if len(pts) == 2:
        # two opposite corners -> axis-aligned rectangle
        (x0, y0), (x1, y1) = pts
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

    if pts[0] == pts[-1]:
        pts = pts[:-1]  # strip an explicit closing duplicate
    if len(pts) < 4:
        raise ValueError("boundary polygon must have at least 4 distinct points")

    for i in range(len(pts)):
        ax, ay = pts[i]
        bx, by = pts[(i + 1) % len(pts)]
        if ax != bx and ay != by:
            raise ValueError("boundary must be a rectilinear polygon (axis-aligned edges)")

    area = 0.0
    for i in range(len(pts)):
        ax, ay = pts[i]
        bx, by = pts[(i + 1) % len(pts)]
        area += ax * by - bx * ay
    if abs(area) < 1e-9:
        raise ValueError("boundary polygon is degenerate (zero area)")
    return pts


def load_block(path: str):
    """Load one instance_info.json block -> ``(top_name, instances, boundary)``."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    top_name = str(data.get("top_name", ""))
    instances = data.get("instances", {})
    if not isinstance(instances, dict):
        raise ValueError(f"'instances' must be a dict in {path}")

    records = []
    for leaf_name, attrs in instances.items():
        row = {"leaf_instance_name": leaf_name}
        for spec in schema.INSTANCE_ATTRS:
            row[spec.name] = _apply_spec(attrs, spec)
        records.append(row)

    df = pd.DataFrame(records, columns=["leaf_instance_name"] + [s.name for s in schema.INSTANCE_ATTRS])
    _cast(df, schema.INSTANCE_ATTRS)
    boundary = _parse_boundary(data.get("boundary"))
    logger.info("Loaded block '%s' with %d instance(s) from %s", top_name, len(df), path)
    return top_name, df, boundary


def load_cell_info(path: str) -> pd.DataFrame:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    records = []
    for cell_name, attrs in data.items():
        row = {"cell_name": cell_name}
        for spec in schema.CELL_ATTRS:
            row[spec.name] = _apply_spec(attrs, spec)
        records.append(row)
    df = pd.DataFrame(records, columns=["cell_name"] + [s.name for s in schema.CELL_ATTRS])
    _cast(df, schema.CELL_ATTRS)
    logger.info("Loaded %d cell(s) from %s", len(df), path)
    return df
