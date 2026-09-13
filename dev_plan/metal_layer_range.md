# Measuring part of the stack: `--min-layer` / `--max-layer`

The plan for restricting a metal-density build to a range of routing layers, from the real design
case recorded in [`real_design_case_record.md`](real_design_case_record.md). That design routes
from M2 to B2; its stack also holds M1 (the rail layer, which reads 0.027) and TM1/TM2/ALPA (thick
top metals, each 0.000), which are not routing layers and only add rows, grids and noise.

## 1. The numbering is the panel's row number

`--min-layer 2 --max-layer 12` names **1-based stack positions**. Two things pin that rather than
leaving it to guesswork:

- the example fits the design exactly: M1=1, M2–M8=2–8, FM1=9, FM2=10, B1=11, B2=12;
- `MetalPanel._layers_box` labels its rows `enumerate(self.data.layers, start=1)`
  (`ui_metal.py:164`), so the number in the flag is the row number the user is reading.

`TechRouting.layers` is in file order and is never sorted (`test_routing.py:280`), and a layer that
cannot be measured still occupies a position - the panel disables such a row rather than hiding it.
So a range can name a layer that measures nothing; that is allowed and reported.

The numbering is a property of *(the tech LEF, the filters, the code version)*, so the run logs the
resolved ends **by name** - `layers M2..B2 (11 of 15), ignoring M1, TM1, TM2, ALPA` - which is the
only thing that lets a user confirm their `12`. It has already moved once: dropping region layers
changed this design's stack from 18 rows to 15, and the log in the case record predates that.

## 2. The flag

```
--min-layer N   --max-layer N      integers, default None = the whole stack
```

Hyphens for the metal group (`--grid-size`, `--min-segment-length`) with `--min_layer`/`--max_layer`
accepted as aliases; dest `min_layer`/`max_layer`; both recorded in the summary's `params`.
`--min-layer` alone means "to the top", `--max-layer` alone "from the bottom". Layer *names* are not
accepted - the request was integers, and names would need a story for partial matches.

**Validation is mandatory, not defensive.** A range outside the stack must raise rather than clamp,
because an empty trimmed stack does not fail where you would expect it to: `MetalData.kinds()`
returns `[]`, then `ui_layout.py:50` reads `self._kinds[0][0]` inside `MainWindow.__init__` -
*outside* `_run_metal`'s `try` - so the user would get a traceback after a successful build and a
printed summary. The slice itself is the second trap: `--min-layer 0` as `layers[lo - 1:hi]` is
`layers[-1:12]`, which is empty on a 15-layer stack, silently.

`trimmed` therefore rejects `lo < 1`, `hi < lo` and `hi > len(stack)`, naming the range and the size.
`build_metal` raises before any grids are built, so the CLI's existing
`except Exception` → `error: ...` → exit 1 catches it with no traceback.

## 3. `TechRouting.trimmed(lo, hi)`

Returns a **new** `TechRouting`, so `__init__` rebuilds `_by_name`. The point is that
`ShapeStream._layer` resolves names through `tech.get`: mutating `tech.layers` in place would leave
out-of-range layers *still resolvable* while the panel and the blockage model showed the trimmed
stack. `read` keeps its one-argument signature, which four test files and three sample scripts rely
on, and the new object pickles to `parallel`'s workers like the old one.

**`trimmed` builds new `RouteLayer`s, re-indexed `0..n-1`.** `TechRouting.__init__` copies a list
(`routing.py:112-114`) and `RouteLayer.index` is set at construction, so a naive
`TechRouting(self.layers[lo:hi])` leaves indices `lo..hi-1`: self-consistent for the grids, and wrong
for every place that reads a layer back by index (`ui_metal.py`'s rows, `blocked_layers`,
`sample_data/metal/quickstart.py:61`, `generate_metal.py:512`).

Two things come out of `trimmed` and nowhere else, because a second place deciding either is how the
map and the log drift apart:

- **`filtered_layers`** - the names it dropped, so a filtered shape is not reported as a layer the
  LEF never defined;
- **`stack_offset`** - how many layers were dropped below the kept block, which is what keeps the
  macro-blockage fallback anchored to the *untrimmed* stack (§5).

## 4. Honest counters

The trimmed stack alone cannot tell "outside the range" from "this LEF never declared it": both are
absent from `_by_name`. So:

- `ShapeStream` derives `filtered_layers` from the tech (`getattr(tech, "filtered_layers", ())`)
  rather than taking it as a parameter. There are three stream-construction sites (the sequential
  path, `_worker`, and the parent's chunks) and deriving it removes an edit at each - and removes the
  failure mode where a worker and its parent disagree, which would be invisible, because both would
  still produce the right *map* and only the diagnostics would differ.
- `_layer` tests membership first and returns `None` as before, so the three call sites are
  unchanged; the shape is counted as **`filtered`**, not `unknown`.
- `filtered` joins `SHAPE_COUNTERS` and `PER_PLACEMENT_COUNTERS` (it describes the text, so a block
  placed K times carries K copies of it), and the hand-written `totals` literal in `build_metal`
  gains the key in the same commit - it duplicates `SHAPE_COUNTERS`, and `fold` raises `KeyError` on
  the first block without it.
- `_describe` reports it as **`logger.info`, not a warning**: `unknown` warns because the data
  surprised us, while a filtered layer is a choice the user made. A warning would also break
  `assert not data.warnings` on any trimmed build.
- The summary's `layers_not_in_tech` subtracts the filtered names, so a trimmed run stops claiming
  the LEF does not define layers it defines. `_macro_blockage` gets the same treatment so ignored
  `OBS` layers do not land in its `unknown` bucket. That function already has a bucket *called*
  `ignored`/`ignored_layers` (OBS below the 10 % footprint threshold), so this work spells its own
  concept **filtered** to keep the two apart.

## 5. The macro-blockage fallback stays anchored to the full stack

`--macro-block-layers N` means "a macro that declares no `OBS` is assumed to block the bottom N".
Anchored to the trimmed stack, `--min-layer 2 --macro-block-layers 4` would block M2–M5 instead of
M1–M4 - so M5, *a layer inside the requested range*, would lose capacity and its number would change
for a reason the user did not ask for.

Anchoring it to the **full** stack keeps the flag's promise literal: a trimmed run is exactly the
untrimmed run restricted to the kept layers, which is the contract a user will assume and which the
equivalence test in §7 therefore asserts. The fallback then affects the intersection of the full
stack's bottom N with the kept layers, and the log names the layers it actually affected rather than
only counting them. Two consequences, both reported rather than hidden: a depth larger than the kept
stack affects fewer layers than its count, and a macro whose `OBS` is entirely outside the range
blocks *nothing* - deliberately, because its own LEF says so - which the summary already reports
under `ignored_cells`.

Implemented as `TechRouting.fallback_layers(depth)`, beside the re-indexing that makes it necessary,
so the rule lives in one place: a kept layer is in the fallback when `index + stack_offset < depth`.

## 6. GUI

`MetalPanel` needs nothing: its rows come from `data.layers`, nothing shows an index, nothing assumes
a count, and the presets iterate the in-range layers. Two things change:

- the status bar reads `9 layers`, which looks like a short stack rather than a filtered one, so it
  names the range. `MetalData.stack_note` holds that rule (in one place, and testable without Qt);
- `CellDetailPanel._capacity_note`'s "block the bottom N layer(s)" has to mean the full stack, and
  has to say when the range leaves the fallback affecting nothing.

## 7. Tests

- **The trim**, beside the existing layer tests in `tests/test_routing.py`: order kept, indices
  re-based without gaps (so `layers[layer.index] is layer` still holds), `get`/`usable`/`horizontal`/
  `vertical` agreeing with the trimmed list, a trimmed-away name no longer resolvable, `min` alone,
  `max` alone, and `ValueError` for `0`, for `max` past the end, and for `min > max`.
- **The measurement for kept layers is unchanged**: build a fixture untrimmed and trimmed to its
  middle layers, asserting the kept layers' per-cell demand and utilisation match. This is the oracle
  for the whole change, and it is only true because of §5.
- **The counters and the log**: an in-stack, out-of-range name counts as `filtered` with `unknown ==
  0`, while a genuinely absent name still counts as `unknown`; `layers_not_in_tech` does not list
  filtered layers; a macro whose `OBS` names only filtered layers is not reported as "not in the tech
  LEF"; the new line is `info`, not a warning.
- **The parallel path with a trim**: `totals["filtered"] > 0` on *both* the pooled and the sequential
  build of the same trimmed input, and the two totals equal - the first half being what proves the
  tag reached the workers, since the existing comparison cannot see a missing tag (both paths would
  miss it).
- **The CLI**: defaults are `None`, both spellings parse and reach `build_metal`, an out-of-range
  range exits with a message and no traceback, and the help documents the fallback's anchor.
- **The GUI**: a trimmed panel lists only the range, the status bar names it, and the capacity note's
  depth refers to the full stack.
- **The sample**: `sample_data/metal/quickstart.py --check --min-layer 2` reaches `build_metal`
  (today its `parse_known_args` extra is discarded, so it would silently print full-stack numbers
  while GUI mode honoured the flag).
- Everything pinned today stays green: the untrimmed stack remains the default, so every existing
  layer assertion, golden and `verify()` is unaffected. `SAMPLE_SHAPES` gains `"filtered": 0` -
  `pytest.approx`'s mapping comparison fails on a key-set mismatch.

## 8. Stage 2, gated on the measurement

Filtering saves a layer's geometry work immediately (keep-out arithmetic, raster, grid) but not the
parse: the object is still built and the tail still tokenised - and it **must** still be tokenised,
because `*` coordinate reuse lives per *statement*, so skipping a tail mis-resolves a later form or
raises on a valid DEF (`tests/test_routing.py:430` pins exactly that). The next step would be
skipping the *object construction* for a filtered form while keeping `n_forms`, `n_points` and
`layers_used` exact. Whether that is worth touching the parser's hot path again depends on the
`filtered` count this stage reports, so it is decided on that number rather than guessed.

## 9. Verification

1. `python -m pytest -q` - the whole suite, none moved.
2. `main.py metal ... --min-layer 2 --max-layer 12` on the sample: the panel's rows, the status bar's
   range, the resolved names in the log line, the `filtered` count, and no filtered layer in the
   summary's `layers` or `layers_not_in_tech`.
3. The same build untrimmed, to show the kept layers' numbers are identical.
4. `sample_data/metal/quickstart.py --check --min-layer 2 --max-layer 11` to prove the flag reaches
   `build_metal` through the wrapper.
5. `--min-layer 0`, `--min-layer 5 --max-layer 3`, `--max-layer 99` each fail with a clear message
   and no traceback.
