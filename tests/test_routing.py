"""DEF + tech LEF -> routing shapes, streamed.

Two things are being pinned here. The conversion rules, which decide what the metric
measures - a via counted as a wire, or a width taken from the wrong place, produces a
plausible map that is simply wrong. And the streaming contract, because a design with 10^8
wire segments cannot be held in memory and the accumulation path must be the one that runs.
"""
import contextlib
import io

import pytest

from vlsi_viewer.parsers.routing import (POWER, SHAPE_COUNTERS, SIGNAL, ShapeStream,
                                         TechRouting, parse_def)

TECH_LEF = """\
LAYER poly
  TYPE MASTERSLICE ;
END poly
LAYER metal1
  TYPE ROUTING ;
  WIDTH 0.07 ;
  SPACING 0.07 ;
  PITCH 0.14 ;
  DIRECTION HORIZONTAL ;
END metal1
LAYER via1
  TYPE CUT ;
  WIDTH 0.07 ;
END via1
LAYER metal2
  TYPE ROUTING ;
  WIDTH 0.07 ;
  SPACING 0.07 ;
  PITCH 0.19 ;
  DIRECTION VERTICAL ;
END metal2
LAYER metal3
  TYPE ROUTING ;
  MINWIDTH 0.05 ;
  PITCH 0.2 ;
  DIRECTION HORIZONTAL ;
END metal3
"""

HEAD = """\
VERSION 5.8 ;
DESIGN rt ;
UNITS DISTANCE MICRONS 1000 ;
DIEAREA ( 0 0 ) ( 10000 10000 ) ;
COMPONENTS 1 ;
- u1 INV + PLACED ( 0 0 ) N ;
END COMPONENTS
"""


class Collect:
    """A sink that records what it is handed, for assertions."""

    def __init__(self):
        self.rects = []
        self.diagonals = []
        self.polygons = []

    def add_rects(self, layer_index, scope, x0, y0, x1, y1):
        for i in range(x0.size):
            self.rects.append((layer_index, scope, float(x0[i]), float(y0[i]),
                               float(x1[i]), float(y1[i])))

    def add_diagonal(self, layer_index, scope, x0, y0, x1, y1, half):
        self.diagonals.append((layer_index, scope, x0, y0, x1, y1, half))

    def add_polygon(self, layer_index, scope, ring):
        self.polygons.append((layer_index, scope, ring))

    def on_layer(self, layer_index, scope=None):
        return [r for r in self.rects
                if r[0] == layer_index and (scope is None or r[1] == scope)]


def _tech(tmp_path, text=TECH_LEF):
    path = tmp_path / "tech.lef"
    path.write_text(text)
    with contextlib.redirect_stdout(io.StringIO()):
        return TechRouting.read([str(path)])


def _run(tmp_path, body, stream_kwargs=None, stream=None, name="rt.def"):
    path = tmp_path / name
    path.write_text(HEAD + body)
    if stream is None:
        stream = ShapeStream(_tech(tmp_path), Collect(), **(stream_kwargs or {}))
    with contextlib.redirect_stdout(io.StringIO()):
        routing = parse_def(str(path), stream=stream)
        stream.flush()
    return routing, stream


# -- tech LEF ----------------------------------------------------------------------

def test_only_routing_layers_are_kept_and_order_is_file_order(tmp_path):
    tech = _tech(tmp_path)
    assert [layer.name for layer in tech] == ["metal1", "metal2", "metal3"]
    assert [layer.index for layer in tech] == [0, 1, 2]
    assert tech["metal2"].is_horizontal is False
    assert tech.horizontal and tech.vertical


def test_spacing_falls_back_to_pitch_minus_width(tmp_path):
    """metal3 declares MINWIDTH and no SPACING; pitch - width is the best estimate."""
    tech = _tech(tmp_path)
    assert tech["metal3"].width == pytest.approx(0.05)
    assert tech["metal3"].spacing == pytest.approx(0.2 - 0.05)


def test_layer_with_no_width_at_all_is_marked_unusable(tmp_path):
    tech = _tech(tmp_path, """\
LAYER ghost
  TYPE ROUTING ;
  PITCH 0.2 ;
  DIRECTION HORIZONTAL ;
END ghost
""")
    assert tech["ghost"].usable is False
    assert tech.usable == []


# -- the reported design's tech LEF -------------------------------------------------
#
# Verbatim stanzas from `dev_plan/issue.tech_layer_detect.md` (a real 18-layer design), and
# the acceptance table from its report. It is one file doing three things at once: a region
# layer, a layer with no stated spacing, and a layer whose two pitch values differ.

REPORT_STANZAS = """\
LAYER M1
   TYPE ROUTING ;
   MASK 2 ;
   DIRECTION HORIZONTAL ;
   PITCH 0.020 0.032 ;
   OFFSET 0.0 ;
   WIDTH 0.016 ;
   SPACING 0.016 ;
END M1
LAYER M2_FB1
   TYPE ROUTING ;
   MASK 2 ;
   DIRECTION VERTICAL ;
   PITCH 0.038 0.038 ;
   OFFSET 0.000 0.000 ;
   PROPERTY LEF58_REGION " REGION FB1 BASEDLAYE R M2 ; " ;
   WIDTH 0.0190 ;
   MAXWIDTH 0.5 ;
   SPACING 0.0190 ;
END M2_FB1
LAYER M3_FB1
   TYPE ROUTING ;
   MASK 2 ;
   DIRECTION HORIZONTAL ;
   PITCH 0.04 0.04 ;
   PROPERTY LEF58_REGION " REGION FB1 BASEDLAYER M3 ; " ;
   WIDTH 0.019 ;
   SPACING 0.029 ;
END M3_FB1
LAYER M5
   TYPE ROUTING ;
   DIRECTION HORIZONTAL ;
   PITCH 0.076 0.076 ;
   OFFSET 0.000 ;
   WIDTH 0.038 ;
   MINWIDTH 0.038 ;
   SPACINGTABLE
     PARALLELRUNLENGTH 0 1.2
     WIDTH 0 0.038 0.038 ;
END M5
LAYER B1
   TYPE ROUTING ;
   DIRECTION HORIZONTAL ;
   PITCH 0.126 0.126 ;
   OFFSET 0.000 0.000 ;
   WIDTH 0.062 ;
   PROPERTY LEF58_SPACING "
   SPACING 0.089 ENDINLINE 0.09 WITHIN 0.0335 PARALLELEDGE 0.089 WITHIN 0.0985 ;
   ";
END B1
LAYER TM1
   TYPE ROUTING ;
   DIRECTION VERTICAL ;
   PITCH 0.4 0.4 ;
   WIDTH 0.2 ;
   SPACING 0.2 ;
END TM1
"""


def test_a_region_layer_is_not_a_routing_layer(tmp_path):
    """`M2_FB1`/`M3_FB1` declare TYPE ROUTING but their rules belong to a region over M2/M3.

    They are not track systems of the stack, so they are not routing layers - and the one
    spelled `BASEDLAYE R` must be excluded by the same rule as the cleanly spelled one, or
    the defect survives for exactly one of the layers.
    """
    tech = _tech(tmp_path, REPORT_STANZAS)
    assert [layer.name for layer in tech] == ["M1", "M5", "B1", "TM1"]
    assert tech["M1"].index == 0 and tech["TM1"].index == 3       # re-indexed, no gaps


def test_a_horizontal_layer_takes_the_y_pitch(tmp_path):
    """`PITCH xDistance yDistance`: x is the spacing of *vertical* tracks, y of horizontal.

    M1 is horizontal with `PITCH 0.020 0.032`, so 0.032 is the distance between its own
    tracks - and 0.016 + 0.016 equals it exactly, the usual factor of 1.0. Its capacity was
    60 % overstated while the x value was taken instead.

    The vertical control below is what stops this passing under "always take y".
    """
    tech = _tech(tmp_path, REPORT_STANZAS)
    assert tech["M1"].pitch == pytest.approx(0.032)
    vertical = _tech(tmp_path, REPORT_STANZAS.replace("DIRECTION HORIZONTAL ;\n   PITCH 0.020",
                                                      "DIRECTION VERTICAL ;\n   PITCH 0.020"))
    assert vertical["M1"].pitch == pytest.approx(0.020)


def test_the_reported_layers_read_the_reported_values(tmp_path):
    """The report's acceptance table, in one place.

    M5 and B1 state no default spacing - the rules that look like one live inside properties
    - so `pitch - width` supplies it, which is what the report expects and what the LEF's own
    table base row agrees with for B1.
    """
    tech = _tech(tmp_path, REPORT_STANZAS)
    table = {"M1": (0.016, 0.016, 0.032), "M5": (0.038, 0.038, 0.076),
             "B1": (0.062, 0.064, 0.126)}
    for name, (width, spacing, pitch) in table.items():
        layer = tech[name]
        assert (layer.width, layer.spacing, layer.pitch) == pytest.approx(
            (width, spacing, pitch)), name


def test_the_pitch_falls_back_along_the_axis_not_across_it(tmp_path):
    """A layer that declares only the other axis still gets a pitch rather than none."""
    tech = _tech(tmp_path, """\
LAYER h
  TYPE ROUTING ;
  DIRECTION HORIZONTAL ;
  WIDTH 0.1 ;
  SPACING 0.1 ;
  PITCH 0 0.4 ;
END h
LAYER v
  TYPE ROUTING ;
  DIRECTION VERTICAL ;
  WIDTH 0.1 ;
  SPACING 0.1 ;
  PITCH 0.4 0 ;
END v
""")
    assert tech["h"].pitch == pytest.approx(0.4)
    assert tech["v"].pitch == pytest.approx(0.4)


def test_a_diagonal_layer_keeps_the_previous_pitch_choice(tmp_path):
    """Nothing is perpendicular to a diagonal, so the rule has no axis to prefer.

    DIAG45 is not horizontal either - the layer table groups it with the vertical ones - and
    keeping the x value first means this change alters nothing for it.
    """
    tech = _tech(tmp_path, """\
LAYER d
  TYPE ROUTING ;
  DIRECTION DIAG45 ;
  WIDTH 0.1 ;
  SPACING 0.1 ;
  PITCH 0.2 0.3 ;
END d
""")
    assert tech["d"].pitch == pytest.approx(0.2)
    assert tech["d"].is_horizontal is False


def test_tech_lef_order_is_not_sorted(tmp_path):
    """metal10 must stay after metal2, or the GUI's layer panel order is nonsense."""
    body = "".join(f"""LAYER metal{n}
  TYPE ROUTING ;
  WIDTH 0.1 ;
  SPACING 0.1 ;
  PITCH 0.2 ;
  DIRECTION HORIZONTAL ;
END metal{n}
""" for n in (1, 2, 10))
    assert [layer.name for layer in _tech(tmp_path, body)] == ["metal1", "metal2", "metal10"]


# -- a range of the stack ----------------------------------------------------------

def test_trimmed_keeps_the_range_and_re_indexes_it(tmp_path):
    """The kept layers are numbered from zero again, and no gaps.

    Every grid is keyed by `layer.index` and the panel's rows are built in that order, so the
    numbers have to stay a list position - a slice would leave the kept layers numbered from
    `lo`, which is self-consistent for the grids and wrong for everything that reads a layer
    back by index.
    """
    tech = _tech(tmp_path).trimmed(2, 3)
    assert [layer.name for layer in tech] == ["metal2", "metal3"]
    for index, layer in enumerate(tech):
        assert layer.index == index
        assert tech.layers[layer.index] is layer
    assert tech["metal2"].direction == "VERTICAL"      # the layer's own rules came along
    assert tech["metal2"].pitch == pytest.approx(0.19)


def test_a_trimmed_stack_keeps_the_derived_views_in_step(tmp_path):
    tech = _tech(tmp_path).trimmed(1, 2)
    assert [layer.name for layer in tech.usable] == ["metal1", "metal2"]
    assert [layer.name for layer in tech.horizontal] == ["metal1"]
    assert [layer.name for layer in tech.vertical] == ["metal2"]
    assert len(tech) == 2


def test_a_trimmed_away_layer_is_no_longer_resolvable(tmp_path):
    """A new object, not an edit: `_by_name` is what decides whether a layer exists.

    Editing `layers` in place would leave the dropped names resolving, so the panel and the
    wiring would be measuring two different stacks - and only the picture would show it.
    """
    full = _tech(tmp_path)
    tech = full.trimmed(2, 3)
    assert tech.get("metal1") is None
    assert full.get("metal1") is not None              # the original is untouched
    assert tech.filtered_layers == frozenset({"metal1"})


def test_either_end_of_the_range_may_be_left_out(tmp_path):
    tech = _tech(tmp_path)
    assert [layer.name for layer in tech.trimmed(2)] == ["metal2", "metal3"]
    assert [layer.name for layer in tech.trimmed(None, 2)] == ["metal1", "metal2"]
    assert [layer.name for layer in tech.trimmed(1, 3)] == ["metal1", "metal2", "metal3"]
    assert tech.trimmed().filtered_layers == frozenset()


@pytest.mark.parametrize("lo, hi", [(0, None), (0, 3), (-1, 2), (2, 1), (1, 4), (None, 0),
                                    (4, None), (1, 99)])
def test_a_range_that_does_not_fit_the_stack_raises(tmp_path, lo, hi):
    """Refused rather than clamped, because an empty stack does not fail where the mistake is.

    `MetalData.kinds()` would come back with no maps at all and the window indexes the first
    of them, a long way from the flag that caused it. `lo=0` is the same trap more quietly:
    `layers[lo - 1:hi]` is `layers[-1:hi]` - empty on this stack, and silently *not* empty on
    a one-layer one.
    """
    with pytest.raises(ValueError, match="layer range"):
        _tech(tmp_path).trimmed(lo, hi)


def test_the_macro_fallback_counts_from_the_untrimmed_stack(tmp_path):
    """`--min-layer 2 --macro-block-layers 4` blocks metal1..metal4, not metal2..metal5.

    A macro that declares no OBS is guessed to block the bottom of the stack the *tech LEF*
    declares. If the guess moved with the range, a layer the caller asked to keep would lose
    capacity for a reason they did not ask for - and a trimmed run would no longer be the
    untrimmed run restricted to its layers.
    """
    tech = _tech(tmp_path)                             # metal1, metal2, metal3
    assert [layer.name for layer in tech.fallback_layers(2)] == ["metal1", "metal2"]
    trimmed = tech.trimmed(2, 3)
    assert [layer.name for layer in trimmed.fallback_layers(2)] == ["metal2"]
    assert [layer.name for layer in trimmed.fallback_layers(1)] == []
    # A depth that stops exactly above the range blocks nothing inside it.
    assert [layer.name for layer in tech.trimmed(3).fallback_layers(2)] == []
    assert [layer.name for layer in tech.trimmed(3).fallback_layers(3)] == ["metal3"]


def test_a_shape_on_a_trimmed_away_layer_is_not_an_unknown_layer(tmp_path):
    """Two absences told apart: the caller left the layer out, or the LEF never had it.

    Only one of them is worth a warning - an out-of-range layer is a choice, and a caller who
    reads `assert not data.warnings` as "this run is clean" would otherwise lose that check
    on every trimmed build.
    """
    tech = _tech(tmp_path).trimmed(2, 3)
    body = ("NETS 1 ;\n- n1 ( u1 A )\n"
            "  + ROUTED metal1 ( 0 0 ) ( 0 100 )\n"
            "  NEW metal2 ( 0 0 ) ( 0 100 )\n"
            "  NEW metal9 ( 0 0 ) ( 0 100 ) ;\n"
            "END NETS\nEND DESIGN\n")
    _routing, stream = _run(tmp_path, body, stream=ShapeStream(tech, Collect()))
    assert stream.n_filtered == 1                      # metal1, outside the range
    assert stream.n_unknown_layer == 1                 # metal9, never in the LEF at all
    assert [(r[0], r[1]) for r in stream.sink.rects] == [(0, 0)]   # metal2, now the bottom layer


# -- what a wire becomes -----------------------------------------------------------

def test_axis_aligned_wire_becomes_its_keepout_rectangle(tmp_path):
    """A minimum-width wire inflated by half its spacing covers exactly one track pitch.

    metal2: width 0.07, spacing 0.07, so the keep-out is 0.07 + 0.07 = 0.14 across - which
    is the layer's pitch, the property the whole metric rests on.
    """
    _routing, stream = _run(tmp_path, """\
NETS 1 ;
- n1 ( u1 A )
  + ROUTED metal2 ( 0 0 ) ( 0 1000 ) ;
END NETS
END DESIGN
""")
    rects = stream.sink.on_layer(1)
    assert len(rects) == 1
    _layer, _scope, x0, y0, x1, y1 = rects[0]
    # width/2 + spacing/2 each side across the wire; half-width extension plus spacing/2
    # beyond each end along it.
    assert (x1 - x0) == pytest.approx(0.07 / 2 + 0.07 / 2 + 0.07 / 2 + 0.07 / 2)
    assert (y1 - y0) == pytest.approx(1.0 + 0.07 / 2 + 0.07 / 2 + 0.07 / 2 + 0.07 / 2)
    assert (x1 - x0) == pytest.approx(0.14)          # one track pitch
    assert y0 == pytest.approx(-0.07, abs=1e-9)


def test_coordinates_are_converted_once_to_microns(tmp_path):
    routing, _stream = _run(tmp_path, """\
NETS 1 ;
- n1 ( u1 A ) + ROUTED metal1 ( 0 0 ) ( 2000 0 ) ;
END NETS
END DESIGN
""")
    assert routing.db_unit == 1000
    assert routing.boundary == [[0.0, 0.0], [0.0, 10.0], [10.0, 10.0], [10.0, 0.0]]


# -- vias --------------------------------------------------------------------------

def test_zero_length_regular_wire_is_omitted(tmp_path):
    """A via point has no extent, so it has no area. Half of a real DEF's segments."""
    _routing, stream = _run(tmp_path, """\
NETS 1 ;
- n1 ( u1 A )
  + ROUTED metal2 ( 500 500 ) ( 500 1500 )
  NEW metal1 ( 500 1500 ) via1_4 ;
END NETS
END DESIGN
""")
    assert stream.n_via == 1
    assert [r[0] for r in stream.sink.rects] == [1]      # only the metal2 wire


def test_zero_routewidth_special_shape_is_omitted(tmp_path):
    """'routeWidth 0' marks a via placement, not a zero-width wire.

    Substituting the layer default - the obvious reading - would invent a wire at every
    power-grid via, in the most visually prominent part of the map.
    """
    _routing, stream = _run(tmp_path, """\
SPECIALNETS 1 ;
- VDD + USE POWER
  NEW metal3 0 + SHAPE STRIPE ( 100 100 ) via3_4 ;
END SPECIALNETS
END DESIGN
""")
    assert stream.n_via == 1
    assert stream.sink.rects == []


# -- layers the tech LEF cannot route -----------------------------------------------
#
# A shape on a layer the tech LEF does not define, or declares without a width, is counted by
# *what it is* rather than by how many points it has - three different rules, plus the
# unusable-layer path, and 4.5 M shapes of the reporting design were of this kind. These are
# pinned because a fast path that decided counters without building shapes would have to
# reproduce every one of them.
SPECIAL_TECH = """\
LAYER metal1
  TYPE ROUTING ;
  WIDTH 0.1 ;
  SPACING 0.1 ;
  PITCH 0.2 ;
  DIRECTION HORIZONTAL ;
END metal1
LAYER metal2
  TYPE ROUTING ;
  SPACING 0.1 ;
  PITCH 0.2 ;
  DIRECTION VERTICAL ;
END metal2
"""


def _special(tmp_path, forms):
    body = "SPECIALNETS 1 ;\n- VDD + USE POWER\n" + forms + "\nEND SPECIALNETS\nEND DESIGN\n"
    stream = ShapeStream(_tech(tmp_path, SPECIAL_TECH), Collect())
    return _run(tmp_path, body, stream=stream)[1]


@pytest.mark.parametrize("forms, expected", [
    # A filled ring is one shape; its edges are counted separately, so it is 1 + 3, not 3.
    ("  + POLYGON XX ( 0 0 ) ( 100 0 ) ( 100 100 ) ( 0 100 ) ;",
     {"unknown": 1, "polygon_edges": 3}),
    # A rect is one shape.
    ("  + RECT XX ( 0 0 ) ( 100 100 ) ;", {"unknown": 1}),
    # A routed form is one shape per segment, and a single point is still one shape.
    ("  + ROUTED XX 100 ( 0 0 ) ( 100 0 ) ;", {"unknown": 1}),
    ("  + ROUTED XX 100 ( 0 0 ) ;", {"unknown": 1}),
    # A via is never an unknown layer: its name is a via name, not a layer name.
    ("  + VIA V12 ( 0 0 ) ( 100 100 ) ;", {"vias": 2, "unknown": 0}),
    # A layer declared without a width routes nothing, and says so once per shape - a special
    # form states its own width, so it reaches the geometry and only the lookup is counted.
    ("  + ROUTED metal2 100 ( 0 0 ) ( 0 100 ) ;", {"unusable": 1, "emitted": 1}),
])
def test_a_shape_on_a_layer_the_tech_lef_cannot_route_is_counted_by_what_it_is(
        tmp_path, forms, expected):
    stream = _special(tmp_path, forms)
    attributes = dict(SHAPE_COUNTERS)
    for counter, value in expected.items():
        assert getattr(stream, attributes[counter]) == value, counter


def test_a_regular_wire_on_an_unusable_layer_is_counted_twice(tmp_path):
    """Its width comes from the layer, so the lookup *and* the wire report it.

    The difference from the special case above is where the width comes from: a regular wire
    has none of its own, so a layer without one is reported once when the layer is looked up
    and again when the zero width is found.
    """
    body = "NETS 1 ;\n- n1 ( u1 A )\n  + ROUTED metal2 ( 0 0 ) ( 0 100 ) ;\nEND NETS\nEND DESIGN\n"
    stream = ShapeStream(_tech(tmp_path, SPECIAL_TECH), Collect())
    stream = _run(tmp_path, body, stream=stream)[1]
    assert stream.n_usable_layer_missing == 2
    assert stream.n_emitted == 0


def test_a_via_form_still_advances_the_star_coordinate(tmp_path):
    """'*' means "the last coordinate used", and a via form's points set it.

    A '+ VIA' array's points are still *scanned*; only their shapes are not built. The
    statement shares that coordinate state across its forms, so a fast path that skipped the
    tail to save the work would resolve the wire below against the wrong point - or raise,
    when the statement has no earlier point at all. This is the counterexample that killed
    the first version of that optimisation, so it is pinned here.
    """
    _routing, stream = _run(tmp_path, """\
SPECIALNETS 1 ;
- VDD + USE POWER
  + VIA V12 ( 100 200 ) ( 300 400 )
  NEW metal3 400 ( * 900 ) ( 800 900 ) ;
END SPECIALNETS
END DESIGN
""")
    assert stream.n_via == 2                       # counted, not built
    assert len(stream.sink.rects) == 1
    rect = stream.sink.rects[0]
    # The wire runs 300 -> 800 in database units, so '*' resolved to the via form's last
    # point; the keep-out expansion is symmetric, which leaves the midpoint where it was.
    assert (rect[2] + rect[4]) / 2 == pytest.approx((300 + 800) / 2 / 1000)


# -- width sources -----------------------------------------------------------------

def test_regular_wire_uses_the_layer_width(tmp_path):
    _routing, stream = _run(tmp_path, """\
NETS 1 ;
- n1 ( u1 A ) + ROUTED metal2 ( 0 0 ) ( 0 1000 ) ;
END NETS
END DESIGN
""")
    _, _s, x0, _y0, x1, _y1 = stream.sink.on_layer(1)[0]
    assert (x1 - x0) == pytest.approx(0.14)      # 0.07 width + 0.07 spacing


def test_nondefault_rule_overrides_width_and_spacing(tmp_path):
    """A 2W2S rule doubles both, so ignoring it halves a clock region's apparent metal.

    Also checks that the override is per field and per layer: a rule naming only metal2
    leaves metal1 alone, and a rule omitting SPACING keeps the layer's.
    """
    _routing, stream = _run(tmp_path, """\
NONDEFAULTRULES 1 ;
- CTS_2W2S
  + LAYER metal2 WIDTH 140 SPACING 140
  ;
END NONDEFAULTRULES
NETS 1 ;
- n1 ( u1 A ) + NONDEFAULTRULE CTS_2W2S + ROUTED metal2 ( 0 0 ) ( 0 1000 ) ;
END NETS
END DESIGN
""")
    _, _s, x0, _y0, x1, _y1 = stream.sink.on_layer(1)[0]
    assert (x1 - x0) == pytest.approx(0.14 + 0.14)      # doubled width and spacing


def test_rule_not_naming_a_layer_leaves_it_on_the_default(tmp_path):
    _routing, stream = _run(tmp_path, """\
NONDEFAULTRULES 1 ;
- WIDE_M2
  + LAYER metal2 WIDTH 140
  ;
END NONDEFAULTRULES
NETS 1 ;
- n1 ( u1 A ) + NONDEFAULTRULE WIDE_M2 + ROUTED metal1 ( 0 0 ) ( 1000 0 ) ;
END NETS
END DESIGN
""")
    # A horizontal wire is long in x and one width-plus-spacing thick in y.
    _, _s, _x0, y0, _x1, y1 = stream.sink.on_layer(0)[0]
    assert (y1 - y0) == pytest.approx(0.14)     # metal1's own width + spacing


def test_special_wire_states_its_own_width(tmp_path):
    _routing, stream = _run(tmp_path, """\
SPECIALNETS 1 ;
- VDD + USE POWER
  + ROUTED metal1 340 ( 0 0 ) ( 2000 0 ) ;
END SPECIALNETS
END DESIGN
""")
    # 2 um long in x; 0.34 um routeWidth plus spacing across in y.
    _, _s, _x0, y0, _x1, y1 = stream.sink.on_layer(0, POWER)[0]
    assert (y1 - y0) == pytest.approx(0.34 + 0.07)


# -- jogs --------------------------------------------------------------------------

def test_non_preferred_short_jog_is_dropped(tmp_path):
    """A horizontal blip on a vertical layer, shorter than one track pitch."""
    _routing, stream = _run(tmp_path, """\
NETS 1 ;
- n1 ( u1 A )
  + ROUTED metal2 ( 0 0 ) ( 0 1000 )
  NEW metal2 ( 0 1000 ) ( 100 1000 ) ;
END NETS
END DESIGN
""")
    assert stream.n_jog == 1
    assert len(stream.sink.on_layer(1)) == 1     # only the vertical wire


def test_preferred_short_stub_is_kept(tmp_path):
    """A short segment along the layer's own direction is real metal, whatever its length.

    Only non-preferred jogs are dropped - a blanket length threshold would quietly discard
    genuine stubs, which is why the rule is about direction and not just distance.
    """
    _routing, stream = _run(tmp_path, """\
NETS 1 ;
- n1 ( u1 A )
  + ROUTED metal1 ( 0 0 ) ( 100 0 ) ;
END NETS
END DESIGN
""")
    assert stream.n_jog == 0
    assert len(stream.sink.on_layer(0)) == 1


def test_jog_rule_can_be_disabled(tmp_path):
    _routing, stream = _run(tmp_path, """\
NETS 1 ;
- n1 ( u1 A )
  + ROUTED metal2 ( 0 0 ) ( 0 1000 )
  NEW metal2 ( 0 1000 ) ( 100 1000 ) ;
END NETS
END DESIGN
""", stream_kwargs={"min_segment": 0.0})
    assert stream.n_jog == 0
    assert len(stream.sink.on_layer(1)) == 2


# -- scope -------------------------------------------------------------------------

def test_scope_comes_from_use_then_from_the_section(tmp_path):
    _routing, stream = _run(tmp_path, """\
SPECIALNETS 1 ;
- VDD + USE POWER
  + ROUTED metal1 340 ( 0 0 ) ( 2000 0 ) ;
- VSS
  + ROUTED metal1 340 ( 0 0 ) ( 0 2000 ) ;
END SPECIALNETS
NETS 1 ;
- sig ( u1 A ) + USE SIGNAL + ROUTED metal2 ( 0 0 ) ( 0 1000 ) ;
END NETS
END DESIGN
""")
    assert len(stream.sink.on_layer(0, POWER)) == 2      # POWER stated, and section default
    assert len(stream.sink.on_layer(1, SIGNAL)) == 1


# -- other shapes ------------------------------------------------------------------

def test_diagonal_goes_to_the_diagonal_path_not_a_bounding_box(tmp_path):
    _routing, stream = _run(tmp_path, """\
NETS 1 ;
- n1 ( u1 A ) + ROUTED metal2 ( 0 0 ) ( 1000 1000 ) ;
END NETS
END DESIGN
""")
    assert len(stream.sink.rects) == 0
    assert len(stream.sink.diagonals) == 1
    _, _, x0, y0, x1, y1, half = stream.sink.diagonals[0]
    assert (x0, y0, x1, y1) == (0.0, 0.0, 1.0, 1.0)
    assert half == pytest.approx(0.07 / 2 + 0.07 / 2)


def test_special_rect_is_a_filled_shape_with_reversed_corners_normalised(tmp_path):
    _routing, stream = _run(tmp_path, """\
SPECIALNETS 1 ;
- VDD + USE POWER
  + RECT metal1 ( 2000 3000 ) ( 1000 1000 ) ;
END SPECIALNETS
END DESIGN
""")
    _, _s, x0, y0, x1, y1 = stream.sink.on_layer(0, POWER)[0]
    assert (x0, y0) == pytest.approx((1.0 - 0.035, 1.0 - 0.035))
    assert (x1, y1) == pytest.approx((2.0 + 0.035, 3.0 + 0.035))


def test_polygon_is_handed_over_as_a_ring(tmp_path):
    _routing, stream = _run(tmp_path, """\
SPECIALNETS 1 ;
- VDD + USE POWER
  + POLYGON metal1 ( 0 0 ) ( 1000 0 ) ( 1000 1000 ) ( 0 1000 ) ;
END SPECIALNETS
END DESIGN
""")
    assert len(stream.sink.polygons) == 1
    _layer, scope, ring = stream.sink.polygons[0]
    assert scope == POWER
    assert ring.shape[0] >= 4


# -- streaming contract -------------------------------------------------------------

def test_streaming_gives_the_same_shapes_as_accumulating(tmp_path):
    """The memory-saving path must not be a different path in behaviour.

    Driven from the same DEF with and without a sink: the streamed shapes, and the net count
    the parser reports, must match what the retaining parse produces.
    """
    body = "NETS 3 ;\n" + "".join(
        f"- n{i} ( u1 A ) + ROUTED metal2 ( {i} 0 ) ( {i} 1000 ) ;\n"
        for i in (100, 200, 300)) + "END NETS\nEND DESIGN\n"

    streamed = Collect()
    _routing, stream = _run(tmp_path, body,
                            stream=ShapeStream(_tech(tmp_path), streamed),
                            name="streamed.def")

    path = tmp_path / "plain.def"
    path.write_text(HEAD + body)
    with contextlib.redirect_stdout(io.StringIO()):
        from vlsi_viewer.parsers.DEF import DefParser
        parser = DefParser(str(path), parse_net=True, parse_specialnet=True)
        wires = [w for net in parser.getAllNets() for w in net.wiring]

    assert parser.n_nets == 3
    assert len(streamed.on_layer(1, SIGNAL)) == len(wires) == 3
    assert stream.n_via == 0 and stream.n_jog == 0


def test_a_sink_leaves_no_nets_behind(tmp_path):
    """Nets are handed over and dropped, so the parse does not grow with the design."""
    body = "".join(f"- n{i} ( u1 A ) + ROUTED metal2 ( {i * 10} 0 ) ( {i * 10} 500 ) ;\n"
                   for i in range(50))
    path = tmp_path / "many.def"
    path.write_text(HEAD + "NETS 50 ;\n" + body + "END NETS\nEND DESIGN\n")

    held = []
    with contextlib.redirect_stdout(io.StringIO()):
        from vlsi_viewer.parsers.DEF import DefParser
        parser = DefParser(str(path), parse_net=True, parse_specialnet=True,
                           sink=lambda net, dbu, ndrs: held.append(net.net_name))
    assert len(held) == 50                          # every net reached the sink
    assert parser.getAllNets() == []                # and none was kept


def test_section_count_mismatch_is_flagged(tmp_path, caplog):
    """A DEF whose declared nets exceed the parsed ones is reported, not silently short."""
    import logging
    body = "NETS 9 ;\n- n1 ( u1 A ) + ROUTED metal2 ( 0 0 ) ( 0 500 ) ;\nEND NETS\nEND DESIGN\n"
    path = tmp_path / "short.def"
    path.write_text(HEAD + body)
    with caplog.at_level(logging.WARNING, logger="vlsi_viewer.parsers.routing"):
        with contextlib.redirect_stdout(io.StringIO()):
            parse_def(str(path))
    assert any("9 NETS" in r.message for r in caplog.records)


# -- layer resolution ---------------------------------------------------------------

def test_wire_on_a_layer_absent_from_the_tech_lef_is_counted(tmp_path):
    _routing, stream = _run(tmp_path, """\
NETS 1 ;
- n1 ( u1 A ) + ROUTED metal9 ( 0 0 ) ( 0 1000 ) ;
END NETS
END DESIGN
""")
    assert stream.n_unknown_layer == 1
    assert stream.sink.rects == []
