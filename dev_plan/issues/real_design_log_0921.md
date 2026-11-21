# Real-design def-mode run, 2026-09-21 — job 1657044030 on `lx956c_ioe.def.gz` + `--json`: silent for hours after "End DEF parsing" (root cause: quadratic `--json` fill)

Submitted 2026-09-21 17:24 from `whalcld103-hs` via the csh wrapper
`run_design_browser.physical_mode.def.csh` (in
`/tmppdata/LinuxCore950_PD_N3_t/user/l00922843/design_brower`), LSF queue
`bigmem`, `rusage cpu=4;mem=20000`, ran on host `whalcld234-hs` (JOBID
1657044030):

```
run_design_browser.physical_mode.def.csh \
  /tmppdata/AICoreV516PD/user/l00922843/956C/lx956c_ioe_WORKDIR/a0.outgoing/TAG00009_FC_inn25_newFCsyn/lx956c_ioe.def.gz \
  --json lx956c_ioe.instance_info.power.json
```

The wrapper collects all of `$argv` into one variable (`set def="$argv[1-]"`)
and expands it after `--def`, so the `--json …` pair is carried on the same
line as the DEF; argparse's option recognition splits it back apart. The
script itself (Gvim25, snapshot 1):

```csh
#!/bin/csh -f
set def="$argv[1-]"
set exec="/tmppdata/LinuxCore950_PD_N3_t/user/l00922843/design_brower/VLSI_design_browser-master/main.py"
set py="/tmppdata/LinuxCore950_PD_N3_t/user/l00922843/design_brower/venv/bin/python3"
# set lefs="ls /tmppdata/LinuxCore950_PD_N2_t/user/data/LX950/N+3j/lib/stdcell/for_1650v200/lef/*onlypr.lef /tmppdata/LinuxCore950_PD_N2_t/user/data/LX950/PDS/LX956C_TAG_ME M/lef/*lef"
dsb -A root.ug_yothier.Linx956_PD2_HCllass -q bigmem -R "cpu=4;mem=20000" -I "${py} ${exec} def --lef lefs/*.lef --grid_size 2.28 --physical_mode --def ${def}"
```

**Symptom.** The job parsed LEF (10.4 s) and DEF (26.0 s, **3,347,979
instances**) normally, then printed nothing for hours. The last line ever
emitted is the `INFO vlsi_viewer.parsers.convert: def: …` summary from DEF
parsing (snapshot 3). The same design **without `--json` completes in a short
time**, so the hang is specific to the `--json` path.

**Root cause (verified, not a resource problem): the `--json` fill
(`fill_instances`, added in the latest commit `b2da0fd`) is O(N²) in the
instance count of a flat design — ~10¹³ dict merges for 3.35M instances, i.e.
days of CPU — and it logs nothing until the per-file summary, which only
appears after the whole record loop finishes.** Details in section 4.

## 1. Snapshot 1 — the csh wrapper (Gvim25 on `whalcld103-hs`)

See the script transcription above (title bar:
`run_design_browser.physical_mode.def.csh (/tmppdata/LinuxCore950_PD_N3_t/user/l00922843/design_brower)`).

## 2. Snapshot 2 — submission, queue, LEF parse starts

```
[l00922843@whalcld103-hs /tmppdata/LinuxCore950_PD_N3_t/user/000922843/design_brower (2026-09-21 17:24:29)]>
run_design_browser.physical_mode.def.csh /tmppdata/AICoreV516PD/user/l00922843/956C/lx956c_ioe_WORKDIR/a0.outgoing/TAG00009_FC_inn25_newFCsyn/lx956c_ioe.def.gz --json lx956c_ioe.instance_info.power.json
JOBID      MESSAGE
1657044030   Submit job successfully.

2026-09-21 17:24:40.200 ==> job state changed to: PENDING

2026-09-21 17:24:40.914 ==> job state changed to: RUNNING
Job is running on host whalcld234-hs

Start parsing Lef files
Total 220 LEF files
Parsing lefs/hir1zh228_ckmesh_1p14m_4dpm_q1_3q2_2q3_2b_2tma_onlypr.lef
Parsing lefs/hir1zh228l10p57sdb_aic_lvt_onlypr.lef
Parsing lefs/hir1zh228l10p57sdb_aic_svt_onlypr.lef
Parsing lefs/hir1zh228l10p57sdb_aic_ulvt_onlypr.lef
Parsing lefs/hir1zh228l10p57sdb_base_lvt_onlypr.lef
Parsing lefs/hir1zh228l10p57sdb_baseopt_lvt_onlypr.lef
Parsing lefs/hir1zh228l10p57sdb_baseoptm_lvt_onlypr.lef
Parsing lefs/hir1zh228l10p57sdb_baseopt_svt_onlypr.lef
Parsing lefs/hir1zh228l10p57sdb_baseoptm_svt_onlypr.lef
Parsing lefs/hir1zh228l10p57sdb_baseopt_ulvt_onlypr.lef
Parsing lefs/hir1zh228l10p57sdb_baseoptm_ulvt_onlypr.lef
```

## 3. Snapshot 3 (last output ever) — LEF done, DEF parsed, then silence

```
Parsing lefs/HIS6LC956C6SRAMTP256X90M2HSB.lef
Parsing lefs/HIS6LC956C6SRAMTP32X144M1HSB.lef
Parsing lefs/HIS6LC956C6SRAMTP32X150M1HSB.lef
Parsing lefs/HIS6LC956C6SRAMTP32X72M1HSB.lef
Parsing lefs/HIS6LC956C6SRAMTP32X84M1HSB.lef
Parsing lefs/HIS6LC956C6SRAMTP32X96M1HSB.lef
Parsing lefs/HIS6LC956C6SRAMTP64X116M1HSB.lef
Parsing lefs/HIS6LC956C6SRAMTP64X120M1HSB.lef
Parsing lefs/HIS6LC956C6SRAMTP64X160M1HSB.lef
Parsing lefs/HIS6LC956C6SRAMTP64X64M1HSB.lef
Parsing lefs/HIS6LC956C6SRAMTP64X86M1HSB.lef
End parsing 220 LEF file in 10.4225s
INFO vlsi_viewer.parsers.convert: lef: 17380 macro(s) from 220 file(s)
Load DEF file /tmppdata/AICoreV516PD/user/l00922843/956C/lx956c_ioe_WORKDIR/a0.outgoing/TAG00009_FC_inn25_newFCsyn/lx956c_ioe.def.gz
End DEF parsing in 25.9657s
INFO vlsi_viewer.parsers.convert: def: /tmppdata/AICoreV516PD/user/l00922843/956C/lx956c_ioe_WORKDIR/a0.outgoing/TAG00009_FC_inn25_newFCsyn/lx956c_ioe.def.gz -> 3347979 instance(s) (dropped 0 filler, skipped 0 unplaced), 8 boundary point(s)
```

Nothing after that line — no `power: …` fill summary, no metric-tree build,
no window. (The def flow's pickle cache is skipped for in-memory input,
`metrics.py:318` "in-memory input; pickle cache skipped", so no `pickle
cache` line is expected in either variant.)

## 4. Root cause — O(N²) per-record re-merge in the `--json` fill

After `instance_info_from_def` returns, `cli.resolve_inputs`
(`vlsi_viewer/cli.py:298-299`) does, **only when `--json` was given**:

```python
filled = (fill_instances(blocks, args.json_files)
          if getattr(args, "json_files", None) else None)
```

Inside `fill_instances` (`vlsi_viewer/parsers/convert.py`), one JSON record is
resolved per design instance, and each resolution calls `_instances()`:

```python
def _instances(index, name):
    merged: dict = {}
    for block in index.get(name, ()):
        for leaf, entry in block["instances"].items():
            merged.setdefault(leaf, entry)     # rebuilds the WHOLE block dict
    return merged
```

```python
def _resolve(index, name, key, seen=frozenset()):
    ...
    instances = _instances(index, name)   # O(block size), per record
    if key in instances: ...
```

For a flat design (all 3,347,979 instances are leaves of the top block), every
one of the ~3.35M records of `lx956c_ioe.instance_info.power.json` therefore
pays a full 3.35M-entry dict merge:

3,347,979 records × 3,347,979 merges ≈ **1.1 × 10¹³ `setdefault` ops ≈ days**
before the first fill log line (the per-file summary at `convert.py:507`) can
print. With no per-record progress logging in between, the job looks dead.

### Benchmarks confirming the quadratic growth

Synthetic flat designs (one block, N instances) with a matching N-record power
JSON, driven through the real `fill_instances`, run on 2026-09-21 with
`presentation/.venv` python; script kept at `dev_plan/bench_fill.py`:

| N instances = records | fill time | rate |
|---|---|---|
| 1,000 | 0.03 s | 30,574 rec/s |
| 2,000 | 0.13 s | 15,024 rec/s |
| 4,000 | 0.58 s | 6,906 rec/s |
| 8,000 | 2.53 s | 3,162 rec/s |

Time quadruples for every doubling of N (4.3×, 4.5×, 4.4×) and the rate halves
each step — textbook O(N²). Extrapolating the N = 8,000 point to the real
3,347,979 records: 2.53 s × (3,347,979 / 8,000)² ≈ 4.4 × 10⁵ s ≈ **5 days**
(linear extrapolation would give ~18 min — wrong by the factor N). If the
JSON covered only a fraction of the instances, the cost scales proportionally:
~1/10 of the records would still be ~12 h.

### Why it is fast without `--json`

Without `--json`, `fill_instances` is never called; everything else (LEF/DEF
parse, `load_or_build`, `build_physical`) is O(N) and this run proves it is
fast. The fill is the *only* code-path difference between the two variants, so
the difference in wall time is entirely the fill's. The `json.load` of the
power file (tens of seconds, a few hundred MB of file) is finite and
secondary; the quadratic merge loop dominates by orders of magnitude.

## 5. Proposed fix (not implemented — recorded for later)

Merge each block's instances **once** and reuse the merged dict for all record
lookups: thread a `cache: Dict[str, dict]` (keyed by block `top_name`)
through `_instances` / `_resolve` / `_target` / `_shape`, created once in
`fill_instances`. The merged dict holds references to the same entry objects,
so the fill semantics (in-place fill, input's value wins) are unchanged; the
fill drops from O(N × records) to O(N + records), i.e. seconds here instead of
days. Optionally add a periodic progress log (e.g. every 100k records) inside
the record loop, since the loop is currently silent end to end.
