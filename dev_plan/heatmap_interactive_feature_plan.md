## Initial rough plan
### Background
In heatmap, it only support zoom/pan/fit currently. 
When user see a hotspot region and want to analyze the detailed information in those grid located in hotspot, there is no way to do it from heatmap.

### New feature
Now the grid tiles in heatmap should be selectable by mouse left click drag.
After select a group of grids which boundary is also highlighted, a new hierarchy tree will be built in new frame below original hierachy tree window.

### Hierarchy tree for selected region
This hierarchy tree only consider all things inside selected region.

### Performance evaluation
Give analysis of compute completity for this new feature and impact on total performance.

### Supported mode
First development stage supports phsyical mode in json and def mode. Next development stage(not this development round) supports metal mode which hierarchy tree is able to show wire length distribution per layer in selected region by hierarchies.

### Update official dev plan this file
Append to this file.

---

# Implementation plan (approved 2026-10-19)

## Context

The physical-mode heat map (`json --physical_mode`, `def --physical_mode`) supports only
zoom/pan/fit/hover. A user who spots a hotspot cannot ask "which hierarchies live in this
rectangle?" This feature adds left-drag selection of grid tiles, highlights the region
boundary, and shows a second hierarchy tree below the existing one, restricted to
instances that intersect the selection.

The later metal-mode stage (per-layer wire length per hierarchy in the selected region) is
out of scope. Metal mode has no hierarchy/instance data today, so stage 2 needs a different
data path. The selection payload and UI stay reusable but metal selection is not enabled.

## Decisions confirmed with the user

1. **Boundary rule**: any instance whose bbox intersects the selected tile rectangle is
   included. Area, ULVT area, macro area and bits are apportioned by
   `intersection_area / box_area`; counts count each intersecting instance once.
   **Physical-only instances are excluded from the region tree entirely** (filler, tap,
   decap, and any `is_physical_only` cell): they contribute no count, area, bit or macro
   metric, and a path containing only physical-only instances is omitted.
2. **Columns**: exactly the same columns as the main tree, built from `schema.METRICS`, so
   future metric additions appear automatically. No `Density%`, no new power columns.
3. **Threshold**: the region tree ignores the toolbar Min threshold and shows every
   hierarchy path with at least one selected instance; empty branches are omitted.

## Architecture

```
GenericGraphicsView --sigSelectArea/sigSelectPos/sigSelectDragged--> LayoutView
LayoutView --region_selected(RegionSelection | None)--> MainWindow
MainWindow --> RegionSelection (tile snapping, pure) --> RegionData(PhysicalData, DesignData)
RegionData --lazy, batched stats per path--> region TreeView --> HierarchyTree (unchanged)
```

- `PhysicalData` stores all leaf boxes as path-sorted float32 arrays (`_geom`, `_is_macro`,
  `_is_phys_only`, `_is_ulvt`, `_leak`, `_dyn`, `_leaf_paths`) and provides
  `_slice_for(path)` (`vlsi_viewer/physical.py:85-100`). The region filter is a vectorised
  mask over those arrays; no new spatial index is needed.
- The missing input for the standard metric columns is per-box cell metadata: add one
  `int32` cell code per box plus a small per-cell attribute table during the existing
  `build_physical` walk. Do not retain a second per-leaf DataFrame.
- New `vlsi_viewer/region.py` is pure data (no Qt): tile snapping, `RegionSelection`,
  `RegionData` (selection mask, per-path RAW_COLS, lazily computed metric values).
- `vlsi_viewer/model.py` gains lazy `TreeView`/`Column` adapters so `HierarchyTree` works
  unchanged (it only calls `.get` on counts, children, column series and bars).
- `vlsi_viewer/ui_region.py` holds a small `RegionPanel` (title, summary, second tree).

## UI layout

Physical mode, before any selection. The left column is a vertical splitter; the region
frame is **hidden until the first selection**, then appears below the main tree and hides
again when the selection is cleared. The empty-state hint is kept for the next show.

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ [Search hierarchy…] [Exact ▾] [Find]   │ Min:[100]  ☐ Include macros                 │
├──────────────────────────────────────────────┬───────────────────────────────────────┤
│ LEFT PANE (horizontal splitter, stretch 3)   │ RIGHT PANE (LayoutView, stretch 4)    │
│ ┌──────────────────────────────────────────┐ │ ┌───────────────────────────────────┐ │
│ │ MAIN HIERARCHY TREE (self._tree)         │ │ │ [Map: Cell density ▾] Min[0.0]    │ │
│ │ ▾ TOP                                    │ │ │ Max[1.0] [Fit]                    │ │
│ │   ▸ CORE        12,345  1.2M …           │ │ ├───────────────────────────────────┤ │
│ │   ▸ IFU          8,901  0.9M …           │ │ │    heat map (grid tiles)          │ │
│ │   ▸ IEX          7,403  0.7M …           │ │ │                       ┌────────┐  │ │
│ │   ▸ LSU          7,202  0.6M …           │ │ │                       │ legend │  │ │
│ └──────────────────────────────────────────┘ │ └───────────────────────────────────┘ │
│ ═══════════ vertical splitter (3:2) ════════ │                                       │
│ ┌──────────────────────────────────────────┐ │                                       │
│ │ QGroupBox "Selected region"              │ │                                       │
│ │ Drag on the heat map to select a region  │ │                                       │
│ │ ┌──────────────────────────────────────┐ │ │                                       │
│ │ │ REGION TREE (self._region_tree)      │ │ │                                       │
│ │ │ (empty until a selection is made)    │ │ │                                       │
│ │ └──────────────────────────────────────┘ │ │                                       │
│ └──────────────────────────────────────────┘ │                                       │
├──────────────────────────────────────────────┴───────────────────────────────────────┤
│ Physical mode · 354×409 grid · top lx956c_ioe      x=195.2 y=245.1 density[24,19]=… │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

After a drag, the map shows the snapped selection outline and the lower tree is populated
with only paths that have selected, non-physical instances. Interaction: left-drag selects
tiles (rubber band during the drag, snapped outline on release), middle-drag pans, wheel
zooms, `F` fits, `Esc` or a click outside clears. The region tree's root expands one level
on each new selection; expand/collapse/sort and click-to-contour behave like the main tree.

## Implementation order

1. Record this plan in `dev_plan/heatmap_interactive_feature_plan.md`.
2. Fix/add `GenericGraphicsView` selection signals.
3. Add `cell_code` / `cell_attrs` to `build_physical`.
4. Add `region.py`: `selection_from_points`, `RegionSelection`, `RegionData`.
5. Add lazy region adapters to `model.py`.
6. Add selection mapping/overlays to `ui_layout.py`.
7. Add `ui_region.py` and wire the vertical splitter in `ui_main.py`.
8. Add `HierarchyTree.reset_first_population()` / `clear_view()` and fix the root
   context-menu crash.
9. Add the benchmark, measure, and append the "as built" results.

## Files and changes

### `vlsi_viewer/genericView.py`

- Fix the left-release branch: use `self.mousePressPos` as the first corner (the current
  code uses the release position twice, so `sigSelectArea` is unreachable). Emit
  `sigSelectArea(QRect)` when `abs(dx) > 3 or abs(dy) > 3`, otherwise
  `sigSelectPos(mousePressPos)`; normalize the rect.
- Add `sigSelectDragged(QRect)` emitted from `mouseMoveEvent` while the left button is held
  and the drag exceeds 3 px. Leave middle-button pan and right-button behavior untouched.
- Escape is handled by a window-level `QShortcut` in `MainWindow`.

### `vlsi_viewer/physical.py`

- Add `_cell_attr_arrays(cells)` returning arrays indexed by cell code: `area` (float64),
  `reg_bits` (`register_bit_count` where `is_register_cell`, else 0), `mb_bits` (`reg_bits`
  where > 1), `drive_size` (int64), and bool arrays `is_bi` (`is_buffer | is_inverter`),
  `is_pulse`, `is_clock`, `is_icg`.
- In `build_physical`, build `code_of = {name: i for i, name in enumerate(cells.index)}`
  before `walk`; append `code_of[cell]` beside the existing per-box lists; sort the codes
  with the other arrays. Assign `data._cell_codes` and `data._cell_attrs` after
  `PhysicalData(...)`, like `_pins`; initialize both to `None` in `PhysicalData.__init__`.
- Missing cells are already skipped by the walk.

### `vlsi_viewer/region.py` (new, pure data)

```
@dataclass(frozen=True)
class RegionSelection:
    rect: tuple[float, float, float, float]   # physical x0, y0, x1, y1
    col0: int; row0: int; col1: int; row1: int
    tile_count / width / height properties

def selection_from_points(px0, py0, px1, py1, extent, grid_size, rows, cols)
        -> RegionSelection | None

class RegionData:
    def __init__(self, physical, design, selection)
    roots / children                            # delegated to DesignData
    selected_count -> int
    any_selected(path) -> bool
    stats(path) -> dict[str, float] | None      # RAW_COLS, cached
    metric_values(path) -> dict[str, float]     # schema.METRICS, cached
    prefetch(paths) -> None                     # batched metric computation
    summary_text() -> str
```

- Tile snapping: the tile grid spans `[x0, x0 + cols*g] x [y0, y0 + rows*g]` (it may
  overhang the die; the pixmap does too). `col = floor((px - x0)/g)`, likewise row, for both
  endpoints; take the inclusive range and clamp to `0..cols-1` / `0..rows-1`. A drag ending
  exactly on a tile boundary includes the tile above/right of it. A click is the degenerate
  one-tile case. If the press/release box does not intersect the tile grid, return `None`.
- Constructor: `usable = ~is_phys_only`; `hit = intersection & usable` with four strict
  comparisons (`x0 < rx1 & x1 > rx0 & y0 < ry1 & y1 > ry0`). Physical-only instances are
  excluded from `_idx` before any aggregation. Keep `self._idx = np.flatnonzero(hit)`
  (sorted) and compute overlap fractions once for those boxes in chunks
  (`frac = clip_area / geometric_box_area`, 0 when the box area is 0). Boundary-touching
  boxes (zero-area intersection) are excluded.
- `stats(path)`: find the path's leaf range with `_slice_for(path)`, locate the selected
  indices in that range with two `np.searchsorted` on `_idx`, then reduce that subset:
  - std set = `~is_macro & ~is_phys_only`; macro set = `is_macro & ~is_phys_only`;
  - `count`, `d1d2_count`, `bi_count`, `pul_count`, `ckb_count`, `icg_count`,
    `macro_count`: one per intersecting box;
  - `area`, `ulvt_area`, `bi_area`, `macro_area`, `reg_bits`, `mb_bits`: weighted by
    `frac`.
  Return `None` when the path has no selected usable boxes.
- `metric_values(path)`: one-row DataFrame from the raw stats, then each
  `schema.METRICS[i].compute` once. `prefetch(paths)` builds one DataFrame for all requested
  paths and calls each compute once, then stores the per-path dicts. Individual per-path
  metric evaluation measured ~0.9 ms/path; 1000 paths batched took ~1 ms total.
- A future MetricSpec built from existing RAW_COLS appears automatically. A future metric
  needing a new raw column fails loudly in the column test.

### `vlsi_viewer/model.py`

- Add `_format_region_metric(kind, value)`: for `kind == "count"` render
  `f"{int(round(value)):,}"`; otherwise delegate to `schema.format_metric`.
- Add `region_columns(region, roots, include_macros)` and
  `view_for_region(region, include_macros)`:
  - iterate `schema.METRICS` / `STD_METRICS`, sharing a small `_column(spec, series, bar)`
    helper with `metric_columns`;
  - `_RegionSeries.get(path, default)` -> `region.metric_values(path)[key]`;
  - `_RegionBar.get(path, default)` -> count/area: value / region-root total; percent:
    value clipped to 0..1; gradient metrics keep `bar=None`;
  - `_RegionChildren.get(parent)` -> `design.children[parent]` filtered by
    `region.any_selected` (vectorized) and prefetched;
  - `_RegionCounts.get(path)` -> selected std count (unused while threshold is 0);
  - `TreeView(roots=[r for r in design.roots if any_selected(r)], children=...,
    counts=..., columns=..., paths=[])`.
- `Density%` is appended to the main tree outside `schema.METRICS`; it stays excluded.

### `vlsi_viewer/ui_layout.py`

- Add `selectable: bool = True`; the metal branch passes `selectable=False`.
- Add `region_selected = pyqtSignal(object)` carrying a `RegionSelection` or `None`.
- Mapping: `_viewport_point_to_physical(pt)` uses `mapToScene` and
  `py = extent_y0 + extent_y1 - scene_y`. `_selection_from_viewport_rect(rect)` maps both
  corners, normalizes, then calls `selection_from_points`.
- Persistent `QGraphicsRectItem` at z=30 with a cosmetic 2 px pen and faint fill; z=29
  dashed rubber band during drag. Both use `setAcceptedMouseButtons(Qt.NoButton)`.
  `region_selected` is emitted once on release, never per move.
- `clear_selection()` removes both items and emits `region_selected(None)`.
- Selection survives zoom/pan/fit/map switch; `refresh()` leaves it alone.

### `vlsi_viewer/ui_region.py` (new)

```
class RegionPanel(QWidget):
    node_clicked = pyqtSignal(str)
    sort_changed = pyqtSignal(str)
    show_region(region, include_macros, reset_expansion=True) -> None
    clear() -> None
```

- `QGroupBox("Selected region")` with a word-wrapped summary label and a second
  `HierarchyTree` with threshold 0. Hidden while nothing is selected; the empty-state
  hint "Drag on the heat map to select a region" is retained for the next show.
- `show_region`: optionally reset first-population (a new selection auto-expands its root
  one level), build `view_for_region`, set it, update the summary, show the pane.
  Include-macros rebuilds pass `reset_expansion=False` so the expansion state survives.
  `clear`: `tree.clear_view()`, the hint, and hide the pane.
- Re-emit the tree's `node_clicked` and `sort_changed`.

### `vlsi_viewer/ui_main.py`

- Physical branch: pane 0 becomes `QSplitter(Qt.Vertical)` with `[self._stack,
  region_panel]` (stretch 3:2, initial sizes ~[480, 260], `setChildrenCollapsible(False)`).
  Keep the outer horizontal splitter and its 3:4 stretch unchanged.
- Metal branch constructs `LayoutView(metal, external_controls=True, selectable=False)`.
- Create `self._region_panel`, `self._region = None`, `self._region_include_macros = None`;
  connect `layout.region_selected -> _on_region_selected`, panel `node_clicked` to the
  existing contour toggle, panel `sort_changed` to the status bar.
- `_on_region_selected(None)`: clear `_region`, `region_panel.clear()`. Otherwise:
  `_region = RegionData(self._physical, self._design1, selection)` and
  `region_panel.show_region(_region, include_macros)`.
- `_apply_settings`: rebuild the region view only when `include_macros` actually changed;
  never apply the toolbar Min threshold to the region tree.
- Window-level `QShortcut(QKeySequence(Qt.Key_Escape), self)` calls
  `self._layout.clear_selection()`; store the shortcut object.
- No region panel in metal, compare, or tree-only modes.

### `vlsi_viewer/ui_tree.py`

- Add `reset_first_population()` (clears `_populated_once`) and `clear_view()` (clears
  items, drops `_view`, resets `_populated_once`, restores the single "Hierarchy" header).
- Fix the pre-existing root-path crash in `_on_context_menu`:
  `path.split('/', 1)[1]` raises for a path such as `TOP`; use
  `path.partition('/')[2] or path`.

### Tests

- New `tests/test_region.py`:
  - `selection_from_points`: click, inclusive drag, endpoint exactly on a boundary, clamp
    at the tile-grid edge, drag from outside into the grid, drag fully outside -> `None`,
    whole-die drag.
  - `RegionData` on a small nested design built from the same JSON as its `DesignData`:
    hand-computed RAW_COLS; partial overlap apportioning; boundary-touching exclusion;
    zero-area box; physical-only exclusion from counts and every metric, including a macro
    flagged `is_physical_only`; a path containing only physical-only instances is absent;
    macro stats; counts once; fractional bits; empty/macro-only regions; filtered children;
    lazy `.get`; `prefetch` batching; columns equal `schema.METRICS` labels; bars normalized
    by the region root; whole-die parity with `design.metric_values()` for every RAW_COLS
    (fixture has no physical-only macro).
- `tests/test_physical.py`: `_cell_codes` aligned with `_leaf_paths`/`_geom`/`_is_macro`;
  `_cell_attrs` values match the library.
- `tests/test_gui_smoke.py`: drag/click signal events; `LayoutView` snapping, overlay
  z-order and `NoButton`, click selects one tile, drag emits no `region_selected` until
  release, `clear_selection` emits `None`; `MainWindow` second tree, threshold ignored,
  include-macros rebuild, region node click toggles contour, Escape clears; metal/tree-only
  have no region panel; `HierarchyTree` root right-click does not raise.
- Full suite: `python -m pytest -q`.

### Performance evaluation

Let `N` = leaf boxes, `K` = selected usable boxes, `D` = max depth.

| Operation | Time | Memory | Expected at 3.35 M |
|---|---|---|---|
| Build overhead | O(N + C): one append per leaf, one aligned gather | +4N bytes (`int32` code) + O(C) attrs | +1–2 s and ~13.4 MB; ~2–3 % of startup |
| Mask + selected fractions | O(N + K), four comparisons + chunked fractions | O(K) indices + 4K bytes | **~36 ms measured**; `flatnonzero` adds a pass of the same order |
| `stats(path)` | O(log N + log K + k) | chunk temporaries | root full-die ~30–60 ms; normal node <1 ms |
| Child filtering | O(m(log N + log K)), vectorized | O(m) | negligible per expansion |
| Metrics | one `compute` per metric per batch | O(m·metrics) | ~1 ms per 1000 paths batched (vs ~0.9 ms/path individually) |
| Full-die selection end-to-end | O(N) once | O(K) transient | ~100–200 ms estimated |

A typical hotspot selection is ~55–75 ms end-to-end, dominated by the O(N) mask scan; its
per-selection stats and tree rows are under 10 ms. No work happens on mouse-move except
updating one scene rect. A whole-die level expansion is ~30–60 ms; results are cached per
path.

#### Real-design estimate: `lx956c_ioe` (3,355,697 instances)

Sources: `dev_plan/issue/real_design_log_0921.md` (LEF 10.42 s, DEF 25.97 s for 3,347,979
instances, 220 LEFs, 4 CPU / 20 GB), `dev_plan/pin_density_map.md` (`build_physical`
12.5 s at 2.34 M, pin grid 2.5–3.5 s at 3.35 M), `dev_plan/hierarchy_contour.md`
(synthetic 1 M-cell build ~6.8 s, walk ~2.3 s/M), and the bundled-sample measurement
(`build_design` 0.42 s / `build_physical` 0.97 s at ~108 k instances).

**Initial runtime, command start → GUI visible** (no `--json`):

| Stage | Time | Basis |
|---|---|---|
| LEF parse + cell index (220–221 LEFs, 17.4 k macros) | **10.4–11.2 s measured** | 09-21 log; metal `cell-index` 11.18 s |
| DEF parse + convert (3.35 M instances) | **25.2–26.0 s measured** | 09-21 and 09-13 logs |
| Tree build (`load_or_build` → `_build_leaves` → `_flatten`) | 10–15 s projection | 3.9 µs/instance on the bundled sample; in-memory cache skipped |
| `build_physical` (block/cell DataFrame load, walk, four grids, pin grid) | 20–22 s projection | 12.5 s at 2.34 M, scaled to 3.35 M (17.9 s) + 2.5–3.5 s pin pass |
| Qt window construction | <1 s | existing behaviour |
| **Baseline total** | **~67–75 s** | sum of the above |
| **This feature's build-time addition** | **+1–2 s** | one extra `list.append` per box in the walk, one aligned int32 sort, +13.4 MB |
| **Total with this feature** | **~68–77 s** | ~2–3 % of startup |

If `--json` power filling is used, add ~20 s (dominated by the JSON load; the fill itself
is 0.15 s after the 09-21 fix) — independent of this feature.

**Selection → region tree populated** (one left-drag release):

| Case | `RegionData` construction | First tree population | Total, release → tree |
|---|---|---|---|
| Typical hotspot, ~1 % of boxes (K≈33 k) | ~50–60 ms (the N-scan dominates) | ~5–15 ms | **~55–75 ms** |
| 10 % selection (K≈335 k) | ~55–65 ms | ~10–35 ms | **~65–100 ms** |
| Whole die (K≈3.35 M) | ~50–80 ms | ~50–120 ms | **~100–200 ms** |

Memory while a selection exists: mask N bytes (3.35 MB), `_idx` 8K bytes (0.26 MB typical,
26.8 MB full-die), `_frac` 4K bytes (0.13 MB typical, 13.4 MB full-die), plus small caches.
Nothing is allocated when no selection exists.

### Documentation

- Add `sample_data/bench_region_select.py`; measure selection construction, root stats and
  RSS on the bundled ~100 k-instance physical sample, then project per box to 3.35 M.
- Append an "as built" section with measured timings, test counts and known limits.
- Add a short paragraph to the README's physical-layout section.

---

# As built (2026-10-19)

## What changed

| File | Change |
|---|---|
| `vlsi_viewer/genericView.py` | Fixed the unreachable `sigSelectArea` (release was compared to itself); added `sigSelectDragged` during a left drag. Middle-drag pan and right-drag behavior unchanged. |
| `vlsi_viewer/physical.py` | `build_physical` now appends one cell code per leaf box and builds a small per-cell attribute table (`area`, `reg_bits`, `mb_bits`, `drive_size`, `is_bi`, `is_pulse`, `is_clock`, `is_icg`). Stored on `PhysicalData` as `_cell_codes` / `_cell_attrs`, like `_pins`. |
| `vlsi_viewer/region.py` (new) | `RegionSelection`, `selection_from_points` (tile snapping), and `RegionData` (O(N) mask + overlap fractions, lazy per-path RAW_COLS, batched metric prefetch). Pure data, no Qt. |
| `vlsi_viewer/model.py` | Shared `_column` helper; `region_columns` / `view_for_region` with lazy `.get` series, bars normalized by the region root, and filtered children. |
| `vlsi_viewer/ui_layout.py` | `selectable` flag, `region_selected` signal, viewport→physical mapping with Y inversion, snapped selection rectangle at z=30, z=29 rubber band, `clear_selection()`. |
| `vlsi_viewer/ui_region.py` (new) | `RegionPanel`: "Selected region" group box, summary label, second `HierarchyTree`; `show_region` / `clear`. |
| `vlsi_viewer/ui_main.py` | Physical mode's left pane is a vertical splitter: main tree above, region panel below. Escape shortcut clears; include-macros rebuilds the region view; the Min threshold is not applied to it. Metal mode passes `selectable=False`. |
| `vlsi_viewer/ui_tree.py` | `reset_first_population()` and `clear_view()`; fixed the root-path crash in "Copy full name" (`TOP` has no `/`). |
| `tests/test_region.py` (new) | 17 tests: snapping, apportioning, boundary-touch, zero-area, physical-only, macros, children, prefetch, registry-following columns, whole-die parity. |
| `tests/test_physical.py`, `tests/test_gui_smoke.py` | Cell-code alignment; drag/click signals; LayoutView snapping, overlay z-order and `NoButton`; region panel and MainWindow wiring; tree helpers. |

## Semantics as built

- A drag snaps to whole tiles with `floor` on both endpoints, inclusive, clamped to the
  tile grid (`cols*g` / `rows*g`, which may overhang the die like the pixmap). A click is
  the one-tile case. A press/release box outside the tile grid clears.
- An instance is included when its bbox has positive-area overlap with the selection
  (`x0 < rx1 & x1 > rx0 & y0 < ry1 & y1 > ry0`). Area, ULVT area, B/I area, macro area,
  register bits and MB bits are apportioned by `overlap_area / box_area`.
- **Physical-only instances are excluded before aggregation.** They contribute no count,
  area, bit or macro metric, and a branch containing only them is absent. This is stricter
  than the density map, which counts their area.
- Columns are built by iterating `schema.METRICS` / `schema.STD_METRICS`, so a future metric
  registered there appears automatically. `Density%` (appended outside the registry) is not
  shown. Region count formatting rounds apportioned bit counts; other kinds delegate to
  `schema.format_metric`.
- The region tree ignores the toolbar Min threshold. Clicking its nodes uses the same
  contour toggle as the main tree. Include macros rebuilds its columns without resetting
  the user's expansion.

## Performance (measured)

`python sample_data/bench_region_select.py` on the bundled physical sample
(108,436 boxes, 19 hierarchy nodes, 170×170 grid, grid size 3.0):
`build_design` 0.41 s, `build_physical` 0.98 s.

| Selection | K selected | RegionData | root stats | metrics | child batch | idx+frac |
|---|---|---|---|---|---|---|
| 1 % hotspot (densest tile) | 1,093 | 0.90 ms | 0.17 ms | 1.52 ms | 1.71 ms | 0.01 MB |
| 10 % | 6,192 | 0.59 ms | 0.33 ms | 1.03 ms | 2.01 ms | 0.07 MB |
| whole die | 51,086 | 1.94 ms | 2.59 ms | 1.19 ms | 4.60 ms | 0.61 MB |

The whole-die K is about half the box count because physical-only filler is excluded.
The child batch is the root's six hierarchy children; metrics are computed in one batched
pandas pass (individual per-path evaluation measured ~0.9 ms/path).

Projection to `lx956c_ioe` (3,355,697 instances), per-box scaling:

| Case | RegionData construction | Root stats | Metrics + children | Total, release → tree |
|---|---|---|---|---|
| ~1 % hotspot (K≈33 k) | ~28–60 ms (O(N) mask scan dominates) | ~2–5 ms | ~2–10 ms | **~35–75 ms** |
| 10 % (K≈335 k) | ~18–60 ms | ~17–50 ms | ~5–15 ms | **~40–125 ms** |
| Whole die (K≈3.35 M) | ~36–100 ms | ~170 ms | ~5–20 ms | **~100–250 ms** |

A separate micro-benchmark measured ~36 ms for the mask + selected fractions on 3.35 M
random boxes (a naive all-box fraction version was ~94 ms). The sample's per-box
projection is more conservative (30–60 ms for the mask scan). Typical hotspot selections
stay under the 100 ms worker gate; the whole-die case is the only one over it and is a
deliberate "select everything" action. Mouse-move work is O(1) (one rubber-band rect).

Initial runtime impact: the extra `list.append` per box and the aligned int32 sort add
~1–2 s to the ~67–75 s `lx956c_ioe` startup (LEF 10.4–11.2 s + DEF 25.2–26.0 s measured;
tree build 10–15 s and `build_physical` 20–22 s projected). Memory +13.4 MB for the cell
codes, plus 3.35 MB of mask and up to ~40 MB of idx+fractions while a whole-die selection
exists. Nothing is allocated when no selection exists.

## Verification

- `python -m pytest -q` → **688 passed in 69.14 s** (657 before; 31 new tests).
- Offscreen end-to-end on the bundled sample: an 11×11-tile hotspot selected 489
  instances, the region tree showed root `CPU_CLUSTER` with child `core_0` and 12 columns.
- Manual checks covered: rubber band during drag, snapped outline on release, overlay
  z=30 / `NoButton`, main threshold ignored, include-macros columns, region-node contour,
  Escape and outside-click clear, selection surviving zoom/pan/fit, physical-only
  exclusion, and metal mode unchanged.

## Known limits

- Metal mode selection is disabled (`selectable=False`); per-layer wire length by hierarchy
  remains stage 2.
- Whole-die selections take ~100–250 ms end-to-end at 3.35 M; a hotspot is ~35–75 ms.
  If the worker gate is exceeded on the real machine, move `RegionData` construction into
  the existing token/worker pattern.
- The region tree has no search box (`TreeView.paths=[]`).
- A metric that needs a *new* raw column must add that aggregate to `RegionData.stats`; the
  column test fails loudly until it does. Metrics built from the existing RAW_COLS follow
  automatically.
