# Metal density mode — as built

Implements `dev_plan/metal_density_mode.md`. The approved plan is
`dev_plan/metal_density_plan.md`; this file records what actually happened, phase by phase.

## Phase 0a — validating the parser findings against real files

The findings below were originally *inferred* from documented LEF/DEF shapes read through search
results, because `github.com`, `raw.githubusercontent.com` and the WebFetch domain check were all
blocked during planning. `raw.githubusercontent.com` turned out to be reachable from the shell, so
every finding was checked against a real file **before any fix was written**:

- **tech LEF** — Nangate45, `flow/platforms/nangate45/lef/NangateOpenCellLibrary.tech.lef` from
  OpenROAD-flow-scripts. 19 KB, 22 `LAYER` blocks.
- **routed DEF** — `test/gcd_nangate45.def` from OpenROAD. 300 KB, of which a 167 KB prefix was
  retrieved (enough to cover `COMPONENTS`, `TRACKS`, `SPECIALNETS` and most of `NETS`).

Three of the six findings were confirmed, two were **refuted**, and one significant one was new.
The refutations matter more than the confirmations: one of them would have introduced a bug.

### Confirmed 1 — `TlefParser` loses the spacing of 9 of the 10 routing layers

Running the real parser over the real tech LEF, verbatim output:

| layer | pitch | width | spacing | f = (W+S)/P |
|---|---|---|---|---|
| metal1 | 0.140 | 0.070 | **0.065** | 0.964 |
| metal2 | 0.190 | 0.070 | **0.000** | 0.368 |
| metal3 | 0.140 | 0.070 | **0.000** | 0.500 |
| metal4–metal10 | 0.280–1.600 | 0.140–0.800 | **0.000** | 0.500 |

Only `metal1` carries a plain `SPACING 0.065 ;`. Every other routing layer uses a
`SPACINGTABLE` block, and the parser has no reader for it, so `spacing` stays at its `0.0`
initialiser. The predicted failure mode was "the last of several `SPACING` clauses wins"; the
real one is worse and simpler — **there is no `SPACING` clause at all on those layers**, so the
value is simply absent.

Consequence for the metric: keep-out inflation is `s/2 = 0`, so `D_L` degenerates to raw metal
area instead of track-pitch area, and `f` comes out 0.37–0.50 instead of ~1.0. The map would be
systematically about half the correct value on nine layers and *inconsistent* with `metal1`,
which would make the layer checkboxes actively misleading. This is the single most important fix
in phase 0b.

### Confirmed 2 — 22 `LAYER` blocks, only 10 routing

`poly`, `active`, `OVERLAP` and the nine `via*` cut layers are all returned by
`TlefParser.layers`. Filtering on `type == 'ROUTING'` is mandatory, as planned.

### Confirmed 3 — `f_L` genuinely varies, so the pitch normalisation is load-bearing

With the correct spacings, `f` is 1.0 for most Nangate45 layers — but **not all**: `metal1` is
0.964 and `metal2` is 0.737 (`W+S = 0.14` against `P = 0.19`). So the `f_L = (W+S)/P` capacity
normalisation is not a theoretical nicety; on the real library it changes `metal2`'s reading by
36 %. Without it, a fully-utilised `metal2` would read 0.74.

### Refuted 1 — "`routeWidth 0` means use the layer default" is WRONG, and would have been a bug

Real special wiring:

```
NEW metal3 0 + SHAPE STRIPE ( 62280 61600 ) via3_4_960_340_1_3_320_320
NEW metal2 0 + SHAPE STRIPE ( 62280 61600 ) via2_3_960_340_1_3_320_320
```

Width `0` here marks a **via placement** — a single point plus a via name, with no wire at all.
Zero area is the correct contribution. The planned "fall back to the layer's LEF width" would
have manufactured a phantom wire at *every* PG via, i.e. invented metal that does not exist, in
the most visually prominent part of the map.

The correct rule is the opposite of what was planned: **a shape with `routeWidth 0` contributes
no wire area** and is counted as a via. 66 such shapes appear in the truncated real DEF.

### Refuted 2 — glued `*` coordinates do not appear in real output

`(1760*)` / `(*703600)` (from a tutorial, not from tool output) do **not** occur in this DEF.
Real output uses the spaced forms, which the current regex already handles:

```
+ ROUTED metal3 ( 52630 55580 ) ( 53770 * )
NEW metal2 ( 52630 55580 ) ( * 57540 )
```

Counts: `\(\*` → 0, `[0-9]\*\)` → 0. So the glued-form fix is **defensive robustness, not a
confirmed bug**, and is downgraded accordingly — still worth the two extra alternatives and a
test, but it must not be described as a real-world defect. The `SPACINGTABLE` width clobbering
stays real but *latent*: it happens, but Nangate45 writes `WIDTH` **after** the table, so the
correct value overwrites the damage. The repo's own syntax reference lists `WIDTH` **before**
`SPACINGTABLE` — the spec-legal order — under which the clobber sticks. Order-dependent, fixable
in the same pass.

### New — half of all wire segments are via points, and the end-extension would corrupt them

Measured on the real DEF:

| form | count |
|---|---|
| `NEW` forms total | 1849 |
| two or more points (a real segment) | 795 |
| one point (a via placement) | 1054 |
| `DefWire` objects built from them | 2068 |
| **zero-length `DefWire` (via points)** | **1054 — 51 %** |

Two consequences, both significant:

- **Correctness.** Regular DEF wiring defaults to a half-width extension at each end. Applied to
  a zero-length segment that produces a phantom `w x w` square at every via — thousands of them.
  A zero-length segment must therefore contribute **no** area and take no extension.
- **Performance.** Half the parsed segments are vias. Dropping them at parse time halves `N`
  before rasterisation — a bigger and cheaper win than anything in the reduction list, and it
  applies to every real DEF, not just large ones.

### Also verified as already correct

- `TRACKS X 190 DO 172 STEP 380 LAYER metal1 ;` parses to
  `metal1 / X / offset 190 / step 380 / mask 0 / num_tracks 172` — masked and unmasked forms both
  fine, and `num_tracks` is captured (the earlier `TRACKS` fix holds).
- `+ SHAPE` after `routeWidth` (`metal4 960 + SHAPE STRIPE`, `metal1 340 + SHAPE FOLLOWPIN`) is
  matched — `SHAPE_OR_MASK` appears in both positions in `re_special_wiring_form`.
- Via names as bare identifiers (`via1_7`, `via2_5`) are captured. `NOT_KEYWORD`'s uppercase
  `VIA` cannot match lowercase `via1_7`, and `\b` fails mid-identifier anyway.
- End-to-end the real DEF parses cleanly in **0.7 s**: 734 components, 20 tracks, 221 nets,
  2068 `DefWire`, 90 `DefSWire`.

### One thing the real file settles for the sample data

The real die is `65480 x 65480` DBU at `UNITS DISTANCE MICRONS 2000` — **32.7 µm square**. At the
10 µm default grid that is a 4x4 map, which is useless for demonstrating the feature. Confirms the
plan's decision to generate a ~2 mm die rather than reuse an existing test DEF.

### Phase 0a conclusion

Three confirmed (one severe, one mandatory filter, one vindicating a design choice), two refuted
(one of which would have been a bug), one new and worth ~2x on performance. The refutations are
the return on doing this check first: both were plausible readings of the syntax, and only
contact with real output distinguished them.

## Phase 0b (part 1) — tech LEF robustness

`TlefParser`'s layer scan was a flat `elif` chain over the stanza's lines, and `LefLayer` had no
way to distinguish a table row from a layer statement. Both changed.

**The stanza is now a nested block.** `__parseLayer` consumes a `SPACINGTABLE … ;` body as a
unit, so its `WIDTH <breakpoint> <spacings>…` rows can no longer be read as the layer's default
width. Only the numbers after the first on a `WIDTH` row are collected, because the first is the
row's width breakpoint; `PARALLELRUNLENGTH` / `TWOWIDTHS` / `INFLUENCE` lines are breakpoints
throughout and are ignored — taking the minimum over *all* numbers in a table returns 0, which
was the trap.

**Spacing is resolved after the stanza, not line by line.** `widths`, `spacings` and
`table_spacings` are collected, then:

| value | resolution |
|---|---|
| `width` | first `WIDTH`, else `MINWIDTH`, else 0.0 (honestly unknown) |
| `spacing` | the unqualified `SPACING x ;`, else `min(spacings)`, else `min(table_spacings)`, else 0.0 |

**Other robustness changes**, each from a shape real LEFs contain:

| change | why |
|---|---|
| `LAYER_END = (?=\s|;\|$)` on the value regexes | `DIRECTION VERTICAL;` with no space before the semicolon used to parse as empty, which mislabels the H/V grouping |
| `TYPE` captured as `[A-Za-z_]\w*` | `TYPE OVERLAP;` used to capture `OVERLAP;` including the semicolon |
| `FLOAT` accepts an exponent | `PITCH 3.4e-1` and similar machine-written values |
| `LefLayer.lef58_type` | `PROPERTY LEF58_TYPE "TYPE NWELL ;"` wrote into the same field as the base `TYPE`, so a routing layer carrying one lost `'ROUTING'` and dropped out of every routing filter |
| `width` initialised `0.0`, not `0` | it is a distance; the int was an accident |
| `__skipTo` helper | the four block-skipping loops were the same loop four times |

**Verified on the real Nangate45 tech LEF.** Before: 9 of 10 routing layers had `spacing == 0.0`.
After: every routing layer resolves both width and spacing, and `f = (W+S)/P` lands where it
should — 1.000 for `metal3`–`metal10`, 0.964 for `metal1`, and **0.737 for `metal2`**, which is
the layer that vindicates the pitch normalisation: at `W+S = 0.14` against `P = 0.19`, a
fully-utilised `metal2` would otherwise read 0.74.

**Tests: `tests/test_tech_lef.py`, 14 cases.** The Nangate45 `metal2` stanza is reproduced
verbatim, including the trailing spaces the tool wrote. Against the original code **10 of the 14
fail**; against the fixed code all 14 pass — checked by reverting `parsers/LEF/` to HEAD and
re-running, so the tests are known to pin the bugs rather than merely describe them.

`python -m pytest -q` → **182 passed** (168 before).

Note for the record: the *width* clobbering was order-dependent and did not bite on Nangate45,
which writes `WIDTH` after the table and so repaired it. The spec-legal order (`WIDTH` before
`SPACINGTABLE`, as `LEF_DEF_syntax reference.md` lists it) does bite, and both orders are now
covered by a parametrised test.

## Phase 0b (part 2) — DEF: non-default rules, net class, polygons

Three additions, all needed by the metric and none of them previously available.

**`NONDEFAULTRULES` is now parsed** (`defNdr.py`, `DefParser.__extractNdrRules`). A net's
`+ NONDEFAULTRULE name` used to be a string with nothing behind it, so a 2W2S clock rule read as
the 1W1S default — roughly halving the metal a clock region appeared to use. A rule is one
statement (one `;` ends it; the `+ LAYER` clauses have no terminator of their own) split on its
clauses into `DefNdrLayer(width, spacing, diagwidth, wireext)` per layer. Values stay in
database units, matching `DefTrack`. Nothing in the section may raise: an unreadable rule is
reported and kept as an empty rule rather than taking the parse down with it — the same lesson
`__extractTracks` learned.

**Nets now record which section they came from** (`DefNet.is_special`) **and their `+ USE`**
(`DefNet.use`). Both were needed because `NETS` and `SPECIALNETS` share one table and nothing
else in a statement distinguishes them, so there was no way to separate signal metal from power
metal — a power stripe would read as a routing hotspot. `USE` is read from the whole statement,
since the grammar allows it either side of the wiring.

**`+ POLYGON` shapes are captured whole** (`defSPolygon.py`). The per-edge `DefSWire` objects the
parser emits cannot be reassembled into the ring: they carry no polygon id and the closing edge
is never emitted (a 4-vertex ring yields 3 edges). The filled shape's *area* is unrecoverable
from them, so it is captured where the vertex list still exists. The edges are still emitted, so
the behaviour existing consumers and tests depend on is unchanged.

**Two smaller fixes:**

| change | why |
|---|---|
| `re_glued_star` splits `(300*)` / `(*400)` before tokenising | the glued form occurs in real DEF; splitting the text keeps `WIRE_POINT`'s separator strict, whereas relaxing it to `\s*` would let a malformed `(1234)` backtrack into x=123, y=4 |
| `__extractNets` searches the whole statement for `+ NONDEFAULTRULE` | the header/wiring split cuts at the first non-wiring clause, so a rule reference placed *after* the wiring belonged to neither part and was dropped silently |

**Tests: `tests/test_def_ndr.py` (13 cases) plus 9 added to `tests/test_def_nets.py`.** The NDR
fixtures use the real statement shape, with `+ LAYER` clauses that have no terminator.

**Verified on the real routed DEF**, unchanged where it should be and newly informative where it
should be: 734 components, 20 tracks, 221 nets, 2068 `DefWire`, 90 `DefSWire`, parse time 0.61 s.
Now additionally — 2 special nets with `USE` of `GROUND`/`POWER` and 219 signal nets with
`SIGNAL`; 1054 zero-length via points (**50 %** of all `DefWire`); and `*` reuse still resolving
correctly through the glue split, which the real file exercises directly
(`( 52630 55580 ) ( 53770 * )` → `(52630, 55580) → (53770, 55580)`).

`python -m pytest -q` → **204 passed** (182 after part 1, 168 before phase 0b).

Phase 0b is complete. The parsers now expose everything the metric needs, and the two
"confirmed but latent" findings from phase 0a are fixed in the same pass.

## Phase 1 — the rasteriser (`vlsi_viewer/raster.py`)

### The planned algorithm was replaced, on measured grounds

The plan specified a four-class difference-array decomposition: `O(1)` per rectangle
regardless of how many bins it spans, plus one `cumsum` per layer. Working the operation
counts out before writing it showed that scheme needs 12 to 36 scatter writes per rectangle
(the four-class split, each class a constant-add range) against the 2 to 6 bin pieces a
straightforward "split at bin boundaries" needs *for routing geometry specifically* - a
segment is about one gcell long, so it touches a handful of bins. The difference array also
pays a full `cumsum` over the grid per layer, which the piece approach never pays.

So the implementation splits each rectangle at bin boundaries into pieces that fall inside
exactly one bin and folds them with one weighted `np.bincount` per window. Cost is
`O(sum of bins touched)`, exact, and with no per-shape allocation - which was the actual
defect in the old physical-mode rasteriser.

The difference array would still win on input with many die-spanning shapes. There are none
in routing (a power stripe touches ~200 bins, and there are tens of them), so this is not a
trade against expected data - but it is a real characteristic and it is recorded here rather
than buried: a design that was mostly full-die shapes would be better off with the planned
scheme.

Non-rectangular shapes take a second path. `add_segment` builds the **exact** Minkowski sum
of the segment with a square via `LineString.buffer(cap_style=square)` and rasterises it
with per-bin `shapely` intersection. That is far too slow for a whole design, but diagonals
are a small minority, and a bounding box - the obvious shortcut - over-counts a 10 um
diagonal by roughly 25x.

### A real bug the property test found

`test_matches_brute_force_on_random_rectangles` runs 3000 random rectangles (fat, thin, long,
negative, overhanging) through both the vectorised path and an independent loop-based
implementation of the same definition, and compares. It failed on first run: **46 of 522 bins
differed**, the worst by 415 um².

Cause: the grid rounds up, so its last column and row overhang the die - a 200 um die at a
7 um grid ends at 203 um. Shapes were being clipped to the *grid's span* rather than to the
*extent*, so a wire reaching the die edge was counted in 3 um of overhang that is not design
area. Every edge cell was inflated. Fixed, and pinned by
`test_shape_past_the_die_edge_is_clipped_to_the_die_not_the_grid`.

This is exactly the class of error the plan predicted for this module - a subtly wrong
vectorised split that still produces a plausible map - and it was caught before anything was
built on top of it.

### Performance: measured, not estimated

Synthetic routing geometry (80/20 horizontal/vertical, 2-40 um segments, one inflated
rectangle per segment), `tracemalloc` peak:

| segments | grid | time | per segment | peak |
|---|---|---|---|---|
| 8 x 10^5 (10^7 total) | 200 x 200 | 0.37 s | 463 ns | 92 MB |
| 2 x 10^6 (2.4 x 10^7 total) | 200 x 200 | 0.90 s | 449 ns | 111 MB |
| 8 x 10^6 (10^8 total) | 2000 x 2000 | 4.21 s | 526 ns | 270 MB |
| 2 x 10^6 | 1000 x 1000 (2 um) | 2.90 s | 1450 ns | 132 MB |

**Two fixes came out of measuring, and the first was the bigger one.** A walk over the shapes
to find chunk boundaries was a Python loop over millions of elements - seconds by itself,
giving back most of what the module exists to save; it is now a `cumsum`/`searchsorted`. And
peak memory was **independent of the chunk size** (1448 MB at every setting), which located
the real cost: not the piece expansion, but ~20 working arrays the length of the *input*.
Blocking the input took peak from 1448 MB to 270 MB with no change in time.

Headline: **~500 ns per segment**, so 10^7 segments rasterise in about 5 s and 10^8 in about
50 s, with memory bounded rather than proportional to the design. Grid resolution is the
dominant knob - a 2 um grid triples the per-segment cost, because shapes touch more bins.

That is rasterisation only. Parsing is the binding constraint at these sizes (phase 0a), and
phase 5 will produce the end-to-end numbers.

**Tests: `tests/test_raster.py`, 28 cases** - hand-computed single/multi-bin cases, a 300-bin
thin rectangle, edge-clipping, reversed corners, degenerate and out-of-grid shapes,
sum-not-union, chunk-size invariance, weights, dtype, and the exact-area checks for diagonal
segments and convex/concave polygons.

`python -m pytest -q` → **232 passed** (204 after phase 0b).

### Correction: the tempting optimisation was 2x slower

Profiling attributed 1.18 s of the 4.2 s run to 1220 `np.repeat` calls, so the piece expansion
was rewritten to group shapes by their piece shape `(nx, ny)` and broadcast a
`(shapes, pieces)` grid instead - removing nine of the ten repeats per window. It measured
**8.8 s, twice as slow**. The grouping needs a column-wise `np.unique` over every shape to find
the groups, and the 2-D temporaries are far less cache-friendly than the flat passes they
replaced. `np.repeat`'s `tottime` was a misleading signal on its own.

Reverted, keeping only two genuine wins found in the same pass: `np.repeat(spans_x, ...)` was
being computed twice, and the piece-to-shape index was built even when the caller passed no
weights. Result **3.95 s / 494 ns per segment**, marginally better than the 4.21 s it started
at. The dead-end is recorded here because the faster-looking version is the tempting one.

Also measured, on the assumption the production machine has memory to spare: raising the block
and chunk budgets does **nothing** for speed - 4.26 s at 2^18/2^20 against 4.35 s at 2^22/2^22,
while peak memory goes from 142 MB to 867 MB. The defaults stay small. Whatever the speed
ceiling is, it is not allocation overhead.

That leaves process-level parallelism as the remaining lever, and it belongs after the
end-to-end benchmark (phase 5) rather than before: phase 0a found that **parsing, not
rasterising, is the binding constraint** at these sizes, so optimising the rasteriser further
before measuring the whole path would be optimising the wrong stage. Recorded as the next thing
to do if the end-to-end numbers demand it.

## Phase 2 — the streaming conversion (`parsers/routing.py`)

`convert` is the wrong home for this: its contract is the viewer's JSON structures,
string-keyed and round-trippable, while routing geometry has no JSON form and is far too
large to hold. New module, one output contract.

**Nothing retains geometry.** A design can carry 10^8 wire segments, which is gigabytes as
objects, so the DEF parser gained a `sink`: each net is handed over as soon as it is parsed
and then dropped. Peak memory is one batch, not one design. The parser also counts sections
as their headers go past (`n_nets`, `declared_nets`), which is the only way to compare
declared against parsed once the nets are being discarded - and it works at any file size,
unlike re-reading the head.

The sink receives the database unit and the rule table as well as the net, because it is
called *during* construction and the caller has not yet been given the parser it would have
to ask for them. Scaling the rules to microns makes a *copy*, not an in-place edit: the
stream is holding the parser's originals and divides by the unit itself, so scaling those in
place would apply the conversion twice.

**Vias are omitted**, per your instruction. A via is a routing point with no extent - regular
wiring builds a zero-length `DefWire`, special wiring writes `routeWidth 0` - and both are
skipped rather than substituted with the layer's default width, which would invent a wire at
every via, or extended by the half-width end rule, which would turn each into a phantom
square. Measured on the real DEF: **1120 via points against 1038 real wire rectangles**, so
more than half the parsed geometry is vias.

**Jogs are dropped by direction, not by length.** Your requirement was to ignore short jogs
across a layer's preferred direction - a horizontal blip on a vertical layer used to shift
track. A blanket length threshold was my first reading and it was wrong: it dropped **83**
segments of a real DEF, including genuine short stubs running *along* their layer. The rule is
now "non-preferred direction **and** shorter than one track pitch", which drops **4** segments
covering 0.03 % of the area. `min_segment=0` keeps every jog.

### A bug the tests caught in the conversion

`+ RECT` special shapes have **no width** - the reference makes it optional and the parser
leaves it `None` - so the check meant for `routeWidth 0` was silently discarding every one of
them. On a power grid that is the entire PG mesh, gone with no error. The RECT branch now
comes before the width check, and `+ POLYGON` edges are skipped explicitly (their filled area
is taken from `net.polygons`, where the whole ring exists) rather than being counted as vias.

**Tests: `tests/test_routing.py`, 23 cases** - tech LEF filtering and ordering, the spacing
fallback, the keep-out geometry against hand arithmetic, single micron conversion, both via
forms omitted, layer width vs non-default rule vs stated `routeWidth`, per-field rule
override, jog vs short stub, scope from `USE` and from section, diagonals and polygons routed
to their own paths, unknown layers counted, the streaming/accumulating equivalence, that a
sink leaves no nets behind, and the count-mismatch warning.

`python -m pytest -q` → **255 passed** (232 after phase 1).

## Phase 3 — assembly (`vlsi_viewer/assembly.py`)

`find_single_top` reports zero or several roots with the same message shape the physical path
uses, so the CLI's existing error-and-exit already covers it. `HierarchyAssembler.walk` gives
each block its global `Frame`, recursing through instances whose `cell_name` names another
block, and raises on a cycle.

`physical.build_physical` is deliberately left alone - its frame walk is a closure over a dozen
side-effect lists with twenty-odd tests pinning it - so the metal path gets its own walker.

### A real bug, found by an exhaustive test

`Frame.compose` was written first with `Orient.mergeOrient`, which combines mirrors by XOR-ing
global X and Y flags. That is wrong whenever the **parent is rotated and the child is
mirrored**: the child's mirror axis rotates with the parent. The 64-pair test (every outer
orientation against every inner) failed on exactly those pairs - all four rotated parents
against all four mirrored children - and none of the rotation-only or mirror-only pairs.

Rewritten to compose the actual 2x2 matrices, which is exact by construction:
`M = M_parent M_child`, `t = M_parent t_child + t_parent`. Every pair now matches
`CoordinateProcess.dbTransform` applied twice by hand. This would have shown up as sub-block
wiring mirrored against its parent in exactly the four-orientation layout the sample data uses.

**Tests: `tests/test_metal_assembly.py`, 91 cases** - the root rules, parity with the engine for
all eight orientations, rectangles staying rectangles, the 64 composition pairs, nesting two
levels deep checked by hand, a block used twice being visited twice, cycles, and missing cells.

## Phase 4 — the metric (`vlsi_viewer/metal.py`)

`MetalData` composes maps on demand, because a metal map has state (which layers, which scope)
that a plain array lookup cannot carry - but it duck-types `extent`, `grid_size`, `rows`,
`cols`, `boundary_polys` and `heat(kind)`, so the existing `LayoutView` drives it unchanged.

Capacity is `routable x f_L` with `f_L = (W+S)/P`; see the metric section above for why.
Macros subtract capacity only below `macro_block_layers`. A group is `sum(D)/sum(C)`, never a
sum. `heat` never returns NaN, because `grid_to_image` has no NaN handling and a NaN paints
garbage - a cell with no capacity reads 0.0.

`cell_detail(ix, iy, kind)` returns the per-layer `D`, `C`, `U`, the pitch factor, and the
group's `sum(D)/sum(C)`, which is what the GUI's hover readout shows so a user can check the
colour against the arithmetic.

### Two bugs the tests caught

**The default scope drew an empty map.** `_consumed` looked the grids up with the routing
module's integer `SIGNAL`/`POWER` constants, but `_GridSink` keys them by the scope *strings*.
Signal and power worked; `all` - the default - matched nothing and silently returned nothing.
Found by asserting `all == signal + power` rather than just that the numbers looked plausible.

**Macros contributed no capacity at all.** `load_cell_info` leaves a RangeIndex with the name
in a column; the `.set_index("cell_name")` re-keying lives in
`physical._load_blocks_and_cells`, not in the loader, so every macro lookup returned None and
the macro quietly vanished from the capacity. Recorded in a helper with that reasoning, because
the failure mode is silence.

**Tests: `tests/test_metal_metric.py`, 22 cases** - hand arithmetic for one wire and for thirty,
the clip, the pitch factor on a layer whose pitch exceeds its rules, a fully-utilised layer
reading exactly 1.0, macro capacity above and below the block limit, the weighted group
formula shown to differ from the plain mean, canonical group keys, scope separation with
`all == signal + power`, no NaN anywhere, and the error paths.

One correction to the plan's worked example: it computed an 8 um wire's keep-out as
`(8 + 0.1) x 0.2`, omitting the end extension. The reference gives regular wiring a default
extension of half the wire width at each end and the implementation applies it, so the figure
is `(8 + 0.2) x 0.2`. The plan's 0.486 for thirty wires is therefore 0.492.

`python -m pytest -q` → **368 passed** (255 after phase 2).

## Phase 6 — the sample (`sample_data/metal/`)

A 1P12M stack and a hierarchical routed design, generated by `generate_metal.py`:

| file | what it holds |
|---|---|
| `tech.lef` | 12 routing layers, M1/M3/M5/M7/M9/M11 horizontal, plus cut and overlap layers |
| `cells.lef` | 16 macros including a `CLASS BLOCK` SRAM and FILL/TAP/DCAP |
| `sub.def` | `SUB`: 13.5k placed cells, local TRACKS, 18k signal nets, M1 followpins |
| `top.def` | `TOP`: four `SUB` instances at N/W/FS/E, NONDEFAULTRULES, PG stripes and a `+ POLYGON` ring |
| `orphan.def` | an unrelated design, for the two-root error path |

**The tech LEF is deliberately awkward, one shape per layer**, each corresponding to a bug
found in the real Nangate45 file or the reference: M2 carries four qualified `SPACING` clauses
with the widest last (last-match-wins); M6 carries a `SPACINGTABLE PARALLELRUNLENGTH` block
(rows read as the layer's `WIDTH`); M7 has `MINWIDTH` and no `WIDTH`; M8 writes
`DIRECTION VERTICAL;` with no space before the semicolon. M2's pitch is also deliberately
larger than its rules (0.14 against 0.19) so the pitch normalisation is exercised by the
committed sample, not only by a unit test.

The die was sized **down** rather than the net count up. At 12k nets over a 500x400 um block
the busiest cell reached only 0.18 - a map with no congestion on it - because that is a tenth
of the routing a real block that size carries. Shrinking the block to 260x200 um gives a peak
of 0.925 with 817 distinct values, which looks like a design. Inflating the net count to match
an unrealistic area would only have made a larger file that still did not.

Two generator bugs worth recording, both caught by checks rather than by looking:

- **Colliding component names.** Naming cells `r{row}_{int(x)}` maps a whole site's worth of
  positions to one name, and the parser merges duplicates. `convert`'s declared-versus-parsed
  warning reported 9659 declared against 3774 parsed, which is what pointed at it.
- **The top level held the leaves.** Writing all the cell placements into `top.def` meant it
  never referenced `SUB`, so the two DEFs were two designs and `find_single_top` correctly
  refused them. The leaves now live in `sub.def` and reach global coordinates through four
  different rotations, which is what makes frame composition for *wires* something the
  committed sample actually exercises.

## Phase 5 — measured performance

Run through the generator's `--stress` mode: synthetic DEFs of two-segment nets over a
20 x 20 mm die at a 10 um grid (a 2000 x 2000 grid).

| | 100k nets | 200k nets |
|---|---|---|
| DEF size | ~8 MB | 16.1 MB |
| write | 0.30 s | 3.0 s |
| **build total** | **6.7 s** | ~11.5 s |
| peak RSS | 385 MB | ~700 MB |

Split by stage at 200k nets:

| stage | time | per shape |
|---|---|---|
| parse + convert | 4.37 s | 21.9 us/net |
| rasterise | 0.12 s | 602 ns/shape |

**Parsing is 97 % of the run.** The rasteriser is 36x faster than the parser, which confirms
what phase 0a predicted from the real file - and it means the effort spent tuning the
rasteriser (the reverted broadcast rewrite included) was effort spent on 3 % of the runtime.
That is the return on measuring before optimising further.

Extrapolating honestly: 10^6 nets is ~22 s, 10^7 is ~4 minutes, and 10^8 is upwards of half an
hour and out of reach without replacing the DEF parser with something compiled. The viewer is
comfortable to about 10^6 wire segments and usable to about 10^7, which covers a block or a
small chip rather than a full-chip flat DEF.

### A 51x pathology the benchmark found

The first stress run took **345 seconds** for 100k nets - 3.46 ms per net, against 67 us
afterwards. The cause was `Bins.add_polygon`, which intersects one bin at a time with
`shapely`, and which `build_metal` was using to rasterise the **die outline**. At a
2000 x 2000 grid that is four million intersections, and it dominated everything.

An axis-aligned rectangle now takes the vectorised path in `add_polygon` before the per-bin
loop. That is not a tidy-up: a die outline and a power ring are rectangles essentially always,
so the slow path was the *common* path. 345 s -> 6.7 s.

## Phase 7 — the CLI

`vlsi_viewer metal --def ... --lef ... --tech-lef ...`, with `--grid-size` (10 um),
`--macro-block-layers` (4), `--min-segment-length` and `--top`. **No `--compare_*`, no
`--physical_mode`, no `--contour_gap`, no `--out`** - a routing map has nothing to compare
against and no instance boxes to contour, so the capability is expressed by the flag not
existing, which is how the other flows do it too. A test asserts each of those flags is
rejected, so the scope cannot quietly widen.

Metal mode gets its own path in `main` rather than a branch in `resolve_inputs`: it consumes
neither the JSON structures nor the metric tree, and `resolve_inputs` returns sources for a
pipeline it does not use.

`quickstart.py` gained a `metal` shortcut over the sample. Unlike the other flows it passes
**two** DEFs, because a hierarchy normally is two: the top one places the sub-block, and only
together do they describe a design.

### A deviation, recorded

The grids are built **before** the window exists, with progress logged to the terminal. For
the sizes this is comfortable with - about 10^6 wire segments, a few seconds - that is
invisible. A full-chip flat DEF would spend minutes with no window on screen, and moving the
build behind a visible window with a progress bar is the first thing to do if that becomes the
normal case. This is the same synchronous-startup shape that the physical mode's performance
review identified as its "stuck GUI at launch", so it is a deliberate acceptance rather than an
oversight, and it is recorded here and in the README.

## Phase 8 — the GUI

`LayoutView` was made source-agnostic rather than forked. It already funnelled everything
through `heat(kind)`, so what it needed was: a map list from the source (`kinds()`) instead of
the hard-coded `HEAT_TYPES`, a `contour_enabled` flag, and an `external_controls` option that
leaves the min/max and Fit widgets unparented so the panel can adopt them. The widgets stay
attributes of the view, so nothing that pokes at `layer.min_spin` has to care.

Metal mode builds **no hierarchy toolbar at all** - no search box, match mode, Find,
min-instances or macros toggle - and no tree, no compare view, no `Density%` column. A search
box that filters a tree nobody can see is worse than no search box.

`MetalPanel` holds the layer checkboxes (bottom to top, each with its mean utilisation), the
net-class selector, All H / All V / None, and the **cell detail** box: on hover it shows the
cell's coordinates, `D`, `C` and `U` per selected layer, and the group's `sum(D)/sum(C)` with
the capacity policy in force. That readout is why the metric is worth having in a GUI - it
makes the colour checkable rather than something to take on trust.

The ramp is fixed at `[0, 1]` for metal maps rather than autoscaled to the data, because 1.0
meaning "every track consumed" is the whole point and autoscaling would throw the calibration
away.

**Tests: `tests/test_metal_cli.py` (14) and `tests/test_metal_gui.py` (20)** - the flag surface
including each absent flag, the pre-window error paths (unreadable input, two unrelated DEFs),
and then the GUI's consistency rather than its widgets: unticking a layer changes the map, All
H selects exactly the horizontal layers, the scope combo moves the numbers, and the cell
readout equals the pixel that was drawn.

`python -m pytest -q` → **408 passed** (368 after phase 4).

## Phase 9 — the panel, after the first look at it on screen

The first screenshot of the mode showed a large blank area to the right of the map, one
sub-block outline in the wrong corner, and a readout with its numbers cut off. Three separate
causes, and the blank area turned out to be measurable rather than a matter of taste.

### The blank area was one size hint

`QSplitter` reported `sizes() == [554, 942]` for a panel whose width was *fixed* at 230, so 712
px sat dead inside the splitter. The 942 was a size hint, and one widget produced it: the
min/max `QDoubleSpinBox`es are ranged to `1e12` so the physical mode's power values fit, and a
spin box sizes itself for the longest string its range can hold - 331 px each for three-digit
values. A hint is not free: it became the panel's minimum width, which put the *window's* floor
at ~1342 px and squeezed the spinners' arrows onto their own digits.

`setMaximumWidth(96)` alone would not have done it - a widget's minimum is what a layout
honours, and `QSizePolicy.Ignored` is the part that says "the width is the layout's business,
not the hint's". Both modes share those spin boxes, so the fix is in `LayoutView` and physical
mode gets it too. Measured after: splitter `[1104, 292]`, panel 292, and the whole rest of the
window to the map.

### The stray rectangle was a missing frame

`_boundary_polys` returned each block's outline untransformed, where `physical.py` maps them
through the block's frame. A block placed four times therefore drew one rectangle at the origin.
It now walks the tree and transforms vertex by vertex - not by bounding box, because a quarter
turn has to swap the outline's extents. Four outlines appear in their four quadrants, and the
die is drawn a shade brighter than the sub-blocks, since on a dark map "outside the die" and
"inside with no metal" are the same colour.

Walking the tree instead of iterating `blocks` introduced a `KeyError` on the first run: the
walk visits every *instance*, including leaf cells that are not blocks and have no DEF of their
own. `_macro_area` had been getting away with the same traversal only because it looks cell
names up in the LEF rather than in `blocks`.

### The readout was clipped by arithmetic, not by the layout

The panel is 292 px and the sample's rows read `M2  D 17.004  C 73.684  U 0.23` - the `D` and
`C` letters alone cost three characters twelve times over. The heading row now carries them
once, the numbers are three significant figures, and the header and peak lines are `Ignored` so
that a live readout cannot ratchet the splitter's minimum wider with each hover. Same trap as
the spin boxes, one widget class over: a `QLabel`'s minimum width is the width of the string it
is currently holding.

The detail rows are height-capped and scroll, so twelve of them can never squeeze out the twelve
checkboxes above them, which are the control that matters.

### The map was dark because the ramp is calibrated

Peak utilisation is 0.463 while typical cells are ~0.03, and the INNOVUS ramp's first third
spans 0…0.33, so nearly everything landed on the same navy. The fixed `[0, 1]` range is
deliberate - 1.0 means every track consumed, and autoscaling to the data would throw that away -
so it stays the default and **Auto** fits the ramp to the map's own 99.5th percentile instead,
with the true peak still reported beside it. Not the maximum: one saturated power-ring corner
would flatten everything else.

The readout gained the two things that were computable but unstated: the bottleneck layer is
bolded, and the horizontal and vertical maxima are reported apart, because a cell whose
horizontal layers are full is still routable upward.

### A trap worth recording: the offscreen font lies

`QT_QPA_PLATFORM=offscreen` reports **17 px per character** where a real Windows UI is ~9, so
absolute pixel widths measured in tests do not transfer - the same string measured 425 px
offscreen and ~150 px on screen. Worse, `font-size` in a stylesheet has no effect there and
`QFontInfo.family()` comes back empty, so the metrics cannot be trusted at all. The GUI tests
therefore assert *relationships* (the panel's minimum does not grow when the readout fills in,
the detail box is the one with a capped height) rather than pixel counts, and the widths that
mattered were measured with an explicit 9 pt font set on the application.

**Tests: `tests/test_metal_gui.py` (33) and `tests/test_metal_metric.py` (24)** - the width
policy, `Auto`, the bottleneck highlight, the direction maxima, and the transformed boundaries
(including a rotated placement, which a bounding-box shortcut would pass and vertex-by-vertex
transformation would not).

`python -m pytest -q` → **428 passed**.

## Phase 10 — the layout after living with it

The second look at the running window produced two requests and one defect.

### A regression from phase 9, and its cause was my own fix

The Min/Max spin boxes were rendering as **nothing**. Phase 9 stopped a `QDoubleSpinBox` from
claiming 331 px of panel width by adding `QSizePolicy.Ignored` alongside `setMaximumWidth(96)`.
Measured, side by side, with the same 1e12 range: `Preferred` + `setMaximumWidth` lays a box out
at 96 px, `Ignored` + `setMaximumWidth` lays it out at **zero**. `QWidgetItem::sizeHint()`
returns no width at all for an `Ignored` horizontal policy, and every row these boxes sit in ends
with `addStretch(1)` — so the stretch took the row and the boxes got what was left, which was
nothing. `setMaximumWidth` alone was always sufficient: a QBoxLayout and a QToolBar both bound
the slot they give a widget by its maximum, so the 331 px hint never reaches the layout and never
becomes the window's minimum either.

Phase 9's tests could not see this. They set spin box values programmatically, which works
perfectly at zero width, so the suite stayed green over two invisible widgets — and physical
mode, whose controls row is the same HBox with the same stretch, was broken the same way without
anyone having looked at it. The new test shows the window and asserts `width() > 0`.

### The two tables were fighting over one column

Net class, value range, twelve layer rows and twelve detail rows all lived in the right-hand
column. Twelve plus twelve does not fit in 800 px, so the detail won and the layer list went
behind a scrollbar at M5. They are now three panes — **cell detail | map | layers** — with
stretch 0:1:0, so the side panes keep their width and the map takes every spare pixel
(measured: `[250, 731, 411]` on a 1400 px window, splitter minimum ~630 px).

That meant splitting `MetalPanel` in two, and splitting a widget silently drops the internal
calls that made one half follow the other: `_update_details` used to re-render the hovered cell
whenever the selection changed. The panel now emits `selection_changed` and the window connects
it to the readout's `refresh`, so a layer tick still re-renders a cursor that has not moved —
which is the whole point of the readout, since numbers describing a map that is no longer on
screen are worse than no numbers.

The value range moved to a toolbar of its own, which is also where a spin box costs nothing:
the panel's width is now spent entirely on the layer table.

### The layer table grew the three numbers that explain the fourth

Capacity is `routable area × (W + S) / P`, so each row now shows the layer's own width, spacing
and pitch from the tech LEF — formatted with `:g`, because three significant figures would print
Nangate45's real 0.065 µm width as `0.06`. The factor `f` lives in the row's tooltip: it reads
`1.000` on most layers, so a column for it would cost width on every row to say "nothing to
see", and on a layer where it is not 1.0 it is the answer to a question the row cannot otherwise
answer. `MetalData._pitch_factor` became public as `pitch_factor` for that tooltip, so the GUI
asks the metric rather than re-deriving the formula and drifting from the map.

### What a review of the design turned up

A second pass over the plan, before the code was written, found four things worth fixing:

**A pane is sized from its `sizeHint()`, and a hint can beat a maximum.** The layer table's hint
grows with the font — under the offscreen platform's wide one it asked for 519 px, over the
pane's own 460 px ceiling, and the splitter handed it over anyway, leaving the map 623 px of
1400. `setSizes([260, 800, 340])` is honoured exactly and gave the map back 169 px
(`[260, 792, 340]` measured). Starting widths, not limits: the divider still moves, and the map
still gives up its own width first when the window narrows.

**A widget left in a layout that is never installed is a trap.** `_controls_row` still listed
the ramp's spin boxes and Fit button after the toolbar adopted them, so adding that row to a
layout later would pull them straight back out of the toolbar — which would then silently have
no Min/Max at all. With `external_controls` they now go into a throwaway layout.

**Two emission paths for one signal.** `_on_scope` repeated `_apply_kind`'s body instead of
calling it, so "emits exactly once" was a coincidence of two methods staying in sync. It calls
`_apply_kind` now, and a test counts the emissions.

**The toolbar's last item absorbs all the slack** — the peak label sat in a few hundred
invisible pixels of it. `Fixed` now, so it is exactly its text width and a narrow toolbar cannot
clip it. The toolbar also got an `objectName` and a hidden `toggleViewAction`: it is the only
route to the ramp, and a right-click must not be able to hide it.

### Two things worth recording

**A spin box is built around its own `QLineEdit`.** `toolbar.findChildren(QLineEdit) == []` is
the obvious way to assert the metal toolbar has no search box. It fails — against the two range
spin boxes, each of which contains one. The check has to filter by parent.

**Qt lets a minimum beat a maximum.** Under a very wide font the layer buttons alone exceed
`MetalPanel`'s 460 px ceiling and the pane comes out wider than its own `setMaximumWidth`. That
is Qt (a widget's minimum wins), not a layout bug, so the tests assert font-independent
invariants instead: the map is the widest pane, and panes plus handles account for the window.
The offscreen platform's 17 px/char is what made this visible, and it is the same trap phase 9
recorded.

**Tests: `tests/test_metal_gui.py` (44) and `tests/test_gui_smoke.py` (30)** — the spin boxes
actually being visible, the range widgets being in the toolbar and not the panel, the readout
being the left pane, a stationary cursor following a selection change, the layer table matching
the tech LEF, 0.065 surviving formatting, the pane balance holding on a narrow window, the
selection signal firing exactly once, and the readout working standalone from `(data, kind_of)`.

`python -m pytest -q` → **440 passed**.

## Phase 11 — the first look at the new layout

Three defects, all from one screenshot of the running window. One of them was mine from phase 8,
and it had been wrong the whole time.

### The map drawn at start-up was not the map the panel selected

The panel's tick boxes said every layer; the view drew `L:M1`. Nothing pushed the selection into
the view at construction - `_update_details` refreshed the readouts and the *scope* combo's
handler called `set_kind`, but the initial state never did. So the first thing on screen was the
M1 map, which on this sample carries almost nothing (mean 0.026 against the group's 0.14), and it
only became the map the user asked for once they touched the scope selector and came back -
which is exactly what was reported: "initial Signal+Power map is so blue; when I change to signal
only and shift back it becomes brighter". The hover readout named the kind all along
(`L:M1[47,14]`), which is how the bug was pinned.

Worse than cosmetic: the toolbar's `peak 0.463` described the group while the drawn map was M1,
so the panel contradicted the picture from the first frame. `MetalPanel.__init__` now ends with
`_apply_kind()`, and a test asserts the drawn map, the panel's selection and the reported peak
all agree at construction.

### The readout table was three rows tall in a half-empty pane

Reported as "Cell Detail is shown partly even there are much space below". Three Qt behaviours
had to be worked around, and the symptom is what you get from getting any of them wrong:

- A `QScrollArea`'s size hint is the size its widget *had* when the policy was last consulted,
  not what the widget now needs - so asking it to size itself gave a table a fraction of the
  height it required.
- A `QGridLayout` reports its hint from the geometry it finds itself in, and the scroll area
  resizes its widget to the viewport. Installing the table while the area was a few pixels tall
  meant the grid measured *nothing*, the area stayed that tall, and the two kept each other
  small. Instrumenting the fill showed `count() == 39` items with a hint of 0.
- A `QGridLayout` also keeps a row structure for every row it has ever held, so re-filling a
  layout leaves it sized for the largest table it has shown.

The table is therefore built on a detached widget, measured there, and only then installed -
with the height settled first. Measured: 243 px of scroll area for 241 px of rows, where before
it was 2 px for the same content.

### The layer table needed the width and the padding

Two things at once. The panes were sized for the offscreen platform's font and the real one is
wider, so the four-column table overflowed its pane, which is why the last header (`U`) was
missing and the values were cut. The detail pane went 260 → 300 and the layer pane 340 → 400,
and the detail pane's stretch factors became 1:4:1 rather than 0:1:0 - with the side panes at
zero stretch they never gave up a pixel, so the map absorbed the whole loss as the window
narrowed, down to a 292 px sliver against a 400 px layer list.

The other half is alignment: each `W/S/P` field is padded to the widest in the table, so the
slashes line up down the column instead of the digits shuffling row by row (`0.07/0.07/0.14`
against `0.8/0.8/1.6`). The leftover width goes to an empty column rather than to the last data
column, which keeps each heading directly over the numbers it names.

`python -m pytest -q` → **443 passed**.

## Phase 12 — the real files, vendored

Phase 0a validated this mode against two real files fetched into a scratch directory and thrown
away: OpenROAD-flow-scripts' Nangate45 tech LEF and OpenROAD's `test/gcd_nangate45.def`. The
tests that cite them inline verbatim stanzas, so the originals could never regress them. Five real
files now live in `sample_data/real/` (616 KB) with a `PROVENANCE.md` recording revisions,
hashes and licences, and `tests/test_real_samples.py` asserts the measured properties against the
files themselves. The source survey and the reasoning are in
[`real_sample_sources.md`](real_sample_sources.md).

Re-fetching found one number wrong for a reason worth recording: the as-built's "221 nets" for
the gcd DEF was measured on a 167 KB *prefix*; the full file has 497. The rest reproduce exactly
— 22 `LAYER` blocks of which 10 route, metal1 spacing 0.065, metal2 `f = 0.737`, 734 components,
20 tracks, db_unit 2000, a 32.74 µm die, and 2,504 via points, which the tests now cross-check
two ways: 2,438 single-point forms plus 66 zero-width `+ SHAPE STRIPE` shapes, counted
independently in the file and summed by the parser's `n_via`.

**It found a bug.** `is_macro` compared the whole `CLASS` string against `"CORE"`, so
`CLASS CORE SPACER` — plus `CORE ANTENNACELL` and `CORE WELLTAP`, 8 cells in the real library —
were hard macros. A macro removes capacity from the layers it blocks, and on the gcd design that
was 10.8 of 1071.9 µm², **1 % of the bottom-layer capacity**, invisible until the identity
`capacity == die area × f` was checked against a real library. The grammar is
`CORE [FEEDTHRU|TIEHIGH|TIELOW|SPACER|ANTENNACELL|WELLTAP]`, so only the first word names the
class. The synthetic sample writes a plain `CLASS CORE`, which is exactly why nobody noticed.

Two small honesties while in there: `defParser.py` no longer claims glued `*` coordinates "occur in
real DEF" (a sweep of the real file found zero), and the `.gitattributes` added here pins
`sample_data/real/** -text` so the vendored bytes stay the bytes that were hashed.

`python -m pytest -q` → **467 passed**.

## Phase 13 — the LEF's own blockage, instead of a layer count

`--macro-block-layers` was a guess standing in for data. The macro LEF usually says which layers
a macro obstructs and where, in `OBS`, and this project already read that file - it just never
looked inside `OBS`. It does now, and the flag became the fallback for a library that stays
silent. The plan, the decisions and what the review caught are in
[`macro_obs_blockage.md`](macro_obs_blockage.md).

**The parse.** A nested `OBS` block of `LAYER` sections and `RECT`s, closed by a *bare* `END`.
The cursor is left on that terminator because the caller's single `cursor += 1` steps past it -
stepping past it in the reader would make the enclosing walk skip `END <macro>` and run off the
end of the file. That also meant adding the length guard the macro walk had never had, which
turned the documented `IndexError` on a truncated library into "read what is there".

**The filter.** Per (cell, layer): union the rectangles, close by 0.1 µm, clip to the macro, and
count the layer as blocked only if the union covers a tenth of the macro's own footprint. A
prototype settled that: filtering per *component* discards a tessellated blockage outright - 45
tiles each under the threshold, 780 µm² of real blockage lost, measured - while a per-rectangle
rule is worse still, and a union needs no `MultiPolygon` handling. The closing exists because the
same coverage written with 0.05 µm gaps between tiles stays 50 separate regions instead of one,
and a gap that small is a tessellation artifact rather than a routable channel.

**The model.** `MetalData` carried two capacity grids because a macro blocked either the bottom
N layers or none. It now carries `{layer_index: blocked}` - float32, and only for the layers
something actually blocks - and precomputes the routable area per layer, so `_routable` stopped
allocating a grid per call: `cell_detail` runs on every mouse hover. Per-layer storage was not
the obvious win it looked like: one base plus *B* blocked grids is *more* than the constant three
it replaced at the default depth, which is why the dtype and the precomputation matter.

**Two bugs the new tests found**, both in my own first implementation:

- I conflated "declares no OBS" with "declared obstructions that were judged negligible", so a
  macro carrying only pin-access bites fell back to the layer count - the exact three-state
  confusion the change exists to remove. `test_pin_access_bites_are_not_a_keep_out` failed.
- The transform for a macro-local obstruction is `M_block·M_orient·p + (M_block·loc + t_block)`,
  and applying the *composed* matrix to the instance location as well puts a rotated macro's
  obstruction where a second rotation of its placement says. Nothing pinned a rotated macro
  before; the new orientation test does.

**And one the real file settled:** the 107 `OBS` blocks in the vendored Nangate45 library are all
on `metal1` and all interior - pin-access bites inside standard cells. Every one of those cells
is `CLASS CORE`, so under the rule they remove no capacity at all, which is what keeps the gcd
capacity identity intact.

`python -m pytest -q` → **487 passed**.

## Phase 14 — three defects in the layer extraction, from a real design

[`issue.tech_layer_detect.md`](issue.tech_layer_detect.md) reports three defects from an 18-layer
design's tech LEF (`wha1cd082-hs`). All three are in the extraction that feeds the metric, and
every reported number reproduced with the real parser before anything changed. The plan is
[`tech_lef_layer_extraction.md`](tech_lef_layer_extraction.md).

**The root cause of two of them is one missing concept.** `__parseLayer` scans line by line and had
no notion of a quoted `PROPERTY` payload, so statements belonging to a property's *own
mini-language* were read as the layer's base statements. A quoted `SPACINGTABLE` supplied a spacing
from its PRL breakpoints - `M5`'s minimum was **−0.2** - and a quoted `LEF58_SPACING` supplied
another from its conditional clauses (`B1` → **0.089**). The repository had been bitten by this
before, when `PROPERTY LEF58_TYPE` clobbered `TYPE`, and that was patched narrowly. It is now
consumed as a unit.

Two mechanisms, because one does not cover both shapes: an *unquoted* `PROPERTY name value ;` is
self-terminating and a one-line regex ends it, where a quote-parity reader would run on to the next
quoted line; everything else ends on the first line with an even number of quotes that also
contains `;`. Since a payload can contain any base statement, the fallback guard is the stanza's
own end - `END <layer>` or the next `LAYER` breaks the read with a warning, so a malformed library
loses one property rather than the rest of the layer. The unquoted tables - Nangate45's, sky130's,
the sample's - are base statements and keep working.

**Region layers are dropped, keyed on the property name.** `M2_FB1`/`M3_FB1`/`M4_FB1` declare
`TYPE ROUTING` and carry `PROPERTY LEF58_REGION`, and were listed as routing layers. The old
pattern matched `BASEDLAYER M3` but not the file's `BASEDLAYE R M2`, so the fix keys the exclusion
on `LEF58_REGION` itself and parses the names best-effort for the log line. Three layers now
disappear from the panel with a reason in `-v` output instead of looking like a parse failure.

**The pitch is the one perpendicular to the layer's own tracks** - the defect that silently changes
what the map *means*. `M1` is `HORIZONTAL` with `PITCH 0.020 0.032`, and taking the x value made
`(W + S) / P` = 1.6: its capacity overstated 60 %, so the map read too low. It is 0.032, and the
factor 1.000. The axis convention is not cited from a document in this repository - the reference
in `dev_plan/` is a syntax card with no prose - so it is pinned by two real files instead:

- `M1`'s `WIDTH 0.016` + `SPACING 0.016` equals exactly its y-pitch 0.032;
- ASAP7's `M2` carries `PITCH 0.180 0.144` beside a quoted `LEF58_PITCH " PITCH 0.144
  FIRSTLASTPITCH 0.180 ;"`, and the payload names 0.144 - the y value - as the layer's pitch.

A measurement over all three vendored tech LEFs (26 routing layers: direction, `pitch_x`,
`pitch_y`, chosen pitch, width, spacing, `f`) confirms exactly one row moves: ASAP7's `M2`,
0.180 → 0.144. Nangate45's ten and sky130's six are unchanged, and sky130's `li1` (`VERTICAL`,
0.46/0.34) keeps the x value as a positive control for a layer whose two pitches differ and whose
direction is the other one. That move also updated the one vendored expectation that had encoded
the bug: `test_real_samples.py` asserted `M2`'s factor as `0.144/0.18`, and it is now 1.0.

**A sanity assertion found a real file that violates it.** The plan added "every real layer's
`spacing <= pitch`" - and ASAP7's `Pad` failed it: `WIDTH 0.16`, `PITCH 0.32`, and a spacing table
whose values are 8 and 12 µm, all three straight out of the file. A pad plane is not a track
system; its `PITCH` is the distance between pads, so `(W + S) / P` is meaningless and **`Pad` has
`f = 25.5`**, reading as almost unused on a map. Recorded in `PROVENANCE.md` rather than fixed -
the honest fixes are to exclude it from the routing stack the way a region layer is, or clamp the
factor at 1.0, and neither is decided. The assertion is `spacing >= 0`, because the LEF genuinely
does not guarantee the stronger one.

`tests/test_real_samples.py` also gained a check that the size and `sha256` in `PROVENANCE.md` are
what the vendored bytes are - parsed out of the document rather than repeated in the test, so the
record cannot quietly drift away from the files it describes.

`python -m pytest -q` → **500 passed**.

## Phase 15 — the 7005-second routing read

`real_design_case_record.md` recorded a chip-level run whose routing read took **7005 s** for
~30 M lines, single-threaded, peaking at 18.9 GB of a 20 GB request. Two proposals existed for
it - one from another agent - and neither had been measured. The plan is
[`metal_routing_performance.md`](metal_routing_performance.md).

**Neither document had found the cost, and neither had I.** A first set of four "obvious" fast
paths was killed by an adversarial review with working counterexamples against the real code:
skipping the tokenisation of a `+ VIA` array breaks `*` coordinate reuse across a statement's
forms; "fewer than two points emits nothing" is false in both branches (a single-point routed
form is a real rectangle from its extension field, a single-point regular form is a deliberate
zero-length wire); and counting unknown-layer shapes as `points - 1` is wrong in four different
ways. Measured on the vendored gcd DEF, the middle one takes `n_via` from 2504 to 66.

**So the first phase was measurement, not code.** `generate_metal.py --real-shape` writes the
mix the run's own counters describe - via arrays in both real spellings, a giant power net,
die-spanning stripes, undefined layers, jogs, NDR-referencing nets, 3.36 M instances, gzipped
on request - with knobs for points per form, lines per form and via nets, and reports stage
seconds, GC time, live objects and RSS. On this machine it runs at the same speed as the one
Phase 5 measured on (`--stress 200000`: 10.55 s against 11.5 s recorded), so its constants are
comparable. What it says:

| test | result |
|---|---|
| per via-point shape, 200 k vs 2 M | 13.5 -> 12.5 us, **constant** |
| one giant power net vs 1,000 nets | 19.1 vs 18.2 us/line - none |
| points spread over 8 lines vs 1 | 12.7 vs 19.1 us/line - none |
| gzipped vs plain input | 19.2 vs 19.1 us/routing-line - gzip is free |
| 3.36 M instances, GC | 4.96 s of 41 s = 12 % |
| the real OpenROAD gcd DEF, as reference | **200 ns/char, 11.8 us/shape - the same constants** |

**There is no quadratic to delete.** Both documents' rankings are wrong in checkable ways: the
line-by-line loop its #1 blames reads the *same file* at 4.2 us/line (pass 1, 6 M lines in 25 s)
against pass 2's 233 us/line, and its #2 and #4 optimise work that is already batched - numpy is
entered once per 65,536 shapes, not once per shape. Its #5's premise ("a segment spans ~1 bin
vertically") is false for vertical layers, whose wires run the die's full height.

**What the missing factor turned out to be.** By the run's own counters, 147 M dropped shapes at
12.5 us is 1838 s, plus 41 s of components and ~150 s of reading - about 2,100 s against the
observed 7005 s. The gap is not a hidden pathology: the log counts only the shapes it *drops* and
never says how many it *measures*. The arithmetic closes at ~250 M total shapes. That counter
(`n_emitted`) is now reported, and it is the first thing the next real run will supply.

**The fixes that the measurement justified**, each with its equivalence argument in the code:

| change | effect |
|---|---|
| form scan: a required first character, and a digit lookahead before the 40-keyword check | **182 -> 37 ns per character**, match stream identical over 16,000 forms |
| tokeniser: the 40-keyword lookahead removed, rejection moved to a set lookup per matched word | the lookahead never protected the token stream (it produced `HAPE` from `SHAPE`); 0 point divergences over 19,646 real tails |
| `re_glued_star.sub` and the clause scans guarded by a literal substring check | provable no-ops otherwise; the gcd parse's `re.sub` was 6.7 % of it |
| `+ VIA` arrays: points still scanned, no shapes built, counted on the net | removes a fan-out of one object per point at 85 % of a real DEF's shapes |
| pass 2 skips components; the decoded DEF is released; `__slots__` on both wire types | 3.36 M objects no longer built twice, and no per-instance dict at 10^8 shapes |

| case | before | after | |
|---|---|---|---|
| via-heavy (the real design's dominant class) | 25.68 s | **10.72 s** | **2.4x** |
| per via shape | 12.5 us | **5.2 us** | 2.4x |
| 3.36 M instances | 41.3 s | **31.0 s** | 1.34x |
| the real gcd DEF | 59.2 ms | 49.1 ms | 1.21x |
| `--stress 200000` (2-point nets) | 10.55 s | 9.52 s | 1.11x |

The boundary is now visible and worth stating: **the win is where the design is via-dominated**
(124.7 M via points against 12.9 M jogs, in the real run). The 2-point-wire path barely moved,
because its cost is ~40 us per *net* spread across ten per-statement sites - each a full scan of
the statement - and no single surgical change touches that.

**The log strategy — because a run's log is the only evidence when the design cannot be
shared.** One line per stage with elapsed, rate and RSS (the only elapsed number before this was
the parser's own, which mixes parsing, conversion and rasterisation); the emitted-shape counter
beside the six drop counters; the input's own shape (forms, points, points per form, the longest
statement, lines, and which layer names the DEF uses that the tech LEF does not - the 4.5 M-shape
class's cause); RSS, GC seconds, collections per generation and live objects; and a single
`metal-summary:` JSON line carrying all of it. `--profile` adds cProfile's top 15 by self time,
which is the only way to separate parser-self from sink-self, and the heartbeat is now time-based
with a rate and an estimate from the section's declared count, flushed every time - a line-based,
unflushed heartbeat is 230 s of silence that a killed job loses.

**A test caught a real bug in that work**: the cancel callable was being assigned to the parser
*after* construction, and `DefParser` parses from `__init__` - so cancelling would have silently
never fired. It is a constructor argument now, and `tests/test_metal_diagnostics.py` pins the
whole path: cancel stops the build, keeps the partial map, and says so in a warning.

`python -m pytest -q` -> **510 passed**, with the pinned real-file numbers unchanged (gcd 2504
via / 5 jogs / 2327 rects / `means["metal2"] == 0.2527`).

## Phase 16 — the wiring pass across processes

The plan's rule was to adopt parallelism only if the single-core work left the target out of
reach, and it did: 2.4x on the dominant shape class against a 7.8x target. `--jobs N` runs the
wiring pass across processes, off by default.

**The first version was slower than one process, and measuring is what found it.** It cut the DEF
into blocks in the parent and shipped the text to the workers: on a 5 M-line input, 53 s against
44 s, and flat from two workers up. A chip-level DEF is gigabytes, so moving it through pipes
costs more than parsing it. The design now has **every worker read the file itself** and keep
every `jobs`-th net statement, sending back only per-layer grids - a megabyte a worker.

| | |
|---|---|
| one worker through the machinery, 9.1 M lines | 73.1 s against 64.9 s sequential - the machinery is **+13 %** |
| two workers | 51.5 s (1.26x) |
| four workers | 34.3 s (1.9x) |
| eight workers | 28.5 s (2.3x) |

`wall ~= 8 s of machinery + parse/N + ~10 s of per-worker scan and startup`, so a 65 s job is
mostly fixed cost; against the real design's ~3000 s read those terms are noise and the same
model predicts **~3.9x at four cores**, which is the Amdahl ceiling for this problem. That is a
prediction from measured terms, not a measurement at scale - a 3000 s synthetic would be 430 M
lines.

**Two things the work needed that only measurement would have shown.** The first synthetic put
2 M via points into one 500,000-line power statement, and a statement is atomic (its `*`
coordinate state cannot be split across workers), so no pool can parallelise that shape - the
measurement showed exactly the nothing it should have. And the first pooled build lost
**0.77 % of the metal area** while every counter matched: the block cutter had captured the
`NONDEFAULTRULES` body without its section header, so a net naming a rule silently fell back to
the layer defaults. Counters identical, map wrong - the failure mode the review had warned
about, caught by comparing grids rather than counters.

`python -m pytest -q` -> **526 passed**, including pool-versus-sequential on the committed sample
(counters exactly, grids to float32 rounding) and the cutter's own invariant, since a split
statement would still parse and still draw, just in the wrong place.

## Phase 17 — the flow stops parsing what it has already parsed

A sample run with `--jobs 8` put **6.45 s of 7.39 s in `_thread.lock.acquire`, with 40
`CreateProcess` calls**, for a build that takes 0.7 s sequentially. Four things were being read
more than once, and the plan is [`parse_once_flow.md`](parse_once_flow.md).

| redundancy | in the log | on the recorded real design |
|---|---|---|
| macro LEF parsed twice - cell table, then obstructions | `cells.lef` at cell-index and again at blockage | ~10 s of 7051 s |
| a block parsed once per **instance** | `reading routing in SUB` ×4 | zero (flat, one instance); K × for a hierarchy |
| every **worker** re-reads the file | `Load DEF file SUB` ~32× | deliberate, but it multiplied the row above |
| the DEF read once per pass | pass 1 components, pass 2 wiring | ~25 s |

**The test gap was closed first**, because both failures here are silent. Nothing pinned a wire
under a non-identity frame - the frame tests were outline-only and macro-obstruction-only, and
`verify()`'s grid thresholds survive a *composed* transform - and nothing pinned a block's wiring
landing once per placement, which a deduplicated walk passes while losing three quarters of the
metal. Both are now tests, and so is `emitted == 79,277 == 4 × 19,817 + 9` on the committed sample.

**And one of them found a live bug.** `_add_polygon` never applied a frame at all: a `+ POLYGON`
inside a rotated sub-block rasterised in the block's own coordinates, stacked under every other
instance, while `n_emitted` counted it once per instance. It had been invisible because the
sample's only ring sits in the top block, where the frame is the identity. Writing the test took
two attempts for an instructive reason: the first fixture used a **square** ring, and a quarter
turn maps a square ring onto itself, so the test asserted a difference that cannot exist. It is an
L now - which also exercises the other way this path can go wrong, a bounding box instead of a
point map.

**What changed.** `build_metal`'s wiring pass now collects each block's placements and parses the
block **once** with a list of frames; the walk stays per path, because `_macro_blockage` and
`_boundary_polys` need one visit per instance. `ShapeStream.frame` became `frames`, applied in
`flush()` per frame - to *copies* of the pending arrays, so that one frame's output is never fed
into the next frame's transform (that composes them: right for the first placement, wrong for the
rest, and invisible to every counter). `n_emitted` is counted per placement inside the stream, so
its invariant against the sink still holds; the six counters that describe the *text* are
multiplied by the placement count where the totals are folded, so the summary agrees with the
grids; the input characterisation is folded once, because the text is read once.

`--jobs` is now a **cap**: `effective_workers` sizes the pool from the input, and a DEF only a few
megabytes across is parsed in one process. **The plan's own assumption was wrong here** - it
proposed sizing on the declared net counts in pass 1's 64 KB head, and for a chip-level DEF that
head is megabytes of components before the first section header, so the count is not in it. The
sizing reads the *uncompressed* size instead, via gzip's trailer for a `.gz` (whose `st_size` is
the compressed size, and every worker decompresses the whole thing). One pool is built per build
rather than per block, and the `cancel` that `parse_parallel` had always accepted but never passed
to its workers now reaches them - `--jobs > 1` could not be interrupted at all before.

**Measured on the user's own scenario** (`top.def` + `sub.def`, `--jobs 8`):

| | before | after |
|---|---|---|
| `stage routing` | 6.91 s | **0.39 s** |
| full build | ~7.4 s | **0.64 s** |
| `reading routing in SUB` | 4 | 1 |
| LEF parses | 2 | 1 |
| `_thread.lock.acquire` | 6.45 s | gone from the profile |
| shapes measured / jogs | 79,277 / 540 | 79,277 / 540 (unchanged) |
| reported input lines | 172,779 (the text counted once per instance) | 43,242 (once) |

The line count is the one number that *should* move: it describes the input, which is now read
once rather than once per placement, and it makes this summary incomparable with earlier runs'.

`python -m pytest -q` -> **531 passed**, with the real-file numbers unmoved (gcd 2504 / 5 / 2327)
and the new tests in `tests/test_metal_hierarchy_frames.py` covering the frames and the
multiplicity.

## What each change bought

Every number below is measured on a committed or reproducible fixture; the fixtures are named so
each can be re-run. "Cost" is what the change asks of the codebase and the reader, not just its
lines.

### On the project's own test cases

| # | change | gain, measured | fixture | cost |
|---|---|---|---|---|
| 1 | form scan refuses a position on its first character, and asserts the digit before the ~40-keyword lookahead | **182 -> 37 ns per character** (4.9x), match stream identical over 16,000 forms | routing-shaped text, both spellings | two pattern constants; the equivalence is argued in the comment and pinned by the fixture goldens |
| 2 | tokeniser's keyword lookahead replaced by a set lookup per matched word | 890 -> 515 ns per short tail (1.73x, measured in review); 0 point divergences over 19,646 real tails | `sample_data/real/nangate45/gcd_nangate45.def` | via *names* for junk keywords differ (`HAPE` vs `SHAPE`); no metric path reads a via name, and a test parses the real file both ways to prove the shapes and counters match |
| 3 | `re_glued_star.sub` and the clause scans guarded by literal substring checks | `re.sub` alone was 6.7 % of the gcd parse; each guard is a provable no-op otherwise | gcd DEF, and every DEF | three one-line guards |
| 4 | a `+ VIA` array's points are counted on the net instead of building one shape each | part of 25.68 -> 10.72 s below; removes one object per via point, 85 % of a real DEF's shape count | via-heavy synthetic | a net field, a stream counter fold; the points must still be *scanned* (the `*` state crosses forms), which a test pins |
| 5 | pass 2 skips components, the decoded DEF is released, `__slots__` on both wire types | 41.3 -> 31.0 s (1.34x); GC 4.96 -> 1.75 s; 3.36 M objects no longer rebuilt | 3.36 M-instance synthetic (the real design's instance count) | one existing flag finally used, one `del`, two class attributes |
| 6 | everything above, together, on the dominant shape class | **25.68 -> 10.72 s (2.4x)**; 12.5 -> 5.2 us per via shape; GC 1.23 -> 0.77 s | via-heavy synthetic, 2 M via points | - |
| 7 | the same, on the shapes a signal-dominated DEF has | 10.55 -> 9.52 s (1.11x) | `generate_metal.py --stress 200000`, the Phase 5 configuration | the 2-point-wire path is ~40 us per net over ten per-statement scans; no single change reaches it |
| 8 | the same, on a real routed DEF | 59.2 -> 49.1 ms (1.21x) | the vendored gcd DEF | - |
| 9 | the wiring pass across processes (`--jobs N`) | 65 -> 34.3 s at four workers (1.9x), 28.5 s at eight (2.3x) on a 9.1 M-line synthetic; **+13 % at one worker**, which is why the default does not use it | `--real-shape --via-nets 2000000` | a new module, a CLI flag, its own tests; every worker re-reads the file (one line-level scan each, deliberately) |
| 10 | diagnostics (no speed claim) | the log now carries the emitted count, the input's shape, per-stage seconds, RSS and GC - the evidence that made the real-design estimate below possible at all | `tests/test_metal_diagnostics.py` | ~150 lines of reporting |
| 11 | a block's DEF is parsed once per *block*, not once per placement, and placed under each of its frames | the log's `reading routing in SUB` 4× -> 1×; `stage routing` 6.91 -> 0.39 s at `--jobs 8` | `sample_data/metal/{top,sub}.def` | a frames list through the stream and the task tuple; the flush loop must apply frames to copies and never compose them |
| 12 | `--jobs` sized from the input, one pool per build, and the `cancel` it never passed to its workers | 8 workers -> 1 for a 2 MB DEF, and the 6.45 s of lock contention that was 87 % of that run's profile is gone | the same sample; the parallel tests pass an explicit override so they still exercise the pool | a heuristic constant, and a test override that must not be forgotten or the pool's equivalence coverage quietly stops testing |
| 13 | the macro LEF parsed once: the obstructions come out of the same pass that builds the cell table | one LEF pass instead of two; ~10 s of the recorded 7051 s run | the sample, and the vendored Nangate45 library | an opt-in on `cell_info_from_lef`; the "could not read the obstructions" warning goes with the second read |

Equivalence throughout: the suite went from 500 to **526 tests**, and the pinned real-file numbers
never moved (gcd 2504 via / 5 jogs / 2327 rects / `metal2` mean 0.2527). Three proposed fast paths
were dropped before landing because a counterexample showed they changed the map.

### Estimated on the real design

The run's own counters, times the measured per-shape constants. The last row is the one term
nobody has ever counted, and it is why the estimate is a range rather than a number.

| term | the run's count | before | after | effect |
|---|---|---|---|---|
| via points | 124,711,987 | 12.5 us | 5.2 us | ~910 s saved |
| signal jogs | 12,964,342 | ~13 us | ~13 us | unchanged |
| shapes on undefined layers | 4,539,783 | ~13 us | ~13 us | unchanged |
| zero-extent shapes | 4,517,711 | ~13 us | ~13 us | unchanged |
| component objects | 3,355,697 x 2 passes | 41 s | 31 s | ~10 s saved |
| line reading | ~30 M lines | 4.2 us each | unchanged | ~126 s, not a target |
| LEF passes | 221 files x 2 | 21 s | unchanged | not a target |
| garbage collection | - | 3-12 % of the run | less on the via class | ~100-200 s saved |
| **shapes actually measured** | **never reported** | ~12 us | ~10-12 us | **the open term** |

Those terms that *can* be priced save **~1,000-1,100 s, about 1.2x** - and that is the floor,
because it counts only the shapes the log mentions. The rest of the 7005 s is the 5100-odd
seconds of shapes the run never counted, and those go through the same parse path the changes
1-3 sped up: at the via-heavy mix, which is what the counters say the file mostly is, that is
another ~2x. So the honest estimate for the single-core changes is **1.2x at worst and 2.1x at
best, 7005 s -> 5,900 s or -> 3,400 s**, and which end it lands on is exactly what the missing
counter decides.

With `--jobs 4` on top - ~3.9x predicted on the residual, from the scaling model in Phase 16 -
that is **~18 to ~33 minutes** against the 1 h 57 m it took, and the proposed target of 15
minutes is reachable only if the file is as via-dominated as its counters suggest. One
instrumented run settles it: the `metal-summary:` line reports the emitted count, the shape
classes and the stage split, and `--profile` reports which function holds the time.

### Costs worth stating plainly

- **The parallel pass costs CPU to save wall clock** - N extra file scans plus N interpreter
  startups - and it is off by default because at one worker it is 13 % *slower* than not using it.
- **Every change here is a constant-factor change to a per-shape loop.** Nothing made the work
  asymptotically smaller: the design still parses every shape, and the only way past that is a
  parser that emits coordinates directly instead of one object per segment, which is a rewrite
  rather than an optimisation.
- **The failure mode is silent.** A fast path that mis-reads geometry produces no error: the
  counters stay identical and the map is wrong, which is what the first pooled build did at 0.77 %
  of the area. Grids, not counters, are what the equivalence tests compare.

## Where this ended up

| phase | state |
|---|---|
| 0a | findings validated against a real Nangate45 tech LEF and a real routed OpenROAD DEF |
| 0b | parsers: SPACINGTABLE, LEF58_TYPE, NDR section, net class, polygons, vias, jog rule |
| 1 | `raster.py` - exact, 494 ns/segment, memory bounded |
| 2 | `routing.py` - streaming conversion, nothing retained |
| 3 | `assembly.py` - frames for wires, matrix composition |
| 4 | `metal.py` - the metric, per-layer capacity, cell detail |
| 5 | measured: parsing is 97 % of the runtime |
| 6 | `sample_data/metal/` - 1P12M, hierarchical, self-verifying |
| 7 | `metal` subcommand and quickstart shortcut |
| 8 | layer panel, net-class selector, cell readout |
| 9 | the blank sidebar, the misplaced boundary, `Auto`, and a legible readout |
| 10 | three panes, the range in the toolbar, and W/S/P per layer |
| 11 | the startup map, the readout table's height, and the table's alignment |
| 12 | the real files, vendored, and `CLASS CORE SPACER` read as a macro |
| 13 | the LEF's own `OBS` blockage in place of a layer count |
| 14 | property payloads, region layers, and the pitch perpendicular to the tracks |
| 15 | the 7005 s routing read: what it costs, and the changes that cut it |
| 16 | the wiring pass across processes, and the measurement that redrew it |
| 17 | the flow stops parsing a block once per instance, a LEF twice, a file per worker |

Nine bugs were found by checks rather than by reading, and four of them would have produced a
wrong map with no error at all: the scope lookup that left the default view empty, the missing
`.set_index` that made every macro vanish from capacity, the `+ RECT` width check that dropped
the entire power grid, and the `mergeOrient` composition that mirrored sub-block wiring against
its parent. The rest were performance or plumbing: two 51x and 2x pathologies in the rasteriser,
the Python loop over millions of shapes, the 1448 MB peak, and a generator that collided its own
component names.

The performance work added five more of the same kind. Three were caught by an adversarial review
before any code was written: a fast path that would have mis-resolved a `*` coordinate across a
statement's forms, one that would have dropped a real rectangle carried by a single-point routed
form, and one that counted shapes on undeclared layers four different ways - the middle one takes
`n_via` from 2504 to 66 on the real DEF. Two more were caught by the new tests: a cancel callable
that would never have fired, because the parser parses from its constructor and the callable had
been assigned afterwards; and a parallel cutter that took a `NONDEFAULTRULES` body without its
section header, so nets naming a rule fell back to layer defaults and **0.77 % of the metal area
went missing while every counter matched**. The last one is the clearest argument in this document
for comparing grids rather than counters.

## The sample's quick start

`sample_data/metal/quickstart.py`, because metal mode takes the longest command line of any
mode - two DEFs, a macro LEF and a tech LEF - and the sample is the only place those four are
known to fit together.

    python sample_data/metal/quickstart.py           # open the GUI
    python sample_data/metal/quickstart.py --check   # print the numbers, no GUI

Both paths delegate: `--check` calls `build_metal` and the GUI path calls the real CLI, so
there is no second copy of the flags to drift - the same contract as the repository-level
`quickstart.py`. `--check` prints the per-layer geometry and utilisation, the signal/power/all
maxima, the horizontal/vertical maxima and the busiest cell's full arithmetic, which makes it
the thing to run on an unfamiliar DEF.

## Making the sample actually look like a design

The check exposed four separate ways the sample was unrealistic, each of which had been
invisible in the map itself:

**Wires were routed over the SRAMs.** Real designs do not put signal on the lower metals over
a hard macro, and metal there reads as congestion in cells whose capacity is zero. Wires are
now kept out of the macro footprints - and the *whole* segment is tested, not its endpoints,
since a 30 um run between two points outside a macro passes straight over it. A jog is a
sideways step and is tested too.

**The four sub-blocks overlapped.** A quarter turn swaps a block's extents: a 260x200 block
placed West occupies 200x260, and DEF anchors the cell's *origin corner* at the placement, so
West maps `x -> x0 - y` and the block extends to the *left* of its origin. Spacing the columns
by the un-rotated width put one block's wiring inside another's macro. Each instance is now
placed so its **rotated** footprint lands in its grid cell.

That one was found by inverting each frame on a stranded cell and asking which placement put
the metal there - the answer was a *different* block than the one whose macro covered it,
which is what an overlap looks like from the outside.

**Signal was piled onto three layers.** All the wires sat on M2/M3/M4, which made those layers
read several times their own capacity - congestion no router would produce. Real routing uses
the middle of the stack, so the sample now spreads across M2..M8.

**The clustering bias swamped the mean.** The rejection sampler used `activity**2 + 0.08`,
which concentrated wires into a few cells at **27x** the mean. Loosened to a gentle slope. The
die was then sized to the net count rather than the net count to the die: at 12k nets over
0.2 mm² the busiest cell reached 0.18, a congestion map with no congestion on it.

The result verifies at **all-layer max 0.463, 552 distinct values**, per-layer peaks 0.38-0.53,
with no warnings - a map that looks like a design rather than a stress test.

### The check that caught them

`build_metal` gained a warning for **cells carrying wire on a layer whose capacity is zero**,
which is metal drawn where the model says there is no room. Only *signal* metal counts: a
power rail runs straight through a macro, since the macro's own power connects to it, so a
followpin crossing an SRAM is ordinary rather than stranded. That warning is what turned four
sample bugs into something visible, and it is worth having on a user's own DEF for exactly the
same reason - it distinguishes "this region is congested" from "this region cannot be
congested, and something is wrong with the input".

`python -m pytest -q` → **428 passed**.
