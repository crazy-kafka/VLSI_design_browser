from __future__ import annotations
from typing import AnyStr, List, Tuple, Dict, Union, Set, Iterable, TYPE_CHECKING

if TYPE_CHECKING:
    from .defWire import DefWire
    from .defSWire import DefSWire


class DefNet:

    def __init__(self, net_name: AnyStr):
        self.net_name = net_name
        self.connect_pins = []
        self.wiring: List[DefWire] = []
        self.swiring: List[DefSWire] = []

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



