# VLSI Design Hierarchy Visualization Tool — Formal Development Plan

## 1. Context & Purpose

Gate-level VLSI netlists contain multi-level nested hierarchy. Each hierarchy level has distinct statistical characteristics. This tool presents per-hierarchy statistics in a tree-table so physical-design engineers can rapidly analyze design data.

It reads two JSON inputs, reconstructs the hierarchy tree from leaf instance full-paths, computes metrics per hierarchy level (flattened aggregation), and exposes them in a PyQt5 tree-table with expand/collapse, search, sort, min-instance filtering, and two-version diff.

## 2. Input Data Model

### `instance_info.json` (block file)
- shape: `{"top_name": <str>, "instances": {<rel_path>: {attrs...}}}`
- each `instances` key is a leaf path relative to `top_name` (e.g. `MACROA/UNIT1/inv_x`)
- value (dict): `cell_name`, `dynamic_power`, `leakage_power`, `orient`, `location_x`, `location_y`, `is_physical_only`

### `cell_info.json`
- key: `cell_name`
- value (dict): `area`, `size_x`, `size_y`, `is_combinational_cell`, `is_pulse_latch`, `is_register_cell`, `register_bit_count`, `drive_size`, `is_SVT`, `is_LVT`, `is_ULVT`, `is_sram`, `is_macro`, `is_buffer`, `is_inverter`, `is_clock_cell`, `is_integrated_clock_gating_cell`

### Reserved attributes (parsed + persisted, not used in v1)
`dynamic_power`, `leakage_power`, `orient`, `location_x`, `location_y`, `size_x`, `size_y`, `is_combinational_cell`, `is_pulse_latch`, `is_sram`, `is_clock_cell`, `is_integrated_clock_gating_cell` — reserved for the future 2D heat-map feature.

### Partial attributes & defaults
Attributes within an entry may be partially provided. Missing attributes are filled at load time with conservative defaults:
- `bool` → `False`; `int`/`float` → `0`; `str` → `""`.
- `cell_name` (instance) is the join key — if absent, the instance is a **missing cell** (excluded + warning, §4), not defaulted.

Consequences of `0`/`False` defaults: an entry omitting `is_macro` is treated as std-cell; an omitted `drive_size` counts toward D1D2 (0 ≤ 2); an omitted `area` contributes 0 to area-based metrics.

## 3. Hierarchy Construction

- Each block file contributes leaves relative to its `top_name`.
- Multi-block composition: a leaf whose `cell_name` equals another block's `top_name`
  is a block instance — that block's leaves nest at the leaf's absolute path
  (recursive, cycle-guarded). Top-level block(s) are auto-detected (not referenced).
- Split each leaf name on `/`; every prefix is a hierarchy node; the last segment is the leaf.
- Build a tree of hierarchy nodes; leaves are NOT shown as nodes (only hierarchies, ≈1/100 of instance count).
- Each hierarchy aggregates metrics of all descendant leaves (flatten-only mode).

## 4. Metric Scope & Filtering

A leaf is "counted" only if ALL hold:
1. Its `cell_name` exists in `cell_info.json` — else excluded entirely + warning log (deduped per missing `cell_name`).
2. `is_macro == false` — macros excluded from the 10 std metrics; surfaced separately via toggle.
3. `is_physical_only == false` — always excluded, no toggle.

Aggregation is hierarchy-flatten: a hierarchy's metric aggregates every counted descendant leaf.

## 5. Metric Definitions

Let S = set of counted leaves under a hierarchy (post-filter).

1. **Area** = Σ `area(leaf)` over S.
2. **Count** = |S|.
3. **ULVT Ratio** = Σ{`area` : `is_ULVT`} / Area. VT flags mutually exclusive (≤1 of SVT/LVT/ULVT); unclassified cells don't enter numerator.
4. **MB Ratio** = Σ{`register_bit_count` : `is_register_cell` && `register_bit_count > 1`} / Σ{`register_bit_count` : `is_register_cell`}. (`—` if denominator 0.)
5. **D1D2 Ratio** = |{leaf : `drive_size ≤ 2`}| / |S|. (count-based)
6. **Register Bit Count (Bits)** = Σ{`register_bit_count` : `is_register_cell`}.
7. **Clock Buffer/Inverter Count (CKB Cnt)** = |{leaf : (`is_buffer || is_inverter`) && `is_clock_cell`}|.
8. **ICG Count (ICG Cnt)** = |{leaf : `is_integrated_clock_gating_cell`}|.
9. **Pulse Latch Count (PUL Cnt)** = |{leaf : `is_pulse_latch`}|.
10. **Buffer&Inverter Count** = |{leaf : `is_buffer || is_inverter`}|.
11. **Buffer&Inverter Area** = Σ{`area` : `is_buffer || is_inverter`}.

Macro columns (visible only when "Include macros" on):
- **Macro Count** = |{leaf : `is_macro`}|.
- **Macro Area** = Σ{`area` : `is_macro`}.

Division-by-zero → display `—`.

## 6. GUI Design

### Base view (single version)
```
+==================================================================================+
|  VLSI Hierarchy Analyzer                                                        |
|  [Load Data] [Load Compare]  Search: [______] (•E ○W ○R) [Find]  Min:[100 ] [ ]Macros |
+----------------------------------------------------------------------------------+
|  Hierarchy Tree                                        (3,142 hierarchies)       |
|  Hierarchy          | Area       | Count | ULVT% | MB%  | D1D2% | B/I Cnt | B/I Area |
|  ▼ TOP              | 123456.78  | 100000|  8.20 | 12.40| 45.10 |  12000  | 5000.00  |
|    ▼ MACROA         |  60000.00  |  40000|  5.10 | 10.20| 40.00 |   4000  | 1500.00  |
|      ▼ UNIT1        |  20000.00  |  12000|  6.00 | 11.00| 42.00 |   1500  |  600.00  |
|      ▶ UNIT2        |  40000.00  |  28000|  4.80 |  9.90| 44.00 |   2500  |  900.00  |
|    ▶ MACROB         |  63456.78  |  60000|  7.10 | 13.50| 38.00 |   8000  | 3500.00  |
+----------------------------------------------------------------------------------+
|  Status: 20,000,000 instances · load 45.2s · pickle hit · 123 warnings           |
+==================================================================================+
```
- `▼`/`▶` = expanded/collapsed; indentation = depth; tree shows last path segment.
- Search input + match mode live in the **toolbar**; results open in a separate popup window.
- "Include macros" on → append `| Macro Area | Macro Cnt |` columns.
- Metric cells render background **data bars**; count/area scale to the top-level
  total, and ULVT%/MB%/D1D2% are color-coded red→green (ULVT lower-better;
  MB/D1D2 higher-better) over a configurable `[min, max]` range (right-click to
  edit; defaults ULVT% 0.00–0.35, MB% 0.50–0.90, D1D2% 0.55–0.90).

### Search results popup window
```
+================================================+
|  Search Results  ("*clk*" → 42 matches)        |
+------------------------------------------------+
|  Hierarchy            | Area      | Count | ... |
|  TOP/MACROA/UNIT1/clk |  1200.00  |   800 |     |
|  ...                                           |
+------------------------------------------------+
```
- Full-path matches with their metric columns; clicking a row expands the main tree to that hierarchy.

### Compare mode
Load a second data pair → tabs at top of tree area:
```
|  [ V1 ]  [ V2 ]  [ Diff ]                          (compare active)             |
```
- **V1 / V2**: base columns per version.
- **Diff**: per metric `{Δabs, Δrel}` — 14 sortable columns (`ΔArea ΔArea% ΔCnt ΔCnt% ΔULVT(pt) ΔULVT% ΔMB(pt) ΔMB% ΔD1D2(pt) ΔD1D2% ΔBI# ΔBI#% ΔBI-A ΔBI-A%`).

## 7. Interactions

- **Startup**: TOP + first-level children expanded.
- **Search**: exact / wildcard / regex against the full path, case-insensitive; launched from the toolbar, results shown in a separate popup window; click → tree expands to node.
- **Sort**: click metric column header; reorders siblings within each parent only; collapsed subtrees' hidden children not re-sorted; cross-level sort unsupported.
- **Threshold** (`hier_min_inst_count_threshold`): runtime field, default 100; hides hierarchies with Count < N from the tree only; search results unaffected; no data-accuracy impact.
- **Include macros**: toggle adds macro columns.
- **Comparison**: second (instance+cell) pair; diff tabs.

### Diff semantics
- count/area: Δabs = V2−V1; Δrel = (V2−V1)/V1 (V1=0 → `—`).
- ratio metrics (ULVT/MB/D1D2): Δabs = V2−V1 in percentage points; Δrel = (V2−V1)/V1.

## 8. Backend Architecture

Pipeline:
1. Parse JSONs → two typed pandas DataFrames (instances, cells), applying the attribute schema (defaults + type coercion).
2. Vectorized join `instance.cell_name → cell_info`.
3. Derive hierarchy path columns by splitting leaf names.
4. Filter → counted set (exclude missing-cell / macro / physical-only).
5. Group-by hierarchy path; aggregate 7 metrics + macro metrics (vectorized).
6. Persist pickle cache `.vlsi_cache/<content-hash>.pkl` beside inputs; cache hit → fast load; miss → re-preprocess. "Force Reload" menu item.

Performance: all aggregation via pandas/numpy vectorized ops (no per-leaf Python loop); hierarchy count is small so the frontend tree model is cheap.

## 9. Extensibility (Schema-Driven Data & Metric Registry)

Adding a new attribute or metric later must be a one-place change.

### Attribute schema (`schema.py`)
- Each input attribute is declared once as `(name, type, default)` for `instance_info` and `cell_info`.
- `loader.py` reads JSON and applies the schema (fill defaults, coerce types), emitting typed DataFrames. Reserved attributes are declared here too, so they're parsed + persisted for the future heat-map with no loader changes.
- New attribute = add one spec entry; no loader/UI changes.

### Metric registry (`metrics.py`)
- Each metric is a `MetricSpec`: id, display label, formatter (count / area / percent), and a vectorized compute function `f(filtered_df) -> scalar`.
- The 7 std metrics + 2 macro metrics are instances of this spec. Tree-table columns, sorting, and diff columns are all generated from the registry, so a new metric automatically gains a column, sorting, and diff behavior with no UI changes.
- Macro columns are tagged in the registry and render only when "Include macros" is on.

## 10. Technology Stack

Python 3.9, PyQt5, pandas/numpy (scipy if needed). Dev: Windows 11, 8GB, ≤100k instances. Deploy: Linux, 100GB, ≤20M instances.

## 11. Module Breakdown

- `schema.py` — attribute schema (name/type/default) + metric registry (MetricSpec definitions).
- `loader.py` — JSON → typed DataFrames, applying the schema (defaults, coercion) + validation.
- `metrics.py` — hierarchy build, filter, aggregation driven by the metric registry, pickle.
- `model.py` — Qt item model for the tree-table (columns generated from registry).
- `ui_main.py` — main window, toolbar (load / search / threshold / macros), tabs.
- `ui_tree.py` — tree-table + sort + threshold.
- `ui_search.py` — search results popup window.
- `ui_compare.py` — two-version load + diff view.
- `config.py` — threshold default, cache location.

## 12. Testing & Verification

- Unit tests for metric formulas (hand-computed small netlist).
- Filter tests (missing cell, macro, physical-only).
- Hierarchy construction tests (nested paths).
- Pickle round-trip (cache hit == fresh compute).
- Manual GUI smoke test with a sample JSON pair.

## 13. Out of Scope (v1) / Future

- 2D heat map (reserved attributes).
- Level-only aggregation mode.
- Cross-level sorting.
