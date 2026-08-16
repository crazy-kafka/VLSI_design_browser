# VLSI Design Hierarchy Visualization Tool

A PyQt5 desktop application for physical-design engineers to browse a gate-level
netlist's **hierarchy tree** and inspect per-level statistics. It reads two JSON
files, reconstructs the hierarchy from full-path leaf instance names, and renders
a sortable, searchable tree-table of metrics — plus a two-version diff view.

## Features

- **Hierarchy tree-table** — expand/collapse any level; only hierarchies are shown
  (≈1/100 of the instance count), not individual leaf cells.
- **7 standard-cell metrics + macro columns** — computed per hierarchy via
  flattened (all-descendants) aggregation.
- **Sorting** — click a column header; sorts siblings within each level.
- **Search** — exact / wildcard / regex, case-insensitive; results in a popup
  window that jumps the tree to the selected hierarchy.
- **Min-instance threshold** — hide small hierarchies from the tree (UI-only).
- **Two-version comparison** — V1 / V2 / Diff tabs with per-metric Δabs and Δrel.
- **Pickle cache** — fast re-loads via a cache keyed on input file metadata.

## Requirements & install

- Python 3.9+
- pandas, numpy, PyQt5

```bash
pip install -r requirements.txt
```

## Usage

Input files are passed on the command line (no file dialogs):

```bash
# basic view
python main.py sample_data/instance_info.json sample_data/cell_info.json

# show all hierarchies (no threshold) + macro columns
python main.py inst.json cell.json --min-instances 0 --include-macros

# two-version comparison
python main.py v1_inst.json v1_cell.json --compare v2_inst.json v2_cell.json

# ignore the pickle cache and rebuild
python main.py inst.json cell.json --force
```

`python -m vlsi_viewer …` is equivalent. Run `python main.py --help` for all
options (`--compare`, `--min-instances`, `--include-macros`, `--cache-dir`,
`--force`, `--version`).

## Input format

### `instance_info.json`

Keyed by the full hierarchical leaf path (``/``-separated), e.g.
`"TOP/MACROA/UNIT1/inv_x"`. Values are dicts with these attributes:

| attribute | type | default |
|---|---|---|
| `cell_name` | str | *(join key; missing ⇒ excluded)* |
| `dynamic_power` | float | `0.0` |
| `leakage_power` | float | `0.0` |
| `orient` | str | `""` |
| `location_x` | float | `0.0` |
| `location_y` | float | `0.0` |
| `is_physical_only` | bool | `false` |

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
defaults above. Attributes flagged as reserved are parsed and persisted for a
future 2-D heat-map feature but are not surfaced in the current UI.

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
| B/I Cnt | count(`is_buffer` or `is_inverter`) |
| B/I Area | Σ(`area` where buffer/inverter) |

Macro columns (shown with `--include-macros`): **Macro Cnt** = count(`is_macro`),
**Macro Area** = Σ(`area` where `is_macro`).

## Architecture

| Module | Responsibility |
|---|---|
| `vlsi_viewer/schema.py` | attribute specs + metric registry (single source of truth) |
| `vlsi_viewer/loader.py` | JSON → typed DataFrames (defaults + coercion) |
| `vlsi_viewer/metrics.py` | hierarchy build, filtering, flatten aggregation, pickle cache, diff |
| `vlsi_viewer/model.py` | column/view abstractions bridging data to the widgets |
| `vlsi_viewer/ui_tree.py` | tree-table widget (lazy expand, per-level sort, threshold) |
| `vlsi_viewer/ui_search.py` | search results popup |
| `vlsi_viewer/ui_compare.py` | V1 / V2 / Diff tabs |
| `vlsi_viewer/ui_main.py` | main window (toolbar + wiring) |
| `vlsi_viewer/cli.py` | command-line entry point |

Adding a new metric or input attribute is a one-place change in `schema.py`.

## Testing

```bash
python -m pytest
```

The suite covers metric formulas (against hand-computed values), filtering
(missing / macro / physical-only), hierarchy construction, pickle round-trip,
diff, and headless GUI construction.
