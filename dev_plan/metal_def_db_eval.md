# What a geometry-carrying metal db costs — measured before it was built, and after

**Status: implemented.** This report decided the question — whether a db should also store a
block's shapes **before** the placement frames are applied, so that every block can be dumped on
its own with no parent at all — and Phase 3 of `dev_plan/metal_def_db.md` is the result. The
numbers below were taken *before* the code existed, on a layout the implementation did not have
yet; the same bench, re-run afterwards through the shipped path (`SectionWriter` → `write` →
`load` → `geometry` → `add_batch`), gives **0.50 µs per shape** (1,402,400 shapes in 0.70 s) and
**16.0 B/rect raw, 11.0 B zlib 6** — the measurement held, which is what it was for. The crash
that prompted the whole line of work (`Bins.add_grid`: `grid is (72, 124), this grid's is
(189, 253)`) was fixed independently, in Phase 1.

Reproduce every number below with:

    python sample_data/metal/bench_db_geometry.py --scale 50
    python sample_data/metal/bench_db_geometry.py --scale 200

and, for your own design (the projection then uses your DEF's own shape count):

    python sample_data/metal/bench_db_geometry.py --def <your.def> --lef lefs/*.lef \
        --tech-lef <tech.lef> --scale 2 --shapes <the emitted count your run reported>

## What is being evaluated

The 09-17 runs loaded dbs only, each block's db dumped by a separate standalone run
(`dev_plan/issue/real_design_log_0917.md`). They failed for one reason with two faces: a db stores
*rasterised* grids, so it is bound to the frame **and the grid** of the run that wrote it. One block
was refused on the frame, the other crashed on the grid.

`ShapeStream` accumulates every shape in the block's **own** coordinates and applies the frames only
in `flush()` (`routing.py:449-473`), so a db *could* store those batches and let the loading run
rasterise them against the live frames. That makes the dumps independent — and the price is that
the loading run pays the rasterisation again. **The rasteriser's share of the wiring pass is
therefore the floor of any replay**, and it is the number the whole decision hangs on.

## The measurements

One real routed DEF (`sample_data/metal/sub.def`, the committed sample), its wiring statements
repeated `--scale` times — real routing's shape-per-line ratio, coordinates reused. Two scales,
because a share that drifts with volume would be a share you cannot project.

| | scale 50, min of 3 | scale 200, one pair |
|---|---|---|
| fixture | 1,492,797 lines, 990,850 shapes | 5,930,397 lines, 3,963,400 shapes |
| wiring pass (the run's own `stage routing`) | **19.48 s** (19.48–20.31 over 3 runs) | ~76.5 s |
| the same build with the rasteriser dropping every shape | 19.14 s (19.14–20.03) | ~76.1–76.5 s |
| **rasterisation** | **0.36 s = 1.9 %** | 1.9 s / 2.5 % in one pair, **7.0 s / 8.4 % in another** |
| per measured shape (parse + classify + rasterise) | 19.66 µs | 19.5–21.1 µs |
| rects sampled for the section | 1,407,200 | 1,409,600 |
| **bytes per rect** — int32 database units, raw / zlib 6 | **16.0 / 11.0 B (68 %)** | **16.0 / 10.9 B (68 %)** |
| **replay, measured directly** — write the sampled batches in the proposed layout, read them back through a real `ShapeStream` into a real sink | **0.51 µs/shape** = read + inflate + rasterise | 0.51–0.64 µs/shape |
| the same shapes through a parse | 19.12 µs/shape | 19.5–21.1 µs/shape |

**Two things to read off this honestly.** The bytes-per-rect is stable across scales and runs to
within 1 %. The raster share is *not*: it is the difference of two long builds on a shared machine,
and two runs of the same scale-200 fixture gave 2.5 % and 8.4 %. In absolute terms the rasteriser
costs 0.4–7 s of a 20–80 s wiring pass, so the measurement's noise is of the same order as the
quantity. **Treat the raster share as "a few percent, bounded by ~8 %", not as a number** — which
is still an order of magnitude below the 40 % the bar asked about, but not precise enough to make a
five-minute threshold meaningful. Two methods were used and they agree in shape (both grow linearly
with volume): the null-sink difference quoted above, and a timed wrapper around the sink's own calls
(0.27 s at scale 50, 1.07 s at scale 200 — it sees the calls it knows about and nothing else).

## Projections, from those rates

| shapes | geometry section | **replay, from the measured 0.51 µs/shape** | parse + raster the same shapes |
|---|---|---|---|
| `lx956c_core_clamp_wrap` (44,395,406, from the 09-17 log) | **0.49 GB** (raw 0.71) | **0.4 min** | 14.2 min |
| 100 M | 1.10 GB (raw 1.60) | 0.9 min | 31.9 min |
| twice the top | 0.98 GB | 0.8 min | 28.3 min |
| four times the top | 1.95 GB (raw 2.84) | **1.7 min** | 56.6 min |

The replay column is a *direct* measurement, not a share extrapolated: the sampled batches are
written in the proposed layout (per layer and scope, int32 database units, zlib) and read back
through a fresh `ShapeStream` into a real sink, so the read, the inflate, the batch iteration and
the rasterisation are all inside the number. It comes out at **1/37 of a parse** — the reader does
0.51 µs of work per shape where the parser does 19.12.

That also retires the raster-share noise above: the share was only ever a way to estimate this, and
the estimate it gave (0.4 min for the top) agrees with the measurement to within the noise that
prompted it. The share stays in the report because clause 3 was written in terms of it, not because
the decision still rests on it.

For comparison, the same 1,696 s of parsing rebuilds from the **rasterised** db today in ~23 s. A
geometry db is a *second* flavour inside the same file, taken only when the fast path does not
apply — a re-placed block, or one dumped on its own.

**Re-measured after implementation** (same fixture, same scale, `--scale 50`, the bench now using
the real writer and the real `add_batch`): 1,402,400 shapes replayed in 0.70 s = **0.50 µs/shape**,
against 19.45 µs to parse them, and 16.0 B/rect raw / 11.0 B compressed. The raster share on this
run came out at 1.08 s of a 19.27 s wiring pass (5.6 %). Nothing moved outside the noise.

## Against the pre-registered bar

| clause | result |
|---|---|
| replay for the four-block design ≤ 5 minutes | **pass** — 1.7 min for four times the top's shapes, measured directly |
| geometry section ≤ 1 GB per block, ≤ 3 GB for the design | **pass** — 0.49 GB for the top's own shapes; 1.95 GB at 4× |
| raster share ≤ 40 % of the routing stage | **pass** — a few percent, bounded by ~8 % |
| the fast path survives when the design does match | **pass as a design property, not a measurement** — the rasterised grids stay in the same db, the loading run tries them first and falls back to the replay, and logs which. Nothing is removed. |

All four clauses pass, and the one that looked marginal does not: it was marginal only while the
replay was estimated from a noisy difference of two builds. Measured on the path it will take, the
replay is seconds per block.

## What the projection rests on

- **The fixture is a throughput fixture, not a layout.** One DEF's wiring repeated, so the
  shapes-per-line ratio is real and the coordinates repeat. Nothing in these numbers depends on
  where the shapes are, only on how many.
- **The per-shape rate is conservative.** 19.4 µs here against the real 09-16 run's 112.9 M shapes
  in 1,696.70 s = **15.0 µs** — so the projections above are ~25 % pessimistic on the parse side,
  and the replay projection scales with it.
- **The three sub-blocks' shape counts are not in the log** — their dbs were refused or never
  reached — so the design row assumes they total 3× the top. `--shapes` replaces the assumption
  with your own counts.
- **The compression ratio and the raster share are properties of the DEF's coordinate statistics**,
  measured here on the sample's. The command above measures both on yours.
- **The definition of validity narrows for a geometry db**: the shapes are pure DEF data, so the
  checks become the DEF stat, `--min-segment-length` and the measured layer set — not the frames,
  the grid size or the LEF identities, because the rasterisation happens live against the live LEF.
  That is the robustness the 09-17 failures were asking for, and it is a change to the checks, not
  only an addition to the file.

## Recommendation

**Implement it.** Every clause passes on measured numbers, and the sizes and rates are stable:

- **replay**: 0.51 µs/shape measured on the path it will take — **0.4 min for the top's 44.4 M
  rects, 1.7 min for a design four times that** — against 14.2 min and 56.6 min to parse them;
- **size**: 10.9–11.0 bytes per rect compressed, stable to 1 % across scales and runs — 0.49 GB for
  the top, ~1.95 GB for a design four times it, about a quarter of the DEFs' own uncompressed size;
- **the fast path is untouched**: the rasterised grids stay in the same db and are tried first, so
  the 23 s rebuild survives for a design that matches, and the replay is paid only where it is
  needed — a re-placed block, or one dumped on its own.

What it buys is what the 09-17 runs could not do: each block dumped in its own job, in any order,
with no parent at all, and a design re-placed later still loading from its dbs.

The one input still missing is your own DEF's numbers, and the reason to take it is the sizes
rather than the speed: the raster share on the sample is small enough that the replay is not in
doubt, but how many bytes per rect your wiring compresses to depends on its coordinate statistics.
One command at `--scale 2` on a DEF you already have answers it.

**That trade was taken.** The implementation is Phase 3 of `dev_plan/metal_def_db.md`: `ShapeStream`
gained an `on_batch` hook and a public `add_batch`, `A.def.db` became a streaming container with the
v1 npz reader retained, the workers write their own sections and the parent merges by concatenating
them, and the loading run tries grids → replay → refuse. The rejected alternative is recorded there
too: keep the rasterised db and add a **placement-only read** (a DEF named as context read for its
components, ~2–3 min, instead of its full parse), which removes the serialisation between dump jobs
without a byte of geometry — cheaper, but it still needs the parent DEF present at dump time, which
is exactly the dependency the 09-17 workflow could not satisfy.

The one measurement that would change the verdict is the raster share on your own DEF: run the
command above, and if the wiring pass is mostly rasterisation rather than parsing, the replay is
most of the parse and the second flavour buys little.
