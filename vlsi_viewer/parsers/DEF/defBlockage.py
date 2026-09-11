from __future__ import annotations
from typing import List, Tuple, Dict, Union, Set, Iterable, TYPE_CHECKING, AnyStr

if TYPE_CHECKING:
    pass


class DefBlockage:

    def __init__(self, layer_name: str, shape_type: str, pts: List[Tuple[int, int]]):
        self.layer_name = layer_name
        self.shape_type = shape_type
        self.pts = pts
        if self.shape_type == 'RECT':
            x0 = self.pts[0][0]
            y0 = self.pts[0][1]
            x1 = self.pts[1][0]
            y1 = self.pts[1][1]
            self.pts = [
                (min(x0, x1), min(y0, y1)),
                (max(x0, x1), min(y0, y1)),
                (max(x0, x1), max(y0, y1)),
                (min(x0, x1), max(y0, y1))
            ]

    def __repr__(self):
        return f'''
Def Blockage:
    layer_name {self.layer_name}
    shape_type {self.shape_type}
    pts        {self.pts}
'''


