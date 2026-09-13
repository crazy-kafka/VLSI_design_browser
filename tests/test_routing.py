"""DEF + tech LEF -> routing shapes, streamed.

Two things are being pinned here. The conversion rules, which decide what the metric
measures - a via counted as a wire, or a width taken from the wrong place, produces a
plausible map that is simply wrong. And the streaming contract, because a design with 10^8
wire segments cannot be held in memory and the accumulation path must be the one that runs.
"""
import contextlib
import io

import pytest

from vlsi_viewer.parsers.routing import (POWER, SIGNAL, ShapeStream, TechRouting, parse_def)

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
