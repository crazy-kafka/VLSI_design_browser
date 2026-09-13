"""Metal-density grids: per-layer routing utilisation.

The metric, in full, because it is the point of the feature.

**Keep-out expansion.** Each wire segment is expanded by half its own spacing rule on every
side. The reason is calibration: a minimum-width wire expanded by half the spacing covers
exactly ``W + S`` across, and ``W + S`` is the layer's track pitch, so the expanded area is
measured in *track-pitch area consumed* and ``1.0`` means every track is used. A wire routed
at ``2W2S`` expands to twice that, i.e. two track pitches, with no special case.

**Capacity is normalised by the actual pitch.** ``W + S == P`` holds for Nangate45 but not
for every library - sky130's met1 is 0.14 + 0.14 against a 0.34 pitch, and Nangate45's own
metal2 is 0.14 against 0.19. Where they differ, a fully-utilised layer's expanded area is only
``(W+S)/P`` of the cell, so dividing by the raw cell area would read 0.74 at *full*
utilisation. Capacity therefore carries the same factor:

    f_L    = (W_L + S_L) / P_L
    C_L(c) = routable_L(c) * f_L
    U_L(c) = clip(D_L(c) / C_L(c), 0, 1)

At full utilisation with a ``kW/kS`` rule the effective pitch is ``kP``, so the wire count is
``g/(kP)`` and ``D = g^2 (W+S)/P = C``: ``U = 1.0`` means full track utilisation for any rule
mix and any library. Fall back to ``f_L = 1`` when the LEF gives no pitch.

**Macros block what their LEF says they block.** A hard macro's ``OBS`` names the layers it
obstructs and the geometry on each, so that is what removes capacity - a macro that blocks
``metal2`` and ``metal4`` but not ``metal3`` is expressible, and so is one that blocks only
part of its own outline. Only the obstructions that cover a meaningful part of the macro
count (``OBS_MIN_FOOTPRINT_FRACTION``); a scattered pin-access bite is not a keep-out region.
A macro whose LEF declares no ``OBS`` cannot be judged from data at all, and falls back to
``macro_block_layers`` (default 4): the bottom N layers, over the whole outline. That fallback
is a guess, so it is reported when it engages.

**Groups are capacity-weighted.** Layers are parallel resources, so a group's utilisation is
``sum(D_L) / sum(C_L)`` - not a sum, which would drive every cell to 1.0, and not a plain
mean, because the members no longer share a capacity once macros block some of them.

**Signal and power are separable.** A power stripe is fixed and deliberate; merging it with
signal metal makes a region under a stripe read as a routing hotspot.
"""
from __future__ import annotations

import gc
import json
import logging
import os
import time
from typing import AnyStr, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from . import config
from .assembly import Frame, HierarchyAssembler, find_single_top
from .loader import load_block, load_cell_info
from .parsers import Cancelled
from .parsers.convert import cell_info_from_lef, instance_info_from_def
from .parsers.routing import (POWER, SIGNAL, RouteLayer, ShapeStream, TechRouting, parse_def)
from .raster import Bins

logger = logging.getLogger(__name__)

# What a shape's scope can be, and what the view asks for.
SCOPE_SIGNAL = "signal"
SCOPE_POWER = "power"
SCOPE_ALL = "all"

SCOPES = (SCOPE_ALL, SCOPE_SIGNAL, SCOPE_POWER)

# How much of a macro's own footprint its obstructions have to cover, together, before they
# count as blockage. A fraction rather than an absolute area, so it means the same thing on a
# 130 nm SRAM and a 7 nm one: the alternative drops a block area that a compiler wrote as
# tiles, and keeps pin-access bites that are not keep-outs.
OBS_MIN_FOOTPRINT_FRACTION = 0.10

# Gaps below this, between obstruction shapes on one layer, are closed before that judgement.
# A tessellated blockage separated by less than a track pitch is one region, not a field of
# islands: every routing layer of every PDK measured here has a pitch above 0.14 um.
OBS_CLOSE_UM = 0.1


class GcMonitor:
    """Time inside the collector, and collections per generation.

    Worth measuring rather than assuming, because the cost is invisible where it happens: a
    live set of millions of objects - one power net held whole, every component of a flat
    design - makes each gen-2 collection walk all of it, and the walk is attributed to
    whichever code happened to be allocating when it fired.
    """

    def __init__(self):
        self.seconds = 0.0
        self.counts = [0, 0, 0]
        self._started = None
        gc.callbacks.append(self)

    def __call__(self, phase, info):
        if phase == "start":
            self._started = time.perf_counter()
        else:
            self.seconds += time.perf_counter() - self._started
            self.counts[info["generation"]] += 1

    def close(self) -> None:
        gc.callbacks.remove(self)


def resident_mb():
    """(resident, peak) megabytes, or (None, None) where the OS will not say.

    /proc first, because the runs that matter are on Linux and it is where the request's
    memory limit bites; psutil only if it happens to be installed, since it is not a
    dependency.
    """
    try:
        with open("/proc/self/status") as handle:
            found = {line.split(":")[0]: line.split()[1] for line in handle
                     if line.startswith(("VmRSS", "VmHWM"))}
        return int(found["VmRSS"]) / 1024, int(found["VmHWM"]) / 1024
    except (OSError, KeyError, IndexError):
        pass
    try:
        import psutil
        info = psutil.Process().memory_info()
        return info.rss / 1e6, getattr(info, "peak_wset", info.rss) / 1e6
    except Exception:                                   # noqa: BLE001 - best effort only
        return None, None


class Stages:
    """Per-stage seconds, logged as each stage closes.

    A run used to have exactly one elapsed number - the parser's own "End DEF parsing in
    7005s" - which covers parsing, conversion and rasterisation together and so cannot say
    where the time went. One line per stage is what makes a real run diagnosable from its log
    alone, which is the only thing available when the design cannot be handed over.
    """

    def __init__(self):
        self.seconds: Dict[AnyStr, float] = {}
        self.gc = GcMonitor()
        self._name = "start"
        self._started = time.perf_counter()

    def mark(self, name: AnyStr, detail: AnyStr = "") -> None:
        """Close the open stage, report it, and open ``name``.

        ``detail`` describes the stage being *closed* - its elapsed time and what it
        produced belong on the same line - so a call reads "open this, and here is what the
        last one did".
        """
        now = time.perf_counter()
        elapsed = now - self._started
        self.seconds[self._name] = self.seconds.get(self._name, 0.0) + elapsed
        resident = resident_mb()[0]
        logger.info("metal: stage %-17s %9.2fs  %s%s", self._name, elapsed, detail,
                    "" if resident is None else f"  rss {resident:,.0f} MB")
        self._name, self._started = name, now

    def close(self) -> Dict[AnyStr, float]:
        self.mark("done")
        self.seconds.pop("done", None)
        self.gc.close()
        return self.seconds


class MetalData:
    """Per-layer routing utilisation, ready to render.

    Duck-types the parts of :class:`~vlsi_viewer.physical.PhysicalData` that
    :class:`~vlsi_viewer.ui_layout.LayoutView` uses - ``extent``, ``grid_size``, ``rows``,
    ``cols``, ``boundary_polys`` and ``heat(kind)`` - so the existing view drives it with no
    special casing. Unlike the physical grids it composes on demand, because a metal map has
    state (which layers, which scope) that a plain array lookup cannot carry.
    """

    def __init__(self, top_name, boundary_polys, grid_size, extent, rows, cols,
                 layers: Sequence[RouteLayer], capacity_base,
                 blocked: Dict[int, np.ndarray], macro_block_layers: int,
                 grids: Dict[Tuple[int, str], np.ndarray], warnings: List[AnyStr],
                 blockage: Dict = None, totals: Dict = None):
        self.top_name = top_name
        self.boundary_polys = boundary_polys
        self.grid_size = float(grid_size)
        self.extent = extent
        self.rows = int(rows)
        self.cols = int(cols)
        self.layers = list(layers)
        self.macro_block_layers = int(macro_block_layers)
        self.warnings = list(warnings)
        # How the blockage was decided - which macros declared OBS, which fell back to the
        # layer count. The readout reports it, because the two are not equally trustworthy.
        self.blockage = dict(blockage or {})
        # What the stream dropped and why: vias, jogs, unknown layers, degenerate shapes,
        # polygon edges. The warnings say it in prose; this is the same thing a caller can
        # read, for a summary line or a benchmark.
        self.totals = dict(totals or {})
        self._capacity_base = np.asarray(capacity_base, dtype=np.float64)
        self._grids = grids                    # (layer index, scope) -> inflated area
        self._scope = SCOPE_ALL
        self._cache: Dict[Tuple[str, str], np.ndarray] = {}
        # Routable area per layer, computed once. A macro can block a non-contiguous set of
        # layers - its OBS names them - so there is no "bottom layers" pair to switch between;
        # a layer with no entry keeps the whole die. Precomputed rather than derived in
        # `_routable`, which is called per layer by `heat` and per pixel by `cell_detail`.
        self._routable: Dict[int, np.ndarray] = {
            int(index): np.clip(self._capacity_base - area, 0.0, None)
            for index, area in blocked.items()}

    # -- geometry --------------------------------------------------------------------

    @property
    def routable_top(self) -> np.ndarray:
        """The die's own area per cell, before any macro takes a bite out of it."""
        return self._capacity_base

    @property
    def blocked_layers(self) -> List[int]:
        """Layer indices some macro blocks. Empty when no macro blocks anything."""
        return sorted(self._routable)

    @property
    def horizontal(self) -> List[RouteLayer]:
        return [layer for layer in self.layers if layer.is_horizontal]

    @property
    def vertical(self) -> List[RouteLayer]:
        return [layer for layer in self.layers if not layer.is_horizontal]

    @property
    def scope(self) -> str:
        return self._scope

    def set_scope(self, scope: AnyStr) -> None:
        if scope not in SCOPES:
            raise ValueError(f"unknown scope {scope!r}; expected one of {SCOPES}")
        if scope != self._scope:
            self._scope = scope
            self._cache = {}

    def _routable_area(self, layer: RouteLayer) -> np.ndarray:
        """The layer's routable area per cell: the die, less whatever a macro blocks there."""
        return self._routable.get(int(layer.index), self._capacity_base)

    def capacity(self, layer: RouteLayer) -> np.ndarray:
        """Available routing resource per cell, in the same units as the consumed area."""
        factor = self.pitch_factor(layer)
        return self._routable_area(layer) * factor

    @staticmethod
    def pitch_factor(layer: RouteLayer) -> float:
        """``(W + S) / P`` - the share of a cell that is usable metal-plus-spacing.

        1.0 when the layer's pitch is exactly its width plus its spacing, which is the usual
        case; below 1.0 the layer's tracks are further apart than their rules require, and
        without this the same wiring would read as less congested than it is.

        Public because the layer table reports it: the GUI has no business re-deriving the
        formula, or its tooltip would drift from the number the map is drawn from.
        """
        if layer.pitch <= 0:
            return 1.0
        return (layer.width + layer.spacing) / layer.pitch

    def _consumed(self, layer: RouteLayer, scope: AnyStr):
        """Inflated area consumed on one layer, or None if it carries nothing.

        None rather than a zeros grid, because a design has a grid only for the layers and
        scopes it actually uses and allocating the rest would cost more than the metric.
        """
        if scope == SCOPE_ALL:
            # Keyed by the scope *strings*, the same as `_GridSink.grids()` uses. Looking
            # these up with the routing module's integer SIGNAL/POWER constants silently
            # matched nothing, which left the default scope drawing an empty map.
            signal = self._grids.get((layer.index, SCOPE_SIGNAL))
            power = self._grids.get((layer.index, SCOPE_POWER))
            if signal is None:
                return power
            if power is None:
                return signal
            return signal + power
        key = (layer.index, SCOPE_SIGNAL if scope == SCOPE_SIGNAL else SCOPE_POWER)
        return self._grids.get(key)

    def layer_util(self, layer: RouteLayer) -> float:
        """Mean utilisation of one layer, for the panel's per-layer readout."""
        consumed = self._consumed(layer, self._scope)
        if consumed is None:
            return 0.0
        capacity = self.capacity(layer)
        live = capacity > 0
        if not live.any():
            return 0.0
        return float(np.clip(consumed[live] / capacity[live], 0.0, 1.0).mean())

    # -- composition -----------------------------------------------------------------

    def kinds(self) -> List[Tuple[str, str]]:
        """``(kind, label)`` for the map selector, one entry per layer, bottom to top.

        The layer panel builds its own group kinds from the checkboxes; this is what the
        combo shows when nothing is grouped.
        """
        return [(self.layer_kind(layer),
                 f"{layer.name} {'H' if layer.is_horizontal else 'V'}")
                for layer in self.layers]

    @staticmethod
    def layer_kind(layer: RouteLayer) -> str:
        return f"L:{layer.name}"

    @staticmethod
    def group_kind(names: Sequence[AnyStr]) -> str:
        """A canonical group kind: sorted by name, so the cache key is stable."""
        return "G:" + ",".join(sorted(names))

    def layers_of(self, kind: AnyStr) -> List[RouteLayer]:
        """The layers a kind selects. An unknown layer name selects nothing, not everything."""
        if kind.startswith("L:"):
            name = kind[2:]
            return [layer for layer in self.layers if layer.name == name]
        if kind.startswith("G:"):
            names = set(kind[2:].split(","))
            return [layer for layer in self.layers if layer.name in names]
        raise ValueError(f"unsupported map kind {kind!r}")

    def heat(self, kind: AnyStr) -> np.ndarray:
        """The composed map for ``kind``, at the current scope.

        Never NaN: ``heatmap.grid_to_image`` has no NaN handling, and a NaN propagates into
        the colour lookup and paints garbage. A cell with no routable area - entirely under a
        macro, on a blocked layer - reads 0.0, which renders as "nothing routable here".
        """
        cache_key = (kind, self._scope)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        layers = self.layers_of(kind)
        consumed = np.zeros((self.rows, self.cols), dtype=np.float64)
        capacity = np.zeros((self.rows, self.cols), dtype=np.float64)
        for layer in layers:
            layer_consumed = self._consumed(layer, self._scope)
            if layer_consumed is not None:
                consumed += layer_consumed
            capacity += self.capacity(layer)
        with np.errstate(divide="ignore", invalid="ignore"):
            out = np.divide(consumed, capacity, out=np.zeros_like(consumed),
                            where=capacity > 0)
        out = np.clip(out, 0.0, 1.0).astype(np.float32)
        self._cache[cache_key] = out
        return out

    def max_util(self, kind: AnyStr) -> float:
        grid = self.heat(kind)
        return float(grid.max()) if grid.size else 0.0

    def mean_util(self, kind: AnyStr) -> float:
        """Mean over cells that have any capacity - the rest would dilute it.

        "Any capacity" is deliberately the same test the map uses. A cell a macro leaves a
        sliver of is a hot cell on the map - a small denominator and real metal on top of it -
        so excluding it here would make the summary disagree with the picture.
        """
        layers = self.layers_of(kind)
        if not layers:
            return 0.0
        routable = sum(self._routable_area(layer) > 0 for layer in layers) > 0
        grid = self.heat(kind)
        return float(grid[routable].mean()) if routable.any() else 0.0

    def cell_detail(self, ix: int, iy: int, kind: AnyStr) -> dict:
        """Everything behind one pixel, for the readout that makes the map checkable.

        Reports ``D``, ``C`` and ``U`` per selected layer plus the group's ``sum(D)/sum(C)``,
        so a user can confirm the colour they see is the arithmetic they expect rather than
        taking the ramp on trust.
        """
        if not (0 <= ix < self.cols and 0 <= iy < self.rows):
            raise IndexError(f"cell ({ix}, {iy}) is outside the {self.rows}x{self.cols} grid")
        per_layer = []
        total_d = total_c = 0.0
        for layer in self.layers_of(kind):
            consumed_grid = self._consumed(layer, self._scope)
            consumed = 0.0 if consumed_grid is None else float(consumed_grid[iy, ix])
            capacity = float(self.capacity(layer)[iy, ix])
            total_d += consumed
            total_c += capacity
            per_layer.append({
                "name": layer.name,
                "direction": "H" if layer.is_horizontal else "V",
                "consumed": consumed,
                "capacity": capacity,
                "util": (consumed / capacity) if capacity > 0 else 0.0,
                "pitch_factor": self.pitch_factor(layer),
            })
        return {
            "ix": ix, "iy": iy,
            "x": self.extent[0] + (ix + 0.5) * self.grid_size,
            "y": self.extent[1] + (iy + 0.5) * self.grid_size,
            "layers": per_layer,
            "consumed": total_d,
            "capacity": total_c,
            "util": min(1.0, total_d / total_c) if total_c > 0 else 0.0,
            "scope": self._scope,
            "macro_block_layers": self.macro_block_layers,
        }

    def __repr__(self):
        return (f"MetalData(top={self.top_name!r}, {self.rows}x{self.cols} @ "
                f"{self.grid_size:g}um, {len(self.layers)} layers)")


class _GridSink:
    """Collects the stream's shapes into one :class:`~vlsi_viewer.raster.Bins` per layer.

    One bin accumulator per (layer, scope) pair, created on first use: a design that puts no
    metal on a layer does not pay for its grid, and most designs use power on only the bottom
    few layers.
    """

    def __init__(self, extent, grid_size):
        self.extent = extent
        self.grid_size = grid_size
        self._bins: Dict[Tuple[int, int], Bins] = {}
        self.n_polygons = 0
        self.n_diagonals = 0

    def _bins_for(self, layer_index, scope) -> Bins:
        key = (layer_index, scope)
        bins = self._bins.get(key)
        if bins is None:
            bins = self._bins[key] = Bins(self.extent, self.grid_size)
        return bins

    def add_rects(self, layer_index, scope, x0, y0, x1, y1) -> None:
        self._bins_for(layer_index, scope).add_rects(x0, y0, x1, y1)

    def add_diagonal(self, layer_index, scope, x0, y0, x1, y1, half_width) -> None:
        self.n_diagonals += 1
        self._bins_for(layer_index, scope).add_segment(x0, y0, x1, y1, half_width)

    def add_polygon(self, layer_index, scope, ring) -> None:
        self.n_polygons += 1
        self._bins_for(layer_index, scope).add_polygon(ring)

    def grids(self) -> Dict[Tuple[int, str], np.ndarray]:
        named = {}
        for (layer_index, scope), bins in self._bins.items():
            named[(layer_index, SCOPE_SIGNAL if scope == SIGNAL else SCOPE_POWER)] = \
                bins.grid()
        return named


def build_metal(def_paths: Sequence[AnyStr], lef_paths: Sequence[AnyStr],
                tech_paths: Sequence[AnyStr], grid_size: float = None,
                macro_block_layers: int = None, min_segment=None,
                top: AnyStr = None, on_progress=None, cancel=None) -> MetalData:
    """Build the per-layer utilisation grids for a DEF hierarchy.

    The DEFs are read twice, deliberately. The first pass takes only the components and the
    boundary - which is all the parser reads by default, so it stops at ``END COMPONENTS``
    and costs little - and yields the block table. The second pass knows each block's global
    frame and can therefore stream its wiring straight into the accumulating grids without
    ever holding the geometry. Reading once would mean buffering every segment, which at 10^8
    segments is gigabytes.

    ``cancel`` is an optional callable consulted during the wiring pass; when it returns True
    the build stops and returns what it has measured, with a warning saying so. A chip-level
    build runs for hours, and the useful answer to "this input was wrong" is a partial map in
    seconds rather than a killed job.
    """
    grid_size = config.DEFAULT_METAL_GRID_SIZE if grid_size is None else float(grid_size)
    if macro_block_layers is None:
        macro_block_layers = config.DEFAULT_MACRO_BLOCK_LAYERS
    if grid_size <= 0:
        raise ValueError("grid size must be > 0")

    def progress(message):
        if on_progress is not None:
            on_progress(message)

    stages = Stages()
    stages.mark("tech-lef")
    tech = TechRouting.read(tech_paths)
    if not tech.layers:
        raise ValueError("the tech LEF declares no TYPE ROUTING layers; there is nothing "
                         "to measure")

    # Pass 1: block table, so every block's frame is known before any wiring is streamed.
    stages.mark("components")
    progress("reading block outlines")
    blocks: Dict[AnyStr, tuple] = {}
    path_of_block: Dict[AnyStr, AnyStr] = {}
    for path in def_paths:
        data = instance_info_from_def(path, top)
        name, instances, boundary = load_block(data)
        # `data` is the decoded DEF and `instances` the block it was turned into; only the
        # latter outlives this line, and holding both is holding a whole DEF twice.
        del data
        if name in blocks:
            logger.warning("two DEFs define a block named %r; the later one is ignored",
                           name)
            continue
        blocks[name] = (instances, boundary)
        path_of_block[name] = path
    if not blocks:
        raise ValueError("no DEF was readable")

    root = top if (top in blocks) else find_single_top(blocks)
    stages.mark("cell-index", f"{len(blocks)} block(s), root {root!r}")
    # One cell-table lookup for the whole build. It used to be read twice - once here and
    # again inside the blockage measurement - which parsed the macro LEF twice over.
    cells = _indexed_cells(lef_paths)
    assembler = HierarchyAssembler(blocks, cells)

    boundary_points = blocks[root][1]
    if boundary_points is None:
        raise ValueError("metal mode requires a 'boundary' on the top-level block")
    xs = [point[0] for point in boundary_points]
    ys = [point[1] for point in boundary_points]
    extent = (min(xs), min(ys), max(xs), max(ys))
    cols = max(1, int(np.ceil((extent[2] - extent[0]) / grid_size)))
    rows = max(1, int(np.ceil((extent[3] - extent[1]) / grid_size)))

    # Capacity: the die's own area per cell, then the macro footprint removed from the
    # layers macros block. Both are the rasteriser's job - it already does exact per-bin
    # clipping, and reusing it keeps one definition of "area in this cell".
    stages.mark("capacity", f"{0 if cells is None else len(cells):,} cell(s) from "
                            f"{len(lef_paths)} LEF file(s)")
    progress("measuring capacity")
    die = Bins(extent, grid_size)
    die.add_polygon([(float(x), float(y)) for x, y in boundary_points])
    capacity_base = die.grid(dtype="float64")

    warnings: List[AnyStr] = []
    stages.mark("blockage", f"{rows} x {cols} grid @ {grid_size:g} um, die "
                            f"{extent[2] - extent[0]:.1f} x {extent[3] - extent[1]:.1f} um")
    try:
        obstructions = _macro_obstructions(lef_paths)
    except Exception as exc:                            # pragma: no cover - defensive
        warnings.append(f"could not read the macro LEF's obstructions ({exc}); macros that "
                        f"cannot be measured block their bottom layers instead")
        obstructions = {}
    blocked, blockage = _macro_blockage(assembler, blocks, cells, obstructions, tech, extent,
                                        grid_size, root, macro_block_layers, warnings)

    if rows * cols > config.DEFAULT_METAL_MAX_BINS:
        warnings.append(
            f"the grid is {rows} x {cols} = {rows * cols:,} cells, above the "
            f"{config.DEFAULT_METAL_MAX_BINS:,} this is tuned for; expect roughly "
            f"{rows * cols * 4 / 1e6:.0f} MB per layer. A coarser --grid-size would fit "
            f"this design in about {np.sqrt(rows * cols / config.DEFAULT_METAL_MAX_BINS):.1f}x "
            f"less memory")

    # Pass 2: stream each block's wiring through its frame.
    stages.mark("routing", f"{len(blockage)} macro type(s) with obstruction data")
    sink = _GridSink(extent, grid_size)
    totals = {"emitted": 0, "vias": 0, "jogs": 0, "unknown": 0, "unusable": 0,
              "degenerate": 0, "polygon_edges": 0}
    # Summed over blocks: what the DEFs were like, as opposed to what came out of them.
    text_stats: Dict[AnyStr, object] = {"forms": 0, "points": 0, "lines": 0,
                                        "statement_lines_max": 0, "statement_chars_max": 0,
                                        "points_max": 0, "layers_used": set()}

    def on_block(name, frame: Frame) -> None:
        path = path_of_block.get(name)
        if path is None:
            # A block we can see but have no DEF for: its wires cannot be measured. Said
            # once, because silently omitting a whole sub-block's routing is the kind of
            # thing nobody notices in a picture.
            warnings.append(f"block {name!r} is instantiated but no DEF defines it; its "
                            f"wiring is not counted")
            return
        progress(f"reading routing in {name}")
        stream = ShapeStream(tech, sink, frame=frame, min_segment=min_segment)
        # The components were read in pass 1; this pass wants the wiring, and re-building
        # three million DefComponents that nothing reads costs memory for nothing.
        routing = parse_def(path, stream=stream, skip_components=True, cancel=cancel)
        stream.flush()
        for key, attribute in (("emitted", "n_emitted"), ("vias", "n_via"),
                               ("jogs", "n_jog"), ("unknown", "n_unknown_layer"),
                               ("unusable", "n_usable_layer_missing"),
                               ("degenerate", "n_degenerate"),
                               ("polygon_edges", "n_polygon_edge")):
            totals[key] += getattr(stream, attribute)
        stats = routing.stats
        text_stats["forms"] += stats.get("forms", 0)
        text_stats["points"] += stats.get("points", 0)
        text_stats["lines"] += stats.get("lines", 0)
        for key in ("statement_lines_max", "statement_chars_max", "points_max"):
            text_stats[key] = max(text_stats[key], stats.get(key, 0))
        text_stats["layers_used"] |= set(stats.get("layers_used", ()))
        if routing.ndrs:
            logger.info("%s: %d non-default rule(s)", name, len(routing.ndrs))

    progress("reading routing")
    try:
        assembler.walk(root, on_block)
    except Cancelled as stopped:
        # Not a failure: the grids hold everything read up to the interrupt, and saying so is
        # what keeps a partial map from being mistaken for a complete one.
        warnings.append(f"stopped early on request ({stopped}); the map covers only the "
                        f"wiring that had been read")
        logger.warning("metal: %s", warnings[-1])
    if assembler.missing:
        missing = sorted(set(assembler.missing))
        warnings.append(f"{len(missing)} cell type(s) are neither in the LEF nor a block, "
                        f"so they contribute no footprint: {', '.join(missing[:5])}"
                        + (" ..." if len(missing) > 5 else ""))

    if not tech.usable:
        warnings.append("no routing layer in the tech LEF has a usable width")

    shapes = totals["emitted"] + sum(value for key, value in totals.items()
                                     if key != "emitted")
    stages.mark("grids", f"{shapes:,} shape(s), {text_stats['points']:,} point(s)")

    # Metal where there is said to be no room. Either the DEF routes over a macro - which a
    # real design does not do on the layers that macro blocks - or the model is over-blocking.
    # Either way those cells' numbers mean nothing, and silently reporting them as congestion
    # would be the wrong answer.
    grids = sink.grids()
    stranded = _stranded_cells(capacity_base, blocked, grids)
    if stranded:
        warnings.append(
            f"{stranded} cell(s) carry signal wire on a layer a macro obstructs there, so "
            f"their utilisation is not a congestion reading")

    stage_seconds = stages.close()
    _describe(totals, warnings)

    # One machine-readable line for the whole run. Its point is that the evidence can be
    # carried back without the design: what was measured, how the time split, what the input
    # was like, and where the memory went. The fields a synthetic benchmark has to be checked
    # against - statement sizes, points per form, the layer names - are the ones a DEF's own
    # header does not carry.
    resident, peak = resident_mb()
    logger.info("metal-summary: %s", json.dumps({
        "design": root,
        "grid": [rows, cols],
        "grid_size_um": grid_size,
        "die_um": [round(extent[2] - extent[0], 3), round(extent[3] - extent[1], 3)],
        "params": {"min_segment": min_segment, "macro_block_layers": macro_block_layers,
                   "top": top},
        "inputs": {"defs": [_file_note(path) for path in def_paths],
                   "lefs": len(lef_paths),
                   "tech_lefs": [_file_note(path) for path in tech_paths]},
        "stages_s": {name: round(seconds, 2) for name, seconds in stage_seconds.items()},
        "shapes": dict(totals, total=shapes),
        "input_text": dict(text_stats, layers_used=len(text_stats["layers_used"])),
        "layers_not_in_tech": sorted(set(text_stats["layers_used"]) -
                                     {layer.name for layer in tech.layers}),
        "layers": [{"name": layer.name, "direction": layer.direction,
                    "width_um": layer.width, "pitch_um": layer.pitch,
                    "usable": layer.usable} for layer in tech.layers],
        "blockage": blockage,
        "gc_s": round(stages.gc.seconds, 2),
        "gc_counts": stages.gc.counts,
        "rss_mb": None if resident is None else round(resident),
        "peak_rss_mb": None if peak is None else round(peak),
        "warnings": warnings,
    }, sort_keys=True, default=str))
    return MetalData(root, _boundary_polys(assembler, blocks, root), grid_size, extent, rows,
                     cols, tech.layers, capacity_base, blocked, macro_block_layers,
                     grids, warnings, blockage, totals)


def _file_note(path) -> Dict:
    """Path, bytes and mtime - enough to say which file a result came from."""
    try:
        info = os.stat(path)
        return {"path": str(path), "mb": round(info.st_size / 1e6, 1),
                "mtime": int(info.st_mtime)}
    except OSError:
        return {"path": str(path)}


def _indexed_cells(lef_paths):
    """The cell library keyed by cell name, or None.

    ``load_cell_info`` leaves a RangeIndex and keeps the name in a column, so it has to be
    re-keyed before it can be looked up by name. That re-keying lives in
    ``physical._load_blocks_and_cells`` rather than in the loader, which is easy to miss and
    fails silently: every lookup returns None, so macros simply vanish from the capacity.
    """
    if not lef_paths:
        return None
    from .parsers.convert import cell_info_from_lef
    return load_cell_info(cell_info_from_lef(lef_paths)).set_index("cell_name")


def _macro_obstructions(lef_paths) -> Dict[AnyStr, Dict[AnyStr, list]]:
    """Each hard macro's ``OBS`` geometry, straight from the macro LEF.

    ``{cell_name: {layer_name: [(x0, y0, x1, y1), ...]}}`` in the macro's own coordinates.
    Only cells whose ``CLASS`` is not ``CORE`` are included: a standard cell's obstructions
    are where its own pins may not be approached, a few percent of a cell that is not a
    keep-out region, and treating them as blockage would subtract scattered slivers from
    every layer they touch.

    A cell with no ``OBS`` is absent from the mapping rather than present with an empty one -
    the caller has to be able to tell "declares nothing" (fall back to a guess) from "declares
    geometry" (trust it).
    """
    if not lef_paths:
        return {}
    from .parsers.LEF import LefParser
    from .parsers.convert import is_macro_class

    obstructions = {}
    for name, macro in LefParser(list(lef_paths)).getMacros().items():
        if not is_macro_class(macro.macroClass()):
            continue
        declared = macro.obstructions()
        if declared:
            obstructions[name] = declared
    return obstructions


def _obs_blockage(rects, size, warnings, name) -> list:
    """The part of one layer's obstruction geometry worth calling a blockage.

    A macro's ``OBS`` often carries small shapes - pin-access bites, tie-off holes - beside
    the region that really is blocked. What matters is whether the obstructions *together*
    cover a meaningful part of the macro: a scatter of bites across a tenth of one percent of
    a 40 x 20 um SRAM is not a keep-out, while a tessellated block area, which can arrive as
    dozens of rectangles each smaller than the threshold, absolutely is. So the judgement is
    on the union, and the geometry rasterised is the rectangles it was built from.

    The union is closed by a small epsilon first. A blockage written as a field of tiles with
    sub-epsilon gaps between them is one region; at 0.1 um the gap is below the track pitch of
    every layer of every PDK this has seen, so it is a tessellation artifact rather than a
    routable channel.
    """
    footprint = float(size[0]) * float(size[1])
    if footprint <= 0 or not rects:
        return []
    from shapely.geometry import box
    from shapely.ops import unary_union

    outer = box(0.0, 0.0, float(size[0]), float(size[1]))
    shapes = [box(*rect) for rect in rects]
    try:
        merged = unary_union(shapes)
    except Exception:                                   # pragma: no cover - defensive
        try:
            merged = unary_union([shape.buffer(0) for shape in shapes])
        except Exception:
            # Rather than drop a real blockage because shapely would not read it, keep all of
            # it: over-blocking is the safe direction for a congestion reading.
            warnings.append(f"{name}: could not merge its obstruction geometry; every "
                            f"rectangle is counted")
            return list(rects)
    merged = merged.buffer(OBS_CLOSE_UM, join_style=2).buffer(-OBS_CLOSE_UM, join_style=2)
    merged = merged.intersection(outer)                 # a macro cannot block more than itself
    if merged.is_empty or merged.area < OBS_MIN_FOOTPRINT_FRACTION * footprint:
        return []
    return list(rects)


def _macro_blockage(assembler, blocks, cells, obstructions, tech, extent, grid_size, root,
                    macro_block_layers, warnings) -> Dict[int, np.ndarray]:
    """Blocked area per cell, per layer, in global coordinates.

    Two sources, deliberately distinguishable. A macro that declares ``OBS`` blocks what its
    obstructions cover, on the layers they name - which may be any set of layers, contiguous
    or not. A macro that declares none cannot be judged from data at all, so it falls back to
    ``macro_block_layers`` whole-die-footprint layers from the bottom, and says so.

    The instance's own orientation is composed with its block's frame, so the blockage lands
    where the cell's geometry actually is. That is the same transform the *wiring* goes
    through (`Frame.compose`, both of them), which is what matters here: an obstruction that
    does not sit exactly where the wires the DEF placed around it are is worse than no model
    at all.
    """
    if cells is None:
        return {}, {}
    macros = cells[(cells["size_x"] > 0) & (cells["size_y"] > 0)]
    macros = macros[macros["is_macro"]]
    if macros.empty:
        return {}, {}

    index_of = {layer.name: int(layer.index) for layer in tech.layers}
    usable = {layer.name for layer in tech.usable}
    unknown = {}
    ignored = {}
    no_obs = 0
    nothing_left = []

    # What each macro blocks, decided once per cell type rather than per placement.
    plan: Dict[AnyStr, Dict[int, list]] = {}
    for name in macros.index:
        declared = obstructions.get(name)
        if not declared:
            no_obs += 1
            continue
        size = (float(macros.at[name, "size_x"]), float(macros.at[name, "size_y"]))
        layers = {}
        for layer_name, rects in declared.items():
            index = index_of.get(layer_name)
            if index is None or layer_name not in usable:
                unknown[layer_name] = unknown.get(layer_name, 0) + 1
                continue
            kept = _obs_blockage(rects, size, warnings, name)
            if kept:
                layers[index] = kept
            else:
                ignored[layer_name] = ignored.get(layer_name, 0) + 1
        # Recorded even when empty: a macro that declared obstructions and had them judged
        # negligible blocks nothing, which is a different answer from a macro that declared
        # none and has to be guessed at. Absent from `plan` must mean "no OBS at all".
        plan[name] = layers
        if not layers:
            nothing_left.append(name)

    # How the blockage was decided, for whoever has to judge the numbers. `logger.info`
    # rather than a user-facing warning: a macro with no OBS is not suspect *data*, it is the
    # case `--macro-block-layers` exists for, and the map is as good as that flag allows.
    summary = {"obs_cells": len(plan), "obs_layers": sorted({index for layers in plan.values()
                                                             for index in layers}),
               "fallback_cells": no_obs, "fallback_layers": macro_block_layers,
               "ignored_cells": sorted(nothing_left), "ignored_layers": dict(ignored),
               "unknown_layers": dict(unknown)}
    if ignored:
        logger.info("metal: obstruction geometry on %d layer(s) was too small a part of its "
                    "macro to count as blockage: %s", len(ignored),
                    ", ".join(sorted(ignored)))
    logger.info("metal: blockage from %d macro(s) declaring OBS over %d layer(s); %d fall "
                "back to the bottom %d layer(s); %d declare nothing significant",
                summary["obs_cells"], len(summary["obs_layers"]), no_obs, macro_block_layers,
                len(nothing_left))
    if unknown:
        logger.info("metal: %d obstruction layer(s) are not in the tech LEF and are not "
                    "counted: %s", len(unknown), ", ".join(sorted(unknown)))

    bins: Dict[int, Bins] = {}
    if no_obs and macro_block_layers > 0:
        for layer in tech.layers[:macro_block_layers]:
            bins[layer.index] = Bins(extent, grid_size)

    def bin_for(layer_index):
        if layer_index not in bins:
            bins[layer_index] = Bins(extent, grid_size)
        return bins[layer_index]

    def on_block(name, frame: Frame) -> None:
        instances = assembler.instances(name)
        if instances is None or instances.empty:
            return
        rows = instances[instances["cell_name"].isin(macros.index)]
        if rows.empty:
            return
        x = rows["location_x"].to_numpy(dtype=np.float64)
        y = rows["location_y"].to_numpy(dtype=np.float64)
        kinds = rows["cell_name"].to_numpy()
        orientations = rows["orient"].fillna("N").astype(str).to_numpy()
        for cell_name in pd.unique(kinds):
            picked_cell = kinds == cell_name
            size = (float(macros.at[cell_name, "size_x"]),
                    float(macros.at[cell_name, "size_y"]))
            by_layer = plan.get(cell_name)
            for orientation in pd.unique(orientations[picked_cell]):
                picked = picked_cell & (orientations == orientation)
                # A macro-local point goes through the cell's orientation, then its placement,
                # then the block's frame:
                #     p_global = M_block (M_orient p + loc) + t_block
                # so the matrix mapping obstruction geometry is M_block M_orient, and the
                # offset is M_block loc + t_block. Subtle, and only visible on a rotated cell:
                # applying the *composed* matrix to the location as well would put the
                # obstruction where a second rotation of the placement says, not where the
                # cell is.
                (a, b), (c, d) = frame.compose(str(orientation), (0.0, 0.0)).matrix
                (ea, eb), (ec, ed) = frame.matrix
                tx = ea * x[picked] + eb * y[picked] + frame.origin[0]
                ty = ec * x[picked] + ed * y[picked] + frame.origin[1]
                if by_layer is None:
                    # Nothing declared, so nothing to trust: the cell's whole footprint, on
                    # the bottom `macro_block_layers` layers.
                    if macro_block_layers <= 0:
                        continue
                    for layer in tech.layers[:macro_block_layers]:
                        _emit(bin_for(layer.index), a, b, c, d, tx, ty,
                              0.0, 0.0, size[0], size[1])
                    continue
                for layer_index, rects in by_layer.items():
                    target = bin_for(layer_index)
                    for rect in rects:
                        _emit(target, a, b, c, d, tx, ty, *rect)

    assembler.walk(root, on_block)
    return ({index: blocked.grid(dtype="float32") for index, blocked in bins.items()},
            summary)


def _emit(bins, a, b, c, d, tx, ty, rx0, ry0, rx1, ry1) -> None:
    """Rasterise one macro-local rectangle across a whole group of placed instances.

    The four corners are the composed transform's four expressions, kept inline rather than
    going through ``Frame.apply_rect`` so that a *group* can be emitted in one call: an
    obstruction is a rectangle offset inside the macro, which the old extents-swap shortcut
    could not express at all, and doing it per instance would be one call per placement per
    rectangle per layer.
    """
    ax, ay = a * rx0 + b * ry0 + tx, c * rx0 + d * ry0 + ty
    bx, by = a * rx1 + b * ry1 + tx, c * rx1 + d * ry1 + ty
    bins.add_rects(np.minimum(ax, bx), np.minimum(ay, by),
                   np.maximum(ax, bx), np.maximum(ay, by))


def _stranded_cells(capacity_base, blocked, grids) -> int:
    """Cells where a layer a macro obstructs carries signal wire anyway.

    Wire drawn where the model says there is no room is real metal, so counting it is the
    honest thing and hiding it would defeat the purpose - but the ratio in those cells is not
    a congestion reading, so it is worth saying so. There is no `macro_block_layers` test
    here: obstruction-derived blocking is independent of that flag, which only governs the
    fallback for macros that declare nothing.

    Only *signal* metal counts. Power rails run straight through a macro - the macro's own
    power connects to them - so a followpin on M1 crossing an SRAM is ordinary, not stranded.
    """
    stranded = np.zeros(capacity_base.shape, dtype=bool)
    for (layer_index, scope), grid in grids.items():
        if scope != SCOPE_SIGNAL:
            continue
        area = blocked.get(int(layer_index))
        if area is None:
            continue
        no_room = np.clip(capacity_base - area, 0.0, None) <= 0
        if no_room.any():
            stranded |= (grid > 0) & no_room
    return int(stranded.sum())


def _boundary_polys(assembler, blocks, root):
    """Every block's outline, in **global** coordinates.

    A sub-block's boundary is written in its own frame, exactly as its wiring is, so it has
    to go through the same placement. Returning it raw - which this did - draws the outline
    at the origin instead of where the block sits, and a block placed four times shows one
    rectangle in the wrong corner. ``physical.py`` maps them the same way.
    """
    polygons = []

    def on_block(name, frame: Frame) -> None:
        # The walk visits every instance, including leaf cells that are not blocks and have
        # no DEF of their own - `_macro_area` gets away with indexing `instances` because it
        # has a LEF to look in, but `blocks` would raise here.
        entry = blocks.get(name)
        if entry is None or not entry[1]:
            return
        # Vertex by vertex, so a rectilinear outline stays rectilinear rather than collapsing
        # to its bounding box. The top block's frame is the identity, so this is a no-op for
        # the die itself.
        polygons.append((name, [(float(x), float(y)) for x, y in
                                (frame.apply_point(*point) for point in entry[1])]))

    assembler.walk(root, on_block)
    return polygons


def _describe(totals, warnings):
    """Turn the conversion counters into the one-line notes a user should see."""
    # Reported first, because it is the number the rest are relative to: without it a log
    # saying "147 M shapes dropped" leaves everything else in the run unaccounted for.
    if totals["emitted"]:
        logger.info("metal: %d shape(s) measured and handed to the rasteriser",
                    totals["emitted"])
    if totals["vias"]:
        logger.info("metal: %d via point(s) omitted (no wire area)", totals["vias"])
    if totals["jogs"]:
        logger.info("metal: %d non-preferred jog(s) shorter than a track pitch dropped",
                    totals["jogs"])
    if totals["unknown"]:
        warnings.append(f"{totals['unknown']} shape(s) on layers the tech LEF does not "
                        f"define were skipped")
    if totals["unusable"]:
        warnings.append(f"{totals['unusable']} shape(s) on routing layers with no width "
                        f"rule were skipped")
    if totals["degenerate"]:
        warnings.append(f"{totals['degenerate']} shape(s) had no extent and were skipped")
