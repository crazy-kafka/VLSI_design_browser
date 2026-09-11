# VLSI Design Hierarchy Visualization Tool

A PyQt5 desktop application for physical-design engineers to browse a gate-level
netlist's **hierarchy tree** and inspect per-level statistics. It reads a cell
library plus one or more block files, reconstructs (and auto-composes) the design
hierarchy, and renders a sortable, searchable tree-table of metrics — plus a
two-version diff view and an optional physical layout view (2-D heat map).

## Features

- **Three input flows** — `json` (pre-processed), `def` (DEF + LEF, with placement) and
  `verilog` (gate-level netlist + LEF). The EDA flows convert to the JSON form first, so
  one pipeline serves all three. `python quickstart.py` opens any of them on the bundled
  samples.
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
  2-D heat map (cell density / leakage power / dynamic power / ULVT density)
  beside the hierarchy tree. Interactive pan/zoom/fit, a color range adjustable
  in the UI, a fixed vertical thermal legend, and outlined block boundaries.
  Hovering reports the cursor coordinates + grid value; clicking a hierarchy node
  draws a dashed contour around its instances (multiple loops for
  scatter-distributed blocks), and a "Density%" column reports each hierarchy's
  spacing density. Placement follows DEF semantics (lower-left `location_x/y` +
  `orient`); nested sub-blocks are composed through their placement frame.
- **Pickle cache** — fast re-loads via a cache keyed on input file metadata + schema version.

## Requirements & install

- Python 3.9+
- pandas, numpy, PyQt5
- shapely (contour geometry)

```bash
pip install -r requirements.txt
```

## Quick start

Preset shortcuts for the bundled samples, so nothing long has to be typed:

```bash
python quickstart.py            # list the shortcuts
python quickstart.py json       # sample_data/*.json           (two-version compare)
python quickstart.py physical   # sample_data/physical/*.json  (2-D density heat map)
python quickstart.py def        # sample_data/eda/core.def   + cells.lef
python quickstart.py verilog    # sample_data/eda/core.v     + cells.lef
```

Extra flags pass through to the real CLI (`python quickstart.py def --grid_size 2.0`),
and the `def`/`verilog` shortcuts write their generated JSON to a temporary directory so
a demo never litters the checkout.

## Usage

Inputs are passed on the command line (no file dialogs). There are three subcommands -
`json`, `verilog` and `def` - one per input format:

```bash
# --- json: pre-processed cell_info.json + instance_info.json (the original interface)

# basic view (one cell library + one block)
python main.py json --cell_info sample_data/cell_info.json \
                    --block_info sample_data/instance_info.json

# multiple blocks: a sub-block referenced by name is nested automatically
python main.py json --cell_info sample_data/cell_info.json \
    --block_info sample_data/instance_info.json sample_data/block_B.instance_info.json

# show all hierarchies (no threshold) + macro columns + verbose log
python main.py json --cell_info c.json --block_info a.json b.json \
    --min-instances 0 --include-macros --verbose

# two-version comparison (reuses the same cell_info.json)
python main.py json --cell_info cell.json --block_info v1_a.json \
    --compare_block_info v2_a.json

# physical layout mode: 2-D heat map (mutually exclusive with --compare_block_info);
# uses the bundled ~100k-instance CPU-cluster sample
python main.py json --cell_info sample_data/physical/cell_info.json \
    --block_info sample_data/physical/instance_info.json \
        sample_data/physical/CORE.json sample_data/physical/IFU.json \
        sample_data/physical/IEX.json sample_data/physical/LSU.json \
    --physical_mode

# ignore the pickle cache and rebuild
python main.py json --cell_info c.json --block_info a.json --force

# --- def: DEF + macro LEF (placement comes from the DEF, so physical mode works)
python main.py def --def core.def --lef cells.lef --physical_mode
python main.py def --def v1.def --compare_def v2.def --lef cells.lef   # two-version diff

# --- verilog: gate-level netlist + macro LEF (no placement -> no physical mode)
python main.py verilog --verilog core.v --lef cells.lef --top core
python main.py verilog --verilog v1.v --compare_verilog v2.v --lef cells.lef --top core
```

`python -m vlsi_viewer …` is equivalent, and `--version` works at the top level. Run
`python main.py <subcommand> --help` for that subcommand's options:

| subcommand | inputs | modes |
|---|---|---|
| `json` | `--cell_info`, `--block_info`, `--compare_block_info` | compare, `--physical_mode` |
| `verilog` | `--verilog`, `--lef`, `--top`, `--compare_verilog`, `--out` | compare only |
| `def` | `--def`, `--lef`, `--top`, `--compare_def`, `--out` | compare, `--physical_mode` |

Options shared by all three: `--min-instances`, `--include-macros`, `--cache-dir`,
`--force`, `--verbose`. `--grid_size` and `--contour_gap` apply to the two flows that can
render a heat map. Within a subcommand, physical mode and the compare flag are mutually
exclusive. In physical mode, hover the layout view to read the cursor coordinates and the
heat-map grid value in the bottom-right status bar.

The `verilog` and `def` flows convert their inputs into exactly the JSON the `json`
subcommand takes, writing it beside the input (or into `--out`) - see
[EDA input formats](#eda-input-formats).

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
| `is_physical_only` | bool | `false` |

Attributes may be **partially provided** — missing values are filled with the
defaults above.

An instance whose `cell_name` is absent or not found in `cell_info.json` is a
**missing cell**: it is excluded from all metrics and reported in the status bar
(and the warning log).

`is_physical_only` marks area-only cells (filler, tap, decap, antenna, boundary). An
instance is physical-only if **either** the instance or its library cell says so. Such
cells count in the **density** heat map only: they are excluded from the leakage,
dynamic and ULVT maps, and entirely absent from the hierarchy tree, the contours and
the `Density%` metric.

## EDA input formats

`--verilog` and `--def` read EDA files directly instead of hand-written JSON. Both
convert their inputs to exactly the JSON documented under [Input
format](#input-format) — LEF becomes `cell_info.json`, the netlist or DEF becomes
`instance_info.json` — and write it beside the input (or into `--out`) before loading
it, so the generated files can be inspected and fed back to the `json` subcommand.

| input | gives | notes |
|---|---|---|
| LEF (`--lef`) | `cell_info.json` | macro `SIZE` (microns) → `size_x`/`size_y`/`area`; `CLASS` other than `CORE` → `is_macro` |
| DEF (`--def`) | `instance_info.json` | `DESIGN` → `top_name`, `DIEAREA` → `boundary`, `COMPONENTS` → instances. Coordinates are DEF database units divided by `UNITS DISTANCE MICRONS` |
| Verilog (`--verilog`) | `instance_info.json` | flattened to instance-name paths; **no placement**, hence no physical mode |

Things worth knowing:

- **Power is absent.** Neither DEF nor a netlist carries leakage/dynamic power, so the
  leakage and dynamic heat maps are empty for these flows and the CLI warns about it.
- **Filler is dropped.** `FILL*` components tile every row gap, so keeping them would
  peg the density map at 100%. Tap, decap and other physical-only cells are kept and
  flagged instead — they appear in density but not in the tree.
- **Unplaced components are skipped**, rather than piled onto the die origin.
- **Cell-name heuristics are library conventions.** Which cells are buffers, or how many
  bits a flop holds, is not in the LEF. The rules live in one table at the top of
  `vlsi_viewer/parsers/convert.py`; edit them for a different library.
- **Known parser limits** (vendored as-is): DEF `ROWS`/`SITE` are not parsed, a
  component statement wrapped over several lines is silently skipped (the CLI warns when
  the parsed count disagrees with the `COMPONENTS` count), and a DEF that omits `UNITS`
  falls back to 2000 database units per micron (also warned about).

`sample_data/eda/` is a browsable example — a macro LEF, a DEF and a gate-level
netlist describing the same small CPU cluster, generated by
`python sample_data/eda/generate_eda_sample.py`.

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

`--physical_mode` (available on the `json` and `def` subcommands) replaces the compare
view with an interactive **layout view** to the right of the hierarchy tree. The design
is cut into an equal-size square grid (cell size set via `--grid_size`, default
**3.0 × 3.0** in physical units), and each grid square is colored by one of four heat
maps:

| Layer | Per-grid value | Default range |
|---|---|---|
| Cell density | Σ(instance area overlapping the grid) / grid_area | 0.0 – 1.0 |
| Leakage power | Σ(instance_area_ratio_in_grid × leakage_power) | 0.0 – max |
| Dynamic power | Σ(instance_area_ratio_in_grid × dynamic_power) | 0.0 – max |
| ULVT density | Σ(ULVT-instance area overlapping the grid) / grid_area | 0.0 – 1.0 |

Density counts **every** placed box, including physical-only cells, because the area
they occupy is real. The other three maps count only instances with actual logic: a
physical-only instance contributes to density and to nothing else, and is absent from
the tree, the contours and `Density%` (see
[`is_physical_only`](#cell_infojson)). Missing-cell instances are skipped everywhere.
The heat-color **min/max range** is adjustable from the
layout controls and is remembered per map type (each map keeps whatever range you
last left it on); a fully-packed bin (density 100%) renders the top gradient stop
(near-white), and a fixed vertical thermal legend (navy → blue → cyan → green →
yellow → red → near-white, matching the INNOVUS ramp) shows the current range with
0/25/50/75/100% value ticks. Pan/zoom with the mouse wheel, press **`F`** to fit,
and hover to read the cursor coordinates and grid value in the bottom-right status
bar.

#### Hierarchy contours & density

Clicking a hierarchy node in the tree draws a dashed outline around that node's
instances; clicking the same node again hides it, and clicking another node swaps
it. Instances scattered beyond `--contour_gap` (default `2 × grid_size`) become
**multiple loops**. A **Density%** column reports each hierarchy's spacing density
`non-macro area / (contour area − macro area)` (higher-better gradient, range
20%–65%). Contours/densities are computed lazily and cached, and boxes are
pre-merged (exact) so the geometry scales to large (10M-instance) subsystems.

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
| `vlsi_viewer/cli.py` | command-line entry point (three input subcommands) |
| `vlsi_viewer/parsers/` | vendored LEF / DEF / Verilog parsers (`DEF/`, `LEF/`, `verilog/`) |
| `vlsi_viewer/parsers/convert.py` | EDA files → the viewer's `cell_info` / `instance_info` JSON |
| `vlsi_viewer/physical.py` | physical mode: heat-map grids + per-hierarchy contour/density |
| `vlsi_viewer/contour.py` | rectilinear union geometry (shapely) + box pre-merge |
| `vlsi_viewer/heatmap.py` | thermal colormap, grid array → QImage |
| `vlsi_viewer/ui_layout.py` | layout view widget (heat map, controls, legend, contour overlay) |
| `vlsi_viewer/genericView.py` | interactive QGraphicsView (pan / zoom / fit) |
| `vlsi_viewer/coordinateProcess.py` | DEF-style orient & coordinate transforms |
| `vlsi_viewer/Point.py`, `utils.py` | small shared helpers |
| `quickstart.py` | preset GUI shortcuts for the bundled samples |

Adding a new metric or input *attribute* is a one-place change in `schema.py`. A new
input *format* additionally needs a converter in `vlsi_viewer/parsers/convert.py` and a
subparser in `cli.py`.

## Testing

```bash
python -m pytest
```

The suite covers metric formulas (against hand-computed values), filtering
(missing / macro / physical-only), hierarchy construction, pickle round-trip,
diff, physical-mode grid construction, boundary validation, contour geometry
(both backends, incl. box pre-merge exactness), headless GUI construction, and — for the
EDA flows — the LEF/DEF/Verilog converters (including the parser quirks they defend
against), the generated JSON round-tripping through the real loaders, CLI subcommand
parsing, and the quickstart shortcuts.
