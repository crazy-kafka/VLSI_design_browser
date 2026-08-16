"""Load ``instance_info.json`` and ``cell_info.json`` into typed DataFrames.

Missing attributes are filled with defaults and coerced to the declared type,
per the attribute schema in :mod:`vlsi_viewer.schema`.
"""
import json

import pandas as pd

from . import schema

_DTYPE = {"bool": "bool", "int": "int64", "float": "float64", "str": "object"}
_DEFAULT = {"bool": False, "int": 0, "float": 0.0, "str": ""}


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


def load_instance_info(path: str) -> pd.DataFrame:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    records = []
    for leaf_name, attrs in data.items():
        row = {"leaf_instance_name": leaf_name}
        for spec in schema.INSTANCE_ATTRS:
            row[spec.name] = _apply_spec(attrs, spec)
        records.append(row)
    df = pd.DataFrame(records, columns=["leaf_instance_name"] + [s.name for s in schema.INSTANCE_ATTRS])
    return _cast(df, schema.INSTANCE_ATTRS)


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
    return _cast(df, schema.CELL_ATTRS)
