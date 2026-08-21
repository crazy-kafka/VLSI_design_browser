# VLSI Design Hierarchy Visualization Tool

A PyQt5 desktop application for physical-design engineers to browse a gate-level
netlist's **hierarchy tree** and inspect per-level statistics. It reads a cell
library plus one or more block files, reconstructs (and auto-composes) the design
hierarchy, and renders a sortable, searchable tree-table of metrics — plus a
two-version diff view and an optional physical layout view (2-D heat map).

## Features

- **Hierarchy tree-table** — expand/collapse any level; only hierarchies are shown
  (≈1/100 of the instance count), not individual leaf cells.
- **10 standard-cell metrics + macro columns** — computed per hierarchy via
  flattened (all-descendants) aggregation.
- **Data bars** — background progress bars in metric cells: count/area scale to the
  top-level total; ULVT%/MB%/D1D2% are color-coded red→green (bad→good) over a
  configurable min–max range.
- **Sorting** — click a metric header; sorts siblings within each level, shows the
  active sort in the status bar, and re-applies it automatically as you expand.
- **Search** — exact / wildcard / regex, case-insensitive; results in a popup
  window that jumps the tree to the selected hierarchy. In compare mode the popup
  is split into V1/V2 panels and clicking a row jumps to that version's tab.
- **Context menu** — right-click a hierarchy name to copy its full or base name.
- **Min-instance threshold** — hide small hierarchies from the tree (UI-only).
- **Two-version comparison** — V1 / V2 / Diff tabs with per-metric Δabs and Δrel.
- **Physical layout mode** — `--physical_mode` renders the placed design as a
  2-D heat map (cell density / leakage power / dynamic power) beside the
  hierarchy tree. Interactive pan/zoom/fit, adjustable grid size and color range,
  thermal legend, and outlined block boundaries. Placement follows DEF semantics
  (lower-left `location_x/y` + `orient`); nested sub-blocks are composed through
  their placement frame.
- **Pickle cache** — fast re-loads via a cache keyed on input file metadata + schema version.

## Requirements & install

- Python 3.9+
- pandas, numpy, PyQt5

```bash
pip install -r requirements.txt
```

## Usage

Input files are passed on the command line (no file dialogs):

```bash
# basic view (one cell library + one block)
python main.py --cell_info sample_data/cell_info.json --block_info sample_data/instance_info.json

# multiple blocks: a sub-block referenced by name is nested automatically
python main.py --cell_info sample_data/cell_info.json \
               --block_info sample_data/instance_info.json sample_data/block_B.instance_info.json

# show all hierarchies (no threshold) + macro columns + verbose load/build log
python main.py --cell_info c.json --block_info a.json b.json --min-instances 0 --include-macros --verbose

# two-version comparison (reuses the same cell_info.json)
python main.py --cell_info cell.json --block_info v1_a.json \
               --compare_block_info v2_a.json

# compare using the bundled demo data (v1 vs v2)
python main.py --cell_info sample_data/cell_info.json \
    --block_info sample_data/instance_info.json sample_data/block_B.instance_info.json \
    --compare_block_info sample_data/instance_info_v2.json sample_data/block_B.instance_info_v2.json

# physical layout mode: 2-D heat map of the placed design (mutually exclusive
# with --compare_block_info; uses the bundled ~100k-instance CPU-cluster sample:
# CPU_CLUSTER with 4 rotated cores, each with IFU / IEX / LSU sub-blocks)
python main.py --cell_info sample_data/physical/cell_info.json \
    --block_info sample_data/physical/instance_info.json \
        sample_data/physical/CORE.json sample_data/physical/IFU.json \
        sample_data/physical/IEX.json sample_data/physical/LSU.json \
    --physical_mode

# ignore the pickle cache and rebuild
python main.py --cell_info c.json --block_info a.json --force
```

`python -m vlsi_viewer …` is equivalent. Run `python main.py --help` for all
options (`--block_info`, `--compare_block_info`, `--physical_mode`,
`--min-instances`, `--grid_size`, `--include-macros`, `--cache-dir`, `--force`,
`--verbose`, `--version`). `--physical_mode` and `--compare_block_info` are
mutually exclusive. In physical mode, hover the layout view to read the cursor
coordinates and the heat-map grid value in the bottom-right status bar.

## Input format

### `instance_info.json` (block file)

```json
{
  "top_name": "TOP",
  "instances": {
    "MACROA/UNIT1/inv_x": { "cell_name": "INV_X1" }
  }
}
```

`top_name` is the block's design name; each `instances` key is a leaf path
**relative to `top_name`**. Each leaf attribute dict:

| attribute | type | default |
|---|---|---|
| `cell_name` | str | *(join key; missing ⇒ excluded)* |
| `dynamic_power` | float | `0.0` |
| `leakage_power` | float | `0.0` |
| `orient` | str | `""` |
| `location_x` | float | `0.0` |
| `location_y` | float | `0.0` |
| `is_physical_only` | bool | `false` |

`location_x`/`location_y` are the **lower-left corner** of the instance's
bounding box, and `orient` uses LEF/DEF naming (`N`/`S`/`W`/`E`/`FN`/`FS`/`FW`/
`FE`). These drive physical layout mode; sub-block instances are transformed
into global coordinates through their placement frame.

#### `boundary` (block outline)

A block may carry an optional `boundary` — a list of (x, y) vertices describing
its outline. The outline must be a **rectilinear** (axis-aligned) non-degenerate
polygon; a two-point boundary is expanded into an axis-aligned rectangle.
Physical mode requires a `boundary` on the top-level block and draws sub-block
boundaries in global coordinates:

```json
{
  "top_name": "TOP",
  "instances": {},
  "boundary": [(0, 0), (2000, 0), (2000, 800), (1200, 800), (1200, 1000), (0, 1000)]
}
```

### Multiple blocks & automatic nesting

Pass several `--block_info` files to compose a hierarchy. A leaf whose `cell_name`
equals another block's `top_name` is a **block instance**: that block's leaves are
nested at the leaf's absolute path. The top-level block(s) are auto-detected (a
block not referenced by any other). A block instance whose file is *not* provided
stays a leaf, so `cell_info.json` treats it as a macro or missing cell as usual.

### `cell_info.json`

Keyed by `cell_name`. Values are dicts with these attributes:

| attribute | type | default |
|---|---|---|
| `area` | float | `0.0` |
| `size_x` / `size_y` | float | `0.0` |
| `is_combinational_cell` | bool | `false` |
| `is_pulse_latch` | bool | `false` |
| `is_register_cell` | bool | `false` |
| `register_bit_count` | int | `0` |
| `drive_size` | int | `0` |
| `is_SVT` / `is_LVT` / `is_ULVT` | bool | `false` |
| `is_sram` | bool | `false` |
| `is_macro` | bool | `false` |
| `is_buffer` | bool | `false` |
| `is_inverter` | bool | `false` |
| `is_clock_cell` | bool | `false` |
| `is_integrated_clock_gating_cell` | bool | `false` |

Attributes may be **partially provided** — missing values are filled with the
defaults above.

An instance whose `cell_name` is absent or not found in `cell_info.json` is a
**missing cell**: it is excluded from all metrics and reported in the status bar
(and the warning log).

## Metrics

Computed over the "counted" set: standard cells (`is_macro == false` and
`is_physical_only == false`) with a known `cell_name`. Aggregation is
**hierarchy-flatten** (all descendant leaves).

| Column | Definition |
|---|---|
| Area | Σ `area` |
| Count | number of instances |
| ULVT% | Σ(`area` where `is_ULVT`) / Area |
| MB% | Σ(`register_bit_count` where `is_register_cell` and `> 1`) / Σ(`register_bit_count` where `is_register_cell`) |
| D1D2% | count(`drive_size ≤ 2`) / Count |
| Bits | Σ(`register_bit_count` where `is_register_cell`) |
| CKB Cnt | count((`is_buffer` or `is_inverter`) and `is_clock_cell`) |
| ICG Cnt | count(`is_integrated_clock_gating_cell`) |
| PUL Cnt | count(`is_pulse_latch`) |
| B/I Cnt | count(`is_buffer` or `is_inverter`) |
| B/I Area | Σ(`area` where buffer/inverter) |

Percentage metrics (ULVT%/MB%/D1D2%) use a red→green quality gradient over a
configurable `[min, max]` range (right-click a gradient **column header** to edit);
defaults are ULVT% 0.00–0.35, MB% 0.50–0.90, D1D2% 0.55–0.90. In compare mode the
Diff tab's `ΔX%` columns are also gradient-colored over `[−0.5, 0.5]` (MB/D1D2
higher-better, the rest lower-better); editing a range in any tab re-renders V1, V2,
and Diff together.

Macro columns (shown with `--include-macros`): **Macro Cnt** = count(`is_macro`),
**Macro Area** = Σ(`area` where `is_macro`).

## Physical layout mode

`--physical_mode` replaces the compare view with an interactive **layout view**
to the right of the hierarchy tree. The design is cut into an equal-size square
grid (default cell **3.0 × 3.0** in physical units, adjustable in the UI), and
each grid square is colored by one of three heat maps:

| Layer | Per-grid value | Default range |
|---|---|---|
| Cell density | Σ(instance area overlapping the grid) / grid_area | 0.0 – 1.0 |
| Leakage power | Σ(instance_area_ratio_in_grid × leakage_power) | 0.0 – max |
| Dynamic power | Σ(instance_area_ratio_in_grid × dynamic_power) | 0.0 – max |

Both standard cells and macros contribute (`is_physical_only` and missing-cell
instances are skipped). The heat-color **min/max range** and the **grid size**
are adjustable from the layout controls; values above the max render white, and
a thermal legend shows the current range. Pan/zoom with the mouse wheel and
press **`F`** to fit the design to the view.

## Architecture

| Module | Responsibility |
|---|---|
| `vlsi_viewer/schema.py` | attribute specs + metric registry (single source of truth) |
| `vlsi_viewer/loader.py` | JSON → typed DataFrames (defaults + coercion + boundary validation) |
| `vlsi_viewer/metrics.py` | hierarchy build, filtering, flatten aggregation, pickle cache, diff |
| `vlsi_viewer/model.py` | column/view abstractions bridging data to the widgets |
| `vlsi_viewer/theme.py` | visual theme (palette, stylesheet, data-bar colors) |
| `vlsi_viewer/ui_tree.py` | tree-table widget (lazy expand, per-level sort, threshold) |
| `vlsi_viewer/ui_search.py` | search results popup |
| `vlsi_viewer/ui_compare.py` | V1 / V2 / Diff tabs |
| `vlsi_viewer/ui_main.py` | main window (toolbar + wiring) |
| `vlsi_viewer/cli.py` | command-line entry point |
| `vlsi_viewer/physical.py` | physical mode: heat-map grid construction |
| `vlsi_viewer/heatmap.py` | thermal colormap, grid array → QImage |
| `vlsi_viewer/ui_layout.py` | layout view widget (heat map, controls, legend) |
| `vlsi_viewer/genericView.py` | interactive QGraphicsView (pan / zoom / fit) |
| `vlsi_viewer/coordinateProcess.py` | DEF-style orient & coordinate transforms |
| `vlsi_viewer/Point.py`, `utils.py` | small shared helpers |

Adding a new metric or input attribute is a one-place change in `schema.py`.

## Testing

```bash
python -m pytest
```

The suite covers metric formulas (against hand-computed values), filtering
(missing / macro / physical-only), hierarchy construction, pickle round-trip,
diff, physical-mode grid construction, boundary validation, and headless GUI
construction.
