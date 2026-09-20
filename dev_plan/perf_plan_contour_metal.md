# Performance plan: physical-mode contour/density responsiveness + metal-mode DEF parse

Analysis of the two hot spots the user reported, with fresh measurements where the
repository's own notes did not already have them. Probe harness:
`dev_plan/code_sample/perf_probe.py` (synthetic shapes only). Probe machine constants
differ from the ones recorded in `metal_routing_performance.md`; ratios, not absolute
numbers, are what transfer.

## Part 1 — Physical mode: why the GUI stutters, and what to do about it

### How it works today

- Tree row render → `_LazyDensity.get(path)` (`model.py`) → `_DensityJob` on a
  `QThreadPool` capped at `min(cpus//2, 4)` → `PhysicalData.density_for(path)`.
- `density_for` = `contour.contour_area(subtree_boxes, gap)` + numpy slice sums. The
  contour area is **computed from scratch for every node**: `merge_boxes` (pandas,
  O(subtree)) → shapely `unary_union` → `.area`. Cache key `("area", path, gap)`.
- Contour click → `ContourWorker` (dedicated 1-thread pool, FIFO) →
  `contour.contour_loops` over the **same** union again, cache key `("loops", path, gap)`
  — so a clicked node's union is computed twice.
- Stale contour results are dropped only **at delivery** (`_on_contour_ready` token
  check): a stale expensive contour still runs to completion before the fresh one starts.
- No thread priorities are set anywhere; nothing backs off while the user interacts.

### Measured (this machine, synthetic placement of abutting std cells)

| N boxes | merge_boxes (pandas) | unary_union on merged | sweep-area on merged |
|---|---|---|---|
| 100,000 | 0.051 s | 0.020 s | 0.001 s |
| 1,000,000 | 0.397 s | 0.064 s | 0.001 s |
| 3,000,000 | 1.181 s | 0.118 s | 0.001 s |

- `merge_boxes` is the dominant per-call cost (~0.4 s per 1M boxes) and is pandas
  groupby work, i.e. long GIL-holding C calls. For the **root node** of a 10M-instance
  design this is ~4 s of nearly uninterrupted GIL — the single biggest stutter source.
- For area-only (density), shapely's union is 60-100x more expensive than an exact
  rectilinear sweep over the same merged rectangles (1 ms vs 64-118 ms), and the sweep
  result matches shapely's `.area` exactly (verified in the probe).
- GIL probe (GUI-like 60 fps tick loop + background threads): worst tick gap goes
  9.5 ms solo → 13-23 ms with 1-4 `merge_boxes` threads → up to ~31 ms with 4
  `unary_union` threads. Visible stutter, and the real GUI does more work per tick than
  the probe.

### Root causes, in order of impact

1. **Quadratic-ish total work**: expanding the tree fires one independent union per node;
   the root node re-unions the entire design. Total work is O(Σ subtree sizes).
2. **GIL**: all background pools are Python threads; `merge_boxes` (pandas) holds the GIL
   for hundreds of ms per call, and up to 5 background threads (4 density + 1 contour)
   compete with the GUI thread for it.
3. **Redundant union**: area and loops are separate cache entries over the same geometry.
4. **FIFO without preemption**: a stale heavy contour blocks the fresh click behind it.

### Plan P1 — threading quick wins (no algorithm change, ~30 lines)

- **P1.1 Thread priority.** `QThread.currentThread().setPriority(QThread.LowPriority)`
  first thing in `_DensityJob.run` and `_ContourJob.run`. On Windows this maps to
  `THREAD_PRIORITY_BELOW_NORMAL`; the GUI thread wins scheduling. One line each.
- **P1.2 Stale-drop before compute.** `ContourWorker` keeps `self._latest_token`;
  `_ContourJob.run()` compares its token **before** starting and once between
  `merge_boxes` and `unary_union`, returning silently when stale. A rapid
  click-click sequence no longer serialises two heavy unions.
- **P1.3 Interaction throttle.** `GenericGraphicsView` wheel/drag/scroll events bump an
  "interacting until" timestamp (GUI thread, plain attribute); `_DensityJob.run()` waits
  (bounded, e.g. ≤ 300 ms, re-checking every 50 ms) for interaction to end before
  computing. Density values are progressive by design, so the delay is invisible; paint
  events stop competing with pandas.

Verify: the 16 ms-heartbeat probe from `hierarchy_contour.md` (worst gap target < 30 ms
while expanding the full tree on the bundled sample); `pytest -q`.

### Plan P2 — algorithm (the actual fix)

- **P2.1 Bottom-up merged-rectangle cache (kills root cause 1+3).** Union is associative:
  `merge(node) = merge_boxes(concat(merge(child) for children) + own leaves)`, exact for
  the same gap-padded boxes. Precompute once in `build_physical` (offline, before the
  window exists): pad `geom` by `gap/2` in one numpy pass, then merge bottom-up over the
  sorted `leaf_paths` tree, storing `path -> (k, 4) float32` (phys-only boxes filtered
  up front). Cost: one full-size merge (~0.4 s/1M today, less after P2.3) + merges over
  shrinking child sets. Memory: a few × the top set (measured ~1k rects per 1M cells).
  Then:
  - `density_for(path)` = sweep-area over `merged[path]` (**~1 ms**, no pandas, no
    shapely, almost no GIL) + the existing numpy macro/non-macro slice sums.
  - `contour_for(path)` = shapely `unary_union` over the same `merged[path]` → loops
    (≤ ~0.1 s worst case, GIL-releasing C++), still on `ContourWorker`.
  - The `("area", …)` / `("loops", …)` double computation disappears: one shared
    merged-set cache, area derived by sweep, loops derived by shapely only on click.
- **P2.2 Exact sweep-line union area for density (kills the shapely dependency in the
  density path).** X-sweep over merged rects with per-slab y-interval merge; numpy
  inside, O(k log k), exact for rectilinear unions (boxes are axis-aligned by
  construction). Already validated in the probe against shapely `.area`.
- **P2.3 numpy `merge_boxes` (kills the pandas/GIL hotspot).** Same two-pass run-merge,
  but `np.lexsort` + a Python loop over **groups** (≈ √N distinct row/column keys —
  ~1k groups per 1M boxes) with `np.maximum.accumulate` inside each group, instead of
  DataFrame + `groupby().cummax()/shift()/agg` chains. Expected 3-5x on the merge step
  and numpy's GIL release on the large passes. Output identical (same 9-decimal rounding,
  same merge semantics) — the contour tests are the oracle.
- **P2.4 Shrink the density pool to 1 thread** once per-job cost is ~ms (from P2.1);
  keep `_bounded_threads` for the contour worker only. With P2.1 in place, 4 GIL-hungry
  density threads buy nothing and still contend.

Verify: `pytest -q` (density/density-% asserts and contour goldens unchanged); density
values bit-compared against the current implementation on the bundled sample and on
`sample_data/physical`; build-time delta of `build_physical` reported (expect
+~0.5 s/1M boxes, one-time, offline).

Environment note: the dev box runs shapely 1.8.5 while `requirements.txt` says >= 2.0.
Upgrading makes `unary_union`/`union_all` measurably faster; optional, and P2.2 makes
the density path indifferent to it either way.

## Part 2 — Metal mode: DEF parsing of NETS / SPECIALNETS

### Cost structure today (measured, `metal_routing_performance.md` + probe)

- ~12 µs per shape, linear; no hidden quadratic. Breakdown: two full-text regex passes
  (form scan + per-tail token scan) ≈ 40-59 % of the run; `DefWire`/`DefSWire`
  allocation ≈ 0.86 µs/shape; dispatch ≈ 0.13 µs; raster ≈ 0.6 µs/shape.
- Probe on this machine confirms the *structure*: token scan ~2-4x the cost of a
  points-only `findall` over the same text (36 vs 18 ns/char); a bulk
  `findall(ints)` + `np.array` conversion is viable (25 ns/char).
- The process pool (`parallel.py`, `--jobs`) exists, is off by default, and is measured:
  4 workers ≈ 1.9x, 8 ≈ 2.3x on a 9 M-line input, ~3.9x at 4 cores predicted on the real
  30 M-line design. `RANGE_WORK_UNITS` (byte-range split, removes the per-worker
  full-file scan) is implemented but off pending evaluation
  (`metal_work_units_eval.md`).
- Checked and rejected as targets: `re_non_wiring_clause.search` in `__split_statement`
  (0.4 ns/char, noise); the `'USE' in statement` / `'NONDEFAULTRULE' in statement`
  substring guards (already cheap supersets); GC (3-12 %, addressed in Phase 1 of the
  earlier plan).

### Plan M0 — baseline first

Re-run `generate_metal.py --real-shape` before anything lands; goldens = `pytest -q`
(500 tests) + the pinned real-file counters. Report wall clock per phase, as the earlier
plan did.

### Plan M1 — parallel by default for large inputs (days, lowest risk, biggest certain win)

- Change `--jobs` default from 1 to auto: `min(os.cpu_count(), 8)` passed through
  `effective_workers`, which already gates by uncompressed size (8 MB/worker), so small
  DEFs stay sequential and pay nothing (the +13 % machinery cost never engages).
- Finish the `RANGE_WORK_UNITS` evaluation and enable it: each worker then reads only its
  own byte range instead of scanning the whole file, removing the residual sequential
  term (measured ~23 s/worker of full-file scan on the real design).
- GUI note: `main.py` already has the `__main__` guard; spawned workers are safe.

### Plan M2 — pure-points fast path in the tokeniser (small, self-contained)

Tails that contain no letters are pure `( x y ) …` sequences — the bulk of
NETS/SPECIALNETS text (via arrays especially). For those, skip `re_wire_token` and use
one `re_pt.findall` + bulk int conversion (measured ~2x cheaper per character), then walk
the flat int array resolving `*` reuse in numpy where possible. Guard: any letter,
`RECT`, or `VIRTUAL` in the tail → existing tokenizer. Equivalence oracle: the existing
tokeniser differential tests + fixture goldens, byte-identical token streams.

### Plan M3 — single-pass wiring scanner (the structural one)

Today the wiring span is scanned twice in full: `re_special_wiring_form` /
`re_regular_wiring_form` over the whole statement, then `re_wire_token` over each form's
tail (each tail also *copied* by `statement[match.end():form_end]`). Replace with one
combined token pattern over the span — clause keywords, form headers, points, `RECT`,
`VIRTUAL`, via names — tracking current-form state (layer, width, rule, shape) in Python.
Removes one full pass and every tail copy. This rewrites
`__add_special_wiring`/`__add_regular_wiring` internals only; the net/sink contract is
untouched. Risk: the two-level split is load-bearing (`*` state, clause termination) —
gate on the differential harness over every fixture tail plus the pinned counters, and on
a measured win on `--real-shape` before keeping it.

### Plan M4 — direct-emit on the sink path (only if M0-M3 leave allocation hot)

When a sink is set, the parser builds one `DefWire`/`DefSWire` per segment that
`ShapeStream.add_net` immediately decomposes into pending arrays. Emit straight into the
stream's buckets on the sink path (arrays of ints per form), keeping object building for
the no-sink legacy callers. Saves ~0.9-1.0 µs/segment (~8 % of the 12 µs constant).
Medium risk to the parser↔stream contract; same equivalence tests.

### Plan M5 — optional, only if the target is still missed

A C-accelerated (Cython/Rust) tokeniser for the two scans — the only remaining 5-10x
lever, at the price of a build dependency the project has so far refused (numba was
rejected for the same reason). Also: move `_run_metal`'s synchronous build behind a
worker thread with progress + cancel (UX debt already recorded in `cli.py`), and finish
`--dump-db` adoption so re-runs skip parsing entirely.

## Suggested sequencing

| Phase | Contents | Risk | Expected effect |
|---|---|---|---|
| 1 | P1.1-P1.3 (threading) | very low | GUI stays interactive during background work |
| 2 | M1 (jobs auto + byte ranges) | low | ~2-4x metal read on multi-GB DEFs, zero parser changes |
| 3 | P2.3 → P2.2 → P2.1 → P2.4 | medium | per-node density ~ms; root-node stutter gone |
| 4 | M2, then M3 if M0 says so | medium | ~1.5-2x single-core parse |
| 5 | M4 / M5 | high | only on measurement |

Each phase ships independently with before/after numbers from the repo's own harnesses
and `pytest -q` green; stop when the targets (GUI worst tick gap < 30 ms; routing read ≤
15 min on the real design) are met.

## As built (branch `performance_dev`, 2026-09-21)

Landed: **P1** (threading), **P2** (physical algorithm), **M1** (parallel default +
byte ranges), **M2** (point-only tokeniser fast path). Full suite 651/651 on Windows,
including the previously-failing CRLF preamble test (fixed by newline-normalising the
scan's decoded header lines). Measured on this machine:

| change | before | after |
|---|---|---|
| `merge_boxes`, 1M boxes | 0.397 s (pandas) | 0.111 s (numpy, 3.6x) |
| `density_for`, bundled sample per node | a fresh subtree union each | **1-9 ms** (sweep over cached merged set) |
| `contour_for`, bundled sample per node | merge + union + loops | 1.7-295 ms (shapely over ≤6.6k merged rects) |
| build_physical overhead for the merged cache | - | +0.1 s on 108k boxes, offline |
| `--jobs` default | 1 | min(cores, 8), size-gated (2 MB sample → 1 worker, verified) |
| byte ranges | off | on at `jobs >= 4`; jobs=4 build == sequential exactly (counters, grids allclose) |
| tokeniser, 512-pt via arrays | 52 ns/char | 44 ns/char (1.18x); gcd tails 1.01x (no regression) |
| end-to-end, 45 MB via-array DEF | 6.54 s | 6.42 s (~2%; diluted by `__split_points`' per-point loop - M3's business) |

Not landed, with the reason: **M3** (single-pass scanner) - the structural parser
rewrite; needs the differential harness run and belongs in its own change. **M4/M5** -
only if the next real Linux run misses the target. The Windows-specific trap to
remember when benchmarking the pool: the caller needs the `__main__` guard
(spawn re-imports the entry module), and `generate_metal.py --out` is a *directory*.

Open verification for the real Linux design (`lx956c_ioe`): `--jobs 8` against
`dev_plan/issue/real_design_log_0915.md` settles the byte-range projection
(1.67-1.9x); watch the parent scan (~105 s projected) and the giant-statement
ceiling, which Phase 6 (splitting it) would address next.
