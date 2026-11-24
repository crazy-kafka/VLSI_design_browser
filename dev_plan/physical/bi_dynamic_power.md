# Data-path buffer/inverter dynamic power: tree metric, heat map, and the map-selector order

Status: current.

## Requirement

PD power analysis wants the dynamic-power contribution of the buffer/inverter cells,
because those cells drive the nets and usually carry a large share of the switching
power. The metric is **data-path** B/I power: clock-flagged buffers/inverters belong to
the clock tree and are excluded. Add:

1. a tree/region/compare power metric for dynamic power of data-path BUFFER and
   INVERTER cells;
2. a physical-mode heat map for the same quantity;
3. a map-selector order with density maps first and power maps below.

The viewer has per-instance `dynamic_power` only — no net-switching power, wire
capacitance or activity data — so the metric is the sum of the supplied per-instance
values for B/I cells. Connected-net switching is included exactly insofar as the power
file attributes it to the driving cell (the usual PD report convention). This limit was
confirmed with the user before implementation.

## Semantics

- Counted over the same "powered" set as leakage/dynamic: non-missing and
  non-physical-only instances; macros are in the set but carry no B/I flag, so only
  standard cells contribute.
- `is_buffer` / `is_inverter` are the existing cell-library flags (`CELL_ATTRS`), set by
  `cell_info_from_lef`'s name heuristics or by a supplied `cell_info.json`.
- **Clock cells are excluded**: an instance contributes only when its cell is
  `is_buffer or is_inverter` **and not** `is_clock_cell`. This makes the metric the
  data-path B/I power; clock-tree B/I power stays in the total `dynamic_power` and in
  the separate `CKB Cnt`/`B/I Cnt` columns.
- Metric key `bi_dynamic_power`, label `B/I Dyn Pwr`, `kind="power"` — so it joins
  `POWER_METRIC_KEYS` and is hidden by default when the input carries no power.
- Map key `bi_dynamic`, label `B/I dynamic power`; absolute power, unclamped, same
  area-fraction apportioning as the existing dynamic map.

## Implementation

- `vlsi_viewer/schema.py`: new `MetricSpec("bi_dynamic_power", "B/I Dyn Pwr", "power",
  False, _m_bi_dynamic)` after `Dynamic Power`. The registry drives the main tree,
  search, region tree, compare V1/V2/Δ columns and the Metrics menu automatically.
- `vlsi_viewer/metrics.py`: `RAW_COLS` / `_POWER_COLS` gain `bi_dynamic_power`; the power
  frame adds `np.where((is_buffer | is_inverter) & ~is_clock_cell, dynamic_power, 0.0)`
  before the per-parent groupby; `CACHE_VERSION` bumps `3` → `4` so stale pickles are
  rejected.
- `vlsi_viewer/region.py::RegionData.stats`: supplies the raw key from the existing
  per-box `dyn`, `is_bi` and `is_clock` cell-attr arrays, weighted by selection overlap
  — the same rule as `leakage_power`/`dynamic_power`, with clock cells excluded.
- `vlsi_viewer/physical.py`: a per-cell `is_bi_cell` flag (`is_buffer or is_inverter`,
  and not `is_clock_cell`) and per-box `_bis` array; a `bi_dynamic` grid accumulated in
  the same raster pass with `frac * bidyn` in `_acc` and the macro/large-patch branch;
  `PhysicalData.bi_dynamic` and `heat("bi_dynamic")`.
  Physical-only boxes are zeroed like the other power grids. `PhysicalData` deliberately
  does **not** gain `kinds()`: `LayoutView` treats any source with `kinds()` as
  fixed-ratio metal data, which would put every physical map on a 0..1 ramp.
- `vlsi_viewer/ui_layout.py`: `DENSITY_TYPES` (cell, ULVT) then optional `pins`, then
  `POWER_TYPES` (leakage, dynamic, B/I dynamic). Ranges remain keyed by the map kind, so
  the reorder does not disturb the per-map min/max cache.

## Tests

- `test_metrics.py`: registry key list; B/I metric sums only data-path BUF/INV powered
  power (a clock-flagged inverter is excluded while `bi_count`, `ckb_count` and total
  `dynamic_power` keep it), rolls up the hierarchy, ignores macros/physical-only/missing.
- `test_physical.py`: BUF and INV bins carry their dynamic power on `bi_dynamic`; a NAND,
  a physical-only cell and a clock buffer contribute zero (the clock buffer still raises
  `dynamic`); `heat("bi_dynamic")` returns the grid.
- `test_region.py`: the selected-region raw key is overlap-weighted, and a dedicated test
  proves a clock inverter is excluded; the existing whole-die equality test covers the
  new registry metric.
- `test_gui_smoke.py`: column counts (14 std metrics, 28 diff columns), selector order
  `[density, ulvt, pins, leakage, dynamic, bi_dynamic]`, new map renders, and the new
  power key hides/shows with `has_power`.

## Limits

- The metric/map are empty when the cell library does not set `is_buffer`/`is_inverter`
  (or when the input carries no power), consistent with the existing power surfaces.
- Clock-path exclusion depends on the cell library's `is_clock_cell` flag. The
  `cell_info_from_lef` name heuristic sets it for names starting `CK`/`DCCK`, so
  `CLKBUF*`/`CLKINV*`-style cells need the flag supplied by a `cell_info.json` (the
  bundled samples set it explicitly); an unflagged clock buffer would still count.
- There is no net-level data; the value is per-instance as supplied.
- The pinned map order replaces the old `density/leakage/dynamic/ulvt[/pins]` order
  recorded in [pin_density_map.md](pin_density_map.md) and
  [ulvt_density_map.md](ulvt_density_map.md); those documents remain the history of how
  each map was added.

## Verification

- Focused: `python -m pytest tests/test_metrics.py tests/test_physical.py
  tests/test_region.py tests/test_gui_smoke.py tests/test_parsers_eda.py
  tests/test_cli.py -q` → 220 passed.
- Full suite → 770 passed.
- Demo: `python quickstart.py physical` — the bundled hierarchy-expanded design has
  31,900 data-path B/I instances worth **2,775.66** dynamic (the 5,768 clock-flagged B/I
  instances worth 515.08 are excluded; all B/I is 37,668 / 3,290.74; total dynamic
  13,415.88). `python quickstart.py def` — 1,062 B/I instances worth 37.85 of the design's
  133.58 dynamic power (that LEF has no clock-flagged B/I cells, so the value is
  unchanged; physical-only TAP/DCAP records are excluded as on the existing power maps).
  Metric and map totals agree exactly on both samples.
