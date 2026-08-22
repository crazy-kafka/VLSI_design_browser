"""Physical mode: build the 2-D heat-map grids (density / leakage / dynamic power).

Placement + orientation follow DEF semantics: each instance's ``location_x/y`` is
the lower-left corner of its (possibly rotated) bounding box, and ``orient`` is one
of N/S/W/E/FN/FS/FW/FE. Nested sub-block instances are composed through their
placement frame using :mod:`vlsi_viewer.coordinateProcess`.
"""
import logging
import time

import numpy as np

from . import schema
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
        self._contour_cache = {}               # path -> (geom|None, loops, area)

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
        left = int(np.searchsorted(self._leaf_paths, path, side="left"))
        right = int(np.searchsorted(self._leaf_paths, path + "￿", side="left"))
        return slice(left, right)

    def boxes_for(self, path: str):
        """(k, 4) float32 box array for ``path`` and its descendants."""
        return self._geom[self._slice_for(path)]

    def contour_for(self, path: str):
        """Closed contour loops + enclosed area for a hierarchy path (cached)."""
        from . import contour
        cached = self._contour_cache.get(path)
        if cached is not None:
            return cached[1], cached[2]

        boxes = self._geom[self._slice_for(path)]
        t0 = time.perf_counter()
        if contour._BACKEND == "shapely":
            geom = contour.union_geometry(boxes, self.contour_gap)
            loops, area = contour.geom_loops_area(geom)
        else:
            geom = None
            loops, area = contour.contour_geometry(boxes, self.contour_gap)
        self._contour_cache[path] = (geom, loops, area)
        logger.info("contour: %s (%d boxes) -> %d loop(s), area %.0f (%.1fs)",
                    path, len(boxes), len(loops), area, time.perf_counter() - t0)
        return loops, area

    def density_for(self, path: str) -> float:
        """Hierarchy density = non_macro_area / (contour_area - macro_area)."""
        _, area = self.contour_for(path)
        sl = self._slice_for(path)
        box_area = (self._geom[sl, 2] - self._geom[sl, 0]) * (self._geom[sl, 3] - self._geom[sl, 1])
        mac = float(box_area[self._is_macro[sl]].sum())
        non = float(box_area[~self._is_macro[sl]].sum())
        den = area - mac
        if den <= 0 or non <= 0:
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
    hierarchy's instances into one contour loop; defaults to ``2 * grid_size``.

    Raises ``ValueError`` if there is not exactly one top-level block, if the top
    block has no ``boundary``, or if a boundary is not rectilinear.
    """
    if grid_size <= 0:
        raise ValueError("grid size must be > 0")
    if contour_gap is None:
        contour_gap = 2.0 * grid_size
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

    def walk(name, prefix, visiting):
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
                chain.append((orient, (float(getattr(row, "location_x")),
                                       float(getattr(row, "location_y")))))
                walk(cell, _join(prefix, getattr(row, "leaf_instance_name")), visiting)
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
    grid_area = grid_size * grid_size

    for i in range(n):
        bx0, by0, bx1, by1 = geom[i]
        bx0, by0 = max(bx0, x0), max(by0, y0)
        bx1, by1 = min(bx1, x1), min(by1, y1)
        if bx1 <= bx0 or by1 <= by0:
            continue
        ix0 = max(0, min(cols - 1, int((bx0 - x0) // grid_size)))
        ix1 = max(0, min(cols - 1, int((bx1 - x0) // grid_size)))
        iy0 = max(0, min(rows - 1, int((by0 - y0) // grid_size)))
        iy1 = max(0, min(rows - 1, int((by1 - y0) // grid_size)))
        box_area = (bx1 - bx0) * (by1 - by0)
        ul = bool(is_ulvt[i])
        lk = float(leak[i])
        dy = float(dyn[i])
        for iy in range(iy0, iy1 + 1):
            gy0 = y0 + iy * grid_size
            gy1 = gy0 + grid_size
            oy = max(0.0, min(gy1, by1) - max(gy0, by0))
            if oy <= 0:
                continue
            for ix in range(ix0, ix1 + 1):
                gx0 = x0 + ix * grid_size
                gx1 = gx0 + grid_size
                ox = max(0.0, min(gx1, bx1) - max(gx0, bx0))
                if ox <= 0:
                    continue
                ov = ox * oy
                density[iy, ix] += ov / grid_area
                if ul:
                    ulvt[iy, ix] += ov / grid_area
                frac = ov / box_area
                leakage[iy, ix] += frac * lk
                dynamic[iy, ix] += frac * dy

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
