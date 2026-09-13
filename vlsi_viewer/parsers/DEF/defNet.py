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



