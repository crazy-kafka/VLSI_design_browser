# Real design case — power JSON misses both `gpu_sp_top` placements: flattened block component names

**Target:** `def --physical_mode` with a power `--json` file; the leakage/dynamic heat maps
and the hierarchy power columns
**Design:** same hierarchy as the previous record — top `gpu_gpc_top_if`; blocks
`gpu_ff_top_if` (one placement) and `gpu_sp_top` (two placements); 220 LEF files /
17,385 macros
**Evidence:** the new leakage-map/Gvim snapshot (2026-11-20), the `gpu_ff_top_if` grep,
the bundled six-core physical-sample snapshot, and the reproduction in
[`issue_reproduce/`](../../issue_reproduce/)
**Related:** the orientation/location case in
[real_design_case_fn_block_placement.md](real_design_case_fn_block_placement.md)

Legend:

- **Observed** — visible in a supplied snapshot.
- **Code** — read from this checkout, with the file and line linked.
- **Reproduced** — produced by
  [`reproduce_power_fill.py`](../../issue_reproduce/reproduce_power_fill.py), whose complete
  run is [`output.txt`](../../issue_reproduce/output.txt). Every check in it passed.

---

## 1. Conclusion

Current code **can** produce this symptom; under the stated assumption that every leaf
record for both `gpu_sp_top` placements is present, the JSON content is not the blocker.

The fill resolves a key to a **block table**, not to a placement. The two `gpu_sp_top`
components are named with a flattened, multi-segment DEF name
(`U_GPU_SHADER_TOP/u_gpu_shc_top/gen_sp_1_u_sp` and `…gen_sp_0_u_sp`), while
[`_resolve`](../../vlsi_viewer/parsers/convert.py#L368) only ever descends through the **first**
`/` segment ([convert.py:383](../../vlsi_viewer/parsers/convert.py#L383)). It looks for an
instance named `U_GPU_SHADER_TOP` in the top table; that name is the first segment of the
block component, not an instance. Every leaf record under either sp placement is therefore
unmatched before its leaf is read, the shared `gpu_sp_top` table keeps the default power of
0, and both placements render 0.

The single-instance `gpu_ff_top_if` is the real control: its component is
`U_GPU_FF_TOP_IF`, one segment, so the same code descends into its table and its power map
is populated. The bundled six-core sample is the multi-instance control: six `CORE`
placements, one-segment names, all six populated. Neither instantiation count nor
orientation is the cause; the flat, multi-segment block name is.

---

## 2. Symptom

**Observed.** With the power JSON supplied, the **density** map is correct (the previous
orientation/location fix is in the current code), but the **leakage** map is populated
across the die except the two top `gpu_sp_top` footprints. The lower-left
`gpu_ff_top_if` footprint is populated and is annotated “this subblock instantiated once,
power map is okay”. The Count, Area, ULVT%, MB% and D1D2% columns for the `gen_sp_*` rows
are normal; the power columns are built from the same leaf entries as the map, so they
necessarily read zero as well — the map is the direct evidence, the columns are the
consequence.

Both sp placements are zero — the `N` sibling (`gen_sp_0_u_sp`) as well as the `FN` sibling
(`gen_sp_1_u_sp`). That is the first clue that this is not the old geometry/orientation
problem: that one was FN-specific. A per-placement geometry issue would leave the N
placement populated; a shared block-table/fill issue leaves both empty.

**Observed (power file).** The Gvim snapshot of `power.json` shows records for leaves under
**both** sp placements:

```
U_GPU_SHADER_TOP/u_gpu_shc_top/gen_sp_0_u_sp/U_RS_EXT_RSM_SP_TOP/MBTIT_reg_sig_buf_d1_reg_19_… :
    dynamic_power: 0.002
    leakage_power: 4.7488e-05
U_GPU_SHADER_TOP/u_gpu_shc_top/gen_sp_1_u_sp/U_RS_EXT_RSM_SP_TOP/MBTIT_reg_sig_buf_d1_reg_19_… :
    dynamic_power: 0.002
    leakage_power: 4.7488e-05
```

The file also contains records for other subtrees (`u_gpu_sq_top`, etc.), so it is a
top-level power file, not a per-block one. The `top_name` line is above the visible part of
the snapshot; it must be the top (`gpu_gpc_top_if`) for those other records to fill, and the
map is populated elsewhere, so it is. §7 states the check to make this explicit.

**Observed (single-instance control).** The grep over the parent DEF returns exactly one
component for the ff block:

```
- U_GPU_FF_TOP_IF gpu_ff_top_if + FIXED ( 0 0 ) N + WEIGHT 1
```

One placement, one path segment, power map okay. The difference from the sp block is not
“one vs two placements”; it is the name shape. §5 and §6 break that correlation with
synthetic and bundled controls.

**Observed (previous record).** The two sp placements are the flattened components already
recorded in the orientation case:

```
- U_GPU_SHADER_TOP/u_gpu_shc_top/gen_sp_1_u_sp gpu_sp_top + FIXED ( 0 2029200 ) FN + WEIGHT 1
- U_GPU_SHADER_TOP/u_gpu_shc_top/gen_sp_0_u_sp gpu_sp_top + FIXED ( 1577760 2029200 ) N + WEIGHT 1
```

So the power keys are exactly those component names plus the block’s own leaf path.

---

## 3. How the fill is supposed to work

**Code.** [`fill_instances`](../../vlsi_viewer/parsers/convert.py#L442) runs on the converted
block dicts **before** the hierarchy is expanded. It builds one instance table per block
([`_block_instances`](../../vlsi_viewer/parsers/convert.py#L339)); a record for a sub-block leaf
is written into that block’s table, and **every** placement of the block later reads the same
entry. That is why one record can light six placements in the test, and why both sp
placements fail together here: neither record ever reaches the table.

**The three documented key forms** ([README.md:410](../../README.md#L410),
[power_json_fill.md:34](../eda/power_json_fill.md#L34)):

| file | key | resolved by |
|---|---|---|
| top file, flattened | `u_core/u1` | descending the container chain (`cell_name` names another block) |
| per-block file | `u1` | the block named by `top_name` |
| either, path copied from the tree | `TOP/u_core/u1` | leading `<top>/` stripped ([`_target`](../../vlsi_viewer/parsers/convert.py#L393)) and retried |

**The resolver.** `_resolve` tries the whole key; if that misses, it splits at the **first**
`/` and descends only when that head’s `cell_name` is another block. Everything after the
head is the remainder. The tests cover a single-segment block (`u0/r0_0`,
[test_parsers_eda.py:524](../../tests/test_parsers_eda.py#L524)); they do not cover a block
instance name that itself contains `/`.

**The diagnostics.** An unmatched record is counted and the file warns
([convert.py:536](../../vlsi_viewer/parsers/convert.py#L536)); the CLI reports the aggregate
([cli.py:315](../../vlsi_viewer/cli.py#L315)). The real run should show a line like:

```
power: <file>: N of M record(s) filled no instance of 'gpu_gpc_top_if' (e.g. …gen_sp_0…, …gen_sp_1…)
power: <filled> of <design> design instance(s) filled from 1 file(s)
```

N is the number of records under the two sp components; the design count is short by the sp
leaves × 2. This is the first thing to check in the real run log.

**The read side.** The physical walk reads `leakage_power`/`dynamic_power` from each leaf row
([physical.py:554](../../vlsi_viewer/physical.py#L554)); the tree power columns are built from
the same leaf entries ([metrics.py:201](../../vlsi_viewer/metrics.py#L201)). If the block table
is at its default 0, both the map and the columns are zero; there is no separate power path
that could fill them.

---

## 4. Root cause

For the sp key

```
U_GPU_SHADER_TOP/u_gpu_shc_top/gen_sp_1_u_sp/U_RS_EXT_RSM_SP_TOP/sp_leaf_1
```

the top table has the entry

```
U_GPU_SHADER_TOP/u_gpu_shc_top/gen_sp_1_u_sp   -> cell_name gpu_sp_top
```

but `_resolve` does not try that entry. It tries the whole key (not an instance), then
`head = U_GPU_SHADER_TOP`; `instances.get("U_GPU_SHADER_TOP")` returns nothing, so it returns
`None`. The record is counted as unmatched (`convert.py:491-497`) and the leaf keeps no
power. The same happens for `gen_sp_0_u_sp` and for every other leaf under either component.
The `gpu_sp_top` table is shared by both placements, so both are zero.

The flat top-level leaf in the same design works because its whole key is an entry in the top
table: `U_GPU_SHADER_TOP/u_gpu_shc_top/u_gpu_sq_top/flat_leaf`. The ff block works because
its component name is one segment: `U_GPU_FF_TOP_IF` is an entry in the top table whose
`cell_name` is `gpu_ff_top_if`, so the resolver descends and the remainder `ff_leaf` is found.
The only difference between the working and failing blocks is whether the block component is
a single path segment.

The original design notes describe the container chain as one segment per block (`u_core/u1`,
[power_json_fill.md:34](../eda/power_json_fill.md#L34)); the real DEF writes the block component as
a flattened name. The resolver inherited the one-segment assumption.

---

## 5. Single instantiation vs multi-instantiation

**The fill is per block table; the count is not the variable.** The same code fills one
record for a six-placement block in the existing test (`summary.instances == 6`) and in the
bundled sample-shaped reproduction. The real `gpu_ff` is one placement and works; the real
sp is two placements and fails, but the two synthetic rows below break the correlation:

| case | placements | block component name | fill result |
|---|---|---|---|
| `gpu_ff_top_if` (real) | 1 | `U_GPU_FF_TOP_IF` — single segment | filled; map okay |
| `gpu_sp_top` (real) | 2 | `U_GPU_SHADER_TOP/…/gen_sp_*_u_sp` — flattened | unmatched; both zero |
| `CORE` (bundled sample) | 6 | `core_0`…`core_5` — single segment | all six populated |
| synthetic | 1 | single segment | matched 1, design 1/1, leaf powered |
| synthetic | 1 | flattened multi-segment | matched 0, design 0/1, not powered |
| synthetic | 2 | single segment | matched 1, design 2/2, leaf powered |
| synthetic | 2 | flattened multi-segment | matched 0, design 0/2, not powered |
| synthetic, one slashed + one single-segment, record via the single | 2 | mixed | matched 1, design 2/2, **both** placements powered |
| synthetic, sample-shaped six `CORE` | 6 | single segment | matched 1, design 6/6, leaf powered |

The mixed row is the decisive one: a record that reaches the shared table through the
single-segment component powers the sibling placement whose own component is slashed as
well. The slashed component is not poisoning the table or the placement machinery; it is
only an unreachable entry point. Conversely, the single-placement multi-segment row fails,
so two placements are not required for the failure.

**Why both sp placements are zero.** Both components are slashed; neither record resolves;
the shared `gpu_sp_top` table stays at 0; the physical walk expands that table for the N and
FN placements alike. The orientation is irrelevant to the fill. The bundled sample’s FN and
FS cores carry power, which is the orientation control.

---

## 6. The bundled `sample_data/physical` sample

The current sample is a six-core control for exactly the multi-placement/multi-orientation
side:

- [`generate_physical.py:94`](../../sample_data/physical/generate_physical.py#L94):
  `CORES_X, CORES_Y = 3, 2`; six `CORE` placements `core_0`…`core_5`
  ([generate_physical.py:292](../../sample_data/physical/generate_physical.py#L292)) at
  **N / W / S / E / FN / FS**; every core is placed at the lower-left of its slot, the
  fixed DEF rule from the previous case.
- Each `CORE` is one block table with `ifu`/`iex`/`lsu`; all six placements share its leaves.
  The top’s `core_i` container entries also carry random `leakage_power`/`dynamic_power`
  from `_attrs` (0.0428, 0.0104, …), but those are **container** rows: `physical.walk` and
  the metrics expand them and read the leaves, so the container values do not appear in the
  map or the tree.
- The computed hierarchy values (via `metrics.build_design`, and matching the supplied
  snapshot):

  | path | count | leakage | dynamic |
  |---|---|---|---|
  | `CPU_CLUSTER` | 153,600 | 5,360.71 | 13,415.88 |
  | `CPU_CLUSTER/core_0` … `core_5` | 22,600 each | **788.17 each** | **1,972.99 each** |
  | `core_0/ifu` | 8,000 | 280.73 | 694.83 |
  | `core_0/iex` | 7,400 | 256.31 | 648.83 |
  | `core_0/lsu` | 7,200 | 251.13 | 629.33 |
  | `uncore` | 18,000 | 631.34 | 1,577.05 |

  The six identical core rows are the shared-leaf sum (`ifu + iex + lsu`), not the six
  different container attrs. That is expected and is the same “one table, many placements”
  behavior the fill relies on.
- The sample is a **JSON-path** input; its power is already in `CPU_CLUSTER`/`CORE`/`IFU`/
  `IEX`/`LSU` files, so it never calls `_resolve`. It cannot reproduce the slashed-name
  failure because its component names are one segment. It is a working control for six
  placements, six orientations and shared power, not a counterexample.
- A synthetic sample-shaped fill (six `core_i` → `CORE` → `ifu` → leaf, all one segment) with
  one record `core_0/ifu/std_leaf` fills **six** design instances. So the sample’s naming is
  exactly the form the resolver supports; the real sp naming is not.
- The sample’s `verify()` checks density, not power. The six-core power behavior is currently
  demonstrated by the GUI snapshot and this reproduction; a future regression could assert
  the six rows’ power explicitly.

The sample screenshot also answers the orientation question: its `FN`/`FS` cores show power,
so a mirrored placement is not a power blocker when the block table is reachable. The real
sp `N` and `FN` are both zero, which points at the shared table, not orientation.

---

## 7. Reproduction

The reproduction is a self-contained script in
[`issue_reproduce/`](../../issue_reproduce/) with its own README; it runs the real converter,
the real `fill_instances` and the real `metrics.build_design`, and returns `RESULT: PASS`
(exit 0). Run from the repository root:

```bash
python issue_reproduce/reproduce_power_fill.py 2>&1 | tee issue_reproduce/output.txt
```

The decisive lines (the full run is in [`output.txt`](../../issue_reproduce/output.txt)):

```
DEF tops: ['GPU_TOP', 'gpu_ff_top_if', 'gpu_sp_top']
fill summary: matched=2 records=2 design=2/6
fill warning: … 2 of 4 record(s) filled no instance of 'GPU_TOP'
  (e.g. U_GPU_SHADER_TOP/u_gpu_shc_top/gen_sp_0_u_sp/…/sp_leaf_1,
        U_GPU_SHADER_TOP/u_gpu_shc_top/gen_sp_1_u_sp/…/sp_leaf_1)
  GPU_TOP                                                leak=6.000e-05 dyn=8.000e-03
  GPU_TOP/U_GPU_FF_TOP_IF                                leak=1.000e-05 dyn=2.000e-03
  GPU_TOP/U_GPU_SHADER_TOP/u_gpu_shc_top/gen_sp_1_u_sp   leak=0.000e+00 dyn=0.000e+00
  GPU_TOP/U_GPU_SHADER_TOP/u_gpu_shc_top/gen_sp_0_u_sp   leak=0.000e+00 dyn=0.000e+00
  GPU_TOP/U_GPU_SHADER_TOP/u_gpu_shc_top/u_gpu_sq_top    leak=5.000e-05 dyn=6.000e-03
  six-core: matched=1 design=6/6 leaf_powered=True
  workaround: matched=1 design=2/6 leaf_powered=True
  RESULT: PASS
```

The script’s seven checks:

1. The real-shaped DEF hierarchy: the ff leaf and the flattened top leaf fill; both sp
   leaves stay without power; the warning names the sp records.
2. The hierarchy power columns: ff 1.000e-05, both sp 0, top total 6.000e-05
   (= ff + flattened top leaf).
3. The single-vs-multi matrix above.
4. The sample-shaped six-core fill: one record → six design instances.
5. The per-block workaround: `top_name: gpu_sp_top`, a block-relative key; one record fills
   both sp placements (`design=2/6` here because the synthetic design has six leaves total:
   ff 1 + flat 1 + two sp leaves × two placements = 6; the one filled sp leaf counts twice).
6. The bundled sample’s six cores, with the values in §6.
7. An optional `build_physical` grid check. On the Windows copy used to prepare this record,
   `shapely` is not installed, so check 7 prints `skipped: No module named 'shapely'`; checks
   1–6 are the decisive ones and do not need shapely. On a host with shapely the grid check
   runs and expects the leakage grid to be ff + flattened-top-leaf, with the sp leaves
   contributing nothing.

The record was written only because the run ended `RESULT: PASS`; the script exits non-zero
on any mismatch, and the plan was to cancel this file if that happened.

---

## 8. Is the power JSON legal?

Under the stated assumption (every leaf of both sp blocks is present with the values shown),
yes for the documented flattened-top form:

- The keys are the top-relative paths under the top: the block component path plus the
  block’s leaf path. The viewer’s tree shows the same paths with the leading top name, and
  `_target` accepts both (it strips a leading `<top>/` and retries); the fill contract says a
  flattened top file and “the path a user copies out of the tree” are accepted
  ([README.md:410](../../README.md#L410),
  [`_target`](../../vlsi_viewer/parsers/convert.py#L393)).
- The values use the schema names `leakage_power`/`dynamic_power`
  ([schema.py:26](../../vlsi_viewer/schema.py#L26)) and are non-zero in the snapshot.
- The only mismatch is the resolver’s one-segment assumption. A JSON change alone cannot
  make the slashed entry point reachable: the resolver has no way to match
  `U_GPU_SHADER_TOP/u_gpu_shc_top/gen_sp_1_u_sp` as a prefix of the key.

**Check the run before editing the JSON.** In the run log, look for:

1. `power: <file>: N of M record(s) filled no instance of 'gpu_gpc_top_if' (e.g. …gen_sp…)`
   — this is the confirmation of the resolver failure; N is the number of sp leaf records.
2. `power: <filled> of <design> design instance(s) filled from 1 file(s)` — the design count
   is short by the sp leaves × 2.
3. The hierarchy `Leakage P`/`Dynamic P` columns for both `gen_sp_*` rows are 0 while their
   count/area are normal.
4. `head -1 power.json` (or the JSON’s first key) names the top
   (`gpu_gpc_top_if`/`GPU_TOP`). If it instead names `gpu_sp_top`, the parent-prefixed keys
   are wrong for that file; that is a JSON correction, not this code issue, and the other
   subtrees’ records would not fill either.

**Workaround (works today).** Split the sp records into a per-block file:

```json
{
  "top_name": "gpu_sp_top",
  "instances": {
    "U_RS_EXT_RSM_SP_TOP/MBTIT_reg_sig_buf_d1_reg_19_…": {
      "leakage_power": 4.7488e-05,
      "dynamic_power": 0.002
    }
  }
}
```

The keys are the block’s own instance names (strip the
`U_GPU_SHADER_TOP/u_gpu_shc_top/gen_sp_*_u_sp/` prefix). One record fills **both** sp
placements because the block table is shared; the reproduction’s workaround check confirms
`matched=1`, both placements powered. If the two placements’ values differ, the shared table
can carry only one value: the first resolved record wins (the fill treats the second as a
conflict and keeps the first). That is a second, separate limitation; the real snapshot’s two
records have the same values.

---

## 9. Recommended fix (not applied)

This record is analysis only; the viewer source is unchanged.

**Make `_resolve` try every instance-name prefix at a `/` boundary, longest first**, not just
the first segment. Keep the whole-key match first, descend only when the prefix’s `cell_name`
is another block, and keep the `seen` cycle guard. Sketch:

```python
def _resolve(tables, name, key, seen=frozenset()):
    if name not in tables or name in seen:
        return None
    instances = tables[name]
    if key in instances:
        return instances[key]
    for cut in [i for i, ch in enumerate(key) if ch == "/"][::-1]:
        head, tail = key[:cut], key[cut + 1:]
        entry = instances.get(head)
        if entry is None:
            continue
        child = str(entry.get("cell_name") or "")
        if child in tables:
            found = _resolve(tables, child, tail, seen | {name})
            if found is not None:
                return found
    return None
```

- **Why longest first:** a block component can itself contain `/`; the longest matching
  block prefix is the innermost one. If its remainder does not resolve, fall back to a
  shorter block prefix.
- **Performance:** only unmatched keys reach the loop; whole-key matches (the common
  flattened-leaf case) return immediately. For a table with many instances, precompute the
  list of block-instance names (usually few) and test `key.startswith(name + "/")` longest
  first, rather than scanning every `/` of every key. The fill is already O(records); this
  keeps the extra cost small.
- **Tests:** add a multi-segment block component with two placements and records for both
  (top-relative and top-prefixed keys); the mixed one-slashed/one-single table case; and the
  sample-shaped six-core one-record→six-instance case. Keep the existing three key forms
  (`SUB/r0_0`, `TOP/u0/r0_0`, `TOP/TOP/u0/r0_0`) passing.
- **Caveat:** after the fix, both sp placement records resolve to the *same* block leaf
  entry; if their values differ, the first wins. Per-placement power values are not
  representable in the current block table; that is a separate design question.
- **Alternative:** carry a path→instance map out of the converter so the fill never has to
  guess where a block name ends. It is heavier and touches more of the data model; the
  resolver prefix fix is the smaller change.

Do not rename the DEF component to work around this; the name is part of the design
database, and the viewer should accept a legal flattened component name.

---

## 10. Related notes

- The previous orientation/location fix is present and the density map is correct; this
  power issue is independent of geometry. Both sp placements being zero (N and FN) is the
  quick discriminator.
- The real run’s 69,333 instances with missing `cell_info` are excluded from all metrics and
  from the physical walk; they contribute no power independently of this issue. They are a
  different, much smaller population than the two sp blocks’ leaves.
- The bundled sample’s top `core_i` container entries carry power values that the tree/map
  never read; the per-core power is the shared leaf sum. If a future sample check compares
  container values with tree rows, it should compare leaves.
- The fill warning says “filled no instance” but does not say “the block component contains
  `/`”; a future diagnostic could name the prefix attempt, but the count and examples are
  enough to identify the case once the name shape is known.
- A stale `--out` dump would carry the same missing power; the same fill limitation applies
  when a `def` run with `--json` is dumped and reloaded.

---

## 11. Status

Recorded for future work. The reproduction in
[`issue_reproduce/`](../../issue_reproduce/) passes all decisive checks and is the
artifact used for this write-up. No viewer source, sample, test or configuration file was
modified; the only additions are the reproduction directory and this record.
