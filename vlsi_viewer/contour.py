"""Hierarchy contour geometry: union outline of a set of axis-aligned boxes.

Uses shapely's ``unary_union`` (a hard dependency) to compute the exact
rectilinear union boundary, including holes and disconnected components. Boxes
are first collapsed into maximal rectangles (``merge_rects``), which is exact
and turns a dense placement from O(N) into ~O(sqrt N) inputs.

Public API:

- ``merge_rects(boxes, gap)`` -> (M, 4) merged rectangles
- ``rect_union_area(rects)`` -> exact union area (sweep line)
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


def _segmented_cummax(values, group_starts):
    """Per-group prefix maximum (the start of each group resets the maximum)."""
    out = np.empty_like(values)
    ends = np.r_[group_starts[1:], len(values)]
    for start, end in zip(group_starts, ends):
        out[start:end] = np.maximum.accumulate(values[start:end])
    return out


def _merge_bands(arr, band0, band1, start, hi):
    """One band merge pass over columns ``[x0, y0, x1, y1]``.

    Rows sharing ``(band0, band1)`` are sorted by ``start`` and merged while
    ``start <= running max(hi)``; the run is replaced by its bounding interval.
    The returned rows keep all four columns, with the run's start/hi extent
    replaced by the run's min/max. Exact analogue of the old pandas pass.
    """
    order = np.lexsort((arr[:, start], arr[:, band1], arr[:, band0]))
    a = arr[order]
    change = np.r_[True,
                   (a[1:, band0] != a[:-1, band0]) | (a[1:, band1] != a[:-1, band1])]
    starts = np.flatnonzero(change)
    run_max = _segmented_cummax(a[:, hi], starts)
    prev = np.empty(len(a), dtype=float)
    prev[0] = -np.inf
    prev[1:] = run_max[:-1]
    prev[starts] = -np.inf                 # a new band starts a new run
    seg_starts = np.flatnonzero(a[:, start] > prev)

    out = a[seg_starts].copy()
    out[:, start] = np.minimum.reduceat(a[:, start], seg_starts)
    out[:, hi] = np.maximum.reduceat(a[:, hi], seg_starts)
    return out


def merge_rects(boxes, gap=0.0):
    """Merge overlapping/abutting boxes into maximal rectangles.

    A dense placement collapses from O(N) to ~O(sqrt N) rectangles without
    changing the union. Expansion by ``gap/2``, rounding to 9 decimals and both
    run-merge passes are fused; the result is an ``(M, 4)`` float64 array of
    ``x0, y0, x1, y1``. Exact for features down to ~1e-9 (coordinates are
    rounded to absorb float noise; a real feature smaller than that would change
    the union's topology). Input boxes must satisfy ``x0 <= x1`` and ``y0 <= y1``.
    """
    arr = np.array(boxes, dtype=float, copy=True)
    if arr.size == 0:
        return np.empty((0, 4))
    if arr.ndim == 1:
        arr = arr.reshape(1, 4)

    if gap:
        h = gap / 2.0
        arr[:, 0] -= h
        arr[:, 1] -= h
        arr[:, 2] += h
        arr[:, 3] += h
    np.round(arr, 9, out=arr)

    # horizontal merge on (y0, y1) strips, then vertical on (x0, x1) strips
    strips = _merge_bands(arr, 1, 3, 0, 2)
    return _merge_bands(strips, 0, 2, 1, 3)


def merge_boxes(boxes):
    """Compatibility wrapper: merge without gap padding (returns an ndarray)."""
    return merge_rects(boxes, 0.0)


def rect_union_area(rects):
    """Exact union area of axis-aligned rectangles.

    A sweep over distinct x coordinates: within one slab no rectangle starts or
    ends, so the union is ``slab_width * covered_y_length``. A segment tree over
    compressed y coordinates maintains the covered length from cover counts.
    Zero-area and non-finite rectangles are ignored; the result is the same
    union area shapely computes, without constructing polygons.
    """
    arr = np.asarray(rects, dtype=float)
    if arr.size == 0:
        return 0.0
    if arr.ndim == 1:
        arr = arr.reshape(1, 4)
    keep = (np.isfinite(arr).all(axis=1)
            & (arr[:, 2] > arr[:, 0]) & (arr[:, 3] > arr[:, 1]))
    arr = arr[keep]
    if len(arr) == 0:
        return 0.0

    ys = np.unique(np.concatenate((arr[:, 1], arr[:, 3])))
    if len(ys) < 2:
        return 0.0
    ylo = np.searchsorted(ys, arr[:, 1]).astype(np.intp)
    yhi = np.searchsorted(ys, arr[:, 3]).astype(np.intp)

    x = np.concatenate((arr[:, 0], arr[:, 2]))
    delta = np.concatenate((np.ones(len(arr), dtype=np.int32),
                            -np.ones(len(arr), dtype=np.int32)))
    lo = np.concatenate((ylo, ylo))
    hi = np.concatenate((yhi, yhi))
    order = np.argsort(x, kind="mergesort")
    x, delta, lo, hi = x[order], delta[order], lo[order], hi[order]

    y_intervals = len(ys) - 1
    cover = np.zeros(4 * y_intervals + 4, dtype=np.int32)
    covered = np.zeros(4 * y_intervals + 4, dtype=np.float64)

    def update(node, left, right, qlo, qhi, change):
        if qlo <= left and right <= qhi:
            cover[node] += change
        else:
            mid = (left + right) // 2
            if qlo < mid:
                update(node * 2, left, mid, qlo, qhi, change)
            if qhi > mid:
                update(node * 2 + 1, mid, right, qlo, qhi, change)
        if cover[node] > 0:
            covered[node] = ys[right] - ys[left]
        elif right - left == 1:
            covered[node] = 0.0
        else:
            covered[node] = covered[node * 2] + covered[node * 2 + 1]

    unique_x, starts = np.unique(x, return_index=True)
    area = 0.0
    for k in range(len(unique_x) - 1):
        for j in range(int(starts[k]), int(starts[k + 1])):
            update(1, 0, y_intervals, int(lo[j]), int(hi[j]), int(delta[j]))
        area += covered[1] * (unique_x[k + 1] - unique_x[k])
    return float(area)


def _union(boxes, gap):
    """Union geometry of ``boxes`` padded by ``gap/2`` (pre-merged)."""
    expanded = merge_rects(boxes, gap)
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


def contour_geometry(boxes, gap=0.0):
    """Return ``(loops, area)`` of the contour around ``boxes`` (one pass).

    ``loops`` is a list of closed ``[(x, y), ...]`` rings; ``area`` is the area
    enclosed by them.
    """
    return geom_loops_area(_union(boxes, gap))


def loops_from_rects(rects):
    """Closed outline loop(s) from already-expanded merged rectangles."""
    return geom_loops_area(_unary_union([_sbox(*b) for b in rects]))[0]


def contour_loops(boxes, gap=0.0):
    """Closed outline loop(s) around ``boxes``, bridging gaps < ``gap``."""
    return loops_from_rects(merge_rects(boxes, gap))


def contour_area(boxes, gap=0.0):
    """Area enclosed by the contour loop(s) around ``boxes`` (spacing scope).

    Only the union area is computed; loop coordinates are not extracted. This
    uses the exact sweep-line area rather than constructing shapely polygons,
    so density lookups avoid both polygon union and large coordinate lists.
    """
    return rect_union_area(merge_rects(boxes, gap))
