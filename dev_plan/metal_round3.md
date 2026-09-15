# Round 3: a readable metal log, byte-range work units, and the 8.78 M "diagonals"

Three pieces of work, in the order the user raised them. The third changes what the tool measures,
so it is the one to read first.

## 1. The 8.78 M "45-degree shapes" are not in the design

The user confirmed 45° routing cannot exist from M2 to B2 by design rule, so the `diagonals` counter
had to be reporting something that is not metal. It is. Cadence *LEF/DEF 5.8 Language Reference*,
p874, defines the last element of `routingPoints`:

> **`VIRTUAL ( x y )`** — "Indicates that there is a **virtual (non-physical zero-width) connection**
> between the previous point and the new `( x y )` point. An `*` indicates that the x or y value is
> to be used from the previous point. The layer remains unchanged. You can use this keyword to
> **retain the symbolic routing graph**."

A virtual connection is a graph edge, not a shape, and nothing constrains a non-physical edge to be
orthogonal — the reference's own Example 7-12 (p876) writes one that is neither orthogonal nor 45°:
`+ ROUTED M1 ( 0 0 ) ( 5 0 ) VIRTUAL ( 7 1 ) RECT ( -3 0 -1 2 ) ( 7 7 ) ;` (dx=2, dy=1, on M1).

`VIRTUAL` is not in `WIRE_KEYWORDS`, so `__scan_tokens` reads it as a *via name* and its point
becomes a wire corner, measured as a full-width wire with keep-out. Reproduced in this checkout:

```
+ ROUTED M3 ( 0 0 ) ( 100 0 ) VIRTUAL ( 200 200 ) ;
  -> 'M3' (0,0)->(100,0)      (the real wire)
  -> 'M3' (100,0)->(200,200)  (a virtual connection, reported as a 45° shape)
```

So about **15.6 % of the run's `emitted` area is not there**, and `metal.py`'s log line is wrong
twice: the slope is arbitrary, and the segment is not metal at all.

The same two reference pages give two more deviations, both reproduced:

- **`RECT ( deltax1 deltay1 deltax2 deltay2 )`** is dropped silently today. p874: "a rectangle is
  created from the previous `( x y )` routing point using the delta values. The RECT values **leave
  the current point and layer unchanged**."
- **A via switches the layer**: "If you specify a via, layerName for the next routing coordinates
  (if any) is implicitly changed to the other routing layer for the via." This parser attributes
  every segment in a form to the form's layer: `+ ROUTED M3 ( 0 0 ) ( 100 0 ) V4 ( * 200 ) ( 300 * )`
  returns all three segments on `M3`, where the reference puts the last two on `M4`. The fix needs
  the via's two layers, which the reference defines through the via master — inferring them from the
  name is a trap (`via1_4`/`via2_5` encode the **lower** layer and the cut count) and
  `lefParser.py:47` skips `VIA` stanzas. So this one is *measured* first: count forms where a via has
  a real point after it. Measured on the committed real DEF for scale: 2,438 of 4,746 wires carry a
  via and **100 % of them are zero-length**, so the switch would change nothing there.

The `*` implementation, by contrast, is **correct** — p874 says exactly what `__scan_tokens` does
with `last` — so that candidate was ruled out by evidence rather than argument, as was a missed form
boundary (any merge of two forms would push `points_max` above the run's 2).

**How the next run confirms this**: a `virtual` counter, and for the first 5 non-orthogonal segments
that still survive as metal, the net name, layer, both points in database units, whether the form
text contains `*`, and the form's first 200 characters. If `virtual` lands at 8.78 M the case is
closed; if it lands near zero the samples show the raw text that produced them.

**Landed.** `VIRTUAL` and the inline `RECT` are now their own tokens, ahead of the generic via-name
alternative, and a virtual connection emits no shape while its point still carries the path
forward. The rectangle is resolved to absolute corners at parse time - the only moment the point
its deltas are relative to is known - and emitted as a box grown by half the spacing rule like any
other metal. The reference's own Example 7-11 and 7-12 are the fixtures, and the metric test does
the arithmetic by hand: on M3 at 0.1/0.1, `(1,3)-(6,3)` (1.04) + the `RECT` (4.41) + `(8,4)-(8,9)`
(1.04) = 6.49 um^2, with the virtual connection contributing nothing and `diagonals` reading 0.

Two things that cost time and are worth writing down:

- **The metric clips to the die.** A fixture of mine sat on the die corner, so a wire straddling
  it contributed only its inner half (0.51 rather than 1.04) and the hand arithmetic looked wrong
  when the code was right. The existing hand-arithmetic tests all place their shapes away from the
  edge for this reason.
- **A test that swaps a compiled pattern into a module-level name and restores it *after* the
  assertions poisons every test after it** when it fails. `test_real_samples.py` did exactly that
  with `re_wire_token`, and my change made it fail, which produced 30 failures in unrelated files
  all reading `IndexError: no such group`. Both that test and the one in `test_def_nets.py` that
  swaps `re_special_wiring_form` now restore in a `finally`.

The count that closes the case is still the next run's: `virtual` against 8,777,752.

## 2. The routing pass: imbalance, and a scan every worker repeats

| term | measured | how |
|---|---|---|
| routing stage, 8 workers | 1,780.64 s | was 5,940.63 s single-core (3.34x) |
| **lost to statement-count imbalance** | **~850 s** | the largest single read is **829.6 s** — one chunk, 58.7 M lines, the power net |
| **per-worker file scan** | **211 s** each, eight of them | 0.742 µs/line over 284.9 M lines, measured here |

The classes partition the total exactly (56,375,666 + 108,844,474 + 11,796,228 + 72,051,441 =
249,067,809 = `total`, `diagonals` ⊆ `emitted`), which with the reference's grammar says what
`points_max: 2` means: **every wire in this DEF is a one-segment form** — 124,356,542 two-point
forms, the rest one-point via placements.

**Scanning in blocks was tried and dropped, with numbers.** `Reader._lines()` was rewritten to read
a block and split it there, on the plan's figure of 0.742 → 0.252 µs/line. It is *slower* at every
block size tried, and for both implementations (slicing lines out of the block, and the C-level
`splitlines`):

| | `sub.def` (48 chars/line) | synthetic, 17 chars/line |
|---|---|---|
| the file iterator | **0.22 µs/line** | **0.14 µs/line** |
| block + slice, 1 MB | 0.43 | 0.36 |
| block + `splitlines`, 1 MB | 0.28 | 0.19 |
| block + `splitlines`, 256 KB | 0.24 | 0.16 |

Python's per-line file iterator is already implemented in C; re-deriving the lines in Python adds a
generator layer and a per-line scan on top of work that is done for free. It also raised the peak
memory of a skipped statement from ~0 to ~36 MB (an 8 MB block materialises that much in line
strings), which the reader's own memory test caught — so the change was reverted and the test
removed with it. The 211 s per worker is the *statement* logic around the read, not the read.

## The byte-range evaluation is done, and the switch is off

`dev_plan/metal_work_units_eval.md` carries the whole measurement: the scan is 2.0-2.4× cheaper than
the statement logic each worker runs today (0.29-0.37 against 0.69-0.71 µs/line), a pooled range
build is **1.19-1.23× faster than the stride at 8 workers** on a fixture shaped to the real design
(giant statement 17.5 % of the file), it reads a quarter as much, it *loses* at 2 workers, and the
projection for `lx956c_ioe` is 1,780.6 s → ~935 s (1.90×). Equivalence is exact on every fixture.
Two of the five pre-registered clauses fail, so it was recorded rather than enabled: the prototype
stays behind `RANGE_WORK_UNITS = False`, and the decision waits on one `--jobs 8` run of the real
design.

What is left is the change that removes work instead of moving it:

- **Work units are byte ranges, packed by the parent.** The parent decompresses a `.gz` once to a
  temporary file (this design's 2.1 GB is *stored*, so that is I/O, not CPU), scans it once
  recording each net statement's first-line offset, packs statements into one range per worker **by
  bytes** and cuts only at a statement start (so the giant statement stays whole), and each worker
  reads only its own ranges through the existing `Chunk`/`parse_chunk`. Invariants: every statement
  parsed exactly once, in file order within a worker; `check_counts` still sees every statement;
  cancel, salvage and `note` unchanged. The *partition* moves — that is the point of packing by
  bytes — and the equivalence test is written for exactly that: counters are integers and compare
  equal, and the grids are compared with `np.allclose(rtol=1e-6)`, which is the rounding of a
  different summation order. The `stride` stays as the fallback for a caller that cannot seek.

  The parent's scan has to be cheaper than the one it replaces, so it does one thing: test a line's
  first character (`-`) and match `_NET` on the few that pass. That is the read plus a comparison,
  ~0.2 µs/line and ~60 s over 284.9 M lines — not the 211 s a worker spends on the same file, which
  is the full statement logic, and not the block reader the measurement above rejected.

Ceiling after that: the parent's ~60 s scan plus the giant net's ~830 s chunk — **~15 min at 8
workers and no better at 16** until the giant statement itself is split (deferred; the hazard is
that `*`
state is per statement, so a worker starting mid-statement mis-resolves every `*` after it while
every counter stays plausible).

## 3. A metal log you can read

The bulk of the log is the DEF parser's own progress lines, and `DefParser.__init__` hard-wires
`self.puts = print`, so eight workers write to one stdout with nothing saying which spoke. The
summary is one `json.dumps` record with ~20 top-level keys including a per-layer list.

- `DefParser` takes an injectable `puts`, defaulting to today's `print`/`Print`, so the JSON path and
  the parser-level heartbeat tests are untouched. Metal mode passes a callable that tags a worker's
  lines `[w{index}] ` on stdout, and gives the child a *replacing* logging handler with the same tag
  (adding one instead would double-print every record under fork).
- The summary dict is unchanged; a small `_log_summary` emits it as `metal-summary: <section> <json>`
  — `params`, `stages_s`, `shapes`, `input_text`, one line per `layer M3`, `memory`, `inputs`,
  `blockage`, `filtered_layers`, `warnings` — so it is greppable by section and each payload is
  still valid JSON.

## Verification

1. `python -m pytest -q` — **589, green**, which is the readable log, the worker tag, the virtual
   connection and the inline rectangle. Still to come: the byte-range partition against the stride.
2. **Bit-identical invariance**: no committed DEF contains `VIRTUAL` or an inline `RECT`, and every
   via-carrying wire in the vendored gcd DEF is zero-length — so the geometry changes must leave the
   sample, the vendored DEF and every golden number exactly as it is.
3. The committed sample, pooled and sequential, must agree on every counter and the grid sums.
4. The real design, which is the user's: `--jobs 8` and `--jobs 16` on `lx956c_ioe`, expecting
   ~15 min from 30.8, the tagged log, the sectioned summary, per-worker RSS, the `virtual` count
   against 8,777,752, and the sample lines if that count comes back near zero.
