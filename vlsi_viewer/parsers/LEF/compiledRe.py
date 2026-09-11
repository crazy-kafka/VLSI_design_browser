from __future__ import annotations
from typing import List, Tuple, Dict, Union, Iterable, TYPE_CHECKING, AnyStr

if TYPE_CHECKING:
    pass

import re


class CompiledRe:

    FLOAT = r'-?\d+(?:\.\d+)?'

    #macro match
    MACRO_START = r'^\s*MACRO\s+([0-9a-zA-Z_]+)'
    re_macro_start = re.compile(MACRO_START)
    CLASS = r'CLASS\s+([A-Za-z]+(?:\s+[A-Za-z]+)*)'
    re_class = re.compile(CLASS)
    SIZE = rf'SIZE\s+({FLOAT})\s+BY\s+({FLOAT})'
    re_size = re.compile(SIZE)
    PIN_START = r'PIN ([_0-9a-zA-Z\[\]]+)'
    re_pin_start = re.compile(PIN_START)
    DIRECTION = r'DIRECTION\s+([A-Za-z]+)'
    re_direction = re.compile(DIRECTION)
    USE = r'USE\s+([A-Za-z]+)'
    re_use = re.compile(USE)
    LAYER = r'LAYER ([0-9a-zA-Z_.-]+)'
    re_layer = re.compile(LAYER)
    RECT = rf'RECT (?:MASK \d )?({FLOAT}) ({FLOAT}) ({FLOAT}) ({FLOAT})'
    re_rect = re.compile(RECT)

    #layer match
    re_layer_name = re.compile(rf'^\s*LAYER\s+(?P<LAYER>[^\s]+)')
    re_layer_type = re.compile(rf'^\s*TYPE\s+(?P<TYPE>[^\s]+)\s+')
    re_layer_direction = re.compile(rf'^\s*DIRECTION\s+(?P<DIRECTION>HORIZONTAL|VERTICAL|DIAG45|DIAG135)\s+')
    re_layer_pitch = re.compile(rf'^\s*PITCH\s+(?P<PITCH_X>{FLOAT})\s+(?P<PITCH_Y>{FLOAT})\s+')
    re_layer_pitch_single = re.compile(rf'^\s*PITCH\s+(?P<PITCH>{FLOAT})\s+;')
    re_layer_width = re.compile(rf'^\s*WIDTH\s+(?P<WIDTH>{FLOAT})\s+')
    re_layer_min_width = re.compile(rf'^\s*MINWIDTH\s+(?P<MINWIDTH>{FLOAT})\s+')
    re_layer_max_width = re.compile(rf'^\s*MAXWIDTH\s+(?P<MAXWIDTH>{FLOAT})\s+')
    re_layer_spacing = re.compile(rf'^\s*SPACING\s+(?P<SPACING>{FLOAT})\s+')
    re_area = re.compile(rf'^\s*AREA\s+(?P<AREA>{FLOAT})\s+;')

    re_LEF58_type = re.compile(rf'PROPERTY LEF58_TYPE "TYPE (?P<TYPE>\S+) ;"')
    re_LEF58_region = re.compile(rf'PROPERTY\s+LEF58_REGION\s+"\s*REGION\s+(?P<REGION>\S+)\s+BASEDLAYER\s+(?P<BASEDLAYER>\S+)\s*;\s*"\s+;')

    #propertydefinition
    re_property_definitions = re.compile(rf'^\s*PROPERTYDEFINITIONS')
    re_end_property_definitions = re.compile(rf'^\s*END\s+PROPERTYDEFINITIONS')

    #unit
    re_units = re.compile(rf'^\s*UNITS')
    re_end_units = re.compile(rf'^\s*END\s+UNITS')

    #via
    re_via = re.compile(rf'^\s*VIA\s+(?P<VIA>[^\s]+)')

    #VIARULE
    re_via_rule = re.compile(rf'^\s*VIARULE\s+(?P<VIARULE>[^\s]+)')





