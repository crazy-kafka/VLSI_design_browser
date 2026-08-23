"""Physical mode: build the 2-D heat-map grids (density / leakage / dynamic power).

Placement + orientation follow DEF semantics: each instance's ``location_x/y`` is
the lower-left corner of its (possibly rotated) bounding box, and ``orient`` is one
of N/S/W/E/FN/FS/FW/FE. Nested sub-block instances are composed through their
placement frame using :mod:`vlsi_viewer.coordinateProcess`.
"""
import logging
import threading
import time

import numpy as np

from . import config, schema
from .coordinateProcess import CoordinateProcess, Orient
from .loader import load_block, load_cell_info

logger = logging.getLogger(__name__)


class PhysicalData:
    """Precomputed grids + geometry for one physical layout view.

    Leaf geometry is stored as compact numpy arrays sorted by hierarchy path, so
    a 10M-instance design stays in tens of MB instead of a list of Python tuples.
    Per-hierarchy access is a slice into the arrays (``_slice_for``), computed
    lazily; nothing is duplicated per ancestor path.
    """

    def __init__(self, top_name, boundary_polys, grid_size,
                 extent, rows, cols, density, leakage, dynamic, ulvt,
                 geom, is_ulvt, is_macro, leak, dyn, leaf_paths, contour_gap):
        self.top_name = top_name
        self.boundary_polys = boundary_polys   # list of (name, [(x, y), ...]) in global coords
        self.grid_size = grid_size
        self.extent = extent                   # (x0, y0, x1, y1) grid bounds
        self.rows = rows
        self.cols = cols
        self.density = density                 # (rows, cols)
        self.leakage = leakage                 # (rows, cols)
        self.dynamic = dynamic                 # (rows, cols)
        self.ulvt = ulvt                       # (rows, cols) ULVT-cell density
        self._geom = geom                      # (N, 4) float32 [x0,y0,x1,y1], sorted by path
        self._is_ulvt = is_ulvt                # (N,) bool
        self._is_macro = is_macro              # (N,) bool
        self._leak = leak                      # (N,) float32
        self._dyn = dyn                        # (N,) float32
        self._leaf_paths = leaf_paths          # (N,) object array, sorted lexicographically
        self.contour_gap = contour_gap
        self._contour_cache = {}               # (path, gap) -> (loops, area)
        self._contour_lock = threading.Lock()

    @property
    def boxes(self):
        """Legacy accessor: reconstruct per-box tuples (for tests/consumers)."""
        n = len(self._geom)
        return [(float(self._geom[i, 0]), float(self._geom[i, 1]),
                 float(self._geom[i, 2]), float(self._geom[i, 3]),
                 float(self._leak[i]), float(self._dyn[i]),
                 bool(self._is_ulvt[i]), str(self._leaf_paths[i]),
                 bool(self._is_macro[i])) for i in range(n)]

    def heat(self, kind: str) -> np.ndarray:
        return {"density": self.density, "leakage": self.leakage,
                "dynamic": self.dynamic, "ulvt": self.ulvt}[kind]

    def _slice_for(self, path: str):
        """Slice of the sorted arrays covering ``path`` and its descendants."""
        # The upper bound includes the path separator so a sibling whose name
        # merely extends the queried path (TOP/cpu vs TOP/cpu_aux) is excluded.
        left = int(np.searchsorted(self._leaf_paths, path, side="left"))
        right = int(np.searchsorted(self._leaf_paths, path + "/￿", side="left"))
        return slice(left, right)

    def boxes_for(self, path: str):
        """(k, 4) float32 box array for ``path`` and its descendants."""
        return self._geom[self._slice_for(path)]

    def _contour(self, path: str, gap: float):
        """Cached contour loops for a path at a gap (thread-safe)."""
        from . import contour
        key = ("loops", path, gap)
        with self._contour_lock:
            cached = self._contour_cache.get(key)
            if cached is not None:
                return cached
        boxes = self._geom[self._slice_for(path)]
        t0 = time.perf_counter()
        loops = contour.contour_loops(boxes, gap)
        with self._contour_lock:
            self._contour_cache[key] = loops
        logger.info("contour: %s (gap %g, %d boxes) -> %d loop(s) (%.1fs)",
                    path, gap, len(boxes), len(loops), time.perf_counter() - t0)
        return loops

    def _contour_area(self, path: str, gap: float) -> float:
        """Cached contour area for a path at a gap (thread-safe)."""
        from . import contour
        key = ("area", path, gap)
        with self._contour_lock:
            cached = self._contour_cache.get(key)
            if cached is not None:
                return cached
        boxes = self._geom[self._slice_for(path)]
        t0 = time.perf_counter()
        area = contour.contour_area(boxes, gap)
        with self._contour_lock:
            self._contour_cache[key] = area
        logger.info("contour area: %s (gap %g, %d boxes) -> %.0f (%.1fs)",
                    path, gap, len(boxes), area, time.perf_counter() - t0)
        return area

    def contour_for(self, path: str):
        """Closed contour loops for a hierarchy path (cached)."""
        return self._contour(path, self.contour_gap)

    def density_for(self, path: str) -> float:
        """Hierarchy density = non_macro_area / (contour_area - macro_area).

        ``contour_area`` is the gap-padded spacing scope (``self.contour_gap``),
        so a hierarchy's internal spacing lowers its density. Returns NaN when
        undefined (no non-macro area or denominator <= 0).
        """
        area = self._contour_area(path, self.contour_gap)
        sl = self._slice_for(path)
        box_area = (self._geom[sl, 2] - self._geom[sl, 0]) * (self._geom[sl, 3] - self._geom[sl, 1])
        mac = float(box_area[self._is_macro[sl]].sum())
        non = float(box_area[~self._is_macro[sl]].sum())
        den = area - mac
        if not (den > 0 and non > 0):
            return float("nan")
        return min(1.0, non / den)


def _oriented_extent(orient: str, w: float, h: float):
    """Axis-aligned (width, height) of a cell given its orientation."""
    r = Orient.orient_map[orient]["R"]
    return (w, h) if (r // 90) % 2 == 0 else (h, w)


def _load_blocks_and_cells(block_paths, cell_path):
    blocks = {}
    for p in block_paths:
        name, df, boundary = load_block(p)
        if name in blocks:
            prev_df, prev_b = blocks[name]
            from .metrics import _merge_blocks
            df = _merge_blocks(prev_df, df)
            boundary = prev_b if prev_b is not None else boundary
        blocks[name] = (df, boundary)
    cells = load_cell_info(cell_path).set_index("cell_name")
    return blocks, cells


def build_physical(block_paths, cell_path, grid_size: float = 3.0,
                   contour_gap: float = None) -> PhysicalData:
    """Build heat-map grids for a single-top-block design.

    ``contour_gap`` is the proximity threshold (in physical units) for merging a
    hierarchy's instances into one contour loop; defaults to
    ``config.DEFAULT_CONTOUR_GAP_FACTOR * grid_size`` and must be >= 0.

    Raises ``ValueError`` if there is not exactly one top-level block, if the top
    block has no ``boundary``, if a boundary is not rectilinear, or if the grid
    size / contour gap are invalid.
    """
    if grid_size <= 0:
        raise ValueError("grid size must be > 0")
    if contour_gap is None:
        contour_gap = config.DEFAULT_CONTOUR_GAP_FACTOR * grid_size
    if contour_gap < 0:
        raise ValueError("contour gap must be >= 0")
    blocks, cells = _load_blocks_and_cells(block_paths, cell_path)

    referenced = set()
    for df, _ in blocks.values():
        referenced.update(df["cell_name"].dropna().astype(str).unique())
    tops = [n for n in blocks if n not in referenced]
    if len(tops) != 1:
        raise ValueError(
            f"physical mode requires exactly one top-level block; found {len(tops)}"
            + (f": {', '.join(sorted(tops))}" if tops else " (none)"))

    top = tops[0]
    top_boundary = blocks[top][1]
    if top_boundary is None:
        raise ValueError("physical mode requires a 'boundary' on the top-level block")

    sizes = {name: (row["size_x"], row["size_y"])
             for name, row in cells.iterrows()}
    is_ulvt = {name: bool(row["is_ULVT"]) for name, row in cells.iterrows()}
    is_macro = {name: bool(row["is_macro"]) for name, row in cells.iterrows()}

    chain = []        # outermost-first list of (orient, origin) container frames
    boundary_polys = []
    _xs0, _ys0, _xs1, _ys1 = [], [], [], []
    _leaks, _dyns, _ulvts, _macros, _paths = [], [], [], [], []

    def _join(prefix, rel):
        return f"{prefix}/{rel}" if prefix else rel

    def global_pt(pt):
        # A leaf's point is in its innermost block's local frame; compose the
        # container frames innermost-first (reverse push order) to reach global.
        x, y = pt
        for orient, origin in reversed(chain):
            x, y = CoordinateProcess.dbTransform("to_global", (x, y), orient, origin)
        return x, y

    # Fast path: when every ancestor frame is orient N (pure translation), a
    # leaf's global box is just its local box translated by the accumulated
    # origins — no per-leaf transform or 4-corner min/max needed.
    tx, ty = 0.0, 0.0
    trans_only = True

    def walk(name, prefix, visiting):
        nonlocal tx, ty, trans_only
        if name in visiting:
            raise ValueError(f"cyclic block reference in physical mode: {name}")
        visiting.add(name)
        df, boundary = blocks[name]
        if boundary:
            boundary_polys.append((name, [global_pt(p) for p in boundary]))
        for row in df.itertuples():
            cell = getattr(row, "cell_name")
            if cell in blocks:
                orient = getattr(row, "orient") or "N"
                ox = float(getattr(row, "location_x"))
                oy = float(getattr(row, "location_y"))
                chain.append((orient, (ox, oy)))
                was_trans = trans_only
                if orient == "N":
                    tx += ox
                    ty += oy
                else:
                    trans_only = False
                walk(cell, _join(prefix, getattr(row, "leaf_instance_name")), visiting)
                if orient == "N":
                    tx -= ox
                    ty -= oy
                trans_only = was_trans
                chain.pop()
                continue
            if getattr(row, "is_physical_only"):
                continue
            if cell not in sizes:
                continue  # missing cell -> no geometry
            orient = getattr(row, "orient") or "N"
            if orient not in Orient.orient_map:
                raise ValueError(f"invalid orient {orient!r}")
            ex, ey = _oriented_extent(orient, *sizes[cell])
            lx, ly = float(getattr(row, "location_x")), float(getattr(row, "location_y"))
            if trans_only:
                _xs0.append(lx + tx); _ys0.append(ly + ty)
                _xs1.append(lx + tx + ex); _ys1.append(ly + ty + ey)
            else:
                g = [global_pt(c) for c in
                     ((lx, ly), (lx + ex, ly), (lx, ly + ey), (lx + ex, ly + ey))]
                xs = [c[0] for c in g]
                ys = [c[1] for c in g]
                _xs0.append(min(xs)); _ys0.append(min(ys))
                _xs1.append(max(xs)); _ys1.append(max(ys))
            _leaks.append(float(getattr(row, "leakage_power")))
            _dyns.append(float(getattr(row, "dynamic_power")))
            _ulvts.append(is_ulvt.get(cell, False))
            _macros.append(is_macro.get(cell, False))
            _paths.append(_join(prefix, getattr(row, "leaf_instance_name")))
        visiting.discard(name)

    t_walk = time.perf_counter()
    walk(top, top, set())
    n = len(_paths)
    logger.info("physical: walked %d leaf box(es) (%.1fs)",
                n, time.perf_counter() - t_walk)

    # Compact arrays, sorted by leaf path so each hierarchy's boxes are a slice.
    geom = np.column_stack([_xs0, _ys0, _xs1, _ys1]).astype(np.float32)
    leak = np.asarray(_leaks, dtype=np.float32)
    dyn = np.asarray(_dyns, dtype=np.float32)
    is_ulvt = np.asarray(_ulvts, dtype=bool)
    is_macro = np.asarray(_macros, dtype=bool)
    leaf_paths = np.asarray(_paths, dtype=object)
    order = np.argsort(leaf_paths, kind="stable")
    geom, leak, dyn = geom[order], leak[order], dyn[order]
    is_ulvt, is_macro, leaf_paths = is_ulvt[order], is_macro[order], leaf_paths[order]
    del _xs0, _ys0, _xs1, _ys1, _leaks, _dyns, _ulvts, _macros, _paths

    bx = [p[0] for p in top_boundary]
    by = [p[1] for p in top_boundary]
    extent = (min(bx), min(by), max(bx), max(by))
    x0, y0, x1, y1 = extent

    cols = max(1, int(np.ceil((x1 - x0) / grid_size)))
    rows = max(1, int(np.ceil((y1 - y0) / grid_size)))
    density = np.zeros((rows, cols), dtype="float64")
    leakage = np.zeros((rows, cols), dtype="float64")
    dynamic = np.zeros((rows, cols), dtype="float64")
    ulvt = np.zeros((rows, cols), dtype="float64")
    gs = grid_size
    gs2 = gs * gs

    # --- vectorized rasterization ------------------------------------------
    # A box's contribution to its cell patch is separable (outer(oy, ox)/gs2),
    # so std cells (<= 2x2 patch) accumulate via bincount and macros via a
    # per-box outer-product update.
    bx0 = np.maximum(geom[:, 0], x0)
    by0 = np.maximum(geom[:, 1], y0)
    bx1 = np.minimum(geom[:, 2], x1)
    by1 = np.minimum(geom[:, 3], y1)
    keep = (bx1 > bx0) & (by1 > by0)
    bx0, by0, bx1, by1 = bx0[keep], by0[keep], bx1[keep], by1[keep]
    ul = is_ulvt[keep]
    lk = leak[keep]
    dynv = dyn[keep]
    box_area = (bx1 - bx0) * (by1 - by0)
    ix0 = np.maximum(0, np.minimum(cols - 1, ((bx0 - x0) // gs).astype(np.intp)))
    ix1 = np.maximum(0, np.minimum(cols - 1, ((bx1 - x0) // gs).astype(np.intp)))
    iy0 = np.maximum(0, np.minimum(rows - 1, ((by0 - y0) // gs).astype(np.intp)))
    iy1 = np.maximum(0, np.minimum(rows - 1, ((by1 - y0) // gs).astype(np.intp)))
    dx = ix1 - ix0
    ddy = iy1 - iy0

    def _acc(flat, ov, ba, lk_, dy_, ul_):
        """bincount-accumulate one group of (flat, overlap-area) pairs."""
        frac = ov / ba
        dens = ov / gs2
        density[...] += np.bincount(flat, weights=dens, minlength=rows * cols).reshape(rows, cols)
        ulvt[...] += np.bincount(flat, weights=np.where(ul_, dens, 0.0),
                                 minlength=rows * cols).reshape(rows, cols)
        leakage[...] += np.bincount(flat, weights=frac * lk_, minlength=rows * cols).reshape(rows, cols)
        dynamic[...] += np.bincount(flat, weights=frac * dy_, minlength=rows * cols).reshape(rows, cols)

    # 1x1 patch: box fully inside one cell
    m = (dx == 0) & (ddy == 0)
    if m.any():
        _acc(iy0[m] * cols + ix0[m], box_area[m], box_area[m], lk[m], dynv[m], ul[m])

    # 1x2 patch: one column, two rows (crosses a horizontal grid line)
    m = (dx == 0) & (ddy == 1)
    if m.any():
        w = bx1[m] - bx0[m]
        oy0 = (y0 + (iy0[m] + 1) * gs) - by0[m]
        oy1 = by1[m] - (y0 + (iy0[m] + 1) * gs)
        flat = np.concatenate([iy0[m] * cols + ix0[m], (iy0[m] + 1) * cols + ix0[m]])
        ov = np.concatenate([w * oy0, w * oy1])
        ba = np.concatenate([box_area[m], box_area[m]])
        _acc(flat, ov, ba, np.concatenate([lk[m], lk[m]]),
             np.concatenate([dynv[m], dynv[m]]), np.concatenate([ul[m], ul[m]]))

    # 2x1 patch: two columns, one row (crosses a vertical grid line)
    m = (dx == 1) & (ddy == 0)
    if m.any():
        h = by1[m] - by0[m]
        ox0 = (x0 + (ix0[m] + 1) * gs) - bx0[m]
        ox1 = bx1[m] - (x0 + (ix0[m] + 1) * gs)
        flat = np.concatenate([iy0[m] * cols + ix0[m], iy0[m] * cols + (ix0[m] + 1)])
        ov = np.concatenate([h * ox0, h * ox1])
        ba = np.concatenate([box_area[m], box_area[m]])
        _acc(flat, ov, ba, np.concatenate([lk[m], lk[m]]),
             np.concatenate([dynv[m], dynv[m]]), np.concatenate([ul[m], ul[m]]))

    # 2x2 patch: crosses both a horizontal and a vertical grid line
    m = (dx == 1) & (ddy == 1)
    if m.any():
        ox0 = (x0 + (ix0[m] + 1) * gs) - bx0[m]
        ox1 = bx1[m] - (x0 + (ix0[m] + 1) * gs)
        oy0 = (y0 + (iy0[m] + 1) * gs) - by0[m]
        oy1 = by1[m] - (y0 + (iy0[m] + 1) * gs)
        f00 = iy0[m] * cols + ix0[m]
        f01 = iy0[m] * cols + (ix0[m] + 1)
        f10 = (iy0[m] + 1) * cols + ix0[m]
        f11 = (iy0[m] + 1) * cols + (ix0[m] + 1)
        flat = np.concatenate([f00, f01, f10, f11])
        ov = np.concatenate([oy0 * ox0, oy0 * ox1, oy1 * ox0, oy1 * ox1])
        ba = np.concatenate([box_area[m]] * 4)
        lk4 = np.concatenate([lk[m]] * 4)
        dy4 = np.concatenate([dynv[m]] * 4)
        ul4 = np.concatenate([ul[m]] * 4)
        _acc(flat, ov, ba, lk4, dy4, ul4)

    # Larger patches (macros): few, so a per-box outer-product update is fine.
    for i in np.flatnonzero(~((dx <= 1) & (ddy <= 1))):
        r0, r1, c0, c1 = int(iy0[i]), int(iy1[i]), int(ix0[i]), int(ix1[i])
        col_l = x0 + np.arange(c0, c1 + 1) * gs
        col_r = x0 + (np.arange(c0, c1 + 1) + 1) * gs
        ox = np.minimum(bx1[i], col_r) - np.maximum(bx0[i], col_l)
        row_b = y0 + np.arange(r0, r1 + 1) * gs
        row_t = y0 + (np.arange(r0, r1 + 1) + 1) * gs
        oy = np.minimum(by1[i], row_t) - np.maximum(by0[i], row_b)
        patch = np.outer(oy, ox) / gs2
        density[r0:r1 + 1, c0:c1 + 1] += patch
        if ul[i]:
            ulvt[r0:r1 + 1, c0:c1 + 1] += patch
        frac = patch / box_area[i]
        leakage[r0:r1 + 1, c0:c1 + 1] += frac * lk[i]
        dynamic[r0:r1 + 1, c0:c1 + 1] += frac * dynv[i]

    # Density ratios are in [0, 1]. Clamp float round-off so fully-packed bins
    # land on exactly 1.0 (the heat map renders 100% density as white) instead
    # of 1.0 +/- 1e-13.
    density = np.clip(density, 0.0, 1.0)
    density[density > 1.0 - 1e-9] = 1.0
    ulvt = np.clip(ulvt, 0.0, 1.0)
    ulvt[ulvt > 1.0 - 1e-9] = 1.0

    logger.info("physical: %d cell box(es), grid %d x %d, extent %s",
                n, rows, cols, extent)
    return PhysicalData(top, boundary_polys, grid_size,
                        extent, rows, cols, density, leakage, dynamic, ulvt,
                        geom, is_ulvt, is_macro, leak, dyn, leaf_paths, contour_gap)
