import numpy as np

from vlsi_viewer.heatmap import grid_to_image, thermal_color


def test_thermal_anchors():
    assert thermal_color(0.0) == (0, 0, 0)       # black (low end)
    assert thermal_color(1.0) == (255, 0, 0)     # red
    mid = thermal_color(0.5)
    # somewhere between blue and green (should have green component)
    assert mid[1] > 0
    assert mid[0] == 0


def test_grid_to_image_white_above_max():
    arr = np.array([[0.0, 0.5, 2.0]])
    img = grid_to_image(arr, 0.0, 1.0)
    assert img.width() == 3 and img.height() == 1
    white = (255 << 24) | (255 << 16) | (255 << 8) | 255  # ARGB
    # index 0 -> dark, index 1 -> mid, index 2 (>= max) -> white
    assert img.pixel(0, 0) != white
    assert img.pixel(1, 0) != white
    assert img.pixel(2, 0) == white
