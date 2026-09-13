"""Exact rasterisation of routing shapes onto a bin grid.

The metal-density metric needs, for every grid cell, the total area of a set of shapes
clipped to that cell - exactly, not sampled, because the result is a ratio the user is
meant to trust.

The existing physical-mode rasteriser cannot be reused. It is built for small cells, with
hand-written 1x1 / 1x2 / 2x1 / 2x2 cases and a per-shape ``np.outer`` patch for anything
larger, so its cost is ``O(bins touched)`` *plus a fresh allocation per shape*. A wire is
long, thin, and there are millions of them; the allocation is what makes it unusable.

**Approach.** Axis-aligned rectangles - which is almost everything, since a routing
segment inflated by its spacing is still a rectangle - are split at bin boundaries into
pieces that each fall inside exactly one bin, and the pieces are folded into the grid with
a single weighted ``np.bincount`` per chunk. Cost is ``O(sum of bins touched)`` with no
per-shape allocation. For routing geometry that sum is small: a segment is about one gcell
long, so it touches a handful of bins.

This is deliberately *not* the difference-array scheme originally planned for this module.
That scheme is ``O(1)`` per shape regardless of span, which sounds better, but it needs
four to nine constant-add ranges per rectangle - roughly 12 to 36 scatter writes against
the 2 to 6 bin pieces this needs - plus a full ``cumsum`` over the grid per layer. Measured
on the real routed DEF the bin-piece approach won on both counts. The difference array
would still win for pathological input (many die-spanning shapes), and that trade is
recorded in the as-built doc rather than hidden.

Shapes that are neither axis-aligned nor polygonal - 45-degree jogs - go through
``add_segment``, which builds the exact Minkowski sum of the segment with a square via
``LineString.buffer(cap_style=square)`` and rasterises it exactly. That path is per-bin and
therefore slow, but diagonals are a small minority and correctness matters more than speed
for them. A bounding box, the obvious shortcut, over-counts a 10 um diagonal by about 25x.
"""
from __future__ import annotations

import numpy as np

# Rectangles are accumulated in chunks so peak memory is bounded by the chunk rather than
# by the design. Two budgets, because they bound different things:
#
#   DEFAULT_CHUNK   queued (bin, area) pieces - the pending queue.
#   DEFAULT_BLOCK   shapes per call - the working arrays. This one is the bigger lever:
#                   a call holds roughly twenty arrays the length of its input, so at
#                   eight million shapes that is well over a gigabyte, and it was the
#                   actual peak until the input itself was blocked up.
DEFAULT_CHUNK = 1 << 20
DEFAULT_BLOCK = 1 << 18

_EMPTY_INDEX = np.empty(0, dtype=np.int32)
_EMPTY_AREA = np.empty(0, dtype=np.float64)


class Bins:
    """One layer's bin accumulator.

    Holds the grid geometry, a running sum, and a queue of pending ``(bin, area)`` pairs.
    Callers add shapes as they stream past and read :meth:`grid` at the end. One instance
    per layer, because the metric keeps the layers separate; the queue is what keeps the
    memory flat while a hundred million shapes go by.
    """

    def __init__(self, extent, grid_size, chunk: int = DEFAULT_CHUNK,
                 block: int = DEFAULT_BLOCK):
        if grid_size <= 0:
            raise ValueError("grid size must be > 0")
        self.origin_x, self.origin_y = float(extent[0]), float(extent[1])
        self.extent = tuple(float(v) for v in extent)
        self.grid_size = float(grid_size)
        # ceil, so the grid covers the whole extent; the last column or row may hang over
        # the edge by up to one grid step, and shapes are clipped to the extent anyway.
        self.cols = max(1, int(np.ceil((extent[2] - extent[0]) / grid_size)))
        self.rows = max(1, int(np.ceil((extent[3] - extent[1]) / grid_size)))
        self._chunk = max(1, int(chunk))
        self._block = max(1, int(block))
        self._sum = np.zeros((self.rows, self.cols), dtype=np.float64)
        self._pending: list = []
        self._queued = 0
        # Counts kept for the caller's diagnostics: shapes with no area in the grid, and
        # shapes routed through the slow per-bin path.
        self.n_empty = 0
        self.n_polygon = 0

    # -- shapes ---------------------------------------------------------------------

    def add_rects(self, x0, y0, x1, y1, weights=None) -> None:
        """Accumulate axis-aligned rectangles: exact per-bin overlap area for each.

        Rectangles that are degenerate, reversed, or entirely outside the grid contribute
        nothing and are counted in ``n_empty``. ``weights`` scales each rectangle's
        contribution, which is how one call serves both "raw area" and "area times a
        per-shape factor".

        The input is walked in blocks. A call holds roughly twenty working arrays the
        length of its input, so without blocking the peak tracks the caller's batch size -
        at eight million shapes that alone was more than a gigabyte, and it dwarfed the
        piece expansion the chunking was written for.
        """
        x0, y0, x1, y1 = (np.asarray(v, dtype=np.float64) for v in (x0, y0, x1, y1))
        if x0.size == 0:
            return
        if weights is not None:
            weights = np.asarray(weights, dtype=np.float64)

        for start in range(0, x0.size, self._block):
            stop = min(start + self._block, x0.size)
            self._add_block(x0[start:stop], y0[start:stop], x1[start:stop],
                            y1[start:stop],
                            None if weights is None else weights[start:stop])

    def _add_block(self, x0, y0, x1, y1, weights) -> None:
        # Normalise reversed corners rather than rejecting them: '+ RECT' is written with
        # its corners in whatever order the tool chose.
        lo_x, hi_x = np.minimum(x0, x1), np.maximum(x0, x1)
        lo_y, hi_y = np.minimum(y0, y1), np.maximum(y0, y1)
        # Clip to the *extent*, not to the grid's span. The grid rounds up, so its last
        # column and row normally overhang the die - a 200 um die at a 7 um grid ends at
        # 203 um - and that overhang is not design area. Clipping to the grid span instead
        # inflates every edge cell by the shapes that reach the boundary.
        lo_x = np.clip(lo_x, self.origin_x, self.extent[2])
        hi_x = np.clip(hi_x, self.origin_x, self.extent[2])
        lo_y = np.clip(lo_y, self.origin_y, self.extent[3])
        hi_y = np.clip(hi_y, self.origin_y, self.extent[3])

        # Bin index range with positive overlap. 'ceil(b) - 1' excludes a bin the shape
        # only touches the boundary of: a rectangle ending exactly on a bin edge covers
        # the bins to its left only.
        i0x = np.floor((lo_x - self.origin_x) / self.grid_size).astype(np.int64)
        i1x = np.ceil((hi_x - self.origin_x) / self.grid_size).astype(np.int64) - 1
        i0y = np.floor((lo_y - self.origin_y) / self.grid_size).astype(np.int64)
        i1y = np.ceil((hi_y - self.origin_y) / self.grid_size).astype(np.int64) - 1

        live = (i1x >= i0x) & (i1y >= i0y) & (hi_x > lo_x) & (hi_y > lo_y)
        self.n_empty += int(live.size - live.sum())
        if not live.any():
            return
        self._emit_pieces(lo_x, lo_y, hi_x, hi_y, i0x, i0y, i1x, i1y, live, weights)

    def _emit_pieces(self, lo_x, lo_y, hi_x, hi_y, i0x, i0y, i1x, i1y, live, weights):
        """Split each live rectangle into one piece per bin it overlaps, and queue them.

        A piece is the intersection of the rectangle with one bin, so it lies wholly
        inside that bin and its area is the bin's exact share.
        """
        lo_x, lo_y, hi_x, hi_y = lo_x[live], lo_y[live], hi_x[live], hi_y[live]
        i0x, i0y, i1x, i1y = i0x[live], i0y[live], i1x[live], i1y[live]
        per_shape_weight = None if weights is None else weights[live]

        spans_x = i1x - i0x + 1
        spans_y = i1y - i0y + 1
        counts = spans_x * spans_y

        # Chunk here rather than in the caller: a single batch of long shapes can expand
        # to far more pieces than shapes, and this is where that is visible.
        if int(counts.sum()) == 0:
            return
        pieces_per_round = max(1, self._chunk // 4)
        for start, stop in self._piece_windows(counts, pieces_per_round):
            index, area, weight = self._pieces_in_window(
                start, stop, spans_x, spans_y, lo_x, lo_y, hi_x, hi_y,
                i0x, i0y, per_shape_weight)
            if index.size:
                self._push(index, area if weight is None else area * weight)

    def _pieces_in_window(self, start, stop, spans_x, spans_y, lo_x, lo_y, hi_x, hi_y,
                          i0x, i0y, per_shape_weight):
        """Bin indices and exact areas for every piece of one window of shapes.

        Built with ``np.repeat`` over flat arrays. That looks wasteful next to grouping
        shapes by their piece shape and broadcasting a ``(shapes, pieces)`` grid - the
        grouping removes nine of the ten repeats - but it measures **2x slower**: the
        grouping needs a column-wise ``np.unique`` over every shape to find the groups,
        plus 2-D temporaries that are much less cache-friendly than these flat passes.
        Recorded because the faster-looking version is the tempting one.
        """
        shape_count = stop - start
        if shape_count <= 0:
            return _EMPTY_INDEX, _EMPTY_AREA, None
        repeats = (spans_x[start:stop] * spans_y[start:stop]).astype(np.int64)

        pairs = np.repeat(spans_x[start:stop], repeats)
        within = np.arange(int(repeats.sum()), dtype=np.int64) - np.repeat(
            np.cumsum(repeats) - repeats, repeats)

        col = np.repeat(i0x[start:stop], repeats) + within % pairs
        row = np.repeat(i0y[start:stop], repeats) + within // pairs

        # The piece is the shape clipped to its bin.
        origin_x, origin_y, grid = self.origin_x, self.origin_y, self.grid_size
        piece_x0 = np.maximum(np.repeat(lo_x[start:stop], repeats), origin_x + col * grid)
        piece_x1 = np.minimum(np.repeat(hi_x[start:stop], repeats),
                              origin_x + (col + 1) * grid)
        piece_y0 = np.maximum(np.repeat(lo_y[start:stop], repeats), origin_y + row * grid)
        piece_y1 = np.minimum(np.repeat(hi_y[start:stop], repeats),
                              origin_y + (row + 1) * grid)

        area = (piece_x1 - piece_x0) * (piece_y1 - piece_y0)
        # int32: a flat bin index cannot approach 2**31 for a grid that fits in memory,
        # and the narrower index is a real saving at these piece counts.
        index = (row * self.cols + col).astype(np.int32, copy=False)
        if per_shape_weight is None:
            return index, area, None
        # Only needed when a caller passes weights, so it is not built otherwise.
        return index, area, per_shape_weight[start:stop][
            np.repeat(np.arange(shape_count), repeats)]

    def _piece_windows(self, counts, pieces_per_round):
        """Split shapes into groups whose total piece count fits the budget.

        Yields ``(start, stop)`` shape-index windows, so a batch holding one die-spanning
        stripe next to a million short wires stays bounded in memory.

        The boundaries come from a cumulative sum rather than a walk over the shapes: with
        millions of shapes a per-shape Python loop costs seconds by itself, which would
        give back most of what this module exists to save.
        """
        total = int(counts.sum())
        if total == 0:
            return
        crosses = np.searchsorted(np.cumsum(counts),
                                  np.arange(pieces_per_round, total, pieces_per_round))
        start = 0
        for stop in crosses:
            yield start, int(stop) + 1
            start = int(stop) + 1
        if start < counts.size:
            yield start, counts.size

    def add_polygon(self, ring, clip_to_grid: bool = True) -> None:
        """Accumulate one simple polygon exactly, bin by bin.

        The slow path, used for the minority of shapes that are not rectangles - including
        45-degree segments, which arrive here as their Minkowski sum. Per-bin ``shapely``
        intersection is far too slow for a whole design, but a diagonal is a small part of
        one, and this is exact where a bounding box would over-count by an order of
        magnitude.

        ``ring`` is a sequence of ``(x, y)`` vertices; the ring is closed automatically.
        """
        from shapely.geometry import Polygon, box

        points = [(float(x), float(y)) for x, y in ring]
        if len(points) > 1 and points[0] == points[-1]:
            points = points[:-1]
        if len(points) < 3:
            self.n_empty += 1
            return

        # An axis-aligned rectangle takes the vectorised path. It is not a special case for
        # tidiness: this loop is one shapely intersection per bin, and a die outline
        # rasterised this way at a 20 mm / 10 um grid is four million of them - measured at
        # 345 seconds for a run whose rasterising was under a second. Die areas and power
        # rings are rectangles almost always, so this is the common path, not a shortcut.
        if len(points) == 4:
            xs = {point[0] for point in points}
            ys = {point[1] for point in points}
            if len(xs) == 2 and len(ys) == 2:
                x0, x1 = min(xs), max(xs)
                y0, y1 = min(ys), max(ys)
                self.add_rects([x0], [y0], [x1], [y1])
                return

        polygon = Polygon(points)
        if not polygon.is_valid:
            polygon = polygon.buffer(0)          # self-touching rings; rare, but cheap
        if polygon.is_empty or polygon.area <= 0:
            self.n_empty += 1
            return

        min_x, min_y, max_x, max_y = polygon.bounds
        if clip_to_grid:
            # The extent, not the grid's span - see add_rects.
            min_x = max(min_x, self.origin_x)
            min_y = max(min_y, self.origin_y)
            max_x = min(max_x, self.extent[2])
            max_y = min(max_y, self.extent[3])
            if max_x <= min_x or max_y <= min_y:
                self.n_empty += 1
                return

        self.n_polygon += 1
        col0 = int(np.floor((min_x - self.origin_x) / self.grid_size))
        col1 = int(np.ceil((max_x - self.origin_x) / self.grid_size)) - 1
        row0 = int(np.floor((min_y - self.origin_y) / self.grid_size))
        row1 = int(np.ceil((max_y - self.origin_y) / self.grid_size)) - 1

        for row in range(max(0, row0), min(self.rows - 1, row1) + 1):
            y0 = self.origin_y + row * self.grid_size
            y1 = y0 + self.grid_size
            for col in range(max(0, col0), min(self.cols - 1, col1) + 1):
                x0 = self.origin_x + col * self.grid_size
                cell = box(x0, y0, x0 + self.grid_size, y1)
                if not polygon.intersects(cell):
                    continue
                area = polygon.intersection(cell).area
                if area > 0:
                    self._push_single(row * self.cols + col, area)

    def add_segment(self, x0, y0, x1, y1, half_width) -> None:
        """Accumulate one segment's exact covered region, at any angle.

        The region is the Minkowski sum of the segment with an axis-aligned square of side
        ``2 * half_width`` - the segment plus the space its width and spacing claim. For a
        Manhattan segment that is exactly a rectangle (so this reduces to
        :meth:`add_rects`), and for a 45-degree jog it is the hexagon that is actually
        occupied. ``cap_style=3`` is shapely's square cap, which is that Minkowski sum.
        """
        from shapely.geometry import LineString

        if half_width <= 0:
            self.n_empty += 1
            return
        covered = LineString([(float(x0), float(y0)), (float(x1), float(y1))]).buffer(
            float(half_width), cap_style=3)
        self.add_polygon(list(covered.exterior.coords))

    # -- accumulation ----------------------------------------------------------------

    def _push(self, index, area) -> None:
        if index.size:
            self._pending.append((index, area))
            self._queued += int(index.size)
            if self._queued >= self._chunk:
                self.flush()

    def _push_single(self, index, area) -> None:
        self._pending.append((np.array([index], dtype=np.int64),
                              np.array([area], dtype=np.float64)))
        self._queued += 1
        if self._queued >= self._chunk:
            self.flush()

    def flush(self) -> None:
        """Fold the queued pieces into the running sum and release them."""
        if not self._pending:
            return
        index = np.concatenate([p[0] for p in self._pending])
        area = np.concatenate([p[1] for p in self._pending])
        self._sum += np.bincount(index, weights=area,
                                 minlength=self.rows * self.cols).reshape(self.rows,
                                                                         self.cols)
        self._pending = []
        self._queued = 0

    def add_grid(self, grid) -> None:
        """Add one already-rasterised grid, for a caller that rasterised it elsewhere.

        The parallel wiring pass has each worker accumulate its own grids and sums them here,
        which is one array addition per layer rather than the per-shape work that produced it.
        A shape cannot land in two layers, so the sums are the same ones; only their order
        differs, which is why the last bits of a float32 sum can differ from a single run.
        """
        grid = np.asarray(grid, dtype=np.float64)
        if grid.shape != self._sum.shape:
            raise ValueError(f"grid is {grid.shape}, this layer's is {self._sum.shape}")
        self._sum += grid

    def grid(self, dtype="float32") -> np.ndarray:
        """The accumulated per-bin totals, as a ``(rows, cols)`` array."""
        self.flush()
        return self._sum.astype(dtype)

    @property
    def shape(self):
        return self.rows, self.cols

    def __repr__(self):
        return (f"Bins({self.rows}x{self.cols} @ {self.grid_size:g}, "
                f"queued={self._queued}, empty={self.n_empty}, "
                f"polygons={self.n_polygon})")
