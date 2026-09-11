from __future__ import annotations
from typing import List, Tuple, Dict, AnyStr, Union, Set, Iterable, TYPE_CHECKING

if TYPE_CHECKING:
    pass


class DefWire:

    def __init__(self, layer_name: AnyStr, rule: AnyStr, from_pt: Tuple[int, int], to_pt: Tuple[int, int]):
        self.layer_name = layer_name
        self.rule = rule
        self.from_pt = from_pt
        self.to_pt = to_pt

    def __repr__(self):
        return f'layer {self.layer_name} rule {self.rule} from_pt {self.from_pt} to_pt {self.to_pt}'

