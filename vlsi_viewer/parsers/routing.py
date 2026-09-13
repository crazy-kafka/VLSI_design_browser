"""DEF + tech LEF -> routing shapes, normalised to microns and streamed.

The conversion layer between the vendored parsers and the metal-density metric. It sits
beside :mod:`convert` rather than inside it because its output is a different kind of thing:
``convert`` produces the viewer's JSON structures, string-keyed and round-trippable, while
routing geometry has no JSON form and is far too large to hold. One module, one contract.

**Nothing here retains geometry.** A design can carry 10^8 wire segments, which is gigabytes
as Python objects, so the DEF is parsed once and each net's shapes are handed to a sink and
dropped. Peak memory is one batch, not one design. The DEF parser takes a ``sink`` for this;
it accumulates nets only when no sink is set, which is what the existing component-only
callers rely on.

Three conversion rules come from the reference and from measuring a real routed DEF:

**Vias are omitted.** A via is a routing point with no extent: regular wiring builds a
zero-length ``DefWire`` for it, and special wiring writes one with ``routeWidth 0``.
Measured on `test/gcd_nangate45.def`, **half of all** ``DefWire`` objects are these. They
occupy no wire area, so they are skipped - not substituted with the layer's default width,
which would invent a wire at every via, and not extended by the half-width end rule, which
would turn each into a phantom square.

**Width comes from wherever it is stated.** Regular wiring carries no width at all, so it
takes the layer default, or its non-default rule's override when the net names one. Special
wiring states its own ``routeWidth``.

**Distances leave in microns.** DEF is in database units and the tech LEF is already microns,
so every DEF distance is divided by ``DefParser.dbUnit()`` exactly once, here, and nothing
downstream has to know about units.
"""
from __future__ import annotations

import logging
import re
from typing import AnyStr, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .DEF import DefParser
from .LEF import TlefParser

logger = logging.getLogger(__name__)

# Shape classes the accumulator distinguishes. Signal metal is what a router can still move;
# power metal is fixed and deliberate. Merging them makes a VDD stripe read as a hotspot.
SIGNAL = 0
POWER = 1

# Shapes are handed over in batches: one call per shape would make callback overhead
# dominate, and one call per design would defeat the streaming.
DEFAULT_BATCH = 1 << 16


def _routing_pitch(layer) -> float:
    """The pitch that separates adjacent tracks of ``layer``, from its LEF ``PITCH``.

    ``PITCH {distance | xDistance yDistance}``: the x value is the spacing of *vertical*
    tracks, the y value of *horizontal* ones, so the number this metric wants is the one
    perpendicular to the layer's own direction. A single-value ``PITCH`` sets both, so it
    makes no difference there - but where they differ (a real design's M1 `PITCH 0.020
    0.032`) reading the x value overstated that layer's capacity by 60 %.

    A layer with no direction, or a diagonal one, has no axis to prefer and keeps the x
    value first, as before. A zero for the chosen axis falls back to the other rather than
    reporting no pitch at all.
    """
    direction = (layer.direction or "").upper()
    if direction.startswith("H"):
        return layer.pitch_y or layer.pitch_x
    if direction.startswith("V"):
        return layer.pitch_x or layer.pitch_y
    return layer.pitch_x or layer.pitch_y


class RouteLayer:
    """One routing layer, in microns and in stack order.

    ``usable`` is False when the layer cannot be measured - no width rule anywhere in the
    tech LEF - which is reported rather than silently producing zero-area wires.
    """

    __slots__ = ("name", "index", "direction", "pitch", "width", "spacing", "usable")

    def __init__(self, name: AnyStr, index: int, direction: AnyStr, pitch: float,
                 width: float, spacing: float):
        self.name = name
        self.index = index
        self.direction = direction or ""
        self.pitch = float(pitch)
        self.width = float(width)
        self.spacing = float(spacing)
        self.usable = self.width > 0

    @property
    def is_horizontal(self) -> bool:
        return self.direction.upper().startswith("H")

    def __repr__(self):
        return (f"RouteLayer({self.name}, {self.direction or '?'}, pitch={self.pitch:g}, "
                f"w={self.width:g}, s={self.spacing:g}"
                + ("" if self.usable else ", UNUSABLE") + ")")


class TechRouting:
    """The routing layers of a tech LEF, in stack order, bottom to top.

    Order is the file's order, which is conventionally bottom-to-top, and is never sorted:
    a lexical sort would put ``metal10`` between ``metal1`` and ``metal2``, and the layer
    panel is built from this order.
    """

    def __init__(self, layers: Sequence[RouteLayer]):
        self.layers: List[RouteLayer] = list(layers)
        self._by_name = {layer.name: layer for layer in self.layers}

    def __len__(self):
        return len(self.layers)

    def __iter__(self):
        return iter(self.layers)

    def __getitem__(self, name) -> RouteLayer:
        return self._by_name[name]

    def get(self, name) -> Optional[RouteLayer]:
        return self._by_name.get(name)

    @property
    def usable(self) -> List[RouteLayer]:
        return [layer for layer in self.layers if layer.usable]

    @property
    def horizontal(self) -> List[RouteLayer]:
        return [layer for layer in self.layers if layer.is_horizontal]

    @property
    def vertical(self) -> List[RouteLayer]:
        return [layer for layer in self.layers if not layer.is_horizontal]

    @classmethod
    def read(cls, lef_paths: Sequence[AnyStr]) -> "TechRouting":
        """Read routing layers from one or more tech LEF files.

        Only ``TYPE ROUTING`` layers are kept. A real tech LEF is about half non-routing -
        Nangate45 has 22 ``LAYER`` blocks of which 10 are routing - and accepting a cut or
        masterslice layer would put phantom layers in the GUI. A layer whose rules come from
        a region over a base layer (``PROPERTY LEF58_REGION``) is also dropped: it is not a
        track system of the stack, and counting its metal as a layer of its own would
        measure the same silicon twice.

        The pitch is the one perpendicular to the layer's own tracks, because that is the
        distance between two adjacent tracks of *that* layer: a horizontal layer's tracks
        are stacked vertically, so its pitch is the y value. Taking the x value whenever one
        exists overstated the capacity of a real 18-layer design's M1 by 60 %.

        Spacing falls back to ``pitch - width`` when the LEF states none, which is the usual
        relation and far better than the zero a missing clause would otherwise leave behind
        (see the as-built notes: nine of the ten Nangate45 routing layers used to come out
        with no spacing at all).
        """
        parsed: Dict[AnyStr, object] = {}
        for path in lef_paths:
            for name, layer in TlefParser(path).layers.items():
                parsed.setdefault(name, layer)

        routing: List[RouteLayer] = []
        skipped = 0
        regions: List[AnyStr] = []
        for name, layer in parsed.items():
            if (layer.type or "").upper() != "ROUTING":
                continue
            if layer.region_layer:
                regions.append(name)
                continue
            pitch = _routing_pitch(layer)
            width = layer.width or layer.min_width
            spacing = layer.spacing
            if spacing <= 0 and pitch > 0 and width > 0:
                spacing = max(pitch - width, 0.0)
            if width <= 0:
                skipped += 1
                logger.warning(
                    "tech LEF: routing layer %s declares no usable width (WIDTH and "
                    "MINWIDTH both absent); its wires cannot be measured and are skipped",
                    name)
            routing.append(RouteLayer(name, len(routing), layer.direction, pitch, width,
                                      spacing))
        if regions:
            logger.info("tech LEF: %d region-defined layer(s) are not routing layers of the "
                        "stack and are skipped: %s", len(regions), ", ".join(regions))
        logger.info("tech LEF: %d routing layer(s) of %d layer(s), %d unusable, "
                    "%d region-defined", len(routing), len(parsed), skipped, len(regions))
        return cls(routing)


class ShapeStream:
    """Turns parsed nets into micron-normalised shapes, in batches, retaining nothing.

    Each wire arrives as its own rectangle already expanded by half its spacing rule - the
    keep-out region. That expansion is what makes the metric a track-utilisation measure
    rather than a coverage measure: a minimum-width wire expanded by half the spacing covers
    exactly one track pitch, so a bin reading 1.0 means every track in it is consumed.

    The sink receives

    ``add_rects(layer_index, scope, x0, y0, x1, y1)``
        axis-aligned keep-out rectangles, as arrays.
    ``add_diagonal(layer_index, scope, x0, y0, x1, y1, half_width)``
        the centre line of a 45-degree jog and the half-width it must be buffered by, one
        shape at a time. These are rare, so they are not batched.
    ``add_polygon(layer_index, scope, ring)``
        one ``+ POLYGON`` ring, an ``(N, 2)`` array in microns, one at a time.

    An optional ``frame`` places the shapes: it must expose ``apply_rect(x0, y0, x1, y1)``
    and ``apply_point(x, y)``, because a diagonal's ends have to be moved as *points* - a
    rectangle transform would collapse it to its bounding box.
    """

    def __init__(self, tech: TechRouting, sink, db_unit=None, ndrs=None, frame=None,
                 batch: int = DEFAULT_BATCH, min_segment=None):
        self.tech = tech
        # Set by configure() when the DEF is the source of these, because they are only
        # known partway through parsing it.
        self.db_unit = None if db_unit is None else float(db_unit)
        self.ndrs = ndrs or {}
        self.sink = sink
        self.frame = frame
        self.batch = max(1, int(batch))
        # Length below which a *non-preferred-direction* jog is dropped. None means "use
        # each layer's own pitch" - below one track pitch a jog covers under 0.04 um^2 of a
        # 10 um cell. Pass 0 to keep every jog.
        self.min_segment = min_segment
        self._pending: Dict[Tuple[int, int], List[list]] = {}
        self._diagonals: list = []
        self._count = 0
        # Diagnostics the caller reports rather than hides. The six drop counters say what
        # was thrown away; `n_emitted` says what was *measured*, and without it a run's
        # shapes cannot be reconciled with its clock: a log that reports 147 M dropped
        # shapes and no emitted count leaves the rest of the work unaccounted for.
        self.n_via = 0
        self.n_jog = 0
        self.n_degenerate = 0
        self.n_polygon_edge = 0
        self.n_usable_layer_missing = 0
        self.n_unknown_layer = 0
        self.n_emitted = 0

    def configure(self, db_unit, ndrs) -> None:
        """Adopt the database unit and rule table of the DEF being parsed."""
        self.db_unit = float(db_unit)
        self.ndrs = ndrs or {}

    def require_configured(self) -> None:
        if self.db_unit is None:
            raise RuntimeError(
                "ShapeStream needs a database unit before it can measure anything; pass "
                "one, or drive it from parse_def() which supplies the DEF's own")

    # -- layer and rule lookup -------------------------------------------------------

    def _layer(self, name) -> Optional[RouteLayer]:
        layer = self.tech.get(name)
        if layer is None:
            self.n_unknown_layer += 1
        elif not layer.usable:
            self.n_usable_layer_missing += 1
        return layer

    def _rules(self, layer: RouteLayer, rule) -> Tuple[float, float]:
        """Effective width and spacing for one wire, in microns.

        A net naming a non-default rule takes that rule's width and spacing where it states
        them, per field: a rule commonly names only some layers, and on the layers it does
        name it commonly overrides only some fields. A field it omits keeps the layer
        default.
        """
        width, spacing = layer.width, layer.spacing
        if rule and rule != "default":
            entry = self.ndrs.get(rule)
            if entry is None:
                logger.debug("net references unknown non-default rule %r; using layer "
                             "defaults", rule)
                return width, spacing
            override = entry.layers.get(layer.name)
            if override is None:
                logger.debug("non-default rule %s does not name layer %s; using layer "
                             "defaults", rule, layer.name)
                return width, spacing
            if override.width:
                width = override.width / self.db_unit
            if override.spacing:
                spacing = override.spacing / self.db_unit
        return width, spacing

    # -- shape emission --------------------------------------------------------------

    def _emit(self, layer: RouteLayer, scope: int, x0, y0, x1, y1) -> None:
        bucket = self._pending.get((layer.index, scope))
        if bucket is None:
            bucket = self._pending[(layer.index, scope)] = [[], [], [], []]
        bucket[0].append(x0)
        bucket[1].append(y0)
        bucket[2].append(x1)
        bucket[3].append(y1)
        self._count += 1
        self.n_emitted += 1
        if self._count >= self.batch:
            self.flush()

    def flush(self) -> None:
        """Hand every pending shape to the sink and release it."""
        for (layer_index, scope), coords in self._pending.items():
            x0 = np.asarray(coords[0], dtype=np.float64)
            y0 = np.asarray(coords[1], dtype=np.float64)
            x1 = np.asarray(coords[2], dtype=np.float64)
            y1 = np.asarray(coords[3], dtype=np.float64)
            if self.frame is not None:
                x0, y0, x1, y1 = self.frame.apply_rect(x0, y0, x1, y1)
            self.sink.add_rects(layer_index, scope, x0, y0, x1, y1)
        self._pending = {}
        self._count = 0

        for layer_index, scope, x0, y0, x1, y1, half in self._diagonals:
            if self.frame is not None:
                x0, y0 = self.frame.apply_point(x0, y0)
                x1, y1 = self.frame.apply_point(x1, y1)
            self.sink.add_diagonal(layer_index, scope, x0, y0, x1, y1, half)
        self.n_emitted += len(self._diagonals)
        self._diagonals = []

    # -- nets ------------------------------------------------------------------------

    def add_net(self, net) -> None:
        """Convert one parsed net's wiring into shapes."""
        self.require_configured()
        scope = self._scope(net)
        for wire in net.wiring:
            self._add_regular(wire, net, scope)
        for swire in net.swiring:
            self._add_special(swire, scope)
        for polygon in net.polygons:
            self._add_polygon(polygon, scope)
        # '+ VIA' points the parser counted instead of building. Each would have taken the
        # `shape == 'VIA'` branch above and done nothing but increment this counter, so the
        # total is the same number by a shorter route.
        self.n_via += net.via_points

    @staticmethod
    def _scope(net) -> int:
        """Signal or power, preferring the net's own statement of it.

        ``+ USE POWER`` outranks the section the net came from when the two disagree; a
        special net that says nothing is treated as power, which is what it almost always
        is and is the safer default for a map that is meant to separate fixed metal from
        routable metal.
        """
        if net.use in ("POWER", "GROUND"):
            return POWER
        if net.use is not None:
            return SIGNAL
        return POWER if net.is_special else SIGNAL

    def _is_preferred(self, layer: RouteLayer, x0, y0, x1, y1) -> bool:
        """Whether a segment runs along its layer's preferred direction.

        A tool shifts a net sideways without changing layer by inserting a short jog across
        the preferred direction - a horizontal blip on a vertical layer. Those are the
        segments worth dropping, and only when they are short. A short *preferred-direction*
        stub is real metal and is never dropped by that rule.
        """
        if not layer.direction:
            return True
        horizontal = (y0 == y1)
        vertical = (x0 == x1)
        if not horizontal and not vertical:
            return False                 # a diagonal is never preferred
        return horizontal == layer.is_horizontal

    def _is_jog(self, layer: RouteLayer, x0, y0, x1, y1, span: float) -> bool:
        if self.min_segment == 0 or self._is_preferred(layer, x0, y0, x1, y1):
            return False
        # None means "use the layer's pitch": below one track pitch a jog contributes under
        # 0.04 um^2 to a 10 um cell, which is far inside the metric's other approximations.
        threshold = layer.pitch if self.min_segment is None else self.min_segment
        return threshold > 0 and span < threshold

    def _add_regular(self, wire, net, scope: int) -> None:
        layer = self._layer(wire.layer_name)
        if layer is None:
            return
        x0, y0 = wire.from_pt
        x1, y1 = wire.to_pt
        if x0 == x1 and y0 == y1:
            # A via point: no extent, so no wire area. Half of a real DEF's segments.
            self.n_via += 1
            return
        width, spacing = self._rules(layer, wire.rule)
        # Regular wiring defaults to half the wire width of extension at each end.
        self._add_wire(layer, scope, x0, y0, x1, y1, width, spacing, width / 2.0)

    def _add_special(self, swire, scope: int) -> None:
        if swire.shape == "VIA":
            self.n_via += 1
            return
        if swire.shape == "POLYGON":
            # One edge of a ring whose filled area is handled from net.polygons, where the
            # whole vertex list exists. Counting the edges here would double-count it.
            self.n_polygon_edge += 1
            return
        layer = self._layer(swire.layer_name)
        if layer is None:
            return
        if swire.shape == "RECT":
            # A filled rectangle whose geometry is explicit, so no width is involved - the
            # parser leaves `width` None for these, which is why the width check below has
            # to come *after* this branch. It is also why the corners are sorted: the
            # parser does not normalise '+ RECT' the way it does DefBlockage.
            self._add_box(layer, scope, swire.x0, swire.y0, swire.x1, swire.y1,
                          layer.spacing)
            return
        if not swire.width:
            # 'routeWidth 0' on a routed form marks a via placement, not a zero-width wire.
            self.n_via += 1
            return
        extension = max(swire.e0 or 0, swire.e1 or 0) / self.db_unit
        self._add_wire(layer, scope, swire.x0, swire.y0, swire.x1, swire.y1,
                       swire.width / self.db_unit, layer.spacing, extension)

    def _add_wire(self, layer, scope, x0, y0, x1, y1, width, spacing, extension) -> None:
        """One wire segment, as its keep-out rectangle (or as a diagonal centre line)."""
        if width <= 0:
            self.n_usable_layer_missing += 1
            return
        span = max(abs(x1 - x0), abs(y1 - y0)) / self.db_unit
        if self._is_jog(layer, x0, y0, x1, y1, span):
            self.n_jog += 1
            return
        if x0 != x1 and y0 != y1:
            # A diagonal jog. The sink buffers the centre line exactly rather than taking a
            # bounding box, which for a 10 um diagonal would over-count by about 25x.
            self._diagonals.append((layer.index, scope, x0 / self.db_unit,
                                    y0 / self.db_unit, x1 / self.db_unit,
                                    y1 / self.db_unit,
                                    width / 2.0 + spacing / 2.0))
            if len(self._diagonals) >= self.batch:
                self.flush()
            return
        self._add_box(layer, scope, x0, y0, x1, y1, spacing, width=width,
                      extension=extension)

    def _add_box(self, layer, scope, x0, y0, x1, y1, spacing, width=0.0,
                 extension=0.0) -> None:
        """Axis-aligned footprint grown by half the spacing rule on every side."""
        grow = spacing / 2.0
        lo_x, hi_x = sorted((x0 / self.db_unit, x1 / self.db_unit))
        lo_y, hi_y = sorted((y0 / self.db_unit, y1 / self.db_unit))
        if width > 0:
            # The wire's own footprint is width-across plus its end extension lengthwise.
            if x0 == x1:
                lo_x -= width / 2.0
                hi_x += width / 2.0
                lo_y -= extension
                hi_y += extension
            else:
                lo_y -= width / 2.0
                hi_y += width / 2.0
                lo_x -= extension
                hi_x += extension
        if hi_x - lo_x <= 0 or hi_y - lo_y <= 0:
            self.n_degenerate += 1
            return
        self._emit(layer, scope, lo_x - grow, lo_y - grow, hi_x + grow, hi_y + grow)

    def _add_polygon(self, polygon, scope: int) -> None:
        """A ``+ POLYGON`` ring, expanded by half the layer's spacing rule.

        Rare, so the exact ``shapely`` buffer is affordable; a ring is a filled shape, not
        an outline, so it is handed over whole rather than as its edges.
        """
        from shapely.geometry import Polygon

        layer = self._layer(polygon.layer_name)
        if layer is None:
            return
        ring = [(x / self.db_unit, y / self.db_unit) for x, y in polygon.pts]
        if len(ring) < 3:
            return
        shape = Polygon(ring)
        if not shape.is_valid:
            shape = shape.buffer(0)
        if shape.is_empty or shape.area <= 0:
            return
        grow = layer.spacing / 2.0
        if grow > 0:
            shape = shape.buffer(grow, join_style=2)
        self.sink.add_polygon(layer.index, scope,
                              np.asarray(shape.exterior.coords, dtype=np.float64))
        # Counted where the screen counts it: the ring arrives as one shape, while its edges
        # went to `n_polygon_edge` above.
        self.n_emitted += 1


class DefRouting:
    """What a DEF contributes besides its shapes.

    Tracks and non-default rules are normalised to microns here, so the caller never sees a
    database unit. Components are handed over as the parser produced them, because the
    instance conversion already knows how to scale those.
    """

    def __init__(self, path, design_name, db_unit, boundary, components, tracks, ndrs,
                 stats: Dict = None):
        self.path = path
        self.design_name = design_name
        self.db_unit = db_unit
        self.boundary = boundary
        self.components = components
        self.tracks = tracks
        self.ndrs = ndrs
        # What the text was like - statement sizes, points, layer names. See
        # `DefParser.getStats`.
        self.stats = dict(stats or {})


def parse_def(def_path: AnyStr, stream: Optional[ShapeStream] = None,
              top=None, skip_components: bool = False, cancel=None) -> DefRouting:
    """Parse one DEF, streaming its wiring into ``stream`` if one is given.

    Net, special-net and rule parsing are always enabled: the metal flow needs all three,
    and enabling them is what moves the parser's stopping point from ``END COMPONENTS`` to
    ``END NETS``. The declared section counts are compared against what was parsed, because
    a DEF that puts a section where the dispatcher has already stopped would otherwise lose
    it silently - the same check ``convert`` already applies to components.

    ``skip_components`` is for a caller that has already read them - the metal flow's second
    pass, which wants the wiring and nothing else. The section is still scanned; what it no
    longer does is build and hold a ``DefComponent`` per instance, which on a flat
    chip-level DEF is millions of objects that no one reads.
    """
    def sink(net, db_unit, ndrs):
        # The stream is configured lazily, on the first net: the database unit and the
        # rule table are only known once the parse has read past UNITS and
        # NONDEFAULTRULES, and the parser hands them over here rather than the caller
        # having to ask for a parser it has not been given yet.
        if stream.db_unit is None:
            stream.configure(db_unit, ndrs)
        stream.add_net(net)

    # `cancel` is consulted once per heartbeat; returning True from it raises `Cancelled`,
    # which abandons the parse and leaves whatever was already handed to the sink in place.
    parser = DefParser(def_path, parse_net=True, parse_specialnet=True, parse_ndr=True,
                       skip_comp=skip_components, cancel=cancel,
                       sink=None if stream is None else sink)
    db_unit = parser.dbUnit()
    boundary = [[x / db_unit, y / db_unit] for x, y in parser.shape()]

    _warn_on_count_mismatch(def_path, "NETS", parser.declared_nets, parser.n_nets)
    _warn_on_count_mismatch(def_path, "SPECIALNETS", parser.declared_special_nets,
                            parser.n_special_nets)

    return DefRouting(def_path, parser.designName or top, db_unit, boundary,
                      parser.getAllComponents(), parser.getTracks(),
                      {name: _scaled_rule(rule, db_unit)
                       for name, rule in parser.getNdrRules().items()},
                      parser.getStats())


def _scaled_rule(rule, db_unit):
    """A copy of a non-default rule with its distances in microns.

    A copy, not an edit in place: the stream is holding the parser's original rule objects
    and divides by the database unit itself, so scaling those in place would apply the
    conversion twice.
    """
    from .DEF.defNdr import DefNdrLayer, DefNdrRule

    scaled = DefNdrRule(rule.rule_name)
    scaled.hardspacing = rule.hardspacing
    scaled.unparsed = list(rule.unparsed)
    for layer_name, entry in rule.layers.items():
        converted = DefNdrLayer(entry.layer_name)
        for field in ("width", "spacing", "diagwidth", "wireext"):
            value = getattr(entry, field)
            setattr(converted, field, None if value is None else value / db_unit)
        scaled.layers[layer_name] = converted
    return scaled


def _warn_on_count_mismatch(def_path, section: AnyStr, declared: Optional[int],
                            parsed: int) -> None:
    """Compare a section's declared count with what was parsed.

    A mismatch means the parser stopped before, or inside, that section - the failure mode
    that made ``NONDEFAULTRULES`` invisible for so long. Worth saying out loud, because the
    map that results is wrong in a way nothing else reveals.
    """
    if declared is None or declared == parsed:
        return
    logger.warning("%s declares %s %s but %d were parsed; wiring the parser did not reach "
                   "is not counted", def_path, declared, section, parsed)
