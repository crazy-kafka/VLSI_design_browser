from __future__ import annotations

import re
from typing import List, Tuple, Dict, Union, Set, Iterable, TYPE_CHECKING

if TYPE_CHECKING:
    pass


class CompiledRe:

    # BUSBITCHARS are '[]' by default, so an identifier may carry bus bit selects.
    # Without them here, buses collapse onto one another ('data[0]' and 'data[1]' both
    # become 'data') and any pin reference with a bit select fails to match at all.
    NAME = r'[_\w\d\/\[\]]+'
    PINNAME = r'[_\w\d\[\]]+'
    INTEGER = r'-?\d+'
    # A non-default rule's distances are database units. The reference implies integers,
    # but a decimal costs nothing to accept and avoids losing a rule to formatting.
    NDR_DIST = r'-?\d+(?:\.\d+)?'
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

    # --- nets and wiring (DEF NETS / SPECIALNETS) -----------------------------
    # Anchored: a statement begins at column 0 with "- name". Wiring coordinates can
    # also carry a '-', so an unanchored '-' would misfire on them.
    re_net = re.compile(rf'^\s*-\s+(?P<net_name>{NAME})')
    re_net_conn = re.compile(rf'\(\s+(?P<inst_name>{NAME})\s+(?P<term_name>{NAME})\s+\)')
    re_ndr = re.compile(rf'\+\s+NONDEFAULTRULE\s+(?P<ndr>{NAME})')

    # Words that begin a wiring clause or a following clause. None may be read as a
    # layer or a via name: with the special-wiring keyword optional (below), a loose
    # 'STYLE 3' would otherwise match the routed "<layer> <width>" form.
    #
    # The names are written once and used two ways: as the alternation below, and as a set
    # the tokeniser consults after it has matched a word (`__scan_tokens`). A set lookup is
    # paid once per matched word; the alternation form of the same test was being retried
    # at every character of every tail.
    WIRE_KEYWORDS = ("COVER", "FIXED", "ROUTED", "NOSHIELD", "SHIELD", "NEW", "POLYGON",
                     "RECT", "VIA", "SHAPE", "STYLE", "MASK", "DO", "STEP", "BY", "SOURCE",
                     "USE", "VOLTAGE", "WEIGHT", "PATTERN", "PROPERTY", "FIXEDBUMP",
                     "ROUTEHALO", "HALO", "REGION", "XTALK", "NONDEFAULTRULE", "SHIELDNET",
                     "VPIN", "SUBNET", "ESTCAP", "FREQUENCY", "ORIGINAL", "DIST", "NETLIST",
                     "USER", "TIMING")
    WIRE_KEYWORD = r'(?:' + '|'.join(WIRE_KEYWORDS) + r')'
    NOT_KEYWORD = rf'(?!(?:{WIRE_KEYWORD})\b)'

    # A routing point, or a via, in the order they appear. Each coordinate is an integer
    # or '*', which per the reference's DEF Coordinate Conventions means "reuse the last
    # coordinate" - so the caller has to carry state between points.
    WIRE_NUM = r'\*|-?\d+'
    WIRE_POINT = rf'\(\s*(?P<x>{WIRE_NUM})\s+(?P<y>{WIRE_NUM})(?:\s+(?P<ext>-?\d+))?\s*\)'
    # Two more elements of `routingPoints`, both sitting between the points (reference 872-874).
    # They have to be recognised *ahead of* the generic via-name alternative: read as a via name,
    # `VIRTUAL` turns its point into a wire corner - which measures a non-physical connection as
    # full-width metal - and `RECT` leaves its four deltas to match nothing and be dropped.
    WIRE_VIRTUAL = rf'VIRTUAL\s*\(\s*(?P<vx>{WIRE_NUM})\s+(?P<vy>{WIRE_NUM})\s*\)'
    WIRE_RECT = (rf'RECT\s*\(\s*(?P<rx0>-?\d+)\s+(?P<ry0>-?\d+)\s+'
                 rf'(?P<rx1>-?\d+)\s+(?P<ry1>-?\d+)\s*\)')
    ORIENT_CODE = r'N|S|W|E|FN|FS|FW|FE'
    # No keyword lookahead here: it was retried at every character of every tail to reject
    # a word that is a clause keyword (`+ SHAPE STRIPE` would otherwise read as a via), and
    # the tokeniser can make that test once per *matched word* instead. It does, in
    # `__scan_tokens`, against `WIRE_KEYWORDS`.
    #
    # The old lookahead did not protect the token stream anyway: rejecting SHAPE at its
    # first character let the engine match 'HAPE' one character later, so the junk name it
    # produced was a truncation rather than nothing. Points, the only tokens the metric
    # reads, are identical either way - measured over 19,646 tails of the vendored files.
    re_wire_token = re.compile(
        rf'{WIRE_VIRTUAL}|{WIRE_RECT}|{WIRE_POINT}|(?P<via>{NAME})'
        rf'(?:\s+(?P<via_orient>{ORIENT_CODE}))?')

    # The point pattern alone, for tails that hold routing points and nothing else -
    # via arrays and whole power nets are the bulk of a chip-level DEF's text, and the
    # full token pattern pays for its via/RECT/VIRTUAL alternatives at every match.
    # The parser substitutes every point away and falls back to `re_wire_token` when
    # anything non-whitespace remains, so nothing is ever dropped silently.
    re_points_tail = re.compile(WIRE_POINT)
    # A character that cannot appear inside a routing point, so its presence means the
    # tail holds a via name (or RECT/VIRTUAL/keywords) and the point-only scan has
    # nothing to win. NAME's alphabet minus the digits: [_\w\d\/\[\]] - \d.
    re_word_char = re.compile(r'[A-Za-z_/\[\]]')

    # A wiring form starts at its keyword and runs to the next form (or the next
    # non-wiring clause). Layer names may carry '[]' or '.'; widths are positive.
    WIRE_LAYER = r'[A-Za-z_][\w\[\]\/.]*'
    SHAPE_OR_MASK = r'(?:\+\s*SHAPE\s+\S+\s*|\+\s*MASK\s+\d+\s*)*'
    STYLE = r'(?:\+\s*STYLE\s+\d+\s*)?'
    # Three cheap refusals in front of the form grammar. All are *implied* by it rather than
    # added to it, which is what makes them safe: every branch below starts with '+', a
    # letter or '_', so that class cannot reject a match the grammar would have taken; the
    # layer/width branch requires a digit after its name, so asserting that first keeps the
    # keyword lookahead from being retried at every letter of every tail; and forms are
    # whitespace-separated, so one can never begin inside a word.
    #
    # That last one is not decoration. Rejecting `MASK` at its first character lets the engine
    # advance one character and match `ASK 1` as a layer named ASK with width 1 - the same
    # failure the token pattern had, where it is handled by the keyword set in `__scan_tokens`.
    # Here it costs geometry: the form that owned those points ends early, and the mask's own
    # points land on a layer no tech LEF defines. A three-mask process writes `+ MASK 1` after
    # a form's points, so the class is millions of shapes in a real file.
    #
    # This scan sees every character of a DEF's wiring, so it is the one worth making
    # cheap: measured on routing-shaped text, 182 -> 37 ns per character, with the match
    # stream identical - same positions, same groups - over 16,000 forms.
    FORM_FIRST = r'(?=[+A-Za-z_])(?<![A-Za-z0-9_])'
    LAYER_WITH_WIDTH = (rf'(?P<layer>(?={WIRE_LAYER}\s+\d){NOT_KEYWORD}{WIRE_LAYER})'
                        rf'\s+(?P<width>\d+)')
    # Special wiring: one form per match. The reference brackets the
    # {+ COVER|+ FIXED|+ ROUTED|+ SHIELD net} keyword ahead of the POLYGON/RECT/VIA
    # forms, so it is optional for those three; the routed "layerName routeWidth" form
    # requires it, which is what keeps other clauses from looking like a route.
    re_special_wiring_form = re.compile(
        FORM_FIRST +
        rf'(?:(?:\+\s*(?:COVER|FIXED|ROUTED|SHIELD\s+{NAME})|\bNEW)\s+)?{SHAPE_OR_MASK}'
        rf'(?:\+\s*POLYGON\s+(?P<poly_layer>{WIRE_LAYER})'
        rf'|\+\s*RECT\s+(?P<rect_layer>{WIRE_LAYER})'
        rf'|\+\s*VIA\s+(?P<via_name>{NAME})(?:\s+(?P<via_orient>{ORIENT_CODE}))?'
        rf'|{LAYER_WITH_WIDTH}'
        rf'\s*{SHAPE_OR_MASK}{STYLE})')
    # {+ COVER|+ FIXED|+ ROUTED|+ NOSHIELD} layer [TAPER|TAPERRULE rule] [STYLE n];
    # regular wiring has no routeWidth.
    re_regular_wiring_form = re.compile(
        FORM_FIRST +
        rf'(?:\+\s*(?:COVER|FIXED|ROUTED|NOSHIELD)|\bNEW)\s+(?P<layer>{WIRE_LAYER})'
        rf'(?:\s+(?:TAPERRULE\s+(?P<taper_rule>{NAME})|\bTAPER\b))?{STYLE}')
    # Clauses that may follow (or be interleaved with) wiring. These terminate the
    # wiring text, so a stray '+ SOURCE DIST' is not mistaken for a via.
    re_non_wiring_clause = re.compile(
        rf'\+\s*(?:SOURCE|USE|VOLTAGE|FIXEDBUMP|PATTERN|WEIGHT|PROPERTY|XTALK'
        rf'|NONDEFAULTRULE|SHIELDNET|VPIN|SUBNET|ESTCAP|FREQUENCY|ORIGINAL)\b')

    # --- non-default rules (reference 683-701) ---------------------------------------
    # A rule ends with a single ';' and the '+ LAYER' clauses inside it carry no
    # terminator of their own, so a whole rule arrives as one statement and is split
    # here. Without this the '+ NONDEFAULTRULE name' on a net is a string with nothing
    # behind it, and a 2W2S clock rule silently reads as the 1W1S default.
    re_ndr_rule = re.compile(rf'^\s*-\s+(?P<rule_name>{NAME})')
    re_ndr_layer = re.compile(
        rf'\+\s*LAYER\s+(?P<layer>{WIRE_LAYER})(?P<body>.*?)'
        rf'(?=\+\s*(?:LAYER|VIA|VIARULE|MINCUTS|HARDSPACING|PROPERTY)\b|$)',
        re.DOTALL)
    # DIAGWIDTH must precede WIDTH or the alternation matches the tail of it.
    re_ndr_field = re.compile(
        rf'(?P<field>DIAGWIDTH|SPACING|WIREEXT|WIDTH)\s+(?P<value>{NDR_DIST})')
    re_ndr_hardspacing = re.compile(r'\+\s*HARDSPACING\b')
    re_ndr_other = re.compile(r'\+\s*(?P<clause>VIA|VIARULE|MINCUTS|PROPERTY)\b')

    # A net's own '+ USE'. It outranks the section the net came from when the two
    # disagree, which is why both are recorded rather than one being inferred.
    re_net_use = re.compile(USE)

    # '(*703600)' and '(1760*)' glue '*' to the number it replaces. Splitting them before
    # tokenising keeps WIRE_POINT's separator strict, and that matters: relaxing it to
    # '\s*' would let a malformed '(1234)' backtrack into x=123, y=4 rather than fail.
    re_glued_star = re.compile(r'(?<=\d)(?=\*)|(?<=\*)(?=\d)')

    re_blockage = re.compile(rf'LAYER\s+(?P<layer_name>{NAME})\s+(?P<shape_type>POLYGON|RECT)')

    re_db_unit = re.compile(rf'UNITS\s+DISTANCE\s+MICRONS\s+(?P<unit>\d+)\s+')

    # {X|Y} start DO numtracks STEP space [MASK maskNum [SAMEMASK]] [LAYER l ...]
    # (reference 510-517). SAMEMASK is separately optional, so it must not swallow the
    # separator before LAYER: an earlier pattern required two whitespace runs after the
    # mask number, so the ordinary 'MASK 1 LAYER M4' never matched. LAYER may name
    # several layers, hence 'layers'.
    re_track = re.compile(
        rf'TRACKS\s+(?P<direction>X|Y)\s+(?P<offset>\d+)\s+DO\s+(?P<num_tracks>\d+)\s+'
        rf'STEP\s+(?P<step>\d+)(?:\s+MASK\s+(?P<mask_num>\d+)(?:\s+SAMEMASK)?)?'
        rf'\s+LAYER\s+(?P<layers>{NAME}(?:\s+{NAME})*)')

    re_property_definition = re.compile('PROPERTYDEFINITIONS')
    re_end_property_definition = re.compile(r'END\s+PROPERTYDEFINITIONS')

    re_pin = re.compile(rf'-\s+(?P<pin_name>{PINNAME})\s+(?:\+\s+NET\s+{PINNAME}\s+)?{DIRECTION}\s+{USE}\s+{LAYER}\s+{PT0}\s+{PT1}\s+{PSTATUS}\s+{PT2}\s+{ORIENT}')
    END_PIN = r'END PINS'




















