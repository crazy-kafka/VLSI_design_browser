"""Exact bin rasterisation.

`Bins` is the piece of the metal-density feature most able to be *quietly* wrong: a
vectorised split at bin boundaries that drops or double-counts an edge still produces a
plausible-looking map. So beyond the hand-computed cases there is a property test against
an independent brute-force reference - written the obvious slow way, one rectangle at a
time with explicit loops, so that a mistake in the repeat/tile/window machinery shows up
as a mismatch rather than as a slightly-off number nobody questions.
"""
import numpy as np
import pytest

from vlsi_viewer.raster import Bins


def _brute(rects, extent, grid_size):
    """The definition, implemented the slow obvious way: per rectangle, per overlapped bin."""
    x0e, y0e, x1e, y1e = extent
    cols = max(1, int(np.ceil((x1e - x0e) / grid_size)))
    rows = max(1, int(np.ceil((y1e - y0e) / grid_size)))
    out = np.zeros((rows, cols), dtype=np.float64)
    for rx0, ry0, rx1, ry1 in rects:
        lo_x, hi_x = min(rx0, rx1), max(rx0, rx1)
        lo_y, hi_y = min(ry0, ry1), max(ry0, ry1)
        lo_x, hi_x = max(lo_x, x0e), min(hi_x, x1e)
        lo_y, hi_y = max(lo_y, y0e), min(hi_y, y1e)
        if hi_x <= lo_x or hi_y <= lo_y:
            continue
        for row in range(rows):
            by0, by1 = y0e + row * grid_size, y0e + (row + 1) * grid_size
            oy = min(hi_y, by1) - max(lo_y, by0)
            if oy <= 0:
                continue
            for col in range(cols):
                bx0, bx1 = x0e + col * grid_size, x0e + (col + 1) * grid_size
                ox = min(hi_x, bx1) - max(lo_x, bx0)
                if ox > 0:
                    out[row, col] += ox * oy
    return out


def _bins(extent=(0.0, 0.0, 100.0, 100.0), grid_size=10.0, **kwargs):
    return Bins(extent, grid_size, **kwargs)


# -- grid geometry ------------------------------------------------------------------

def test_grid_shape_covers_the_extent():
    bins = _bins(extent=(0.0, 0.0, 95.0, 25.0), grid_size=10.0)
    assert bins.shape == (3, 10)          # ceil, so the grid never falls short


@pytest.mark.parametrize("grid_size", [0.0, -1.0])
def test_non_positive_grid_is_rejected(grid_size):
    with pytest.raises(ValueError):
        _bins(grid_size=grid_size)


# -- single rectangles --------------------------------------------------------------

def test_rect_inside_one_bin():
    bins = _bins()
    bins.add_rects([2.0], [3.0], [5.0], [7.0])
    grid = bins.grid()
    assert grid[0, 0] == pytest.approx(3.0 * 4.0)
    assert grid.sum() == pytest.approx(12.0)


def test_rect_over_four_bins():
    """A rectangle straddling one bin boundary in each axis, by hand."""
    bins = _bins()
    bins.add_rects([8.0], [8.0], [22.0], [16.0])
    grid = bins.grid()
    # x: 2 in bin 0, 10 in bin 1, 2 in bin 2.  y: 2 in bin 0, 6 in bin 1.
    assert grid[0, 0] == pytest.approx(2.0 * 2.0)
    assert grid[0, 1] == pytest.approx(10.0 * 2.0)
    assert grid[0, 2] == pytest.approx(2.0 * 2.0)
    assert grid[1, 0] == pytest.approx(2.0 * 6.0)
    assert grid[1, 1] == pytest.approx(10.0 * 6.0)
    assert grid[1, 2] == pytest.approx(2.0 * 6.0)
    assert grid.sum() == pytest.approx(14.0 * 8.0)


def test_rect_ending_on_a_bin_edge_does_not_leak_into_the_next():
    """'ceil(b) - 1' exists for this: a shape touching an edge covers only its own side."""
    bins = _bins()
    bins.add_rects([0.0], [0.0], [10.0], [10.0])
    grid = bins.grid()
    assert grid[0, 0] == pytest.approx(100.0)
    assert grid[0, 1] == 0.0
    assert grid[1, 0] == 0.0


def test_long_thin_rect_spans_many_bins():
    """A wire, not a cell: this is the shape the old rasteriser was worst at."""
    bins = _bins(extent=(0.0, 0.0, 3000.0, 10.0), grid_size=10.0)
    bins.add_rects([0.0], [4.9], [3000.0], [5.1])
    grid = bins.grid()
    assert grid.shape == (1, 300)
    assert grid.sum() == pytest.approx(3000.0 * 0.2, rel=1e-6)
    assert np.allclose(grid[0], 0.2 * 10.0)


def test_reversed_corners_are_normalised():
    """'+ RECT' corners come in whatever order the tool wrote them."""
    forward, backward = _bins(), _bins()
    forward.add_rects([2.0], [3.0], [8.0], [9.0])
    backward.add_rects([8.0], [9.0], [2.0], [3.0])
    np.testing.assert_allclose(forward.grid(), backward.grid())


def test_overlapping_rects_sum_rather_than_unite():
    """The metric's arithmetic depends on this: two wires at minimum spacing tile two
    track pitches, and wires *closer* than the spacing rule must be able to exceed 1.0
    so that a DRC-risk area reads as over-subscribed."""
    bins = _bins()
    bins.add_rects([0.0, 0.0], [0.0, 0.0], [10.0, 10.0], [10.0, 10.0])
    assert bins.grid()[0, 0] == pytest.approx(200.0)


def test_shapes_outside_the_grid_are_ignored():
    bins = _bins(extent=(0.0, 0.0, 50.0, 50.0), grid_size=10.0)
    bins.add_rects([100.0, -50.0], [100.0, -50.0], [200.0, -40.0], [200.0, -40.0])
    assert bins.grid().sum() == 0.0
    assert bins.n_empty >= 1


def test_shape_partly_outside_the_grid_is_clipped_not_dropped():
    bins = _bins(extent=(0.0, 0.0, 50.0, 50.0), grid_size=10.0)
    bins.add_rects([45.0], [0.0], [80.0], [10.0])
    assert bins.grid().sum() == pytest.approx(5.0 * 10.0)


@pytest.mark.parametrize("coords", [
    (0.0, 0.0, 0.0, 10.0),          # zero width
    (0.0, 0.0, 10.0, 0.0),          # zero height
    (5.0, 5.0, 5.0, 5.0),           # a point
])
def test_degenerate_shapes_contribute_nothing(coords):
    bins = _bins()
    bins.add_rects([coords[0]], [coords[1]], [coords[2]], [coords[3]])
    assert bins.grid().sum() == 0.0


def test_empty_batch_is_a_no_op():
    bins = _bins()
    bins.add_rects([], [], [], [])
    assert bins.grid().sum() == 0.0


# -- the property test --------------------------------------------------------------

def test_matches_brute_force_on_random_rectangles():
    """Thousands of random rectangles, including bin-straddling and long thin ones.

    The reference is an independent implementation of the same definition, written with
    explicit loops. It is slow and boring on purpose: the vectorised path's risk is in the
    repeat/tile arithmetic and the chunk windows, and this is what catches those.
    """
    rng = np.random.default_rng(20250913)
    extent = (0.0, 0.0, 200.0, 120.0)
    grid_size = 7.0

    n = 3000
    x0 = rng.uniform(-20.0, 200.0, n)
    y0 = rng.uniform(-20.0, 120.0, n)
    # A mix of fat and very thin, and a few long ones.
    w = np.where(rng.random(n) < 0.6, rng.uniform(0.0, 3.0, n), rng.uniform(0.0, 120.0, n))
    h = np.where(rng.random(n) < 0.6, rng.uniform(0.0, 3.0, n), rng.uniform(0.0, 60.0, n))
    rects = list(zip(x0, y0, x0 + w, y0 + h))

    bins = Bins(extent, grid_size)
    bins.add_rects(x0, y0, x0 + w, y0 + h)
    np.testing.assert_allclose(bins.grid(dtype="float64"),
                               _brute(rects, extent, grid_size), rtol=1e-9, atol=1e-9)


def test_shape_past_the_die_edge_is_clipped_to_the_die_not_the_grid():
    """The grid rounds up, so its last column overhangs the die.

    A 200 um die at a 7 um grid ends at 203 um. That 3 um of overhang is not design area,
    and a shape reaching the boundary must not be counted in it - clipping to the grid
    span instead inflated every edge cell.
    """
    extent = (0.0, 0.0, 200.0, 7.0)
    bins = Bins(extent, 7.0)
    assert bins.cols == 29                      # 29 * 7 = 203, so column 28 overhangs
    bins.add_rects([196.0], [0.0], [500.0], [7.0])
    grid = bins.grid(dtype="float64")
    assert grid[0, 28] == pytest.approx(4.0 * 7.0)      # 196..200, not 196..203
    assert grid.sum() == pytest.approx(4.0 * 7.0)


def test_chunking_does_not_change_the_result():
    """A tiny chunk exercises the window-splitting path, which must be invisible."""
    rng = np.random.default_rng(7)
    n = 500
    x0, y0 = rng.uniform(0, 90, n), rng.uniform(0, 90, n)
    w, h = rng.uniform(0.1, 40, n), rng.uniform(0.1, 40, n)

    big, small = _bins(chunk=1 << 20), _bins(chunk=64)
    for bins in (big, small):
        bins.add_rects(x0, y0, x0 + w, y0 + h)
    np.testing.assert_allclose(big.grid(dtype="float64"), small.grid(dtype="float64"))


def test_weights_scale_contributions():
    plain, weighted = _bins(), _bins()
    plain.add_rects([0.0], [0.0], [10.0], [10.0])
    weighted.add_rects([0.0], [0.0], [10.0], [10.0], weights=[2.5])
    assert weighted.grid()[0, 0] == pytest.approx(2.5 * plain.grid()[0, 0])


def test_output_dtype_is_float32_by_default():
    bins = _bins()
    bins.add_rects([0.0], [0.0], [10.0], [10.0])
    assert bins.grid().dtype == np.float32
    assert bins.grid(dtype="float64").dtype == np.float64


# -- non-rectangular shapes ---------------------------------------------------------

def test_diagonal_segment_is_not_a_bounding_box():
    """A 45-degree jog covers a hexagon, not its bounding box.

    The bounding box of a 10 um diagonal at a 0.2 um width is about 25x too large, which
    is why this path exists at all.
    """
    half = 0.5
    bins = Bins((0.0, 0.0, 40.0, 40.0), 10.0)
    bins.add_segment(5.0, 5.0, 15.0, 15.0, half)
    total = bins.grid(dtype="float64").sum()

    length = np.hypot(10.0, 10.0)
    assert total == pytest.approx(length * 2 * half + (2 * half) ** 2, rel=1e-6)
    # Far below the bounding box, and no mass in the corners it does not reach.
    assert total < (10.0 + 2 * half) ** 2 / 2
    grid = bins.grid(dtype="float64")
    assert grid[0, 3] == 0.0 and grid[3, 0] == 0.0


def test_axis_aligned_segment_reduces_to_a_rectangle():
    bins = Bins((0.0, 0.0, 100.0, 20.0), 10.0)
    bins.add_segment(1.0, 10.0, 21.0, 10.0, 0.5)
    assert bins.grid(dtype="float64").sum() == pytest.approx(20.0 * 1.0 + 1.0 * 1.0)


def test_zero_width_segment_contributes_nothing():
    bins = Bins((0.0, 0.0, 100.0, 20.0), 10.0)
    bins.add_segment(1.0, 10.0, 21.0, 10.0, 0.0)
    assert bins.grid().sum() == 0.0


def test_polygon_area_is_exact():
    bins = Bins((0.0, 0.0, 100.0, 100.0), 10.0)
    bins.add_polygon([(0.0, 0.0), (40.0, 0.0), (40.0, 30.0), (0.0, 30.0)])
    assert bins.grid(dtype="float64").sum() == pytest.approx(40.0 * 30.0)


def test_concave_polygon_is_handled():
    """An L-shape: shoelace-shaped area, minus the notch."""
    bins = Bins((0.0, 0.0, 100.0, 100.0), 10.0)
    bins.add_polygon([(0.0, 0.0), (40.0, 0.0), (40.0, 10.0), (10.0, 10.0),
                      (10.0, 40.0), (0.0, 40.0)])
    assert bins.grid(dtype="float64").sum() == pytest.approx(400.0 + 300.0)


@pytest.mark.parametrize("ring", [
    [(0.0, 0.0), (10.0, 0.0)],                       # too few points
    [(0.0, 0.0), (0.0, 0.0), (0.0, 0.0)],            # zero area
])
def test_degenerate_polygons_contribute_nothing(ring):
    bins = Bins((0.0, 0.0, 100.0, 100.0), 10.0)
    bins.add_polygon(ring)
    assert bins.grid().sum() == 0.0


def test_polygon_outside_the_grid_contributes_nothing():
    bins = Bins((0.0, 0.0, 50.0, 50.0), 10.0)
    bins.add_polygon([(100.0, 100.0), (140.0, 100.0), (140.0, 130.0), (100.0, 130.0)])
    assert bins.grid().sum() == 0.0


def test_rectangle_polygon_takes_the_fast_path_and_agrees_with_it():
    """An axis-aligned rectangle is rasterised vectorised, not one shapely call per bin.

    The per-bin path is still there for real polygons, but a die outline or a power ring is
    a rectangle, and on a 2000x2000 grid the per-bin loop costs four million shapely calls -
    measured at 345 seconds against under a second for the vectorised path.
    """
    ring = [(3.0, 4.0), (43.0, 4.0), (43.0, 34.0), (3.0, 34.0)]
    polygon_way = Bins((0.0, 0.0, 100.0, 100.0), 10.0)
    polygon_way.add_polygon(ring)
    assert polygon_way.grid(dtype="float64").sum() == pytest.approx(40.0 * 30.0)

    # A closed ring with the first vertex repeated must give the same answer.
    closed = Bins((0.0, 0.0, 100.0, 100.0), 10.0)
    closed.add_polygon(ring + [ring[0]])
    np.testing.assert_allclose(polygon_way.grid(dtype="float64"),
                               closed.grid(dtype="float64"))

    # And it must equal the rectangle path exactly, cell for cell.
    rectangle_way = Bins((0.0, 0.0, 100.0, 100.0), 10.0)
    rectangle_way.add_rects([3.0], [4.0], [43.0], [34.0])
    np.testing.assert_allclose(polygon_way.grid(dtype="float64"),
                               rectangle_way.grid(dtype="float64"))
