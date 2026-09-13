# Metal density mode

## Context

The viewer has three input flows (`json` / `def` / `verilog`) and one physical view: a 2-D
heat map of instance-derived quantities (cell density, leakage, dynamic, ULVT). All of them
describe *placement*. Nothing describes *routing*, so there is no way to see where metal is
exhausted — where signal noise and DRC violations come from.

This adds a fourth flow, `metal`, rendering per-routing-layer metal utilization from a DEF's
wiring. Requirements are in `dev_plan/metal_density_mode.md`. Scale is the hard requirement:
real designs reach **10⁷–10⁸ wire segments**, which rules out holding the geometry in memory
and makes parser throughput the binding constraint. The calculation is specified in full
because it is the point of the feature.

## The calculation

### Notation

The die is cut into a grid of `g x g` cells (`--grid-size`; default **10.0** µm for this mode,
`config.DEFAULT_METAL_GRID_SIZE`). Cell `c` has in-die area `A(c) <= g^2` — edge cells are
partial, so `A` is an array, not a scalar.

The tech LEF gives routing layers with `d_L` (`DIRECTION`), `p_L` (`PITCH`), `W_L` (`WIDTH`),
`S_L` (`SPACING`). `TlefParser(path).layers` already returns all four (`LefLayer`), in
**microns**; DEF coordinates are **DB units**, so wire and track coordinates are divided by
`DefParser.dbUnit()` — the same conversion `instance_info_from_def` already applies to
components and the boundary.

Per wire segment `k` on layer `L`, of net `n`:

- **width** `w_k` — the statement's `routeWidth` for special wiring; for regular wiring the
  NDR's `WIDTH` for `L` if `n` references a rule, else `W_L`. Regular DEF wiring carries no
  width at all (`DefWire` is `layer_name, rule, from_pt, to_pt, via, via_orient`), which is
  why the tech LEF is mandatory rather than optional.
- **spacing** `s_k` — the NDR's `SPACING` for `L` if `n` references a rule, else `S_L`.
- **extension** `e_k` — regular wiring defaults to half the wire width at each end; special
  wiring is 0 unless the statement gives an `extValue`.

### The metric: keep-out utilization

Expand each segment rectangle by half its own spacing on all four sides:

    r_k = the segment rectangle (length ℓ, width w_k)
    g_k = inflate(r_k, s_k / 2)          ->  (ℓ + s_k) x (w_k + s_k)

Why this expansion is the right one: a minimum-width wire inflated by `S_L / 2` covers exactly
`W_L + S_L = p_L` across — **one track pitch**. A wire routed at `2W2S` inflates to
`2(W + S) = 2 p_L`, exactly two track pitches. The inflated area is therefore measured in
*track-pitch area consumed*, with no special case for NDR, and it stays correct for power
stripes and polygons that do not sit on signal tracks at all.

Overlapping expansions **add** rather than unify. That is what the track argument requires:
two wires at exactly minimum spacing tile two track pitches with no overlap, while wires
*closer* than the spacing rule overlap and push `U` above true occupancy — a conservative
signal, which is the right direction for a DRC-risk map. The `clip` bounds it.

### Capacity: two corrections, both forced by real tech LEFs

**Correction 1 — capacity must be normalized by the actual pitch.** The identity "a
minimum-width wire inflated by `S/2` covers one track pitch" requires `W + S == P`. That holds
for Nangate45 (width 0.07, spacing 0.07, pitch 0.14 ✓) but **not** for every library, and real
tech LEFs show it failing: a 90 nm example layer has `WIDTH 0.160`, default `SPACING 0.180`,
`PITCH 0.410`, and sky130 met1 is `WIDTH 0.14`, `PITCH 0.34` with a 0.14 minimum spacing.

When `W + S < P`, a fully-utilized layer's inflated area is only `(W+S)/P` of the cell, so `U`
would read 0.82 at *full* utilization on sky130 met1 — a systematically low map, silently.

Fix by scaling capacity into the same "inflated area" units rather than assuming they coincide:

    f_L    = (W_L + S_L) / P_L          usable inflated area per unit cell area
    C_L(c) = (A(c) - B_L(c)) x f_L

`f_L = 1` when `W + S == P` (the common case, and the whole previous formula). Verify the
general case holds: at full utilization with a `kW/kS` rule, the effective pitch is `kP`, so the
track count is `g/(kP)` and the inflated area is `g^2 x (kW + kS)/(kP) = g^2 (W+S)/P = C`. So
`U = 1.0` means full track utilization **for any rule mix and any library** — which is the
property the whole metric rests on. Fall back to `f_L = 1` when `PITCH` is absent from the LEF.

**Correction 2 — macros only block the bottom layers.** A hard macro such as an SRAM is built
from M1–M4 only; M5 and above route freely over it, so capacity is layer-dependent:

    B_L(c) = macro/blockage area in c, counted only for layers up to the macro block limit

With `--macro-block-layers N` (default **4**) meaning "macros block the bottom N routing
layers". Storing `C_L` naively is `N_layers` arrays; instead store the routable area twice and
apply `f_L` per layer:

    routable_base(c) = A(c)                        # in-die area, edge-aware
    routable_bot(c)  = A(c) - macro_area(c)        # below the limit
    C_L(c) = (routable_bot(c) if index(L) < N else routable_base(c)) x f_L

Two grids plus a scalar per layer, not twelve grids. Getting the macro part wrong is not
cosmetic: with uniform subtraction, `U` over every macro reads **high** (capacity understated)
exactly where routing is in fact free. `--macro-block-layers 0` disables it entirely.

### Single layer

    D_L(c) = Σ_{k on L} area(g_k ∩ c)        inflated area consumed on L inside c
    U_L(c) = clip( D_L(c) / C_L(c), 0, 1 )

`1.0` means every track on that layer is consumed. A cell with `C_L(c) == 0` (fully under a
macro, on a blocked layer) returns `0.0`.

### Multi-layer (the checkbox group)

Layers are **parallel** resources: they add in capacity, not in area. For a selected group
`G ⊆ L`:

    U_G(c) = Σ_{L∈G} D_L(c) / Σ_{L∈G} C_L(c)         capacity-weighted mean

**This is now genuinely weighted**, not a disguised arithmetic mean: with per-layer capacity,
a macro blocks M1–M4 but not M5–M12, so `C_L` differs across the group and the weighting
matters. Summing instead drives every cell to 1.0 and the map goes uniformly white.
Ticking `M1 M3 M5 M7 M9 M11` reads *average horizontal utilization*, `M2 M4 M6 M8 M10 M12`
*average vertical utilization*, all twelve *total routing utilization*.

### Worked example

Grid 10 µm, no macro → `A = 100 µm²`. Layer M3: `P = 0.2`, `W = 0.1`, `S = 0.1` → `f = 1.0`.

| | value |
|---|---|
| 30 horizontal M3 wires of length 8 µm | each keep-out `8.1 x 0.2 = 1.62 µm²` |
| `D_M3` | `48.6 µm²` |
| `C_M3` = 100 x 1.0 | `100 µm²` |
| `U_M3` = 48.6 / 100 | **0.486** |
| cross-check by tracks | 50 tracks x 10 µm = 500 track-µm available, 30 x 8 = 240 used → 0.48 ✓ |

For contrast, that same 48.6 µm² of inflated area on a sky130-met1-like layer
(`W 0.14`, `S 0.14`, `P 0.34` → `f = 0.82`) has `C = 82 µm²` and reads `0.593` — correctly
higher, because the layer offers fewer usable tracks in the same area.

Same cell carrying M1 at `U = 0.10`, M3 at `0.486`, M5 at `0.20`: the horizontal group reads
`ΣD / ΣC`, which reduces to the plain mean `(0.10 + 0.486 + 0.20) / 3 = 0.262` when the `f_L`
are equal.

### Reading the map

No bottleneck metric is computed, so H/V is answered by two selections. A cell is a real
bottleneck when **both** read high — no direction left to escape in. High horizontal with low
vertical is normally routable. Calibration: a DRC-clean routed design typically peaks around
0.85–0.9 locally, so the range is `[0.0, 1.0]` with 1.0 as "every track consumed".

## Non-preferred-direction segments (jogs)

A vertical layer may carry short horizontal segments — a track shift without a layer change.
Two consequences, both handled:

**Nothing can break.** The rasterizer bins by **shape**, never by the layer's declared
direction. Orientation is a property of the segment (`x0==x1` or `y0==y1`), and the layer's
`DIRECTION` is used *only* to label the GUI's H/V grouping. So a horizontal jog on M6 is an
ordinary rectangle and takes the same path as any other; there is no code path that can be
confused by it. This is a deliberate design property, and it gets a test.

**Small jogs are dropped, and counted.** Below a threshold a jog is negligible in area but not
in *count*, and count is what costs time. Drop a segment when its length is below
`max(w_k + s_k, p_L)` — i.e. shorter than one track pitch, which for a 0.2 µm stack means
segments under ~0.2 µm, each contributing under `0.04 µm²` to a 100 µm² cell. Report the
number dropped in the hover/stats text so it is visible rather than silent, and make the
threshold a flag (`--min-segment-length`) so it can be set to 0 for an exact run.

**A caveat, stated rather than hidden:** the area-to-track equivalence assumes wires run along
their layer's preferred direction. A non-preferred jog consumes track crossings rather than
track length, so its contribution to `D_L` is approximate. Being short and rare, the error is
well inside the metric's other approximations, but it belongs in the docs.

## Performance

The target is 10⁷–10⁸ wire segments. At that scale **the DEF parser is the bottleneck, not the
rasterizer**: `DefParser` is a Python line-by-line loop with per-line regex, on the order of
10⁵ lines/s, so 10⁸ wiring statements is ~1000 s before any binning happens. Two architectural
consequences.

### 1. Nothing may hold all the segments

At 10⁸ segments, coordinate arrays alone are 1.6 GB. The pass must **stream**: parse, rasterize
each chunk, discard it. Peak memory is `O(bins x layers)` plus one chunk, independent of segment
count. This requires a streaming API the parser does not have — `__extractNets` /
`__extractSpecialNets` currently accumulate every net into `self.__nets`. Add an iterator form
that yields parsed statements (or segment batches) without retaining them; keep the existing
accumulating behaviour for the current callers so nothing else changes.

### 2. Reduction before rasterization — the cheapest lever, in order

1. **Block-wise scanning instead of line-by-line.** Read the NETS/SPECIALNETS regions in large
   blocks and use `re.finditer` over the block (C-speed scanning) rather than a Python loop
   calling `.search()` per line. This attacks the actual bottleneck.
2. **Drop micro-segments** (the jog rule above) and zero-length/degenerate shapes, counted.
3. **Drop segments on unusable or non-routing layers**, and those entirely outside the die
   bbox, before any binning math.
4. **`str.split()`-based field extraction** where a regex is not needed — `str.split` runs at C
   speed and beats `re` on short strings.

### 3. Exact O(1)-per-segment binning

The per-bin overlap `f_x(column) · f_y(row)` decomposes into four classes, each a *constant*
value over a *rectangular range of bins*:

| class | bins | value |
|---|---|---|
| interior | full bins in x, full bins in y | `1.0` |
| x-edges | the ≤2 partial columns, full rows | `f_x` |
| y-edges | full columns, the ≤2 partial rows | `f_y` |
| corners | the ≤4 corner bins | `f_x · f_y` |

A constant over a bin range is added with **four scatter writes into a difference array**,
independent of how many bins the range spans. So a segment spanning 200 bins costs the same
as one spanning two — there is no `O(bins touched)` term anywhere in the hot path. This is
exact, not an approximation. Then one `cumsum(axis=0)` + `cumsum(axis=1)` per layer.

For the common case — a wire whose thin extent sits inside a single bin, which is the norm
since `w + s` (~0.2 µm) is far below `g` (10 µm) — classes 3 and 4 are empty: roughly six
scatter writes and one difference array per layer.

Accumulate with `np.bincount` on flattened indices with weights (a compiled C loop), not
`np.add.at` (5–10× slower). Only the interior class needs a full-grid difference array per
layer — 16 MB each at 2000×2000 float32, 192 MB for twelve layers, with the partial-edge
classes written straight into the output grid.

### 4. Parallelism and optional compiled kernels

- **Row bands are independent.** Split the grid into horizontal bands; a segment crossing a
  band boundary is split at it (the class decomposition already computes bin ranges, so this is
  free). Bands then accumulate into disjoint slices with **no contention and no locks** —
  dispatch with `concurrent.futures.ProcessPoolExecutor`, no new dependency.
- **Layers are independent too**, if a two-pass or buffered arrangement is worth it. Bands are
  the better first cut because they work in a single streaming pass.
- **Optional numba.** If `numba` is importable, a `@njit(parallel=True, cache=True)` kernel over
  segments with per-band private accumulators is the natural accelerator; detect at runtime and
  fall back to numpy. Keeps the install light while using the fastest available path. Do not
  make it a hard dependency, and do not add a GPU path (CuPy/Torch) for a desktop viewer.

### 5. Do not repeat the synchronous-startup mistake

`build_physical()` already runs synchronously before the Qt event loop, which the perf review
identified as the cause of an apparently frozen GUI at launch. A 10⁸-segment metal pass is
minutes, so metal mode **must** build behind a visible window with progress (segments
processed) and a cancel. The status bar already carries messages; reuse that channel.

### 6. Measure, do not claim

Ship a `--stress N` generator mode producing a synthetic DEF at 10⁵ / 10⁶ / 10⁷ segments, and
record **measured** wall-clock and peak RSS per stage (parse, rasterize, cumsum) in the as-built
doc. The numbers above are estimates from operation counts and must be replaced by measurements
before the feature is called done. `config.DEFAULT_METAL_MAX_BINS` guards the grid memory
(≈16 MB/grid) with a warning naming the memory and the `--grid-size` that would fit.

## New and changed files

| file | purpose |
|---|---|
| `vlsi_viewer/raster.py` (new) | `Bins` — vectorized, band-parallel rasterizer. Qt-free, numpy only |
| `vlsi_viewer/assembly.py` (new) | `find_single_top`, `HierarchyAssembler` — block assembly, Qt-free |
| `vlsi_viewer/metal.py` (new) | `build_metal`, `MetalData`, `MetalLayer` — mirrors `physical.py` |
| `vlsi_viewer/parsers/routing.py` (new) | DEF + tech LEF → micron-normalized, **streaming** routing model |
| `vlsi_viewer/ui_metal.py` (new) | `MetalPanel` — layer checkboxes, scope, presets, cell-detail readout |
| `parsers/DEF/defNdr.py`, `defSPolygon.py` (new) | NDR rules; whole-polygon vertices |
| `parsers/DEF/{defParser,compiledRe,defNet}.py` | NDR section, `is_special`/`use`, polygon capture, streaming iterator, block-wise scan |
| `parsers/convert.py` | extract `instances_from_components` so a DEF is parsed once |
| `config.py`, `cli.py`, `ui_layout.py`, `ui_main.py`, `quickstart.py`, `README.md` | wiring and docs |

`physical.py` is left untouched. Its `walk()` is a closure over ~12 side-effect lists with 20+
tests pinning it; `assembly.HierarchyAssembler` provides the same frame composition for the
metal path instead of refactoring it.

## Architecture

    MetalData
        top_name, boundary_polys, grid_size, extent, rows, cols
        layers: list[MetalLayer]      # tech-LEF order, bottom -> top; the panel's order
        capacity_base, capacity_bot   # two grids, not twelve
        macro_block_layers: int
        routable: dict[str, ndarray]  # bool per layer; False where C_L == 0
        warnings: list[str]
        kinds() -> list[tuple[str, str]]       # combo contents
        heat(kind) -> ndarray                  # composed map, cached by kind string
        layer_util(layer, scope) -> float      # per-layer readout for the panel
        cell_detail(ix, iy, kind) -> dict      # D_L, C_L, U_L per layer + the group sum

`kind` grammar: `"L:M3"` = one layer, `"G:M1,M3,M5"` = a group, canonicalized by sorting on
`MetalLayer.index` so the cache key is stable.

Per-layer `D` grids are stored lazily per `(layer, scope)` so a layer carrying no power costs
one grid, not two; `all` is `signal + power` computed on demand.

**`heat()` must not return NaN.** `heatmap.grid_to_image` has no NaN handling — a NaN
propagates into the LUT index and yields garbage pixels. Zero-capacity cells return `0.0`.

**Render reuse.** `LayoutView` already funnels everything through `heat(kind)` — `HEAT_TYPES`
(`ui_layout.py:13`), `_on_type` (`:107`), `_autoset_range` (`:134`), `_on_hover` (`:152`),
`refresh` (`:215`). The seam exists: make the combo contents come from the source
(`self._kinds = source.kinds() if hasattr(source, "kinds") else HEAT_TYPES`) and keep using
`heat(kind)`. `_on_hover` is also where the cell-detail readout hangs. Add
`self._contour_enabled = hasattr(physical, "contour_for")` with `toggle_contour()` returning
immediately when False, and an `external_controls` flag so `MetalPanel` can adopt the min/max
and Fit widgets (which stay attributes of `LayoutView`, so existing tests still pass). Note the
import direction: `ui_layout` imports `physical`, so do not put a `kinds()` that imports
`HEAT_TYPES` onto `PhysicalData`.

## Rasterizer detail (`raster.py`)

The existing rasterizer cannot be reused: `physical.py:404-418` costs `O(bins touched)` per
shape with a per-shape allocation. At a 10 µm grid on a 20 mm die (2000×2000) one full-die
macro is 4·10⁶ bins — a 32 MB temporary and ~100 ms *each*.

**Axis-aligned rectangles** use the four-class difference-array decomposition above: exact,
`O(N + bins)` per layer, no per-shape term, no per-shape allocation.

**Diagonals and polygons take an exact second primitive.** A 45° segment inflated by
`(w+s)/2` is the Minkowski sum of the segment with an axis-aligned square — ≤3 rectangles plus
2 right triangles. Polygons use a scanline decomposition with the even-odd rule. Both reduce to
**trapezoid accumulation**: within one grid row, split the shape at every column line; each
strip lies in exactly one bin and its area is `(x1-x0)·(h(x0)+h(x1))/2` exactly, because `h` is
linear in `x` inside a slab. This is `O(bins touched)` but only for the minority of shapes that
need it. A bounding box is **not** acceptable: it over-counts a 10 µm diagonal by ~25×.

Anything else — a segment neither axis-aligned nor 45°, a zero-area polygon, a layer with no
usable width rule — is skipped, counted, and warned about once. An honest failure rather than a
silently wrong map.

## Parser work required

None of this code has run in production before, so these are corrections to unproven code.

**`NONDEFAULTRULES` is not parsed at all** — no dispatcher entry (`defParser.py:68-79`), no
regex, no class. Needs a section handler for `ruleName + LAYER layer WIDTH w [SPACING s]
[WIREEXT e]` producing a per-rule, per-layer lookup, reached from `DefWire.rule` (which holds
only a name today). Insert the key **after** `'TRACKS'`: the standard DEF order puts
`NONDEFAULTRULES` before `COMPONENTS`, so it is reachable even under the default config, and it
does not disturb `last_type`.

**Streaming.** Add an iterator form of the net/specialnet sections that yields parsed statements
without retaining them (see Performance §1). Existing accumulating callers keep working.

**Signal/power scope needs a `DefNet` field.** `NETS` and `SPECIALNETS` both call
`__statement_net(header)` and land in the same `self.__nets` dict, and `DefNet` records no
origin. Add `is_special`, and parse `+ USE` (`POWER|GROUND|SIGNAL|...`) so the selector can
prefer an explicit `USE` over section origin.

**Polygon area needs a new class.** `+ POLYGON` emits one edge per `DefSWire` and **drops the
closing edge** (`tests/test_def_nets.py:91-98` pins a 3-edge result for a 4-vertex ring), with no
polygon id — chaining the edges cannot recover the ring. Add `DefNet.polygons` /
`DefSPolygon(layer_name, pts)` capturing the full vertex list at parse time, **keeping the
per-edge `DefSWire`s** so existing tests still pass.

**Enabling net parsing changes where parsing stops.** `last_type` is the last *surviving* key
after the opt-out deletions (`defParser.py:88-102`): with defaults it is `COMPONENTS`, so the
parser returns before `PINS`/`SPECIALNETS`/`NETS` are reached. The metal path always constructs
`DefParser(path, parse_net=True, parse_specialnet=True, parse_ndr=True)` and **verifies by count
against the head** — `NETS n ;`, `SPECIALNETS n ;`, `NONDEFAULTRULES n ;` — warning on
mismatch, the pattern `convert.py:166-173` already uses. `instance_info_from_def` keeps its
flags, so existing flows are unchanged.

**`TlefParser` (routing layers).** The first two are silent-wrong-answer bugs, and both come
from the stanza being scanned line-by-line with an `elif` chain. Real tech LEFs use these forms
routinely — a 90 nm example layer carries four `SPACING` clauses, and `SPACINGTABLE` is the norm
where the 90 nm/130 nm rules were written as tables rather than a single spacing.

- **`SPACINGTABLE` rows clobber the default width.** `re_layer_width` is `^\s*WIDTH\s+…`, and the
  rows inside a spacing table look exactly like that:
  `WIDTH 0.00  0.15 0.15 0.15 0.15`. The layer's `width` becomes `0.00` — or a table
  breakpoint — and every wire on that layer computes zero area. The rows are *line-initial*, so
  anchoring does not save it.
- **`SPACING` is last-match-wins.** The scan re-assigns `spacing` on every matching line, so a
  layer with several qualified clauses keeps the *last*. In the 90 nm example the clauses are
  `0.180`, `0.18 LENGTHTHRESHOLD 1.0`, `0.22 RANGE 0.3 10.0`, `0.60 RANGE 10.05 100000.0`, so
  `spacing` becomes `0.60` — **3.3× the default** — inflating every wire's keep-out and making
  the map read far too congested.
  Correct rule: the **unqualified `SPACING x ;` is the default** — take it; else the minimum over
  all clauses; else the spacing table's smallest entry; else `P - W`. The minimum is exactly what
  the one-track-pitch argument needs.
- **`LEF58_TYPE` clobbers the type.** `re_LEF58_type` writes into the same field the base `TYPE`
  uses (`lefParser.py:56-57` vs `:44-45`), so a routing layer carrying
  `PROPERTY LEF58_TYPE "TYPE NWELL ;"` loses `'ROUTING'` and vanishes from the map. Give
  `LefLayer` a separate `lef58_type` field.
- **`WIDTH` may be absent.** `LefLayer.width` initializes to the int `0`. Fall back to
  `min_width`; if both are 0 the layer is `usable=False`, its segments are skipped and counted,
  and its checkbox is disabled with a tooltip. Not a silent zero-width inflation.
- **Harden `re_layer_direction`/`re_layer_width`/`re_layer_spacing` to accept `\s*;`.** They
  demand whitespace after the value, so `DIRECTION VERTICAL;` (no space) yields `''` — which
  would mislabel the H/V grouping in the GUI.
- Filter to `type == 'ROUTING'`. `layers` returns *every* `LAYER` — cut, masterslice, overlap,
  implant. OpenROAD reports reading a Nangate45 LEF as "22 layers, 27 vias, 135 library cells",
  so a real file has roughly twice as many layers as routing layers.
- **Layer order is LEF file order**, conventionally bottom-to-top. Do not sort.

Confirmed *not* a problem: the regexes are `^\s*`-anchored, so a mid-line `WIDTH` inside
`MINIMUMCUT 2 WIDTH 0.1 ;` cannot overwrite the default width. The `SPACINGTABLE` case is the
opposite — those rows are line-initial.

The fix for the table forms is to scan the stanza with awareness of the nested
`SPACINGTABLE … ;` block — consume it as a unit and take its minimum — rather than treating
every line independently. That is a contained change to `TlefParser.__parseStart`'s inner loop,
and the fixture below must reproduce the real shapes or it will not catch either bug.

**Other conversion details:** `DefSWire` `+ RECT` corners are **not** normalized (unlike
`DefBlockage`), so min/max them. `DefTrack` gives `offset`/`step`/`num_tracks` in raw DB units
with no `db_unit` attached. Fix the lost trailing NDR clause in `__extractNets`:
`+ ROUTED M2 ... + NONDEFAULTRULE X ;` currently drops the rule because only `header` is
searched.

### Real DEF shapes the parser must survive

Checked against real routed DEF excerpts, one at a time, against the actual patterns in
`DEF/compiledRe.py`. Two are genuine gaps; the rest are recorded so the sample emits them.

**Gap 1 — glued `*` coordinates are silently dropped.** Real DEF writes both
`(-200 -200 )(200 *)` *and* the compact `(1760*)`, `(*703600)` forms. `WIRE_POINT` is
`\(\s*(?P<x>…)\s+(?P<y>…)\)`, and on `(1760*)` there is no whitespace between `1760` and `*`,
so **the match fails** — the point is dropped and the wire geometry is wrong, with no error.
`(200 *)` and `(-200 -200 )` are fine. The fix is two extra alternatives for the glued forms,
but the separator must stay `\s+` for the number–number case: with `\s*`, a malformed `(1234)`
would backtrack into `x=123, y=4` and mis-parse silently instead of failing loudly.

**Gap 2 — `routeWidth 0` means "use the layer default".** Real special wiring writes
`NEW M2 0 + SHAPE FOLLOWPIN ( … )`; the `0` is not a zero-width wire. Taken literally it
produces a zero-area strip for every followpin, i.e. most of the power grid silently missing
from the map. Treat `width == 0` on a special wire as "unset" and fall back to the layer's LEF
width.

**Verified already correct** (worth stating so nobody "fixes" them):

- `+ SHAPE` **after** `routeWidth` in the routed form. `SHAPE_OR_MASK` is applied both before
  the alternatives and again after `(?P<width>\d+)`, so `NEW M2 0 + SHAPE FOLLOWPIN ( … )`
  matches. `+ SHAPE RING + POLYGON M1 …` (shape before the form) also matches.
- `WIRE_LAYER` stops before `(`, so the glued `+ ROUTED M2( 1740 702395 )` form — no space
  between layer and paren, and no routeWidth — parses as layer `M2` plus its routing points.
- A via orientation code directly after the via (`VIA23_1cut_…_2_1 W`) is captured by
  `re_wire_token`'s optional `via_orient`.
- Layer names are lowercase in some real DEFs (`m1`, `met1`); `WIRE_LAYER` accepts them, and the
  code must never match on layer *names* anyway.

**Minor, harmless for this metric but worth a test:** a real power net can open with
`(* GND )` — a `*` component name and no space after the paren. `re_net_conn` requires
`\(\s+NAME\s+NAME\s+\)`, so it does not match and `connect_pins` comes out empty. Connections
do not affect metal density, so this is a note rather than a fix; it must not, however, throw.

**NDR section shapes.** The DEF 5.8 form (the authority here, matching
`LEF_DEF_syntax reference.md:683-701`) writes one `+ LAYER` line per layer with **no semicolons
between them**, terminated by a single `;` on the rule:

    NONDEFAULTRULES 1 ;
        - analog_track
          + LAYER li1 WIDTH 900 SPACING 2700
          + LAYER met1 WIDTH 900 SPACING 2700
          + LAYER met2 WIDTH 900 SPACING 2700
        ;
    END NONDEFAULTRULES

`__read_statement` already joins to `;`, so the whole rule arrives as one statement and the
split on `+ LAYER` works. Values are **DB units** (`900` at dbu 1000 = 0.9 µm), so they need the
same division as coordinates. A `layer M1 / width 1 ; / spacing 0.6 ;` variant also circulates
on forums — it is *not* DEF 5.8 and is most likely another tool's format; if it appears, skip it
with a warning and never raise, the same discipline as `__extractTracks`.

**Scale:** real designs carry hundreds of special nets even when small (`SPECIALNETS 237 ;` in one
published example), and followpins alone put a wire on every standard-cell row. The sample must
have a realistic special-net count for the PG stripe/followpin path to be exercised meaningfully,
and a many-net fixture belongs in the tests.

## Assembly of several DEFs

Each `--def` is a complete design. They are converted to blocks and assembled into one
hierarchy exactly as the `json`/`def` physical flows do, then the single root is found.

Frame composition **is** sound for wires: `coordinateProcess.dbTransform` is, for all eight
orientations, a rotation by a multiple of 90° plus an axis reflection about the placement
origin. An axis-aligned rectangle maps to an axis-aligned rectangle (min/max of the transformed
corners is exact), a segment maps to a segment, and the direction class is preserved (axis-x ↔
axis-y under 90°, ±45° stays ±45°). The translation-only fast path (`physical.py:227-256`) is a
plain offset and is sound for both. A sub-block DEF's wiring is in that block's local frame and
composes through the same chain as its instances. Reproduce the composition order exactly
(`reversed(chain)`, innermost first).

`assembly.find_single_top` performs the root check before any walking and raises
`ValueError("metal mode requires exactly one top-level block; found N: A, B")` — the existing
`physical.py:188-195` logic with the mode name generalized. `cli.main` already catches it,
prints `error: ...` and returns 1 without opening a window (`cli.py:224-226`).

A referenced block with no DEF passed is a leaf: it contributes no wires and no macros, and is
reported once as a warning rather than silently omitted.

## CLI

    python main.py metal --def top.def sub.def --lef cells.lef --tech-lef tech.lef
    python main.py metal --def core.def --lef cells.lef --tech-lef tech.lef --grid-size 5
    python main.py metal --def core.def --lef cells.lef --tech-lef tech.lef \
        --macro-block-layers 4 --min-segment-length 0.2

New subparser following the existing recipe (`cli.py:56-119`): `--def` (required, `nargs="+"`),
`--lef` (`+`), `--tech-lef` (`+`), `--grid-size`, `--macro-block-layers` (default 4),
`--min-segment-length` (default = the layer pitch), `_add_shared`. **No `--compare_*`, no
`--physical_mode`, no `--contour_gap`** — absent flags rather than runtime rejections, which is
how the existing modes express their capabilities. A `metal` branch in `resolve_inputs` returns
in-memory data (like `def`/`verilog`, nothing is written); `main` builds `MetalData` behind the
shown window and passes it to `MainWindow`.

`quickstart.py` gets a `metal` shortcut — but only **after** the sample files are committed,
because `test_quickstart_shortcuts_are_valid` asserts every referenced sample exists. Also check
`main`'s sample-existence guard, which picks the first path-looking argument
(`quickstart.py:81-84`), against the new argument order.

## GUI layout (for review)

No hierarchy widgets at all in metal mode: the search field, match-mode combo, Find button,
min-instances spinner and include-macros checkbox are **not built**, and neither is the tree or
the `Density%` column. The window is the map plus one panel.

    +=========================================================================================+
    | VLSI Hierarchy Analyzer                                                    [–] [ ] [X]  |
    +--------------------------------------------------------------------------------+========+
    |                                                                                | METAL  |
    |                                                                                | DENSITY|
    |               +=====================================================+          |--------|
    |               |                                                     |          | Scope  |
    |               |                                                     |          | [Sig+  |
    |               |                                                     |          |  Power]|
    |               |                    LAYOUT VIEW                      |          |--------|
    |               |              M1..M12 metal density                 |          | Min    |
    |               |              thermal colour map                   |          | [0.000]|
    |               |                                                     |          | Max    |
    |               |        (no tree, no contour, no search,             |          | [1.000]|
    |               |         no min-instances, no macros toggle)         |          | [ Fit ]|
    |               |                                                     |          |--------|
    |               |                                  +---------+        |          | Layers |
    |               |                                  | legend  |        |          | M12 V  |
    |               |                                  | navy -> |        |          |  .42 x |
    |               |                                  | white   |        |          | M11 H  |
    |               |                                  +---------+        |          |  .55 x |
    |               |                                                     |          | M10 V  |
    |               |                                                     |          |  .31 . |
    |               +=====================================================+          |  ...   |
    |                                                                                | M1  H  |
    |                                                                                |  .04 x |
    |     +------------------------------------------------------------------------+ |--------|
    |     | CELL DETAIL   M3 at (ix=42, iy=17)   x=425.0 y=175.0                   | | [All H]|
    |     |   D = track-pitch area consumed       C = routable area in this cell   | | [All V]|
    |     |   M1  D 0.061  C 1.000  U 0.061                                        | | [None] |
    |     |   M3  D 0.940  C 1.000  U 0.940   <- hovered cell on the selected layer| |--------|
    |     |   M5  D 0.240  C 1.000  U 0.240                                        | | Group  |
    |     |   ----------------------------------------------------------------     | | M1+M3+ |
    |     |   GROUP M1+M3+M5   sumD 1.241 / sumC 3.000 = 0.414  (kept-out/clip)    | | M5     |
    |     |   capacity: macros block the bottom 4 layers                           | | 0.414  |
    |     +------------------------------------------------------------------------+ |--------|
    +--------------------------------------------------------------------------------+========+
    | 200x200 grid @ 10.0 um  12 layers  top core  |  parse 12.4s  raster 3.1s  (streamed)  |
    +=========================================================================================+

The **CELL DETAIL** box is the answer to "how is the density calculated, and is it reasonable":
it shows the hovered cell's bin index, the per-layer `D`, `C` and `U` that produced the pixel,
the group's `ΣD / ΣC` arithmetic with the result, and the capacity policy in force. The status
bar keeps a compact one-liner plus the stage timings so a slow run is self-explaining.

Other layout notes:

- **Layer list is bottom-to-top** (M1 first, panel reads M12→M1 top-down as drawn), tech-LEF file
  order, with each layer's mean `U` beside it so one layer can be read without switching to it.
- **Presets earn their ~10 lines**: your doc's own example is "M1 M3 M5 grouped as horizontal",
  six clicks by hand or one with the button. They only set checkboxes.
- **Unusable layers** (no width rule in the tech LEF) show a disabled checkbox with a tooltip
  rather than being absent, so the user can see why a layer is missing.
- `heatmap.grid_to_image` gets an optional `mask` so bins with no capacity render neutral grey,
  distinguishable from "0 % used".

## Sample data (`sample_data/metal/`)

The existing sample die is 122 x 88 µm — 117 cells at a 10 µm grid, which cannot show a
congestion pattern. Use a ~2 mm block-scale die (200 x 200 cells).

`generate_metal.py`, following `generate_eda_sample.py`'s shape (docstring stating intent,
constants at the top, one writer per file, a `verify()` that re-parses through the real pipeline,
`main()` printing a summary):

1. **Tech LEF** — 1P12M: `M1,M3,M5,M7,M9,M11 HORIZONTAL`, `M2,M4,M6,M8,M10,M12 VERTICAL`, with
   pitches widening by height as real stacks do. Modelled on Nangate45's measured track pitches
   (0.14 / 0.19 / 0.14 / 0.28 / 0.28 / 0.28 / 0.80 / 0.80 / 1.60 / 1.60 µm) and sky130's
   (0.37 / 0.48 / 0.74 / 0.96 / 3.33 µm), so the sample spans both the `W + S == P` case and the
   `W + S < P` case that Correction 1 exists for. It must deliberately include:

   - a layer with **several qualified `SPACING` clauses** (`… LENGTHTHRESHOLD 1.0`,
     `… RANGE 0.3 10.0`), ordered so the largest comes last — the shape that catches
     last-match-wins;
   - a layer with a **`SPACINGTABLE PARALLELRUNLENGTH`** block — the shape that catches the
     default-width clobbering;
   - a `MINWIDTH`-only layer, and `DIRECTION VERTICAL;` with no space before the semicolon;
   - cut, masterslice and overlap layers, so the routing-layer filter is exercised.

   The sample is more valuable as a parser stress case than as a pretty picture, so these variants
   are mandatory rather than decorative — every one of them corresponds to a bug above.
2. **Macro LEF** — the 20-cell library (logic across SVT/LVT/ULVT, an SRAM `CLASS BLOCK`,
   FILL/TAP/DCAP), reusing the existing generator's tables where possible.
3. **`sub.def`** — a leaf block with local TRACKS, macros, its own `NETS`, and a `SPECIALNETS`
   followpin plus one PG ring as `+ POLYGON`.
4. **`top.def`** — ~2 mm die, four `sub` instances at **four different orientations** (so frame
   composition for wires is exercised by real data), `NONDEFAULTRULES` written in the real
   no-semicolon `+ LAYER` form with DB-unit values (a `2W2S` clock rule and a wider PG rule, both
   referenced by nets), all 12 `TRACKS` with direction matching the LEF, SRAM macros sized so the
   M1–M4 blocking is visible, grid-style PG stripes (`+ RECT` and one `+ POLYGON` ring), and
   `NETS` routed along a smooth target-utilization field so the map has structure to find —
   including ~2 % 45° jogs and a sprinkling of non-preferred-direction jogs, so both paths are
   exercised end to end.

   It must also emit the real-world forms from the parser section, because those are what make the
   tests meaningful rather than decorative:

   - **compact `*` coordinates** (`(1760*)`, `(*703600)`) alongside the spaced form — the shape
     that catches Gap 1;
   - a **PG followpin on every row**, written `NEW M2 0 + SHAPE FOLLOWPIN ( … )` with
     `routeWidth 0` — the shape that catches Gap 2, and realistic besides, since followpins alone
     put a wire on every standard-cell row;
   - a few hundred **special nets**, and one net opening with `(* GND )`;
   - at least one layer referenced by its **lowercase** name.
5. **`orphan.def`** — a standalone design with a different `DESIGN` name, for the multiple-root
   error test.
6. **`--stress N`** — synthetic DEF at 10⁵/10⁶/10⁷ segments plus a `benchmark()` that prints
   per-stage wall clock and peak RSS. Not committed.

`verify()` asserts, in order of strength:

1. **Identity, rasterizer-free:** `Σ_bins D_L ≈ Σ_segments w_eff · length` per layer to 1e-6
   relative. Catches any DB-unit/micron scaling bug and any missing inflation.
2. **Intent match:** mean `U_L` over routable bins within ±0.05 of the generator's own per-layer
   target. Ties the metric to design intent.
3. **Distribution shape** (per layer and for the H/V/all groups): `0 ≤ U ≤ 1`; mid-range share
   > 0.25; **saturated share < 0.20** (the classic failure — summing layers, or double
   inflation, pegs everything near 1.0); > 50 distinct values; and
   `roughness = mean(|diff(U, axis=1)|)` < 0.15, the per-bin-noise guard from
   `generate_physical.py:429`.
4. **Macro blocking is layer-aware:** mean `U` over an SRAM footprint is low on M5+ and high
   relative to it on M1–M4 — the direct test that `--macro-block-layers` is doing something.
5. **Layer metadata survives the parser:** every routing layer's width/spacing/pitch as seen by
   `TlefParser` equals what the generator wrote — specifically including the four-`SPACING`-clause
   layer and the `SPACINGTABLE` layer. This is the end-to-end regression check for the two silent
   parser bugs, and it runs on every sample regeneration. Plus **TRACKS**
   `step ≈ pitch × dbu` per layer, with direction consistent with the LEF.
6. **NDR actually applied:** each rule is referenced, and NDR wire area exceeds the equivalent
   layer-default area by the expected multiplier.
7. **PG rings** close, have positive shoelace area, and appear only in the `power` scope.
8. **Jogs:** the generator plants known jogs; verify they are dropped by the default threshold
   and counted, and that `--min-segment-length 0` keeps them.
9. **Hierarchy:** one hand-computed `sub.def` wire lands in the expected **global** bin for a
   rotated instance, and `Σ D_L` over the flat assembly equals the sum of per-block totals.
10. **Idempotent:** regenerating produces byte-identical files (seeded `random.Random(0)`).

## Tests

| file | covers |
|---|---|
| `tests/test_raster.py` (new) | rect in one bin; rect over 4 bins hand-computed; a 300-bin-long thin rect (guards against any `O(shape x patch)` regression); clipping at the extent with area conserved; degenerate/negative coords; two overlapping rects **sum** (pins "sum not union"); 45° segment area == `L·t` with mass on the correct side plus a 3-bin analytic case; 4-vertex ring and a concave ring; **band splitting** — a rect crossing a band boundary gives the same grid single-threaded and band-parallel; float32 vs float64 reference within 1e-5 |
| `tests/test_metal_metric.py` (new) | hand-computed `D = (w+s)·L`; the worked example verbatim; NDR `2W2S` doubling; **per-layer capacity**: a macro raises `U` on blocked layers only, and `--macro-block-layers 0` disables it; the group formula uses `ΣD/ΣC` with unequal capacities (assert it differs from the naive mean of `U`); zero-capacity → `U == 0` and no NaN; `D > C` clips to 1.0; signal/power/`USE` scope; **non-preferred-direction segment on a vertical layer rasterizes correctly** (the jog test); micro-segment drop threshold and `--min-segment-length 0`; `NETS 0 ;`; gzipped DEF ≡ plain; no `UNITS` warns; no TRACKS still works; VIA-only net contributes 0 and is counted; `kinds()` order bottom-to-top |
| `tests/test_def_ndr.py` (new) | per-layer WIDTH/SPACING/DIAGWIDTH/WIREEXT; `HARDSPACING`; `VIA`/`VIARULE`/`MINCUTS` names; the **real no-semicolon `+ LAYER` form** joins into one rule with DB-unit values; a rule naming a layer subset; net-level `+ NONDEFAULTRULE` resolves; `TAPERRULE` still wins; the previously-lost trailing NDR clause; `NONDEFAULTRULES` after `COMPONENTS` pinned as ignored-with-warning; a non-DEF `layer M1 / width 1 ;` variant warns and is skipped without raising; `is_special`/`use` tagging; `DefSPolygon` exists *and* `swiring` still holds the edges |
| `tests/test_def_nets.py` (extend) | the real-DEF forms: `(1760*)` and `(*703600)` give the same geometry as their spaced equivalents and do **not** vanish; a malformed `(1234)` still fails to match rather than backtracking into 123/4; `NEW M2 0 + SHAPE FOLLOWPIN ( … )` yields a wire of the layer's LEF width, not zero area; `(* GND )` leaves `connect_pins` empty without raising; a DEF with several hundred special nets parses |
| `tests/test_def_stream.py` (new) | the streaming iterator yields exactly the statements the accumulating path stores, for a multi-net DEF; memory-shaped check that the iterator does not retain (a counter, not a memory probe); malformed/truncated section ends cleanly rather than hanging |
| `tests/test_metal_assembly.py` (new) | TOP+SUB translation into the right global bin; a rotated frame with a 45° wire (position and direction class); multiple roots → `ValueError` matching `"exactly one top-level"`; referenced-but-missing block warns; duplicate `top_name` merges |
| `tests/test_metal_cli.py` (new) | defaults incl. `grid_size == 10` and `macro_block_layers == 4`; required-flag `SystemExit`s; `--compare_def`/`--physical_mode`/`--contour_gap` **absent** (pins scope); `resolve_inputs` returns in-memory data and writes nothing |
| `tests/test_metal_gui.py` (new) | offscreen, `QT_QPA_PLATFORM` set before PyQt5 imports: `MetalPanel` builds N checkboxes with M1 first; checking M1+M3 yields a `G:` kind and changes the pixmap; scope combo changes the pixmap; `All H` checks exactly the horizontal layers; **no hierarchy toolbar is built** (search field / min-instances / include-macros absent); `MainWindow(design=None, metal=...)` has no tree in the central widget; **cell detail updates on hover and its numbers reconcile** (`ΣD / ΣC` equals the displayed `U`, and equals the pixel's value); a disabled checkbox appears for an unusable layer; `toggle_contour` is a no-op; legend still parents to the view |
| `tests/test_parsers_eda.py` (extend) | tech LEF against a **real-shaped fixture**, not just the sample: routing-only filter with cut/overlap layers present; **a stanza with four `SPACING` clauses returns the unqualified default, not the last** (the 90 nm shape: 0.180 / 0.18 LENGTHTHRESHOLD / 0.22 RANGE / 0.60 RANGE → must be 0.18, not 0.60); **a `SPACINGTABLE PARALLELRUNLENGTH` block leaves the layer `width` intact** (must not become 0.00); `LEF58_TYPE` not clobbering `type`; missing `WIDTH` → `MINWIDTH`; `DIRECTION VERTICAL;` without a space; `f_L` computed from pitch; layer order preserved |
| `tests/test_metal_sample.py` (new) | generator loaded by path (`spec_from_file_location`, as `test_sample_generator.py` does); `verify()`; per-layer direction/pitch/width/spacing vs spec; every routed segment's layer is `TYPE ROUTING` with a usable width |

The existing 168 tests must stay green throughout.

## Ordered implementation

| phase | deliverable | gate |
|---|---|---|
| 0a | **Validate against real files first.** Obtain a real tech LEF and a real routed DEF (Nangate45 and sky130 are both open and small), drop them in a scratch dir, and run `TlefParser` / `DefParser` over them to confirm or refute the four findings — the two tech-LEF bugs and the two DEF gaps | a written note recording which findings reproduced and which did not, **before** any fix is written |
| 0b | parser: `compiledRe` additions + regex hardening, `defNdr.py`, `defSPolygon.py`, `DefNet` fields, NDR section, `is_special`/`use`, polygon capture, NDR-search fix, `WIRE_POINT` glued-`*`, `routeWidth 0` | `test_def_ndr.py`; `test_def_nets.py`/`test_def_tracks.py` green |
| 1 | `raster.py` (single-threaded numpy first, bands as a flag) | `test_raster.py` |
| 2 | `routing.py` — conversion + **streaming iterator** + block-wise scan | `test_def_stream.py`; existing parser tests unchanged |
| 3 | `assembly.py` | `test_metal_assembly.py` |
| 4 | `config.py` + `metal.py` + per-layer capacity | `test_metal_metric.py` |
| 5 | `--stress` mode + **measure and record** parse/raster numbers | numbers in the as-built doc |
| 6 | `sample_data/metal/` generator + files | `test_metal_sample.py` |
| 7 | `cli.py` metal subcommand, `quickstart.py`, README | `test_metal_cli.py`; `test_quickstart_shortcuts_are_valid` |
| 8 | `ui_layout.py` source-agnostic + `external_controls` + contour flag; `ui_metal.py`; `ui_main.py` (no toolbar, progress); `heatmap` mask | `test_metal_gui.py` + the whole GUI suite |

Phase 5 sits before the sample generator deliberately: if the measured numbers miss the 10⁷
target, that changes the design, and it is cheaper to find out before the samples are built on
top. Phases 0–4 are pure library work with no GUI or CLI surface, which makes "must not impact
existing function" demonstrable rather than asserted.

## Known limits to document

- **Throughput is parser-bound.** Rasterization is `O(N)` with a small constant; reading 10⁸
  wiring statements with a Python parser is the wall. Block-wise scanning and `str.split` push it
  as far as pure Python reasonably goes; beyond that the honest answer is "this DEF is too big
  for the desktop viewer" rather than a hang. Streamed with progress so it degrades visibly.
- **Via metal is not counted.** A via's enclosures need the DEF `VIAS` section and LEF
  `VIA`/`VIARULE`, none of which is parsed. Vias are counted and reported rather than silently
  dropped.
- **Non-preferred jogs** are dropped below a threshold, and their area-to-track equivalence is
  approximate where they are kept (see above).
- **Macro blocking layer count is a parameter, not a parsed fact.** The real answer lives in LEF
  `OBS`, which is not parsed; `--macro-block-layers` defaults to 4 and is the user's to set.
- **Overlapping expansions sum**, which is conservative — intentional, and necessary for the
  track-pitch argument.
- **Grid resolution.** At 10 µm a cell holds ~50–100 tracks on a 0.1–0.2 µm pitch, the intended
  noise/resolution balance, but hotspots below 10 µm are averaged away. A router's own gcell is
  typically 1–5 µm, so `--grid-size` should be easy to lower.
- **No real DEF was available**, so realism rests entirely on the sample generator, and the
  performance numbers are estimates until phase 5 measures them.

## Verification

1. `python sample_data/metal/generate_metal.py` — self-verify prints per-layer stats and asserts
   them; non-zero exit on failure.
2. `python sample_data/metal/generate_metal.py --stress 10000000` — prints per-stage wall clock
   and peak RSS; compare against the recorded numbers.
3. `python main.py metal --def sample_data/metal/top.def sub.def --lef sample_data/metal/cells.lef
   --tech-lef sample_data/metal/tech.lef` — window opens, **no toolbar, no tree, no contour**, 12
   checkboxes bottom-to-top, map fills the window.
4. Picture sanity: PG stripes read near-white on their layers; the density field shows as a
   gradient not noise; `All H` vs `All V` visibly differ; the legend's 1.0 tick is the top.
5. **Hover reconciliation by hand:** pick a cell, confirm the CELL DETAIL box's `ΣD / ΣC` equals
   the displayed `U` and matches the pixel colour; toggle `--macro-block-layers 0` and watch `C`
   and `U` change over an SRAM.
6. `--grid-size 5` changes resolution and the hover readout still matches the pixels.
7. Multi-root: `metal --def sample_data/metal/top.def sample_data/metal/orphan.def ...` prints
   `error: ... found 2 ...` and exits 1 with no window.
8. `--def top.def` alone (no `sub.def`) still assembles and warns about the missing block.
9. `python -m pytest -q` — 168 existing tests green; `json`/`def`/`verilog` untouched
   (`instance_info_from_def` keeps its flags, so its parse still stops at `COMPONENTS`).
10. `python quickstart.py metal` runs the sample.

## Risks

- **The rasterizer is the highest-risk code.** A subtly wrong vectorized decomposition still
  produces a plausible map, which is why the property tests and the rasterizer-free identity
  check in `verify()` exist. The band-parallel path is the same algorithm with a different
  partition, and is pinned against the single-threaded result.
- **The performance target may not be reachable in pure Python** at the top of the stated range.
  Phase 5 exists to find that out early and cheaply; the fallback is clear reporting and honest
  documentation, not a silent hang.
- **`TlefParser` has never seen a real tech LEF.** Its `LEF58_TYPE` collision and missing `WIDTH`
  would produce a wrong map rather than an error, so both get explicit tests and a visible
  warning instead of a silent fallback.
- **Enabling net parsing changes the DEF parser's termination point.** Contained by giving the
  metal path its own explicit flags, leaving `instance_info_from_def` alone, and pinning the
  existing flows with a test.
- **No real DEF available**; if you can supply one later, that is the highest-value follow-up.

## Reference material

Real tech LEFs worth copying the *shapes* from when writing the sample and the test fixture:

- **Nangate45** tech LEF — `flow/platforms/nangate45/lef/NangateOpenCellLibrary.tech.lef` in
  OpenROAD-flow-scripts, plus the matching macro LEF; described in the
  [platform bring-up guide](https://openroad-flow-scripts.readthedocs.io/en/latest/contrib/PlatformBringUp.html).
  Measured track pitches per layer appear in OpenROAD's global-router logs, e.g.
  [est_rc_cugr1.ok](https://github.com/The-OpenROAD-Project/OpenROAD/blob/76e9543ee9a8e133d3e194218a9302309284470f/src/grt/test/est_rc_cugr1.ok).
- **sky130** tech LEF — `flow/platforms/sky130hd/lef/sky130_fd_sc_hd.tlef`, provenance documented
  in [lambdapdk's sky130 README](https://raw.githubusercontent.com/siliconcompiler/lambdapdk/HEAD/lambdapdk/sky130/README.md);
  per-layer pitches in
  [clock_route_alpha.ok](https://github.com/The-OpenROAD-Project/OpenROAD/blob/1897c306b5f2688f80bb6a53672a2e0c99c3c774/src/grt/test/clock_route_alpha.ok).
  Note sky130 names its layers `li1`, `met1`…`met5`, not `M1`… — good evidence that the code must
  take layer order from the file and never parse layer *names*.
- The **four-`SPACING`-clause stanza** (`0.180` / `0.18 LENGTHTHRESHOLD` / `0.22 RANGE` /
  `0.60 RANGE`) and the LEF layer field definitions come from
  [this LEF walkthrough](https://ieda.oscc.cc/train/eda/chip-circuit/Part_2-chip_files/2_3_LEF.html).
- The **`SPACINGTABLE PARALLELRUNLENGTH`** syntax, a worked 90 nm table, and the width/PRL lookup
  procedure come from
  [this 90 nm DRC reference](https://www.iccircle.com/static/upload/img20250721225931.pdf).
- The LEF `OFFSET` and `SPACINGTABLE` usage on sky130 met1, and OpenLane's `tracks.info` derivation
  (`<layer> X|Y <offset> <pitch>`), are in the
  [PDK porting doc](https://raw.githubusercontent.com/chiplicity/openlane/5d781512eead37021cc4e7c86907074846b8fcdd/docs/source/PDK_STRUCTURE.md).

DEF shapes worth copying from:

- The authoritative **[LEF/DEF 5.8 Language Reference](http://coriolis.lip6.fr/doc/lefdef/lefdefref/DEFSyntax.html)**
  — the same one `dev_plan/LEF_DEF_syntax reference.md` follows.
- A **routed `SPECIALNETS` block** with the compact coordinate forms, in
  [this floorplan-compiler thesis](https://ir.lib.uth.gr/xmlui/bitstream/handle/11615/13779/P0013779.pdf?sequence=1&isAllowed=y):
  `+ ROUTED m1 100 (-200 -200 )(200 *)` / `NEW m1 100 (-200 200 )(200 *) + USE GROUND ;`.
- **`+ SHAPE FOLLOWPIN` with `routeWidth 0`** and a `SPECIALNETS 237 ;` section, in
  [this DEF overview](https://data.ivlsi.com/design-exchange-format-def-in-vlsi-physical-design/).
- **Routed-segment and via forms** including the glued `*` coordinates
  (`NEW M4(75 702300)(1760*)`, `(*703600)`) and `TRACKS` guidance, in
  [this DEF tutorial](https://ieda.oscc.cc/en/train/eda/chip-circuit/Part_2-chip_files/2_4_DEF.html)
  and [this TRACKS write-up](https://blog.csdn.net/soulermax/article/details/148235273).
- **`NONDEFAULTRULES` in the no-semicolon `+ LAYER` form**, in
  [this EDA forum thread](https://bbs.eetop.cn/thread-439190-1-424.html).

**Caveat on provenance:** `raw.githubusercontent.com` and `github.com` are both blocked from this
environment, so none of these files could be downloaded and read directly — everything above is
from search-result excerpts. The two tech-LEF bugs and the two DEF gaps are derived from the
*documented shapes* against the code's actual regex and `elif` behaviour, which is a solid
inference but not a measurement. So the first task of phase 0 is to drop a real tech LEF and a real
routed DEF into a scratch directory and run `TlefParser` and `DefParser` over them, before trusting
any of these fixes. That is the cheapest possible way to convert this section from inference to
fact.

---

# Phase 0a corrections (measured, not inferred)

The findings above were inferred from documented syntax read through search results, because the
upstream file hosts were unreachable at planning time. `raw.githubusercontent.com` proved
reachable from the shell, so they were checked against a real Nangate45 tech LEF and a real
routed OpenROAD DEF before any fix was written. Full detail in
`dev_plan/metal_density_asbuilt.md`. Three corrections to the sections above:

*Superseded — "Gap 1, glued `*` coordinates".* Not present in real output. The real DEF writes
`( 53770 * )` and `( * 57540 )`, which the current regex already handles; `\(\*` and `[0-9]\*\)`
both occur zero times. The glued forms came from a tutorial, not from a tool. Keep the fix as
cheap defensive robustness with a test, but do **not** describe it as a real-world defect.

*Superseded — "Gap 2, `routeWidth 0` means use the layer default".* **Reversed.** Width 0 marks a
**via placement** — `NEW metal3 0 + SHAPE STRIPE ( 62280 61600 ) via3_4_960_340_1_3_320_320` — a
single point plus a via, with no wire. Zero area is correct. The planned fallback would have
manufactured a phantom wire at every PG via, inventing metal in the most visually prominent part
of the map. Correct rule: `routeWidth 0` contributes no wire area and is counted as a via.

*Superseded — the severity of the `SPACINGTABLE` bug.* It is worse than "a table row clobbers the
width". Measured on the real LEF, **9 of 10 routing layers have `spacing == 0.0`** because they
declare a `SPACINGTABLE` and no plain `SPACING` clause at all, and the parser has no table reader.
The width clobbering is real but latent — Nangate45 writes `WIDTH` after the table, repairing it.

**Added — zero-length segments.** 51 % of the `DefWire` objects built from the real DEF (1054 of
2068) are zero-length via points. They must contribute no area *and take no end extension*, or
each becomes a phantom `w x w` square. They are also the cheapest performance win available:
dropping them at parse time halves `N` for every real DEF.

**Added — `f_L` is load-bearing on the real library.** With correct spacings, `f = (W+S)/P` is
1.0 for most Nangate45 layers but 0.964 for `metal1` and **0.737 for `metal2`** (`W+S = 0.14`
against `P = 0.19`). Without the normalisation a fully-utilised `metal2` would read 0.74.
