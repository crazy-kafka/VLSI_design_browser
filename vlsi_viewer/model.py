"""Column/view abstractions bridging :class:`DesignData` to the Qt tree widgets."""
import fnmatch
import re
from dataclasses import dataclass
from typing import Callable, List

import pandas as pd

from . import schema
from .metrics import diff_table


@dataclass
class Column:
    """One display column: a label, a per-path value series, and a formatter."""
    label: str
    series: pd.Series              # indexed by hierarchy path
    fmt: Callable[[object], str]


def metric_columns(design, include_macros: bool = False) -> List[Column]:
    mv = design.metric_values(include_macros)
    metrics = schema.METRICS if include_macros else schema.STD_METRICS
    cols = []
    for m in metrics:
        fmt = (lambda v, k=m.kind: schema.format_metric(k, v))
        cols.append(Column(m.label, mv[m.key], fmt))
    return cols


def diff_columns(d1, d2, include_macros: bool = False) -> List[Column]:
    metrics = schema.METRICS if include_macros else schema.STD_METRICS
    dt = diff_table(d1, d2, include_macros)
    cols = []
    for m in metrics:
        fmt_abs = (lambda v, k=m.kind: schema.format_delta_abs(k, v))
        fmt_rel = (lambda v: schema.format_delta_rel(v))
        cols.append(Column("Δ" + m.label, dt[f"{m.key}_abs"], fmt_abs))
        cols.append(Column("Δ" + m.label + "%", dt[f"{m.key}_rel"], fmt_rel))
    return cols


@dataclass
class TreeView:
    """Everything a :class:`HierarchyTree` needs to render one dataset."""
    roots: List[str]
    children: dict          # parent path -> sorted child paths
    counts: pd.Series       # path -> instance count (threshold filtering)
    columns: List[Column]
    paths: List[str]        # all hierarchy paths (for search)


def view_for_single(design, include_macros: bool = False) -> TreeView:
    return TreeView(
        roots=design.roots,
        children=design.children,
        counts=design.hier["count"],
        columns=metric_columns(design, include_macros),
        paths=list(design.hier.index),
    )


def view_for_diff(d1, d2, include_macros: bool = False) -> TreeView:
    return TreeView(
        roots=d1.roots,
        children=d1.children,
        counts=d1.hier["count"],
        columns=diff_columns(d1, d2, include_macros),
        paths=list(d1.hier.index),
    )


def match_paths(paths, pattern: str, mode: str) -> List[str]:
    """Match hierarchy paths by exact / wildcard / regex (case-insensitive)."""
    if not pattern:
        return []
    if mode == "exact":
        pl = pattern.lower()
        return [p for p in paths if p.lower() == pl]
    if mode == "wildcard":
        pl = pattern.lower()
        return [p for p in paths if fnmatch.fnmatch(p.lower(), pl)]
    if mode == "regex":
        try:
            rx = re.compile(pattern, re.IGNORECASE)
        except re.error:
            return []
        return [p for p in paths if rx.search(p)]
    return []
