from __future__ import annotations
from typing import List, Tuple, Dict, Union, Iterable, TYPE_CHECKING, AnyStr

if TYPE_CHECKING:
    pass


class LefLayer:

    def __init__(self, layer_name: AnyStr):
        self.name = layer_name
        self.type = ''
        # 'PROPERTY LEF58_TYPE "TYPE X ;"' - a variant of the base TYPE, kept separate
        # because it must not overwrite `type` (see CompiledRe.re_LEF58_type).
        self.lef58_type = None
        self.direction = ''
        self.pitch_x = 0.0
        self.pitch_y = 0.0
        self.width = 0.0
        self.min_width = 0.0
        self.max_width = 0.0
        self.spacing = 0.0
        self.area = 0.0

        # Set when the stanza carried a `PROPERTY LEF58_REGION`: the layer's rules belong to
        # a region over a base layer rather than describing a track system of the stack, so
        # it is not a routing layer. A flag of its own because `region`/`based_layer` below
        # are parsed from the payload and can legitimately come out empty - a real file
        # spells the clause `REGION FB1 BASEDLAYE R M2`, with a space inside the keyword.
        self.region_layer = False
        self.region = None
        self.based_layer = None

    def __repr__(self):
        return f'''
Lef Layer {self.name}
    type        {self.type}
    lef58_type  {self.lef58_type}
    direction   {self.direction}
    pitch       {self.pitch_x} {self.pitch_y}
    width       {self.width}
    min_width   {self.min_width}
    max_width   {self.max_width}
    spacing     {self.spacing}
    area        {self.area}
    region      {self.region}
    based_layer {self.based_layer}
    region_layer {self.region_layer}
'''


