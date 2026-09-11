# INNOVUS heat-map gradient + per-map min/max

## 1. Gradient replaced with the INNOVUS ramp

`dev_plan/code_sample/heatmap_color.py` (supplied as the INNOVUS reference) is 127
`QColor(r,g,b,240)` entries. Analysis showed it is structurally **7 stops evenly spaced
at k/6 with linear interpolation** - the same architecture `vlsi_viewer/heatmap.py`
already used - with the stops listed **high -> low**, and integer-quantization artifacts
at indices 21/42/63/84/105. The alpha (240) is deliberately ignored.

`_THERMAL_ANCHORS` is now the same ramp reversed into low -> high:

| t | colour |
|---|---|
| 0 | `(0,0,102)` navy |
| 1/6 | `(0,0,255)` blue |
| 1/3 | `(0,255,255)` cyan |
| 1/2 | `(0,128,0)` green |
| 2/3 | `(255,255,0)` yellow |
| 5/6 | `(255,0,0)` red |
| 1 | `(255,243,243)` near-white |

The stop colours were recovered by fitting each segment as a line on its interior
points (excluding the boundary artifacts) and evaluating at the stop. The fit lands on
canonical web colours, independently confirming the stops and their positions.

### What was wrong before

| t | old | INNOVUS | dev |
|---|---|---|---|
| 0.000 | `(0,0,0)` black | `(0,0,102)` navy | 102 |
| 0.167 | `(0,0,139)` dark blue | `(0,0,255)` blue | 116 |
| 0.333 | `(0,255,255)` cyan | `(0,255,255)` cyan | ok |
| 0.500 | `(0,255,0)` green | `(0,128,0)` green | **128** |
| 0.667 | `(255,255,0)` yellow | `(255,255,0)` yellow | ok |
| 0.833 | `(255,0,0)` red | `(255,0,0)` red | ok |
| 1.000 | `(255,255,255)` white | `(255,243,243)` near-white | 17 |

The warm half already matched; the cold half was wrong (black and dark blue instead of
navy and blue) and the green stop was exactly twice as bright as INNOVUS's - the
visible symptom that prompted the change. 69/128 rasterized steps were off by more
than 32.

### Result

Deviation from the INNOVUS table across the 128 raster steps: **max 13/255, mean
4.9/255**. The residual is not anchor error - it is INNOVUS's own ±1-step rounding,
since its segment boundaries sit a fraction of a step off the k/6 grid (measured
20.6 / 40.9 / 62.5 / 84.1 / 104.4). Both ends of the ramp are now visibly correct (see
`_THERMAL_ANCHORS` comment for the ramp order).

`grid_to_image` also builds its 128 bin colours into a module-level `_LUT` once and
gathers it, replacing a loop of 128 full-array `idx == i` comparisons.

### Consequence: the top stop is near-white, not pure white

A fully-packed bin (density 100%) now renders `(255,243,243)` rather than `#FFFFFF`.
That is what INNOVUS does; the colour is ~5% off pure white. The snap-to-exactly-1.0
clamp in `physical.py` is unchanged - it still guarantees fully-packed bins land on the
top stop. `README.md` and the `LegendWidget` docstring were reworded accordingly.

## 2. User-edited min/max survives a map switch

`LayoutView._on_type` called `_autoset_range()` unconditionally on every Map combo
switch, and `_lo`/`_hi` were a single un-keyed pair, so the user's edit was discarded on
every switch and re-derived from the data on return.

`LayoutView` now keeps `self._ranges` (kind -> `(lo, hi)`). `_on_type` records the
outgoing map's range and restores it on revisit; `_autoset_range` runs only on the
**first** visit to each map. The spin-box/legend writes were factored into
`_set_range(lo, hi)` so auto-range and restore share one path (both must write the spin
boxes with `blockSignals` to avoid re-entering `_apply_range`).

Range is per-session and per-`LayoutView` (compare tabs don't share it); the repo has no
`QSettings` usage, and the `schema._GRADIENT_RANGES` precedent is likewise in-memory.

## Test

- `tests/test_heatmap.py::test_thermal_anchors` - the 7 new stops, exact.
- `tests/test_heatmap.py::test_ramp_tracks_innovus_sample` - parses the sample and
  bounds the deviation at max 16/255 and mean 5/255 (measured 13 and 4.9). Its docstring
  records why the residual cannot reach 0 for a k/6-spaced ramp.
- `tests/test_heatmap.py::test_grid_to_image_top_value_above_max` - top stop is
  `(255,243,243)`, low stop is navy.
- `tests/test_gui_smoke.py::test_layout_range_kept_across_map_switch` - edited
  min/max survives switching map type and back (fails before the fix: `(0.0, 0.25)`).
- `tests/test_gui_smoke.py::test_layout_first_visit_to_map_autotanges` - an unvisited
  map still derives its range from the data.

## Verification

- `python -m pytest -q` -> 91 passed.
- Ramp vs INNOVUS, 128 raster steps: max 13/255, mean 4.9/255 (was max 125).
- Side-by-side render (`%TEMP%/heatmap_innovus_preview.png`): new ramp, INNOVUS sample
  reversed, and a synthetic density grid. The two ramps are visually identical and the
  fully-packed block renders near-white.
