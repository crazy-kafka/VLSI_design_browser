"""Wires and rings under an instance's frame, and a block that lands once per placement.

These are silent failure modes, which is why they are pinned before the flow that produces them is
changed. A transform applied *twice* - the second instance's frame composed onto the first's -
moves a sub-block's wiring somewhere plausible, and a block visited once instead of once per
placement loses three quarters of its metal; neither shows up in a counter, and
`generate_metal.verify()` survives both, because its grid thresholds (max > 0.30, distinct > 30,
occupied > 2 %) hold on a quarter of the design.

`+ POLYGON` is worse than either: it was never transformed at all, so a ring inside a rotated
sub-block rasterises in the sub-block's local coordinates, stacked under every other instance while
`n_emitted` counts it once per instance. The committed sample cannot see it because its only ring
sits in the top block, where the frame is the identity.
"""
import contextlib
import io
import os

import numpy as np
import pytest

from vlsi_viewer.metal import SCOPE_ALL, build_metal

SAMPLE = "sample_data/metal"

TECH = """\
LAYER M1
  TYPE ROUTING ;
  WIDTH 0.1 ;
  SPACING 0.1 ;
  PITCH 0.2 ;
  DIRECTION HORIZONTAL ;
END M1
LAYER M2
  TYPE ROUTING ;
  WIDTH 0.1 ;
  SPACING 0.1 ;
  PITCH 0.2 ;
  DIRECTION VERTICAL ;
END M2
"""

# A 4 x 4 um block, one wire across it: (1,1) to (3,1) in microns, so a quarter turn puts the same
# wire on the x = 3 grid line running in y.
SUB_HEAD = """\
VERSION 5.8 ;
DESIGN SUB ;
UNITS DISTANCE MICRONS 1000 ;
DIEAREA ( 0 0 ) ( 4000 4000 ) ;
COMPONENTS 0 ;
END COMPONENTS
"""
SUB_WIRE = """\
NETS 1 ;
- n1 ( PIN A )
  + ROUTED M1 ( 1000 1000 ) ( 3000 1000 ) ;
END NETS
"""
# An L, not a square: a quarter turn maps a square ring onto itself, so a square would test
# nothing about rotation - and the L is also the shape a bounding-box normalisation would get
# wrong, which is the other way this path can quietly produce the wrong metal.
SUB_RING = """\
SPECIALNETS 1 ;
- VDD + USE POWER
  + POLYGON M1 ( 1000 1000 ) ( 3000 1000 ) ( 3000 1500 ) ( 1500 1500 ) ( 1500 3000 )
    ( 1000 3000 ) ;
END SPECIALNETS
"""
TOP_HEAD = """\
VERSION 5.8 ;
DESIGN TOP ;
UNITS DISTANCE MICRONS 1000 ;
DIEAREA ( 0 0 ) ( 20000 20000 ) ;
"""


def _defs(tmp_path, sub_body, placements, top_wires=""):
    """Write a two-block design and return the paths to build it."""
    (tmp_path / "tech.lef").write_text(TECH)
    (tmp_path / "sub.def").write_text(SUB_HEAD + sub_body + "END DESIGN\n")
    components = "".join(f"- u{index} SUB + SOURCE DIST + PLACED "
                         f"( {x * 1000} {y * 1000} ) {orient} ;\n"
                         for index, (orient, x, y) in enumerate(placements))
    top = TOP_HEAD + f"COMPONENTS {len(placements)} ;\n" + components + "END COMPONENTS\n"
    if top_wires:
        top += top_wires
    (tmp_path / "top.def").write_text(top + "END DESIGN\n")
    return [str(tmp_path / "top.def"), str(tmp_path / "sub.def")], [str(tmp_path / "tech.lef")]


def _build(tmp_path, sub_body, placements, top_wires="", grid_size=1.0):
    paths, techs = _defs(tmp_path, sub_body, placements, top_wires)
    with contextlib.redirect_stdout(io.StringIO()):
        return build_metal(paths, [], techs, grid_size=grid_size)


def _cells(data, layer="M1"):
    """The (row, col) cells of one layer that hold anything, at the all-scope."""
    data.set_scope(SCOPE_ALL)
    heat = np.asarray(data.heat(data.group_kind([layer])), dtype=np.float64)
    return set(zip(*np.nonzero(heat > 0)))


def test_a_wire_in_a_sub_block_lands_where_its_instance_puts_it(tmp_path):
    """The oracle for multi-frame placement: what a rotated copy contributes equals the same
    wire written directly in the parent, and a *composed* transform fails this and little else."""
    alone = _build(tmp_path, SUB_WIRE, [("N", 0, 0)])
    both = _build(tmp_path, SUB_WIRE, [("N", 0, 0), ("W", 4, 0)])
    # The W instance turns the local (1,1)-(3,1) wire into a vertical run at global x = 3,
    # y = 1..3 - which is what the same wire drawn in the top block looks like.
    direct = _build(tmp_path, SUB_WIRE, [("N", 0, 0)],
                    top_wires="NETS 1 ;\n- t1 ( PIN A )\n  + ROUTED M1 ( 3000 1000 ) "
                              "( 3000 3000 ) ;\nEND NETS\n")
    assert _cells(alone) < _cells(both)                  # the second instance added metal
    assert _cells(both) - _cells(alone) == _cells(direct) - _cells(alone)


def test_a_ring_in_a_sub_block_lands_where_its_instance_puts_it(tmp_path):
    """`+ POLYGON` was never transformed: the ring stayed in the block's own coordinates.

    Both instances rasterised the same local ring on top of each other, so the die showed one ring
    where it should show two - and the shape count said two, which is what made it invisible.
    """
    alone = _build(tmp_path, SUB_RING, [("N", 0, 0)])
    both = _build(tmp_path, SUB_RING, [("N", 0, 0), ("W", 4, 0)])
    assert _cells(alone) < _cells(both)
    assert len(_cells(both)) > len(_cells(alone))        # not the same ring twice


def test_the_committed_sample_places_its_sub_block_four_times():
    """The absolute number: 4 x SUB's own 19,817 shapes plus the top's 9.

    Nothing else in the suite pins this. A walk that visits each *block* once instead of each
    placement passes every other test - `verify()`, the GUI tests, quickstart - while losing three
    quarters of the metal.
    """
    paths = [os.path.join(SAMPLE, "top.def"), os.path.join(SAMPLE, "sub.def")]
    with contextlib.redirect_stdout(io.StringIO()):
        data = build_metal(paths, [os.path.join(SAMPLE, "cells.lef")],
                           [os.path.join(SAMPLE, "tech.lef")], grid_size=10.0)
    assert data.totals["emitted"] == 4 * 19817 + 9
    assert data.totals["jogs"] == 4 * 135
