# Stop parsing the same thing twice

The plan for the redundant reads a sample run exposed. What was built and what it measured goes
in [`metal_density_asbuilt.md`](metal_density_asbuilt.md) under *Phase 17*.

## What prompted it

A user's sample run with `--jobs 8` spends **6.45 s of 7.39 s in `_thread.lock.acquire`, with 40
`CreateProcess` calls**, for a build that takes ~1 s sequentially (`--jobs 2`: 0.98 s). Four
things are read more than once:

| effect | in the log | cost |
|---|---|---|
| macro LEF parsed twice | `cells.lef` at cell-index, then again at blockage | ~10 s of the recorded 7051 s run (221 files, 11.3 + 10.2 s) |
| a block parsed once per **instance** | `reading routing in SUB` x4 | K x a block's parse; **zero** on the recorded flat design, linear in instances for a hierarchical one |
| every **worker** re-reads the file | `Load DEF file SUB` ~32x | deliberate, but it multiplies the row above: 4 x 8 = 32 reads |
| the DEF read once per pass | pass 1 components, pass 2 wiring | ~25 s of the recorded run; required for hierarchies, overhead for a flat design |

Plainly: on the recorded design (flat, one instance) this is ~35 s of 7051 s, 0.5 %. The value is
that the flow stops doing work twice, that a hierarchical design stops paying K x per instance,
and that `--jobs` stops being a pessimisation on small inputs.

## The test gap that went first

Two things the suite did not pin, both silent failure modes:

- **a wire under a non-identity frame** - the frame tests were outline-only and
  macro-obstruction-only, and `verify()` asserts grid spread, which a *composed* transform (frame
  2 applied on top of frame 1) passes;
- **a block's wiring landing K times** - a walk deduplicated to visit SUB once still passes
  `verify()` (every threshold survives: max 0.478, distinct 562 -> 395, occupied 0.817 -> 0.807),
  so nothing but a direct count catches it.

Plus a third that was a **live bug**: `_add_polygon` applies no frame at all, so a `+ POLYGON`
inside a rotated sub-block rasterises in local coordinates, stacked on every other instance, while
`n_emitted` counts it once per instance. Invisible until now because the sample's only polygon sits
in the top block, where the frame is the identity.

## C. Parse a block once, place it under each of its paths

The walk stays per **path** (`test_metal_assembly.py` pins `["TOP","SUB","SUB"]`, and
`_macro_blockage` and `_boundary_polys` both need per-instance visits). Only the routing pass gets
its own collector: `build_metal` appends each `(block, frame)` visit to a list and parses each block
once. K is the number of paths, so the frames are a **list**, not a set keyed on `Frame`: two
instances at the same orientation and location are two placements.

`ShapeStream.frame` becomes `frames` (read in two places, both in `flush()`; no test passes one).
`flush()` transforms **copies** of the pending arrays once per frame and calls the sink per frame:
never a `np.concatenate` of K copies (2 GB transiently at K=1000), never feeding a transformed array
into the next frame's transform (that composes the frames), and `_diagonals` cleared **once** after
the loop rather than inside it. The per-shape path keeps its local coordinates - hoisting the
transform into it would flip `_is_preferred`'s jog decision for rotated blocks.

`_add_polygon` gains the frame via the **point map applied to every vertex**, after buffering once
in local coordinates; `apply_rect`'s two-corner normalisation would turn a non-rectangular ring
into its bounding box.

Counters, split so that both existing contracts survive: `n_emitted` counts **per frame inside the
stream** (keeping `n_emitted == rects + diagonals + polygons`, which
`tests/test_metal_diagnostics.py` pins); the six drop counters are multiplied by K where the block's
totals are folded (the design contains K copies of that wiring, so the summary must agree with the
grids); the input characterisation is folded **once** - the text is read once now - and the maxima
and layer union stay once, since multiplying an idempotent fold corrupts it.

Also moving, and stated rather than discovered: the `except Cancelled` moves from `walk` to the new
parse loop; a cancel now yields a prefix of the shapes for all paths; the per-path diagnostics
collapse to one per block.

## A. Size the pool to the work, once per build

`--jobs N` becomes a cap, sized on **statements, not bytes**: a `.gz` DEF's `st_size` is its
compressed size (a 200 MB `.gz` is a 2 GB DEF, and every worker also decompresses it). Pass 1 already
reads each DEF's head, and the section headers are in it, so the declared net counts are free:

    workers = clamp(min(jobs, ceil(declared_statements / DEFAULT_CHUNK_STATEMENTS)), 1, jobs)

No declared count -> one worker. Decided once per build (the pool is shared, so the marginal cost of
the second block is zero), clamped to at least 1 (`--jobs 0` currently builds nothing), and logged
once so the decision is visible. **The sizing takes an explicit override, and
`tests/test_metal_parallel.py` passes it** - a threshold near one chunk would otherwise send those
equivalence builds down the sequential path and have them compare a sequential run with a sequential
run, green and testing nothing.

## B. One pool per build, and a working cancel

One `ProcessPoolExecutor` per build, closed in a `finally`. `parse_parallel` accepts a `cancel` and
never uses it today - `_worker` builds its `Reader` without one - so `--jobs > 1` cannot be
interrupted at all, contradicting the CLI's promise. Wire it through; the README's "scales nearly
linearly with cores" needs rewording once N is a cap.

## D. Read each macro LEF once

`LefParser.__init__` already reads `OBS` in the pass that builds the cell table; only
`convert.cell_info_from_lef` discarding the macro objects creates the second pass. Add an opt-in that
returns both the info dict and the obstruction map, and delete `metal._macro_obstructions`.

Must not change: the default return stays a plain dict keyed by cell name; the `is_macro_class`
filter; "declares no OBS" vs "declared some judged negligible"; `n_obs_unmodelled`; and the no-LEF
path, where `_indexed_cells` returns `None` - returning `{}` would make every leaf instance
"missing" and raise a warning on the empty-LEF build a test uses.

## Deferred, with its number

One pass instead of two for a *flat* design: capacity and blockage built mid-parse, on the first net.
Saves one full read of the DEF - ~25 s of 7051 s, 0.35 % - at the cost of restructuring `build_metal`
and keeping both paths for hierarchies. Recorded so the decision is visible.

## Verification

The user's own command before and after (`--jobs 8 --profile`): `stage routing` ~6.9 s -> ~1.0 s,
four `reading routing in SUB` become one, the LEF section appears once, and `_thread.lock.acquire`
leaves the profile's top slot. Then the same at `--jobs 1` for identical geometry, and
`python -m pytest -q` with every pinned number unmoved (gcd 2504 / 5 / 2327, `SAMPLE_SHAPES`,
pool-vs-sequential equality, the `n_emitted` invariant).
