from __future__ import annotations
from typing import AnyStr, List, Tuple, Dict, Union, Set, Iterable, TYPE_CHECKING

if TYPE_CHECKING:
    pass


class DefPin:

    def __init__(self, pin_name: AnyStr, direction: AnyStr, layer: AnyStr, pstatus: AnyStr, x: int, y: int, orient: AnyStr):
        self.pin_name = pin_name
        self.direction = direction
        self.layer = layer
        self.pstatus = pstatus
        self.pos_x = x
        self.pos_y = y
        self.pos = (x, y)
        self.orient = orient

    def __repr__(self):
        return f'''
DefPin
    pin_name  {self.pin_name}
    direction {self.direction}
    layer     {self.layer}
    pstatus   {self.pstatus}
    loc       {self.pos_x} {self.pos_y}
    orient    {self.orient}
'''


