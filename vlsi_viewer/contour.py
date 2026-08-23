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


def merge_boxes(boxes):
    """Merge overlapping/abutting boxes into maximal rectangles.

    Collapses a dense placement (cells abutting in rows) from O(N) to ~O(sqrt N)
    rectangles without changing the union, so `unary_union` runs on far fewer
    inputs. Exact for features down to ~1e-9 (coordinates are rounded to 9
    decimals to absorb float noise; a real feature smaller than that would
    change the union's topology).
    """
    import pandas as pd
    arr = np.round(np.asarray(boxes, dtype=float), 9)
    if arr.size == 0:
        return []
    df = pd.DataFrame(arr, columns=["x0", "y0", "x1", "y1"])

    def _merge_runs(frame, by, start_col, hi):
        """Merge rows sharing ``by`` where ``start_col`` <= running ``hi``."""
        frame = frame.sort_values(by + [start_col])
        grp = frame.groupby(by, sort=False)
        frame["run_max"] = grp[hi].cummax()
        frame["prev_max"] = grp["run_max"].shift(1).fillna(-np.inf)
        frame["seg"] = np.cumsum(frame[start_col].values > frame["prev_max"].values)
        out = frame.groupby(by + ["seg"], sort=False).agg(
            **{start_col: (start_col, "min"), hi: (hi, "max")}).reset_index()
        return out

    # --- horizontal merge: within each (y0, y1) row, merge abutting x-runs ---
    strips = _merge_runs(df, ["y0", "y1"], "x0", "x1")
    # --- vertical merge: within each (x0, x1) column, merge abutting y-runs ---
    merged = _merge_runs(strips, ["x0", "x1"], "y0", "y1")

    return list(merged[["x0", "y0", "x1", "y1"]].itertuples(index=False, name=None))


def _union(boxes, gap):
    """Union geometry of ``boxes`` padded by ``gap/2`` (pre-merged)."""
    expanded = merge_boxes(_expanded(boxes, gap))
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


def contour_loops(boxes, gap=0.0):
    """Closed outline loop(s) around ``boxes``, bridging gaps < ``gap``."""
    return geom_loops_area(_union(boxes, gap))[0]


def contour_area(boxes, gap=0.0):
    """Area enclosed by the contour loop(s) around ``boxes`` (spacing scope).

    Only the union area is computed; loop coordinates are not extracted, so
    density lookups avoid materializing large coordinate lists.
    """
    return _union(boxes, gap).area
