"""Tests for the dual-backend hierarchy contour module."""
import pytest

from vlsi_viewer import contour as C


def _run_both(fn):
    """Run fn against both backends and return (shapely, manual) results."""
    out = {}
    for backend in ("shapely", "scipy"):
        old = C._BACKEND
        C._BACKEND = backend
        try:
            out[backend] = fn()
        finally:
            C._BACKEND = old
    return out["shapely"], out["scipy"]


def _area(boxes, gap):
    return C.contour_area(boxes, gap)


def _loops(boxes, gap):
    return C.contour_loops(boxes, gap)


@pytest.mark.parametrize("gap", [0.0, 3.0])
def test_contour_area_matches_shapely(gap):
    boxes = [(0.0, 0.0, 1.0, 1.0), (1.0, 0.0, 2.0, 1.0), (0.0, 1.0, 1.0, 2.0)]
    sa, ma = _run_both(lambda: _area(boxes, gap))
    assert ma == pytest.approx(sa)
    if gap == 0.0:
        assert ma == pytest.approx(3.0)   # exact union of the three boxes
    else:
        assert ma > 3.0                   # gap padding enlarges the scope


def test_abutting_boxes_one_loop():
    boxes = [(0.0, 0.0, 1.0, 1.0), (1.0, 0.0, 2.0, 1.0)]  # form a 2x1 rectangle
    sl, ml = _run_both(lambda: _loops(boxes, 0.0))
    assert len(sl) == 1
    assert len(ml) == 1


def test_corner_touch_is_two_loops():
    # touching only at a corner -> two separate polygons (both backends)
    boxes = [(0.0, 0.0, 1.0, 1.0), (1.0, 1.0, 2.0, 2.0)]
    sl, ml = _run_both(lambda: _loops(boxes, 0.0))
    assert len(sl) == 2
    assert len(ml) == 2


def test_scatter_beyond_gap_is_two_loops():
    boxes = [(0.0, 0.0, 1.0, 1.0), (10.0, 0.0, 11.0, 1.0)]
    sl, ml = _run_both(lambda: _loops(boxes, 0.0))
    assert len(sl) == 2
    assert len(ml) == 2


def test_scatter_within_gap_merges():
    boxes = [(0.0, 0.0, 1.0, 1.0), (2.0, 0.0, 3.0, 1.0)]  # 1-unit gap
    sl, ml = _run_both(lambda: _loops(boxes, 2.0))       # gap 2 bridges it
    assert len(sl) == 1
    assert len(ml) == 1
    # with gap 0 they stay separate
    sl0, ml0 = _run_both(lambda: _loops(boxes, 0.0))
    assert len(sl0) == 2 and len(ml0) == 2


def test_donut_has_hole():
    boxes = [(0.0, 0.0, 3.0, 1.0), (0.0, 2.0, 3.0, 3.0),
             (0.0, 1.0, 1.0, 2.0), (2.0, 1.0, 3.0, 2.0)]
    sl, ml = _run_both(lambda: _loops(boxes, 0.0))
    assert len(sl) == 2  # exterior + hole
    assert len(ml) == 2
    sa, ma = _run_both(lambda: _area(boxes, 0.0))
    assert ma == pytest.approx(sa)
    assert ma == pytest.approx(8.0)


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
            a0, a1 = C.contour_area(boxes, gap), C.contour_area(merged, gap)
            assert a0 == pytest.approx(a1)
            l0, l1 = C.contour_loops(boxes, gap), C.contour_loops(merged, gap)
            assert len(l0) == len(l1)


def test_area_matches_across_backends_fuzz():
    import random
    rng = random.Random(0)
    for _ in range(50):
        n = rng.randint(1, 20)
        boxes = [(rng.uniform(0, 20), rng.uniform(0, 20),
                  rng.uniform(0, 20) + 1, rng.uniform(0, 20) + 1) for _ in range(n)]
        boxes = [(a, b, a + 1.0, b + 1.0) for a, b in
                 ((rng.uniform(0, 20), rng.uniform(0, 20)) for _ in range(n))]
        gap = rng.choice([0.0, 2.0])
        sa, ma = _run_both(lambda: _area(boxes, gap))
        assert ma == pytest.approx(sa, abs=1e-6)
