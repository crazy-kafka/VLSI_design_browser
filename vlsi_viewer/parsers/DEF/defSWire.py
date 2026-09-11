from __future__ import annotations
from typing import AnyStr, List, Tuple, Dict, Union, Set, Iterable, TYPE_CHECKING

if TYPE_CHECKING:
    pass


class DefSWire:

    def __init__(self, layer_name: AnyStr, width: int, x0: int, y0: int, e0: int, x1: int, y1: int, e1: int, via: str):
        self.layer_name = layer_name
        self.width = width
        self.x0 = x0
        self.y0 = y0
        self.e0 = e0
        self.x1 = x1
        self.y1 = y1
        self.e1 = e1
        self.via = via

    def __repr__(self):
        return f'layer {self.layer_name} width {self.width} from {(self.x0, self.y0, self.e0)} to {(self.x1, self.y1, self.e1)} via {self.via}'

