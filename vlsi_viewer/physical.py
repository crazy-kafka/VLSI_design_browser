"""Physical mode: build the 2-D heat-map grids (density / leakage / dynamic power).

Placement + orientation follow DEF semantics: each instance's ``location_x/y`` is
the lower-left corner of its (possibly rotated) bounding box, and ``orient`` is one
of N/S/W/E/FN/FS/FW/FE. Nested sub-block instances are composed through their
placement frame using :mod:`vlsi_viewer.coordinateProcess`.
"""
import logging

import numpy as np

from . import schema
from .coordinateProcess import CoordinateProcess, Orient
from .loader import load_block, load_cell_info

logger = logging.getLogger(__name__)


class PhysicalData:
    """Precomputed grids + geometry for one physical layout view."""

    def __init__(self, top_name, boundary_polys, boxes, grid_size,
                 extent, rows, cols, density, leakage, dynamic):
        self.top_name = top_name
        self.boundary_polys = boundary_polys   # list of (name, [(x, y), ...]) in global coords
        self.boxes = boxes                     # (x0, y0, x1, y1, leakage, dynamic)
        self.grid_size = grid_size
        self.extent = extent                   # (x0, y0, x1, y1) grid bounds
        self.rows = rows
        self.cols = cols
        self.density = density                 # (rows, cols)
        self.leakage = leakage                 # (rows, cols)
        self.dynamic = dynamic                 # (rows, cols)

    def heat(self, kind: str) -> np.ndarray:
        return {"density": self.density, "leakage": self.leakage,
                "dynamic": self.dynamic}[kind]


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


def build_physical(block_paths, cell_path, grid_size: float = 3.0) -> PhysicalData:
    """Build heat-map grids for a single-top-block design.

    Raises ``ValueError`` if there is not exactly one top-level block, if the top
    block has no ``boundary``, or if a boundary is not rectilinear.
    """
    if grid_size <= 0:
        raise ValueError("grid size must be > 0")
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

    chain = []        # outermost-first list of (orient, origin) container frames
    boundary_polys = []
    boxes = []

    def global_pt(pt):
        # A leaf's point is in its innermost block's local frame; compose the
        # container frames innermost-first (reverse push order) to reach global.
        x, y = pt
        for orient, origin in reversed(chain):
            x, y = CoordinateProcess.dbTransform("to_global", (x, y), orient, origin)
        return x, y

    def walk(name, visiting):
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
                walk(cell, visiting)
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
            boxes.append((min(xs), min(ys), max(xs), max(ys),
                          float(getattr(row, "leakage_power")),
                          float(getattr(row, "dynamic_power"))))
        visiting.discard(name)

    walk(top, set())

    bx = [p[0] for p in top_boundary]
    by = [p[1] for p in top_boundary]
    extent = (min(bx), min(by), max(bx), max(by))
    x0, y0, x1, y1 = extent

    cols = max(1, int(np.ceil((x1 - x0) / grid_size)))
    rows = max(1, int(np.ceil((y1 - y0) / grid_size)))
    density = np.zeros((rows, cols), dtype="float64")
    leakage = np.zeros((rows, cols), dtype="float64")
    dynamic = np.zeros((rows, cols), dtype="float64")
    grid_area = grid_size * grid_size

    for (bx0, by0, bx1, by1, leak, dyn) in boxes:
        bx0, by0 = max(bx0, x0), max(by0, y0)
        bx1, by1 = min(bx1, x1), min(by1, y1)
        if bx1 <= bx0 or by1 <= by0:
            continue
        ix0 = max(0, min(cols - 1, int((bx0 - x0) // grid_size)))
        ix1 = max(0, min(cols - 1, int((bx1 - x0) // grid_size)))
        iy0 = max(0, min(rows - 1, int((by0 - y0) // grid_size)))
        iy1 = max(0, min(rows - 1, int((by1 - y0) // grid_size)))
        box_area = (bx1 - bx0) * (by1 - by0)
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
                frac = ov / box_area
                leakage[iy, ix] += frac * leak
                dynamic[iy, ix] += frac * dyn

    # Density is a ratio in [0, 1]. Clamp float round-off so fully-packed bins
    # land on exactly 1.0 (the heat map renders 100% density as white) instead
    # of 1.0 +/- 1e-13.
    density = np.clip(density, 0.0, 1.0)
    density[density > 1.0 - 1e-9] = 1.0

    logger.info("physical: %d cell box(es), grid %d x %d, extent %s",
                len(boxes), rows, cols, extent)
    return PhysicalData(top, boundary_polys, boxes, grid_size,
                        extent, rows, cols, density, leakage, dynamic)
