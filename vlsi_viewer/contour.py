"""Hierarchy contour geometry: union outline of a set of axis-aligned boxes.

Two interchangeable backends, selected at import time:

- **shapely** (primary): ``unary_union`` computes the exact rectilinear union
  boundary, holes, and disconnected components.
- **scipy + manual** (fallback, used when shapely is not importable): clusters
  boxes with ``scipy.spatial.cKDTree`` and computes the rectilinear union
  boundary with a plane sweep implemented here.

Public API (identical contract for both backends):

- ``cluster_boxes(boxes, gap)`` -> list of clusters (each a list of boxes).
  Boxes whose edge-to-edge distance is ``< gap`` are connected.
- ``contour_loops(boxes, gap)`` -> list of closed loops, each a list of (x, y).
- ``contour_area(boxes, gap)`` -> float (union area, exteriors minus holes).
"""
import logging

import numpy as np

logger = logging.getLogger(__name__)

try:
    from shapely.geometry import box as _sbox, MultiPolygon, Polygon
    from shapely.ops import unary_union as _unary_union
    _BACKEND = "shapely"
except ImportError:  # pragma: no cover - exercised only when shapely is absent
    _BACKEND = "scipy"

logger.info("contour backend: %s%s", _BACKEND,
            "" if _BACKEND == "shapely" else " (scipy clustering + manual union)")


# ---------------------------------------------------------------------------
# Clustering (shared by both backends; scipy.cKDTree accelerates it)
# ---------------------------------------------------------------------------

def _expanded_overlap(a, b, gap):
    """True if the gap-expanded rectangles meet along a segment or region.

    Point-only contact (two corners touching) does NOT merge, matching shapely's
    union, which keeps point-touching polygons separate.
    """
    ax0, ay0, ax1, ay1 = a[0] - gap, a[1] - gap, a[2] + gap, a[3] + gap
    bx0, by0, bx1, by1 = b[0] - gap, b[1] - gap, b[2] + gap, b[3] + gap
    ox = min(ax1, bx1) - max(ax0, bx0)
    oy = min(ay1, by1) - max(ay0, by0)
    if ox < 0 or oy < 0:
        return False
    return ox > 0 or oy > 0  # intersection is a segment or a region


def cluster_boxes(boxes, gap):
    """Split boxes into clusters so boxes closer than ``gap`` share a cluster.

    Uses scipy.spatial.cKDTree over box centers with a per-box query radius to
    generate candidate neighbors, then keeps only pairs whose gap-expanded
    rectangles truly overlap (exact edge-to-edge test), unioned transitively.
    """
    boxes = list(boxes)
    n = len(boxes)
    if n == 0:
        return []
    arr = np.asarray(boxes, dtype=float)
    centers = np.column_stack(((arr[:, 0] + arr[:, 2]) / 2.0,
                               (arr[:, 1] + arr[:, 3]) / 2.0))
    diag = np.hypot(arr[:, 2] - arr[:, 0], arr[:, 3] - arr[:, 1])
    radius = gap + diag  # if expanded rects overlap, centers are within this

    try:
        from scipy.spatial import cKDTree
        from scipy.sparse import coo_matrix
        from scipy.sparse.csgraph import connected_components
        tree = cKDTree(centers)
        # Per-box radii are asymmetric: a small box may not reach a big box's
        # center, but the big box's query does reach the small box. Collect
        # candidate pairs from either side (no `j > i` guard) so proximity is
        # detected regardless of box size, then filter exactly (vectorized).
        ii, jj = [], []
        for i, nbrs in enumerate(tree.query_ball_point(centers, radius)):
            for j in nbrs:
                if j != i:
                    ii.append(i)
                    jj.append(j)
        pi = np.asarray(ii, dtype=np.intp)
        pj = np.asarray(jj, dtype=np.intp)
        minx = np.minimum(arr[pi, 2], arr[pj, 2])
        maxx = np.maximum(arr[pi, 0], arr[pj, 0])
        miny = np.minimum(arr[pi, 3], arr[pj, 3])
        maxy = np.maximum(arr[pi, 1], arr[pj, 1])
        ox = minx - maxx + 2 * gap
        oy = miny - maxy + 2 * gap
        ok = (ox >= 0) & (oy >= 0) & ((ox > 0) | (oy > 0))
        pi, pj = pi[ok], pj[ok]
        if len(pi) == 0:
            return [[b] for b in boxes]
        mat = coo_matrix((np.ones(len(pi)), (pi, pj)), shape=(n, n))
        _n_comp, labels = connected_components(mat, directed=False)
    except ImportError:  # pragma: no cover - scipy is a hard dependency
        parent = list(range(n))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for i in range(n):
            for j in range(i + 1, n):
                if _expanded_overlap(boxes[i], boxes[j], gap):
                    ri, rj = find(i), find(j)
                    if ri != rj:
                        parent[rj] = ri
        labels = np.asarray([find(i) for i in range(n)])

    groups = {}
    for i in range(n):
        groups.setdefault(int(labels[i]), []).append(boxes[i])
    return list(groups.values())


# ---------------------------------------------------------------------------
# Interval helpers (manual sweep)
# ---------------------------------------------------------------------------

def _merge_intervals(ivs):
    """Merge overlapping-or-touching intervals; returns sorted disjoint list."""
    ivs = sorted(ivs)
    out = []
    for a, b in ivs:
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _interval_len(ivs):
    return sum(b - a for a, b in ivs)


def _symdiff(left, right):
    """Symmetric difference of two merged interval lists, as interval pieces."""
    ev = {}
    for a, b in left:
        ev.setdefault(a, [0, 0])[0] += 1
        ev.setdefault(b, [0, 0])[0] -= 1
    for a, b in right:
        ev.setdefault(a, [0, 0])[1] += 1
        ev.setdefault(b, [0, 0])[1] -= 1
    ys = sorted(ev)
    il = ir = 0
    out = []
    seg_start = None
    for y in ys:
        il += ev[y][0]
        ir += ev[y][1]
        diff = il != ir          # coverage state on (y, next_y)
        if diff:
            if seg_start is None:
                seg_start = y
        elif seg_start is not None:
            out.append((seg_start, y))
            seg_start = None
    return out


# ---------------------------------------------------------------------------
# Manual rectilinear union (plane sweep) - the "manual union" fallback
# ---------------------------------------------------------------------------

def _manual_union(boxes):
    """Return (loops, area) of the rectilinear union of boxes (plane sweep)."""
    xs = sorted({b[0] for b in boxes} | {b[2] for b in boxes})
    by_x0 = {}
    by_x1 = {}
    for b in boxes:
        by_x0.setdefault(b[0], []).append(b)
        by_x1.setdefault(b[2], []).append(b)

    active = []
    verticals = []    # (x, y0, y1)
    horizontals = []  # (y, x0, x1)
    area = 0.0
    for idx, x in enumerate(xs):
        # coverage just LEFT of x: boxes with x0 < x <= x1 (active as-is)
        u_left = _merge_intervals([(b[1], b[3]) for b in active])
        # move to coverage just RIGHT of x: drop boxes ending at x, add starting
        active = [b for b in active if b[2] != x]
        active.extend(by_x0.get(x, ()))
        u_right = _merge_intervals([(b[1], b[3]) for b in active])

        for y0, y1 in _symdiff(u_left, u_right):
            verticals.append((x, y0, y1))

        if idx < len(xs) - 1:
            xn = xs[idx + 1]
            area += (xn - x) * _interval_len(u_right)
            for y0, y1 in u_right:
                horizontals.append((y1, x, xn))
                horizontals.append((y0, x, xn))

    loops = _stitch(verticals, horizontals)
    return loops, area


def _stitch(verticals, horizontals):
    """Join boundary segments into closed orthogonal loops.

    At every vertex the walk turns to the most counter-clockwise unused edge,
    which traces a connected region as a single loop even through a self-touch
    (pinch) point, matching shapely's union.
    """
    edges = []
    for x, y0, y1 in verticals:
        if y1 > y0:
            edges.append(((x, y0), (x, y1)))
    for y, x0, x1 in horizontals:
        if x1 > x0:
            edges.append(((x0, y), (x1, y)))

    adj = {}
    for i, (p0, p1) in enumerate(edges):
        adj.setdefault(p0, []).append(i)
        adj.setdefault(p1, []).append(i)

    used = set()
    loops = []
    for start in range(len(edges)):
        if start in used:
            continue
        pts = [edges[start][0]]
        cur = start
        cur_end = edges[start][1]
        used.add(cur)
        while True:
            nxt = _turn_edge(adj, edges, cur, cur_end, used)
            if nxt is None:
                break
            e0, e1 = edges[nxt]
            other = e0 if e1 == cur_end else e1
            pts.append(cur_end)
            cur = nxt
            cur_end = other
            used.add(cur)
            if cur_end == pts[0]:
                break
        if len(pts) >= 4:
            loops.append(pts)
    return loops


def _turn_edge(adj, edges, cur, at_pt, used):
    """Pick the unused edge at ``at_pt`` that makes the leftmost turn."""
    prev_pt = edges[cur][0] if edges[cur][1] == at_pt else edges[cur][1]
    dx_in = at_pt[0] - prev_pt[0]
    dy_in = at_pt[1] - prev_pt[1]
    best = None
    best_key = None
    for j in adj.get(at_pt, ()):
        if j == cur or j in used:
            continue
        e0, e1 = edges[j]
        other = e0 if e1 == at_pt else e1
        dx_out = other[0] - at_pt[0]
        dy_out = other[1] - at_pt[1]
        cross = dx_in * dy_out - dy_in * dx_out   # >0 = left turn
        dot = dx_in * dx_out + dy_in * dy_out
        # leftmost turn first (largest cross), then straight, then right
        key = (-cross, dot)
        if best_key is None or key < best_key:
            best_key = key
            best = j
    return best


def _manual_contour(boxes, gap):
    loops = []
    area = 0.0
    for cluster in cluster_boxes(boxes, gap):
        # Re-split each gap-merged cluster into edge-connected pieces so that
        # boxes touching only at a corner become separate loops (like shapely).
        for sub in cluster_boxes(cluster, 0.0):
            cl, ca = _manual_union(sub)
            loops.extend(cl)
            area += ca
    return loops, area


# ---------------------------------------------------------------------------
# shapely backend
# ---------------------------------------------------------------------------

def geom_loops_area(geom):
    """Extract closed loops + area from a shapely geometry (MultiPolygon ok)."""
    loops = []
    area = 0.0
    polys = list(geom.geoms) if getattr(geom, "geom_type", "") == "MultiPolygon" else [geom]
    for poly in polys:
        if getattr(poly, "is_empty", False):
            continue
        loops.append(list(poly.exterior.coords))
        for ring in poly.interiors:
            loops.append(list(ring.coords))
        area += poly.area
    return loops, area


def _shapely_contour(boxes, gap):
    # ``boxes`` are already gap-expanded; ``unary_union`` alone yields disjoint
    # scatter groups (MultiPolygon) and holes, so no explicit clustering is
    # needed here.
    geom = _unary_union([_sbox(*b) for b in boxes])
    return geom_loops_area(geom)


def union_geometry(boxes, gap=0.0):
    """Return a reusable shapely union geometry for ``boxes`` (shapely only).

    Boxes are pre-merged (exact) so the union runs on far fewer inputs.
    Raises ``NotImplementedError`` on the manual backend, where reuse is not
    supported.
    """
    if _BACKEND != "shapely":
        raise NotImplementedError("union_geometry requires the shapely backend")
    return _unary_union([_sbox(*b) for b in merge_boxes(_expanded(boxes, gap))])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _expanded(boxes, gap):
    """Each box padded by ``gap/2`` so within-gap instances merge into one loop.

    Returns a numpy (N, 4) array (no per-box tuples) so large inputs stay lean.
    """
    h = gap / 2.0
    arr = np.asarray(boxes, dtype=float)
    return np.column_stack((arr[:, 0] - h, arr[:, 1] - h,
                            arr[:, 2] + h, arr[:, 3] + h))


def merge_boxes(boxes):
    """Exact maximal-rectangle merge of overlapping/abutting boxes.

    Collapses a dense placement (cells abutting in rows) from O(N) to ~O(sqrt N)
    rectangles without changing the union, so `unary_union` runs on far fewer
    inputs. Exact: merging overlap/abut preserves the union bit-for-bit.
    """
    import pandas as pd
    arr = np.round(np.asarray(boxes, dtype=float), 6)
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


def contour_geometry(boxes, gap=0.0):
    """Return ``(loops, area)`` of the contour around ``boxes`` (one pass).

    ``loops`` is a list of closed ``[(x, y), ...]`` rings; ``area`` is the area
    enclosed by them. Boxes are padded by ``gap/2`` before unioning, so
    instances closer than ``gap`` form a single merged loop (the hierarchy's
    spacing scope) while genuinely separate scatter stays as multiple loops.
    """
    expanded = merge_boxes(_expanded(boxes, gap))
    if _BACKEND == "shapely":
        return _shapely_contour(expanded, 0.0)
    return _manual_contour(expanded, 0.0)


def contour_loops(boxes, gap=0.0):
    """Closed outline loop(s) around ``boxes``, bridging gaps < ``gap``."""
    return contour_geometry(boxes, gap)[0]


def contour_area(boxes, gap=0.0):
    """Area enclosed by the contour loop(s) around ``boxes`` (spacing scope)."""
    return contour_geometry(boxes, gap)[1]
