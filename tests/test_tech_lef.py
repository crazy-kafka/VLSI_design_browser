"""Tech LEF layer parsing.

`TlefParser` had never been used by the application before the metal-density work, so
these tests were written against the shapes real tech LEFs actually contain rather than
against tidy synthetic ones. Two of them pin bugs that produce a *wrong* result with no
error, which is why the fixtures reproduce the real stanzas verbatim where possible:

- a layer that declares a `SPACINGTABLE` and no plain `SPACING` used to end up with
  `spacing == 0.0`, which silently disables the spacing expansion in the metric;
- a spacing table's `WIDTH <breakpoint> ...` rows are shape-identical to the layer's own
  `WIDTH` statement, so a line-by-line scan reads them as the default width.

The Nangate45 stanzas here are copied from
`OpenROAD-flow-scripts/flow/platforms/nangate45/lef/NangateOpenCellLibrary.tech.lef`.
"""
import pytest

from vlsi_viewer.parsers import TlefParser

# Verbatim from the real Nangate45 tech LEF, including the trailing spaces the tool
# wrote after SPACINGTABLE and after each row.
NANGATE_METAL2 = """LAYER metal2
  TYPE ROUTING ;
  SPACINGTABLE
    PARALLELRUNLENGTH    0.0000     0.3000     0.9000     1.8000     2.7000     4.0000
      WIDTH 0.0000       0.0700     0.0700     0.0700     0.0700     0.0700     0.0700
      WIDTH 0.0900       0.0700     0.0900     0.0900     0.0900     0.0900     0.0900
      WIDTH 0.2700       0.0700     0.0900     0.2700     0.2700     0.2700     0.2700
      WIDTH 1.5000       0.0700     0.0900     0.2700     0.5000     0.9000     1.5000      ;
  WIDTH 0.07 ;
  PITCH 0.19 ;
  DIRECTION VERTICAL ;
  OFFSET 0.095 0.07 ;
  RESISTANCE RPERSQ 0.25 ;
  THICKNESS 0.14 ;
END metal2
"""


def _layers(tmp_path, text, name="tech.lef"):
    path = tmp_path / name
    path.write_text(text)
    return TlefParser(str(path)).layers


def _routing(layers):
    return {n: L for n, L in layers.items() if L.type == "ROUTING"}


# -- layer kinds -------------------------------------------------------------------

def test_non_routing_layers_are_returned_and_identifiable(tmp_path):
    """Every LAYER is parsed, including cut/masterslice/overlap - the caller filters.

    A real tech LEF is roughly half non-routing: the Nangate45 file has 22 LAYER blocks
    of which only 10 are TYPE ROUTING.
    """
    layers = _layers(tmp_path, """LAYER poly
  TYPE MASTERSLICE ;
END poly
LAYER metal1
  TYPE ROUTING ;
  WIDTH 0.07 ;
  PITCH 0.14 ;
  DIRECTION HORIZONTAL ;
END metal1
LAYER via1
  TYPE CUT ;
  WIDTH 0.07 ;
END via1
LAYER OVERLAP
  TYPE OVERLAP ;
END OVERLAP
""")
    assert sorted(layers) == ["OVERLAP", "metal1", "poly", "via1"]
    assert list(_routing(layers)) == ["metal1"]


# -- spacing -----------------------------------------------------------------------

def test_unqualified_spacing_wins_over_conditional_clauses(tmp_path):
    """A bare 'SPACING x ;' is the layer default; the conditional clauses are not.

    The real 90 nm shape runs 0.180 / 0.18 LENGTHTHRESHOLD / 0.22 RANGE / 0.60 RANGE. A
    last-match-wins scan keeps 0.60 - 3.3x too large - which inflates every wire's
    keep-out in the metric.
    """
    layers = _layers(tmp_path, """LAYER METAL1
  TYPE ROUTING ;
  WIDTH 0.160 ;
  SPACING 0.180 ;
  SPACING 0.18 LENGTHTHRESHOLD 1.0 ;
  SPACING 0.22 RANGE 0.3 10.0 USELENGTHTHRESHOLD ;
  SPACING 0.60 RANGE 10.05 100000.0 ;
  PITCH 0.410 ;
  DIRECTION HORIZONTAL ;
END METAL1
""")
    assert layers["METAL1"].spacing == pytest.approx(0.18)


def test_spacing_table_supplies_spacing_when_no_plain_clause_exists(tmp_path):
    """A table-only layer must not come out with spacing 0.

    This is the Nangate45 metal2..metal10 case: 9 of the 10 routing layers declare a
    SPACINGTABLE and no plain SPACING at all, so a missing table reader leaves spacing
    at its 0.0 initialiser and the metric silently stops being a track-utilisation
    measure.
    """
    layer = _routing(_layers(tmp_path, NANGATE_METAL2))["metal2"]
    assert layer.spacing == pytest.approx(0.07)


def test_spacing_table_breakpoints_do_not_drag_the_minimum_to_zero(tmp_path):
    """The table's row/column headers are widths and run lengths, not spacings.

    PARALLELRUNLENGTH starts at 0.0000 and every WIDTH row opens with its own
    breakpoint, so a naive 'minimum number in the table' would return 0.
    """
    layer = _routing(_layers(tmp_path, NANGATE_METAL2))["metal2"]
    assert layer.spacing > 0


@pytest.mark.parametrize("width_line_first", [True, False])
def test_spacing_table_rows_do_not_clobber_the_default_width(tmp_path, width_line_first):
    """'WIDTH <breakpoint> <spacings>...' rows must not be read as the layer WIDTH.

    Both clause orders are checked. Nangate45 happens to write WIDTH *after* the table,
    which repairs the damage; the LEF grammar lists WIDTH *before* SPACINGTABLE, and in
    that order the clobber sticks.
    """
    table = """  SPACINGTABLE
    PARALLELRUNLENGTH 0.0000 0.3000
      WIDTH 0.0000 0.0700 0.0700
      WIDTH 0.0900 0.0700 0.0900 ;
"""
    body = f"""LAYER metal9
  TYPE ROUTING ;
  PITCH 1.6 ;
  DIRECTION HORIZONTAL ;
{table if not width_line_first else ''}  WIDTH 0.8 ;
{table if width_line_first else ''}END metal9
"""
    layer = _routing(_layers(tmp_path, body))["metal9"]
    assert layer.width == pytest.approx(0.8)
    assert layer.spacing == pytest.approx(0.07)


def test_oneline_spacing_table_is_not_mistaken_for_spacings(tmp_path):
    """'SPACINGTABLE TWOWIDTHS WIDTH ...' on one line carries breakpoints only."""
    layers = _layers(tmp_path, """LAYER m3
  TYPE ROUTING ;
  WIDTH 0.1 ;
  SPACING 0.1 ;
  SPACINGTABLE TWOWIDTHS WIDTH 0.1 0.1 0.2 0.3 ;
  PITCH 0.2 ;
  DIRECTION HORIZONTAL ;
END m3
""")
    assert layers["m3"].spacing == pytest.approx(0.1)
    assert layers["m3"].width == pytest.approx(0.1)


# -- width fallbacks ---------------------------------------------------------------

def test_missing_width_falls_back_to_minwidth(tmp_path):
    """Some layers declare only MINWIDTH; width must not stay 0."""
    layers = _layers(tmp_path, """LAYER m2
  TYPE ROUTING ;
  MINWIDTH 0.05 ;
  SPACING 0.05 ;
  PITCH 0.1 ;
  DIRECTION VERTICAL ;
END m2
LAYER m3
  TYPE ROUTING ;
  SPACING 0.05 ;
  PITCH 0.1 ;
END m3
""")
    assert layers["m2"].width == pytest.approx(0.05)
    assert layers["m3"].width == 0.0        # honestly unknown, not silently invented


# -- TYPE handling -----------------------------------------------------------------

def test_lef58_type_does_not_overwrite_the_base_type(tmp_path):
    """A LEF58_TYPE property describes a variant; it must not replace TYPE.

    Otherwise a routing layer carrying 'PROPERTY LEF58_TYPE "TYPE NWELL ;"' loses
    'ROUTING' and drops out of every routing-layer filter.

    The property is written *last* on purpose: consuming a property statement must stop at
    its own semicolon, and with the property first an over-consuming reader would still pass
    this test by accident, having already read the statements above.
    """
    layers = _layers(tmp_path, """LAYER m4
  TYPE ROUTING ;
  WIDTH 0.1 ;
  SPACING 0.1 ;
  PITCH 0.2 ;
  DIRECTION VERTICAL ;
  PROPERTY LEF58_TYPE "TYPE NWELL ;" ;
END m4
""")
    assert layers["m4"].type == "ROUTING"
    assert layers["m4"].lef58_type == "NWELL"
    assert layers["m4"].width == pytest.approx(0.1)
    assert layers["m4"].spacing == pytest.approx(0.1)
    assert layers["m4"].pitch_y == pytest.approx(0.2)
    assert list(_routing(layers)) == ["m4"]


# -- property payloads are not layer statements -------------------------------------
#
# The stanzas below are verbatim from `dev_plan/issue.tech_layer_detect.md`, a real 18-layer
# design's tech LEF. A property's value is a mini-language belonging to that property, but
# the stanza scanner reads it as layer statements: a quoted SPACINGTABLE body supplied a
# spacing (from its PRL breakpoints, one of them negative) and a quoted LEF58_SPACING
# supplied another (from its conditional clauses). The layer declares no default spacing at
# all, and saying so is the parser's job - the `pitch - width` fallback belongs to
# `TechRouting`, and is tested there.

REPORT_M5 = """LAYER M5
   TYPE ROUTING ;
   DIRECTION HORIZONTAL ;
   PITCH 0.076 0.076 ;
   OFFSET 0.000 ;
   WIDTH 0.038 ;
   MINWIDTH 0.038 ;
   MAXWIDTH 2.1 ;
   PROPERTY LEF58_SPACINGTABLE "
   SPACINGTABLE
   DIRECTIONALSPANLENGTH
   EXACTSPANLENGTHSPACING 0.0380 TO 0.038 PRL -0.0765 0.038 0.114 0.180
   EXACTSPANLENGTHSPACING 0.0380 TO 0.060 PRL -0.2000 0.199
   SPANLENGTH   0.0000       0.1800    0.1800 0.1800
   SPANLENGTH   0.2305       0.0800   0.1300 0.1590 ;
   ";
END M5
"""

REPORT_B1 = """LAYER B1
   TYPE ROUTING ;
   DIRECTION HORIZONTAL ;
   PITCH 0.126 0.126 ;
   OFFSET 0.000 0.000 ;
   WIDTH 0.062 ;
   PROPERTY LEF58_SPACINGTABLE "
   SPACINGTABLE TWOWIDTHS
   WIDTH 0.0            0.064  0.089  0.110  0.133   0.190   0.450
   WIDTH 0.155 PRL 0.25   0.089  0.089  0.110  0.133   0.190   0.450
   ";
   PROPERTY LEF58_SPACING "
   SPACING 0.089 ENDINLINE 0.09 WITHIN 0.0335 PARALLELEDGE 0.089 WITHIN 0.0985 MINLENGTH 0.063 ;
   SPACING 0.126 ENDINLINE 0.09 WITHIN 0.0335 PARALLELEDGE 0.1055 WITHIN 0.0985 MINLENGTH 0.063 ENCLOSECUT BELOW 0.045 CUTSPACING 0.152 ;
   ";
END B1
"""


def test_a_quoted_spacing_table_does_not_supply_the_layer_spacing(tmp_path):
    """M5's table lives inside a property, and its numbers are not the layer's rules.

    Ingested, the minimum is -0.2 - a PRL breakpoint - which the `spacing <= 0` guard turns
    into a plausible-looking 0.038 by accident. The parser has to say "no spacing stated",
    because the fallback for that is a documented decision and this is not.
    """
    layers = _layers(tmp_path, REPORT_M5)
    assert layers["M5"].spacing == 0.0
    assert layers["M5"].width == pytest.approx(0.038)
    assert (layers["M5"].pitch_x, layers["M5"].pitch_y) == pytest.approx((0.076, 0.076))


def test_a_quoted_property_does_not_open_table_mode(tmp_path):
    """The payload neither contributes spacings nor swallows the statements after it."""
    layers = _layers(tmp_path, REPORT_M5.replace("   \";\nEND M5", "   \";\n  SPACING 0.5 ;\nEND M5"))
    assert layers["M5"].spacing == pytest.approx(0.5)


def test_a_quoted_spacing_property_does_not_contribute_conditionals(tmp_path):
    """B1: two conditional `SPACING` clauses inside a quoted LEF58_SPACING.

    They are rules for specific geometry, not the layer's default, and the tool showed the
    smaller of them (0.089) as the layer's spacing.
    """
    layers = _layers(tmp_path, REPORT_B1)
    assert layers["B1"].spacing == 0.0
    assert layers["B1"].spacing != pytest.approx(0.089)
    assert layers["B1"].spacing != pytest.approx(0.064)


def test_an_unquoted_property_does_not_swallow_the_stanza(tmp_path):
    """LEF also allows `PROPERTY name value ;` with no quotes.

    A reader that waited for a closing quote would run past it - to the next quoted line, or
    to the end of the layer, losing every statement in between.
    """
    layers = _layers(tmp_path, """LAYER m9
  TYPE ROUTING ;
  PROPERTY FOOBAR 1 ;
  WIDTH 0.1 ;
  SPACING 0.1 ;
  PITCH 0.2 ;
  DIRECTION VERTICAL ;
  PROPERTY LEF58_TYPE "TYPE NWELL ;" ;
END m9
""")
    assert layers["m9"].width == pytest.approx(0.1)
    assert layers["m9"].spacing == pytest.approx(0.1)
    assert layers["m9"].pitch_x == pytest.approx(0.2)
    assert layers["m9"].direction == "VERTICAL"
    assert layers["m9"].lef58_type == "NWELL"


def test_a_property_whose_quote_opens_on_the_next_line(tmp_path):
    """How `asap7` writes it: the statement line ends, the payload starts on the next one.

    That trailing-space form is real - `PROPERTY LEF58_SPACING ` with the quote on the line
    below - and a reader keyed on the statement line's own quote would eat the layer.
    """
    layers = _layers(tmp_path, """LAYER m7
  TYPE ROUTING ;
  WIDTH 0.1 ;
  PITCH 0.2 ;
  DIRECTION VERTICAL ;
  PROPERTY LEF58_SPACING
    " SPACING 0.9 ENDOFLINE 0.1 WITHIN 0.08 PARALLELEDGE 0.1 WITHIN 0.08 ; " ;
  SPACING 0.1 ;
END m7
""")
    assert layers["m7"].spacing == pytest.approx(0.1)      # the clause after the property
    assert layers["m7"].width == pytest.approx(0.1)
    assert layers["m7"].pitch_x == pytest.approx(0.2)


# -- region layers -----------------------------------------------------------------

def test_a_region_property_is_captured_however_it_is_spelled(tmp_path):
    """`M2_FB1`'s clause is spelled `REGION FB1 BASEDLAYE R M2` - a space inside the keyword.

    The marker is what matters (the layer is region-defined), but the names are worth
    reading too: an exact grammar quietly left this one layer with no region at all, which
    is how it kept its place in the routing list while its neighbours could be excluded.
    """
    layers = _layers(tmp_path, """LAYER M2_FB1
   TYPE ROUTING ;
   DIRECTION VERTICAL ;
   PITCH 0.038 0.038 ;
   PROPERTY LEF58_REGION " REGION FB1 BASEDLAYE R M2 ; " ;
   WIDTH 0.0190 ;
   SPACING 0.0190 ;
END M2_FB1
LAYER M3_FB1
   TYPE ROUTING ;
   DIRECTION HORIZONTAL ;
   PITCH 0.04 0.04 ;
   PROPERTY LEF58_REGION " REGION FB1 BASEDLAYER M3 ; " ;
   WIDTH 0.019 ;
   SPACING 0.029 ;
END M3_FB1
LAYER M1
   TYPE ROUTING ;
   DIRECTION HORIZONTAL ;
   PITCH 0.020 0.032 ;
   WIDTH 0.016 ;
   SPACING 0.016 ;
END M1
""")
    for name, base in (("M2_FB1", "M2"), ("M3_FB1", "M3")):
        assert layers[name].region_layer is True, name
        assert layers[name].region == "FB1", name
        assert layers[name].based_layer == base, name
    assert layers["M1"].region_layer is False
    assert layers["M1"].region is None


# -- punctuation and numeric forms -------------------------------------------------

@pytest.mark.parametrize("line,expected", [
    ("  DIRECTION VERTICAL ;", "VERTICAL"),
    ("  DIRECTION VERTICAL;", "VERTICAL"),      # no space before the semicolon
    ("  DIRECTION HORIZONTAL;", "HORIZONTAL"),
])
def test_direction_survives_missing_space_before_semicolon(tmp_path, line, expected):
    """Machine-generated stanzas omit the space; a blank direction mislabels H/V."""
    layers = _layers(tmp_path, f"""LAYER m5
  TYPE ROUTING ;
  WIDTH 0.1 ;
  SPACING 0.1 ;
  PITCH 0.2 ;
{line}
END m5
""")
    assert layers["m5"].direction == expected


def test_pitch_pair_and_single_forms(tmp_path):
    layers = _layers(tmp_path, """LAYER a
  TYPE ROUTING ;
  PITCH 0.34 0.17 ;
  DIRECTION HORIZONTAL ;
END a
LAYER b
  TYPE ROUTING ;
  PITCH 0.34 ;
  DIRECTION VERTICAL ;
END b
LAYER c
  TYPE ROUTING ;
  PITCH 3.4e-1 ;
  DIRECTION VERTICAL ;
END c
""")
    assert (layers["a"].pitch_x, layers["a"].pitch_y) == (pytest.approx(0.34),
                                                          pytest.approx(0.17))
    assert (layers["b"].pitch_x, layers["b"].pitch_y) == (pytest.approx(0.34),
                                                          pytest.approx(0.34))
    assert layers["c"].pitch_x == pytest.approx(0.34)     # exponent form


# -- ordering ----------------------------------------------------------------------

def test_layer_order_is_file_order(tmp_path):
    """The stack is read bottom-to-top from the file; it must not be sorted.

    The GUI's layer panel takes its order from here, and lexical sorting would put
    metal10 between metal1 and metal2.
    """
    names = [f"metal{i}" for i in range(1, 11)]
    text = "".join(f"""LAYER {n}
  TYPE ROUTING ;
  WIDTH 0.07 ;
  SPACING 0.07 ;
  PITCH 0.14 ;
  DIRECTION HORIZONTAL ;
END {n}
""" for n in names)
    assert list(_layers(tmp_path, text)) == names
