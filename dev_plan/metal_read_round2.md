# Round 2: the single-core cost of the chip-level read

The plan for the two single-core runs recorded in
[`issue/real_design_log_0914.md`](issue/real_design_log_0914.md) — `lx956c_ioe`, 2.1 GB gzipped,
284.9 M lines, routing stage **5,940.63 s** of 6,006 s of compute, ≈102 min of wall clock. Round 1
is [`metal_routing_performance.md`](metal_routing_performance.md) and Phase 15-17 of
[`metal_density_asbuilt.md`](metal_density_asbuilt.md).

## Decisions taken with the user

- **Single-core efficiency first.** The parallel path stays available (the host has 96 cores and the
  queue tolerates ~16 for one job) and is deliberately deferred to the end of this document.
- **45° geometry is not a target.** In this design it exists only on `ALPA`, which the run
  *excluded* (`filtered_layers: ["ALPA", "M1", "TM1", "TM2"]`), so no diagonal can reach the
  rasteriser. The profile's 132.6 M shapely calls (14.5 % of the profiled run) therefore cannot be
  this design's data — either the deployed copy rasters something this checkout does not, or the
  share is cProfile inflation. `n_diagonals` goes into the log so the next run settles it; no
  diagonal code is written.

## What the log establishes

The routing read is 98.91 % of the compute; `components` 43.91 s, `cell-index` 11.18 s, `blockage`
9.54 s, `grids` 0.74 s. The shape population, which sums exactly to the run's 253,607,592: via
points 108,844,474 (42.9 %), **filtered 72,051,441 (28.4 %)**, emitted 51,851,532 (20.4 %), jogs
11,818,300, unknown (`ASK`) 4,539,783, degenerate 4,502,062.

**One statement is 20 % of the file and all of the memory story**: `statement_lines_max` 58,549,358
and `statement_chars_max` 4,979,560,694 for one power net. The parse holds, at once, a list of
58.5 M line strings plus their join (~1.94 × the text, measured), then a full-text wiring slice, and
then `list(finditer(...))` — a match object is 208 bytes, so ~57 M of them is 11.8 GB. Summed
across those stages that is ~27 GB, against the run's own `peak_rss_mb: 42123` on a `mem=20000`
request.

## The defects this turned up

**`ASK` is not a layer — it is `+ MASK` mis-parsed.** `re_special_wiring_form`'s `NOT_KEYWORD`
lookahead refuses the match at the `M` of `MASK`, `finditer` then advances **one character**, and
`ASK 1` matches as `layer=ASK, width=1`. It is the same one-character-advance failure the token
pattern already has a fix for (`WIRE_KEYWORDS`), never applied to the form pattern. It costs the
map, not just the log: the artifact form also ends the *preceding* form's tail, so those points lose
their class and the via points among them are counted nowhere. This design's tech LEF is a
three-mask process.

**`degenerate` (4,502,062) is explained**: a single-point or zero-length form carrying a width and
no `extValue`, plus zero-area `+ RECT`. It is a class, not a mystery — and the summary should say
which class, per layer.

## The phases

1. **Phase 1 — make the next run answer these questions by itself.** `n_diagonals` into the log (it
   is counted at `metal.py:451` and never read); a per-layer breakdown of
   `filtered`/`unknown`/`degenerate` (the first prices Phase 4, the second would have named `ASK` in
   one line); `"version": __version__` in `metal-summary`; floor `input_size`'s modulo-2^32 wrapped
   value for `.gz`. The generator gains `--min-layer`/`--max-layer` for `--real-shape`, without which
   the 28.4 % filtered class cannot be written at all.
2. **Phase 2 — bound the giant statement.** Three changes, none of which may alter the shape
   sequence: (a) a one-item lookahead instead of `list(finditer(...))` (~11.8 GB); (b) scan the
   statement in place — `__split_statement` returns positions and the form scans take
   `finditer(statement, start, end)` — instead of slicing it twice (~10 GB), verified equivalent over
   15,246 real statements; (c) accumulate a statement's text in chunks as it is read rather than
   holding every line and joining once. Pinned by a `tracemalloc` bound plus every existing golden.
   A fourth change — releasing the net to the sink in batches *inside* a statement — is held back:
   it is the only one that bounds a shape-heavy net, and the only one that can move last-bit grid
   values or double-fold a `PER_PLACEMENT_COUNTER`.
3. **Phase 3 — `+ MASK`, one line.** `FORM_FIRST` gains `(?<![A-Za-z0-9_])`: a form never starts
   inside a word. Measured on four fixtures: a via array goes `vias` 1 → 3, `unknown` 2 → 0 with
   `emitted` unchanged, and a `+ ROUTED … + MASK 1 …` form goes `emitted` **0 → 2** — the map gains
   metal it was dropping. No committed fixture contains `MASK` in wiring, and the guard changes
   nothing over 15,246 real statements, so no golden can move.
4. **Phase 4 — the filtered fast path**, gated on Phase 1's per-layer breakdown: skip the object and
   the tail scan for a form whose layer is outside the measured range, counting the shapes the
   stream would have counted (seven classification rules, derived from `_add_regular`,
   `_add_special` and `_layer`). This is also what makes filtered 45° geometry free.
5. **Phase 5 — the tokeniser's group calls**: `group('ext')` is called for tokens with no extension,
   and `group('via')`/`group('via_orient')` for every word before the keyword set rejects it.

## What it is worth

| lever | basis | estimate | confidence |
|---|---|---|---|
| Phase 2 (a+b+c) | 11.8 GB of match objects + ~10 GB of slices, measured | memory: 27 GB → ~10 GB; time: 100-300 s | high (a and b are verified no-ops) |
| Phase 3 | 4.5 M shapes move from `unknown`; two segments recovered per swallowed form | correctness, plus the parse of 4.5 M artifact forms | high |
| Phase 4 | 28.4 % of shapes, but they pay the *shared* per-form work | 200-500 s if multi-point, ~0.3 % if single-point | medium — decide on Phase 1's numbers |
| Phase 5 | ~1.7-2.2 B `group` calls ≈ 297 s | 100-250 s | medium-high |

**Honest target: ~1.3-1.5x single-core**, 5,940 s → ~4,000-4,600 s. Round 1's 15-minute read is not
reachable on one core: ~3.3 µs/line on pass 1 puts the file's text alone near 950 s.

## Verification

`python -m pytest -q`, with the pinned set unmoved (`SAMPLE_SHAPES` at `rel=1e-9`,
`emitted == 4 × 19,817 + 9`, gcd 2,504 via / 5 jogs / 2,327 rects / `metal2` mean 0.2527,
`verify()`); a `tracemalloc` bound test for Phase 2; a two-way fixture for Phase 3 (the artifact
numbers with the old pattern reconstructed, the corrected ones with the new); a counters-identical
on/off test for Phase 4; and the generator sweep before/after for the timing claims, recorded in the
as-built doc. The end-to-end confirmation is a real run, which is the user's to make — the summary
now carries what it needs to be read without a profiler.

## The parallel path, deferred

`--jobs` remains the largest lever — larger than everything above — and needs two things first: the
stride must be decided *before* the reader accumulates a statement's lines (today every worker holds
the 58.5 M-line power net, so four workers is ~35 GB on a 20 GB request and sixteen is certain
death), and Phase 2 must bound the statement in the pooled path too, where `parse_chunk` copies the
chunk's text again. The cancellation work in [`pooled_cancel.md`](pooled_cancel.md) is what makes
trying it cheap.
