# Real OBS blockage, and a smaller metal CLI

The plan for replacing the macro-blockage heuristic with the macro LEF's own obstruction
geometry. What was built and what the measuring turned up is in
[`metal_density_asbuilt.md`](metal_density_asbuilt.md) under *Phase 13*.

## What prompted it

`--macro-block-layers` was a guess standing in for data: a hard macro removed capacity from
"the bottom N layers, over the whole macro outline". The macro LEF usually says exactly which
layers a macro obstructs and where, in `OBS` - and this project already read that file, it just
never looked inside `OBS`. Measured on the vendored real Nangate45 library: 107 `OBS` blocks,
1554 `RECT`s, one `LAYER` per block.

Separately, the `metal` subcommand accepted four flags it never read: `_add_shared` was called
on all four subparsers, but `main()` hands metal to `_run_metal` before any of the read sites,
so `--min-instances`, `--include-macros`, `--cache-dir` and `--force` were accepted and ignored -
with help text advertising a hierarchy filter for a mode that has no hierarchy.

## Decisions taken with the user

- **OBS is authoritative**; `--macro-block-layers` (default 4) is the fallback for a macro
  whose LEF declares no `OBS`, and `0` cancels *only* the fallback.
- **Only non-CORE cells contribute.** A standard cell's `OBS` is pin access, not a keep-out; the
  real library's 107 declaring cells are all `CORE`, and honouring them would subtract a few
  percent of metal1 capacity that varies with the cell mix.
- **"Large and continuous" = the union of a layer's obstructions covering ≥ 10 % of the macro's
  own footprint.** A fraction, not an absolute area, so it means the same on a 130 nm SRAM and a
  7 nm one.

## 1. Parse `OBS` — `parsers/LEF/lefParser.py`, `lefMacro.py`, `compiledRe.py`

A branch in the macro loop reading `OBS` as a nested block: `LAYER <name> ;` sections of
`RECT x0 y0 x1 y1 ;`, closed by a **bare** `END`. The cursor is left *on* that terminator, the
contract the pin loop above already honours, because the caller's single `cursor += 1` steps
past it: stepping past it here would make the enclosing walk skip `END <macro>` and run to the
end of the file looking for a terminator that has gone by.

Rects before any `LAYER` are dropped rather than guessed at; `POLYGON`/`PATH` are counted so the
caller can say a layer is less obstructed than its LEF declares. `LefMacro.obstructions()`
returns a copy, because the caller filters it.

## 2. Filter it — `metal.py`

Per (cell, layer), once per cell type rather than per instance:

1. **Union** the rects, then **close** by 0.1 µm. Measured: a blockage written as abutting tiles
   unions to one region, but the same coverage with a 0.05 µm gap stays 50 regions - and such a
   gap is a tessellation artifact, not a routable channel (every layer measured here has a pitch
   above 0.14 µm).
2. **Clip** to the macro's outline; the closing inflates the perimeter (measured: 102 % of the
   footprint) and a macro cannot block more than itself.
3. **Judge the layer at once**: union ≥ 10 % of the footprint → that geometry is the blockage.

A prototype settled this: per-*component* filtering loses a tessellated blockage entirely (a
real 780 µm² blockage discarded, measured), and per-rect filtering is worse. Judging the union
needs no `MultiPolygon` handling and reads the way the intent was described.

## 3. Per-layer blockage replaces the two-grid capacity model

`_macro_area` (one flat grid of whole outlines) becomes `_macro_blockage`, returning
`{layer_index: float32 grid}`. `MetalData.__init__` takes `blocked` in place of `macro_area` and
precomputes the routable area per layer, which retires the `_routable_base`/`_routable_bot` pair
and their "only two arrays are needed" comment: a macro can block a non-contiguous set of
layers, which two grids cannot express. `_stranded_cells` generalises the same way and loses its
`macro_block_layers` early-out, since obstruction-derived blocking is independent of that flag.

Two details that matter at scale: the per-layer grids are **float32** and the routable grids are
built once, because `cell_detail` runs on every mouse hover and `_routable` used to be a
reference return.

## 4. Say which mechanism was used

`logger.info` rather than user-facing warnings - a macro with no `OBS` is not suspect *data*, it
is the case the flag exists for. The counts ride on `MetalData.blockage`, and the readout names
both mechanisms, because they are not equally trustworthy.

## 5. The rest

- **CLI**: `_add_shared` keeps `--verbose` (read before the metal branch); the pipeline group
  moves to `json`/`verilog`/`def`. `threshold=` dropped from the metal `MainWindow` call.
- **Sample**: one block macro with a realistic multi-layer `OBS` and one without, so both paths
  are exercisable. `verify()` asserts the discriminating facts - a cell obstructed on M1 with M3
  whole can only come from OBS, and a cell with M1 and M3 both gone can only come from the
  fallback.
- **Docs**: `config.py`, `README.md`, `quickstart.py` and the `metal.py` docstrings all stated
  the old model as fact.

## Verification

1. `python -m pytest -q` - green.
2. `python sample_data/metal/generate_metal.py` and its `verify()`.
3. The real files: the gcd design must not move (no hard macros in that library), and the
   Nangate45 cell LEF's 107 obstructions must parse while removing no capacity.
4. `python main.py metal --help` - the four dead flags gone.

## What the review and the tests caught

- **Three states, not two.** The first implementation conflated "declares no OBS" with "declared
  obstructions that were judged negligible", so a macro with only pin-access bites fell back to
  the layer count. `test_pin_access_bites_are_not_a_keep_out` failed, which is exactly the bug
  the whole change exists to avoid.
- **The instance transform.** `p_global = M_block·M_orient·p + (M_block·loc + t_block)`:
  applying the *composed* matrix to the location as well puts a rotated macro's obstruction
  where a second rotation of the placement says. Only visible on a rotated cell, and the new
  orientation test found it.
- **Memory was going the wrong way.** 1 base + *B* blocked grids is more than the constant 3 it
  replaced at the default depth, hence float32 and one precomputation.
