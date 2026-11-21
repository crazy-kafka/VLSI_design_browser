# Real-design metal-mode runs, 2026-09-17 — jobs 1650938458 (ioe db) and 1650945821 (fsu db) on `lx956c_core_clamp_wrap`: two db-only logs

Two chip-level metal-mode runs submitted on 2026-09-17 from
`/tmpdata/LinuxCore950_PD_N3_t/user/000922843/design_browser` via `bsub -I`
(queue `long`, `rusage[pu4;mem=20000]`), both on host `whalcld082-hs`.
They differ only in the second `--db`:

- **Run 1** (JOBID 1650938458, submitted 16:13:03):
  `tmp_db/lx956c_core_clamp_wrap.def.db` + `tmp_db/lx956c_ioe.def.db` — ran to
  completion and printed the full `metal-summary`.
- **Run 2** (JOBID 1650945821, submitted ~16:19:50):
  `tmp_db/lx956c_core_clamp_wrap.def.db` + `tmp_db/lx956c_fsu.def.db` — died
  with `ERROR: grid is (72, 124), this grid's is (189, 253)` right after the
  routing read: the `lx956c_fsu` db was evidently written on a different grid
  than the run's 189 × 253 capacity grid.

Shared by both runs: **0 DEF files and 2 dbs**, same tech LEF as 09-15/09-16
(`HNJ7J30R_5756T228H_1P14M_4DPM_…_V2_3mask_DTC0_L8_Vn.lef`), `--min-layer 2
--max-layer 12 --jobs 8`, root block `lx956c_core_clamp_wrap` with die
2526.2 × 1887.8 um on a 189 × 253 grid @ 10 um, 220 LEF files / 17,385 cells,
11 routing layers M2..B2 (ignoring M1, TM1, TM2, ALPA), and blockage from 89
macros (8 macro types) with fallback to the bottom 4 layers.

The logs below are transcribed from the terminal screenshots: snapshots 1–3
are run 1, snapshots 4–5 are run 2. Long `metal-summary` JSON lines wrap in the
terminal and are re-joined to one line here.

## 1. Run 1 — JOBID 1650938458, `…core_clamp_wrap.def.db + …ioe.def.db` (completed)

### Snapshot 1 — submission, queue, tech LEF, components, LEF parse starts

```
[l00922843@whalcld083-hs /tmpdata/LinuxCore950_PD_N3_t/user/000922843/design_browser (2026-09-17 16:13:03)]>
bsub -A root.ug_yyother.Linux956_PD2_HClass -q long -R 'rusage[pu4;mem=20000]' -I "venv/bin/python3 VLSI_design_browser-master/main.py metal --lef lefs/*.lef --tech-lef /tmpdata/LinuxCore950_PD_N2_t/user/data/LX950/N4/
3j/lib/tlef/HNJ7J30R_5756T228H_1P14M_4DPM_Q1_3Q2_2Q3_2B_2TMa_ALPA2_M3_P40_P42_V2_3mask_DTC0_L8_Vn.lef --min-layer 2 --max-layer 12 --jobs 8 --db tmp_db/lx956c_core_clamp_wrap.def.db tmp_db/lx956c_ioe.def.db"
JOBID      MESSAGE
1650938458   Submit job successfully.

2026-09-17 16:14:35.847 ==> job state changed to: PENDING

2026-09-17 16:14:38.317 ==> job state changed to: RUNNING
Job is running on host whalcld082-hs
INFO vlsi_viewer.cli: metal: reading 0 DEF file(s) and 2 db(s)
INFO vlsi_viewer.metal: metal: stage start          0.00s    rss 72 MB
Start parsing tech lef /tmpdata/LinuxCore950_PD_N2_t/user/data/LX950/N4/3j/lib/tlef/HNJ7J30R_5756T228H_1P14M_4DPM_Q1_3Q2_2Q3_2B_2TMa_ALPA2_M3_P40_P42_V2_3mask_DTC0_L8_Vn.lef
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V2 before 'LAYER V1'
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V3 before 'LAYER V2'
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V4 before 'LAYER V3'
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V5 before 'LAYER V4'
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V6 before 'LAYER V5'
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V7 before 'LAYER V6'
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V3_FB1 before 'LAYER V2'
End parsing tech lef in 0.023s
INFO vlsi_viewer.parsers.routing: tech LEF: 3 region-defined layer(s) are not routing layers of the stack and are skipped: M2_FB1, M3_FB1, M4_FB1
INFO vlsi_viewer.parsers.routing: tech LEF: 15 routing layer(s) of 63 layer(s), 0 unusable, 3 region-defined
INFO vlsi_viewer.metal: metal: layers M2..B2 (11 of 15), ignoring M1, TM1, TM2, ALPA
INFO vlsi_viewer.metal: metal: stage tech-lef          0.26s    rss 74 MB
INFO vlsi_viewer.cli: metal: reading block outlines
INFO vlsi_viewer.metal: metal: stage components        0.00s    2 block(s), root 'lx956c_core_clamp_wrap'   rss 74 MB
Start parsing Lef files
Total 220 Lef files
Parsing lefs/hir1zh228_ckmesh_1p14m_4dpm_q1_3q2_2q3_2b_2tma_onlypr.lef
Parsing lefs/hir1zh228l10p57sdb_aic_lvt_onlypr.lef
```

### Snapshot 2 — LEF pass done, capacity, blockage, routing read, shape counters, per-layer tables

```
Parsing lefs/HIS6LC956C6SRAMTP64K86M1HSB.lef
End parsing 220 Lef file in 10.305s
INFO vlsi_viewer.parsers.convert: lef: 17385 macro(s) from 220 file(s)
INFO vlsi_viewer.cell.loader: Loaded 17385 cell(s) from <in-memory>
INFO vlsi_viewer.metal: metal: stage cell-index        10.86s    17,385 cell(s) from 220 Lef file(s)   rss 479 MB
INFO vlsi_viewer.metal: metal: measuring capacity
INFO vlsi_viewer.metal: metal: stage capacity           2.54s    189 x 253 grid @ 10 um, die 2526.2 x 1887.8 um   rss 471 MB
INFO vlsi_viewer.metal: metal: blockage from 89 macro(s) declaring OBS over 3 layer(s); 0 fall back to the bottom 4 layer(s); 0 declare nothing significant
INFO vlsi_viewer.metal: metal: 0 block of DEF (uncompressed); 1 worker(s) of 8 requested
INFO vlsi_viewer.metal: metal: stage blockage           4.63s    8 macro type(s) with obstruction data   rss 484 MB
INFO vlsi_viewer.cli: metal: reading routing
INFO vlsi_viewer.metal: metal: stage routing           0.01s    149,580,831 shape(s), 174,504,205 point(s)   rss 484 MB
INFO vlsi_viewer.metal: metal: stage routing           0.00s    rss 484 MB
INFO vlsi_viewer.metal: metal: 44395406 shape(s) measured and handed to the rasteriser
INFO vlsi_viewer.metal: metal: 63756509 via point(s) omitted (no wire area)
INFO vlsi_viewer.metal: metal: 379478 non-preferred jog(s) shorter than a track pitch dropped
INFO vlsi_viewer.metal: metal: 7226252 VIRTUAL connection(s) kept as connections (not metal, no area)
INFO vlsi_viewer.metal: metal: 33823186 shape(s) on layers outside the requested range were skipped
INFO vlsi_viewer.metal: metal: shapes per layer
INFO vlsi_viewer.metal:   layer   dir         usable    shapes        area um2   util
INFO vlsi_viewer.metal:   M2      VERTICAL    yes       20,128,723    163293.8   4.1 %
INFO vlsi_viewer.metal:   M3      HORIZONTAL  yes       13,411,218    193558.9   4.9 %
INFO vlsi_viewer.metal:   M4      VERTICAL    yes       2,390,867     245954.1   6.4 %
INFO vlsi_viewer.metal:   M5      HORIZONTAL  yes       1,821,019     503849.2   10.8 %
INFO vlsi_viewer.metal:   M6      VERTICAL    yes       1,655,948     457579.8   9.8 %
INFO vlsi_viewer.metal:   M7      HORIZONTAL  yes       1,352,849     441791.8   9.4 %
INFO vlsi_viewer.metal:   M8      VERTICAL    yes       1,074,967     428539.4   9.2 %
INFO vlsi_viewer.metal:   FM1     HORIZONTAL  yes       1,114,829     442669.5   9.5 %
INFO vlsi_viewer.metal:   FM2     VERTICAL    yes         827,717     312665.6   6.7 %
INFO vlsi_viewer.metal:   B1      HORIZONTAL  yes         369,313     480098.8   10.3 %
INFO vlsi_viewer.metal:   B2      VERTICAL    yes         247,956     618204.7   13.2 %
INFO vlsi_viewer.metal:   layer   vias        jogs    diagonals   signal      power
INFO vlsi_viewer.metal:   M2      18,087,120  0       0           17,790,512  2,338,211
INFO vlsi_viewer.metal:   M3      11,795,057  0       0           10,673,227  2,737,991
INFO vlsi_viewer.metal:   M4      6,774,756   0       0           2,365,060   25,807
INFO vlsi_viewer.metal:   M5      10,122,329  61      0           1,753,019   68,000
INFO vlsi_viewer.metal:   M6      4,500,489   6       0           1,387,816   268,132
INFO vlsi_viewer.metal:   M7      4,168,419   270     0           1,091,481   261,368
INFO vlsi_viewer.metal:   M8      3,517,468   83      0           794,709     280,258
INFO vlsi_viewer.metal:   FM1     2,874,932   129,734 0           672,583     442,246
INFO vlsi_viewer.metal:   FM2     1,012,713   116,014 0           611,262     216,455
INFO vlsi_viewer.metal:   B1      636,638     73,596  0           353,006     16,307
INFO vlsi_viewer.metal:   B2      346,588     59,714  0           247,320     636
INFO vlsi_viewer.metal: metal: skipped outside the layer range: M1 33.8 M
```

### Snapshot 3 — per-line `metal-summary`, warnings

```
INFO vlsi_viewer.metal: metal-summary: run     {"design": "lx956c_core_clamp_wrap", "die": [2526.24, 1887.84], "grid": [189, 253], "grid size_um": 10.0, "version": "v0.1.0"}
INFO vlsi_viewer.metal: metal-summary: params   {"max_layer": 12, "min_layer": 2, "min_segment": null, "top_layer": null}
INFO vlsi_viewer.metal: metal-summary: inputs   {"dbs": ["lx956c_core_clamp_wrap.def.db"], "k956c_ioe.def.db"
INFO vlsi_viewer.metal: metal-summary: stages_s {"blockage": 4.63, "capacity": 2.54, "cell-index": 10.86, "components": 0.0, "grids": 0.0, "routing": 0.01, "start": 0.0, "tech-lef": 0.26}
INFO vlsi_viewer.metal: metal-summary: shapes  {"degenerate": 0, "diagonals": 0, "emitted": 44395406, "filtered": 33823186, "jogs": 379478, "polygon_edges": 0, "total": 149580831, "unknown": 0, "unusable": 0, "vias": 63756509, "virtual": 7226252}
INFO vlsi_viewer.metal: metal-summary: input_text {"forms": 121594954, "layers_used": 12, "lines": 135681758, "points": 174504205, "points_max": 2, "rects": 27905877, "statement_chars_max": 2277466977, "statement_lines_max": 262303382}
INFO vlsi_viewer.metal: metal-summary: Layer M2   {"area_um2": 163293.844, "degenerate": 0, "diagonals": 0, "direction": "VERTICAL", "jogs": 0, "name": "M2", "pitch_um": 0.038, "power": 2338211, "shapes": 20128723, "signal": 17790512, "unusable": 0, "usable": true, "util": 0.04133, "vias": 18087120, "width_um": 0.019}
INFO vlsi_viewer.metal: metal-summary: Layer M3   {"area_um2": 193558.906, "degenerate": 0, "diagonals": 0, "direction": "HORIZONTAL", "jogs": 0, "name": "M3", "pitch_um": 0.04, "power": 2737991, "shapes": 13411218, "signal": 10673227, "unusable": 0, "usable": true, "util": 0.0492, "vias": 11795057, "width_um": 0.02}
INFO vlsi_viewer.metal: metal-summary: Layer M4   {"area_um2": 245954.125, "degenerate": 0, "diagonals": 0, "direction": "VERTICAL", "jogs": 0, "name": "M4", "pitch_um": 0.044, "power": 25807, "shapes": 2390867, "signal": 2365060, "unusable": 0, "usable": true, "util": 0.06446, "vias": 6774756, "width_um": 0.024}
INFO vlsi_viewer.metal: metal-summary: Layer M5   {"area_um2": 503849.219, "degenerate": 0, "diagonals": 0, "direction": "HORIZONTAL", "jogs": 61, "name": "M5", "pitch_um": 0.076, "power": 68000, "shapes": 1821019, "signal": 1753019, "unusable": 0, "usable": true, "util": 0.10767, "vias": 10122329, "width_um": 0.038}
INFO vlsi_viewer.metal: metal-summary: Layer M6   {"area_um2": 457579.7, "degenerate": 0, "diagonals": 0, "direction": "VERTICAL", "jogs": 6, "name": "M6", "pitch_um": 0.076, "power": 268132, "shapes": 1655948, "signal": 1387816, "unusable": 0, "usable": true, "util": 0.09776, "vias": 4500489, "width_um": 0.038}
INFO vlsi_viewer.metal: metal-summary: Layer M7   {"area_um2": 441791.75, "degenerate": 0, "diagonals": 0, "direction": "HORIZONTAL", "jogs": 270, "name": "M7", "pitch_um": 0.076, "power": 261368, "shapes": 1352849, "signal": 1091481, "unusable": 0, "usable": true, "util": 0.09441, "vias": 4168419, "width_um": 0.038}
INFO vlsi_viewer.metal: metal-summary: Layer M8   {"area_um2": 428539.375, "degenerate": 0, "diagonals": 0, "direction": "VERTICAL", "jogs": 83, "name": "M8", "pitch_um": 0.076, "power": 280258, "shapes": 1074967, "signal": 794709, "unusable": 0, "usable": true, "util": 0.09159, "vias": 3517468, "width_um": 0.038}
INFO vlsi_viewer.metal: metal-summary: Layer FM1  {"area_um2": 442669.5, "degenerate": 0, "diagonals": 0, "direction": "HORIZONTAL", "jogs": 129734, "name": "FM1", "pitch_um": 0.096, "power": 442246, "shapes": 1114829, "signal": 672583, "unusable": 0, "usable": true, "util": 0.09446, "vias": 2874932, "width_um": 0.048}
INFO vlsi_viewer.metal: metal-summary: Layer FM2  {"area_um2": 312665.594, "degenerate": 0, "diagonals": 0, "direction": "VERTICAL", "jogs": 116014, "name": "FM2", "pitch_um": 0.096, "power": 216455, "shapes": 827717, "signal": 611262, "unusable": 0, "usable": true, "util": 0.06677, "vias": 1012713, "width_um": 0.048}
INFO vlsi_viewer.metal: metal-summary: Layer B1   {"area_um2": 480098.844, "degenerate": 0, "diagonals": 0, "direction": "HORIZONTAL", "jogs": 73596, "name": "B1", "pitch_um": 0.126, "power": 16307, "shapes": 369313, "signal": 353006, "unusable": 0, "usable": true, "util": 0.10252, "vias": 636638, "width_um": 0.062}
INFO vlsi_viewer.metal: metal-summary: Layer B2   {"area_um2": 618204.688, "degenerate": 0, "diagonals": 0, "direction": "VERTICAL", "jogs": 59714, "name": "B2", "pitch_um": 0.126, "power": 636, "shapes": 247956, "signal": 247320, "unusable": 0, "usable": true, "util": 0.13212, "vias": 346588, "width_um": 0.062}
INFO vlsi_viewer.metal: metal-summary: blockage {"fallback_cells": 0, "fallback_layer_names": ["M2", "M3", "M4"], "fallback_layers": 4, "ignored_cells": [], "ignored_layers": {}, "obs_cells": 89, "obs_layers": [0, 1, 2], "unknown_layers": []}
INFO vlsi_viewer.metal: metal-summary: filtered_layers {"filtered_layers": ["ALPA", "M1", "TM1", "TM2"], "layers_not_in_tech": []}
INFO vlsi_viewer.metal: metal-summary: memory  {"gc_counts": [3956, 359, 11], "gc_s": 1.38, "peak_rss_mb": 628, "rss_mb": 484}
INFO vlsi_viewer.metal: metal-summary: warnings  {"block 'lx956c_ioe' comes from a db that does not match this run's hierarchy places this block N at (0, 661.2), the db was written for N at (0, 0); it's wiring is not counted", "4 cell type(s) are neither in the LEF nor a block, so they contribute no footprint: HPM_WRAP_PROJ1650V200_CPU, lx956c_fsu, lx956c_lsm, tensor_remote_np1ppv100; HPM_WRAP_PROJ1650V200_CPU, lx956c_fsu, lx956c_lsm, tensor_remote_np1ppv100 could be a sub-block whose wiring this run has no DEF or db for", "1092 cell(s) carry signal wire on a layer a macro obstructs there, so their utilisation is not a congestion reading"}
WARNING vlsi_viewer.cli: metal: block 'lx956c_ioe' comes from a db that does not match this run's hierarchy places this block N at (0, 661.2), the db was written for N at (0, 0); it's wiring is not counted
WARNING vlsi_viewer.cli: metal: 4 cell type(s) are neither in the LEF nor a block, so they contribute no footprint: HPM_WRAP_PROJ1650V200_CPU, lx956c_fsu, lx956c_lsm, tensor_remote_np1ppv100; HPM_WRAP_PROJ1650V200_CPU, lx956c_fsu, lx956c_lsm, tensor_remote_np1ppv100 could be a sub-block whose wiring this run has no DEF or db for
WARNING vlsi_viewer.cli: metal: 1092 cell(s) carry signal wire on a layer a macro obstructs there, so their utilisation is not a congestion reading
```

## 2. Run 2 — JOBID 1650945821, `…core_clamp_wrap.def.db + …fsu.def.db` (failed: grid mismatch)

### Snapshot 4 — submission, queue, tech LEF, components, LEF parse starts

```
bsub -A root.ug_yyother.Linux956_PD2_HClass -q long -R 'rusage[pu4;mem=20000]' -I "venv/bin/python3 VLSI_design_browser-master/main.py metal --lef lefs/*.lef --tech-lef /tmpdata/LinuxCore950_PD_N2_t/user/data/LX950/N4/
3j/lib/tlef/HNJ7J30R_5756T228H_1P14M_4DPM_Q1_3Q2_2Q3_2B_2TMa_ALPA2_M3_P40_P42_V2_3mask_DTC0_L8_Vn.lef --min-layer 2 --max-layer 12 --jobs 8 --db tmp_db/lx956c_core_clamp_wrap.def.db tmp_db/lx956c_fsu.def.db"
JOBID      MESSAGE
1650945821   Submit job successfully.

2026-09-17 16:19:50.934 ==> job state changed to: PENDING

2026-09-17 16:19:53.814 ==> job state changed to: RUNNING
Job is running on host whalcld082-hs
INFO vlsi_viewer.cli: metal: reading 0 DEF file(s) and 2 db(s)
INFO vlsi_viewer.metal: metal: stage start          0.00s    rss 71 MB
Start parsing tech lef /tmpdata/LinuxCore950_PD_N2_t/user/data/LX950/N4/3j/lib/tlef/HNJ7J30R_5756T228H_1P14M_4DPM_Q1_3Q2_2Q3_2B_2TMa_ALPA2_M3_P40_P42_V2_3mask_DTC0_L8_Vn.lef
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V2 before 'LAYER V1'
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V3 before 'LAYER V2'
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V4 before 'LAYER V3'
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V5 before 'LAYER V4'
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V6 before 'LAYER V5'
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V7 before 'LAYER V6'
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V3_FB1 before 'LAYER V2'
End parsing tech lef in 0.021s
INFO vlsi_viewer.parsers.routing: tech LEF: 3 region-defined layer(s) are not routing layers of the stack and are skipped: M2_FB1, M3_FB1, M4_FB1
INFO vlsi_viewer.parsers.routing: tech LEF: 15 routing layer(s) of 63 layer(s), 0 unusable, 3 region-defined
INFO vlsi_viewer.metal: metal: layers M2..B2 (11 of 15), ignoring M1, TM1, TM2, ALPA
INFO vlsi_viewer.metal: metal: stage tech-lef          0.19s    rss 74 MB
INFO vlsi_viewer.cli: metal: reading block outlines
INFO vlsi_viewer.metal: metal: stage components        0.00s    2 block(s), root 'lx956c_core_clamp_wrap'   rss 74 MB
Start parsing Lef files
Total 220 Lef files
Parsing lefs/hir1zh228_ckmesh_1p14m_4dpm_q1_3q2_2q3_2b_2tma_onlypr.lef
Parsing lefs/hir1zh228l10p57sdb_aic_lvt_onlypr.lef
```

### Snapshot 5 — LEF pass done, capacity, blockage, routing read, then the grid-mismatch error

```
Parsing lefs/HIS6LC956C6SRAMTP64K86M1HSB.lef
End parsing 220 Lef file in 10.516s
INFO vlsi_viewer.parsers.convert: lef: 17385 macro(s) from 220 file(s)
INFO vlsi_viewer.cell.loader: Loaded 17385 cell(s) from <in-memory>
INFO vlsi_viewer.metal: metal: stage cell-index        11.11s    17,385 cell(s) from 220 Lef file(s)   rss 477 MB
INFO vlsi_viewer.metal: metal: measuring capacity
INFO vlsi_viewer.metal: metal: stage capacity           2.54s    189 x 253 grid @ 10 um, die 2526.2 x 1887.8 um   rss 469 MB
INFO vlsi_viewer.metal: metal: blockage from 89 macro(s) declaring OBS over 3 layer(s); 0 fall back to the bottom 4 layer(s); 0 declare nothing significant
INFO vlsi_viewer.metal: metal: 0 block of DEF (uncompressed); 1 worker(s) of 8 requested
INFO vlsi_viewer.metal: metal: stage blockage           3.84s    8 macro type(s) with obstruction data   rss 474 MB
INFO vlsi_viewer.cli: metal: reading routing
INFO vlsi_viewer.metal: metal: lx956c_core_clamp_wrap: 44395406 shape(s) read from a db, the DEF not parsed
ERROR: grid is (72, 124), this grid's is (189, 253)
```

## 3. Differences between the two runs (from the log lines as captured)

- Stage timings: tech-lef 0.26 s vs 0.19 s; cell-index 10.86 s (rss 479 MB) vs
  11.11 s (rss 477 MB); capacity 2.54 s in both (rss 471 MB vs 469 MB);
  blockage 4.63 s (rss 484 MB) vs 3.84 s (rss 474 MB); LEF parse 10.305 s vs
  10.516 s.
- Run 1's routing read reported `149,580,831 shape(s), 174,504,205 point(s)`
  (0.01 s) and 44,395,406 measured shapes; run 2 never got that far — after
  `lx956c_core_clamp_wrap: 44395406 shape(s) read from a db, the DEF not parsed`
  it stopped at `ERROR: grid is (72, 124), this grid's is (189, 253)`.
- Run 1's warnings all concern the **ioe** db: its N is placed by this run's
  hierarchy at (0, 661.2) but the db was written for N at (0, 0), so its wiring
  is not counted; plus the 4 unnamed cell types and 1,092 obstructed-signal
  cells. Run 2 (fsu db) printed no such warnings — it died before the summary.
- Notably, both runs read the **same** 44,395,406 shapes for
  `lx956c_core_clamp_wrap` before diverging, so the divergence is entirely in
  how the second db (ioe vs fsu) is consumed.
