# Grid size via CLI + hover coordinate readout

## 1. Move grid setting from GUI to CLI
- The physical heat-map grid size was a `QSpinBox` in the layout view
  (`ui_layout.py` `grid_spin` / `_on_grid`), which rebuilt the physical data on
  change.
- It is now a CLI argument `--grid_size` (default 3.0), used only in physical
  mode. Added `DEFAULT_GRID_SIZE = 3.0` to `config.py`, `--grid_size` to
  `cli.py` `parse_args`, passed to `build_physical(grid_size=...)`.
- Removed the `Grid:` control and `_on_grid` from `ui_layout.py`, and the
  now-unused `_src_paths` / `_src_cell_path` assignments in `cli.py` (they only
  fed the GUI rebuild).

## 2. Hover coordinate + grid value readout
- `GenericGraphicsView.mouseMoveEvent` already emits `sigSceneMouseMoved` with
  the scene point; `ui_layout.py` connects it to `_on_hover`.
- `_on_hover` maps the scene point back to physical coordinates (inverting the
  flipped-Y view via `py = y0 + y1 - scene_y`), computes the grid bin
  `(iy, ix)`, and emits `hover_changed(str)` with
  `x=.. y=.. <kind>[iy,ix] = <value>`.
- The readout always reads `self._physical.heat(self._kind)`, so it tracks the
  selected map type. Switching the type re-emits with the stored last scene
  point so the label updates immediately.
- `ui_main.py` pins a permanent right-aligned `QLabel` in the status bar
  (`statusBar().addPermanentWidget`) and wires it to `hover_changed`.

## Tests
- `tests/test_cli.py`: `--grid_size` default and explicit-value parsing.
- `tests/test_gui_smoke.py`: dropped the `_src_paths`/`_src_cell_path` lines
  (obsolete); added `test_layout_hover_reports_coords_and_grid`.
