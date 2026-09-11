from __future__ import annotations

import re
from typing import List, Tuple, Dict, Union, Set, Iterable, TYPE_CHECKING

if TYPE_CHECKING:
    pass


class CompiledRe:

    NAME = r'[_\w\d\/]+'
    PINNAME = r'[_\w\d\[\]]+'
    INTEGER = r'-?\d+'
    COMPONENTS_PART = r'COMPINENTS \D+ ;(.*)END COMPONENTS'
    PSTATUS = r'\+ (?P<pstatus>FIXED|COVER|PLACED|UNPLACED)'
    DIRECTION = r'\+\s+DIRECTION\s+(?P<direction>INPUT|OUTPUT|INOUT|FEEDTHRU)'
    USE = r'\+\s+USE\s+(?P<use>ANALOG|CLOCK|GROUND|POWER|RESET|SCAN|SIGNAL|TIEOFF)'
    LAYER = rf'\+\s+LAYER\s+(?P<layer>{NAME})'

    PT = rf'\(\s+(?P<x>{INTEGER})\s+(?P<y>{INTEGER})\s+\)'
    PT0 = rf'\(\s+(?P<x0>{INTEGER})\s+(?P<y0>{INTEGER})\s+\)'
    PT1 = rf'\(\s+(?P<x1>{INTEGER})\s+(?P<y1>{INTEGER})\s+\)'
    PT2 = rf'\(\s+(?P<x2>{INTEGER})\s+(?P<y2>{INTEGER})\s+\)'
    re_pt = re.compile(PT)

    ORIENT = r'(?P<orient>N|S|W|E|FN|FS|FW|FE)'
    SOURCE = r'\+ SOURCE (?P<source>NETLIST|DIST|USER|TIMING)\s+'
    re_component = re.compile(rf'-\s+(?P<compName>\S+)\s+(?P<modelName>\S+)\s+(?:{SOURCE})?{PSTATUS}(?:\s+{PT}\s+{ORIENT})?')
    re_end_component = re.compile(rf'END COMPONENTS')
    PG = rf'-\s+(?P<pgNet>\S+)'
    DIE_PART = rf'DIEAREA\s+(\(\s+\d+\s+\d+\s\)[\s\n]+)+;'
    DESIGN = rf'DESIGN\s+(?P<design>[^\s;]+)\s+;'
    re_design = re.compile(DESIGN)
    END_DESIGN = r'END\s+DESIGN'
    re_end_design = re.compile(END_DESIGN)

    re_net = re.compile(rf'-\s+(?P<net_name>{NAME})')
    re_net_conn = re.compile(rf'\(\s+(?P<inst_name>{NAME})\s+(?P<term_name>{NAME})\s+\)')

    re_special_wiring = re.compile(rf'(?P<layer>{NAME})\s+(?P<width>\d+)\s+\(\s*(?P<x0>[*\d]+)\s+(?P<y0>[*\d]+)(?:\s+(?P<e0>\d+))?\s*\)(?:\s+\(\s*(?P<x1>[*\d]+)\s+(?P<y1>[*\d]+)(?:\s+(?P<e1>\d+))?\s*\))?(?:\s+(?P<via>{NAME}))?')

    re_routing_point = re.compile(rf'\(\s*(?P<x>[\*\d]+)\s+(?P<y>[\*\d]+)(?:\s+(?P<e>\d+))?\s*\)')
    re_routing_point_0 = re.compile(rf'\(\s*(?P<x0>[\*\d]+)\s+(?P<y0>[\*\d]+)(?:\s+(?P<e0>\d+))?\s*\)')
    re_routing_point_1 = re.compile(rf'\(\s*(?P<x1>[\*\d]+)\s+(?P<y1>[\*\d]+)(?:\s+(?P<e1>\d+))?\s*\)')

    re_regular_wiring = re.compile(rf'(?:ROUTED|FIXED|NEW)\s+(?P<layer>{NAME})\s+(?:(?P<TAPER>TAPER|TAPERRULE\s+{NAME})\s+)?')
    re_ndr = re.compile(rf'\+\s+NONDEFAULTRULE\s+(?P<ndr>{NAME})')

    re_blockage = re.compile(rf'LAYER\s+(?P<layer_name>{NAME})\s+(?P<shape_type>POLYGON|RECT)')

    re_db_unit = re.compile(rf'UNITS\s+DISTANCE\s+MICRONS\s+(?P<unit>\d+)\s+')

    re_track = re.compile(rf'TRACKS\s+(?P<direction>X|Y)\s+(?P<offset>\d+)\s+DO\s+\d+\s+STEP\s+(?P<step>\d+)\s+(?:MASK\s+(?P<mask_num>\d+)\s+(?:SAMEMASK)?\s+)?LAYER\s+(?P<layer>{NAME})')

    re_property_definition = re.compile('PROPERTYDEFINITIONS')
    re_end_property_definition = re.compile(r'END\s+PROPERTYDEFINITIONS')

    re_pin = re.compile(rf'-\s+(?P<pin_name>{PINNAME})\s+(?:\+\s+NET\s+{PINNAME}\s+)?{DIRECTION}\s+{USE}\s+{LAYER}\s+{PT0}\s+{PT1}\s+{PSTATUS}\s+{PT2}\s+{ORIENT}')
    END_PIN = r'END PINS'




















