from __future__ import annotations
from typing import List, Tuple, Dict, Union, Iterable, TYPE_CHECKING, AnyStr

if TYPE_CHECKING:
    pass


class LefPin:

    def __init__(self, pin_name: str, direction: str, use: str, layer: str, shape: List[Tuple[float, float]]):
        self.pin_name = pin_name
        self.direction = direction
        self.use = use
        self.layer = layer
        self.shape = shape


