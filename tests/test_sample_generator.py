"""Placement invariants of the physical sample generator.

`sample_data/physical/generate_physical.py` is a standalone script, so it is loaded
by path here. These guard the properties that make its density heat map read as a
real utilisation field rather than solid rectangles - a regression in any of them is
invisible in the extremes of the map (the old flat version passed `verify()`'s
max/min checks), so they are asserted directly on the placement.
"""
import importlib.util
import os
import random

import pytest

_GEN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "sample_data", "physical", "generate_physical.py")

# the IFU sub-block region, as build_subblock lays it out
REGION_W, REGION_H = 170.0, 67.2


@pytest.fixture(scope="module")
def gp():
    spec = importlib.util.spec_from_file_location("generate_physical", _GEN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _place(gp, n=8000, seed=0, phase=0.4):
    rng = random.Random(seed)
    cells = [rng.choice(gp.STD_POOL) for _ in range(n)]
    return gp.place_std_rows(cells, 0.0, 0.0, REGION_W, REGION_H, phase=phase, rng=rng)


def _rows(gp, placed):
    """row y -> list of (x0, x1) spans."""
    rows = {}
    for name, x, y, _orient in placed:
        rows.setdefault(round(y, 6), []).append((x, x + gp.CELLS[name]["size_x"]))
    return rows


def test_placement_is_legal(gp):
    placed, dropped = _place(gp)
    assert dropped == 0
    assert len(placed) == 8000
    for name, x, y, _orient in placed:
        sx, sy = gp.CELLS[name]["size_x"], gp.CELLS[name]["size_y"]
        assert 0.0 <= x and x + sx <= REGION_W + 1e-9, f"{name} escapes the region in x"
        assert 0.0 <= y and y + sy <= REGION_H + 1e-9, f"{name} escapes the region in y"
        assert abs(x / gp.SITE - round(x / gp.SITE)) < 1e-9, f"{name} is off the site grid"
    for y, spans in _rows(gp, placed).items():
        spans.sort()
        for (a0, a1), (b0, b1) in zip(spans, spans[1:]):
            assert b0 >= a1 - 1e-9, f"cells overlap in row y={y}: {a1} > {b0}"


def test_whitespace_is_inside_rows_not_one_stripe(gp):
    """The old bug: one `util` stripe at a fixed x left every interior bin at 1.0."""
    placed, _ = _place(gp)
    rows = _rows(gp, placed)
    interior_holes = 0
    for spans in rows.values():
        order = sorted(spans)
        right_edge = max(x1 for _, x1 in order)
        for (_a0, a1), (b0, _b1) in zip(order, order[1:]):
            if b0 - a1 > 1e-9 and b0 < right_edge - 1e-9:
                interior_holes += 1
    # ~8000 cells over ~67 rows: a per-row constant here would be < 100
    assert interior_holes > 300, f"only {interior_holes} whitespace holes inside rows"


def test_bin_scale_fill_varies(gp):
    """Fill measured in heat-map-bin windows must span a wide range.

    The heat map samples 3.0-wide bins, so this mirrors what it renders. The old
    one-stripe layout held every interior bin at ~1.0 (spread ~0.15); a real
    utilisation field spans most of the range.
    """
    placed, _ = _place(gp, n=12000)
    assert placed
    BIN = 3.0
    filled = {}
    for name, x, y, _o in placed:
        key = (round(y, 6), int(x // BIN))
        filled[key] = filled.get(key, 0.0) + gp.CELLS[name]["size_x"]
    vals = [min(v / BIN, 1.0) for v in filled.values()]
    spread = max(vals) - min(vals)
    assert spread > 0.5, f"bin fill barely varies (spread {spread:.2f})"
    assert sum(v < 0.7 for v in vals) > 0.1 * len(vals), "almost no sparse bins"
    assert sum(v > 0.9 for v in vals) > 0.1 * len(vals), "almost no dense bins"
