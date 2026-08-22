# Hierarchy contour + hierarchy density metric (physical mode)

## Contour display
Clicking a hierarchy node in the tree draws a dashed yellow outline around that
node's instances in the layout view; clicking the same node again hides it;
clicking another node swaps the contour. Multiple loops are drawn when the
instances are scatter-distributed (each scatter group gets its own loop).

- `vlsi_viewer/contour.py` (new): dual-backend rectilinear-union geometry.
  - **shapely backend** (primary): `unary_union` of the gap-expanded boxes gives
    exact exterior/interior rings and disjoint scatter groups; no manual
    clustering needed.
  - **scipy + manual fallback** (used when shapely is not importable): clusters
    boxes with `scipy.spatial.cKDTree` (+ `connected_components`) and computes
    the rectilinear union boundary with a plane sweep implemented here.
  - `contour_geometry(boxes, gap)` -> (loops, area); boxes are padded by
    `gap/2` so instances closer than `gap` merge into one loop (the hierarchy's
    "spacing scope") while genuine scatter stays as multiple loops.
  - `union_geometry` / `geom_loops_area` support child-reuse of cached polygons.
- `vlsi_viewer/physical.py`: `build_physical` threads a prefix through `walk` and
  tags every box with its full hierarchy path + `is_macro`. `PhysicalData` keeps
  per-path aggregates (`path_boxes`, non/macro area) and cached
  `contour_for(path)` / `density_for(path)` (parents reuse children's cached
  geometries when computed bottom-up).
- `vlsi_viewer/ui_tree.py`: `node_clicked` signal on item click (skips the
  lazy-expand placeholder); `vlsi_viewer/ui_main.py` forwards it to
  `LayoutView.toggle_contour(path)`; `ui_layout.py` draws dashed
  `QGraphicsPolygonItem` loops (z=20, above boundary outlines at z=10).

## Density metric
`density = non_macro_area / (contour_area - macro_area)` per hierarchy path,
a percentage with a "higher better" gradient (default range 20%-65%). It is
physical-only (not in `schema.METRICS`); `schema._GRADIENT_RANGES["density"]`
registers the range and `model.density_column(physical, paths)` appends a
"Density%" column to the tree in physical mode.

## CLI
`--contour_gap N` overrides the merge gap (default `2 * grid_size`; factor in
`config.DEFAULT_CONTOUR_GAP_FACTOR`).

## Performance notes
Contour + density are lazy and cached. Two changes scale them to large designs
(a 10M-instance subsystem):

1. **Exact box pre-merge** (`contour.merge_boxes`): overlapping/abutting boxes are
   collapsed into maximal rectangles (horizontal then vertical run-merge) before
   `unary_union`/manual sweep. Exact — the union is unchanged. A dense 10M-cell
   placement collapses to ~1k rectangles, cutting the whole-die contour from
   ~10 min (linear extrapolation) to ~4.5 s.
2. **Compact storage + lazy slice access** (`physical.PhysicalData`): leaf
   geometry is kept as float32 numpy arrays sorted by path (~18 B/box vs ~350 B
   as Python tuples; 10M -> ~160 MB) with a `_slice_for(path)` searchsorted slice
   instead of a duplicated `path_boxes` dict. `contour_for` / `density_for`
   slice the arrays on demand.
3. **Lazy density column** (`model._LazyDensity`): a hierarchy's density is
   computed only when the tree renders that node (lazily on expand), cached
   afterwards, so startup no longer precomputes every node.

Bundled-sample timings: contour of a sub-block ~0.1 s, a core ~0.5 s, the whole
die ~1.5 s (all cached). `--verbose` logs each contour/density computation.

## Verification
- `python -m pytest -q` (79 passed) incl. cross-backend contour tests
  (`tests/test_contour.py`), path/density asserts, and a GUI contour-toggle smoke
  test.
- Manual: physical mode -> click a core/sub-block -> dashed contour appears;
  click again hides it; "Density%" column shows the gradient bar.
