"""Tests for the shapely-backed hierarchy contour module."""
import pytest

from vlsi_viewer import contour as C


def _area(boxes, gap):
    return C.contour_area(boxes, gap)


def _loops(boxes, gap):
    return C.contour_loops(boxes, gap)


@pytest.mark.parametrize("gap", [0.0, 3.0])
def test_contour_area(gap):
    boxes = [(0.0, 0.0, 1.0, 1.0), (1.0, 0.0, 2.0, 1.0), (0.0, 1.0, 1.0, 2.0)]
    area = _area(boxes, gap)
    if gap == 0.0:
        assert area == pytest.approx(3.0)   # exact union of the three boxes
    else:
        assert area > 3.0                   # gap padding enlarges the scope


def test_abutting_boxes_one_loop():
    boxes = [(0.0, 0.0, 1.0, 1.0), (1.0, 0.0, 2.0, 1.0)]  # form a 2x1 rectangle
    assert len(_loops(boxes, 0.0)) == 1


def test_corner_touch_is_two_loops():
    boxes = [(0.0, 0.0, 1.0, 1.0), (1.0, 1.0, 2.0, 2.0)]
    assert len(_loops(boxes, 0.0)) == 2


def test_scatter_beyond_gap_is_two_loops():
    boxes = [(0.0, 0.0, 1.0, 1.0), (10.0, 0.0, 11.0, 1.0)]
    assert len(_loops(boxes, 0.0)) == 2


def test_scatter_within_gap_merges():
    boxes = [(0.0, 0.0, 1.0, 1.0), (2.0, 0.0, 3.0, 1.0)]  # 1-unit gap
    assert len(_loops(boxes, 2.0)) == 1     # gap 2 bridges it
    assert len(_loops(boxes, 0.0)) == 2     # gap 0 keeps them separate


def test_donut_has_hole():
    boxes = [(0.0, 0.0, 3.0, 1.0), (0.0, 2.0, 3.0, 3.0),
             (0.0, 1.0, 1.0, 2.0), (2.0, 1.0, 3.0, 2.0)]
    assert len(_loops(boxes, 0.0)) == 2     # exterior + hole
    assert _area(boxes, 0.0) == pytest.approx(8.0)


def test_merge_boxes_is_exact():
    """Pre-merging abutting/overlapping boxes must not change the union."""
    import random
    rng = random.Random(3)
    for _ in range(40):
        n = rng.randint(1, 60)
        boxes = []
        x = 0.0
        for _ in range(n):  # dense rows -> abutting cells
            w = rng.uniform(0.5, 2.0)
            if x > 20.0:
                x = 0.0
            boxes.append((x, rng.uniform(0, 5), x + w, rng.uniform(0, 5) + 1))
            x += w
        merged = C.merge_boxes(boxes)
        assert len(merged) <= len(boxes)
        for gap in (0.0, 3.0):
            assert _area(boxes, gap) == pytest.approx(_area(merged, gap))
            assert len(_loops(boxes, gap)) == len(_loops(merged, gap))


def test_merge_preserves_tiny_feature():
    """A real feature larger than the rounding tolerance must not be merged away."""
    boxes = [(0.0, 0.0, 10.0, 1.0), (10.000001, 0.0, 20.0, 1.0)]  # 1e-6 gap
    merged = C.merge_boxes(boxes)
    assert len(merged) == 2
    assert len(_loops(boxes, 0.0)) == 2


def test_expanded_accepts_empty_and_flat_input():
    assert C._expanded([], 0.0).shape == (0, 4)
    assert C._expanded((0.0, 0.0, 1.0, 1.0), 0.0).shape == (1, 4)
    assert C.contour_geometry([], 0.0) == ([], 0.0)
    loops, area = C.contour_geometry((0.0, 0.0, 1.0, 1.0), 0.0)
    assert area == pytest.approx(1.0) and len(loops) == 1


def test_loops_are_closed():
    boxes = [(0.0, 0.0, 1.0, 1.0)]
    for loop in _loops(boxes, 0.0):
        assert loop[0] == loop[-1]          # first == last (closed ring)
