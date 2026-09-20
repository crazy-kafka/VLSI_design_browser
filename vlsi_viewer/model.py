"""Column/view abstractions bridging :class:`DesignData` to the Qt tree widgets."""
import fnmatch
import logging
import re
import time
from dataclasses import dataclass
from typing import Callable, List

import numpy as np
import pandas as pd
from PyQt5.QtCore import QObject, QRunnable, QThread, QThreadPool, pyqtSignal

from . import schema
from .metrics import diff_table

logger = logging.getLogger(__name__)

# Interaction throttle for progressive background work. ``note_interaction`` is called
# from GUI event handlers (zoom/pan/fit); density jobs wait for a quiet beat before
# computing so a paint tick never competes with a pandas/GEOS call for the GIL. A plain
# module attribute: there is one GUI thread writing it and workers only read it.
_INTERACT_UNTIL = 0.0
INTERACT_HOLD_S = 0.25


def note_interaction(hold_s: float = INTERACT_HOLD_S) -> None:
    """Record user interaction; background density waits ``hold_s`` past the last one."""
    global _INTERACT_UNTIL
    _INTERACT_UNTIL = time.perf_counter() + hold_s


def _wait_for_idle() -> None:
    """Block a worker thread until interaction has been quiet for ``INTERACT_HOLD_S``."""
    while True:
        remaining = _INTERACT_UNTIL - time.perf_counter()
        if remaining <= 0:
            return
        time.sleep(min(0.05, remaining))


@dataclass
class Column:
    """One display column: label, per-path values, formatter, optional bar ratios."""
    label: str
    series: pd.Series              # indexed by hierarchy path
    fmt: Callable[[object], str]
    bar: pd.Series = None          # indexed by path; 0..1 background bar fraction
    is_macro: bool = False         # true for macro count/area columns (amber bars)
    gradient: str = None           # None | "lower_better" | "higher_better"
    key: str = None                # metric key (for gradient range lookup)


def bar_series(values: pd.Series, roots, kind: str) -> pd.Series:
    """0..1 background-bar fraction for a metric column.

    percent metrics use their own value; count/area metrics use
    value / top-level total (summed over roots).
    """
    if kind == "percent":
        return values.clip(0.0, 1.0)
    total = float(values.reindex(roots).sum(skipna=True))
    if not total or pd.isna(total):
        return pd.Series(float("nan"), index=values.index)
    with np.errstate(divide="ignore", invalid="ignore"):
        return (values / total).clip(0.0, 1.0)


def metric_columns(design, include_macros: bool = False) -> List[Column]:
    mv = design.metric_values(include_macros)
    metrics = schema.METRICS if include_macros else schema.STD_METRICS
    cols = []
    for m in metrics:
        fmt = (lambda v, k=m.kind: schema.format_metric(k, v))
        bar = None if m.gradient else bar_series(mv[m.key], design.roots, m.kind)
        cols.append(Column(m.label, mv[m.key], fmt, bar=bar, is_macro=m.is_macro,
                           gradient=m.gradient, key=m.key))
    return cols


def diff_columns(d1, d2, include_macros: bool = False) -> List[Column]:
    metrics = schema.METRICS if include_macros else schema.STD_METRICS
    dt = diff_table(d1, d2, include_macros)
    cols = []
    for m in metrics:
        fmt_abs = (lambda v, k=m.kind: schema.format_delta_abs(k, v))
        fmt_rel = (lambda v: schema.format_delta_rel(v))
        # Δabs for percent metrics is in percentage points -> drop the "%";
        # Δrel keeps it ("ΔULVT" vs "ΔULVT%"), and count/area get "ΔArea"/"ΔArea%".
        base = m.label[:-1] if m.kind == "percent" else m.label
        rel_label = "Δ" + m.label if m.kind == "percent" else "Δ" + m.label + "%"
        cols.append(Column("Δ" + base, dt[f"{m.key}_abs"], fmt_abs))
        gradient = m.gradient or "lower_better"
        cols.append(Column(rel_label, dt[f"{m.key}_rel"], fmt_rel,
                           gradient=gradient, key=m.key + "_rel"))
    return cols


@dataclass
class TreeView:
    """Everything a :class:`HierarchyTree` needs to render one dataset."""
    roots: List[str]
    children: dict          # parent path -> sorted child paths
    counts: pd.Series       # path -> instance count (threshold filtering)
    columns: List[Column]
    paths: List[str]        # all hierarchy paths (for search)


def _bounded_threads():
    """One density thread.

    With the build-time merged-rectangle cache a density job is a sweep over a
    small rectangle set (~ms), so extra threads only add GIL contention with the
    GUI. (It used to be ``min(cpus // 2, 4)``, back when a job re-unioned a whole
    subtree and throughput mattered more than smoothness.)
    """
    return 1


class _DensityJob(QRunnable):
    """Compute one hierarchy's density off the GUI thread, then deliver it."""

    def __init__(self, physical, path, owner):
        super().__init__()
        self._physical = physical
        self._path = path
        self._owner = owner

    def run(self):
        # Below-normal priority: the GUI thread wins scheduling while this computes.
        QThread.currentThread().setPriority(QThread.LowPriority)
        # Density is progressive (nice-to-have); never let it fight a paint tick.
        _wait_for_idle()
        try:
            value = self._physical.density_for(self._path)
        except Exception:  # a bad path must not kill the thread pool
            value = float("nan")
        # Emitting from a worker thread is auto-queued to the main thread.
        self._owner.ready.emit(self._path, value)


class _LazyDensity(QObject):
    """Series-like mapping that computes density on a bounded background pool.

    ``get(path)`` returns the cached value, or ``default`` while the computation
    is in flight and emits ``ready(path, value)`` on the main thread when done.
    The pool is a single low-priority thread that waits out active GUI
    interaction: per-job cost is ~ms off the merged-rectangle cache, so one
    thread is both fast enough and the smoothest option. ``status`` reports the
    number of pending jobs.
    """

    ready = pyqtSignal(str, float)
    status = pyqtSignal(int)  # number of density jobs pending (0 = idle)

    def __init__(self, physical):
        super().__init__()
        self._physical = physical
        self._cache = {}
        self._pending = set()
        self._pool = QThreadPool()
        self._pool.setMaxThreadCount(_bounded_threads())
        self.ready.connect(self._record)

    def get(self, path, default=None):
        if path in self._cache:
            return self._cache[path]
        if path not in self._pending:
            self._pending.add(path)
            self.status.emit(len(self._pending))
            self._pool.start(_DensityJob(self._physical, path, self))
        return default

    def _record(self, path, value):
        self._cache[path] = value
        self._pending.discard(path)
        self.status.emit(len(self._pending))


class _ContourJob(QRunnable):
    """Compute one hierarchy's contour loops off the GUI thread."""

    def __init__(self, physical, path, token, owner):
        super().__init__()
        self._physical = physical
        self._path = path
        self._token = token
        self._owner = owner

    def run(self):
        QThread.currentThread().setPriority(QThread.LowPriority)
        # Single-threaded FIFO: a superseded request must not delay the fresh one,
        # so staleness is checked *before* paying for the computation, not only at
        # delivery, and again between the merge and the union (abort_check).
        if self._owner.is_stale(self._token):
            return
        from .contour import ContourAborted
        try:
            loops = self._physical.contour_for(
                self._path, abort_check=lambda: self._owner.is_stale(self._token))
        except ContourAborted:      # superseded mid-computation; deliver nothing
            return
        except Exception:  # a bad path must not break the pool
            loops = []
        self._owner.contour_ready.emit(self._path, self._token, loops)


class ContourWorker(QObject):
    """Owns a single-threaded pool so the selected contour beats density work.

    ``request(path, token)`` queues an exact-contour computation; results arrive
    on ``contour_ready(path, token, loops)``. A caller-supplied token lets the
    receiver ignore stale results after a newer selection, and the worker drops a
    stale job before (and midway through) its computation rather than only at
    delivery.
    """

    contour_ready = pyqtSignal(str, int, object)

    def __init__(self):
        super().__init__()
        self._pool = QThreadPool()
        self._pool.setMaxThreadCount(1)  # one exact contour at a time (priority)
        self._latest_token = 0

    def request(self, physical, path, token):
        self._latest_token = max(self._latest_token, token)
        self._pool.start(_ContourJob(physical, path, token, self))

    def is_stale(self, token) -> bool:
        """Whether a newer request has superseded ``token``."""
        return token != self._latest_token


def density_column(physical) -> Column:
    """Physical-only "Density%" column (higher-better, gradient range 20%-65%).

    Values are computed on a background thread per rendered hierarchy node (see
    _LazyDensity) so startup and expansions never block the GUI.
    """
    return Column(label="Density%", series=_LazyDensity(physical),
                  fmt=lambda v: schema.format_metric("percent", v),
                  gradient="higher_better", key="density")


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
