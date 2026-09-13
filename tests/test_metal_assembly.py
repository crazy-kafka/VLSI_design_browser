"""Multi-DEF assembly: placing each block's wiring in global coordinates.

The frame algebra is the risky part. A wrong orientation table or a composition applied in
the wrong order still produces coordinates, and the resulting map still looks like a map -
just one whose sub-blocks are mirrored or rotated against their parents. So every case here
is checked against the underlying :func:`CoordinateProcess.dbTransform` applied by hand,
rather than against another copy of the same composition.
"""
import pandas as pd
import pytest

from vlsi_viewer.assembly import Frame, HierarchyAssembler, find_single_top
from vlsi_viewer.coordinateProcess import CoordinateProcess, Orient


def _instances(rows):
    """An instances frame with the columns the loader produces."""
    return pd.DataFrame(rows, columns=["cell_name", "orient", "location_x", "location_y"])


def _blocks(mapping):
    return {name: (_instances(rows), None) for name, rows in mapping.items()}


# -- choosing the root --------------------------------------------------------------

def test_single_top_is_the_block_nothing_instantiates():
    blocks = _blocks({
        "TOP": [("SUB", "N", 0.0, 0.0)],
        "SUB": [("LEAF", "N", 0.0, 0.0)],
    })
    assert find_single_top(blocks) == "TOP"


def test_two_roots_are_rejected_and_named():
    """Two unrelated designs have no single coordinate system, so there is nothing to draw.

    This is the error path a user hits by passing DEFs that do not belong to one hierarchy.
    """
    blocks = _blocks({"A": [("X", "N", 0.0, 0.0)], "B": [("Y", "N", 0.0, 0.0)]})
    with pytest.raises(ValueError, match="exactly one top-level"):
        find_single_top(blocks)
    with pytest.raises(ValueError, match="A, B"):
        find_single_top(blocks)


def test_no_root_is_rejected():
    """Every block referenced: a cycle, or nothing that is a design."""
    blocks = _blocks({"A": [("B", "N", 0.0, 0.0)], "B": [("A", "N", 0.0, 0.0)]})
    with pytest.raises(ValueError, match="found 0"):
        find_single_top(blocks)


# -- the frame algebra --------------------------------------------------------------

@pytest.mark.parametrize("orient", sorted(Orient.orient_map))
def test_point_transform_matches_the_engine(orient):
    """Parity with the transform the physical-mode walk already uses."""
    frame = Frame(orient, (100.0, -50.0))
    for point in ((0.0, 0.0), (3.5, 7.25), (-2.0, 1.0)):
        assert frame.apply_point(*point) == CoordinateProcess.dbTransform(
            "to_global", point, orient, (100.0, -50.0))


@pytest.mark.parametrize("orient", sorted(Orient.orient_map))
def test_rect_transform_is_the_corner_min_max(orient):
    """Every DEF orientation maps an axis-aligned rectangle to an axis-aligned one.

    Two opposite corners are transformed and re-normalised, which is exact for rotations by
    quarter turns and axis reflections - so the result must equal the min/max over all four
    corners computed point by point.
    """
    frame = Frame(orient, (10.0, 20.0))
    corners = [(x, y) for x in (1.0, 4.0) for y in (2.0, 9.0)]
    moved = [frame.apply_point(x, y) for x, y in corners]
    expected = (min(p[0] for p in moved), min(p[1] for p in moved),
                max(p[0] for p in moved), max(p[1] for p in moved))
    got = frame.apply_rect([1.0], [2.0], [4.0], [9.0])
    assert [float(v[0]) for v in got] == pytest.approx(expected)


def test_rotation_swaps_a_rectangles_extent():
    """A quarter turn really does swap width and height - the transform is not a no-op."""
    frame = Frame("W", (100.0, 200.0))
    x0, y0, x1, y1 = frame.apply_rect([0.0], [0.0], [10.0], [20.0])
    assert (float(x0[0]), float(y0[0]), float(x1[0]), float(y1[0])) == \
        pytest.approx((80.0, 200.0, 100.0, 210.0))


def test_compose_places_a_child_inside_a_rotated_parent():
    """Checked by hand: SUB inside a West-rotated TOP, then a point inside SUB.

    SUB at (100, 200) W means a local point (x, y) goes to (x0 - y, y0 + x), so (10, 0)
    lands at (100, 210). Composing must give the same answer as applying the two transforms
    in turn, which is what makes the nesting trustworthy.
    """
    composed = Frame().compose("W", (100.0, 200.0))
    assert composed.apply_point(10.0, 0.0) == pytest.approx((100.0, 210.0))

    by_hand = CoordinateProcess.dbTransform(
        "to_global",
        CoordinateProcess.dbTransform("to_global", (10.0, 0.0), "W", (100.0, 200.0)),
        "N", (0.0, 0.0))
    assert composed.apply_point(10.0, 0.0) == pytest.approx(by_hand)


def test_compose_twice_matches_applying_three_transforms():
    """Two levels of nesting, verified against the engine applied by hand.

    TOP contains SUB1 at (1000, 0) rotated West; SUB1 contains SUB2 at (100, 200) North.
    A point in SUB2 therefore goes N-at-(100,200) and then W-at-(1000,0).
    """
    inner = Frame("W", (1000.0, 0.0)).compose("N", (100.0, 200.0))
    point = (10.0, 20.0)

    step = CoordinateProcess.dbTransform("to_global", point, "N", (100.0, 200.0))
    step = CoordinateProcess.dbTransform("to_global", step, "W", (1000.0, 0.0))
    assert inner.apply_point(*point) == pytest.approx(step)
    assert inner.apply_point(*point) == pytest.approx((780.0, 110.0))   # by hand


@pytest.mark.parametrize("outer", sorted(Orient.orient_map))
@pytest.mark.parametrize("inner", sorted(Orient.orient_map))
def test_compose_agrees_with_applying_in_turn_for_every_pair(outer, inner):
    """All 64 orientation pairs, each checked against the engine rather than a table."""
    composed = Frame(outer, (300.0, -70.0)).compose(inner, (12.0, 34.0))
    point = (5.5, -6.5)
    step = CoordinateProcess.dbTransform("to_global", point, inner, (12.0, 34.0))
    step = CoordinateProcess.dbTransform("to_global", step, outer, (300.0, -70.0))
    assert composed.apply_point(*point) == pytest.approx(step)


# -- walking the tree ---------------------------------------------------------------

def _walk(blocks, top="TOP", cells=None):
    assembler = HierarchyAssembler(blocks, cells)
    seen = []
    assembler.walk(top, lambda name, frame: seen.append((name, frame.orient, frame.origin)))
    return seen, assembler


def test_walk_visits_the_whole_tree_outermost_first():
    blocks = _blocks({
        "TOP": [("SUB", "N", 10.0, 20.0)],
        "SUB": [("LEAF", "N", 1.0, 2.0)],
    })
    seen, _assembler = _walk(blocks)
    assert [name for name, _o, _p in seen] == ["TOP", "SUB"]
    assert seen[0][1:] == ("N", (0.0, 0.0))
    assert seen[1][1:] == ("N", (10.0, 20.0))


def test_a_block_used_twice_is_visited_twice():
    """It really is in two places, and each appearance contributes its own wires."""
    blocks = _blocks({
        "TOP": [("SUB", "N", 0.0, 0.0), ("SUB", "N", 100.0, 0.0)],
        "SUB": [],
    })
    seen, _assembler = _walk(blocks)
    assert [name for name, _o, _p in seen] == ["TOP", "SUB", "SUB"]
    assert seen[1][2] == (0.0, 0.0) and seen[2][2] == (100.0, 0.0)


def test_cyclic_hierarchy_is_rejected():
    blocks = _blocks({
        "A": [("B", "N", 0.0, 0.0)],
        "B": [("A", "N", 0.0, 0.0)],
    })
    with pytest.raises(ValueError, match="cyclic"):
        _walk(blocks, top="A")


def test_missing_cells_are_recorded_once_per_leaf():
    """An instance naming neither a block nor a known cell has no size, so no footprint."""
    cells = pd.DataFrame({"area": [1.0]}, index=["KNOWN"])
    blocks = _blocks({
        "TOP": [("SUB", "N", 0.0, 0.0), ("GHOST", "N", 0.0, 0.0)],
        "SUB": [("KNOWN", "N", 0.0, 0.0)],
    })
    _seen, assembler = _walk(blocks, cells=cells)
    assert assembler.missing == ["GHOST"]


def test_leaf_instances_are_not_walked_into():
    cells = pd.DataFrame({"area": [1.0]}, index=["KNOWN"])
    blocks = _blocks({"TOP": [("KNOWN", "N", 0.0, 0.0), ("KNOWN", "N", 1.0, 0.0)]})
    seen, assembler = _walk(blocks, cells=cells)
    assert [name for name, _o, _p in seen] == ["TOP"]
    assert assembler.missing == []
