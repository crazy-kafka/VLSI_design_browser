# `--json` for `def` and `verilog`: filling in what the inputs cannot say

DEF and a gate-level netlist describe structure and placement. Neither carries activity, so
`dynamic_power` and `leakage_power` sat at their schema defaults and the leakage and dynamic heat
maps came out flat for both flows — with a CLI warning to say so (`cli.py:284-285` before this).
The only way in was to pre-merge the JSON by hand.

`dev_plan/EDA_file_support.md:16-18` had already promised the fix ("Incremental json file reading
is supported", twice), and README's "incremental JSON" paragraph described the multi-block half of
it. This is the other half: **`--json FILE...` on the `def` and `verilog` subcommands**, whose
instance data is filled into the converted design before anything loads it.

## The decisions, and why

**The fill happens on the converted block dicts, in `resolve_inputs`, before the `--out` dump.**
Three things fall out of that one placement, which is why it is where it is:

- **Absence is only expressible there.** `loader._block_from_data` walks `schema.INSTANCE_ATTRS`
  and substitutes each spec's default for a missing key, so after loading, "no power was supplied"
  and "the power is 0.0" are the same value. A merge at the DataFrame level could not tell them
  apart; the dict can.
- **One record fills every placement.** Both `metrics.load_blocks` and `physical.walk` expand the
  hierarchy from these same dicts and read power off the same entry, so a record for a sub-block's
  leaf placed four times lights four boxes on the map (measured: one `SUB` record → 4 design
  instances on `sample_data/metal`).
- **`--out` writes the filled data**, so the dump is an ordinary input to the `json` subcommand and
  the conversion only has to be done once.

**A file's `top_name` names the block its keys are relative to** — that single rule covers both
forms the user asked for, with no mode switch:

| file | keys | resolved by |
|---|---|---|
| `TOP.json` (flattened) | `u_core/u1` | descending the container chain (`cell_name` names another block) |
| `sub_A.json` (per-block) | `u1` | the block its `top_name` names |
| either, path copied out of the tree | `TOP/u_core/u1` | the leading `<top>/` is stripped and retried |

Descending uses the same `cell_name in blocks` test `metrics.load_blocks` (`metrics.py:96`) and
`physical.walk` (`physical.py:391`) use, so an entry the resolver accepts is one both of them will
place — the resolver cannot accept an instance the hierarchy does not have.

**The rule per attribute, as the user set it:** fill any `schema.INSTANCE_ATTRS` key the input does
not already provide; on a conflict the input's value stands and the file's is counted as ignored; a
record naming an instance the design does not have is ignored. Nothing is fatal — a partial fill is
the normal case (one file per sub-block). A `cell_name` that *disagrees* is the one conflict said
out loud, because it is the strongest sign the file belongs to another version of the design.
Values go through `loader._coerce`, so a value the fill accepts is a value the loader accepts.

## What a run prints

```
power: reading core.power.json
power: core.power.json -> 3994 of 3994 record(s) filled (0.0s)
power: 3994 of 3994 design instance(s) filled from 1 file(s)
```

The aggregate line carries `; N value(s) ignored, the input had them` when there were conflicts.
Warnings (one line each, ≤3 example paths): a file naming a block this design does not have; records
that filled no instance (with a count of those naming a sub-block rather than a leaf — the case a
user hits by pointing the wrong file at a block); disagreeing cell names; unusable values.

The old "carries no power data" warning still fires verbatim when `--json` was not given, and says
"still carries no power data: no --json record matched an instance" when it was given and nothing
matched — the case that must not read like the case where nothing was passed. For `verilog` the run
adds that a netlist has no physical mode, so `--out` is how to keep the filled data; the
`--compare_*` design is never filled (power is not rendered in the compare view), and an INFO line
says so when both are given.

## A bug this work found and fixed: macros apportioned their power by the grid area

`physical.py`'s macro path rasterises a box as an outer product and took its power weight as
`patch / box_area` — but `patch` is *area / gs²*, the per-bin density fraction, which sums to
`1/gs²` over the box rather than to 1. A macro's leakage and dynamic therefore came out divided by
the grid area: **4× low at the default 2 µm grid**. Measured on the EDA sample, the leakage grid
summed to 52.17 against the 53.43 its instances carry; after the fix it sums to 53.432160 (a 2e-8
rounding residual) at every grid size.

The fix splits the two weights — `area = outer(oy, ox)`, `patch = area / gs2` for density and ULVT,
`frac = area / box_area[i]` for the power grids — and
`tests/test_physical.py::test_a_macro_apportions_its_power_like_a_std_cell` is the regression test.
The `json` samples hid this because their macro cells sit at the die's edge in one row: no existing
test asserted a macro's power at all.

## Sample and quickstart

`sample_data/eda/generate_eda_sample.py` now writes `core.power.json` (3994 records, 427 KB, values
following the same activity field the floorplan uses so the maps have structure), and its `verify()`
fills `core.def`'s block, checks the leakage grid sums to the power of the cells that count
(physical-only cells are masked out of that map by design), and fills the netlist with the same file
to show the partial case (270 records name tap/decap cells the netlist does not have).
`quickstart.py def` passes the file, so the demo's leakage and dynamic maps are no longer flat.

## Verification

```
python -m pytest -q                                     # 650 passed (was 634)
python sample_data/eda/generate_eda_sample.py           # verify: OK
python quickstart.py def                                 # leakage/dynamic maps not flat
python main.py def --def sample_data/metal/top.def sample_data/metal/sub.def \
    --lef sample_data/metal/cells.lef --json SUB.json --out /tmp/out   # 1 record -> 4 instances
```

New tests: `tests/test_parsers_eda.py` (9 — the three key forms resolving to one instance, four
placements from one record, the conflict rules, the diagnostics, the loader round trip, the
committed sample's freshness), `tests/test_cli.py` (5 — the flag's presence and absence, the warning
arms, the `--out` round trip, exit 1 on a missing file), `tests/test_physical.py` (2 — the macro
regression and one record → 4× power on the grid).

**One thing the suite found about itself, not about the feature.** With these tests added, the
default `pytest -n 8` (per-test distribution) started losing a worker silently — no traceback, on
`test_metal_gui.py`'s first test, and only when the run was at 8 workers *and* the new modules were
included. It reproduces in neither subset (GUI alone: 83 passed; everything but the GUI modules:
567 passed) and not at `-n 4` or `--dist loadfile -n 8`, which points at a worker that has already
built the heavy metal fixtures aborting when it later creates offscreen Qt windows. The metal GUI
test that "crashes" passes on its own, in its module, and serially, and nothing in this feature
touches Qt. So the README now recommends `-n 4` or `-n 8 --dist loadfile`, both of which are 27 s —
the per-test mode was never faster, it was only luckier with the scheduling.

## Later: the fill was O(N²), and one run hung for days (2026-09-22)

Reported in `dev_plan/issue/real_design_log_0921.md`: a `def` run with `--json` on a 3,347,979
instance design (`job 1657044030`) printed the DEF summary and then nothing for hours. The fill was
quadratic.

`_resolve` called `_instances`, which **rebuilt the block's whole instance dict** on every call, and
`_resolve` is reached once per JSON record. For a flat design - one block holding all 3.35M
instances, which is what that DEF is (`dropped 0 filler`) - every record copied 3.35M entries.
Measured through the real `_resolve` on synthetic flat blocks: 74.8 us per call at 1k entries, 315 us
at 4k, 1,395 us at 16k, 5,579 us at 64k - exactly linear in N, so quadratic in total. Fitted at
3,347,979 records that is ~10 days of CPU; the run was inside this loop, not dead. The new inner
loop measures **0.045 us per record**, i.e. **0.15 s** for the same 3.35M records.

Measured after the fix, end to end through `fill_instances` on a synthetic flat design with a
matching record per instance:

| records | now | the old per-record rebuild |
|---|---|---|
| 50,000 | 0.25 s | ~5 min |
| 200,000 | 1.11 s | ~0.8 h |
| 3,347,979 | ~20 s, dominated by the JSON load | ~10 days |

What changed, all in `parsers/convert.py`:

- `_index_blocks` + `_instances` became **`_block_instances`**, which builds one table per block name
  - once, before the record loop. A single-block group keeps *the block's own dict* (no copy: the
  entries are the objects the fill writes into, so the in-place semantics are unchanged), and only a
  duplicate `top_name` builds a merged dict, earlier file winning, as `metrics._merge_blocks` does.
- `_resolve`, `_target`, `_shape` and the "names no block" warning take that table instead of
  re-deriving it. The container test (`child in index`) reads `child in tables`: same keys, one
  structure. This also removes the same pattern from `_shape`'s walk, which called `_instances` per
  visited block.
- The loop now says what it is doing: `power: reading <file>` before the load (the load alone is
  ~15 s and ~1.7 GB at 3.35M records, measured 4.47 us and 505 B per record), a
  `power: <file>: N of M record(s) read (Xs)` line every `FILL_PROGRESS_RECORDS` (1M) records, and
  the per-file summary now carries its elapsed time. The silence is half of why the run above was
  reported as a hang rather than as slow.

Tests added: the table is built once and is the block's own dict (plus the duplicate-name merge),
a flat fill of 8k records must finish inside a second (it took ~5 s before, ~40 ms now), and the
progress lines appear with the summary's timing. **655 tests pass.**
