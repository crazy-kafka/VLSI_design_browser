from __future__ import annotations
from typing import AnyStr, List, Tuple, Dict, Union, Set, Iterable, TYPE_CHECKING

if TYPE_CHECKING:
    pass


class DefSWire:
    """One segment of a special wire, plus whatever sat at its starting point.

    ``shape`` records how the segment arose, because the two are not geometrically the
    same thing and a consumer needs to tell them apart:

    ``'PATH'``
        a segment of ``layer width routingPoints`` (the usual routed wire).
    ``'RECT'``
        ``+ RECT layer pt pt`` - a filled rectangle. The segment is its diagonal, which
        is a lossy but convenient stand-in for a wire-oriented model.
    ``'POLYGON'``
        one edge of ``+ POLYGON layer pt pt pt ...``.

    ``via``/``via_orient`` are the via at the segment's *start* point (a via replaces a
    routing point, so either adjacent segment could claim it; the start is where it is
    anchored in the DEF text).
    """

    def __init__(self, layer_name: AnyStr, width: int, x0: int, y0: int, e0: int,
                 x1: int, y1: int, e1: int, via: str = None, via_orient: AnyStr = None,
                 shape: AnyStr = 'PATH'):
        self.layer_name = layer_name
        self.width = width
        self.x0 = x0
        self.y0 = y0
        self.e0 = e0
        self.x1 = x1
        self.y1 = y1
        self.e1 = e1
        self.via = via
        self.via_orient = via_orient
        self.shape = shape

    def __repr__(self):
        via = f' via {self.via}' + (f' {self.via_orient}' if self.via_orient else '')
        return (f'layer {self.layer_name} width {self.width} '
                f'from {(self.x0, self.y0, self.e0)} to {(self.x1, self.y1, self.e1)}'
                f' {self.shape}{via}')

