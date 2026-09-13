from __future__ import annotations
from typing import List, Tuple, Dict, AnyStr, Union, Set, Iterable, TYPE_CHECKING

if TYPE_CHECKING:
    pass


class DefWire:
    """One segment of a net's regular wiring (DEF ``NETS``).

    ``rule`` is the wire's non-default rule: a per-wire ``TAPERRULE`` when the wiring
    statement carries one, otherwise the net-level ``+ NONDEFAULTRULE``, otherwise
    ``'default'``. ``via``/``via_orient`` are the via at the segment's start point.
    """

    # One object per segment: the per-instance dict is a real cost at 10^8 segments.
    __slots__ = ("layer_name", "rule", "from_pt", "to_pt", "via", "via_orient")

    def __init__(self, layer_name: AnyStr, rule: AnyStr, from_pt: Tuple[int, int],
                 to_pt: Tuple[int, int], via: AnyStr = None,
                 via_orient: AnyStr = None):
        self.layer_name = layer_name
        self.rule = rule
        self.from_pt = from_pt
        self.to_pt = to_pt
        self.via = via
        self.via_orient = via_orient

    def __repr__(self):
        via = f' via {self.via}' + (f' {self.via_orient}' if self.via_orient else '')
        return (f'layer {self.layer_name} rule {self.rule} '
                f'from_pt {self.from_pt} to_pt {self.to_pt}{via}')

