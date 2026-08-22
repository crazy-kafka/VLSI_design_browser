import numpy as np

from vlsi_viewer.heatmap import grid_to_image, thermal_color


def test_thermal_anchors():
    # seven evenly-spaced stops: black -> dark blue -> cyan -> green ->
    # yellow -> red -> white
    assert thermal_color(0.0) == (0, 0, 0)
    assert thermal_color(1 / 6) == (0, 0, 139)
    assert thermal_color(1 / 3) == (0, 255, 255)
    assert thermal_color(1 / 2) == (0, 255, 0)
    assert thermal_color(2 / 3) == (255, 255, 0)
    assert thermal_color(5 / 6) == (255, 0, 0)
    assert thermal_color(1.0) == (255, 255, 255)
    # midpoints interpolate smoothly between stops
    mid = thermal_color(1 / 4)   # between dark blue and cyan
    assert mid[0] == 0 and mid[1] > 0 and mid[2] > 0


def test_grid_to_image_white_above_max():
    arr = np.array([[0.0, 0.5, 2.0]])
    img = grid_to_image(arr, 0.0, 1.0)
    assert img.width() == 3 and img.height() == 1
    white = (255 << 24) | (255 << 16) | (255 << 8) | 255  # ARGB
    # index 0 -> dark, index 1 -> mid, index 2 (>= max) -> white
    assert img.pixel(0, 0) != white
    assert img.pixel(1, 0) != white
    assert img.pixel(2, 0) == white
