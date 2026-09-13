# The 7005-second routing read: find the cost, then remove it

The plan for metal mode's turnaround on a real chip-level DEF. What the measuring turned up is in
[`metal_density_asbuilt.md`](metal_density_asbuilt.md) under *Phase 15*. Phases 0, 1, 3 and 4 are
executed; Phase 2 is evaluated below and waits on one number from a real run.

## What prompted it

[`real_design_case_record.md`](real_design_case_record.md) records a real run of `lx956c_ioe`
(18 layers, 3,355,697 instances, 17,385 macros from 221 LEF files, a ~30 M-line gzipped routed
DEF). The routing read - pass 2, the NETS/SPECIALNETS pass - took **7005 s (1 h 57 m)**; the
stages beside it are noise: pass 1 25 s, both LEF passes 21 s, tech LEF 0.025 s. The job peaked at
18.9 GB of a 20 GB request, single-threaded, one core at 100 %.

[`performance_improvement.md`](performance_improvement.md) is a proposal list from another agent,
explicitly unverified, claiming "5-10x". It was evaluated before planning, and its ranking does not
survive the run's own numbers:

| its claim | what the code and the log say |
|---|---|
| #1 the line-by-line DEF loop is the bottleneck, "~1000 s for 10^8 statements" | pass 1 reads the **same file** through the same `fetchLine`/gzip loop at **4.2 µs/line** (6 M lines in 25 s); pass 2 is 233 µs/line. The line loop is ~2 % of the run, and the observed total is 7x its estimate |
| #2 `ShapeStream`'s `list.append` (4x10^8 calls) | real, but ~0.1 µs each |
| #3 the rasteriser's `np.repeat` piece expansion | correctly assessed as already-optimised, and its recorded rejection reason is quoted accurately |
| #4 fusing the frame transform into the rasteriser, "1.5-2x" | the transform is already vectorised per batch (`routing.py:312-314`) |
| #5 parallel bands, "segments span ~1 bin vertically" | false for vertical layers, whose wires run the die's full height; the independent axis is the layer, not a band |
| #6 optional numba JIT | cannot help the parser, which is where the time is, and adds a dependency |

**And my own first four fast paths did not survive either.** An adversarial review killed three of
them with working counterexamples against the real code:

- "count a `+ VIA` array's points without tokenising it" - `last`, the `*` coordinate-reuse state,
  is shared across forms and via points *write* it (`defParser.py:443`, `:354`), so the later
  `( * 900 )` in the next form resolves differently or raises.
- "fewer than two points emits nothing" - false in both branches: a single-point `+ ROUTED` form
  is a real 0.24 x 0.14 um rect from its extension field, and a single-point regular form is a
  deliberate zero-length wire counted as `n_via`. Measured on the vendored gcd DEF: the guard takes
  `n_via` from 2504 to 66 (or 0).
- "count unknown-layer shapes as `points - 1`" - there are four different counting rules, not one:
  a 4-point `+ POLYGON` on an undeclared layer is 1 unknown + 3 polygon edges, a `+ VIA` is 2 vias
  and 0 unknown.

What survived is one tokeniser change, and the arithmetic that says the cost is somewhere else
entirely. The measured per-shape constants - `DefSWire` allocation 863 ns, tokenising a short tail
890 ns, `_add_special` dispatch 129 ns, the raster 602 ns/shape - sum to **~500 s of the 7005 s
run, a 14x gap**. Neither proposal document locates the dominant cost, and neither does this plan
yet.

## Decisions taken with the user

- **Surgical, measured first.** No architecture change until a measurement calls for one; measure
  after each phase and stop when the target is met.
- **Synthetic verification.** The benchmark reproduces the shape mix; no design file is shared.
- **Success = wall clock**, plus progress/ETA/cancel, plus a log that identifies the bottleneck on
  the next real run. Proposed threshold: the routing read at **<= 15 min**.
- **Parallelism is evaluated, not assumed.** More CPU time for less turnaround is acceptable, but
  not complexity the single-core work makes unnecessary.

## Phase 0 - find the missing 90 % (the gate)

Extend the repository's own harness, `generate_metal.py --stress N`, which cannot reproduce the
real input: it writes plain text (the real file is `.gz`), `COMPONENTS 0`, no SPECIALNETS, no via
arrays, no NDR-referencing nets, four layers, one line per statement.

New profile with knobs, so a *sweep* separates linear cost from non-linear: `+ VIA` arrays of
1/8/64/512 points on one line and across several; one enormous power net as well as many small
ones; die-spanning stripes (the raster's pieces-per-shape goes from 2-6 to 100+, which is exactly
the case the recorded difference-array rejection did not measure); `+ RECT`, `+ POLYGON`, taper
rules, `+ NONDEFAULTRULE`, `*` reuse; 15-18 layers with 2-3 deliberately absent from the tech LEF;
a few 100 k COMPONENTS; `--gzip`.

Measure with stage timers, `cProfile` self-time, GC statistics (`gc.callbacks` time, collection
counts, live objects) and RSS. Calibrate by multiplying the per-class constants by the run's own
counters (124,711,987 / 12,964,342 / 4,539,783 / 4,517,711) and compare with 7005 s.

**Leading hypothesis for the amplifier: the live-object set.** The parser releases a net only at
`__release` (`defParser.py:561-574`), so the run's peak is one giant net materialised whole, and
pass 2 additionally retains 3.36 M `DefComponent` objects that nothing reads. A multi-million-object
live set makes every gen-2 collection scan it - invisible in a small-net benchmark, absent from both
documents' models. The decisive experiment is ~5 lines: time in GC against time in the loop.

## Phase 0 findings (measured)

The harness is `generate_metal.py --real-shape`, which writes the mix the counters describe -
via arrays in both real spellings, a giant power net, die-spanning stripes, undefined layers,
jogs, NDR-referencing nets, 3.36 M instances, a gzipped DEF when asked - with knobs for points
per form, lines per form and number of via nets. It runs on this development machine at the same
speed as the machine Phase 5 measured on (`--stress 200000`: 10.55 s here against 11.5 s
recorded), so the constants below are comparable.

**1. The cost is ~12 us per shape and ~200 ns per character of DEF text, and both are linear.**
Measured across a 10x range of scales with no super-linear behaviour anywhere:

| measurement | value |
|---|---|
| per via-point shape (200 k vs 2 M via points) | 13.5 -> 12.5 us, constant |
| per routing line (200 k vs 2 M) | 15.6 -> 19.1 us, constant |
| one giant power net vs 1,000 nets, same shape count | 19.1 vs 18.2 us/line - no difference |
| points spread over 8 lines vs 1 | 12.7 vs 19.1 us/line - no penalty |
| gzipped vs plain input | 19.2 vs 19.1 us/routing-line - gzip is free |
| the real OpenROAD gcd DEF, as the reference | 200 ns/char, 11.8 us/shape - the same constants |

**2. Garbage collection is not the amplifier.** At 3.36 M live objects (the real instance count)
GC is 4.96 s of a 41 s run, 12 %; at 20 k instances it is 3 %. The giant-net case costs 1.14 s
of GC against 0.43 s for 1,000 nets - real but 3 %.

**3. The profile says where the 12 us goes.** For a via-heavy run, `__add_special_wiring` self
time is 1.54 s of 5.1 s and `__scan_tokens` is 1.47 s: the two regex scans are ~40 % of the run
(59 % in the profiled run, which inflates). Measured directly, `re_special_wiring_form.finditer`
costs **135-200 ns per character** of the wiring text (perfectly linear over 8.6 kB to 8.6 MB)
and `re_wire_token` costs 63-104 ns per character of each tail. The rest is object creation
(863 ns per `DefSWire`) and per-shape dispatch.

**4. The model still under-predicts the real run by ~3.4x, and the reason is now specific.**
By the counters: 147 M dropped shapes x 12.5 us = 1838 s, plus 41 s of components, ~130 s of line
reading, ~20 s of LEF passes and a small raster - about 2,100 s against the observed 7005 s. The
log counts only the shapes it *drops*. **It never reports how many shapes it measures**, and for
a chip-level design that count is plausibly 100 M+ (the arithmetic closes at ~250 M total
shapes). So the missing factor is not a pathology to remove: it is a shape population the log
does not mention. A counter for emitted shapes is therefore the first thing Phase 4 adds, and it
is what makes the next real run's calibration exact.

**5. So there is no hidden quadratic to delete.** The cost is genuinely per shape, spent in
tokenising, allocating and dispatching each one, and the levers are: make the two regex scans
cheaper per character (the largest single factor, ~40 %), allocate fewer objects, and process
shapes in parallel. The 12.9 M jogs and 9.0 M unknown/degenerate shapes are full-price shapes
whose outcomes are decided late - but the review showed they cannot be skipped earlier without
changing the metric, so their cost stands.

## Phase 1 - remove the located cost, biggest first

*(Executed: the two regex scans, the via fan-out, and the retained instance objects. Measured
results and the equivalence arguments are in the as-built doc's Phase 15.)*

Each fix carries an equivalence argument, and a fix that cannot be shown equivalent does not land.

1. **GC / allocation amplification**, if Phase 0 points there: `gc.disable()` around the routing
   read with a collection at each flush boundary, or `gc.freeze()` after the library loads.
2. **The tokeniser** - the one fast path the review kept. Drop the ~40-keyword negative lookahead
   from `re_wire_token` (`compiledRe.py:66-68`, retried at *every character position*): 0 point
   divergences over 19,646 real tails, and equivalence is about the points and `last`, not via
   names. Guard `re_glued_star.sub(' ', tail)` (`defParser.py:348`) with `'*' in tail` - provably a
   no-op otherwise, worth 6.7 % of the gcd parse.
3. **The giant-net allocation**: in the `+ VIA` branch, keep scanning (so `last` holds) but count
   `len(points)` instead of building a `DefSWire` per point. ~1.8 % of the clock, but it removes
   the object spike behind the 18.9 GB peak.
4. **Retained instance objects**: `skip_comp` on pass 2 (it already exists and is unused;
   `DefRouting.components` has no consumer), the leftover `data` local at `metal.py:393`, and
   `__slots__` on `DefWire`/`DefSWire`.
5. **Raster pieces**, if Phase 0 says so: re-measure the difference-array scheme for die-spanning
   stripes rather than assuming the recorded rejection still holds.
6. **Per-line cost**, if Phase 0 shows one: `__read_statement` is linear (verified), so it would be
   a form regex backtracking on long statements - profile-driven, not guessed.

## Phase 2 - the parallel option, evaluated

*(Executed: `vlsi_viewer/parallel.py`, `--jobs N`, off by default. The scaling below is measured
on this machine, with one design iteration in the middle of it that the measurement forced.)*

**The first version was slower than one process, and the measurement said why.** It cut the DEF
into blocks in the parent and shipped the text to the workers: measured on a 5 M-line input,
53 s against 44 s, flat from two workers up. A chip-level DEF is gigabytes, and moving it
through pipes costs more than parsing it. The design is now that **every worker reads the file
itself** and keeps every `jobs`-th net statement; only per-layer grids come back, a megabyte a
worker.

**What that costs, measured:**

| | |
|---|---|
| one worker through the machinery, 9.1 M lines | 73.1 s against 64.9 s sequential - **the machinery is +13 %** |
| two workers, same input | 51.5 s (1.26x over sequential) |
| four workers | 34.3 s (1.9x) |
| eight workers | 28.5 s (2.3x) |

The shape of those numbers is the whole evaluation: `wall ~= 8 s of machinery + parse/N + ~10 s of
per-worker scan and startup`, so a 65 s job is mostly fixed cost. **For the real design those
fixed terms are noise**: 30 M lines is ~23 s of scanning per worker (in parallel, one floor to
the wall) against a ~3000 s read, so the same model predicts **~3.9x at four cores** - the
Amdahl ceiling, since the only sequential part left is that scan. That is a prediction from the
measured terms, not a measurement at scale: a 3000 s synthetic would be 430 M lines, which is
not something to build on a workstation.

**It also needed a fix that only a realistic input would have shown.** The first synthetic put
2 M via points into *one* 500,000-line power statement, and a statement is atomic - its `*`
coordinate state cannot be split across workers - so no pool can parallelise that shape, and the
measurement showed none. Real DEFs hold millions of statements (the run's 124.7 M via points
across ~24 M lines cannot be fewer than ~5 M statements); with a statement count of that order
the pool scales as above. Worth knowing before trusting a benchmark's statement-size
distribution.

**Decision: adopted, off by default.** `--jobs 1` is the default and does not go through the
machinery at all, which the +13 % above is the reason for. The equivalence tests
(`tests/test_metal_parallel.py`) compare a pooled build against a single-process one on the
committed sample - counters exactly, grids to float32 rounding - and the block cutter's own
invariant is pinned separately, because a split statement would still parse and still draw, just
in the wrong place.

### The original evaluation, before implementing

The sequential fraction is only the reader: `fetchLine`, the `re_net` test per line, and joining
a statement's lines. Pass 1 measures that loop at 4.2 us/line, so 30 M lines is ~126 s of the
7005 s, **~2 %**. Everything after - tokenising, shape construction, the keep-out arithmetic, the
rasteriser's piece expansion - is per-net and per-shape work with no cross-net dependency, and
each layer's grid is independent. Amdahl at four cores: 1 / (0.02 + 0.98/4) = **3.4x**. After
the single-core work lands, the reader's share grows (it is the part that did not get faster):
at a ~3000 s total it is ~6 %, and the ceiling is 3.1x.

The design that makes that real, and its constraints:

- a `spawn` pool, not `fork`: the parent holds the instance table and the grids, and a forked
  worker would inherit all of it;
- the unit of work is a **block of complete statements**, cut on the same `;`-at-end-of-line rule
  the parser uses, with the section (NETS or SPECIALNETS), the database unit and the NDR table
  carried alongside - so a worker needs nothing the parent has not already read;
- each worker accumulates its **own** grids and returns them once at the end: 18 layers x 123 x
  107 x 4 B is 1 MB per worker, so the IPC is negligible and worker memory stays flat;
- a bounded queue, so the reader cannot run ahead of the workers;
- the reader must hand lines to workers from memory, which means `DefParser` needs an input path
  that is not a file - the one real refactor this asks for, and the reason it is a phase of its
  own rather than a tweak.

Costs to be honest about: the grids then sum in a worker-dependent order, so the last bits of a
float32 sum can differ from a single-threaded run (the tests compare with tolerances); and the
whole thing is ~200 lines of new code plus its equivalence test, which is complexity that only
earns its place if the target is real.

**Decision rule, and where it stands.** Adopt only if the single-core result misses the target by
more than the ceiling above can cover. Today's single-core result is 2.4x on the dominant class
and ~1.2x elsewhere; a chip-level run would plausibly land near 3000 s, against a proposed target
of 15 min - so the rule says **adopt**, and 3.1x would put it at about 1000 s. The one number that
could change this is the shape population: if the emitted count that the new log reports turns out
to be far below 100 M, the remaining work is smaller than modelled and the pool may not be worth
its complexity. That is why the recommendation is "implement it after the next real run", not
"implement it now".

## Phase 3 - live feedback

Time-based heartbeat (every ~30 s: lines, lines/s, ETA, RSS) instead of the line-based one, which is
230 s of silence per line at the real run's rate; flushed per line, since a piped log is
block-buffered and a killed job loses its tail. Fix `CURRENT_LINE_CNT`/`LINE_CNT_STEP`, which are
class attributes incremented via `self.` and never reset, so pass 2 continues pass 1's count.
Cancel checked at flush boundaries.

## Phase 4 - the log strategy: make the next real run self-diagnosing

Because verification is synthetic, the run has to carry the evidence back. The log gains: stage
lines (elapsed, input, rate, RSS) - today the only elapsed time is the parser's own, which mixes
parsing with conversion and rasterisation; per-class counts *and seconds*; **input
characterisation** (points per form mean/max/p99, lines per statement, longest statement, biggest
net by points and objects, layers used, layers used but not in the tech LEF) - the field that says
whether the real file resembles the benchmark at all; **memory and GC** (RSS per stage, collections
by generation, time in GC as a % of the run, peak live objects), which kills or confirms the leading
hypothesis in one line; parameters and input identity; and a single `metal-summary:` JSON line
carrying all of it. `--profile [PATH]` wraps the build in `cProfile` and prints the top 15 by self
time - the only way to split parser-self from sink-self, since the sink is called from inside the
parser's loop.

Per-shape timers sit behind `--timing` so ordinary runs pay nothing; stage and characterisation
lines are always on and cost O(1) per stage.

## Rejected, with the measurement behind the rejection

Block-mode parsing of the line loop (~2 % of the run); ring buffers and transform fusion (numpy is
already entered once per 65,536 shapes); band-parallel raster (wrong axis); numba (cannot help the
parser). Counting points without scanning, skipping sub-two-point forms, and counting unknown layers
as `points - 1` - all three corrupt the metric, as the review's counterexamples and the gcd
fixture's own pinned numbers show.

## Verification

`python -m pytest -q` (500 tests) is the equivalence oracle, with the pinned real-file numbers
unchanged: gcd `2504 / 5 / 0 / 0 / 0 / 0`, rects 2327, `means["metal2"] == 0.2527`; the sample's
`sub.def` 135 jogs and 19,817 rects; `top.def` 3 polygon edges. New tests: cross-form `*` after a
`+ VIA`, the single-point extension rect, the four unknown-layer counting rules, a tokeniser
differential over every fixture tail, a full-tuple golden per fixture, and a parse check on the
`metal-summary:` line. Before/after is reported on the harness (stage seconds, per-shape cost, peak
RSS, GC time). If Phase 0 shows the cost is irreducible per-shape Python work at 10^8 shapes, that
will be said plainly - the options then are Phase 2 or a coarser grid, not a promise.
