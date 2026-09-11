# Realistic density field for the physical sample

## Problem

`sample_data/physical/` rendered as flat white rectangles. Measured through the app's
own `build_physical()` (170x170 bins, grid 3.0):

| | before | after |
|---|---|---|
| bins >= 0.99 (share of occupied) | **88.5 %** | **21.0 %** |
| mid-range bins (0.2-0.95) | 4.8 % | **78.0 %** |
| distinct density values | 88 | 173 |
| bin-to-bin roughness (mean abs diff) | 0.148 | **0.065** |
| leaf boxes / box area ÷ die area | 108,436 / 0.604 | 108,436 / 0.604 |

The 60 % "average density" was an artifact of 35.5 % of the die being *entirely* empty,
not of distributed whitespace.

## Root cause

`ROW_UTIL = 0.85` was applied **once per region** as `row_right = x0 + w * util`, so the
15 % slack was a single vertical stripe at one x for every row of a region; inside a row
cells were exactly contiguous (`x += sx`) and rows were butted at pitch 1.0 with zero
vertical slack. A 3.0-wide bin therefore spans 3 rows of a 100 %-contiguous band and
measures exactly 1.0 unless it straddles a region edge. Only ~7 % of the die reached the
mid-range ramp.

`verify()` could not catch it: it asserted only `dmax > 0.85`, `dmax <= 1.0`,
`dmin < 0.05` and `0.55 <= avg <= 0.65`, all of which a saturated map passes.

## Change — `sample_data/physical/generate_physical.py`

1. **Site-aligned rows with distributed whitespace.** `SITE = 0.2` (every library width
   is already a multiple of 0.2, so snapping is lossless). The cursor still only ever
   advances, so non-overlap is preserved.
2. **Smooth 2-D activity field** (`_activity` / `_row_util`): four sinusoids in the
   block's local frame give a target fill of ~0.38 sparsest to ~0.90 densest. It varies
   in x *and* y — a per-row constant only ever yields vertical stripes.
3. **Gaps paid from a running debt, not rolled per cell.** Each cell accrues
   `(1 - util) * width` of owed whitespace and pays it in site-sized holes.
   *This is the load-bearing detail:* an independent Bernoulli draw per cell puts a
   random number of holes in every bin, which renders as per-bin speckle
   (roughness 0.148). Tracking the debt keeps holes evenly spread so bin density
   tracks the field (roughness 0.065) — a 3.4x smoother map that reads as a field.
   The small +/-1 site jitter only avoids perfectly periodic spacing.
4. **Macros as blockages, not reserved strips.** `build_subblock` now lays rows across
   the whole region and passes the SRAM stack as `blocked` rects, so logic reclaims the
   area beside and beneath the macros instead of reserving a dead strip. This is both
   realistic (row-based placement really does run past macros) and what makes the
   counts fit: IEX previously dropped 229 cells and the uncore strips ~1,500.
   `place_std_rows` now asserts `not dropped`, so silent capacity loss fails loudly.
5. `place_std_rows_blocked` merged into `place_std_rows(..., blocked=())` — one code
   path, three call sites.

No geometry changes were needed: the die stays 510x510, the instance count stays
108,436, and the average density stays 0.604, so the README's "~100k-instance
CPU-cluster sample" and the 90k-110k bound both still hold. (The central cross is 60
wide, derived as `die - 2*margin - 2*core`; an earlier estimate of 40 was wrong.)

## Guarding the distribution

`verify()` now asserts the *shape* of the occupied-bin histogram, not just its extremes:
`distinct values > 30`, `mid-range share > 50 %`, `roughness < 0.12`, and
`saturated share < 35 %`. The saturation bound sits above the SRAM macro floor
deliberately: macros are 17.7 % of the die = ~23 % of occupied bins and *should* be
fully packed — measured, macros account for ~96 % of all saturated bins, with std-cell
logic contributing 0.7 % of the die. The old striped layout measured 88.5 %.

## Test

`tests/test_sample_generator.py` (new, 3 tests) loads the generator by path and asserts
on its placement directly, since a flattened map still passes every extreme-value check:
cells stay on the site grid inside the region with no overlaps in any row; whitespace
holes appear *inside* rows (the one-stripe layout had none); and bin-window fill spans
> 0.5 with both sparse and dense bins present.

## Verification

- `python sample_data/physical/generate_physical.py` -> self-verify OK
  (108,436 boxes, avg 0.604, 21.0 % saturated, 78.0 % mid-range, 173 distinct,
  roughness 0.065).
- `python -m pytest -q` -> 94 passed (91 before + 3 new).
- Overlap check over the regenerated data: **0 overlapping pairs** in 749,550 pair
  checks; box area ÷ die area 0.6044; count in [90k, 110k]; max density 1.0.
- Rendered density map compared before/after
  (`%TEMP%/heatmap_real_density.png` vs `%TEMP%/heatmap_real_density_after.png`):
  flat white rectangles -> smooth utilisation gradients with green low-activity patches,
  crisp macro rectangles and empty channels.

## Out of scope

- Vt-mix and power realism (ULVT is still a uniform sprinkle; per-instance power is still
  uncorrelated with cell type). The power maps do inherit the new spatial texture.
- Macro halos/keepouts, explicit routing channels, pin density, filler/tap cells.
