## Performance Review

This is a static review; no production-sized profiler trace was available, so the ranking is based on algorithmic cost and execution flow.

### 1. Physical grid construction: highest likely cost

[physical.py](vlsi_viewer/physical.py) performs a Python nested loop for every leaf box and every grid cell overlapped by that box.

Cost is approximately:

$O\left(\sum_{box} \text{overlappedRows} \times \text{overlappedCols}\right)$

This becomes expensive when cells are large, the grid is fine, or the layout contains many instances.

**Advice**

- Replace the nested Python loops with a vectorized or compiled implementation.
- Use Numba/Cython, or a sparse rectangle-update algorithm.
- Group boxes by affected grid ranges before calculating overlap.
- Benchmark separately for small-cell and large-macro layouts.

### 2. Contour generation repeated for every hierarchy

[physical.py](vlsi_viewer/physical.py) calls `density_for()` for each hierarchy. Each call may invoke:

- `merge_boxes()`
- NumPy conversion and rounding
- Pandas DataFrame creation
- Two Pandas sorts/groupbys
- Shapely polygon creation
- `unary_union()`

The main implementation is in [contour.py](vlsi_viewer/contour.py).

Ancestor hierarchies repeat much of the same work as their descendants because each hierarchy gets its own contour calculation. The cache only avoids repeating the exact same `(path, gap)` request.

**Advice**

- Profile `merge_boxes()` versus Shapely `unary_union()` independently.
- Avoid creating a Pandas DataFrame for every contour request; implement the run-merging operation with NumPy or a compiled routine.
- Consider computing contours only when the user selects a hierarchy, rather than eagerly for every visible row.
- Add a contour cache keyed by hierarchy and geometry version, persisted if startup speed matters.
- For density-only display, calculate area without extracting loops, since `density_for()` does not need loop coordinates.

### 3. Physical density calculations are backgrounded, but physical startup is synchronous

The per-hierarchy density work is correctly dispatched through `QThreadPool` in [model.py](vlsi_viewer/model.py). However, [cli.py](vlsi_viewer/cli.py) builds both the regular design and physical data before starting the Qt event loop.

Therefore, during startup:

- The window does not exist yet.
- The GUI cannot repaint or respond.
- `build_physical()` runs synchronously.
- The block and cell JSON files are loaded once for metrics and again for physical mode.

**Advice**

- Move physical construction into a startup worker after the window is shown.
- Reuse parsed block and cell data between `load_or_build()` and `build_physical()`.
- Persist physical geometry/grid data in a versioned cache, similar to the existing hierarchy pickle cache.
- Show a progress state while physical data is being prepared.

This is likely the main cause of an apparently “stuck GUI” during launch.

### 4. Hierarchy flattening creates repeated Pandas intermediates

[_flatten() in metrics.py](vlsi_viewer/metrics.py) groups direct leaves, builds all prefix nodes, then walks hierarchy depth from deepest to shallowest. Each level creates copies and performs another groupby.

Deep hierarchies can therefore produce substantial allocation and grouping overhead.

**Advice**

- Replace the depth loop with a precomputed integer parent index and NumPy accumulation.
- Encode hierarchy paths once and store parent IDs rather than repeatedly manipulating strings.
- Consider aggregating leaves directly into ancestors using integer ancestor arrays.
- Keep the current Pandas implementation as a correctness reference for benchmarks.

### 5. JSON loading and block expansion are Python/object heavy

[loader.py](vlsi_viewer/loader.py) creates one Python dictionary and one Python record per instance, then converts everything into a DataFrame. [load_blocks() in metrics.py](vlsi_viewer/metrics.py) may copy DataFrames during recursive block expansion and duplicate-block merging.

**Advice**

- Use a faster JSON parser if JSON parsing is measurable.
- Avoid repeated DataFrame copies during recursive expansion; collect normalized records and construct one DataFrame at the end.
- Normalize/coerce attributes in batches where possible.
- Cache parsed block files independently from the aggregate hierarchy cache if multiple modes reuse them.

### 6. Metric computation is repeated during view rebuilds

`metric_columns()` calls `design.metric_values()` and recomputes all registered metrics whenever the view is rebuilt. This affects threshold changes, macro toggles, and search-related view creation.

**Advice**

- Cache metric DataFrames inside `DesignData`, keyed by `include_macros`.
- Avoid rebuilding the entire tree when only the threshold changes; hide/filter existing items where practical.
- Cache search views or reuse the existing `TreeView`.

### 7. Tree rendering can still block the GUI

[ui_tree.py](vlsi_viewer/ui_tree.py) creates and formats every visible hierarchy row on the GUI thread. Density calculation is asynchronous, but row creation, sorting, gradient setup, and column resizing remain synchronous.

**Advice**

- Keep lazy expansion.
- Avoid `resizeColumnToContents(0)` after every expansion for very large trees; resize on demand or use a bounded sample.
- Batch large insertions and temporarily disable sorting/updates.
- Consider `QAbstractItemModel` with a virtualized view instead of `QTreeWidget` for very large hierarchies.

## Recommended Order

1. Measure `build_physical()` and `_contour()` with representative large designs.
2. Remove duplicate parsing between metrics and physical mode.
3. Move physical startup construction behind the visible Qt window.
4. Optimize the physical grid overlap loop.
5. Optimize contour merging and avoid loop extraction for density-only requests.
6. Cache metric DataFrames and physical artifacts.
7. Revisit `_flatten()` and tree rendering if profiling still shows them as significant.

The most important architectural point is that density itself is threaded, but physical-data construction and several preprocessing stages still occur synchronously before Qt enters its event loop.
