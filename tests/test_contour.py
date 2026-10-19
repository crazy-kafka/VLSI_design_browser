"""Tests for the shapely-backed hierarchy contour module."""
import numpy as np
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


def _pandas_merge(boxes):
    """Reference implementation: the old pandas two-pass run merge."""
    import pandas as pd

    arr = np.round(np.asarray(boxes, dtype=float), 9)
    if arr.size == 0:
        return np.empty((0, 4))
    df = pd.DataFrame(arr, columns=["x0", "y0", "x1", "y1"])

    def _merge_runs(frame, by, start_col, hi):
        frame = frame.sort_values(by + [start_col])
        grp = frame.groupby(by, sort=False)
        frame["run_max"] = grp[hi].cummax()
        frame["prev_max"] = grp["run_max"].shift(1).fillna(-np.inf)
        frame["seg"] = np.cumsum(frame[start_col].values > frame["prev_max"].values)
        return frame.groupby(by + ["seg"], sort=False).agg(
            **{start_col: (start_col, "min"), hi: (hi, "max")}).reset_index()

    strips = _merge_runs(df, ["y0", "y1"], "x0", "x1")
    merged = _merge_runs(strips, ["x0", "x1"], "y0", "y1")
    return merged[["x0", "y0", "x1", "y1"]].to_numpy(dtype=float)


def _canonical(rects):
    arr = np.asarray(rects, dtype=float).reshape(-1, 4)
    if arr.size == 0:
        return arr
    return arr[np.lexsort((arr[:, 3], arr[:, 2], arr[:, 1], arr[:, 0]))]


def _assert_same_rects(got, want):
    got, want = _canonical(got), _canonical(want)
    assert got.shape == want.shape
    np.testing.assert_array_equal(got, want)


def _valid_random_boxes(rng, n):
    boxes = []
    for _ in range(n):
        x = rng.uniform(-5.0, 40.0)
        y = rng.uniform(-5.0, 40.0)
        w = rng.choice([0.0, rng.uniform(0.01, 3.0)])
        h = rng.choice([0.0, rng.uniform(0.01, 3.0)])
        boxes.append((x, y, x + w, y + h))
    return boxes


def test_merge_rects_matches_the_pandas_reference():
    import random
    rng = random.Random(17)
    cases = [
        [(0.0, 0.0, 1.0, 1.0)],
        [(0.0, 0.0, 1.0, 1.0), (1.0, 0.0, 2.0, 1.0)],          # abutting
        [(0.0, 0.0, 2.0, 2.0), (1.0, 1.0, 3.0, 3.0)],          # overlapping
        [(0.0, 0.0, 3.0, 3.0), (1.0, 1.0, 2.0, 2.0)],          # nested
        [(0.0, 0.0, 1.0, 1.0), (0.0, 0.0, 1.0, 1.0)],          # duplicates
        [(0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 1.0, 0.0)],          # zero-size
        [(10000000.0, 10000000.0, 10000001.0, 10000001.0),
         (10000001.0, 10000000.0, 10000002.0, 10000001.0)],     # large offsets
        [(0.0, 0.0, 1.0, 1.0), (1.000000001, 0.0, 2.0, 1.0)],  # round quantum
    ]
    for _ in range(30):
        cases.append(_valid_random_boxes(rng, rng.randint(1, 80)))
    for boxes in cases:
        for gap in (0.0, 3.0):
            _assert_same_rects(C.merge_rects(boxes, gap),
                               _pandas_merge(C._expanded(boxes, gap)))


def test_merge_rects_is_well_formed_and_fused():
    import random
    rng = random.Random(23)
    boxes = _valid_random_boxes(rng, 200)
    for gap in (0.0, 3.0):
        got = C.merge_rects(boxes, gap)
        assert got.ndim == 2 and got.shape[1] == 4
        assert np.isfinite(got).all()
        assert (got[:, 0] <= got[:, 2]).all()
        assert (got[:, 1] <= got[:, 3]).all()
        assert len(got) <= len(boxes)
        # Fused expansion + rounding must equal expanding first, then merging.
        _assert_same_rects(got, C.merge_boxes(C._expanded(boxes, gap)))
        if gap == 0.0:
            _assert_same_rects(C.merge_boxes(boxes), got)


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
            y = rng.uniform(0, 5)
            boxes.append((x, y, x + w, y + rng.uniform(0.5, 1.5)))
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


def test_rect_union_area_matches_shapely():
    """The exact sweep must agree with shapely's union area."""
    from shapely.geometry import box as sbox
    from shapely.ops import unary_union

    cases = [
        [],
        [(0.0, 0.0, 1.0, 1.0)],
        [(0.0, 0.0, 2.0, 1.0), (2.0, 0.0, 4.0, 1.0)],       # abutting
        [(0.0, 0.0, 2.0, 2.0), (1.0, 1.0, 3.0, 3.0)],       # overlapping
        [(0.0, 0.0, 3.0, 3.0), (1.0, 1.0, 2.0, 2.0)],       # nested
        [(0.0, 0.0, 1.0, 1.0), (0.0, 0.0, 1.0, 1.0)],       # duplicate
        [(0.0, 0.0, 3.0, 1.0), (0.0, 2.0, 3.0, 3.0),
         (0.0, 1.0, 1.0, 2.0), (2.0, 1.0, 3.0, 2.0)],       # donut
        [(0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 1.0, 0.0)],       # zero area
        [(-5.0, -5.0, 5.0, 5.0), (-4.0, -6.0, 6.0, 4.0)],   # negative coords
    ]
    import random
    rng = random.Random(29)
    for _ in range(60):
        rects = []
        for _ in range(rng.randint(1, 50)):
            x, y = rng.uniform(-10, 10), rng.uniform(-10, 10)
            rects.append((x, y, x + rng.uniform(0.1, 4), y + rng.uniform(0.1, 4)))
        cases.append(rects)

    for rects in cases:
        ref = unary_union([sbox(*r) for r in rects]).area if rects else 0.0
        got = C.rect_union_area(rects)
        assert got == pytest.approx(ref, rel=1e-9, abs=1e-12)


def test_loops_are_closed():
    boxes = [(0.0, 0.0, 1.0, 1.0)]
    for loop in _loops(boxes, 0.0):
        assert loop[0] == loop[-1]          # first == last (closed ring)
