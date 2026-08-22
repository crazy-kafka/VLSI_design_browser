# ULVT density map in physical mode

## Change
Added a fourth physical-mode heat map, "ULVT density" = ULVT-cell area / bin
area (a `[0,1]` ratio like the density map, counting only cells with
`is_ULVT`).

- `vlsi_viewer/physical.py`:
  - `PhysicalData` gains an `ulvt` grid; `boxes` tuples become 7-long
    `(x0,y0,x1,y1,leakage,dynamic,is_ulvt)`.
  - `build_physical` builds an `is_ulvt` lookup from `cell_info` (the
    `is_ULVT` flag already existed in `schema.CELL_ATTRS`), records it per
    box during the walk, accumulates `ov/grid_area` into a separate `ulvt`
    grid for ULVT cells, and applies the same `[0,1]` clamp + near-1.0 snap
    as density.
  - `heat("ulvt")` returns the new grid.
- `vlsi_viewer/ui_layout.py`: added `("ulvt", "ULVT density")` to `HEAT_TYPES`;
  `_autoset_range` treats `ulvt` as density-like (`[0,1]`, no power floor).
  The hover readout and legend pick it up generically.

## Test
`tests/test_physical.py::test_ulvt_density_grid` — a ULVT cell contributes to
both density and ulvt grids; an SVT cell contributes only to density.

## Verification
- `python -m pytest -q` -> 70 passed.
- Real sample: heat types = density/leakage/dynamic/ulvt; ulvt area ~8386
  (matches the XOR2_X1-only ULVT mix); hover readout reports `ulvt[...]`.
