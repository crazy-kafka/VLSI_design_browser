# What the 09-16 run verified, and the three things it left to fix

The first run on `e34c6dd` (`dev_plan/issue/real_design_log_0916.md`). Everything the build claimed
is confirmed by it: worker tags on every line; the summary in twelve short sections; `VIRTUAL` kept
as connections (21,175,654) with `diagonals` 0 and jogs 11,796,228 → 565,424; the inline `RECT`
measured, the total up by **exactly** its count (81,172,072); the per-layer vias column summing to
**exactly** the global 108,844,474 with no point left unplaced; and routing 1,780.64 → 1,696.70 s.

## The one that needed finding: a shared column counted two ways

The per-layer rows and the scalar counters do not share a rule for the placement count. `_emit`
counts a shape per placement itself (`placed = len(self.frames) or 1`), and `emitted` is therefore
*not* in `PER_PLACEMENT_COUNTERS`; vias, jogs, diagonals, degenerate and unusable are counted once
per parse and scaled by the parent. The rows had no such split: the diagonal's `L_DIAGONALS` and
`L_SIGNAL`/`L_POWER` bumps were both one-per-diagonal, so a block placed more than once moved the
summary and not the table. The sample's flat fixtures could not see it.

The fix keeps the stream's convention and gives the fold the same rule: `PER_PLACEMENT_COLUMNS`
names the columns the parent scales by `len(frames)`, and `merge_layer_stats` takes the placement
count from the one caller that knows it — the per-block merge in `build_metal`, never the worker
folding its own chunks. The diagonal's scope column, which belongs with `shapes`, is counted per
placement where it is bumped.

## The one that cannot be settled from a screenshot: 2,730

The run's per-layer `shapes` sum to 112,881,417 against a global `emitted` of 112,884,147. In this
checkout every increment pairs with its row, so at one placement they must agree, and the sample
test asserts it; the same summary line also reads `usable` where the repo has `unusable`, which
proves the transcription slips. So it is either a slip or a deployed copy that is not this commit —
and neither can be told from a screenshot.

What can be told is whether it happens again: `_check_layer_totals` compares each column against
the counter it splits and logs one warning naming any difference, in the same spirit as the
byte-range scan's guard. Eleven rows, once per run.

## Two smaller corrections

- The table's second block formatted five fields, so the scope split printed `signal` and dropped
  `power`, which the plan showed and the summary already carried.
- The byte-range projection used the 09-15 run's 830 s chunk. On this run the largest single read is
  **909.78 s of a 1,696.70 s stage (54 %)**: the fix adds 81 M inline RECTs to measure and they land
  on the worker holding the giant statement, which is why that chunk is ~80 s slower while the stage
  is 84 s faster. The post-change wall is therefore ~993 s, which is **1.71×**, not the 1.90× on
  record in `metal_work_units_eval.md`.
