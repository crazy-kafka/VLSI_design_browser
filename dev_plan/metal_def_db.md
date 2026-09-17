# Metal mode: an intermediate db, so a map rebuild skips the routing parse

A chip-level metal run is a ~28-minute DEF parse for a map that is ~0.6 MB of grids. Opening it
again on the same DEF costs the whole parse again. Three CLI arguments fix that:

- `--dump-db DIR` (`--dump_db`) — one db per DEF input, named from the DEF (`A.def.gz` → `A.def.db`);
- `--db FILE...` — load dbs, usable **with** `--def`, so an updated DEF is the only one re-parsed;
- `--dump-only` — write the dbs and exit, so several designs can be dumped in parallel and a later
  GUI run reads only dbs.

Measured basis (09-16 run, `dev_plan/issue/real_design_log_0916.md`): routing 1,696.70 s of
1,785.87 s; components 66.38, cell-index 12.11, capacity 0.76, blockage 9.90. Removing the routing
read removes ~95 % of the wall; the stages that remain are ~23 s.

## The contract

**The db holds DEF-derived facts only.** No LEF-derived value is stored, so no stored number can
disagree with the LEF in front of the user: the layer table, the filtered-layer list, the capacity
grid and the blockage are rebuilt from the live LEFs on every run. The db records the LEFs'
*identity* (`path`/`size`/`mtime_ns`), used to refuse a db, never to replace a LEF.

**Stored per block**: the routing grids keyed by layer **name** and scope, `totals`,
`layer_stats` (rows keyed by layer name), the text stats, the block-level warnings, the block's own
frames, the remembered components (below), the die boundary polygons, `top_name`, `extent`,
`rows`, `cols`, and the recorded knobs (`grid_size`, `min_layer`, `max_layer`, `min_segment`,
`macro_block_layers`) and identities for the mismatch check.

**Not stored**: `layers`/`filtered_layers` (live LEF), `capacity_base` (0.76 s to rebuild, and then
it cannot drift from the boundary), `blocked`/`blockage` (recomputed — see below), and the full
component table.

**Valid iff** the measured layer set by name, `grid_size`, `--min-segment-length`,
`--macro-block-layers` and the tech/macro LEF identities all equal the recorded ones and the DEF's
`size`+`mtime_ns` are unchanged. Anything else is refused with the difference named: dumped with
`--min-layer/--max-layer` and loaded without → refused (the unmeasured layers would render as 0 %);
dumped without and loaded with a range → refused, and the remedy is better than the flag (the GUI's
layer checkboxes, since a layer's grid, area and utilisation do not depend on the range).

## The keystone: a reused block is materialised as a small block table

`HierarchyAssembler` and `_macro_blockage` read `blocks[name] = (instances, boundary)`. So a reused
db is turned back into exactly that: a DataFrame holding only the **remembered components** —
`(cell_name, orient, location_x, location_y)` for every instance whose cell is a LEF macro *or* is
not in the LEF at all — plus the stored boundary. Every existing stage then works untouched:
`_child_frames` derives each sub-block's frame from the parent's row (so the walk descends), and
`_macro_blockage` finds its macro rows. No second feeding path exists to drift from the first.

That table is also how a top-only dump stays useful: with only `core_wrap.def`, the tool cannot know
`lx956c_ioe` is a block — it is indistinguishable from an unknown cell, the same set behind the
existing "neither in the LEF nor a block" warning. So the resolution happens at **combine** time (a
loaded db whose block name matches a recorded name is a sub-block), and what the dump must supply is
the candidate's placement **in the block's own local coordinates** — which is what lets
`--db core_wrap.db --def SUB.def --dump-only` know where SUB sits, without reading the parent DEF.
A child's global frame is therefore derived, not stored twice, and that same derivation is what the
frame check compares against the child's db.

Sub-block **wiring** still cannot be in the top's db — it lives only in its own DEF — so a top-only
dump is a correct, correctly placed map of the top's own routing, and the combining run names any
block whose wiring no loaded db covers (the precedent of `block 'X' is instantiated but no DEF
defines it`).

## Phases

1. **`vlsi_viewer/metal_db.py`** — `DB_FORMAT`, `db_path_for`, `source_note`, `lef_identity`,
   `save`/`load` (npz, `allow_pickle=False`, header as one JSON string), and
   `mismatch(recorded, current) -> str | None`. Change test = version + path + `mtime_ns` + size,
   the convention `metrics._source_key` uses — never a content hash (hashing a 2 GB `.gz` costs more
   than the parse it guards).
2. **`build_metal`** — per-block products (its own `_GridSink`, text stats, counters, layer stats,
   warnings) folded into the build's totals, so a block can also be *reused* instead of parsed; the
   per-block decision in walk order; dumping only after a complete build (a cancelled run writes
   nothing — a partial grid in a db is a wrong map that loads fast). `MetalData` gains `dbs` and
   `reused`.
3. **`cli.py`** — the three arguments (hyphenated, with the underscore alias), `--def` no longer
   `required` (`--lef`/`--tech-lef` stay required: the layer table and blockage are rebuilt from
   them), `--dump_only` returning 0 at the existing "before Qt" seam.
4. **Docs** — README's flag table and the metal paragraph that says it "caches nothing"; this file.

## The 09-17 runs, and the check they added

Two db-only runs of `lx956c_core_clamp_wrap` (`dev_plan/issue/real_design_log_0917.md`), each
block's db dumped by a separate standalone run, found the one validity check that was missing:

- `lx956c_ioe` was refused on the frame (`N at (0, 0)` recorded, the design places it at
  `(0, 661.2)`) — the design working, and a demonstration of why a sub-block's db is only correct
  in the frame of the run that wrote it.
- `lx956c_fsu` sits at `(0, 0)` in the design — *the same frame a standalone dump records* — so the
  frame check could not tell the two apart, its `72 x 124` grids were added to the design's
  `189 x 253`, and `Bins.add_grid` raised `grid is (72, 124), this grid's is (189, 253)`.

`mismatch()` now takes the run's `(rows, cols, extent)` and compares it after the LEF identities and
before the frames; the extent as well as the cell count, because the same count over a shifted die
puts every grid in the wrong place. `_sink_from_db` also checks an array's shape against its own
header and names the block, so a truncated file is attributable rather than surfacing as the
rasteriser's bare shape error. Run 1's behaviour — warn, draw the rest — is unchanged, and the
message now says what to do instead: re-dump that block with its design's db. (Phase 3 below
replaced that remedy for a db that carries shapes: the run replays them instead, and the message
says so rather than sending the user off to re-dump a block it is about to draw.)

## Verification

Equivalence is the centrepiece: build the sample with `--dump-db`, rebuild from `--db` alone, and
assert counters/totals/layer-stats identical and the grids `np.array_equal`; plus the parallel-dump
path one block at a time; staleness (a rewritten DEF re-parses, a changed LEF refuses every db); a
frame mismatch refused both ways; the remembered-components record; both layer-range directions;
coverage warnings; `--dump_only` writing without Qt; and the measured dump/load cost.

## As built, and what it measured

**625 tests pass** (611 before), 13 of them new in `tests/test_metal_db.py`.

Two mechanisms carry the feature, and both were confirmed by the tests rather than assumed:

- **A reused block is materialised as a small block table** - its remembered components as a
  DataFrame - so `HierarchyAssembler._child_frames` derives each sub-block's frame from the
  parent's row and `_macro_blockage` finds its macro rows, with no second feeding path into either.
- **Per-block products**: each block now gets its own `_GridSink`, text stats, counters and layer
  stats, folded into the build's totals by one `fold_block`. That is what lets a block be *stored*
  and *reused* through the same arithmetic a parse goes through; the sample's `emitted` count
  (79,277) comes back identical from a db, and a `--jobs 8` dump and a `--jobs 1` dump rebuild
  identically.

Measured:

| | |
|---|---|
| a 620 x 620 grid, 12 layers, both scopes | **1.13 MB** in one db (0.12 B per cell per layer-scope, compressed) |
| load + rebuild from that db | **0.31 s** |
| the real design's grids (123 x 107, 11 layers) | ~36 KB compressed, so a db is dominated by the remembered components (~16 B a row, logged per block) |
| the real design's rebuild | the LEF index 12 s + capacity 0.8 s + blockage 10 s, against the 1,785.87 s it replaces |

Three things the implementation settled that the plan had left open:

- **No warnings are stored.** Every warning this build raises is derived from live data - the LEF,
  the components, the totals - so a reused block regenerates exactly the ones that still apply, and
  a stored copy could only go stale. The `header_for` docstring says so.
- **A cancelled run's sequential path keeps its partial grid**: with a sink per block, the geometry
  of a half-read block would have been dropped where the shared sink used to keep it, so the
  `Cancelled` handler flushes and adds it before re-raising.
- **`np.savez` appends `.npz` to a name.** Writing through a file object is what makes the name the
  user asked for - `A.def.gz` becomes `A.def.db`, not `A.def.db.npz`.

The tests found one real gap: a *remembered candidate* whose db is missing is invisible to the walk
(`_child_frames` only descends into blocks it knows), so a design dumped in pieces could lose a
sub-block's wiring with only the generic "neither in the LEF nor a block" warning to show for it.
That warning now names those components as possible sub-blocks and says their wiring needs their own
DEF or db.

## Phase 3: the block's own shapes, so every block dumps alone

Phases 1–2 left the half of the 09-17 problem that mattered most in practice: a db held *rasterised
grids*, so it was bound to the frame **and** the grid of the run that wrote it, and two blocks
dumped in their own jobs could not be assembled. `--db <parent>.db --def <SUB>.def` worked but
serialised the dumps behind the parent's db, which is exactly the parallelism the feature exists to
get. So a db now also carries the block's **own** shapes, and the loading run rasterises them under
its own frames.

The measurements that decided it are in `dev_plan/metal_def_db_eval.md`: **0.51 µs per shape** to
replay (read + inflate + rasterise, measured on the path it would take) against 19.12 µs to parse,
and **10.9–11.0 bytes per rect** compressed, stable to 1 % across scales — 0.49 GB for the top
block's 44.4 M rects, ~1.7 min to replay against 14.2 min to parse.

The seam is `ShapeStream`, which already accumulated every shape in the block's own coordinates and
applied the frames only in `flush()`:

- **`on_batch(kind, layer_index, scope, packed)`** fires in `flush()` before the frame loop, with the
  pending group as int32 database units — the unit `configure()` was handed on the first net, so the
  round trip is exact (`round(x * db_unit)` out, `n / db_unit` back in).
- **`add_batch(...)`** is the inverse: unpack to microns, append to `_pending`, and the next `flush`
  places them under *this* stream's frames. Nothing is re-classified — a stored shape already passed
  the layer range, the jog filter and the scope — and `_as_1d` keeps the parse's hot path at one
  `asarray` over the list it already has.
- **Polygons** are not buffered at all, so `_add_polygon`'s per-frame loop became `_emit_polygon`:
  one place where a ring meets a frame, called by the parse and by the replay both.

**The container is a record stream with a footer** (`body records | header JSON | uint64 len |
b"VLSIDB2\n"`), because the writer cannot know up front how many batches a parse will produce. The
footer's index lets the grids path seek without reading past half a gigabyte of shapes, and
`BlockDb.geometry()` yields one record at a time so a 0.49 GB section never becomes 0.49 GB of
memory. A file that does not end with the magic is read as a **v1 npz**, so a db written by the
build before this one keeps working — and the refusals that only make sense for a db with no shapes
to replay are still tested against one.

**Workers write their own parts.** Every worker opens a `SectionWriter` on `<db>.part<index>`, passes
the object (never crossing a process boundary) to `parse_chunk`, and closes it; the parent merges by
**concatenating** the part files, which is complete precisely because every accumulator downstream is
a sum. Parts are truncating, removed by the parent on both the success and the cancelled path.

**Reuse tries three things in order: grids → replay → refuse.** The geometry flavour's validity is
deliberately *looser*: the DEF it came from, `min_segment`, the measured layer set and the tech LEF
— everything that decided which shapes were stored — but not the macro LEFs, the grid size or the
die, because those act on the live rasterisation. A replay contributes grids only; the counters,
layer stats and text stats come from the header, so a replayed map's numbers are exactly a parse's.

Two things the tests forced out that the plan had not:

- **`emitted` and three row columns are counted per placement, not per parse.** A sub-block dumped
  alone was placed once and is replayed into four, so `_rescaled` moves those numbers by the ratio
  and leaves the rest to `fold_block`'s placement scaling. Without it the summary said 19,826 shapes
  where the table said 79,277 — a disagreement that would have looked like a db defect.
- **The pre-filter was silently defeating the fallback.** The first pass drops a db that fails the
  strict check before any block exists, and the geometry path is only ever consulted *inside*
  `parse_block` — so a changed macro LEF, a changed `--grid-size` or a changed `--min-segment-length`
  refused every db outright and re-parsed, with the replay unreachable. It now computes two verdicts:
  a db that cannot answer for the grids but *can* supply shapes stays a candidate for its block, and
  `parse_block` makes the same two-stage decision again with the frames in hand. A db that fails both
  is the only one that is dropped, and it says why at INFO.

Verification, `tests/test_metal_db.py` (23 cases) and `tests/test_metal_gui.py`:

- **the hierarchical case end to end** — `sub.def` alone dumped with a pool, `top.def` alone dumped
  with a pool, neither naming a parent, then one run over the two dbs with **no DEF at all**:
  `reused == ["TOP"]`, `replayed == ["SUB"]`, counters/layer stats/text stats equal and the grids
  close (a pooled dump sums in another order). `(rects + diagonals + polygons) x placements ==
  emitted` is checked against the file, so nothing may be dropped between the counters and the body.
- **a bare sub dump assembled elsewhere** — the 09-17 workflow, now exact: every grid
  `array_equal` to the one-shot parse, through four placements at four orientations.
- **a standalone dump whose grids do not fit** — the run-2 die mismatch: grids refused, shapes
  replayed, no warning, and the refusal named in the log.
- **the old container**, one arm each: a v1 db that matches rebuilds exactly, and a v1 db from a bare
  dump is still refused by name rather than drawn at (0, 0).
- the replay refused when `min_segment` differs; the replay accepted when only the *macro* LEFs
  change; the container round-tripping rects, diagonals and a variable-length ring across two parts;
  a truncated db reported and re-parsed while the other db still loads.

Measured after the change, with `bench_db_geometry.py` now driving the shipped path (`SectionWriter`
→ `write` → `load` → `geometry` → `add_batch`) rather than a private layout: **0.50 µs per shape**
(1,402,400 shapes in 0.70 s) and **16.0 B/rect raw, 11.0 B zlib 6** — unchanged from the
pre-implementation estimate, which is the point of having measured it first. **636 tests pass.**

The hand-run the plan asked for, on the committed sample:

    python -m vlsi_viewer metal --def sample_data/metal/sub.def --lef ... --dump-db dbs \
        --dump-only --jobs 8
    python -m vlsi_viewer metal --def sample_data/metal/top.def --lef ... --dump-db dbs \
        --dump-only --jobs 8
    python -m vlsi_viewer metal --db dbs/sub.def.db dbs/top.def.db --lef ... --dump-only

The third run reads no DEF at all and logs `SUB: its db's grids do not match this run (...); replaying
its stored shapes`, then `19,817 shape(s) replayed in 8 batch(es)` (two workers' parts, merged), with
`"reused": ["TOP"], "replayed": ["SUB"]` in the summary and no warnings.
