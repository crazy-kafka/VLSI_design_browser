# Enhanced thermal gradient (7 evenly-spaced stops, 128 steps)

## Change
The heat-map colormap in `vlsi_viewer/heatmap.py` now has 7 evenly-spaced
anchors (every 1/6) and is quantized to 128 steps:

black (0%) -> dark blue (~16.67%) -> cyan (33.33%) -> green (50%) -> yellow
(~66.67%) -> red (~83.33%) -> white (100%).

- `_THERMAL_ANCHORS` replaced with the 7 stops (dark blue = `(0,0,139)`).
- `grid_to_image` quantizes via `* 127` and builds 128 colors; the separate
  white mask is removed because white is now the last gradient anchor, and
  out-of-range values (`t > 1.0`) clip to the last step (white).
- `thermal_color` (piecewise-linear interpolation) and the legend
  (`_legend_pixmap`) are unchanged and pick up the new anchors automatically.

## Test
`tests/test_heatmap.py::test_thermal_anchors` asserts the 7 exact stop colors;
`test_grid_to_image_white_above_max` still passes unchanged (values above max
render white).

## Verification
- `python -m pytest -q` -> 68 passed.
- Rendered ramp: step 0 = black, ~21 = dark blue (0,0,138), ~42 = cyan,
  ~63 = green, ~85 = yellow, ~106 = red, 127 = white.
- Real density map: bins == 1.0 render white (0xffffffff); ~0.25 blue, ~0.5
  green, ~0.75 orange — fully-packed regions are white, nothing else is.
