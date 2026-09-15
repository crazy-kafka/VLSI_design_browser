# Per-layer shape statistics at the end of the routing stage

The routing stage reports its shape classes globally, so a log can say that 108 M vias were omitted
but not which layer they were on, and a layer's utilisation is only readable off the map. This adds
a per-layer table at the end of the shape reading, and the same numbers to the machine-readable
summary.

## Cost, measured before the decision

The increments are on the per-shape path and the real run has 249 M shapes. Unit costs measured in
this checkout: a list-index in-place add is **0.0316 µs**, a name-keyed dict bump **0.0387 µs**.
Against the counts in `dev_plan/issue/real_design_log_0915.md`:

| new increment | count | CPU |
|---|---|---|
| emitted, per layer | 56,375,666 | 1.78 s |
| filtered, per layer name | 72,051,441 | 2.79 s |
| jogs, per layer | 11,796,228 | 0.37 s |
| diagonals, per layer | 8,777,752 | 0.28 s |
| vias, per layer | per net, not per point | ~0 |
| | | **5.22 s** |

CPU seconds, not turnaround: the increments run in the workers on their share of the shapes, so at
`--jobs 8` the wall grows by what lands on the critical worker - the one holding the giant power net -
which is **~0.5-1.0 s of 1,780.64 s (0.03-0.06 %)**. Only `--jobs 1` pays the full 5.22 s. The
benchmark's own repeat runs of one configuration varied 5-6 %, so at 8 workers this is below the
noise floor, and it was accepted on that basis rather than assumed.

## Where the counting goes

In `vlsi_viewer/parsers/routing.py`, at the sites that have the layer in scope:

| counter | site | layer |
|---|---|---|
| `n_emitted` | `_emit` — the single funnel for axis-aligned shapes | index |
| `n_emitted` (diagonals) | the tuple built in `_add_wire` | index |
| `n_emitted` (polygons) | `_add_polygon` | index |
| `n_via` | `_add_regular`, `_add_special` | index |
| `n_jog`, `n_diagonal` | `_add_wire` | index |
| `n_degenerate` | `_add_box` | index |
| `n_via` (the bulk) | `add_net` — `net.via_points` | **name**, via the parser |
| `n_filtered` | `_layer` | **name** — an excluded layer has no index in the trimmed stack |

Two structures, then: `ShapeStream.by_layer` — a list indexed by `layer.index`, one row per layer,
because an index bump is 0.0316 µs and this is the per-shape path — and two name-keyed dicts, for
the shapes that have no index to be keyed by. The name-keyed side is not a workaround but the
interesting half: the 72 M filtered shapes are on the layers the caller excluded, and the table says
which.

## The table

```
metal: shapes per layer
  layer  dir         usable     shapes        area um2    util
  M2     VERTICAL    yes      21,884,301    41,203.44   38.1 %
  M3     HORIZONTAL  yes      14,220,988    26,881.10   44.9 %
  layer  vias         jogs      diagonals   signal       power
  M2     1,204,551    884,201           0  17,003,441   4,880,860
metal: skipped before the layer range: ALPA 3.4 M, M1 9.2 M, TM1 1.1 M, TM2 0.2 M
```

Area and utilisation are **read, not recomputed**: `MetalData._consumed`, `.capacity`, `.layer_util`
and `.pitch_factor` already produce exactly the numbers the map shows, and the table is another
reader of them.

## Two things deliberately not done

- **No new entry in `SHAPE_COUNTERS`.** `tests/test_metal_sample.py` builds its golden comparison
  from that tuple and pins the exact key set, so a new entry there is a test break for no benefit.
- **No new summary section.** The per-layer fields ride on the `layer <name>` lines that already
  exist, so the pinned label list in `tests/test_metal_diagnostics.py` is untouched.

## Verification

`python -m pytest -q` — **599 green** (596 before, 3 new). The invariant holds on the committed
sample, checked by test and by hand: per-layer shapes 19,793 = `totals["emitted"]`, jogs 135 =
`totals["jogs"]`, and signal + power = shapes for every layer. `SAMPLE_SHAPES` did not move, which
is the check that `SHAPE_COUNTERS` was left alone; the summary's label list did not move, which is
the check that no new section appeared.

The cost is the plan's, because the bumps turned out to be exactly the counters: the invariant test
proves the per-layer numbers account for every shape the global counters counted, so the increments
are 5.22 s of CPU at the real design's counts and nothing else was added. At `--jobs 8` that is the
~0.5-1.0 s of wall in the plan, spread over the workers.

## What building it turned up

- **The table's own test found the one class that cannot always be placed.** A `+ VIA` form states
  no layer of its own, so its points arrive with a name to be counted under or nothing - and the
  first version of the stream dropped them silently: per-layer vias 1 against a global 3. They are
  now counted in `via_unattributed` and the table prints the number, so the two together are every
  via the run counted and a reader sees the difference instead of having to trust it.
- **A layer with no shapes has no grid at all**, and `MetalData._consumed` answers `None` for it
  rather than an empty array. That is the row the table exists to show - a measured layer that
  carried nothing - so both the table and the summary treat it as zero area rather than crashing.
- **The unit's own docstring was the constraint.** `PER_PLACEMENT_COUNTERS` and `SHAPE_COUNTERS`
  are what the tests' goldens compare against; keeping the per-layer numbers in a structure beside
  them, rather than inside them, is why this change adds no test breakage.
