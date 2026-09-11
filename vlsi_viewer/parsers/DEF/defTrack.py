from __future__ import annotations
from typing import List, Tuple, Dict, AnyStr, Union, Set, Iterable, TYPE_CHECKING

if TYPE_CHECKING:
    pass


class DefTrack:

    def __init__(self, layer_name: AnyStr, direction: AnyStr, offset: int, step: int, mask: int):
        self.layer_name = layer_name
        self.direction = direction
        self.offset = offset
        self.step = step
        self.mask = mask

    def __repr__(self):
        return f'''
DefTrack
    layer_name {self.layer_name}
    direction  {self.direction}
    offset     {self.offset}
    step       {self.step}
    mask       {self.mask}
'''


