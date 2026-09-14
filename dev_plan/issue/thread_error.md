# Metal mode with `--jobs 8` aborts: `error: cannot pickle '_thread.lock' object`

- **Date:** 2026-09-14, job `1645534805` (LSF, queue `long`, `-R 'cpu=4;mem=20000'`, host `whalc234-hs`)
- **Command:** `venv/bin/python3 VLSI_design_browser-master/main.py metal ... --min-layer 2 --max-layer 12 --jobs 8`
- **Design:** `lx956c_ioe` (3,355,697 instances; 17,385 macros from 221 LEF files; die 1060.2 x 1226.6 um)
- **Failure:** the run dies in the *reading routing* stage, after ~80 s of successful stages, with a single-line error and exit.
- **Status:** fixed. The callable is no longer shipped to the workers at all - the parent raises one
  byte of shared memory and the workers read that instead - and a worker that stops now hands back
  what it measured. Plan: [`../pooled_cancel.md`](../pooled_cancel.md); as built: *Phase 19* of
  [`../metal_density_asbuilt.md`](../metal_density_asbuilt.md).

This is the second run of the day on this design. The first (job `1645073007`, 11:46, no `--jobs` flag) completed successfully and is recorded in `real-design-metal-mode.md`. The only new flag on this run is `--jobs 8`, which switches the wiring pass to the multi-process path in `vlsi_viewer/parallel.py` — and that is exactly where it crashes.

## 0. The command (as displayed in the terminal)

```
dsub -A root.ug.yyother.linux956_PD2_MClass -q long -R 'cpu=4;mem=20000' -I "venv/bin/python3 VLSI_design_browser-master/main.py metal --def /tmpdata/LinxCore950_PD_N3_t/user/l00922843/IOE/20.PR.lx956_ioe/TAG
0825_FC_inn25_seqMerge/DATAOUT/lx956c_ioe.def.gz --lef lefts/* --tech-lef /tmpdata/LinxCore950_PD_N2_t/user/data/LX950/N43/lib/tlef/HNJ3730R_57S6T2228H_1P14M_4DPM_Q1_3Q2_2Q3_2B_2TMa_ALPA2_M3_P40_P42_V2_3mask_DTC
O_L8_Vn.lef --min-layer 2 --max-layer 12 --jobs 8"
JOBID      MESSAGE
1645534805 Submit job successfully.
```

The command line is wrapped by the terminal across three display lines; the logical path is
`.../20.PR.lx956_ioe/TAG0825_FC_inn25_seqMerge/DATAOUT/lx956c_ioe.def.gz` and the tech LEF is
`.../V2_3mask_DTCO_L8_Vn.lef` (the line breaks fall inside those two long tokens, confirmed by the
single-line "Load DEF file ..." log line further down).

## 1. Original log text (transcribed from the two terminal snapshots)

### Snapshot 1 — submission, queue, tech LEF, components pass, LEF parse starts

```
dsub -A root.ug.yyother.linux956_PD2_MClass -q long -R 'cpu=4;mem=20000' -I "venv/bin/python3 VLSI_design_browser-master/main.py metal --def /tmpdata/LinxCore950_PD_N3_t/user/l00922843/IOE/20.PR.lx956_ioe/TAG
0825_FC_inn25_seqMerge/DATAOUT/lx956c_ioe.def.gz --lef lefts/* --tech-lef /tmpdata/LinxCore950_PD_N2_t/user/data/LX950/N43/lib/tlef/HNJ3730R_57S6T2228H_1P14M_4DPM_Q1_3Q2_2Q3_2B_2TMa_ALPA2_M3_P40_P42_V2_3mask_DTC
O_L8_Vn.lef --min-layer 2 --max-layer 12 --jobs 8"
JOBID      MESSAGE
1645534805 Submit job successfully.

2026-09-14 14:56:40.694 ==> job state changed to: PENDING

2026-09-14 14:56:43.716 ==> job state changed to: RUNNING
Job is running on host whalc234-hs

INFO vlsi_viewer.cli: metal: reading 1 DEF file(s)
INFO vlsi_viewer.metal: metal: stage start            0.00s   rss 72 MB
Start parsing tech lef /tmpdata/LinxCore950_PD_N2_t/user/data/LX950/N43/lib/tlef/HNJ3730R_57S6T2228H_1P14M_4DPM_Q1_3Q2_2Q3_2B_2TMa_ALPA2_M3_P40_P42_V2_3mask_DTC
O_L8_Vn.lef
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V2 before 'LAYER V1'
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V3 before 'LAYER V2'
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V4 before 'LAYER V3'
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V5 before 'LAYER V4'
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V6 before 'LAYER V5'
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V7 before 'LAYER V6'
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V3_FB1 before 'LAYER V2'
End parsing tech lef in 0.022s
INFO vlsi_viewer.parsers.routing: tech LEF: 3 region-defined layer(s) are not routing layers of the stack and are skipped: M2_FB1, M3_FB1, M4_FB1
INFO vlsi_viewer.parsers.routing: tech LEF: 15 routing layer(s) of 63 layer(s), 0 unusable, 3 region-defined
INFO vlsi_viewer.metal: metal: layers M2..B2 (11 of 15), ignoring M1, TM1, TM2, ALPA
INFO vlsi_viewer.metal: metal: stage tech-lef               0.02s   rss 72 MB
INFO vlsi_viewer.cli: metal: reading block outlines
Load DEF file /tmpdata/LinxCore950_PD_N3_t/user/l00922843/IOE/20.PR.lx956_ioe/TAG0825_FC_inn25_seqMerge/DATAOUT/lx956c_ioe.def.gz
End DEF parsing in 27.2012s
INFO vlsi_viewer.parsers.convert: def: /tmpdata/LinxCore950_PD_N3_t/user/l00922843/IOE/20.PR.lx956_ioe/TAG0825_FC_inn25_seqMerge/DATAOUT/lx956c_ioe.def.gz -> 3355697 instance(s) (dropped 0 filler, skipped 0 unloaded), 8 boundary point(s)
INFO vlsi_viewer.loader: Loaded block 'lx956c_ioe' with 3355697 instance(s) from <in-memory>
INFO vlsi_viewer.metal: metal: stage components       44.25s  1 block(s), root 'lx956c_ioe'  rss 2,485 MB
Start parsing LEF files
Total 221 LEF files
Parsing lefts/hirzh228_ckmesh_1p14m_4dpm_q1_3q2_2q3_2b_2tma_onlypr.lef
```

### Snapshot 2 — LEF parse end, capacity, blockage, routing, then the error

```
End parsing 221 LEF file in 10.644s
INFO vlsi_viewer.parsers.convert: lef: 17385 macro(s) from 221 file(s)
INFO vlsi_viewer.loader: Loaded 17385 cell(s) from <in-memory>
INFO vlsi_viewer.metal: metal: stage cell-index        11.16s  17,385 cell(s) from 221 LEF file(s)  rss 2,390 MB
INFO vlsi_viewer.metal: metal: measuring capacity
INFO vlsi_viewer.metal: metal: stage capacity         0.75s  123 x 107 grid @ 10 um, die 1060.2 x 1226.6 um  rss 2,366 MB
INFO vlsi_viewer.metal: metal: blockage from 89 macro(s) declaring OBS over 3 layer(s); 0 fall back to the bottom 4 layer(s) (M2, M3, M4 inside the measured range); 0 declare nothing significant
INFO vlsi_viewer.metal: metal: stage blockage        9.53s  8 macro type(s) with obstruction data  rss 2,366 MB
INFO vlsi_viewer.cli: metal: reading routing
INFO vlsi_viewer.cli: metal: reading routing in lx956c_ioe
error: cannot pickle '_thread.lock' object
```

**Transcription notes.** The two snapshots are windows of one scrolling terminal; the ~220
per-file "Parsing lefts/..." lines between snapshot 1's last line and snapshot 2's first line are
not captured. The "Start parsing ..." line rendered in the snapshot as "Start parsing Lem files"
is transcribed as "LEF files" (the capital E is ambiguous at this resolution; the surrounding lines
"Total 221 LEF files" / "End parsing 221 LEF file" settle it). The long tech-LEF and DEF paths are
wrapped by the terminal as shown; the spaces in "TAG 0825" and "DTC O_L8" are display wraps, not
characters in the paths. Column alignment of the stage lines is approximate.

