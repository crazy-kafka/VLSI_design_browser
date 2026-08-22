"""Thermal colormap + grid -> QImage."""
import numpy as np
from PyQt5.QtGui import QImage

# Thermal gradient anchors, evenly spaced every 1/6:
# black (0%) -> dark blue (~16.67%) -> cyan (33.33%) -> green (50%) ->
# yellow (~66.67%) -> red (~83.33%) -> white (100%).
_THERMAL_ANCHORS = [
    (0.0,   (0, 0, 0)),          # black
    (1 / 6, (0, 0, 139)),        # dark blue  (~16.67%)
    (1 / 3, (0, 255, 255)),      # cyan       (33.33%)
    (1 / 2, (0, 255, 0)),        # green      (50%)
    (2 / 3, (255, 255, 0)),      # yellow     (66.67%)
    (5 / 6, (255, 0, 0)),        # red        (83.33%)
    (1.0,   (255, 255, 255)),    # white      (100%)
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


def grid_to_image(array: np.ndarray, lo: float, hi: float) -> QImage:
    """Map a grid array to a QImage with a 128-step gradient.

    Values at/above ``hi`` map to the last gradient step (white); values at
    ``lo`` map to black.
    """
    array = np.asarray(array, dtype="float64")
    rows, cols = array.shape
    span = (hi - lo) or 1.0
    t = (array - lo) / span

    out = np.zeros((rows, cols), dtype="uint32")
    idx = np.rint(np.clip(t, 0.0, 1.0) * 127).astype("int32")
    for i in range(128):
        color = _rgb32(thermal_color(i / 127.0))
        mask = (idx == i)
        out[mask] = color

    img = QImage(out.data, cols, rows, cols * 4, QImage.Format_RGB32)
    return img.copy()  # detach from the numpy buffer
