"""DEF net / special-net parsing, checked against the DEF 5.8 reference.

`dev_plan/LEF_DEF_syntax reference.md` is the source of truth here: the syntax quoted in
the docstrings is taken from its NETS (572-595), Regular Wiring (597-611), SPECIALNETS
(613-628), Special Wiring (630-651) and appendix coordinate-convention (833-839)
sections. Each test pins one defect found in the audit recorded in
`dev_plan/def_net_parsing_audit.md`.

Net parsing is off by default, so nothing here runs in the product; the tests pass the
flags explicitly.
"""
import pytest

from vlsi_viewer.parsers.DEF.defParser import DefParser

# The parser needs DESIGN/UNITS/DIEAREA to build, and reads one section at a time.
HEADER = """DESIGN netcase ;
UNITS DISTANCE MICRONS 1000 ;
DIEAREA ( 0 0 ) ( 10000 10000 ) ;
COMPONENTS 1 ;
- u1 INV_X1 + PLACED ( 0 0 ) N ;
END COMPONENTS
"""


def _parse(tmp_path, body, name="case.def", **flags):
    path = tmp_path / name
    path.write_text(HEADER + body)
    defaults = {"parse_net": True, "parse_specialnet": True}
    defaults.update(flags)
    return DefParser(str(path), **defaults)


def _specialnets(tmp_path, statements):
    return _parse(tmp_path, "SPECIALNETS %d ;\n%sEND SPECIALNETS\nEND DESIGN\n"
                  % (len(statements), "".join(statements)))


def _nets(tmp_path, statements):
    return _parse(tmp_path, "NETS %d ;\n%sEND NETS\nEND DESIGN\n"
                  % (len(statements), "".join(statements)))


# -- finding 1: BUSBITCHARS names --------------------------------------------------

def test_bus_net_names_are_not_truncated(tmp_path):
    """A bus is one net per bit; truncating on '[' merges them into one DefNet."""
    parser = _nets(tmp_path, [
        "- data[0] ( u1 A ) ;\n",
        "- data[1] ( u1 A ) ;\n",
    ])
    assert sorted(n.net_name for n in parser.getAllNets()) == ["data[0]", "data[1]"]


def test_bus_pin_connection_is_kept(tmp_path):
    """'( u1 A[2] )' must not be dropped: NAME has to admit the bus brackets."""
    parser = _nets(tmp_path, ["- n1 ( u1 A[2] ) ;\n"])
    assert parser.getNet("n1").connect_pins == ["u1/A[2]"]


def test_pin_connection_maps_to_the_pin_name(tmp_path):
    parser = _nets(tmp_path, ["- VDD ( u1 A ) ( PIN VDD ) ;\n"])
    assert parser.getNet("VDD").connect_pins == ["u1/A", "VDD"]


# -- finding 2: negative coordinates ----------------------------------------------

def test_negative_coordinates_are_parsed(tmp_path):
    """DEF coordinates may be negative; the wiring classes must accept '-'."""
    parser = _nets(tmp_path, ["- n1 + ROUTED M1 ( -100 200 ) ( 500 200 ) ;\n"])
    wire = parser.getNet("n1").wiring[0]
    assert wire.from_pt == (-100, 200) and wire.to_pt == (500, 200)


def test_negative_coordinates_in_special_wiring(tmp_path):
    parser = _specialnets(tmp_path, ["- VSS + ROUTED M1 100 ( -50 -20 ) ( 400 -20 ) ;\n"])
    wire = parser.getNet("VSS").swiring[0]
    assert (wire.x0, wire.y0, wire.x1, wire.y1) == (-50, -20, 400, -20)


# -- finding 3: the RECT / POLYGON / VIA special-wiring forms ----------------------

def test_special_wire_rect_form(tmp_path):
    """'+ RECT layerName pt pt' has no routeWidth, so the old pattern never matched."""
    parser = _specialnets(tmp_path, ["- VDD + RECT M2 ( 0 0 ) ( 300 200 ) ;\n"])
    wire = parser.getNet("VDD").swiring[0]
    assert wire.shape == "RECT"
    assert (wire.x0, wire.y0, wire.x1, wire.y1) == (0, 0, 300, 200)


def test_special_wire_polygon_form(tmp_path):
    """'+ POLYGON layer pt pt pt ...' becomes its edges."""
    parser = _specialnets(
        tmp_path, ["- VDD + POLYGON M2 ( 0 0 ) ( 100 0 ) ( 100 100 ) ( 0 100 ) ;\n"])
    segs = parser.getNet("VDD").swiring
    assert {s.shape for s in segs} == {"POLYGON"}
    assert [(s.x0, s.y0, s.x1, s.y1) for s in segs] == [
        (0, 0, 100, 0), (100, 0, 100, 100), (100, 100, 0, 100)]


def test_special_wire_via_form(tmp_path):
    """'+ VIA viaName [orient] pt ...' is counted, not built.

    The form was previously unmatchable, so the test that pinned it asserted the object it
    produced: a zero-length DefSWire carrying the via's name. Nothing reads that name - the
    metric counts a via point and asks nothing else about it, and one object per point is
    85 % of a real chip-level DEF's shapes. Recognition is what matters, and the count pins
    it, including for the multi-point arrays that a real power grid is written of.
    """
    parser = _specialnets(tmp_path, ["- VDD + VIA V12 N ( 500 600 ) ( 700 800 ) ;\n"])
    net = parser.getNet("VDD")
    assert net.via_points == 2
    assert net.swiring == []


def test_via_between_points_keeps_its_orientation(tmp_path):
    """A via replaces a point; its orientation must not be read as the via name."""
    parser = _nets(tmp_path, ["- n1 + ROUTED M1 ( 0 0 ) V12 N ( 400 0 ) ;\n"])
    wire = parser.getNet("n1").wiring[0]
    assert (wire.via, wire.via_orient) == ("V12", "N")
    assert wire.from_pt == (0, 0) and wire.to_pt == (400, 0)


# -- finding 4: + SHAPE between the width and the routing points -------------------

def test_special_wire_with_shape_clause(tmp_path):
    """SPECIALNETS RING/PADRING/FOLLOWPIN put '+ SHAPE x' after the routeWidth."""
    parser = _specialnets(
        tmp_path, ["- VDD + ROUTED M1 100 + SHAPE RING ( 0 0 ) ( 1000 0 ) ;\n"])
    wire = parser.getNet("VDD").swiring[0]
    assert (wire.width, wire.x0, wire.y0, wire.x1, wire.y1) == (100, 0, 0, 1000, 0)


def test_special_wire_with_shape_and_style(tmp_path):
    parser = _specialnets(
        tmp_path, ["- VDD + ROUTED M1 250 + SHAPE STRIPE + STYLE 3 "
                   "( 0 0 ) ( 800 0 ) ;\n"])
    wire = parser.getNet("VDD").swiring[0]
    assert wire.width == 250 and wire.x1 == 800


# -- findings 5 / 13: every segment, not just the first ---------------------------

def test_all_segments_of_a_multi_point_wire(tmp_path):
    parser = _nets(tmp_path, ["- n1 + ROUTED M1 ( 0 0 ) ( 500 0 ) ( 500 500 ) ;\n"])
    segs = parser.getNet("n1").wiring
    assert [(s.from_pt, s.to_pt) for s in segs] == [
        ((0, 0), (500, 0)), ((500, 0), (500, 500))]


def test_all_segments_of_a_multi_point_special_wire(tmp_path):
    parser = _specialnets(tmp_path, ["- VDD + ROUTED M1 100 ( 0 0 ) ( 500 0 ) ( 500 500 ) ;\n"])
    assert [(s.x0, s.y0, s.x1, s.y1) for s in parser.getNet("VDD").swiring] == [
        (0, 0, 500, 0), (500, 0, 500, 500)]


def test_new_layer_continues_the_same_wire(tmp_path):
    """'NEW layer routeWidth routingPoints' switches layer mid-wire."""
    parser = _nets(tmp_path, ["- n1 + ROUTED M1 ( 0 0 ) ( 500 0 ) "
                              "NEW M2 ( 500 0 ) ( 500 500 ) ;\n"])
    wires = parser.getNet("n1").wiring
    assert [(w.layer_name, w.from_pt, w.to_pt) for w in wires] == [
        ("M1", (0, 0), (500, 0)), ("M2", (500, 0), (500, 500))]


# -- findings 6 / 7: '*' means "reuse the last coordinate" -------------------------

def test_star_reuses_the_last_coordinate_across_the_path(tmp_path):
    """The reference's example: ( 100 100 ) ( * 300 ) ( 500 * ).

    Per spec the middle point is (100, 300) — reusing the previous *x* — and the last is
    (500, 300), reusing the previous *y*.
    """
    parser = _nets(tmp_path, ["- n1 + ROUTED M1 ( 100 100 ) ( * 300 ) ( 500 * ) ;\n"])
    assert [(s.from_pt, s.to_pt) for s in parser.getNet("n1").wiring] == [
        ((100, 100), (100, 300)), ((100, 300), (500, 300))]


def test_extension_only_point_uses_the_last_coordinate(tmp_path):
    """'( * * extValue )' is the spec's wire-extension-at-a-via form."""
    parser = _specialnets(tmp_path, ["- VDD + ROUTED M1 100 ( 200 300 ) ( * * 70 ) ;\n"])
    wire = parser.getNet("VDD").swiring[-1]
    assert (wire.x0, wire.y0, wire.e0) == (200, 300, 0)
    assert (wire.x1, wire.y1, wire.e1) == (200, 300, 70)
    assert wire.x1 is not None and wire.y1 is not None


@pytest.mark.parametrize("kind", ["net", "specialnet"])
def test_star_without_a_previous_coordinate_is_an_error(tmp_path, kind):
    """The spec forbids '*' on the first coordinate.

    The old code instead leaked the unresolved token: it copied the *other* end of the
    pair, so a one-point statement left a literal ``'*'`` (or ``None``) in the wire.
    """
    if kind == "net":
        body = ["- n1 + ROUTED M1 ( * 300 ) ( 500 300 ) ;\n"]
        parse = _nets
    else:
        body = ["- VDD + ROUTED M1 100 ( 0 * ) ;\n"]
        parse = _specialnets
    with pytest.raises(ValueError):
        parse(tmp_path, body)


# -- findings 8 / 12: connections are independent of the other clauses -------------

def test_special_net_connections_are_parsed(tmp_path):
    """SPECIALNETS carry '( comp pin )' too; previously connect_pins stayed empty."""
    parser = _specialnets(tmp_path, ["- VDD ( u1 A ) ( PIN VDD ) + ROUTED M1 100 "
                                     "( 0 0 ) ( 100 0 ) ;\n"])
    net = parser.getNet("VDD")
    assert net.connect_pins == ["u1/A", "VDD"]
    assert len(net.swiring) == 1


def test_connections_survive_a_nondefaultrule_clause(tmp_path):
    """'+ NONDEFAULTRULE' follows the connections; it must not short-circuit them."""
    parser = _nets(tmp_path, ["- n1 ( u1 A ) ( u1 B ) + NONDEFAULTRULE ndr1 "
                              "+ ROUTED M1 ( 0 0 ) ( 400 0 ) ;\n"])
    net = parser.getNet("n1")
    assert net.connect_pins == ["u1/A", "u1/B"]
    assert net.wiring[0].rule == "ndr1"


# -- findings 10 / 11: rule handling and the missing keywords ----------------------

def test_taperrule_lands_in_the_wire_rule(tmp_path):
    """The captured TAPERRULE was computed into an unused '_rule' and discarded."""
    parser = _nets(tmp_path, ["- n1 + ROUTED M1 TAPERRULE ndr2 ( 0 0 ) ( 400 0 ) ;\n"])
    assert parser.getNet("n1").wiring[0].rule == "ndr2"


def test_cover_and_noshield_wires_are_captured(tmp_path):
    """The spec allows {+ COVER | + FIXED | + ROUTED | + NOSHIELD}; only 3 were handled."""
    parser = _nets(tmp_path, [
        "- cov + COVER M1 ( 0 0 ) ( 100 0 ) ;\n",
        "- nos + NOSHIELD M2 ( 0 0 ) ( 200 0 ) ;\n",
    ])
    assert parser.getNet("cov").wiring[0].layer_name == "M1"
    assert parser.getNet("nos").wiring[0].layer_name == "M2"


# -- statements spanning lines, and the defaults guard ----------------------------

def test_a_statement_may_span_several_lines(tmp_path):
    parser = _nets(tmp_path, [
        "- n1\n  ( u1 A )\n  + ROUTED M1\n  ( 0 0 )\n  ( 500 0 )\n  ( 500 500 ) ;\n"])
    net = parser.getNet("n1")
    assert net.connect_pins == ["u1/A"]
    assert [(s.from_pt, s.to_pt) for s in net.wiring] == [
        ((0, 0), (500, 0)), ((500, 0), (500, 500))]


def test_trailing_clauses_are_not_read_as_vias(tmp_path):
    """'+ USE POWER' / '+ SOURCE DIST' follow the wiring; they are clauses, not vias.

    The wiring text is cut at the next non-wiring clause for exactly this reason - a
    loose keyword would otherwise be picked up as a via name by the token scan.
    """
    parser = _specialnets(tmp_path, ["- VDD + ROUTED M1 100 ( 0 0 ) ( 500 0 ) "
                                     "+ USE POWER + SOURCE DIST ;\n"])
    wires = parser.getNet("VDD").swiring
    assert len(wires) == 1
    assert (wires[0].via, wires[0].via_orient) == (None, None)
    assert (wires[0].x1, wires[0].y1) == (500, 0)


def test_net_parsing_is_off_by_default(tmp_path):
    """The product never enables this, so the audit's fixes must not change defaults."""
    path = tmp_path / "default.def"
    path.write_text(HEADER + "NETS 1 ;\n- n1 ( u1 A ) ;\nEND NETS\nEND DESIGN\n")
    parser = DefParser(str(path))
    assert parser.getAllNets() == []
    assert parser.getAllComponents(), "component parsing must be unaffected"


# -- real-DEF forms, validated against test/gcd_nangate45.def (OpenROAD) -----------

@pytest.mark.parametrize("spaced,glued", [
    ("( 100 200 ) ( 300 * )", "( 100 200 ) ( 300* )"),
    ("( 100 200 ) ( * 400 )", "( 100 200 ) ( *400 )"),
])
def test_glued_star_coordinates_match_the_spaced_forms(tmp_path, spaced, glued):
    """'*' may be glued to the number it reuses, not only spaced away from it.

    Real DEF writes both. The glued form is separated before tokenising rather than by
    relaxing the point pattern's separator - a relaxed pattern would let a malformed
    '(1234)' backtrack into x=123, y=4.
    """
    def geometry(clause):
        parser = _nets(tmp_path, [f"- n1 ( u1 A )\n  + ROUTED M3 {clause} ;\n"],
                       )
        return [(w.from_pt, w.to_pt) for w in parser.getNet("n1").wiring]

    assert geometry(spaced) == geometry(glued)


def test_malformed_single_number_point_is_dropped_not_split(tmp_path):
    """'(1234)' is not a DEF point. It must not be read as two coordinates.

    The point pattern requires a separator between x and y precisely so this fails
    instead of inventing a segment to (123, 4).
    """
    parser = _nets(tmp_path, ["- n1 ( u1 A )\n  + ROUTED M3 ( 100 200 ) (1234) ;\n"])
    wires = parser.getNet("n1").wiring
    assert [(w.from_pt, w.to_pt) for w in wires] == [((100, 200), (100, 200))]


def test_net_records_its_section_and_use(tmp_path):
    """NETS and SPECIALNETS share one table, so the origin has to be recorded.

    Without it there is no way to separate signal metal from power metal, and a power
    stripe reads as a routing hotspot.
    """
    parser = _nets(tmp_path, ["- sig ( u1 A ) + USE SIGNAL + ROUTED M3 ( 0 0 ) ( 100 0 ) ;\n"])
    assert parser.getNet("sig").is_special is False
    assert parser.getNet("sig").use == "SIGNAL"

    parser = _specialnets(tmp_path, ["- VDD ( * VDD ) + USE POWER\n  + ROUTED M9 600 ( 0 0 ) ( 0 900 ) ;\n"])
    vdd = parser.getNet("VDD")
    assert vdd.is_special is True
    assert vdd.use == "POWER"


def test_use_can_follow_the_wiring(tmp_path):
    """The grammar allows '+ USE' after the routing, so it is read from the statement."""
    parser = _specialnets(tmp_path, [
        "- GND ( * GND )\n  + ROUTED M1 340 ( 0 0 ) ( 100 0 )\n  + USE GROUND ;\n"])
    assert parser.getNet("GND").use == "GROUND"


def test_star_connection_is_not_an_error(tmp_path):
    """'( * GND )' opens a real power net. It is not a component/pin pair.

    re_net_conn requires two NAME tokens, so '*' matches nothing and the connection list
    comes out empty. Connections do not affect geometry, so that is acceptable - but it
    must not raise, and the wiring has to survive it.
    """
    parser = _specialnets(tmp_path, ["- VDD ( * VDD ) + USE POWER\n  + ROUTED M9 600 ( 0 0 ) ( 0 900 ) ;\n"])
    assert parser.getNet("VDD").connect_pins == []
    assert len(parser.getNet("VDD").swiring) == 1


def test_polygon_is_captured_whole_and_its_edges_still_emitted(tmp_path):
    """The filled shape is recorded, and the per-edge wires are kept alongside it.

    The edges cannot be reassembled into the ring - they carry no polygon id and the
    closing edge is never emitted - so the area has to be captured where the vertex list
    exists. Existing consumers are wire-oriented, so the edges stay.
    """
    parser = _specialnets(tmp_path, [
        "- VDD + USE POWER\n"
        "  + POLYGON M1 ( 0 0 ) ( 400 0 ) ( 400 300 ) ( 0 300 ) ;\n"])
    net = parser.getNet("VDD")

    assert len(net.polygons) == 1
    polygon = net.polygons[0]
    assert polygon.layer_name == "M1"
    assert polygon.pts == [(0, 0), (400, 0), (400, 300), (0, 300)]
    assert polygon.area() == pytest.approx(400 * 300)
    assert polygon.ring()[0] == polygon.ring()[-1]

    assert len(net.swiring) == 3                      # edges, unchanged: a 4-pt ring
    assert {s.shape for s in net.swiring} == {"POLYGON"}


def test_zero_width_special_shape_is_recorded_as_written(tmp_path):
    """'NEW M1 0 + SHAPE FOLLOWPIN' carries width 0, which means no wire.

    Real DEF uses this for via placements. The parser records it faithfully; treating 0
    as 'use the layer default' would invent a wire at every via.
    """
    parser = _specialnets(tmp_path, [
        "- VDD + USE POWER\n"
        "  NEW M3 0 + SHAPE STRIPE ( 62280 61600 ) via3_4_960_340_1_3_320_320 ;\n"])
    shape = parser.getNet("VDD").swiring[0]
    assert shape.width == 0
    assert shape.via == "via3_4_960_340_1_3_320_320"
    assert (shape.x0, shape.y0) == (shape.x1, shape.y1)      # a point, not a segment


def test_negative_coordinates_are_accepted(tmp_path):
    """Special wiring may sit at negative coordinates in real files."""
    parser = _specialnets(tmp_path, [
        "- GND + USE GROUND\n  + ROUTED m1 100 (-200 -200 )(200 -200 ) ;\n"])
    shape = parser.getNet("GND").swiring[0]
    assert (shape.x0, shape.y0, shape.x1, shape.y1) == (-200, -200, 200, -200)
    assert shape.layer_name == "m1"                          # lowercase layer name
