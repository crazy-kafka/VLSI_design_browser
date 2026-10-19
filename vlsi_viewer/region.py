"""Region selection: tile snapping and hierarchy metrics restricted to a rectangle.

This module is pure data (no Qt). :class:`RegionData` reads the path-sorted box
arrays built by :func:`vlsi_viewer.physical.build_physical`, keeps only the boxes
that intersect the selected tile rectangle, and aggregates the same raw columns
``metrics._flatten`` uses. ``model.view_for_region`` turns that into a
``TreeView`` for the second hierarchy tree.

Physical-only instances are excluded before aggregation: filler/tap/decap carry
real area in the density heat map, but they are not part of the hierarchy tree.
"""
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import schema
from .metrics import RAW_COLS

_CHUNK = 2_000_000


@dataclass(frozen=True)
class RegionSelection:
    """A tile-aligned selection in physical coordinates."""

    rect: tuple          # (x0, y0, x1, y1)
    col0: int
    row0: int
    col1: int
    row1: int

    @property
    def tile_count(self) -> int:
        return (self.col1 - self.col0 + 1) * (self.row1 - self.row0 + 1)

    @property
    def width(self) -> float:
        return self.rect[2] - self.rect[0]

    @property
    def height(self) -> float:
        return self.rect[3] - self.rect[1]


def selection_from_points(px0, py0, px1, py1, extent, grid_size, rows, cols):
    """Snap the press/release points to whole tiles.

    The tile grid spans ``[x0, x0 + cols*g] x [y0, y0 + rows*g]`` and may overhang
    the die, just like the heat-map pixmap. Both endpoints are mapped with
    ``floor``; the inclusive range between them is clamped to the grid. A drag
    ending exactly on a tile boundary therefore includes the tile above/right of
    it. A click is the degenerate one-tile case. Returns ``None`` when the
    press/release box does not overlap the tile grid at all (a clear).
    """
    x0, y0 = extent[0], extent[1]
    gx1 = x0 + cols * grid_size
    gy1 = y0 + rows * grid_size
    bx0, bx1 = sorted((px0, px1))
    by0, by1 = sorted((py0, py1))

    if bx1 <= x0 or bx0 >= gx1 or by1 <= y0 or by0 >= gy1:
        return None

    c0 = max(0, min(cols - 1, int(np.floor((bx0 - x0) / grid_size))))
    c1 = max(0, min(cols - 1, int(np.floor((bx1 - x0) / grid_size))))
    r0 = max(0, min(rows - 1, int(np.floor((by0 - y0) / grid_size))))
    r1 = max(0, min(rows - 1, int(np.floor((by1 - y0) / grid_size))))

    rect = (x0 + c0 * grid_size, y0 + r0 * grid_size,
            x0 + (c1 + 1) * grid_size, y0 + (r1 + 1) * grid_size)
    return RegionSelection(rect, c0, r0, c1, r1)


class RegionData:
    """Boxes intersecting one tile-aligned selection, aggregated per hierarchy path.

    The selection mask and overlap fractions are computed once in the constructor
    (a vectorised O(N) scan). Per-path raw columns and metric values are computed
    lazily and cached, because the second tree only visits the rows the user
    expands.
    """

    def __init__(self, physical, design, selection: RegionSelection):
        self._physical = physical
        self._design = design
        self.selection = selection
        self._geom = physical._geom
        self._is_macro = physical._is_macro
        self._is_ulvt = physical._is_ulvt
        self._cell_codes = physical._cell_codes
        self._cell_attrs = physical._cell_attrs
        if self._cell_codes is None:
            raise RuntimeError("PhysicalData has no cell metadata; rebuild with build_physical")

        rx0, ry0, rx1, ry1 = selection.rect
        hit = ((self._geom[:, 0] < rx1) & (self._geom[:, 2] > rx0)
               & (self._geom[:, 1] < ry1) & (self._geom[:, 3] > ry0)
               & ~physical._is_phys_only)
        self._idx = np.flatnonzero(hit).astype(np.intp)
        self._frac = self._fractions(rx0, ry0, rx1, ry1)

        self._stats_cache = {}
        self._metric_cache = {}

    @property
    def roots(self):
        return self._design.roots

    @property
    def children(self):
        return self._design.children

    @property
    def selected_count(self) -> int:
        """Selected instances, excluding physical-only ones."""
        return int(self._idx.size)

    def _fractions(self, rx0, ry0, rx1, ry1) -> np.ndarray:
        """Overlap area / box area for each selected box, in chunks."""
        out = np.empty(self._idx.size, dtype=np.float32)
        for start in range(0, self._idx.size, _CHUNK):
            stop = min(start + _CHUNK, self._idx.size)
            g = self._geom[self._idx[start:stop]]
            ix = np.maximum(0.0, np.minimum(g[:, 2], rx1) - np.maximum(g[:, 0], rx0))
            iy = np.maximum(0.0, np.minimum(g[:, 3], ry1) - np.maximum(g[:, 1], ry0))
            full = (g[:, 2] - g[:, 0]) * (g[:, 3] - g[:, 1])
            out[start:stop] = np.divide(
                ix * iy, full,
                out=np.zeros(full.shape, dtype=np.float64), where=full > 0)
        return out

    def _leaf_range(self, path: str):
        sl = self._physical._slice_for(path)
        return sl.start, sl.stop

    def stats(self, path: str):
        """RAW_COLS for ``path`` and its descendants, or None when nothing is selected."""
        if path in self._stats_cache:
            return self._stats_cache[path]

        start, stop = self._leaf_range(path)
        lo = int(np.searchsorted(self._idx, start, side="left"))
        hi = int(np.searchsorted(self._idx, stop, side="left"))
        if lo >= hi:
            self._stats_cache[path] = None
            return None

        idx = self._idx[lo:hi]
        frac = self._frac[lo:hi]
        macro = self._is_macro[idx]
        std = ~macro
        codes = self._cell_codes[idx]
        attrs = self._cell_attrs
        area = attrs["area"][codes]
        drive = attrs["drive_size"][codes]
        is_bi = attrs["is_bi"][codes]
        is_pulse = attrs["is_pulse"][codes]
        is_clock = attrs["is_clock"][codes]
        is_icg = attrs["is_icg"][codes]
        reg_bits = attrs["reg_bits"][codes]
        mb_bits = attrs["mb_bits"][codes]
        ulvt = self._is_ulvt[idx]

        std_frac = frac[std]
        std_area = area[std]
        out = {
            "count": int(std.sum()),
            "area": float(np.sum(std_area * std_frac)),
            "ulvt_area": float(np.sum(np.where(ulvt[std], std_area, 0.0) * std_frac)),
            "reg_bits": float(np.sum(reg_bits[std] * std_frac)),
            "mb_bits": float(np.sum(mb_bits[std] * std_frac)),
            "d1d2_count": int(np.sum(std & (drive <= 2))),
            "bi_count": int(np.sum(std & is_bi)),
            "bi_area": float(np.sum(np.where(is_bi[std], std_area, 0.0) * std_frac)),
            "pul_count": int(np.sum(std & is_pulse)),
            "ckb_count": int(np.sum(std & is_bi & is_clock)),
            "icg_count": int(np.sum(std & is_icg)),
            "macro_count": int(macro.sum()),
            "macro_area": float(np.sum(area[macro] * frac[macro])),
        }
        self._stats_cache[path] = out
        return out

    def any_selected(self, path: str) -> bool:
        """Whether ``path`` has at least one selected non-physical instance."""
        return self.stats(path) is not None

    def metric_values(self, path: str) -> dict:
        """All registered metric values for ``path``, or ``{}`` when empty."""
        if path not in self._metric_cache:
            raw = self.stats(path)
            if raw is None:
                self._metric_cache[path] = {}
            else:
                frame = pd.DataFrame([raw], columns=RAW_COLS)
                self._metric_cache[path] = {
                    m.key: m.compute(frame).iloc[0] for m in schema.METRICS}
        return self._metric_cache[path]

    def prefetch(self, paths) -> None:
        """Compute metric values for many paths in one batched pandas pass."""
        missing = [p for p in paths if p not in self._metric_cache]
        if not missing:
            return
        rows = {}
        for path in missing:
            raw = self.stats(path)
            if raw is None:
                self._metric_cache[path] = {}
            else:
                rows[path] = raw
        if not rows:
            return
        frame = pd.DataFrame.from_dict(rows, orient="index", columns=RAW_COLS)
        for m in schema.METRICS:
            values = m.compute(frame)
            for path in rows:
                self._metric_cache.setdefault(path, {})[m.key] = values.loc[path]

    def summary_text(self) -> str:
        s = self.selection
        return (f"{s.col1 - s.col0 + 1} × {s.row1 - s.row0 + 1} tiles · "
                f"{s.width:g} × {s.height:g} µm · {self.selected_count:,} inst")
