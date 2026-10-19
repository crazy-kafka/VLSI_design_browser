# Hierarchy contour + density performance improvement (approved 2026-10-19)

## Why

The physical-mode Density% column computes a gap-padded union per visible hierarchy node,
and clicking a node recomputes the same union for its contour. On the bundled 108,436-box
sample:

| Node | Boxes | Merged | pandas merge | shapely area | loops |
|---|---:|---:|---:|---:|---:|
| CPU_CLUSTER | 108,436 | 6,620 | 72–79 ms | 303–356 ms | 311 ms |
| core_1 | 22,607 | 3,084 | 24 ms | 132–173 ms | 133 ms |
| core_0 | 22,607 | 142 | 15 ms | 21–26 ms | 22 ms |
| core_2/ifu | 8,002 | 33 | 10–12 ms | 12–14 ms | 12 ms |
| l2 | 8 | 2 | 9–10 ms | 8–10 ms | 8.6 ms |

All 19 densities take 1.23–1.29 s; the initial GUI queues 6 density jobs (~0.84 s CPU).
The two dominant costs are the ~8–11 ms fixed pandas overhead in `merge_boxes` and the
full shapely union still used for area-only density. Loops and area use separate caches,
so density then contour repeats the merge and union.

## Decisions

- **Approximation permitted**, but the recommended core changes are exact and already meet
  the targets; the default stays exact. A coarse density raster or simplified contour
  preview is only a fallback if the real-design benchmark misses a threshold.
- **Scope: computation + UI scheduling** — merge/area/caching, the double tree rebuild,
  and superseded contour jobs.
- **Priority: both paths equally** — per-node Density% first, then contour clicks.

## Approach

- `contour.merge_rects(boxes, gap)`: fuse float64 expansion, `round(9)`, and a numpy
  two-pass band merge (lexsort + segmented prefix max + reduceat). `merge_boxes` becomes a
  wrapper returning an `(M,4)` ndarray.
- `contour.rect_union_area(rects)`: exact sweep-line area (x events, compressed y,
  segment tree of cover counts/lengths). `contour_area` uses it; `contour_loops` and
  `contour_geometry` keep shapely.
- `PhysicalData`: precompute `_box_area` float32; cache `_slice_for`; one
  `_ContourEntry(rects, loops, area)` per `(path, gap)` with per-product single-flight
  (`threading.Event`). `density_for` uses one slice, the shared rects/area, and the
  precomputed areas. Bound heavy cached rects/loop points with an LRU while retaining
  area floats.
- `ContourWorker` tracks the latest `(token, path)`; `_ContourJob.run` skips stale work
  before computing. `LayoutView` invalidates on clear.
- `MainWindow._apply_settings` uses `set_threshold(..., rebuild=False)` before
  `set_view`, so each settings change rebuilds once.
- Optional: coalesce `_LazyDensity.status` emissions per event-loop turn.

## Implementation order

0. Record this plan; add `sample_data/bench_contour_density.py` and record the baseline.
1. Numpy merge (`merge_rects`/`_merge_bands`/`_segmented_cummax`); fix the contour
   random fixture (`y1 < y0`) and add a pandas-reference equality test.
2. Exact sweep area; route `contour_area`.
3. Route loops/geometry through the fused merge.
4. Unified `PhysicalData` cache, slice cache, `_box_area`, single-flight; density tests.
5. Bound the heavy cache.
6. Skip stale contour work.
7. One tree rebuild per settings change.
8. Optional status coalescing.
9. Final benchmark and full suite.

## Expected results

- Root area 303–413 → 155–179 ms; core_1 132–178 → 72–93 ms; core_0 21–26 → 3–5 ms;
  ifu 12–15 → 1.5–2 ms; l2 9–11 → 0.2 ms; all 19 densities 1.23 → **0.54 s**;
  initial 6 jobs ~0.84 → ~0.38 s CPU.
- Small-node fixed cost falls from ~9–11 ms to ~0.2–0.3 ms.
- Sweep vs shapely relative area ≤1e-9; density change ≤1e-12 (measured 8.9e-16).
- +`_box_area` 4N bytes (~13.4 MB at 3.35M); heavy caches capped ~16 MB rects + ~12 MB
  loops; transient merge O(N), ~0.4–0.5 GB peak on a 3.35M-box path.

## Risks

- Vertical-pass column mapping; cover with exact-reference tests.
- Float64 expansion/rounding order; never mutate caller arrays; keep `_box_area` float32.
- Inverted boxes are outside the contract; fix the fixture.
- Shapely 1.8 only (`unary_union`, scalar `box`).
- Never hold `_contour_lock` during compute; events set in `finally`.
- Qt thread affinity for contour jobs; only plain state in `is_current`.
- `merge_boxes` return type changes to ndarray.
- `contour_geometry` (shapely area) vs `contour_area` (sweep) can differ by ulps.
- `requirements.txt` declares shapely>=2.0 but the environment has 1.8.5.

## Verification

```bash
python -m pytest tests/test_contour.py -q
python -m pytest tests/test_physical.py tests/test_region.py -q
python -m pytest tests/test_gui_smoke.py -q
python -m pytest -q

python sample_data/bench_contour_density.py --repeat 3
python sample_data/bench_contour_density.py --repeat 3 --check
python sample_data/bench_contour_density.py --scale 8 --repeat 3
```

Targets: merged counts identical to the pandas baseline; sweep vs shapely ≤1e-9
relative; density vs frozen baseline ≤1e-12; root area ≤250 ms; smallest node ≤1 ms;
all-node density ≤0.9 s; one rebuild per settings change; stale queued contours do not
compute.

## Out of scope

- Approximate density/contour preview is only a fallback, not the default.
- Tree-model rework, viewport-based density scheduling, metric-column caching, physical
  startup pipeline.
- Shapely 2 migration.

---

# As built (2026-10-19)

## What changed

| File | Change |
|---|---|
| `vlsi_viewer/contour.py` | `merge_rects` fuses float64 expansion, `round(9)` and two numpy band merges (`lexsort` + segmented prefix max + `reduceat`); `merge_boxes` is the gap-0 wrapper and now returns an `(M,4)` ndarray. `rect_union_area` is an exact x-sweep with a compressed-y segment tree. `contour_area` uses merge + sweep; `contour_loops`/`contour_geometry` use the same merged rectangles and shapely for loops. |
| `vlsi_viewer/physical.py` | Precomputed `_box_area` (float32), cached `_slice_for`, one `_ContourEntry(rects, loops, area)` per `(path, gap)`, and per-product single-flight locks. `density_for` uses one slice, the shared rects/area and the precomputed box areas. Heavy rect/loop payloads are LRU-bounded (500k rects / 100k loop points); areas survive eviction. `clear_contour_cache()` resets the cache and accounting. |
| `vlsi_viewer/model.py` | `ContourWorker` tracks the latest `(token, path)`; `_ContourJob.run` skips superseded work before and after computing. |
| `vlsi_viewer/ui_layout.py` | `_clear_contour` invalidates the contour worker. |
| `vlsi_viewer/ui_main.py` | `_apply_settings` calls `set_threshold(..., rebuild=False)` before `set_view`, so threshold/macro changes rebuild the tree once. |
| `tests/test_contour.py` | pandas-reference merge equality, fused-equals-expanded, well-formed merged rects, sweep-vs-shapely random/edge cases; the random fixture now generates valid boxes. |
| `tests/test_physical.py` | shared merge for density+contour (both orders), slice-cache identity, manual density formula, 8-thread single-flight, bounded heavy cache with area retention. |
| `tests/test_gui_smoke.py` | stale contour job skipped before compute, clear invalidates pending work, one rebuild per threshold/macro change. |
| `sample_data/bench_contour_density.py` | New per-node/all-node benchmark with `--repeat`, `--scale`, `--shapely`, `--check`. |

## Measured before/after (bundled sample: 108,436 boxes, 19 nodes, grid 3.0, gap 6.0)

| Node | Baseline merge | Final merge | Baseline area | Final area |
|---|---:|---:|---:|---:|
| CPU_CLUSTER | 81 ms | 34 ms | 425 ms | **147 ms** |
| core_1 | 27 ms | 11 ms | 188 ms | **60 ms** |
| core_0 | 21 ms | 3.3 ms | 27 ms | **4.6 ms** |
| core_2/ifu | 14 ms | 0.86 ms | 15 ms | **1.3 ms** |
| l2 (8 boxes) | 11.5 ms | 0.07 ms | 10.4 ms | **0.10 ms** |

- All 19 hierarchy densities: **1,305 ms → 409–418 ms** (~3.1–3.2×).
- Initial visible set (root + 5 children): **831 ms → 277–284 ms CPU** (~3.0×).
- Merged rectangle counts are unchanged on every sample node (root 6,620).
- Sweep vs shapely area: max absolute difference **8.7e-11** across the sample; random
  sweep tests within 1e-9 relative. Numpy merge is row-for-row identical to the pandas
  reference on the sample and valid random inputs.
- `--check` passes: root area 145.6–146.9 ms (≤250), smallest node 0.10–0.11 ms (≤1),
  all densities 409–418 ms (≤0.9 s).
- Scale probe (`--scale 8`): 867,488 boxes → 52,960 merged; merge 212–220 ms, area
  1,134–1,154 ms (1.31–1.33 µs/box). Linear projection to 3.35 M boxes is ~4.4 s for one
  whole-die area computation; it runs on a background thread and the GUI remains
  responsive. The real design's merged count will differ (dense placements collapse much
  further).

## Memory and caches

- New `_box_area`: 4N bytes (~0.43 MB sample, ~13.4 MB at 3.35 M).
- Heavy LRU caps: 500k merged rectangles (~16 MB float64) and 100k loop points (~12 MB
  CPython); areas remain cached after eviction. Sample payload across all 19 nodes:
  19,772 rectangles (0.63 MB) and 3,840 loop points (~0.43 MB).
- Slice cache capped at 4,096 paths; product locks are per `(path, gap, product)` so
  different paths can compute concurrently.
- Transient merge/sweep arrays remain O(N); lower than the old pandas path at the same
  scale.

## Verification

- `python -m pytest -q` → **700 passed in 68.30 s** (688 before; 12 new tests).
- `python sample_data/bench_contour_density.py --repeat 3 --check` → all checks passed.
- `python sample_data/bench_contour_density.py --scale 8 --repeat 2` → table above.
- Manual/behavioral: density values match the shapely reference, contour loop counts and
  point counts are unchanged, rapid clicks now skip queued stale contours, and Min/macro
  changes rebuild the tree once.

## Known limits

- A whole-die density on a 3.35 M-box design is projected at ~4.4 s CPU (background); the
  exact sweep is the dominant cost. If this is too slow on the real machine, the approved
  fallback is an optional coarse density raster at a documented resolution (the user
  permits approximation); it is not enabled by default.
- `contour_geometry`/`contour_loops` still use shapely for loop extraction; only the area
  path avoids it.
- The installed shapely is 1.8.5 while `requirements.txt` declares >=2.0; the code uses
  only 1.8-compatible APIs.
- Density jobs for rows hidden by a later threshold change still complete (one per unique
  path), as before; viewport-based scheduling is out of scope.
