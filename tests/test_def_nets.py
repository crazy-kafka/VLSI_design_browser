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


# -- VIRTUAL and the inline RECT: routingPoints' other two elements (reference 872-876) ----

def test_virtual_and_rect_together_the_way_the_reference_writes_them(tmp_path):
    """Example 7-12 verbatim, which is what makes it worth pinning:

        + ROUTED M1 ( 0 0 ) ( 5 0 ) VIRTUAL ( 7 1 ) RECT ( -3 0 -1 2 ) ( 7 7 ) ;

    Three properties, all from page 874. `VIRTUAL ( x y )` is "a virtual (non-physical
    zero-width) connection between the previous point and the new ( x y ) point", so the pair
    (5,0)-(7,1) is not a wire - but the new point *is* where the path continues from, so the
    last pair is (7,1)-(7,7). The rectangle is the previous point plus the deltas, (7-3, 1+0)
    to (7-1, 1+2), and leaves that point and the layer alone.

    Read as a via *name*, which is what the tokeniser did, VIRTUAL's point became a wire corner
    and the connection was measured as a full-width wire. A graph edge is not metal, and on a
    Manhattan design it need not be orthogonal either - which is where a real run's millions of
    "45-degree shapes" came from.
    """
    parser = _nets(tmp_path, ["- n1 ( u1 A ) + ROUTED M1 ( 0 0 ) ( 5 0 ) VIRTUAL ( 7 1 ) "
                              "RECT ( -3 0 -1 2 ) ( 7 7 ) ;\n"])
    net = parser.getNet("n1")
    assert [(w.from_pt, w.to_pt) for w in net.wiring] == [((0, 0), (5, 0)), ((7, 1), (7, 7))]
    assert net.rects == [("M1", 4, 1, 6, 3)]
    stats = parser.getStats()
    assert stats["virtual"] == 1 and stats["rects"] == 1


def test_an_inline_rect_does_not_move_the_current_point(tmp_path):
    """The last clause of that sentence: the RECT "leave[s] the current point unchanged"."""
    parser = _nets(tmp_path, ["- n1 + ROUTED M1 ( 0 0 ) ( 5 0 ) RECT ( 10 10 20 20 ) ( 5 7 ) ;\n"])
    net = parser.getNet("n1")
    assert [(w.from_pt, w.to_pt) for w in net.wiring] == [((0, 0), (5, 0)), ((5, 0), (5, 7))]
    assert net.rects == [("M1", 15, 10, 25, 20)]


def test_a_virtual_point_is_not_metal_in_special_wiring_either(tmp_path):
    """The special path emits its own segments, so the rule has to hold there too."""
    parser = _specialnets(tmp_path, ["- VDD + ROUTED M1 100 ( 0 0 ) ( 5 0 ) VIRTUAL ( 7 1 ) "
                                     "( 7 7 ) ;\n"])
    net = parser.getNet("VDD")
    assert [(s.x0, s.y0, s.x1, s.y1) for s in net.swiring] == [(0, 0, 5, 0), (7, 1, 7, 7)]
    assert parser.getStats()["virtual"] == 1


def test_virtual_takes_star_coordinates_like_any_other_point(tmp_path):
    """Page 874 gives VIRTUAL the same rule a point gets: reuse the previous value."""
    parser = _nets(tmp_path, ["- n1 + ROUTED M1 ( 0 0 ) ( 5 0 ) VIRTUAL ( * 7 ) ( 5 9 ) ;\n"])
    net = parser.getNet("n1")
    # The virtual point resolved to (5, 7) - the last x, and its own y - and the segment out of
    # it is real metal, so the path is (0,0)-(5,0) then (5,7)-(5,9).
    assert [(w.from_pt, w.to_pt) for w in net.wiring] == [((0, 0), (5, 0)), ((5, 7), (5, 9))]


def test_mask_clauses_are_not_read_as_virtual_points_or_rects(tmp_path):
    """Example 7-11's `MASK 3 (10 20)` and `MASK 031 VIA1_2` stay mask clauses.

    Both new elements collide with the mask grammar by sight: `MASK 031` is a bare integer
    where a point could start, and the reference notes it may be written with or without the
    leading zero.
    """
    parser = _nets(tmp_path, ["- n1 + ROUTED M1 ( 10 0 ) MASK 3 ( 10 20 ) VIA1_1 "
                              "NEW M2 ( 10 10 ) ( 20 10 ) MASK 1 ( 20 20 ) MASK 031 VIA1_2 ;\n"])
    net = parser.getNet("n1")
    assert [(w.layer_name, w.from_pt, w.to_pt) for w in net.wiring] == [
        ("M1", (10, 0), (10, 20)), ("M2", (10, 10), (20, 10)), ("M2", (20, 10), (20, 20))]
    stats = parser.getStats()
    assert stats["virtual"] == 0 and stats["rects"] == 0


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


def test_a_mask_clause_does_not_become_a_form_on_a_layer_called_ask(tmp_path):
    """`+ MASK 1` after a form's points is a clause, not a form on a layer named `ASK`.

    The guard that stops a keyword opening a form rejects the match at its first character -
    and the engine then advances one character and matches the rest of the word, so `MASK 1`
    was read as `layer=ASK, width=1`. The real run is a three-mask process, and this is where
    its 4.5 M `unknown` shapes and its `layers_not_into_tech: ["ASK"]` came from. The form that
    owned those points also ends early, which is how the geometry below is lost: the two-point
    M4 wire becomes one point, and the mask's own points are counted on a phantom layer.
    """
    import re

    from vlsi_viewer.parsers.DEF.compiledRe import CompiledRe

    body = ("- VDD + USE POWER\n"
            "  + ROUTED M4 40 ( 1000 1000 ) ( 2000 1000 ) + MASK 1 ( 3000 1000 ) ;\n")
    previous = CompiledRe.re_special_wiring_form
    without_guard = re.compile(r'(?=[+A-Za-z_])'
                               + previous.pattern[len(CompiledRe.FORM_FIRST):])
    seen = []
    try:
        for pattern in (without_guard, previous):  # before the fix, then after it
            CompiledRe.re_special_wiring_form = pattern
            parser = _specialnets(tmp_path, [body])
            seen.append((sorted(parser.layers_used),
                         [(wire.layer_name, (wire.x0, wire.y0), (wire.x1, wire.y1))
                          for wire in parser.getNet("VDD").swiring]))
    finally:
        # Restored on the way out, for the same reason the other swapped-pattern test does it:
        # a module-level pattern left swapped parses every later test with the wrong one.
        CompiledRe.re_special_wiring_form = previous

    # Before: the artifact form takes `ASK` as its layer, ends the M4 form early so the wire
    # between the second and third points is never built, and emits the mask's own point as a
    # zero-length shape on a layer no tech LEF defines.
    assert seen[0][0] == ["ASK", "M4"]
    assert seen[0][1] == [("M4", (1000, 1000), (2000, 1000)),
                          ("ASK", (3000, 1000), (3000, 1000))]

    # After: one M4 form, all three points, and no layer named after the rest of a keyword.
    assert seen[1][0] == ["M4"]
    assert seen[1][1] == [("M4", (1000, 1000), (2000, 1000)),
                          ("M4", (2000, 1000), (3000, 1000))]


def test_a_giant_statement_is_not_held_several_times_over(tmp_path):
    """One power net written as one statement: the text must not cost several copies of itself.

    A real chip-level DEF is 20 % one statement - 58,549,358 lines, 4,979,560,694 characters,
    measured - and reading it used to hold, at once, a list of that many line strings, their
    join, a wiring slice, and a list of one match object per form (208 bytes each): ~27 GB for
    a job that asked for 20. The bound is deliberately loose, because the point is the order of
    magnitude rather than a byte count - it fails above ~6x the statement and passes below ~3x.
    """
    import tracemalloc

    form = "  + VIA via1_2 ( 1000 2000 )\n"
    body = ("SPECIALNETS 1 ;\n- VDD + USE POWER\n" + form * 200_000
            + "  ;\nEND SPECIALNETS\nEND DESIGN\n")
    path = tmp_path / "giant.def"
    path.write_text(HEADER + body)

    tracemalloc.start()
    parser = DefParser(str(path), parse_net=True, parse_specialnet=True)
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    stats = parser.getStats()
    assert stats["statement_lines_max"] == 200_002        # the net's line, its forms, its ';'
    assert parser.getNet("VDD").via_points == 200_000     # every point counted, none lost
    assert peak < 3.5 * stats["statement_chars_max"]

