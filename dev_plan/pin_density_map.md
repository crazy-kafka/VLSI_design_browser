# Hierarchy area sort + a pin-density map in DEF physical mode

Two behaviour changes requested together, both landing in the **json/def physical mode**: metal mode
keeps metal density alone because it is far heavier, and the pin map belongs where the heat map is
cheap and already has a working map selector.

1. **The hierarchy table sorted by area when first shown.** Today it is populated in lexicographic
   path order, and a per-level sort runs only when a user clicks a header.
2. **A new map type, "Pin density".** For every pin of every placed instance, the grid cell holding
   that pin's **centre** gains one. Orientation must be applied: a pin's shape is stated in the
   cell's own coordinates.

Settled with the user before implementation: **every pin of every placed instance**; **one point per
pin** (the centre of its whole extent); **power and ground pins excluded**, by the LEF pin's `USE`
and by name as a fallback; **DEF mode only — the json mode omits the map**, because its inputs carry
no pin data.

## What the change rests on

- The physical map selector works (`external_controls` is False there), and its ramp is data-derived
  (`_autoset_range`: lo 0, hi = the map's max), which a count map fits.
- **Trap**: `LayoutView.__init__` sets `_fixed_ratio = hasattr(physical, "kinds")`. Giving
  `PhysicalData` a `kinds()` method to carry the new entry would put *all four* existing physical
  maps on the fixed 0..1 ramp. The entry is built from a data attribute instead.
- Pins exist nowhere today: `LefPin.shape` is overwritten by each RECT (last wins) and nothing reads
  it; `CELL_ATTRS` has no pin column, so a `cell_info.json` can never carry one.
- **The channel already exists**: in the `def` flow `cli.py:238` calls `cell_info_from_lef(args.lef)`
  and hands the result to both `load_or_build` and `build_physical`. Pins ride out of that same walk
  as a second return value — the shape `with_obstructions` already uses for metal's obstruction
  table. The `json` flow loads a `cell_info.json` and passes none, which is the required omission.
- **The placement rule, from `lefdefref.pdf` p89**: *"a DEF COMPONENTS placement pt indicates where
  the lower-left corner of the placement bounding rectangle is placed after any possible rotations or
  flips"*, and *"Components are always placed such that the lower left corner of the cell is the
  origin (0,0) after any orientation."* So a macro-local pin point `p` maps to global as
  **`M_o·p − ℓ + loc`**, where `ℓ` is the lower-left of the *oriented* local bbox: zero for N/FW/FN,
  and non-zero otherwise (for W it is the macro's height). Omitting `ℓ` would put every rotated
  macro's pins one macro-extent away from the box the view draws for it. `physical.py`'s own box code
  (`_oriented_extent`) already follows the reference, so the pins must too — and then they land
  inside the drawn box by construction.
- `assembly.Frame.compose` is the same composition, tested against `CoordinateProcess.dbTransform`
  for all eight orientations and all 64 pairs.

## Phase 1 — the hierarchy table's initial sort

`HierarchyTree.rebuild`/`_populate` add rows in `TreeView.children` order. Make **Area (column 1)
descending** the initial sort by setting `_sort_column`/`_sort_order`/`_sort_active` and the header
indicator before the rows go in, letting the existing `_sort_item` do the work at each level —
including in `_populate`, so a lazily expanded subtree is sorted too. Descending is what the user's
first header click does, and it preserves the sibling order `test_bar_ratios_stored` pins.

## Phase 2 — pins out of the LEF, and only there

Rides the walk that already happens; no second LEF parse.

- **`lefParser`**: inside the pin body loop, accumulate the pin's rect union alongside the existing
  last-wins `shape`, and set the pin's **centre** (`(min+max)/2` per axis) on the `LefPin` — the
  centre of the union, so a three-rectangle pin is one point. `shape`/`setPin` contracts untouched.
- **`convert.cell_info_from_lef(..., with_pins=True)`**: mirrors `with_obstructions` — returns
  `(info, pins)` with `pins = {cell: [(use, name, cx, cy), …]}` filtered where both facts are in
  hand: skip `USE POWER`/`GROUND`, or a name starting with VDD, VSS, VCC, GND, VPP, VBB, VPW, VNW.
  The two extras are mutually exclusive (one-line guard); metal's call site is unchanged.
- **`cli.resolve_inputs`** returns the pins alongside (`None` for json/verilog) → `build_physical`.
  `cell_info.json` and `schema.CELL_ATTRS` are untouched, so an existing cache keeps working.
- Cost: this is the `cell-index` stage, 11.2 s for 221 LEFs / 17,385 cells on the real design.

## Phase 3 — the pin-density grid, and its performance plan

**3.1 The transform.** Per orientation, `_PIN_OFFSET[o] = (−ℓx, −ℓy)` is built at import from the
tested `_ORIENT_MATRIX` by taking the componentwise minimum of `M·corner` over the four corners of
`[0,w]×[0,h]` — derived, not hand-typed. A unit test pins the eight results against their closed
forms (N (0,0), S (w,h), W (h,0), E (0,w), FN (w,0), FS (0,h), FW (0,0), FE (h,w)). Computing the
centre in local coordinates is valid because all eight orientations are linear maps.

**3.2 The pass, grouped and vectorised.** Per block, never per instance: `HierarchyAssembler.walk`
hands each block its `Frame`; the block's instance columns come out of the DataFrame as numpy
(`cells.index.get_indexer` for the cell code, one orientation code lookup); then per orientation
present (≤ 8) the instance × pin expansion is a handful of numpy expressions — `np.repeat` + index
arithmetic for the point index, two gathers for the pin centres, four FMAs plus the grid division,
`keep` for the extent, and `np.bincount` on flat indices — the same idiom the density pass already
uses four times (`physical.py:345-401`). Python iterations = blocks × orientations × chunks.

**3.3 Cost and budget.** Linear in the point count, ~13 passes over T, paid at most once. Peak
memory is bounded by chunking the expansion. Measured below.

**3.4 Why not a pandas explode.** `merge(pins, on="cell_name")` materialises 17–34 M DataFrame rows
with an index and object columns — gigabytes, and slower than raw float32 arrays. Pandas earns its
place only for leaving the DataFrame without a row loop (`get_indexer`, `to_numpy`, `unique`).

**3.5 Laziness.** `PhysicalData.pins` is built on the first `heat("pins")` and cached, so a run that
never opens the map pays nothing. The pass logs its point count and seconds in the physical mode's
existing style.

**3.6 Pre-registered bar**, before any of it was written: (a) a unit test proves a pin lands in the
drawn box for each of the eight orientations; (b) the fixture's measured per-point cost projects the
real design's map at ≤ 5 s; (c) peak RSS inside the build's existing envelope; (d) the `cell-index`
LEF stage does not regress measurably; (e) the existing suite passes untouched. If the projection
exceeds 5 s, trim the index build or the chunk budget — not the correctness.

## Result (measured, this checkout)

    python sample_data/bench_pin_density.py --scale 500     # 234k instances
    python sample_data/bench_pin_density.py --scale 5000    # 2.34M instances

The fixture replicates the real DEF's own instances (its cells, orientations and pin counts) over
the real design's die, because 468 instances of a real file measure almost nothing but per-block
overhead. Scale 1 is the untouched DEF and is what proves the real parse path runs.

| scale | instances | pin points | pin pass | s / M points | pass RSS added |
|---|---|---|---|---|---|
| 500 | 234,000 | 632,981 | 0.24 s | **0.387** | 1 MB |
| 5000 | 2,340,000 | 6,311,993 | 2.33 s | **0.369** | 1 MB |

Linear to within 5 % over a 10× step, and the pass adds **1 MB** at both sizes: the chunking bounds
the temporaries as designed. Projected to `lx956c_ioe`'s 3,355,697 instances at this cell mix
(2.70 pins/instance, 9.1 M points) that is **3.3–3.5 s**, against the 5 s bar — and at 6 or 10
pins per instance, 7.4 s and 12.4 s. The design's own pins-per-instance is unknown here (its LEFs
are not on this machine), so the mix-sensitivity is the honest form of the number.

Where the time goes, from `cProfile` at scale 500: **42 % is `HierarchyAssembler._child_frames`**
(`assembly.py:202`), which scans every instance row with `itertuples` looking for sub-block
references — a per-*instance* cost, not a per-*point* one, and the same scan `build_physical`'s own
box walk pays (its build is 12.5 s at 2.34 M instances, ~5× the pin pass). Vectorising that scan
with `isin` is the obvious next lever; it is shared metal code, so it is left alone here.

The other bar items: (a) three tests place pins under all eight orientations, one under a rotated
sub-block, and one through a reused sub-block, each checked against the box the density map draws;
(c) the 1 MB above; (d) the LEF parse with and without pins is identical within noise on the
Nangate45 library (0.012–0.017 s, 135 cells, 533 pins) — the marginal work is four float comparisons
per RECT, so the real 221-LEF stage's 11.2 s is not in question; (e) 610 tests pass.

Two defects the tests found, both silent: an off-by-one between the pin table's cell codes (0 =
"not in the library") and the offsets table, and an instance with no orientation, which reads as
`''` rather than NaN — the box pass catches that with `or "N"`, and the pin pass now matches it.
Without the second fix every JSON-sourced block would have produced an empty pin map.

## Phase 4 — the map entry, DEF mode only

`LayoutView._kinds` gains `("pins", "Pin density")` **appended** (so no existing combo index moves)
and only when `physical.pins is not None`; `PhysicalData.heat` gains the key. The json mode never
constructs that attribute, so its combo keeps its four maps.

## Verification

1. `pytest -q` (601 before). New: the eight-orientation transform (a pin at a known local position
   lands in the expected grid cell for N/R90/MX); a power-named and a `USE POWER` pin both skipped;
   four maps on the json path and five on the DEF path; siblings in descending area order at build.
2. Must not move: `test_layout_first_visit_to_map_autotanges`,
   `test_layout_range_kept_across_map_switch`, `test_bar_ratios_stored`, every `test_physical.py`
   grid assertion, and the LEF pin tests (last-RECT-wins `shape`).
3. The 3.6 bar, measured on `sample_data/real/nangate45/gcd_nangate45.def` + its LEF and projected to
   3.36 M instances — the projection labelled as one.
4. Then the real design: a DEF+LEF run on `lx956c_ioe`.

## The demo path: `quickstart.py def` had no pins to count

Reported after the first run of the feature: `python quickstart.py def` offers four map types.
Not a defect in the map - `sample_data/eda/cells.lef` declared **no `PIN` statement at all**, so
there was no pin geometry to count and the entry was correctly absent. That sample is *generated*,
so the fix went into `generate_eda_sample.py` rather than the file: every macro now declares its
signal pins (named from the cell's kind, inputs along the bottom edge, the output along the top)
plus a `USE POWER` VDD rail and a `USE GROUND` VSS rail, which the map must *not* count. Physical
only cells declare no signal pin, so the filler and tap cells contribute nothing either way.

The generator's `verify()` asserts what that implies - one counted point per declared signal pin,
none for a rail, none for an area-only cell - and builds the pin grid from the regenerated sample:
20 macros, 56 signal pins, 11,424 points over the placed design, max 30 pins in a 2 um bin.
`quickstart.py def` now offers *Cell density / Leakage power / Dynamic power / ULVT density / Pin
density* and renders the fifth.

## Flagged, not fixed: metal's obstruction transform

`metal._macro_blockage` (`metal.py:1151-1162`) implements `p_global = M_block(M_o·p + loc) + t_block`
— the raw-placement-point convention, without the `ℓ` term. By the reference passage above that is
wrong for S/W/E/FN/FS/FW, and would put a rotated macro's obstruction geometry one macro-extent away
from the same macro's footprint. Nothing in this change touches it, and the pin pass must not inherit
it. Worth a separate check against a rotated macro in a real design.

## Later: the pin grid moved out of the map switch (2026-09-22)

Reported: selecting **Pin density** in physical mode froze the window for a while. Cause, measured:
it was the one grid built lazily, and the build ran **on the GUI thread**, inside the map selector's
own signal handler (`ui_layout._on_type` -> `set_kind` -> `_autoset_range`/`refresh` ->
`PhysicalData.heat("pins")` -> `_pin_grid` -> `_pin_density`). The cost is linear in the pin-point
count (`sum of pins(cell)` over placements) at **0.25-0.34 us per point**: 11,424 points on
`sample_data/eda` (5.8 ms, invisible), 10 M points on a synthetic design (3.35 s). The reported
`lx956c` design has 3,355,697 instances, so about 9.6 M points and **~2.5-3.5 s** of unresponsive
window - no repaint, no hover, no cancel, and "Not responding" past ~5 s. The rest of the switch was
milliseconds; the four other grids are computed in `build_physical`, before `MainWindow` exists.

What changed in `physical.py`, and nothing else:

- `build_physical` now computes the pin grid where it used to retain the source for a later build,
  with the CLI's physical-mode call still landing before the window (`cli.py:447`). The source tuple
  is no longer held, so steady-state memory goes *down*; the grid is 0.4 MB at the 09-17 run's
  189x253.
- `PhysicalData` lost `_pin_source`, `_pin_lock` and `_pin_grid`: with one builder there is one
  lifetime, `has_pins` is `_pins is not None`, and `heat("pins")` returns that array. `_kinds_for`
  is unchanged, so the json path still offers no such map.
- Every phase now announces itself *before* it runs - the walk, the four grids, and the pin grid -
  because the window does not exist yet and a chip-level run was otherwise minutes of silence
  followed by results. The notices pair with the result lines that follow them, and each names what
  is being computed. `_pin_density`'s own point-count line already reports the points and the grid,
  so the wrapper's line was reduced to the two things it alone knows: the elapsed time and the peak
  bin.

Measured after, offscreen on `sample_data/eda` at the same grid: the combo switch to Pin density is
**0.36 ms** (was 6.4 ms, with the build inside it), switching back 0.27 ms, and the whole
`build_physical` - pin grid included - is 0.032 s. On the reported design the ~3 s moved into the
pre-window phase, which is the trade the other four grids already make: paid whether or not the map
is ever opened.

Tests: `test_pin_density_counts_one_point_per_placed_pin` asserted the old lazy contract
(`data._pins is None`) and now asserts the new one (built, and `heat("pins") is data._pins`);
`test_the_build_says_what_it_is_computing` pins each notice ahead of its result line, by index in
the captured records. **652 tests pass.**
