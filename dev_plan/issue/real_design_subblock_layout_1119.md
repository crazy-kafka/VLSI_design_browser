# Real design case — `gen_sp_1_u_sp` (FN) is missing from the physical layout map

**Target:** physical layout mode (`def --physical_mode`), “Cell density” map
**Run:** 2026-11-19, 21:31:18 and 21:55:29 as shown on the host, on `wha1cd233-hs`,
`/tmpdata/LinxCore950_PD_N3_t/user/l00922843/design_browser`
**Design:** top `gpu_gpc_top_if`; blocks `gpu_ff_top_if`, `gpu_sp_top`; 220 LEF files / 17,385 macros
**Evidence:** three attached snapshots — GUI (2055 × 966), DEF grep + `zprep` DIEAREA
(847 × 211), and the run log (1251 × 716). The GUI snapshot is the only one that shows the
symptom; the other two supply the DEF placement and the mode’s own log. The snapshots are
not committed with this file; every line and number quoted below is transcribed from them.

Legend used below:

- **Observed** — visible in one of the three snapshots.
- **Derived** — arithmetic on observed DEF/DIEAREA values (database units, DBU).
- **Code** — read from this checkout, with the file and line linked.
- **Reproduced** — a synthetic two-level design run through `build_physical` during the
  analysis; it is not the real DEF, and is labelled where it appears.

---

## 1. Symptom

**Observed (GUI).** The left hierarchy table lists both placements of `gpu_sp_top` with
*identical* roll-ups:

| row | Area | Count | ULVT% | MB% | D1D2% |
|---|---|---|---|---|---|
| `gen_sp_0_u_sp` | 246,069.46 | 2,539,358 | 3.56 % | 90.73 % | 89.79 % |
| `gen_sp_1_u_sp` | 246,069.46 | 2,539,358 | 3.56 % | 90.73 % | 89.79 % |

So the parser and the hierarchy expansion see both blocks. The map, however, is populated
across the die except for the **top-left lobe**, which is the footprint that belongs to
`gen_sp_1_u_sp`. The snapshot annotates that lobe `gen_sp_1_u_sp` and asks “why it is
missing?”; the top-right lobe, annotated `gen_sp_0_u_sp`, is populated.

The map is the physical mode’s `Cell density` raster with the range control set to
`Min 0.200 / Max 1.000` and the `Fit` view; the die is drawn with a notch in its top edge
between the two lobes. The empty lobe contributes no density at all.

**Observed (DEF grep).** The parent DEF places the two blocks as:

```
- U_GPU_SHADER_TOP/U_gpu_shc_top/gen_sp_1_u_sp gpu_sp_top + FIXED ( 0 2029200 ) FN + WEIGHT 1
- U_GPU_SHADER_TOP/U_gpu_shc_top/gen_sp_0_u_sp gpu_sp_top + FIXED ( 1577760 2029200 ) N + WEIGHT 1
```

The grep command line itself is cut off at the top of the snapshot; the two matching
lines and the shell’s `^C` are what is visible.

**Observed (DIEAREA).** `zprep -A 10 AREA GPU_input/gpu_gpc_top_if.def.gz` returns a
10-vertex rectilinear outline:

```
DIEAREA
( 2580960 3962640 ) ( 1577760 3962640 )
( 1577760 3871440 ) ( 1003200 3871440 )
( 1003200 3962640 ) ( 0 3962640 )
( 0 0 ) ( 1263120 0 )
( 1263120 100320 ) ( 2580960 100320 ) ;
```

**Observed (run log).** The mode is physical, the three blocks are loaded and both
`gpu_sp_top` placements are expanded, and the geometry pass runs over the whole hierarchy:

```
INFO vlsi_viewer.metrics: 3 block(s) loaded; top level: gpu_gpc_top_if
INFO vlsi_viewer.metrics: expanding block 'gpu_sp_top' under 'gpu_gpc_top_if/U_GPU_SHADER_TOP/u_gpu_shc_top/gen_sp_1_u_sp'
INFO vlsi_viewer.metrics: expanding block 'gpu_sp_top' under 'gpu_gpc_top_if/U_GPU_SHADER_TOP/u_gpu_shc_top/gen_sp_0_u_sp'
INFO vlsi_viewer.metrics: expanding block 'gpu_ff_top_if' under 'gpu_gpc_top_if/U_GPU_FF_TOP_IF'
INFO vlsi_viewer.metrics: merged 13794236 leaf instance(s)
WARNING vlsi_viewer.metrics: Found 69333 instance(s) with missing cell_info (52 unique cell_name); excluded from all metrics.
INFO vlsi_viewer.metrics: built hierarchy: 140868 node(s), max depth 14, 13794236 leaf instance(s)
INFO vlsi_viewer.physical: physical: walking 3 block(s) for instance geometry
INFO vlsi_viewer.physical: physical: walked 13724903 leaf box(es) (68.6s)
INFO vlsi_viewer.physical: physical: computing density, leakage, dynamic and ULVT grids over 13724903 box(es) on a 869 x 566 grid
INFO vlsi_viewer.physical: physical: 13724903 cell box(es), grid 869 x 566, extent (0.0, 0.0, 1290.48, 1981.32)
INFO vlsi_viewer.physical: physical: pin density 40654512 pin point(s) on a 869 x 566 grid
```

The converted instance counts are also in the log: `gpu_ff_top_if` 3,118,557,
`gpu_gpc_top_if` 5,288,164, `gpu_sp_top` 2,693,759 (after dropping 153 filler). The tree’s
own rows count 2,539,358 instances per `gpu_sp_top` placement; the tree counts only
non-missing standard cells (it excludes macros and physical-only rows), so the two figures
differ for a reason that is unrelated to the missing map lobe. The 69,333 instances without
`cell_info` are absent from the geometry pass, which is why it walks 13,724,903 boxes rather
than the 13,794,236 leaves the tree merged (13,794,236 − 69,333 = 13,724,903).

---

## 2. Coordinate facts

**Derived.** The DEF coordinates are in DBU at 2,000 DBU/µm. The conversion is fixed by the
snapshot itself: the log’s extent is `(0.0, 0.0, 1290.48, 1981.32)` and the DIEAREA’s
maximum is `(2580960, 3962640)`; `2580960 / 2000 = 1290.48` and
`3962640 / 2000 = 1981.32`.

| quantity | DEF value (DBU) | µm |
|---|---|---|
| die right edge | 2,580,960 | 1,290.480 |
| die top edge | 3,962,640 | 1,981.320 |
| `gen_sp_1_u_sp` placement (FN) | (0, 2,029,200) | (0.000, 1,014.600) |
| `gen_sp_0_u_sp` placement (N) | (1,577,760, 2,029,200) | (788.880, 1,014.600) |
| DIEAREA x breakpoints | 1,003,200 / 1,577,760 | 501.600 / 788.880 |
| DIEAREA notch top | 3,871,440 | 1,935.720 |

**Inferred block size.** The snapshots do not print `gpu_sp_top`’s LEF `SIZE`; the size is
recovered from the parent’s own outline and the sibling placement:

- The N sibling at x = 1,577,760 must reach the die’s right edge to explain the full-height
  top lobe over `[1577760, 2580960]`: width = 2,580,960 − 1,577,760 = **1,003,200 DBU =
  501.6 µm**.
- The DIEAREA’s top edge is 3,962,640 over `[0, 1,003,200]` and over
  `[1,577,760, 2,580,960]`, and drops to 3,871,440 only in the gap
  `[1,003,200, 1,577,760]`. That is the footprint of the two 501.6-wide blocks with a
  287.28 µm gap between them.
- The block’s placement y is 2,029,200 and the lobes reach the top edge 3,962,640: height =
  1,933,440 DBU = **966.72 µm**. The 3,871,440 notch is 45.6 µm below the top and exists
  only between the blocks.

So the two placements should occupy:

| instance | orientation | x range (µm) | y range (µm) |
|---|---|---|---|
| `gen_sp_0_u_sp` | N | 788.88 … 1,290.48 | 1,014.60 … 1,981.32 |
| `gen_sp_1_u_sp` | FN | **0.00 … 501.60** | 1,014.60 … 1,981.32 |

The N row is where the tool draws it. The FN row is *not* where the tool draws it: every
box of that block is computed at negative x and discarded before it reaches the map.

---

## 3. Root cause

### 3.1 The rule the code is supposed to follow

DEF’s `COMPONENTS`/`PLACED` point is the **lower-left corner of the instance’s oriented
bounding box**, not the image of the cell’s local origin. This checkout already states it:

- [README.md:282](README.md#L282): `location_x`/`location_y` are the **lower-left corner**
  of the instance’s bounding box.
- [README.md:505](README.md#L505): the pin transform is
  `M_orient·p − ℓ + loc`, “the LEF/DEF reference’s rule that an instance’s location is the
  lower-left corner of its *oriented* bounding box”.
- [physical.py:284](vlsi_viewer/physical.py#L284) implements exactly that rule for leaf
  pins: the offset is the negated lower-left of the cell’s own oriented bbox, and its unit
  test pins all eight values ([test_physical.py:476](tests/test_physical.py#L476)).

The defect is that the **block-level frame** does not use that rule. It treats the raw
placement as the translation of the orientation map:

- [physical.py:482](vlsi_viewer/physical.py#L482) keeps a chain of
  `(orient, origin)` per enclosing block.
- [physical.py:519](vlsi_viewer/physical.py#L519) pushes the raw `(location_x, location_y)`.
- [physical.py:491](vlsi_viewer/physical.py#L491) maps a leaf point with
  `CoordinateProcess.dbTransform("to_global", …)`, which is always `p → M·p + origin`
  (the same eight matrices are tabulated in [assembly.py:61](vlsi_viewer/assembly.py#L61)).

For a block whose local bbox is `[bx, bx+w] × [by, by+h]`, the correct translation is

```
t = location − min over the four bbox corners of (M · corner)
```

but the code passes `t = location`. The two agree only when `min(M · corner) = 0`, which for
a local bbox starting at `(0, 0)` is true for **N** and **FW**, and false for the other six
orientations:

| orientation | required offset `t − location` | for this block (`w`=501.6, `h`=966.72 µm) |
|---|---|---|
| N | (0, 0) | (0.000, 0.000) |
| S | (w, h) | (501.600, 966.720) |
| W | (h, 0) | (966.720, 0.000) |
| E | (0, w) | (0.000, 501.600) |
| FN | (w, 0) | (**501.600**, 0.000) |
| FS | (0, h) | (0.000, 966.720) |
| FW | (0, 0) | (0.000, 0.000) |
| FE | (h, w) | (966.720, 501.600) |

Note that **E uses the width**, not the height, and that **FN is not offset-free** even
though a mirror does not change the box’s extents. The mirror itself is applied correctly
by `_ORIENT_MATRIX`; what is missing is the translation that puts the mirrored box at the
placement point.

### 3.2 The arithmetic for `gen_sp_1_u_sp`

FN is the map `(x, y) → (x0 + w − x, y0 + y)` once the placement anchors the oriented bbox:

- Correct: `x_global = 0 + 501.6 − x_local`, so the block spans `[0, 501.6]`.
- As implemented: `x_global = 0 − x_local`, so the block spans `[−501.6, 0]`.

The tool therefore draws a correctly mirrored copy of the block, shifted exactly one block
width (501.6 µm) to the left of where it belongs. In this design the left edge of the die is
x = 0, so the shifted copy has no legal area at all.

### 3.3 Why it vanishes instead of appearing as a visible offset copy

`build_physical` clips every box to the top-block extent before rasterising
([physical.py:607](vlsi_viewer/physical.py#L607)):

```python
bx0 = np.maximum(geom[:, 0], x0)
bx1 = np.minimum(geom[:, 2], x1)
keep = (bx1 > bx0) & (by1 > by0)
```

For a box wholly at `x1 <= 0`, `bx0 = 0` and `bx1 <= 0`, so `keep` is false and the box is
dropped from **all** four grids. Pin density runs a separate pass that bins a point only when
`0 <= ix < cols`, so the block's pins are dropped there too. The contour and the
selected-region tree are different: they read the stored boxes (`_geom` / `boxes_for`), which
are not clipped, but those boxes now lie entirely to the left of the die — outside the area
the map shows and outside any on-map selection. Every surface loses the block, through one of
those two variations of the same wrong coordinate.

### 3.4 Why the hierarchy table still shows it

The table is built by `vlsi_viewer.metrics` from the instance table and cell attributes,
not from placed boxes. Both `gpu_sp_top` expansions are in the log, and the two rows are
identical because the block really is instantiated twice with the same contents. The tree
is right; only the geometry path is wrong. That rules out a parse, upcast, or dedup issue.

### 3.5 Scope of the same mistake

The raw-origin assumption is in the **block-level** walker, so it is not specific to
physical density:

- [assembly.py:208](vlsi_viewer/assembly.py#L208)
  (`HierarchyAssembler._child_frames` → `Frame.compose`) makes the same assumption for
  metal-mode wires, and `physical._pin_density` reuses that assembler, so the pin grid has
  the same block-level defect.
- Leaf placements are fine: their boxes are built from the leaf’s oriented extent and its
  lower-left location, and their pins use `_pin_offsets`. The bug appears only when a
  **block** is placed at an orientation other than N or FW (for a block whose local bbox
  starts at `(0, 0)`).

---

## 4. Reproduction

**Reproduced.** A two-level synthetic design was run through the checked-out
`build_physical`: a 10 × 40 block at `(100, 0)` containing one 2 × 2 leaf at its local
`(0, 0)`, once per orientation. The boxes below are read from `boxes_for` (before the
die clip), so they show the transform itself:

| orient | box produced today | box DEF semantics require | error (produced − required) |
|---|---|---|---|
| N | `[100, 0, 102, 2]` | `[100, 0, 102, 2]` | none |
| S | `[98, -2, 100, 0]` | `[108, 38, 110, 40]` | both axes |
| W | `[98, 0, 100, 2]` | `[138, 0, 140, 2]` | −40 in x (= height) |
| E | `[100, -2, 102, 0]` | `[100, 8, 102, 10]` | −10 in y (= width) |
| FN | `[98, 0, 100, 2]` | `[108, 0, 110, 2]` | −10 in x (= width) |
| FS | `[100, -2, 102, 0]` | `[100, 38, 102, 40]` | −40 in y (= height) |
| FW | `[100, 0, 102, 2]` | `[100, 0, 102, 2]` | none |
| FE | `[98, -2, 100, 0]` | `[138, 8, 140, 10]` | both axes |

The FN row is the real case in miniature: the block is mirrored correctly but placed one
block width to the left. Only N and FW happen to need no translation correction.

The reproduction also matches the real design’s shape: at a die edge, the FN copy is
entirely outside the outline and the grids drop it.

---

## 5. Impact and what is not affected

**Affected (geometry-derived surfaces) for the FN block:**

- cell density, ULVT density, leakage and dynamic power (empty in this run anyway, because
  the input carries no power data);
- pin density (the 40.65 M pin points are counted from placed pins; the FN block’s pins
  are binned outside the die and dropped, apart from any pin exactly on x = 0);
- hierarchy contours and the `Density%` column;
- block outlines drawn from `boundary_polys`;
- rectangle selections and the selected-region tree.

**Not affected:**

- the DEF/LEF parse, instance counts, block references, and the hierarchy tree metrics;
- the N sibling (`gen_sp_0_u_sp`) and every other block in this design;
- leaf-level placement and pin transforms, including FN standard cells: `_pin_offsets`
  already implements the lower-left rule for them.

**Metal mode** shares the block-level walker, so a routed DEF with the same hierarchy would
also draw the FN block’s wiring at the negative-x location. The committed metal sample does
not expose it because its generator compensates for the old rule (see §6).

---

## 6. Recommended fix (not applied)

This is a record of the case; no source, sample or test file was changed. The change that
would fix it, for a future task:

1. Add a placement→translation helper next to the frame algebra, e.g. in
   [assembly.py](vlsi_viewer/assembly.py):

   ```python
   def placement_origin(orient, location, bounds):
       """t = location - min(M * bbox_corner); bounds is ((bx, by), (w, h))."""
       if bounds is None:
           return float(location[0]), float(location[1])
       (bx, by), (w, h) = bounds
       lo_x, lo_y, _hi_x, _hi_y = Frame(orient, (0.0, 0.0)).apply_rect(
           [bx], [by], [bx + w], [by + h])
       return float(location[0]) - float(lo_x[0]), float(location[1]) - float(lo_y[0])
   ```

   with a `boundary_bounds(boundary)` that returns the outline’s `((bx, by), (w, h))`.

2. Use that origin at both block-frame call sites:
   - [physical.py:519](vlsi_viewer/physical.py#L519) before pushing onto `chain`;
   - [assembly.py:208](vlsi_viewer/assembly.py#L208) before `frame.compose`.
   Keep `Frame` as `p → M·p + t`; only the translation fed into it changes.

3. Regenerate the two committed samples, because both currently write placements that
   compensate for the old rule:
   - [generate_physical.py:294](sample_data/physical/generate_physical.py#L294): the rotated
     cores go from `(495,15) / (495,495) / (15,495)` to `(285,15) / (285,285) / (15,285)`
     in [instance_info.json](sample_data/physical/instance_info.json).
   - [generate_metal.py:232](sample_data/metal/generate_metal.py#L232): drop the
     `probe`/compensation and place at `target`; [top.def:43](sample_data/metal/top.def#L43)
     changes from `(1060000,60000) / (60000,1060000) / (660000,1180000)` to
     `(660000,60000) / (60000,660000) / (660000,660000)`.

4. Add a regression of exactly this shape (two siblings, FN and N, each with a leaf at the
   same local corner) asserting both boxes and both density bins, and update the three
   physical tests that encode the old expected boxes
   ([test_physical.py:52](tests/test_physical.py#L52),
   [test_physical.py:79](tests/test_physical.py#L79),
   [test_physical.py:546](tests/test_physical.py#L546)).

Do **not** use `CoordinateProcess.calculateOriginByOrient` as-is for the helper: its `E`
branch returns `y0 + height`, where the correct term is `y0 + width` (see §7).

---

## 7. Related latent issues found during the analysis

These are observations, not part of this record’s deliverable:

1. **`calculateOriginByOrient` E branch** — [coordinateProcess.py:131](vlsi_viewer/coordinateProcess.py#L131)
   returns `(x0, y0 + height)` for `E`; the oriented bbox needs `y0 + width`.
   The helper is currently uncalled, so this has no runtime effect today, but it is the
   same table and would mislead a future caller.

2. **`_pin_offsets` docstring** — [physical.py:293](vlsi_viewer/physical.py#L293) says the
   offset is “zero for N/FW/FN”. It is zero for N and FW only; FN is `(w, 0)`. The code and
   its unit test are correct; only the prose is wrong.

3. **Metal macro blockage** — [metal.py:1623](vlsi_viewer/metal.py#L1623) translates a
   macro’s obstruction by `M_block · location + t_block`, treating the macro’s location as
   its origin image. That misses the macro’s own oriented-bbox offset, the same rule
   `_pin_offsets` applies for pins. `test_obstructions_follow_the_placement_and_its_orientation`
   ([test_metal_metric.py:326](tests/test_metal_metric.py#L326)) currently asserts the old
   result, so this is a separate change with metal capacity numbers to re-baseline.

4. **Samples compensate for the old rule** — both generators add the offset themselves, so
   they would place blocks outside the die under a fixed reader unless regenerated as in §6.
   Stale metal DBs store the old frame origins in their headers; the existing frame check
   would refuse and re-parse them, which is the safe outcome.

---

## 8. Status

Recorded for future work. No source, sample, test or configuration file was modified. The
real-design run itself was not repeated; the conclusion rests on the three snapshots, the
DEF/DIEAREA arithmetic above, the cited source paths, and the synthetic reproduction.
