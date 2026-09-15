from __future__ import annotations
from typing import AnyStr, List, Tuple, Dict, Union, Set, Iterable, TYPE_CHECKING

if TYPE_CHECKING:
    from .defWire import DefWire
    from .defSWire import DefSWire
    from .defSPolygon import DefSPolygon


class DefNet:

    def __init__(self, net_name: AnyStr):
        self.net_name = net_name
        self.connect_pins = []
        self.wiring: List[DefWire] = []
        self.swiring: List[DefSWire] = []
        # NETS and SPECIALNETS land in the same table, and nothing else in the statement
        # distinguishes them - so the section it came from has to be recorded here.
        self.is_special = False
        # The '+ USE' clause when the net states one (POWER, GROUND, SIGNAL, ...). A
        # power net is usually special and a special net is usually power, but neither
        # implies the other, so an explicit USE is the more reliable signal and callers
        # should prefer it when present.
        self.use = None
        # Whole '+ POLYGON' shapes. Distinct from `swiring`, which holds their edges and
        # cannot be reassembled into them - see DefSPolygon.
        self.polygons: List[DefSPolygon] = []
        # Via points from a '+ VIA <name> pt pt ...' form, counted rather than built. Each
        # one is a zero-length shape whose geometry nothing reads, so a fan-out of one
        # object per point is a fan-out of garbage: the stream counts them as `n_via` and
        # returns. A via point is 85 % of a real chip-level DEF's shapes, and holding a
        # million of them alive at once is what the memory peak is made of.
        self.via_points = 0
        # The same points, keyed by the layer of the form they came from - a '+ VIA' clause has no
        # layer of its own, the form around it does, so a per-layer count is only possible if it
        # is taken while that layer is still in hand. Points whose form states no layer are left
        # out rather than guessed at; the caller reports them as unattributed.
        self.via_points_by_layer: Dict[AnyStr, int] = {}
        # `VIRTUAL` connections, counted rather than built. They are connections and not shapes
        # (reference 874: "non-physical zero-width"), so there is nothing to build - but they
        # are shapes the stream used to measure as full-width wires, so the count is what says
        # how much of a map came from them.
        self.virtual_points = 0
        # Inline `RECT ( deltax1 deltay1 deltax2 deltay2 )` elements, resolved to absolute
        # corners at parse time as `(layer, x0, y0, x1, y1)`. Each is real metal that this
        # parser used to drop.
        self.rects: List[Tuple[AnyStr, int, int, int, int]] = []

    def __repr__(self):
        out_str = [f'DefWire {self.net_name}']
        out_str.append(f' connect_pin:')
        for conn in self.connect_pins:
            out_str.append(f'    {conn}')
        if self.wiring:
            out_str.append(f'  wiring:')
            for wire in self.wiring:
                out_str.append(f'    {wire}')
        if self.swiring:
            out_str.append(f'  swiring:')
            for swire in self.swiring:
                out_str.append(f'    {swire}')
        return '\n'.join(out_str)



