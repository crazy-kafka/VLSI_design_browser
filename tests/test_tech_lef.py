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
    """
    layers = _layers(tmp_path, """LAYER m4
  TYPE ROUTING ;
  PROPERTY LEF58_TYPE "TYPE NWELL ;" ;
  WIDTH 0.1 ;
  SPACING 0.1 ;
  PITCH 0.2 ;
  DIRECTION VERTICAL ;
END m4
""")
    assert layers["m4"].type == "ROUTING"
    assert layers["m4"].lef58_type == "NWELL"
    assert list(_routing(layers)) == ["m4"]


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
