import os
import re

import numpy as np

from vlsi_viewer.heatmap import grid_to_image, thermal_color

_SAMPLE = os.path.join(os.path.dirname(__file__), "..", "dev_plan", "code_sample",
                       "heatmap_color.py")


def _innovus_sample_colors():
    """Parse the INNOVUS gradient sample: 127 QColor entries, written high -> low."""
    with open(_SAMPLE, encoding="utf-8") as fh:
        text = fh.read()
    return [tuple(int(v) for v in m)
            for m in re.findall(r"QColor\((\d+), (\d+), (\d+), (\d+)\)", text)]


def test_thermal_anchors():
    # seven evenly-spaced stops matching INNOVUS, low -> high:
    # navy -> blue -> cyan -> green -> yellow -> red -> near-white
    assert thermal_color(0.0) == (0, 0, 102)
    assert thermal_color(1 / 6) == (0, 0, 255)
    assert thermal_color(1 / 3) == (0, 255, 255)
    assert thermal_color(1 / 2) == (0, 128, 0)
    assert thermal_color(2 / 3) == (255, 255, 0)
    assert thermal_color(5 / 6) == (255, 0, 0)
    assert thermal_color(1.0) == (255, 243, 243)
    # midpoints interpolate smoothly between stops
    mid = thermal_color(1 / 4)   # between blue and cyan
    assert mid[0] == 0 and mid[1] > 0 and mid[2] > 0


def test_ramp_tracks_innovus_sample():
    """The ramp must reproduce the INNOVUS table within its own quantization noise.

    The sample is INNOVUS's 127-entry integer table; our stops are evenly spaced at
    k/6 while INNOVUS's own segment boundaries sit a fraction of a step off that grid
    (measured: 20.6 / 40.9 / 62.5 / 84.1 / 104.4). That misalignment costs at most one
    step's worth of colour, all of it in the yellow -> green transition, so a 16/255
    bound is the floor for this architecture (mean deviation is ~2/255 and only 12 of
    the 127 steps exceed 8). The previous ramp was off by 125/255 because its green
    stop was twice as bright as INNOVUS's.
    """
    sample = _innovus_sample_colors()
    assert len(sample) == 127
    worst = 0
    total = 0
    for i, (r, g, b, _alpha) in enumerate(sample):
        got = thermal_color(1.0 - i / (len(sample) - 1))   # sample is high -> low
        worst = max(worst, abs(got[0] - r), abs(got[1] - g), abs(got[2] - b))
        total += abs(got[0] - r) + abs(got[1] - g) + abs(got[2] - b)
    assert worst <= 16, f"max channel deviation {worst}/255 from INNOVUS"
    mean = total / (len(sample) * 3)                     # per channel
    assert mean <= 5.0, f"mean channel deviation {mean:.1f}/255"


def test_grid_to_image_top_value_above_max():
    arr = np.array([[0.0, 0.5, 2.0]])
    img = grid_to_image(arr, 0.0, 1.0)
    assert img.width() == 3 and img.height() == 1
    near_white = (255 << 24) | (255 << 16) | (243 << 8) | 243   # ARGB
    # index 0 -> navy, index 1 -> mid, index 2 (>= max) -> near-white top stop
    assert img.pixel(0, 0) == (255 << 24) | (0 << 16) | (0 << 8) | 102
    assert img.pixel(1, 0) != near_white
    assert img.pixel(2, 0) == near_white
