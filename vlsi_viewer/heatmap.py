"""Thermal colormap + grid -> QImage."""
import numpy as np
from PyQt5.QtGui import QImage

# Gradient anchors matching the INNOVUS heat-map ramp, evenly spaced every 1/6.
# INNOVUS ships this as a 127-entry table running high -> low; the stops below are
# the same ramp reversed into low -> high (see dev_plan/heatmap_innovus_gradient.md):
# navy (0%) -> blue (~16.67%) -> cyan (33.33%) -> green (50%) ->
# yellow (~66.67%) -> red (~83.33%) -> near-white (100%).
_THERMAL_ANCHORS = [
    (0.0,   (0, 0, 102)),        # navy
    (1 / 6, (0, 0, 255)),        # blue       (~16.67%)
    (1 / 3, (0, 255, 255)),      # cyan       (33.33%)
    (1 / 2, (0, 128, 0)),        # green      (50%)
    (2 / 3, (255, 255, 0)),      # yellow     (66.67%)
    (5 / 6, (255, 0, 0)),        # red        (83.33%)
    (1.0,   (255, 243, 243)),    # near-white (100%)
]


def thermal_color(t):
    """Piecewise-linear interpolation over the thermal anchors for t in [0, 1]."""
    if t <= 0.0:
        return _THERMAL_ANCHORS[0][1]
    if t >= 1.0:
        return _THERMAL_ANCHORS[-1][1]
    for (t0, c0), (t1, c1) in zip(_THERMAL_ANCHORS, _THERMAL_ANCHORS[1:]):
        if t <= t1:
            f = (t - t0) / (t1 - t0)
            return tuple(int(round(a + (b - a) * f)) for a, b in zip(c0, c1))
    return _THERMAL_ANCHORS[-1][1]


def _rgb32(rgb):
    r, g, b = rgb
    return (0xFF << 24) | (r << 16) | (g << 8) | b


# The 128 raster steps, resolved once: bin index -> packed RGB32.
_LUT = np.array([_rgb32(thermal_color(i / 127.0)) for i in range(128)], dtype="uint32")


def grid_to_image(array: np.ndarray, lo: float, hi: float) -> QImage:
    """Map a grid array to a QImage with a 128-step gradient.

    Values at/above ``hi`` map to the last gradient step (near-white); values at
    ``lo`` map to navy.
    """
    array = np.asarray(array, dtype="float64")
    rows, cols = array.shape
    span = (hi - lo) or 1.0
    t = (array - lo) / span

    idx = np.rint(np.clip(t, 0.0, 1.0) * 127).astype("int32")
    out = _LUT[idx]

    img = QImage(out.data, cols, rows, cols * 4, QImage.Format_RGB32)
    return img.copy()  # detach from the numpy buffer
