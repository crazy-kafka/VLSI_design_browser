from __future__ import annotations
from typing import List, Tuple, Dict, Union, Iterable, TYPE_CHECKING, AnyStr

if TYPE_CHECKING:
    pass

import re


class CompiledRe:

    FLOAT = r'-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?'

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

    # OBS match
    #
    # An OBS body is a sequence of `LAYER <name> ;` sections, each followed by geometry, and
    # the whole thing ends with a *bare* `END` - not `END <macro>`. That bare END is also how
    # a `PORT` inside a pin body ends, so the terminator is anchored and requires nothing but
    # the keyword on the line: matching it as a substring would stop at any line that merely
    # contains those three letters.
    OBS_START = r'^\s*OBS\s*$'
    re_obs_start = re.compile(OBS_START)
    re_obs_end = re.compile(r'^\s*END\s*;?\s*$')
    # Geometry inside OBS that this parser does not model. Counted so the caller can say so
    # rather than silently under-blocking a layer.
    OBS_UNMODELLED = r'^\s*(POLYGON|PATH|WIDTH|DESIGNRULEWIDTH|SPACING|EXCEPTPGNET)\b'
    re_obs_unmodelled = re.compile(OBS_UNMODELLED)

    #layer match
    #
    # A value ends at whitespace, a semicolon or end of line. Demanding trailing
    # whitespace (the earlier shape) silently reads 'DIRECTION VERTICAL;' as empty,
    # which then mislabels the layer's direction - and with it any H/V grouping.
    LAYER_END = r'(?=\s|;|$)'
    re_layer_name = re.compile(rf'^\s*LAYER\s+(?P<LAYER>[^\s]+)')
    re_layer_type = re.compile(rf'^\s*TYPE\s+(?P<TYPE>[A-Za-z_]\w*){LAYER_END}')
    re_layer_direction = re.compile(
        rf'^\s*DIRECTION\s+(?P<DIRECTION>HORIZONTAL|VERTICAL|DIAG45|DIAG135){LAYER_END}')
    re_layer_pitch = re.compile(
        rf'^\s*PITCH\s+(?P<PITCH_X>{FLOAT})\s+(?P<PITCH_Y>{FLOAT}){LAYER_END}')
    re_layer_pitch_single = re.compile(rf'^\s*PITCH\s+(?P<PITCH>{FLOAT})\s*;')
    re_layer_width = re.compile(rf'^\s*WIDTH\s+(?P<WIDTH>{FLOAT}){LAYER_END}')
    re_layer_min_width = re.compile(rf'^\s*MINWIDTH\s+(?P<MINWIDTH>{FLOAT}){LAYER_END}')
    re_layer_max_width = re.compile(rf'^\s*MAXWIDTH\s+(?P<MAXWIDTH>{FLOAT}){LAYER_END}')
    re_layer_spacing = re.compile(rf'^\s*SPACING\s+(?P<SPACING>{FLOAT}){LAYER_END}')
    # A bare 'SPACING x ;' is the layer's default. Every other SPACING form is
    # conditional (RANGE / LENGTHTHRESHOLD / ENDOFLINE) and describes a width band, so
    # it must not override the default - which is what a last-match-wins scan does.
    re_layer_spacing_default = re.compile(rf'^\s*SPACING\s+(?P<SPACING>{FLOAT})\s*;')
    # A spacing table's body is line-initial '<WIDTH> <breakpoint> <spacing>...', which
    # is shape-identical to the layer's own WIDTH statement; the table therefore has to
    # be consumed as a nested block rather than scanned line by line.
    re_layer_spacing_table = re.compile(r'^\s*SPACINGTABLE\b')
    re_layer_width_row = re.compile(r'^\s*WIDTH\s+')
    re_layer_table_header = re.compile(r'^\s*(?:PARALLELRUNLENGTH|TWOWIDTHS|INFLUENCE)\b')
    # A spacing table's body ends at its first semicolon.
    re_layer_table_end = re.compile(r';')
    re_area = re.compile(rf'^\s*AREA\s+(?P<AREA>{FLOAT})\s*;')

    # LEF58_TYPE names a variant of the base type (a NWELL region layer, say). It must
    # not overwrite TYPE, or a routing layer carrying one loses 'ROUTING' and drops out
    # of any routing-layer filter.
    re_LEF58_type = re.compile(
        rf'PROPERTY\s+LEF58_TYPE\s+"TYPE\s+(?P<LEF58_TYPE>[^;\s]+)\s*;')
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





