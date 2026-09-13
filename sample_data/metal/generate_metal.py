"""Generate the metal-density sample: a 1P12M stack over a hierarchical routed design.

Run it with no arguments to (re)write the committed sample:

    python sample_data/metal/generate_metal.py

and with ``--stress N`` to write a synthetic DEF of about N nets into a scratch directory and
report what each stage cost. The stress mode is how the performance numbers in
``dev_plan/metal_density_asbuilt.md`` were measured; it is deliberately *not* committed, since
it exists to be regenerated on whatever machine matters.

The tech LEF is written with several awkward-but-legal shapes on purpose, one per layer, each
of which corresponds to a bug found in the real Nangate45 file or the reference:

| layer | shape | what it catches |
|---|---|---|
| M2 | four qualified `SPACING` clauses, largest last | last-match-wins picking the widest rule |
| M6 | a `SPACINGTABLE PARALLELRUNLENGTH` block | table rows read as the layer's `WIDTH` |
| M7 | `MINWIDTH` and no `WIDTH` | width left at its zero initialiser |
| M8 | `DIRECTION VERTICAL;` with no space before the `;` | a value pattern demanding trailing whitespace |

The sample is more useful as a parser stress case than as a pretty picture, so these are
mandatory rather than decorative.

M2 is also deliberately a layer whose pitch exceeds its rules (0.07 + 0.07 against 0.19), so
the pitch normalisation is exercised by the committed sample and not only by a unit test.
"""
from __future__ import annotations

import argparse
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(HERE))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from vlsi_viewer.assembly import Frame       # noqa: E402  (after the path fix above)

UNITS_PER_MICRON = 2000
DBU = UNITS_PER_MICRON

# name, direction, pitch, width, spacing - microns. Pitches widen with height as real stacks
# do; the numbers follow Nangate45 and sky130's published track pitches.
LAYERS = [
    ("M1", "HORIZONTAL", 0.14, 0.07, 0.07),
    ("M2", "VERTICAL", 0.19, 0.07, 0.07),      # pitch > width + spacing: f < 1
    ("M3", "HORIZONTAL", 0.14, 0.07, 0.07),
    ("M4", "VERTICAL", 0.28, 0.14, 0.14),
    ("M5", "HORIZONTAL", 0.28, 0.14, 0.14),
    ("M6", "VERTICAL", 0.28, 0.14, 0.14),
    ("M7", "HORIZONTAL", 0.40, 0.20, 0.20),
    ("M8", "VERTICAL", 0.40, 0.20, 0.20),
    ("M9", "HORIZONTAL", 0.80, 0.40, 0.40),
    ("M10", "VERTICAL", 0.80, 0.40, 0.40),
    ("M11", "HORIZONTAL", 1.60, 0.80, 0.80),
    ("M12", "VERTICAL", 1.60, 0.80, 0.80),
]
H_LAYERS = {"M1", "M3", "M5", "M7", "M9", "M11"}
# Layers the sample routes signal on. Real routing uses the middle of the stack; M1 is the
# power rail layer here and the top two are wide-pitch.
SIGNAL_LAYERS = ("M2", "M3", "M4", "M5", "M6", "M7", "M8")

# Cells: (name, width, height, LEF class). The SRAM is a CLASS BLOCK so it is a macro; the
# filler cells are marked physical-only by name downstream.
CELLS = [
    ("INV_X1_SVT", 0.14, 0.4, "CORE"),
    ("INV_X2_LVT", 0.28, 0.4, "CORE"),
    ("NAND2_X1_ULVT", 0.28, 0.4, "CORE"),
    ("NOR2_X1_SVT", 0.28, 0.4, "CORE"),
    ("BUF_X1_LVT", 0.14, 0.4, "CORE"),
    ("BUF_X4_SVT", 0.56, 0.4, "CORE"),
    ("CKINV_X1_ULVT", 0.14, 0.4, "CORE"),
    ("CKBUF_X2_SVT", 0.28, 0.4, "CORE"),
    ("SDF_X1_SVT", 0.28, 0.4, "CORE"),
    ("SDF_X2_LVT", 0.56, 0.4, "CORE"),
    ("ICG_X1_ULVT", 0.28, 0.4, "CORE"),
    ("AOI21_X1_SVT", 0.28, 0.4, "CORE"),
    ("SRAM_1024", 40.0, 20.0, "BLOCK"),
    # The second block macro declares no OBS at all - the case a layer count exists for.
    ("SRAM_512", 20.0, 10.0, "BLOCK"),
    ("FILL_8", 1.12, 0.4, "CORE"),
    ("TAP_1", 0.14, 0.4, "CORE"),
    ("DCAP_4", 0.56, 0.4, "CORE"),
]
LOGIC = [c for c in CELLS if c[3] == "CORE" and not c[0].startswith(("FILL", "TAP", "DCAP"))]
STANDARD = [c for c in CELLS if c[3] == "CORE"]

# The obstruction list of the one macro that declares one, in the macro's own coordinates:
# layer -> rectangles. Shape deliberately like a real block macro's, and awkward in three ways
# the metric has to get right, each of which the layer-count model cannot express:
#
#   * M2 arrives as a field of abutting tiles rather than one rectangle, which is how memory
#     compilers write it - a rule judging each rectangle on its own would discard the lot;
#   * M3 is skipped, so a macro that obstructs M1, M2 and M4 but not M3 has to come out that
#     way;
#   * M5 carries only two pin-access bites, 0.04 % of the macro's area, which are not a
#     keep-out region and must not remove any capacity.
OBS = {
    "SRAM_1024": [
        ("M1", [(0.0, 0.0, 40.0, 20.0)]),
        ("M2", [(x * 10.0, y * 5.0, x * 10.0 + 10.0, y * 5.0 + 5.0)
                for x in range(4) for y in range(4)]),
        ("M4", [(0.0, 0.0, 38.0, 19.0)]),
        ("M5", [(1.0, 1.0, 1.4, 1.4), (38.0, 18.0, 38.4, 18.4)]),
    ],
}

# Floorplan, microns.
# The die is sized to the net count rather than the other way round. At 12k nets over a
# 500 x 400 um block the busiest cell reached only 0.18 - a map with no congestion on it -
# because that is a tenth of the routing a real block that size carries. Shrinking the block
# is the honest fix; inflating the net count to match an unrealistic area would just make a
# larger file that still does not look like a design.
SUB_W, SUB_H = 260.0, 200.0
GAP = 40.0
MARGIN = 30.0
ROWS_PER_SUB = 24
ROW_H = 2.4
SITE = 0.14
N_SIGNAL_NETS = 15000
PG_STRIPE_PITCH = 40.0

# The four orientations the sub-blocks are placed at, so frame composition for *wires* is
# exercised by the committed sample rather than only by a unit test.
SUB_ORIENTS = ("N", "W", "FS", "E")


def dbu(microns: float) -> int:
    """Microns to DEF database units, rounding rather than truncating."""
    return int(round(microns * DBU))


# -- tech LEF ------------------------------------------------------------------------

def tech_lef_text() -> str:
    out = ["VERSION 5.8 ;", 'BUSBITCHARS "[]" ;', 'DIVIDERCHAR "/" ;', ""]
    for name, direction, pitch, width, spacing in LAYERS:
        out.append(f"LAYER {name}")
        out.append("  TYPE ROUTING ;")
        # M8: no space before the semicolon, as machine-generated LEFs write it.
        out.append("  DIRECTION VERTICAL;" if name == "M8" else
                   f"  DIRECTION {direction} ;")
        out.append(f"  PITCH {pitch:.2f} ;")
        if name == "M7":
            # No WIDTH at all: the parser has to fall back to MINWIDTH.
            out.append(f"  MINWIDTH {width:.2f} ;")
        else:
            out.append(f"  WIDTH {width:.2f} ;")
        if name == "M2":
            # Four clauses, the widest last. The unqualified one is the default.
            out.append(f"  SPACING {spacing:.2f} ;")
            out.append(f"  SPACING {spacing:.2f} LENGTHTHRESHOLD 1.0 ;")
            out.append("  SPACING 0.30 RANGE 0.3 10.0 ;")
            out.append("  SPACING 0.90 RANGE 10.05 100000.0 ;")
        elif name == "M6":
            out.append("  SPACINGTABLE")
            out.append("    PARALLELRUNLENGTH 0.0000 0.3000 0.9000")
            out.append(f"      WIDTH 0.0000 {spacing:.4f} {spacing:.4f} {spacing:.4f}")
            out.append(f"      WIDTH 0.0900 {spacing:.4f} 0.2000 0.2000")
            out.append("      WIDTH 1.5000 0.2000 0.5000 0.9000 ;")
        else:
            out.append(f"  SPACING {spacing:.2f} ;")
        out.append("END " + name)
        out.append("")
    # Non-routing layers, so the routing filter has something to filter.
    out.append("LAYER VIA1\n  TYPE CUT ;\n  WIDTH 0.07 ;\nEND VIA1\n")
    out.append("LAYER VIA2\n  TYPE CUT ;\n  WIDTH 0.07 ;\nEND VIA2\n")
    out.append("LAYER OVERLAP\n  TYPE OVERLAP ;\nEND OVERLAP\n")
    return "\n".join(out)


# -- macro LEF -----------------------------------------------------------------------

def macro_lef_text() -> str:
    out = ["VERSION 5.8 ;", 'BUSBITCHARS "[]" ;', 'DIVIDERCHAR "/" ;', ""]
    for name, width, height, klass in CELLS:
        out.append(f"MACRO {name}")
        out.append(f"  CLASS {klass} ;")
        out.append(f"  ORIGIN 0 0 ;")
        out.append(f"  SIZE {width:.2f} BY {height:.2f} ;")
        out.append("  SYMMETRY X Y ;")
        if name in OBS:
            # Indentation and the bare END follow the real Nangate45 library.
            out.append("  OBS")
            for layer, rects in OBS[name]:
                out.append(f"    LAYER {layer} ;")
                for rect in rects:
                    out.append("      RECT " + " ".join(f"{value:.2f}" for value in rect) + " ;")
            out.append("  END")
        out.append("END " + name)
        out.append("")
    return "\n".join(out)


# -- floorplan and routing -----------------------------------------------------------

def activity(x: float, y: float) -> float:
    """A smooth 0..1 field, so the map has structure instead of uniform noise.

    Three sines at different periods: long enough that neighbouring grid cells agree, which
    is what makes a heat map legible, and varied enough that it is not one gradient.
    """
    return (0.5 + 0.30 * math.sin(x / 130.0) * math.cos(y / 97.0)
            + 0.12 * math.sin((x + y) / 61.0) + 0.08 * math.cos(x / 29.0))


def build(rng: random.Random):
    """The floorplan, and the contents of **one** sub-block in its own local frame.

    The leaf cells and their wiring are written once, in `sub.def`, and placed four times by
    `top.def` at four different orientations. That is what makes frame composition for wires
    something the committed sample exercises rather than only a unit test: every sub-block's
    routing reaches global coordinates through its own rotation.
    """
    # Laid out on a grid sized by the *larger* dimension, and each instance is placed so its
    # **rotated** footprint lands in its cell. Two subtleties, both of which produced
    # overlapping blocks when ignored: a quarter turn swaps the extents (a 260x200 block
    # placed West occupies 200x260), and DEF anchors the cell's origin corner at the
    # placement - West maps `x -> x0 - y`, so the block extends to the *left* of its origin
    # rather than the right. Overlapping blocks put one block's wiring inside another's
    # macro, which reads as congestion where no router could have put anything.
    span = max(SUB_W, SUB_H)
    die = (2 * span + GAP + 2 * MARGIN, 2 * span + GAP + 2 * MARGIN)
    subs = []
    for index, orient in enumerate(SUB_ORIENTS):
        target = (MARGIN + (index % 2) * (span + GAP),
                  MARGIN + (index // 2) * (span + GAP))
        probe = Frame(orient, (0.0, 0.0)).apply_rect([0.0], [0.0], [SUB_W], [SUB_H])
        subs.append((target[0] - float(probe[0][0]), target[1] - float(probe[1][0]),
                     orient))

    rows, placements = [], []
    row_pitch = (SUB_H - 2 * ROW_H) / max(1, ROWS_PER_SUB - 1)
    for row in range(ROWS_PER_SUB):
        y = ROW_H + row * row_pitch
        limit = SUB_W - 6.0
        x = 6.0
        placed = 0
        while x < limit:
            name, width, _height, _k = rng.choices(
                LOGIC, weights=[3 if c[0].startswith(("INV", "BUF", "NAND")) else 1
                                for c in LOGIC])[0]
            if x + width > limit:
                break
            # Whitespace follows the activity field, so rows are not uniformly full.
            if rng.random() > 0.35 + 0.6 * activity(x, y):
                x += round(SITE * rng.randint(1, 4), 3)
                continue
            # Numbered by placement order, not by coordinate: `int(x)` collides across a
            # whole site's worth of positions, and duplicate component names are silently
            # merged by the parser (which then reports the shortfall, as it should).
            placements.append((f"r{row}_{placed}", name, round(x, 3), round(y, 3),
                               "N" if row % 2 == 0 else "FN"))
            placed += 1
            x += round(width, 3)
        rows.append((row, round(y, 3)))
    # Two macros per sub-block, so macro capacity has something to exclude.
    placements.append(("smem", "SRAM_1024", round(SUB_W / 2, 3), round(SUB_H - 30.0, 3), "N"))
    placements.append(("smem2", "SRAM_512", round(SUB_W / 2, 3), 20.0, "N"))
    return die, subs, rows, placements


def _segment_hits(x0, y0, x1, y1, rects, pad=0.4):
    """Whether a wire segment crosses any blocked rectangle.

    The whole segment, not just its ends: a 30 um run between two points outside a macro can
    pass straight over it, and checking only the endpoints leaves the middle unguarded - which
    is exactly what left metal sitting in cells whose capacity is zero.
    """
    lo_x, hi_x = min(x0, x1) - pad, max(x0, x1) + pad
    lo_y, hi_y = min(y0, y1) - pad, max(y0, y1) + pad
    return any(not (hi_x < bx0 or lo_x > bx1 or hi_y < by0 or lo_y > by1)
               for bx0, by0, bx1, by1 in rects)


def macro_rects(placements, margin=1.0):
    """Footprint of every macro placement, in the sub-block's frame.

    Signal routing is kept out of these. A real router does not put signal wires on the
    lower metals over an SRAM, and a sample that does would show metal in cells whose
    capacity is zero - which reads as over-congestion that no design would actually have.
    """
    # Only the hard macros - a standard cell blocks nothing, and treating one as an obstacle
    # rejects every wire that would cross a logic row, which is nearly all of them.
    sizes = {name: (width, height) for name, width, height, klass in CELLS
             if klass == "BLOCK"}
    rects = []
    for _name, cell, x, y, orient in placements:
        if cell not in sizes:
            continue
        width, height = sizes[cell]
        # A quarter turn swaps the footprint's extents, the same rule the metric applies and
        # `physical._oriented_extent` uses. Blocking the un-swapped rectangle instead leaves
        # the rotated instance's real footprint unguarded, and wires end up in cells the
        # metric marks as a macro - which reads as congestion where there is no room at all.
        if orient in ("W", "E", "FW", "FE"):
            width, height = height, width
        rects.append((x - margin, y - margin, x + width + margin, y + height + margin))
    return rects


def signal_nets(rng: random.Random, extent, blocked=()):
    """Two- and three-segment nets, in the sub-block's own frame.

    Wires run along their layer's preferred direction, with a short jog and - for a couple of
    percent - a 45-degree segment, so every conversion path in the sample is exercised.
    """
    nets = []
    width, height = extent
    for index in range(N_SIGNAL_NETS):
        # Rejection-sampled towards the busy regions, so the map has hotspots a user can
        # point at rather than a uniform sprinkle. A real design concentrates its routing
        # where its logic is, and a sample that does not will not look like one.
        x = y = 0.0
        for _attempt in range(12):
            x = rng.uniform(MARGIN, width - MARGIN)
            y = rng.uniform(MARGIN, height - MARGIN)
            # A gentle slope, not a spike. An aggressive one clusters wires into a few cells
            # at several times the layer's own capacity, which reads as congestion no router
            # would produce; real designs run a peak of a few times the mean, not twenty.
            if rng.random() < activity(x, y) * 0.75 + 0.18:
                break
        density = activity(x, y)
        length = rng.uniform(6.0, 30.0) * (0.6 + 0.8 * density)
        # Spread across the signal layers rather than piling onto three. A real design uses
        # all of them, and concentrating on three makes those three read several times over
        # capacity - congestion no router would produce, and a misleading thing to ship as
        # an example.
        layer = SIGNAL_LAYERS[int(rng.random() * len(SIGNAL_LAYERS))]
        horizontal = layer in H_LAYERS
        if horizontal:
            x1, y1 = min(x + length, width - 2.0), y
        else:
            x1, y1 = x, min(y + length, height - 2.0)
        # A short jog on the same layer, then a stub toward the far pin.
        if rng.random() < 0.35:
            jog = rng.uniform(0.3, 1.5)
            if horizontal:
                points = [(x, y), (x1, y1), (x1, min(y1 + jog, height - 1.0))]
            else:
                points = [(x, y), (x1, y1), (min(x1 + jog, width - 1.0), y1)]
        else:
            points = [(x, y), (x1, y1)]
        # Every leg is checked, not just the long one: a jog steps sideways, and a 1.5 um
        # step is easily enough to put metal inside a macro the main run avoided.
        if any(_segment_hits(*points[i], *points[i + 1], blocked)
               for i in range(len(points) - 1)):
            continue
        diagonal = rng.random() < 0.02
        nets.append({"name": f"net_{index}", "layer": layer, "points": points,
                     "diagonal": diagonal,
                     "ndr": "CTS_2W2S" if index % 37 == 0 else None})
    return nets


def _wire_points(points, diagonal):
    """Render routing points, using the compact '*' reuse form where it applies."""
    parts = []
    last = None
    for i, (x, y) in enumerate(points):
        if diagonal and i == len(points) - 1 and last is not None:
            # A 45-degree tail: equal x and y steps, so the segment is neither axis-aligned.
            dx, dy = x - last[0], y - last[1]
            step = min(abs(dx), abs(dy))
            if step > 1.0:
                x, y = last[0] + math.copysign(step, dx), last[1] + math.copysign(step, dy)
        if last is not None and i % 3 == 2:
            # '*' reuses the previous coordinate - real DEF uses it constantly.
            if x == last[0]:
                parts.append(f"( * {dbu(y)} )")
            elif y == last[1]:
                parts.append(f"( {dbu(x)} * )")
            else:
                parts.append(f"( {dbu(x)} {dbu(y)} )")
        else:
            parts.append(f"( {dbu(x)} {dbu(y)} )")
        last = (x, y)
    return " ".join(parts)


def def_text(design, die, rows, placements, nets, pg_kind, include_ndr):
    out = ["VERSION 5.8 ;", 'DIVIDERCHAR "/" ;', 'BUSBITCHARS "[]" ;',
           f"DESIGN {design} ;", f"UNITS DISTANCE MICRONS {UNITS_PER_MICRON} ;",
           f"DIEAREA ( 0 0 ) ( {dbu(die[0])} {dbu(die[1])} ) ;"]
    for name, _direction, pitch, _w, _s in LAYERS:
        out.append(f"TRACKS X {dbu(1.0)} DO {int(die[0] / pitch)} "
                   f"STEP {dbu(pitch)} LAYER {name} ;")
        out.append(f"TRACKS Y {dbu(1.0)} DO {int(die[1] / pitch)} "
                   f"STEP {dbu(pitch)} LAYER {name} ;")
    if include_ndr:
        out.append("NONDEFAULTRULES 2 ;")
        out.append("- CTS_2W2S")
        for name in ("M2", "M3", "M4"):
            width = 2 * dict((l[0], l[3]) for l in LAYERS)[name]
            spacing = 2 * dict((l[0], l[4]) for l in LAYERS)[name]
            out.append(f"  + LAYER {name} WIDTH {dbu(width)} SPACING {dbu(spacing)}")
        out.append("  ;")
        out.append("- PG_WIDE")
        out.append("  + HARDSPACING")
        out.append(f"  + LAYER M9 WIDTH {dbu(2.4)} SPACING {dbu(1.6)}")
        out.append("  ;")
        out.append("END NONDEFAULTRULES")
    out.append(f"COMPONENTS {len(placements)} ;")
    for name, cell, x, y, orient in placements:
        out.append(f"- {name} {cell} + SOURCE DIST + PLACED ( {dbu(x)} {dbu(y)} ) {orient} ;")
    out.append("END COMPONENTS")

    if pg_kind == "followpins":
        # Inside a sub-block: power rails on M1, one per standard-cell row, spanning the
        # local width. `+ SHAPE FOLLOWPIN` comes *after* the route width, the order real
        # tools write and the shape the wiring regex has to accept.
        out.append("SPECIALNETS 2 ;")
        half = len(rows) // 2
        for net, use, picked in (("VDD", "POWER", rows[:half]),
                                 ("VSS", "GROUND", rows[half:])):
            out.append(f"- {net} ( * {net} ) + USE {use}")
            for _row, y in picked:
                out.append(f"  NEW M1 {dbu(0.34)} + SHAPE FOLLOWPIN "
                           f"( {dbu(2.0)} {dbu(y)} ) ( {dbu(die[0] - 2.0)} {dbu(y)} )")
            out.append("  ;")
        out.append("END SPECIALNETS")
    elif pg_kind == "grid":
        # At the top level: a stripe and a ring, so both PG forms are present - a routed
        # stripe with an explicit route width, and a filled `+ POLYGON` ring whose whole
        # vertex list only exists at parse time.
        out.append("SPECIALNETS 2 ;")
        out.append("- VDD ( * VDD ) + USE POWER")
        out.append(f"  + ROUTED M9 {dbu(3.0)} + SHAPE STRIPE "
                   f"( {dbu(MARGIN)} {dbu(MARGIN)} ) ( {dbu(MARGIN)} {dbu(die[1] - MARGIN)} )")
        for index in range(1, 8):
            x = MARGIN + index * PG_STRIPE_PITCH
            if x > die[0] - MARGIN:
                break
            out.append(f"  NEW M9 {dbu(3.0)} + SHAPE STRIPE ( {dbu(x)} {dbu(MARGIN)} ) "
                       f"( {dbu(x)} {dbu(die[1] - MARGIN)} )")
        out.append("  ;")
        x0, y0 = MARGIN + 15.0, MARGIN + 15.0
        x1, y1 = die[0] - MARGIN - 15.0, die[1] - MARGIN - 15.0
        out.append("- VDD_RING + USE POWER")
        out.append(f"  + POLYGON M11 ( {dbu(x0)} {dbu(y0)} ) ( {dbu(x1)} {dbu(y0)} ) "
                   f"( {dbu(x1)} {dbu(y1)} ) ( {dbu(x0)} {dbu(y1)} ) ;")
        out.append("END SPECIALNETS")

    out.append(f"NETS {len(nets)} ;")
    for net in nets:
        clause = f" + NONDEFAULTRULE {net['ndr']}" if net["ndr"] else ""
        out.append(f"- {net['name']} ( u0/r0_10 A ){clause}")
        out.append(f"  + ROUTED {net['layer']} {_wire_points(net['points'], net['diagonal'])} ;")
    out.append("END NETS")
    out.append("END DESIGN")
    return "\n".join(out) + "\n"


# -- verification --------------------------------------------------------------------

def verify():
    """Re-parse the written files through the real pipeline and assert what must hold."""
    import numpy as np

    from vlsi_viewer.metal import SCOPE_ALL, SCOPE_POWER, SCOPE_SIGNAL, build_metal
    from vlsi_viewer.parsers.routing import TechRouting

    tech_path = os.path.join(HERE, "tech.lef")
    lef_path = os.path.join(HERE, "cells.lef")
    top_path = os.path.join(HERE, "top.def")
    sub_path = os.path.join(HERE, "sub.def")

    with _quiet():
        tech = TechRouting.read([tech_path])
    assert len(tech) == len(LAYERS), f"{len(tech)} routing layers, expected {len(LAYERS)}"
    assert not tech.get("VIA1") and not tech.get("OVERLAP"), "cut/overlap leaked in"

    by_name = {entry[0]: entry for entry in LAYERS}
    for layer in tech:
        expected = by_name[layer.name]
        assert layer.pitch == round(expected[2], 6), \
            f"{layer.name} pitch {layer.pitch} != {expected[2]}"
        assert layer.width == round(expected[3], 6), \
            f"{layer.name} width {layer.width} != {expected[3]}"
        assert layer.spacing == round(expected[4], 6), \
            f"{layer.name} spacing {layer.spacing} != {expected[4]}"
    # The two layers whose shapes are the point of writing them that way.
    assert tech["M2"].spacing == 0.07, "the unqualified SPACING clause must win"
    assert tech["M7"].width == 0.20, "M7 has no WIDTH, so MINWIDTH is the fallback"
    assert tech["M6"].spacing > 0, "the spacing table must yield a usable minimum"
    assert tech["M8"].direction == "VERTICAL", "no space before the ';' must still parse"

    with _quiet():
        data = build_metal([top_path, sub_path], [lef_path], [tech_path], grid_size=10.0)
    print(f"  verify: {data!r}")

    assert data.top_name == "TOP", data.top_name
    assert data.rows >= 40 and data.cols >= 40, (data.rows, data.cols)
    assert not data.warnings, data.warnings

    # Every layer's capacity must be positive somewhere, or its checkbox is a trap.
    for layer in data.layers:
        assert data.capacity(layer).max() > 0, layer.name

    # Blockage, checked where it can tell the two mechanisms apart.
    #
    # SRAM_1024 declares OBS on M1, M2 and M4 but *skips* M3, so there must be cells where M1
    # has no capacity and M3 is untouched - a shape no "block the bottom N layers" answer can
    # produce. SRAM_512 declares none, so it falls back and takes its whole footprint's worth
    # out of M1..M4 together, giving cells where M1 and M3 are both gone. Asserting both
    # populations exist is what proves which mechanism is in force where.
    by_name = {layer.name: layer for layer in data.layers}
    blocked = {data.layers[index].name for index in data.blocked_layers}
    # The union of both mechanisms: the OBS macro obstructs M1, M2 and M4, and the fallback
    # macro adds M3 over its own footprint - which is why M3 appears here even though the
    # macro that declares OBS skips it.
    assert blocked == {"M1", "M2", "M3", "M4"}, blocked
    assert data.blockage["obs_cells"] == 1, data.blockage
    assert data.blockage["fallback_cells"] == 1, data.blockage
    assert "M5" in data.blockage["ignored_layers"], data.blockage    # pin-access bites

    whole = data.routable_top
    m1, m2, m3 = (data.capacity(by_name[name]) for name in ("M1", "M2", "M3"))
    m12 = data.capacity(by_name["M12"])
    assert not (m12 < whole - 1e-9).any(), "nothing may remove capacity on M12"
    assert (m2 < whole - 1e-9).any(), "M2's tile field must count as obstruction"

    obstructed = m1 <= 1e-9
    obs_only = obstructed & (m3 > whole - 1e-9)              # SRAM_1024's footprint
    fallback = obstructed & (m3 <= 1e-9)                     # SRAM_512's footprint
    assert obs_only.any(), ("no cell is obstructed on M1 with M3 whole - the OBS macro's "
                            "layer set is not being used")
    assert fallback.any(), "the fallback macro must block its whole footprint"

    # And the readout agrees with the pixel for one of those cells.
    iy, ix = (int(value) for value in np.argwhere(obs_only)[0])
    assert data.cell_detail(ix, iy, "L:M1")["capacity"] == 0.0
    assert data.cell_detail(ix, iy, "L:M3")["capacity"] > 0

    assert 0.7 < data.cell_detail(0, 0, "L:M2")["layers"][0]["pitch_factor"] < 0.80

    # The picture has to have structure: a spread of values, nothing saturated everywhere,
    # and power visible where the stripes are.
    every = data.group_kind([layer.name for layer in data.layers])
    data.set_scope(SCOPE_ALL)
    grid = data.heat(every)
    assert np.isfinite(grid).all() and grid.min() >= 0 and grid.max() <= 1
    assert grid.max() > 0.30, f"the busiest cell only reaches {grid.max():.3f}"
    distinct = len(np.unique(np.round(grid, 4)))
    assert distinct > 30, f"only {distinct} distinct values - the map is flat"
    occupied = grid[grid > 0]
    assert occupied.size > 0.02 * grid.size, "almost nothing is routed"

    data.set_scope(SCOPE_POWER)
    power = data.heat(every)
    assert power.max() > 0.10, "the power grid is invisible"
    data.set_scope(SCOPE_SIGNAL)
    signal = data.heat(every)
    assert signal.max() > 0.05, "no signal routing is visible"

    # Horizontal groups must be made of horizontal layers, which is the whole point of
    # the H/V split being a selection rather than a computed metric.
    assert all(layer.is_horizontal for layer in data.layers_of(
        data.group_kind([layer.name for layer in tech.horizontal])))
    print(f"  verify: all-layer max {grid.max():.3f}, "
          f"{distinct} distinct values, "
          f"power max {power.max():.3f}, signal max {signal.max():.3f}")
    print("  verify: OK")


class _quiet:
    """Silence the parsers' chatter, which would otherwise drown the verify output."""

    def __enter__(self):
        import contextlib
        import io
        self._redirect = contextlib.redirect_stdout(io.StringIO())
        return self._redirect.__enter__()

    def __exit__(self, *exc):
        return self._redirect.__exit__(*exc)


# -- stress mode ---------------------------------------------------------------------

def stress(count: int, out_dir: str) -> int:
    """Write a synthetic DEF of about ``count`` nets and time each stage.

    The committed sample is a few thousand segments, which says nothing about the sizes the
    metric is meant for. This is how the numbers in the as-built doc were produced.
    """
    import time
    import tracemalloc

    rng = random.Random(7)
    die = (20000.0, 20000.0)
    layer_cycle = ["M2", "M3", "M4", "M5"]

    started = time.perf_counter()
    with open(os.path.join(out_dir, "stress.def"), "w") as handle:
        handle.write("VERSION 5.8 ;\nDESIGN stress ;\n")
        handle.write(f"UNITS DISTANCE MICRONS {UNITS_PER_MICRON} ;\n")
        handle.write(f"DIEAREA ( 0 0 ) ( {dbu(die[0])} {dbu(die[1])} ) ;\n")
        for name, _d, pitch, _w, _s in LAYERS:
            handle.write(f"TRACKS X {dbu(1.0)} DO {int(die[0] / pitch)} "
                         f"STEP {dbu(pitch)} LAYER {name} ;\n")
        handle.write("COMPONENTS 0 ;\nEND COMPONENTS\n")
        handle.write(f"NETS {count} ;\n")
        for index in range(count):
            x = rng.uniform(0.0, die[0])
            y = rng.uniform(0.0, die[1])
            length = rng.uniform(2.0, 40.0)
            layer = layer_cycle[index % len(layer_cycle)]
            if layer in H_LAYERS:
                points = f"( {dbu(x)} {dbu(y)} ) ( {dbu(min(x + length, die[0]))} {dbu(y)} )"
            else:
                points = f"( {dbu(x)} {dbu(y)} ) ( {dbu(x)} {dbu(min(y + length, die[1]))} )"
            handle.write(f"- n{index} ( PIN A )\n  + ROUTED {layer} {points} ;\n")
        handle.write("END NETS\nEND DESIGN\n")
    write_seconds = time.perf_counter() - started

    from vlsi_viewer.metal import build_metal
    tracemalloc.start()
    started = time.perf_counter()
    with _quiet():
        data = build_metal([os.path.join(out_dir, "stress.def")], [],
                           [os.path.join(HERE, "tech.lef")], grid_size=10.0)
    build_seconds = time.perf_counter() - started
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    every = data.group_kind([layer.name for layer in data.layers])
    print(f"stress {count:,} nets -> {data.rows}x{data.cols} grid")
    print(f"  write   {write_seconds:7.2f}s")
    print(f"  build   {build_seconds:7.2f}s   ({build_seconds / count * 1e6:.1f} us/net)")
    print(f"  peak    {peak / 1e6:7.1f} MB")
    print(f"  max util {data.max_util(every):.4f}")
    return 0


# -- entry point ---------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stress", type=int, metavar="NETS",
                        help="write a synthetic DEF of this many nets to --out and time it")
    parser.add_argument("--out", default=None,
                        help="where --stress writes (default: a scratch directory)")
    args = parser.parse_args(argv)

    if args.stress:
        import tempfile
        out = args.out or tempfile.mkdtemp(prefix="metal_stress_")
        os.makedirs(out, exist_ok=True)
        return stress(args.stress, out)

    rng = random.Random(0)
    die, subs, rows, placements = build(rng)
    # Signal wires stay off the macros: a router does not put them over an SRAM on the
    # lower metals, and a sample that did would show metal in cells whose capacity is zero.
    nets = signal_nets(rng, (SUB_W, SUB_H), macro_rects(placements))

    # The top level holds four rotated instances of the one block that carries the cells and
    # the signal routing. Its own wiring is the power grid, which is what a real top-level
    # DEF mostly contains.
    top_placements = [(f"u{index}", "SUB", x, y, orient)
                      for index, (x, y, orient) in enumerate(subs)]

    files = {
        "tech.lef": tech_lef_text(),
        "cells.lef": macro_lef_text(),
        "sub.def": def_text("SUB", (SUB_W, SUB_H), rows, placements, nets,
                            "followpins", True),
        "top.def": def_text("TOP", die, [], top_placements, [], "grid", True),
        "orphan.def": def_text("ORPHAN", (200.0, 200.0), [], [], [], None, False),
    }
    for name, text in files.items():
        with open(os.path.join(HERE, name), "w", newline="\n") as handle:
            handle.write(text)
    total = sum(len(text) for text in files.values())
    print(f"files: {', '.join(sorted(files))} ({total / 1024:.0f} KB)")
    print(f"components: {len(placements)}   signal nets: {len(nets)}   "
          f"rows: {len(rows)}   die: {die[0]:.0f} x {die[1]:.0f} um")
    verify()
    return 0


if __name__ == "__main__":
    sys.exit(main())
