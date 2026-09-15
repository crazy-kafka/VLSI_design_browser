# Evaluating byte-range work units (Phase 3): measure first, decide after

**Status: recorded, not enabled.** The evaluation is finished and the numbers are below. The switch
was left off — `RANGE_WORK_UNITS = False` in `vlsi_viewer/parallel.py` — so no default, no CLI
option, no log line and no measured number changed for a user. The prototype, its tests and the
benchmark stay in the tree as the instrument for the deferred decision; removing them is
`git checkout -- vlsi_viewer/parallel.py` plus the byte-range tests in
`tests/test_metal_parallel.py`, and nothing else depends on them.

Reproduce the whole table with:

    python sample_data/metal/bench_work_units.py                     # both fixtures
    python sample_data/metal/bench_work_units.py --only "one giant statement" --scale 10

and settle the projection, when it is worth settling, by setting `RANGE_WORK_UNITS = True` and
running `--jobs 8` on the real design against `dev_plan/issue/real_design_log_0915.md`.

The prototype is real code, reachable only through that constant — the same shape as
`BYTES_PER_WORKER` and `DEFAULT_CHUNK_STATEMENTS`, which is what lets a test and the benchmark run
both splits in one process.

## What is being evaluated

The routing stage took **1,780.64 s** at 8 workers (`dev_plan/issue/real_design_log_0915.md`) against
5,940.63 s single-core. Two terms in it are not the parse:

| term | measured | source |
|---|---|---|
| per-worker statement scan | **211 s each, ×8** | every worker runs the statement logic over all 284.9 M lines, keeping one statement in eight |
| statement-count imbalance | **~850 s** | the split is by statement count, and one power net is 20 % of the file and one work unit |

The 211 s is the scan *around* the read, not the read: the file iterator is already C-level and was
measured at 0.14–0.22 µs/line, while the statement logic costs 0.742. Byte ranges replace
eight whole-file scans with one cheap parent scan (statement starts only) plus a scan of the ~1/8
each worker actually parses.

**The ceiling does not move.** The giant power net is a 58.5 M-line statement and ~830 s as a single
chunk, so the projection is `parent scan + that chunk` ≈ **~890 s (~2×) at 8 workers, and 16 workers
buys nothing** until that statement itself is split (deferred).

## Pre-registered bar

Decided before the measurement, so a disappointing result cannot be argued away afterwards. Wire it
in only if: equivalence is **exact** on counters and identical on stats for every fixture; ≥ **1.5×**
wall at 8 workers on the giant-statement fixture with no regression at 2 or 4; the projection for
`lx956c_ioe` is ≥ 1.5×; peak RSS is not higher; and `jobs=1`/sequential are unaffected. Otherwise the
numbers are written up and this stops.

## What the prototype must preserve

The three *silent* failure modes matter most — each is a wrong answer that still looks plausible:

- **`preamble` + `rules`** feed `Chunk.header`; without them the parser cannot build, and without the
  rule table a net naming a non-default rule silently falls back to the layer defaults.
- **declared counts and `_found`** feed `check_counts`; empty on both sides means the check *passes*
  while checking nothing.
- **`lines`** is the summary's input line count, and the reader's whole-file scan is its only authority.

Plus: `*` state is per statement, so cuts may only land on statement starts; offsets come from a
binary read and cuts land on a `\n` byte; the slice is decoded with the same default text encoding
`_open()` uses; and the scan's offsets are only valid for the file revision it scanned (re-stat
guard). Since the scan reads bytes and the readers read text, a DEF whose line endings are not `\n`
or `\r\n` (a lone `\r`) would make the two disagree — the guard for that falls back to the stride.

## What the report carries

The scan cost measured both ways at two line lengths; the matrix (`jobs ∈ {1,2,4,8,16}` ×
`{stride, ranges}` × two fixture shapes) with wall, per-worker span, bytes read and peak RSS;
equivalence as exact counter comparisons; the `lx956c_ioe` projection with its terms; and each
safety item above as a passing test.

## Result (measured, this checkout, 16 cores)

Reproduce with `python sample_data/metal/bench_work_units.py --only "one giant statement" --scale 10`.

### The scan, both ways

| fixture | statement logic (what each worker runs today) | the scan that replaces it | ratio |
|---|---|---|---|
| 1.39 M lines, 17 B/line | 0.69-0.71 µs/line | 0.29-0.37 µs/line | **2.0-2.4× cheaper** |
| `sub.def`, 48 B/line | 0.78-0.80 | 0.42-0.45 | 1.8-1.9× |

Not the 4× the per-part breakdown suggested: the binary iteration (0.05 µs/line) and the `;` search
(0.11) are common to both, and they are most of what is left. Getting here needed two fixes found by
measurement - a lone-CR test that scanned every line's bytes (0.17 µs/line, a third of the pass) and
per-line `bytes` slicing (0.09) - and one found by reasoning: `lstrip()[0]` on a blank line raises.

### End to end, giant statement 17.5 % of the file (the real design's share is 20.5 %)

| mode | jobs | wall | vs sequential | slowest worker | total read |
|---|---|---|---|---|---|
| sequential | 1 | 10.5-10.7 s | 1.00× | - | 53.7 MB |
| stride | 2 / 4 / 8 | 8.2 / 7.3 / 7.1-7.5 | 1.3-1.5× | 5.5 / 4.3 / 4.1 s | 107 / 215 / 429 MB |
| ranges | 2 / 4 / 8 | **9.9** / 6.9-8.4 / **5.9-6.1** | 1.07× / 1.3-1.6× / **1.74-1.80×** | 6.4 / 3.5 / 2.1 s | 53.7 / 53.7 / 107 MB |

At 8 workers ranges is **1.19-1.23× faster than stride** and the slowest worker drops 4.1 → 2.1 s.
At **2 workers it loses** (9.86 vs 8.26): the parent's scan is serial and there is not enough
parallel work to repay it.

### Equivalence

Every pooled run above reports `equivalent = yes`: counters equal **exactly**, `forms` and `lines`
identical, grids `allclose(rtol=1e-6)`. 596 tests pass, 8 of them new - including the equivalence of
a range build against both the sequential and stride builds, and a deliberately miscounting scan
that must fail the run rather than measure less (`the statement scan and the readers disagree`).

### The projection for `lx956c_ioe`

Measured coefficient × the log's own terms: parent scan 284.9 M × 0.37 µs = **~105 s**; the giant
net's chunk **830 s** (the 0915 log); the other workers ~716 s each. Wall ≈ **935 s against the
logged 1,780.6 s = 1.90×**. This is a projection, and it rests on the real design being far more
imbalanced than the fixture - workers 6.0/19.5 s under stride there against 2.2/4.1 s here - because
its net sizes vary and the fixture's mostly do not.

## Against the pre-registered bar

| clause | result |
|---|---|
| equivalence exact, every fixture | **pass** |
| ≥ 1.5× wall at 8 workers on the giant fixture | **fail** - measured 1.19-1.23× |
| no regression at 2 or 4 | **fail at 2** (9.86 vs 8.26), pass at 4 |
| projection for the real design ≥ 1.5× | **pass** - 1.90× |
| peak RSS not higher | **not measured** - psutil is absent on this machine |

Two clauses fail as written, so by the bar this is a **no-go on the fixture numbers alone**. The
reason the two disagree is worth stating plainly: the fixture's own imbalance is a third of the real
design's, so it understates the term that byte ranges actually remove. That is an argument, not a
measurement - the measurement that settles it is one `--jobs 8` run on `lx956c_ioe` with the
constant flipped, compared against the 0915 log.

If it is enabled, do it for `jobs >= 4` only.

## A fixture lesson worth keeping

The first version of the giant fixture carried two million component instances, and the `components`
pass — read in the *parent*, before any pool exists — took 12.7 s of a 41 s wall. Every pooled
number was then a comparison of a serial stage with itself, and the change under test vanished into
it. The real design's components stage is 44 s of 1,780. A fixture for a pool question has to be
sized to the stage under test, and the stage breakdown is what showed it: `jobs=1` and `jobs=8` had
the same `components` seconds while `routing` moved.

The other measurement that had to be thrown away first was the plan's own claim that the scan would
be a fraction of the statement logic. It is 2.0-2.4× cheaper, not 4×, and it took three fixes to get
there — a lone-CR test that scanned every line's bytes (0.17 µs/line, a third of the pass), per-line
`bytes` slicing (0.09), and a `lstrip()[0]` that raises on a blank line inside a section.

