"""DEF ``NONDEFAULTRULES`` parsing.

The section was not read at all before the metal-density work: a net's
``+ NONDEFAULTRULE name`` was a string with nothing behind it, so a 2W2S clock rule read
as the 1W1S default and roughly halved the metal a clock region appeared to use.

The statement shape matters and is easy to get wrong. A rule ends with a single ``;`` and
the ``+ LAYER`` clauses inside it have no terminator of their own, so a whole rule arrives
as one statement - the first fixture below is the real form.

Section order is also load-bearing. ``NONDEFAULTRULES`` normally precedes ``COMPONENTS``,
and the dispatcher stops at the last *enabled* section, so whether a late section is seen
depends on whether nets are being parsed. Both configurations are pinned below.
"""
import io
import contextlib
import textwrap

import pytest

from vlsi_viewer.parsers.DEF import DefParser

HEAD = """\
VERSION 5.8 ;
DESIGN test ;
UNITS DISTANCE MICRONS 1000 ;
DIEAREA ( 0 0 ) ( 10000 10000 ) ;
"""

TAIL = """\
COMPONENTS 1 ;
- u1 C1 + PLACED ( 0 0 ) N ;
END COMPONENTS
NETS 1 ;
- n1 ( u1 A ) {net_clause}
  + ROUTED M3 ( 100 100 ) ( 900 100 ) ;
END NETS
END DESIGN
"""

# The real form: one ';' ends the rule, and the '+ LAYER' lines carry no terminator.
RULES = """\
NONDEFAULTRULES 2 ;
- CTS_2W2S
  + LAYER M3 WIDTH 200 SPACING 200 WIREEXT 100
  + LAYER M4 WIDTH 200 SPACING 200
  ;
- PG_3W3S
  + HARDSPACING
  + LAYER M9 WIDTH 600 SPACING 600
  ;
END NONDEFAULTRULES
"""


def _parse(tmp_path, text, name="t.def", parse_net=True):
    path = tmp_path / name
    path.write_text(text)
    with contextlib.redirect_stdout(io.StringIO()):     # the parser is chatty
        return DefParser(str(path), parse_net=parse_net, parse_specialnet=parse_net)


def _def_text(rules=RULES, net_clause="+ NONDEFAULTRULE CTS_2W2S",
              after_components=False):
    if after_components:
        return HEAD + TAIL.format(net_clause=net_clause).replace(
            "END COMPONENTS\n", "END COMPONENTS\n" + rules, 1)
    return HEAD + rules + TAIL.format(net_clause=net_clause)


# -- the section itself -------------------------------------------------------------

def test_real_rule_form_parses(tmp_path):
    """One ';' per rule, '+ LAYER' clauses with no terminator of their own."""
    rules = _parse(tmp_path, _def_text()).getNdrRules()
    assert sorted(rules) == ["CTS_2W2S", "PG_3W3S"]

    cts = rules["CTS_2W2S"]
    assert cts.hardspacing is False
    assert sorted(cts.layers) == ["M3", "M4"]
    assert cts.layers["M3"].width == 200
    assert cts.layers["M3"].spacing == 200
    assert cts.layers["M3"].wireext == 100
    # A field the rule omits stays None, so a caller can fall back per field.
    assert cts.layers["M4"].wireext is None

    assert rules["PG_3W3S"].hardspacing is True
    assert rules["PG_3W3S"].layers["M9"].width == 600


def test_rule_distances_stay_in_database_units(tmp_path):
    """Values are read as written, like DefTrack offsets - the caller scales them.

    Dividing inside the parser would be wrong twice over: the parser does not know the
    DEF's unit until UNITS is read, and every other structural value it returns is raw.
    """
    rules = _parse(tmp_path, _def_text()).getNdrRules()
    assert rules["CTS_2W2S"].layers["M3"].width == 200      # not 0.2
    assert isinstance(rules["CTS_2W2S"].layers["M3"].width, int)


def test_rule_spanning_many_lines_is_one_rule(tmp_path):
    """A rule's clauses are joined to its ';' before being split."""
    rules = _parse(tmp_path, _def_text()).getNdrRules()
    assert len(rules["CTS_2W2S"].layers) == 2


def test_decimal_and_diagwidth_fields(tmp_path):
    body = textwrap.dedent("""\
    NONDEFAULTRULES 1 ;
    - WIDE
      + LAYER M5 DIAGWIDTH 0.18 WIDTH 180 SPACING 0.2 ;
    END NONDEFAULTRULES
    """)
    rule = _parse(tmp_path, HEAD + body + TAIL.format(
        net_clause="+ NONDEFAULTRULE WIDE")).getNdrRules()["WIDE"]
    layer = rule.layers["M5"]
    assert layer.diagwidth == pytest.approx(0.18)     # decimal kept as float
    assert layer.width == 180                         # integer stays an int
    assert layer.spacing == pytest.approx(0.2)


def test_layer_named_without_fields_keeps_an_empty_entry(tmp_path):
    """'+ LAYER M1' on its own names the layer and says nothing about it.

    Kept as an entry with every field None rather than dropped, because that is what the
    rule states: a caller falls back to the LEF default per field.
    """
    body = "NONDEFAULTRULES 1 ;\n- BARE\n  + LAYER M1\n  ;\nEND NONDEFAULTRULES\n"
    rule = _parse(tmp_path, HEAD + body + TAIL.format(
        net_clause="+ NONDEFAULTRULE BARE")).getNdrRules()["BARE"]
    assert sorted(rule.layers) == ["M1"]
    assert rule.layers["M1"].width is None
    assert rule.layers["M1"].spacing is None


def test_rule_with_no_layer_clause_warns_and_is_kept(tmp_path):
    """A rule naming no layer is reported - and still recorded, not discarded.

    The same discipline as __extractTracks: one clause we cannot use is a warning, never
    a reason to lose the components, die area and nets that come after it.
    """
    body = "NONDEFAULTRULES 1 ;\n- EMPTY\n  + HARDSPACING\n  ;\nEND NONDEFAULTRULES\n"
    path = tmp_path / "empty.def"
    path.write_text(HEAD + body + TAIL.format(net_clause="+ NONDEFAULTRULE EMPTY"))
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        parser = DefParser(str(path), parse_net=True, parse_specialnet=True)

    assert "EMPTY" in captured.getvalue()                 # reported
    assert parser.getNdrRules()["EMPTY"].layers == {}     # kept anyway
    assert parser.getNdrRules()["EMPTY"].hardspacing is True
    assert len(parser.getAllComponents()) == 1            # nothing else lost
    assert len(parser.getAllNets()) == 1


# -- how nets reach a rule ----------------------------------------------------------

def test_net_reference_resolves_to_the_rule_name(tmp_path):
    net = _parse(tmp_path, _def_text()).getNet("n1")
    assert net.wiring[0].rule == "CTS_2W2S"


def test_net_without_a_rule_gets_the_default(tmp_path):
    net = _parse(tmp_path, _def_text(net_clause="+ USE SIGNAL")).getNet("n1")
    assert net.wiring[0].rule == "default"


def test_rule_reference_after_the_wiring_is_found(tmp_path):
    """'+ NONDEFAULTRULE X' may sit on either side of the wiring.

    The header/wiring split cuts the wiring text at the first non-wiring clause, so a
    trailing rule clause belonged to neither part and was dropped - silently leaving the
    net on the default rule.
    """
    text = HEAD + RULES + """\
COMPONENTS 1 ;
- u1 C1 + PLACED ( 0 0 ) N ;
END COMPONENTS
NETS 1 ;
- n1 ( u1 A )
  + ROUTED M3 ( 100 100 ) ( 900 100 )
  + NONDEFAULTRULE CTS_2W2S ;
END NETS
END DESIGN
"""
    net = _parse(tmp_path, text, name="late.def").getNet("n1")
    assert net.wiring[0].rule == "CTS_2W2S"


def test_taper_rule_still_beats_the_net_rule(tmp_path):
    text = HEAD + RULES + """\
COMPONENTS 1 ;
- u1 C1 + PLACED ( 0 0 ) N ;
END COMPONENTS
NETS 1 ;
- n1 ( u1 A ) + NONDEFAULTRULE CTS_2W2S
  + ROUTED M3 TAPERRULE PG_3W3S ( 100 100 ) ( 900 100 ) ;
END NETS
END DESIGN
"""
    assert _parse(tmp_path, text, name="taper.def").getNet("n1").wiring[0].rule == "PG_3W3S"


# -- section order ------------------------------------------------------------------

def test_late_section_is_read_when_nets_are_parsed(tmp_path):
    """With nets enabled the parse runs on past COMPONENTS, so a late section is seen."""
    rules = _parse(tmp_path, _def_text(after_components=True)).getNdrRules()
    assert sorted(rules) == ["CTS_2W2S", "PG_3W3S"]


def test_late_section_is_not_read_when_parsing_stops_early(tmp_path):
    """Without nets the parse stops at END COMPONENTS and never reaches a late section.

    This is the documented limit, not a bug to fix: it is the same early-return that
    keeps the existing component-only flows cheap. The metal flow always enables nets,
    so it always sees the section.
    """
    rules = _parse(tmp_path, _def_text(after_components=True),
                   parse_net=False).getNdrRules()
    assert rules == {}


def test_disabling_ndr_parsing_skips_the_section(tmp_path):
    path = tmp_path / "t.def"
    path.write_text(_def_text())
    with contextlib.redirect_stdout(io.StringIO()):
        parser = DefParser(str(path), parse_net=True, parse_specialnet=True,
                           parse_ndr=False)
    assert parser.getNdrRules() == {}
    assert len(parser.getAllNets()) == 1        # nets still parsed
