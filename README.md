# VLSI Design Hierarchy Visualization Tool

A PyQt5 desktop application for physical-design engineers to browse a gate-level
netlist's **hierarchy tree** and inspect per-level statistics. It reads a cell
library plus one or more block files, reconstructs (and auto-composes) the design
hierarchy, and renders a sortable, searchable tree-table of metrics — plus a
two-version diff view and an optional physical layout view (2-D heat map).

## Features

- **Four input flows** — `json` (pre-processed), `def` (DEF + LEF, with placement),
  `verilog` (gate-level netlist + LEF) and `metal` (DEF + tech LEF, routing density). The
  EDA flows convert to the JSON form first, so one pipeline serves the first three.
  `python quickstart.py` opens any of them on the bundled samples.
- **Metal density mode** — per-routing-layer utilisation from a routed DEF, with layer
  checkboxes, a signal/power split, and a hover readout showing the arithmetic behind the
  cell under the cursor. See [Metal density mode](#metal-density-mode).
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
python quickstart.py json       # sample_data/*.json             (two-version compare)
python quickstart.py physical   # sample_data/physical/*.json    (2-D density heat map)
python quickstart.py def        # sample_data/eda/core.def     + cells.lef
python quickstart.py verilog    # sample_data/eda/core.v       + cells.lef
python quickstart.py metal      # sample_data/metal/*.def + cells.lef + tech.lef
```

Extra flags pass through to the real CLI (`python quickstart.py def --grid_size 2.0`).
Nothing is written to disk along the way.

Metal mode takes the longest command line of the four - two DEFs, a macro LEF and a tech LEF -
so its sample has a quick start of its own:

```bash
python sample_data/metal/quickstart.py           # open the GUI on the sample
python sample_data/metal/quickstart.py --check   # print the map's numbers, no GUI
```

`--check` is the one to reach for when a DEF of your own is in question: run it on the sample
first to see what a healthy map looks like, then point it at yours. It prints the per-layer
pitch, width, spacing and `(W+S)/P`, the signal/power/all maxima, the horizontal and vertical
maxima, and the busiest cell's full arithmetic. The sample must be generated once before
either path works - `python sample_data/metal/generate_metal.py`.

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
| `metal` | `--def`, `--lef`, `--tech-lef`, `--top` | `--grid-size`, `--macro-block-layers`, `--min-segment-length`, `--jobs`, `--profile` |

Options shared by the first three: `--min-instances`, `--include-macros`, `--cache-dir`,
`--force`, `--verbose`. `--grid_size` and `--contour_gap` apply to the two flows that can
render a heat map; `metal` has its own `--grid-size` (default 10 µm) because the useful
resolution is different. `metal --jobs N` spreads the wiring pass over N processes — the
per-net work has no dependency between nets, so it scales nearly linearly with cores; `1` (the
default) keeps it all in one process, and `--profile` prints where a build's time went. `N` is a
cap rather than an instruction — a worker costs a spawned interpreter and a full scan of the DEF,
so an input only a few megabytes across is parsed in one process whatever you ask for.
Within a subcommand, physical mode and the compare flag are
mutually exclusive, and `metal` has neither — nor the JSON pipeline's options, which it
cannot act on: it converts nothing, builds no tree and caches nothing. In physical mode, hover the layout view to read
the cursor coordinates and the heat-map grid value in the bottom-right status bar; in metal
mode the same hover fills the panel's cell readout.

The `verilog` and `def` flows convert their inputs into exactly the structures the `json`
subcommand reads, and load them in memory without writing anything - see
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
convert their inputs to exactly the structures documented under [Input
format](#input-format) — LEF becomes the cell library, the netlist or DEF becomes block
data — and load them **in memory**: a run writes no file at all.

### Names of the JSON written by `--out`

`--out DIR` dumps the converted JSON into `DIR`, as a copy to inspect or to feed back to
the `json` subcommand. The names follow the design, not the input file:

| written | name | example |
|---|---|---|
| the cell library | `cell_info.json` | — |
| a block | `<top>.instance_info.json` | `core.instance_info.json` |
| the second design | `<top>.instance_info.compare.json` | `core.instance_info.compare.json` |

The top cell is the DEF's `DESIGN` statement, or `--top` when given — `--top` also renames
the design itself. A netlist names no design, so there `--top` is required and is the only
source of the name. The cell library carries no such name because several LEF files are
**one** library: it is always plain `cell_info.json`.

Naming a block after its top is what lets a version diff keep both sides. `v1/core.def`
against `v2/core.def` are the same file name describing the same design, so both infer the
top `core`; only the `.compare` suffix keeps them apart. That case is the reason the two
sides cannot simply be named after their files. Each `--def` is a separate block, so passing
two same-named DEFs as ordinary `--def` blocks (rather than as a compare pair) gives both the
same name, and the CLI warns instead of letting one silently replace the other.

| input | gives | notes |
|---|---|---|
| LEF (`--lef`) | the cell library | macro `SIZE` (microns) → `size_x`/`size_y`/`area`; `CLASS` other than `CORE` → `is_macro`. Several files are one library |
| DEF (`--def`) | one block each | `DESIGN` → `top_name`, `DIEAREA` → `boundary`, `COMPONENTS` → instances. Coordinates are DEF database units divided by `UNITS DISTANCE MICRONS` |
| Verilog (`--verilog`) | **one** block | flattened to instance-name paths; **no placement**, hence no physical mode. Several files are one netlist |

**How the multi-file flags differ, deliberately:** a netlist is normally split across
files (one per module), so several `--verilog` files are merged into a single design. Each
DEF, by contrast, is a complete design, so several `--def` files stay separate blocks —
the "incremental JSON" behaviour. `.gz` inputs are read transparently for all three.

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
- **`--cache-dir` / `--force` do nothing here.** The pickle cache keys on file mtimes, and
  these flows read no files; they apply to the `json` subcommand, including a JSON dump
  you made with `--out`.
- **Known parser limits** (vendored as-is): DEF `ROWS`/`SITE` are not parsed, a component
  statement wrapped over several lines is skipped, and a DEF that omits `UNITS` falls back
  to 2000 database units per micron. An unrecognised `TRACKS` clause is reported and
  skipped rather than aborting the parse.

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

## Metal density mode

    python main.py metal --def top.def sub.def --lef cells.lef --tech-lef tech.lef
    python main.py metal --def core.def --lef cells.lef --tech-lef tech.lef --grid-size 5

Placement tells you where the cells are; this tells you where the **metal** is. It reads a
routed DEF and the tech LEF that defines its routing layers, and renders a per-layer heat map
of routing utilisation.

### What the number means

Each wire segment is expanded by half its own spacing rule on every side, and the expanded
areas are summed per grid cell. The expansion is what calibrates the scale: a minimum-width
wire expanded by half the spacing covers exactly `W + S` across, which is the layer's track
pitch, so the sum is measured in *track-pitch area consumed* and **1.0 means every track is
used**. A wire routed at `2W2S` expands to two track pitches, automatically.

Capacity carries the same normalisation, `(W + S) / P`, because the two are not always equal
— Nangate45's metal2 is 0.14 against a 0.19 pitch, and sky130's met1 is 0.28 against 0.34.
Without it those layers would read 0.74 and 0.82 at *full* utilisation.

Ticking several layers groups them, and the group is read as `sum(consumed) / sum(capacity)`:
a capacity-weighted mean, not a sum, which would drive every cell white. So ticking the
horizontal layers gives the horizontal-routing map and the vertical layers the vertical one,
and a cell is a genuine bottleneck when **both** read high — a cell with horizontal layers
full and vertical layers empty is still routable.

The window is three panes — the cell readout, the map, and the layer selection — with the
map's value range in the toolbar. The readout sits opposite the selection because in one
column the two tables fought over the same height, and the loser went behind a scrollbar.

### What it counts, and what it does not

| | |
|---|---|
| **vias** | omitted. A via is a routing point with no extent, so it has no wire area; on a real routed DEF they are more than half of all parsed segments |
| **non-preferred jogs** | dropped below one track pitch (a horizontal blip on a vertical layer used to shift track). `--min-segment-length 0` keeps every one; short segments running *along* their layer are never dropped |
| **power** | counted separately from signal. A power stripe is fixed and deliberate, so merging the two makes a region under a stripe read as a hotspot; the panel's net-class selector switches between them |
| **macros** | a hard macro removes capacity where its LEF `OBS` says it obstructs, on the layers it names — a macro that blocks `metal2` and `metal4` but not `metal3` is read that way. Obstructions covering under 10 % of the macro are pin-access bites, not keep-outs, and are ignored. Only cells whose `CLASS` is not `CORE` count. A macro whose LEF declares no `OBS` cannot be judged from data, so it falls back to the bottom `--macro-block-layers` layers (default 4) over its whole footprint; `0` cancels that guess, not the geometry |
| **45° segments** | exact, as their Minkowski sum with a square; a bounding box would over-count a 10 µm diagonal about 25× |

The **cell detail** pane shows the hovered cell's consumed area, capacity and utilisation for
every selected layer, plus the group's `sum(D)/sum(C)`, so the colour on screen can be checked
against the arithmetic that produced it. The busiest layer is bolded - the bottleneck is the
answer to "why is this cell hot" - and the horizontal and vertical maxima are reported apart,
since a cell whose horizontal layers are full is still routable upward.

The **layer list** carries each layer's `width/spacing/pitch` beside its mean utilisation,
because capacity is `routable area × (W + S) / P` and those are the numbers it was computed
from. Hovering a row gives the rules in full, the factor `f`, and — for a layer with no width
rule — why it is disabled rather than merely absent.

The ramp is fixed at `[0, 1]`, where 1.0 means every track on the layer is consumed. A healthy
design peaks well below that and so renders as a nearly uniform dark rectangle, so **Auto**
fits the range to the map's own top half-percent. The peak stays on show beside it, which
keeps the absolute scale unambiguous while the colours are stretched.

### Scale

Comfortable to about **10⁶ wire segments** (seconds); usable to about 10⁷ (minutes). Beyond
that the DEF *parser*, not the rasteriser, is the wall — parsing is 97 % of the runtime — and
a full-chip flat DEF is out of reach for this viewer rather than merely slow. `--stress N` on
the sample generator times a synthetic design of N nets; see
[`dev_plan/metal_density_asbuilt.md`](dev_plan/metal_density_asbuilt.md) for the measured
numbers. Unlike the physical mode, the grids are built before the window appears, so a large
run shows progress in the terminal and no window until it is ready.

`sample_data/metal/` is a browsable example: a 1P12M stack, a 13k-cell hierarchical design and
its power grid, generated by `python sample_data/metal/generate_metal.py`.

`sample_data/real/` is the opposite: five unmodified files from upstream projects, kept so the
parser behaviour this mode was measured against stays checkable. Everything else under
`sample_data/` is synthesized, which is fine for the shape of a map and useless for parser
correctness — the worst bug in this codebase (nine of ten routing layers silently arriving with
`spacing == 0.0`) was invisible against the generated sample and appeared the moment a real tech
LEF was read. Nangate45's tech and cell LEFs, a real routed `gcd` DEF, and the ASAP7 and sky130
tech LEFs; provenance, revisions and licences in
[`sample_data/real/PROVENANCE.md`](sample_data/real/PROVENANCE.md), and the reasoning in
[`dev_plan/real_sample_sources.md`](dev_plan/real_sample_sources.md). The two Nangate45 files
are research-licensed, so remove them before publishing this repository.

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
