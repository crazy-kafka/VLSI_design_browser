"""Hierarchy contour geometry: union outline of a set of axis-aligned boxes.

Uses shapely's ``unary_union`` (a hard dependency) to compute the exact
rectilinear union boundary, including holes and disconnected components. Boxes
are first collapsed into maximal rectangles (``merge_boxes``), which is exact
and turns a dense placement from O(N) into ~O(sqrt N) inputs.

Public API:

- ``contour_geometry(boxes, gap)`` -> (loops, area)
- ``contour_loops(boxes, gap)`` -> list of closed loops, each a list of (x, y)
- ``contour_area(boxes, gap)`` -> float (union area, exteriors minus holes)

``gap`` pads every box by ``gap/2`` before unioning, so instances closer than
``gap`` form a single merged loop (the hierarchy's spacing scope) while genuine
scatter stays as multiple loops. Use ``gap=0`` for the exact footprint.
"""
import logging

import numpy as np
from shapely.geometry import box as _sbox, MultiPolygon
from shapely.ops import unary_union as _unary_union

logger = logging.getLogger(__name__)
logger.info("contour backend: shapely")


class ContourAborted(Exception):
    """An ``abort_check`` reported the work stale mid-computation.

    Raised out of the union before any result is produced, so nothing caches or
    emits a partial answer. Callers (the contour worker) treat it as "drop silently".
    """


def _expanded(boxes, gap):
    """Each box padded by ``gap/2`` so within-gap instances merge into one loop.

    Returns a numpy (N, 4) array (no per-box tuples) so large inputs stay lean.
    """
    arr = np.asarray(boxes, dtype=float)
    if arr.size == 0:
        arr = arr.reshape(0, 4)
    elif arr.ndim == 1:
        arr = arr.reshape(1, 4)
    h = gap / 2.0
    return np.column_stack((arr[:, 0] - h, arr[:, 1] - h,
                            arr[:, 2] + h, arr[:, 3] + h))


def _merge_runs(a, key0, key1, start_col, hi_col):
    """Merge rows sharing ``(key0, key1)`` where ``start_col`` <= running ``hi_col`` max.

    One lexsort over the rows, then a Python loop over *groups* (≈ sqrt(N) distinct
    key pairs for a row-based placement, not N) with numpy inside each. This is the
    pandas ``groupby().cummax()/shift()/agg`` chain this module started with, at a
    fraction of the temporaries - measured ~3-5x faster per million boxes, and numpy
    releases the GIL on the large passes, which a GUI thread appreciates.
    """
    order = np.lexsort((a[:, start_col], a[:, key1], a[:, key0]))
    b = a[order]
    n = len(b)
    new_group = np.ones(n, dtype=bool)
    new_group[1:] = ((b[1:, key0] != b[:-1, key0])
                     | (b[1:, key1] != b[:-1, key1]))
    starts = np.flatnonzero(new_group)
    ends = np.r_[starts[1:], n]
    seg_start = np.ones(n, dtype=bool)
    for s, e in zip(starts, ends):
        run_max = np.maximum.accumulate(b[s:e, hi_col])
        # A group's first row always opens a segment (its "prev" is -inf).
        seg_start[s + 1:e] = b[s + 1:e, start_col] > run_max[:-1]
    seg = np.cumsum(seg_start)
    bounds = np.flatnonzero(np.r_[True, seg[1:] != seg[:-1]])
    out = b[bounds].copy()                    # group keys come from any row: the first
    out[:, start_col] = np.minimum.reduceat(b[:, start_col], bounds)
    out[:, hi_col] = np.maximum.reduceat(b[:, hi_col], bounds)
    return out


def merge_boxes(boxes):
    """Merge overlapping/abutting boxes into maximal rectangles.

    Collapses a dense placement (cells abutting in rows) from O(N) to ~O(sqrt N)
    rectangles without changing the union, so `unary_union` runs on far fewer
    inputs. Exact for features down to ~1e-9 (coordinates are rounded to 9
    decimals to absorb float noise; a real feature smaller than that would
    change the union's topology).

    Returns an ``(M, 4)`` float64 ndarray ``[x0, y0, x1, y1]``. The output is a
    decomposition of the same union, so merging it again (or in nested groups, as
    the hierarchy cache does) changes nothing.
    """
    arr = np.round(np.asarray(boxes, dtype=float), 9)
    if arr.size == 0:
        return np.empty((0, 4))
    if arr.ndim == 1:
        arr = arr.reshape(1, 4)
    # --- horizontal merge: within each (y0, y1) row, merge abutting x-runs ---
    strips = _merge_runs(arr, 1, 3, 0, 2)
    # --- vertical merge: within each (x0, x1) column, merge abutting y-runs ---
    return _merge_runs(strips, 0, 2, 1, 3)


def merged_boxes(boxes, gap):
    """``merge_boxes(_expanded(boxes, gap))``: the gap-padded, merged rectangle set."""
    return merge_boxes(_expanded(boxes, gap))


def _union(boxes, gap, abort_check=None):
    """Union geometry of ``boxes`` padded by ``gap/2`` (pre-merged).

    ``abort_check`` is consulted once between the merge and the union - the two
    expensive stages - and raises :class:`ContourAborted` when it reports the work
    has been superseded.
    """
    expanded = merged_boxes(boxes, gap)
    if abort_check is not None and abort_check():
        raise ContourAborted
    return _unary_union([_sbox(*b) for b in expanded])


def geom_loops_area(geom):
    """Extract closed loops + area from a shapely geometry (MultiPolygon ok)."""
    loops = []
    area = 0.0
    polys = list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]
    for poly in polys:
        if poly.is_empty:
            continue
        loops.append(list(poly.exterior.coords))
        for ring in poly.interiors:
            loops.append(list(ring.coords))
        area += poly.area
    return loops, area


def union_area(rects):
    """Exact union area of axis-aligned rectangles, via an x-sweep.

    For each slab between consecutive rectangle x-edges, the rectangles covering
    the slab are clipped to it (rectangle edges are slab boundaries, so coverage
    is all-or-nothing) and their y-intervals are merged; the area is the sum of
    slab width times covered y length. Exact for rectilinear unions, no shapely,
    and measured 60-100x cheaper than ``unary_union(...).area`` on pre-merged
    input (~1 ms for ~1-2k rectangles).
    """
    a = np.asarray(rects, dtype=np.float64)
    if a.size == 0:
        return 0.0
    xs = np.unique(a[:, [0, 2]])
    total = 0.0
    for i in range(len(xs) - 1):
        x0, x1 = xs[i], xs[i + 1]
        active = (a[:, 0] <= x0) & (a[:, 2] >= x1)
        if not active.any():
            continue
        y0s = a[active, 1]
        y1s = a[active, 3]
        order = np.argsort(y0s, kind="stable")
        y0s, y1s = y0s[order], y1s[order]
        run_max = np.maximum.accumulate(y1s)
        new = y0s > np.r_[-np.inf, run_max[:-1]]
        starts = np.flatnonzero(new)
        covered = (np.maximum.reduceat(y1s, starts) - y0s[starts]).sum()
        total += (x1 - x0) * float(covered)
    return total


def loops_from_merged(merged):
    """Closed outline loop(s) of a pre-merged rectangle set (``merge_boxes`` output)."""
    return geom_loops_area(_unary_union([_sbox(*b) for b in merged]))[0]


def contour_geometry(boxes, gap=0.0):
    """Return ``(loops, area)`` of the contour around ``boxes`` (one pass).

    ``loops`` is a list of closed ``[(x, y), ...]`` rings; ``area`` is the area
    enclosed by them.
    """
    return geom_loops_area(_union(boxes, gap))


def contour_loops(boxes, gap=0.0, abort_check=None):
    """Closed outline loop(s) around ``boxes``, bridging gaps < ``gap``.

    ``abort_check`` may raise :class:`ContourAborted` mid-computation; see
    :func:`_union`.
    """
    return geom_loops_area(_union(boxes, gap, abort_check))[0]


def contour_area(boxes, gap=0.0):
    """Area enclosed by the contour loop(s) around ``boxes`` (spacing scope).

    Only the union area is computed; loop coordinates are not extracted, so
    density lookups avoid materializing large coordinate lists. The area itself
    comes from the exact sweep (:func:`union_area`), not from shapely.
    """
    return union_area(merged_boxes(boxes, gap))
