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
