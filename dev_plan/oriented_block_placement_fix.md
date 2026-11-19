# Fix: oriented sub-block placements are translated by the raw DEF location

Source report: `dev_plan/issue/real_design_subblock_layout_1119.md` (real design,
`gen_sp_1_u_sp` FN copy missing from physical-mode maps).

## Root cause

DEF `PLACED (x y) orient` gives the lower-left corner of the instance's **oriented**
bounding box. `Frame` is `p -> M p + t`; the block-level walkers pass `t = raw location`,
but the correct translation is `t = location - min(M · local_bbox)`.

- `vlsi_viewer/physical.py:513-531` (`build_physical.walk`) pushes raw locations onto the
  frame chain and accumulates them in the N-only fast path.
- `vlsi_viewer/assembly.py:202-210` (`HierarchyAssembler._child_frames`) passes the raw
  location to `Frame.compose`; this feeds metal wiring, metal boundaries, macro blockage,
  physical pin density and metal DB frames.

For `FN` the missing term is `(width, 0)`: the mirrored copy is shifted one block width to
the left. At die edge x=0 it lies entirely at negative x and is discarded by the die clip
(`physical.py:607-611`) and the pin-bin bounds check (`physical.py:412`).

Leaf boxes and `_pin_offsets` already implement the rule; only block frames are wrong.

## Fix

1. Add to `vlsi_viewer/assembly.py` beside `Frame`:
   - `boundary_bounds(boundary)` -> `((bx, by), (w, h))` from min/max over all boundary
     points, or `None`.
   - `placement_origin(orient, location, bounds)` -> `location - min(M·bbox)` using
     `Frame(orient, (0,0)).apply_rect(...)`; raw location when `bounds is None`.
   `Frame` itself is unchanged.
2. Use the corrected origin in `HierarchyAssembler._child_frames` (`boundary(model)` of the
   child block) and in `build_physical.walk` (`blocks[cell][1]`), including the N fast path
   and its rollback.
3. Correct the `_pin_offsets` docstring: zero for N/FW only (FN is the cell width).

## Tests

New (write first):
- `tests/test_metal_assembly.py`: helper invariant over all 8 orientations with a
  nonzero-min bbox, plus the `bounds=None` fallback.
- `tests/test_physical.py`: N + FN siblings at the left edge (the real case), asserting
  exact boxes and nonzero density in both lobes.
- `tests/test_physical.py`: N fast path with a child bbox starting at (2,3).

Updated (they encoded the old rule):
- `test_physical.py::test_nested_rotated_block` -> bin `[0,2]`.
- `test_physical.py::test_nested_rotated_block_two_levels` -> box `[13,15]x[15,17]`.
- `test_physical.py::test_pin_density_under_a_rotated_sub_block` -> origin `(42,0)`,
  pin `(41.5,1.0)` -> `grid[0,10]`, box `(40,0,42,4)`.
- `test_metal_hierarchy_frames.py::test_a_wire_in_a_sub_block_lands_where_its_instance_puts_it`
  -> direct wire oracle at x=7.
- `test_metal_metric.py::test_a_rotated_sub_block_outline_turns_with_it` -> outline
  `(5,5,7,9)`.

## Samples

Both generators compensate for the old rule; regenerate them. The effective frame
translations are unchanged, so the rendered samples and `verify()` numbers stay the same.

- `sample_data/physical/generate_physical.py`: rotated cores become direct lower-left
  placements `(285,15) W`, `(285,285) S`, `(15,285) E`; regenerate `instance_info.json`.
- `sample_data/metal/generate_metal.py`: drop the `Frame` probe, place at `target`;
  `top.def` placements become `(660000,60000) W`, `(60000,660000) FS`,
  `(660000,660000) E`; remove the now-unused `Frame` import.

## Verification

- `python -m pytest tests/test_physical.py tests/test_metal_assembly.py tests/test_metal_hierarchy_frames.py tests/test_metal_metric.py tests/test_sample_generator.py tests/test_metal_sample.py -q`
- `python -m pytest -q`
- `python sample_data/physical/generate_physical.py` and
  `python sample_data/metal/generate_metal.py` -> `verify: OK`
- `git diff` on the samples: only the expected placement lines.

## Follow-up (issue 1119 §7.1, §7.3)

Both deferred items are now fixed:

- `metal.py` `_macro_blockage`: a macro's placement translation now includes its own
  oriented-bbox offset, `M_block·(loc + off) + t_block`, for the declared-OBS path and the
  no-OBS fallback footprint. `tests/test_metal_metric.py` is re-baselined and rotation
  coverage added for non-square, fallback, and nested-in-a-rotated-block macros.
- `coordinateProcess.py`: `calculateOriginByOrient`'s E branch now uses the width, not the
  height; a parametrized unit test pins all eight orientations.

Still not addressed (recorded): `Orient.mergeOrient` is wrong for 16 ordered pairs
(mirrored parent × quarter-turn child) but is uncalled; LEF `ORIGIN` is not parsed, so all
offsets assume a macro-local bbox starting at (0, 0).
