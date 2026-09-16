# Real-design metal-mode run, 2026-09-16 — job 1649642129, first run on the 09-16 build: log + job-statistics snapshot

The second chip-level metal-mode run of `lx956c_ioe` with `--jobs 8`, and the
first run on the build committed 2026-09-16 00:10 (`e34c6dd`, "Report the metal
read per layer, and stop measuring `VIRTUAL` as metal"). That build is visible
all through the log:

- workers tag their own lines `[w0]`–`[w7]` (09-15's run had no attribution),
- the summary is one short line per section (`metal-summary: run`, `params`,
  `inputs`, `stages_s`, `shapes`, `input_text`, `layer M2` … `layer B2`,
  `blockage`, `filtered_layers`, `memory`, `warnings`) instead of one
  ~4,000-character record,
- a per-layer table (shapes / area / utilisation, then vias / jogs /
  diagonals / signal) is printed after the routing stage,
- `VIRTUAL ( x y )` is no longer measured as metal: **21,175,654** VIRTUAL DEF
  connections are "kept as connections (not metal, no area)", and the inline
  `RECT` beside them is now measured — the input's `rects` count is
  81,172,072, exactly the total-shape difference vs the 09-15 run
  (330,239,881 − 249,067,809).

Same design and DEF path as 09-15, but a 13-minute-older file
(mtime 1,788,556,018 vs 1,788,556,810). Submitted 2026-09-16 18:42:35 to
`-q long` with `cpu=4;mem=20000`, queue wait ~3.5 s, host `whalcld233-hs`
(09-15 ran on `metalcd233-hs`). The routing read finished in **1,696.70 s** with
8 workers vs **1,780.64 s** on 09-15 — **4.7 % faster** on the same 8 workers —
while the components pass got slower (66.38 s vs 44.19 s), so the whole run
improved by **60.57 s** of compute (1,785.87 s vs 1,846.44 s, −3.3 %).

The log below is transcribed from the terminal screenshots (snapshots 1–5);
snapshot 6 is the scheduler's job-statistics page for the same job. The routing
phase is eight concurrent workers whose per-minute heartbeats interleave on one
stream, so the "Load DEF file … / Read DEF … / End DEF parsing in …" triples are
not line-continuous between windows. Where a screenshot was ambiguous a digit
or a worker tag may be off; snapshot 6 was transcribed from the page as
displayed (its top is scrolled off).

## 0. The command

```
dsb -A root.ug.yyother.Linx956_PD_HClass -q long -R 'cpu=4;mem=20000' -I 'venv/bin/python3 VLSI_design_browser-master/main.py metal --def /tmpdata/LinxCore950_PD_N3_t/user/l00922843/IOE/20.PR_Lx956_ioe/TAG0825_FC_inn25_seqMerge/DATAOUT/lx956c_ioe.def.gz --lef lefs/* --tech-lef /tmpdata/LinxCore950_PD_N2_t/user/data/LX950/N43/lib/lef/HN3J30R_575GT228H_1P14M_4DPM_Q1_3Q2_2Q3_2B_2TMa_ALPA2_M3_P40_P42_V2_3mask_DTCO_L8_Vn.lef' --min-layer 2 --max-layer 12 --jobs 8"
```

Same as 09-15 except the launcher is spelled `dsb` (09-15's record showed
`dsh`). The scheduler's COMMAND field (snapshot 6) shows the inner command as
`venv/bin/python3 VLSI_design_browser-master/main.py metal … --lef lefs/ …` —
note `lefs/` there, `lefs/*` in the submission line.

## 1. Run log (as captured)

### Snapshot 1 — submission, queue, tech LEF, components pass, LEF parse starts

```
        MESSAGE
JOBID      Submit job successfully.
1649642129  Submit job successfully.

2026-09-16 18:42:35.554 ==> job state changed to: PENDING

2026-09-16 18:42:39.014 ==> job state changed to: RUNNING
Job is running on host whalcld233-hs
INFO vlsi_viewer.cli: metal: reading 1 DEF file(s)
INFO vlsi_viewer.metal: metal: stage start             0.00s    rss 71 MB
Start parsing tech lef /tmpdata/LinxCore950_PD_N2_t/user/data/LX950/N43/lib/lef/HN3J30R_575GT228H_1P14M_4DPM_Q1_3Q2_2Q3_2B_2TMa_ALPA2_M3_P40_P42_V2_3mask_DTCO_L8_Vn.lef
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V2 before 'LAYER V1'
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V3 before 'LAYER V2'
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V4 before 'LAYER V3'
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V5 before 'LAYER V4'
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V6 before 'LAYER V5'
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V7 before 'LAYER V6'
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V3_FB1 before 'LAYER V2'
End parsing tech lef in 0.024s
INFO vlsi_viewer.parsers.routing: tech LEF: 3 region-defined layer(s) are not routing layers of the stack and are skipped: M2_FB1, M3_FB1, M4_FB1
INFO vlsi_viewer.parsers.routing: tech LEF: 15 routing layer(s) of 63 layer(s), 0 unusable, 3 region-defined
INFO vlsi_viewer.metal: metal: layers M2..B2 (11 of 15), ignoring M1, TM1, TM2, ALPA
INFO vlsi_viewer.metal: metal: stage tech-lef                0.02s    rss 71 MB
INFO vlsi_viewer.cli: metal: reading block outlines
Load DEF file /tmpdata/LinxCore950_PD_N3_t/user/l00922843/IOE/20.PR_Lx956_ioe/TAG0825_FC_inn25_seqMerge/DATAOUT/lx956c_ioe.def.gz
Read DEF 5,819,128 lines   178,990 lines/s   1 min elapsed
End DEF parsing in 36.3509s
INFO vlsi_viewer.parsers.convert: def: /tmpdata/LinxCore950_PD_N3_t/user/l00922843/IOE/20.PR_Lx956_ioe/TAG0825_FC_inn25_seqMerge/DATAOUT/lx956c_ioe.def.gz -> 3355697 instance(s) (dropped 0 filler, skipped 0 unplcaced), 8 boundary point(s)
INFO vlsi_viewer.loader: Loaded block 'lx956c_ioe' with 3355697 instance(s) from <in-memory>
INFO vlsi_viewer.metal: metal: stage components           66.38s   1 block(s), root 'lx956c_ioe'    rss 2,485 MB
Start parsing lef files
Total 221 LEF files
Parsing lefs/hirizh228_ckmesh_1p14m_4dpm_q1_3q2_2q3_2b_2tma_onlypr.lef
Parsing lefs/hirizh228_ckmesh_1p14m_4dpm_q1_3q2_2q3_2b_2tma_onlypr.lef.cell_info.json
Parsing lefs/hirizh228l10p57sdb_aic_lvt_onlypr.lef
```

### Snapshot 2 — LEF pass done, capacity and blockage, 8-worker routing read starts (worker tags now visible)

```
Parsing lefs/HI56LC956C6SRA4MTP6X46M1HSB.lef
End parsing 221 LEF file in 11.506s
INFO vlsi_viewer.parsers.convert: lef: 17385 macro(s) from 221 file(s)
INFO vlsi_viewer.loader: loaded 17385 cell(s) from <in-memory>
INFO vlsi_viewer.metal: metal: stage cell-index           12.11s  17,385 cell(s) from 221 LEF file(s)    rss 2,389 MB
INFO vlsi_viewer.cli: metal: measuring capacity
INFO vlsi_viewer.metal: metal: stage capacity             0.76s   123 x 107 grid @ 10 um, die 1060.2 x 1226.6 um    rss 2,364 MB
INFO vlsi_viewer.metal: metal: blockage from 89 macro(s) declaring OBS over 3 layer(s); 0 fall back to the bottom 4 layer(s); 0 declare nothing significant
INFO vlsi_viewer.metal: metal: 2108 MB of DEF (uncompressed); 8 worker(s)
INFO vlsi_viewer.metal: metal: stage blockage              9.90s    8 macro type(s) with obstruction data    rss 2,365 MB
INFO vlsi_viewer.cli: metal: reading routing in lx956c_ioe
Load DEF file lx956c_ioe
[w3] Load DEF file lx956c_ioe
[w0] Load DEF file lx956c_ioe
[w6] Load DEF file lx956c_ioe
[w5] Load DEF file lx956c_ioe
[w1] Load DEF file lx956c_ioe
[w7] Load DEF file lx956c_ioe
[w2] Load DEF file lx956c_ioe
[w4] Load DEF file lx956c_ioe
Read DEF 2,000,736 lines   66,690 lines/s   1 min elapsed   NETS 35,340/38,905   ~0.0 min left
[w3] Read DEF 2,004,239 lines   66,808 lines/s   1 min elapsed   NETS 35,161/38,905   ~0.1 min left
[w0] Read DEF 2,003,348 lines   66,777 lines/s   1 min elapsed   NETS 35,321/38,905   ~0.0 min left
[w6] Read DEF 2,002,628 lines   66,752 lines/s   1 min elapsed   NETS 35,277/38,905   ~0.0 min left
[w5] Read DEF 1,996,120 lines   66,536 lines/s   1 min elapsed   NETS 35,182/38,905   ~0.1 min left
[w4] End DEF parsing in 33.4547s
[w3] End DEF parsing in 33.6977s
[w0] End DEF parsing in 33.5476s
[w1] End DEF parsing in 33.5355s
[w5] End DEF parsing in 33.6807s
[w7] Read DEF 18,074,407 lines   526,813 lines/s   1 min elapsed   SPECIALNETS 11,095/11,095   ~0.0 min left
[w2] Read DEF 27,898,515 lines   929,949 lines/s   1 min elapsed   SPECIALNETS 11,096/11,096   ~0.0 min left
[w3] Load DEF file lx956c_ioe
[w6] Load DEF file lx956c_ioe
[w0] Load DEF file lx956c_ioe
[w2] Read DEF 58,035,173 lines   967,252 lines/s   1 min elapsed   SPECIALNETS 11,096/11,096   ~0.0 min left
[w4] Read DEF 2,016,457 lines   67,179 lines/s   1 min elapsed   NETS 36,768/50,000   ~0.2 min left
[w3] Read DEF 2,022,736 lines   67,424 lines/s   1 min elapsed   NETS 37,131/50,000   ~0.2 min left
[w0] Read DEF 2,020,340 lines   67,344 lines/s   1 min elapsed   NETS 36,618/50,000   ~0.2 min left
[w5] Read DEF 2,015,220 lines   67,173 lines/s   1 min elapsed   NETS 37,030/50,000   ~0.2 min left
[w4] End DEF parsing in 40.5031s
[w3] End DEF parsing in 40.2243s
[w0] End DEF parsing in 40.8579s
[w6] End DEF parsing in 40.3797s
[w5] End DEF parsing in 40.5155s
[w4] Load DEF file lx956c_ioe
[w3] Load DEF file lx956c_ioe
[w6] Load DEF file lx956c_ioe
[w0] Load DEF file lx956c_ioe
[w1] Load DEF file lx956c_ioe
[w5] Load DEF file lx956c_ioe
[w2] Load DEF file lx956c_ioe
[w7] Load DEF file lx956c_ioe
[w4] Read DEF 2,013,876 lines   67,129 lines/s   1 min elapsed   NETS 38,196/50,000   ~0.2 min left
[w3] Read DEF 2,006,195 lines   66,873 lines/s   1 min elapsed   NETS 38,031/50,000   ~0.2 min left
[w6] Read DEF 2,003,667 lines   66,787 lines/s   1 min elapsed   NETS 38,037/50,000   ~0.2 min left
[w0] Read DEF 2,006,276 lines   66,878 lines/s   1 min elapsed   NETS 38,026/50,000   ~0.2 min left
[w5] Read DEF 2,002,395 lines   66,746 lines/s   1 min elapsed   NETS 37,958/50,000   ~0.2 min left
[w4] End DEF parsing in 40.2339s
[w3] End DEF parsing in 40.3394s
[w6] End DEF parsing in 40.2780s
[w0] End DEF parsing in 40.4144s
[w5] End DEF parsing in 40.3496s
[w1] Read DEF 1,966,071 lines   65,535 lines/s   1 min elapsed   NETS 34,711/50,000   ~0.2 min left
[w4] Read DEF 1,979,425 lines   65,978 lines/s   1 min elapsed   NETS 34,886/50,000   ~0.2 min left
[w6] Read DEF 1,973,979 lines   65,796 lines/s   1 min elapsed   NETS 34,692/50,000   ~0.2 min left
[w0] Read DEF 1,903,000 lines   63,431 lines/s   1 min elapsed   NETS 33,685/50,000   ~0.2 min left
[w5] Read DEF 1,935,516 lines   64,513 lines/s   1 min elapsed   NETS 33,770/50,000   ~0.2 min left
[w3] End DEF parsing in 43.8827s
[w4] End DEF parsing in 43.1401s
[w6] End DEF parsing in 43.3132s
[w0] End DEF parsing in 42.6841s
[w5] End DEF parsing in 43.9869s
[w1] Read DEF 1,962,685 lines   65,422 lines/s   1 min elapsed   NETS 35,902/50,000   ~0.2 min left
[w7] Read DEF 1,935,727 lines   64,523 lines/s   1 min elapsed   NETS 35,534/50,000   ~0.2 min left
[w1] End DEF parsing in 41.9335s
[w3] Load DEF file lx956c_ioe
[w4] Load DEF file lx956c_ioe
[w7] Load DEF file lx956c_ioe
[w6] Load DEF file lx956c_ioe
[w5] Load DEF file lx956c_ioe
[w0] Load DEF file lx956c_ioe
[w2] Load DEF file lx956c_ioe
[w4] Read DEF 1,884,798 lines   62,826 lines/s   1 min elapsed   NETS 36,493/50,000   ~0.2 min left
[w3] Read DEF 1,887,160 lines   62,905 lines/s   1 min elapsed   NETS 36,378/50,000   ~0.2 min left
[w6] Read DEF 1,887,843 lines   62,928 lines/s   1 min elapsed   NETS 36,685/50,000   ~0.2 min left
[w0] Read DEF 1,896,070 lines   63,197 lines/s   1 min elapsed   NETS 36,792/50,000   ~0.2 min left
[w5] Read DEF 1,893,674 lines   63,122 lines/s   1 min elapsed   NETS 36,635/50,000   ~0.2 min left
```

### Snapshot 3 — the 6-minute slices: w1's long NETS slice ends at 364.2 s, w7's at 371.3 s; w3's SPECIALNETS slice mid-read

```
[w6] Read DEF 2,000,862 lines   66,694 lines/s   1 min elapsed   NETS 36,064/50,000   ~0.2 min left
[w0] Read DEF 1,958,729 lines   65,821 lines/s   1 min elapsed   NETS 35,452/50,000   ~0.2 min left
[w5] Read DEF 1,979,466 lines   65,982 lines/s   1 min elapsed   NETS 35,010/50,000   ~0.3 min left
[w4] Read DEF 2,011,532 lines   67,051 lines/s   1 min elapsed   NETS 33,926/50,000   ~0.2 min left
[w3] Read DEF 17,962,586 lines   54,172 lines/s   6 min elapsed   SPECIALNETS 11,096/11,096   ~0.0 min left
[w4] End DEF parsing in 43.2316s
[w3] Read DEF 18,074,408 lines   53,635 lines/s   6 min elapsed   SPECIALNETS 11,095/11,095   ~0.0 min left
[w6] End DEF parsing in 43.3855s
[w0] End DEF parsing in 43.3573s
[w5] End DEF parsing in 43.1342s
[w1] Read DEF 19,849,157 lines   54,894 lines/s   6 min elapsed   NETS 35,617/38,904   ~0.0 min left
[w1] End DEF parsing in 364.2037s
[w7] Read DEF 19,901,290 lines   54,228 lines/s   6 min elapsed   NETS 34,785/38,905   ~0.1 min left
[w3] Load DEF file lx956c_ioe
[w4] Load DEF file lx956c_ioe
[w7] End DEF parsing in 371.3069s
[w6] Load DEF file lx956c_ioe
[w0] Load DEF file lx956c_ioe
[w5] Load DEF file lx956c_ioe
[w1] Load DEF file lx956c_ioe
[w3] Read DEF 1,966,071 lines   65,535 lines/s   1 min elapsed   NETS 34,711/50,000   ~0.2 min left
[w4] Read DEF 1,979,425 lines   65,978 lines/s   1 min elapsed   NETS 34,886/50,000   ~0.2 min left
[w6] Read DEF 1,973,979 lines   65,796 lines/s   1 min elapsed   NETS 34,692/50,000   ~0.2 min left
[w0] Read DEF 1,903,000 lines   63,431 lines/s   1 min elapsed   NETS 33,685/50,000   ~0.2 min left
[w5] Read DEF 1,935,516 lines   64,513 lines/s   1 min elapsed   NETS 33,770/50,000   ~0.2 min left
[w3] End DEF parsing in 43.8827s
[w4] End DEF parsing in 43.1401s
[w6] End DEF parsing in 43.3132s
[w0] End DEF parsing in 42.6841s
[w5] End DEF parsing in 43.9869s
[w1] Read DEF 1,962,685 lines   65,422 lines/s   1 min elapsed   NETS 35,902/50,000   ~0.2 min left
[w7] Read DEF 1,935,727 lines   64,523 lines/s   1 min elapsed   NETS 35,534/50,000   ~0.2 min left
[w1] End DEF parsing in 41.9335s
[w3] Load DEF file lx956c_ioe
[w4] Load DEF file lx956c_ioe
[w7] Load DEF file lx956c_ioe
[w6] Load DEF file lx956c_ioe
[w5] Load DEF file lx956c_ioe
[w0] Load DEF file lx956c_ioe
[w2] Load DEF file lx956c_ioe
[w4] Read DEF 1,884,798 lines   62,826 lines/s   1 min elapsed   NETS 36,493/50,000   ~0.2 min left
[w3] Read DEF 1,887,160 lines   62,905 lines/s   1 min elapsed   NETS 36,378/50,000   ~0.2 min left
[w6] Read DEF 1,887,843 lines   62,928 lines/s   1 min elapsed   NETS 36,685/50,000   ~0.2 min left
[w0] Read DEF 1,896,070 lines   63,197 lines/s   1 min elapsed   NETS 36,792/50,000   ~0.2 min left
[w5] Read DEF 1,893,674 lines   63,122 lines/s   1 min elapsed   NETS 36,635/50,000   ~0.2 min left
```

### Snapshot 4 — w2's SPECIALNETS slice ends at 909.78 s (largest single read captured); 15-minute slices still running

```
[w1] End DEF parsing in 43.2225s
[w3] Load DEF file lx956c_ioe
[w4] Load DEF file lx956c_ioe
[w6] Load DEF file lx956c_ioe
[w0] Load DEF file lx956c_ioe
[w5] Load DEF file lx956c_ioe
[w3] End DEF parsing in 42.9371s
[w6] End DEF parsing in 43.5316s
[w0] End DEF parsing in 42.8765s
[w5] End DEF parsing in 43.1146s
[w1] Read DEF 1,850,637 lines   61,682 lines/s   1 min elapsed   NETS 33,721/50,000   ~0.2 min left
[w3] End DEF parsing in 13.3365s
[w6] End DEF parsing in 13.1569s
[w7] Read DEF 1,869,312 lines   62,310 lines/s   1 min elapsed   NETS 34,514/50,000   ~0.2 min left
[w5] End DEF parsing in 12.8186s
[w0] End DEF parsing in 13.9994s
[w1] Read DEF in 46.9205s
[w1] End DEF parsing in 46.4153s
[w7] Load DEF file lx956c_ioe
[w1] Load DEF file lx956c_ioe
[w7] Read DEF 2,009,645 lines   66,987 lines/s   1 min elapsed   NETS 33,362/50,000   ~0.2 min left
[w1] Read DEF 2,014,933 lines   67,162 lines/s   1 min elapsed   NETS 33,652/50,000   ~0.2 min left
[w1] End DEF parsing in 43.5791s
[w1] End DEF parsing in 43.6668s
[w1] Load DEF file lx956c_ioe
[w7] Read DEF 1,815,372 lines   60,512 lines/s   1 min elapsed   NETS 32,932/50,000   ~0.3 min left
[w1] Read DEF 1,864,247 lines   62,141 lines/s   1 min elapsed   NETS 32,641/50,000   ~0.3 min left
[w1] End DEF parsing in 46.9535s
[w1] End DEF parsing in 46.6025s
[w1] Load DEF file lx956c_ioe
[w7] Read DEF 1,851,930 lines   61,730 lines/s   1 min elapsed   NETS 35,695/50,000   ~0.2 min left
[w7] Read DEF 1,842,376 lines   61,411 lines/s   1 min elapsed   NETS 35,587/50,000   ~0.2 min left
[w1] End DEF parsing in 44.6028s
[w1] End DEF parsing in 44.2738s
[w2] Read DEF 58,681,090 lines   66,875 lines/s   15 min elapsed   SPECIALNETS 11,096/11,096   ~0.0 min left
[w1] Read DEF 60,554,368 lines   65,478 lines/s   15 min elapsed   NETS 37,665/50,000   ~0.2 min left
[w2] Read DEF 59,553,368 lines   66,728 lines/s   15 min elapsed   NETS 35,297/38,904   ~0.1 min left
[w7] Read DEF 1,885,840 lines   62,858 lines/s   1 min elapsed   NETS 36,293/50,000   ~0.2 min left
[w2] End DEF parsing in 909.7829s
[w1] End DEF parsing in 41.7836s
[w7] End DEF parsing in 42.3331s
[w1] Load DEF file lx956c_ioe
[w1] End DEF parsing in 12.546s
[w7] End DEF parsing in 12.2884s
[w2] Load DEF file lx956c_ioe
[w2] Read DEF 2,024,463 lines   67,481 lines/s   1 min elapsed   NETS 36,782/50,000   ~0.2 min left
[w2] End DEF parsing in 40.5102s
[w2] Load DEF file lx956c_ioe
[w2] Read DEF 1,985,509 lines   66,183 lines/s   1 min elapsed   NETS 37,652/50,000   ~0.2 min left
[w2] End DEF parsing in 40.4741s
[w2] Read DEF 1,973,886 lines   65,793 lines/s   1 min elapsed   NETS 35,675/50,000   ~0.2 min left
[w2] Read DEF 1,948,213 lines   64,940 lines/s   1 min elapsed   NETS 32,166/50,000   ~0.3 min left
[w2] Read DEF 2,011,617 lines   67,049 lines/s   1 min elapsed   NETS 35,058/50,000   ~0.2 min left
[w2] Read DEF 2,018,907 lines   67,296 lines/s   1 min elapsed   NETS 39,108/50,000   ~0.1 min left
[w2] Read DEF 1,995,771 lines   66,522 lines/s   1 min elapsed   NETS 38,231/50,000   ~0.2 min left
[w2] End DEF parsing in 39.6849s
[w2] End DEF parsing in 40.3816s
[w2] End DEF parsing in 12.373s
```

### Snapshot 5 — routing stage done, shape counters, per-layer tables, per-line metal-summary

```
INFO vlsi_viewer.metal: lx956c_ioe: 5 non-default rule(s)
INFO vlsi_viewer.metal: metal: stage routing             1696.70s  330,239,881 shape(s), 373,423,631 point(s)    rss 2,372 MB
INFO vlsi_viewer.metal: metal: stage grids                 0.00s    rss 2,372 MB
INFO vlsi_viewer.metal: metal: 112884147 shape(s) measured and handed to the rasteriser
INFO vlsi_viewer.metal: metal: 108844474 via point(s) omitted (no wire area)
INFO vlsi_viewer.metal: metal: 565424 non-preferred jog(s) shorter than a tracks pitch dropped
INFO vlsi_viewer.metal: metal: 21175654 VIRTUAL DEF connection(s) kept as connections (not metal, no area)
INFO vlsi_viewer.metal: metal: 86772912 shape(s) on layers outside the requested range were skipped
INFO vlsi_viewer.metal: metal: shapes per layer
  layer  dir        usable         shapes     area um2     util
  M2     VERTICAL   yes        56,409,930     383287.9   35.2 %
  M3     HORIZONTAL   yes        34,565,130     475474.8   43.5 %
  M4     VERTICAL   yes         6,093,689     464912.6   38.8 %
  M5     HORIZONTAL   yes         4,128,966     618479.9   49.9 %
  M6     VERTICAL   yes         3,311,556     526935.1   42.5 %
  M7     HORIZONTAL   yes         2,397,727     559372.3   45.1 %
  M8     VERTICAL   yes         1,894,029     397525.9   32.1 %
  FM1    HORIZONTAL   yes         1,839,993     477524.3   38.6 %
  FM2    VERTICAL   yes         1,319,153     363602.2   29.3 %
  B1     HORIZONTAL   yes           567,716     629250.1   50.8 %
  B2     VERTICAL   yes           353,528     611204.6   49.3 %
  layer         vias          jogs     diagonals        signal
  M2       50,203,793            0             0     52,866,371
  M3       29,985,644            0             0     29,842,206
  M4       12,716,743            0             0      6,078,076
  M5        5,864,061            0             0      4,098,823
  M6        2,743,768           10             0      2,910,351
  M7        2,025,891          431             0      1,999,731
  M8        1,728,044           90             0      1,431,532
  FM1       1,476,931       198,686             0      1,148,301
  FM2         982,610       144,091             0        973,593
  B1          789,625       128,809             0        564,100
  B2          327,364        93,307             0        353,087
INFO vlsi_viewer.metal: metal: skipped outside the layer range: M1 86.8 M
INFO vlsi_viewer.metal: metal-summary: run      {'design': 'lx956c_ioe', 'die_um': [1060.2, 1226.64], 'grid': [123, 107], 'grid_size_um': 10.0, 'version': '0.1.0'}
INFO vlsi_viewer.metal: metal-summary: params   {'macro_block_layers': 4, 'max_layer': 12, 'min_layer': 2, 'min_segment': null, 'top': null}
INFO vlsi_viewer.metal: metal-summary: inputs   {'defs': [{'mb': 2108.0, 'mtime': 1788556018, 'path': '/tmpdata/LinxCore950_PD_N3_t/user/l00922843/IOE/20.PR_Lx956_ioe/TAG0825_FC_inn25_seqMerge/DATAOUT/lx956c_ioe.def.gz'}], 'lefs': 221, 'tech_lefs': [{'mb': 0.2, 'mtime': 1771999514, 'path': '/tmpdata/LinxCore950_PD_N2_t/user/data/LX950/N43/lib/lef/HN3J30R_575GT228H_1P14M_4DPM_Q1_3Q2_2Q3_2B_2TMa_ALPA2_M3_P40_P42_V2_3mask_DTCO_L8_Vn.lef'}]}
INFO vlsi_viewer.metal: metal-summary: stages_s   {'blockage': 9.9, 'capacity': 0.76, 'cell-index': 12.11, 'components': 66.38, 'grids': 0.0, 'routing': 1696.7, 'start': 0.0, 'tech-lef': 0.02}
INFO vlsi_viewer.metal: metal-summary: shapes   {'degenerate': 0, 'diagonals': 0, 'emitted': 112884147, 'filtered': 86772912, 'jogs': 565424, 'polygon_edges': 0, 'total': 330239881, 'unknown': 0, 'usable': 0, 'vias': 108844474, 'virtual': 21175654}
INFO vlsi_viewer.metal: metal-summary: input_text   {'forms': 249067809, 'layers_used': 12, 'lines': 284908024, 'points': 373423631, 'points_max': 2, 'rects': 81172072, 'statement_chars_max': 4979560694, 'statement_lines_max': 58549358}
INFO vlsi_viewer.metal: metal-summary: layer M2         {'area_um2': 383287.875, 'degenerate': 0, 'diagonals': 0, 'direction': 'VERTICAL', 'jogs': 0, 'name': 'M2', 'pitch_um': 0.038, 'power': 3543559, 'shapes': 56409930, 'signal': 52866371, 'unusable': 0, 'usable': true, 'util': 0.35215, 'vias': 50203793, 'width_um': 0.019}
INFO vlsi_viewer.metal: metal-summary: layer M3         {'area_um2': 475474.75, 'degenerate': 0, 'diagonals': 0, 'direction': 'HORIZONTAL', 'jogs': 0, 'name': 'M3', 'pitch_um': 0.04, 'power': 4722924, 'shapes': 34565130, 'signal': 29842206, 'unusable': 0, 'usable': true, 'util': 0.43494, 'vias': 29985644, 'width_um': 0.02}
INFO vlsi_viewer.metal: metal-summary: layer M4         {'area_um2': 464912.562, 'degenerate': 0, 'diagonals': 0, 'direction': 'VERTICAL', 'jogs': 0, 'name': 'M4', 'pitch_um': 0.044, 'power': 15613, 'shapes': 6093689, 'signal': 6078076, 'unusable': 0, 'usable': true, 'util': 0.38757, 'vias': 12716743, 'width_um': 0.024}
INFO vlsi_viewer.metal: metal-summary: layer M5         {'area_um2': 618479.875, 'degenerate': 0, 'diagonals': 0, 'direction': 'HORIZONTAL', 'jogs': 0, 'name': 'M5', 'pitch_um': 0.076, 'power': 30143, 'shapes': 4128966, 'signal': 4098823, 'unusable': 0, 'usable': true, 'util': 0.49926, 'vias': 5864061, 'width_um': 0.038}
INFO vlsi_viewer.metal: metal-summary: layer M6         {'area_um2': 526935.062, 'degenerate': 0, 'diagonals': 0, 'direction': 'VERTICAL', 'jogs': 10, 'name': 'M6', 'pitch_um': 0.076, 'power': 401205, 'shapes': 3311556, 'signal': 2910351, 'unusable': 0, 'usable': true, 'util': 0.42486, 'vias': 2743768, 'width_um': 0.038}
INFO vlsi_viewer.metal: metal-summary: layer M7         {'area_um2': 559372.312, 'degenerate': 0, 'diagonals': 0, 'direction': 'HORIZONTAL', 'jogs': 431, 'name': 'M7', 'pitch_um': 0.076, 'power': 397996, 'shapes': 2397727, 'signal': 1999731, 'unusable': 0, 'usable': true, 'util': 0.45419, 'vias': 2025891, 'width_um': 0.038}
INFO vlsi_viewer.metal: metal-summary: layer M8         {'area_um2': 397525.938, 'degenerate': 0, 'diagonals': 0, 'direction': 'VERTICAL', 'jogs': 90, 'name': 'M8', 'pitch_um': 0.076, 'power': 462497, 'shapes': 1894029, 'signal': 1431532, 'unusable': 0, 'usable': true, 'util': 0.32059, 'vias': 1728044, 'width_um': 0.038}
INFO vlsi_viewer.metal: metal-summary: layer FM1        {'area_um2': 477524.281, 'degenerate': 0, 'diagonals': 0, 'direction': 'HORIZONTAL', 'jogs': 198686, 'name': 'FM1', 'pitch_um': 0.096, 'power': 691692, 'shapes': 1839993, 'signal': 1148301, 'unusable': 0, 'usable': true, 'util': 0.38573, 'vias': 1476931, 'width_um': 0.048}
INFO vlsi_viewer.metal: metal-summary: layer FM2        {'area_um2': 363602.2, 'degenerate': 0, 'diagonals': 0, 'direction': 'VERTICAL', 'jogs': 144091, 'name': 'FM2', 'pitch_um': 0.096, 'power': 345560, 'shapes': 1319153, 'signal': 973593, 'unusable': 0, 'usable': true, 'util': 0.29315, 'vias': 982610, 'width_um': 0.048}
INFO vlsi_viewer.metal: metal-summary: layer B1         {'area_um2': 629250.1, 'degenerate': 0, 'diagonals': 0, 'direction': 'HORIZONTAL', 'jogs': 128809, 'name': 'B1', 'pitch_um': 0.126, 'power': 3616, 'shapes': 567716, 'signal': 564100, 'unusable': 0, 'usable': true, 'util': 0.50789, 'vias': 789625, 'width_um': 0.062}
INFO vlsi_viewer.metal: metal-summary: layer B2         {'area_um2': 611204.625, 'degenerate': 0, 'diagonals': 0, 'direction': 'VERTICAL', 'jogs': 93307, 'name': 'B2', 'pitch_um': 0.126, 'power': 441, 'shapes': 353528, 'signal': 353087, 'unusable': 0, 'usable': true, 'util': 0.49346, 'vias': 327364, 'width_um': 0.062}
INFO vlsi_viewer.metal: metal-summary: blockage      {'fallback_cells': 0, 'fallback_layer_names': ['M2', 'M3', 'M4'], 'fallback_layers': 4, 'ignored_cells': [], 'ignored_layers': {}, 'obs_cells': 89, 'obs_layers': [0, 1, 2], 'unknown_layers': {}}
INFO vlsi_viewer.metal: metal-summary: filtered_layers {'filtered_layers': ['ALPA', 'M1', 'TM1', 'TM2'], 'layers_not_in_tech': []}
INFO vlsi_viewer.metal: metal-summary: memory        {'gc_counts': [21209, 1928, 231], 'gc_s': 4.27, 'peak_rss_mb': 5056, 'rss_mb': 2372}
INFO vlsi_viewer.metal: metal-summary: warnings      ['1 cell type(s) are neither in the LEF nor a block, so they contribute no footprint: tensor_remote_npnpv100', '187 cell(s) carry signal wire on a layer a macro obstructs there, so their utilisation is not a congestion reading']
WARNING vlsi_viewer.cli: metal: 1 cell type(s) are neither in the LEF nor a block, so they contribute no footprint: tensor_remote_npnpv100
WARNING vlsi_viewer.cli: metal: 187 cell(s) carry signal wire on a layer a macro obstructs there, so their utilisation is not a congestion reading
StandardPaths: XDG_RUNTIME_DIR points to non-existing path '/tmp/l00922843', please create it with 0700 permissions.
```

### Snapshot 6 — job statistics (scheduler page; top of the page scrolled off)

```
                                  root.long
CWD_PATH                /tmpdata/LinxCore950_PD_N3_t/user/l00922843/design brower
COMMAND                 venv/bin/python3 VLSI_design_browser-master/main.py metal --def /tmpdata/LinxCore950_PD_N3_t/user/l00922843/IOE/20.PR_Lx956_ioe/TAG0825_FC_inn25_seqMerge/DATAOUT/lx956c_ioe.def.gz --lef lefs/ --tech-lef /tmpdata/LinxCore950_PD_N2_t/user/data/LX950/N43/lib/lef/HN3J30R_575GT228H_1P14M_4DPM_Q1_3Q2_2Q3_2B_2TMa_ALPA2_M3_P40_P42_V2_3mask_DTCO_L8_Vn.lef --min-layer 2 --max-layer 12 --jobs 8
TASK_MAX_RETRY_CNT      0
REQ_TASK_LICENSE        -
TASK_TIMEOUT            0
STDERR_REDIRECT_PATH    append
STDERR_REDIRECT_TYPE    append
STDOUT_REDIRECT_PATH    append
STDOUT_REDIRECT_TYPE    append
RES_GROUP[0]:
    REPLICA             1
    TASK_LABELS         x86_64
    PREFER_NODES        -
    REQ_NODE_SELECT_POLICY -
    REQ_CPU             4
    REQ_MEM             20000
    REQ_GPU             0
TASK[0].JOB_ID          1649642129
TASK[0].TASK_NAME       rg0.0
TASK[0].PID             7633,7635,9733
TASK[0].EXEC_NODE       whalcld233-hs
TASK[0].ALLOC_CPU       4
TASK[0].ALLOC_MEM       20000
TASK[0].TASK_STATE      RUNNING
TASK[0].TASK_CURRENT_RETRY_TIMES 0
TASK[0].TASK_CURRENT_OPERATION EMPTY
TASK[0].TASK_INDEX      0
TASK[0].TRACE_MESSAGE:
    2026/09/16 18:42:35 : [JOB_ADD] Job 1649642129 is submitted by l00922843, job state is PENDING.
    2026/09/16 18:42:38 : [JOB_START] Job 1649642129 start message has been sent, job state is PENDING.
    2026/09/16 18:42:38 : [JOB_START_ACK] Job 1649642129 start message has been received by agent whalcld233-hs.
    2026/09/16 18:42:39 : [JOB_EXECUTION] Job 1649642129 state is from PENDING to RUNNING, execution path: /tmpdata/LinxCore950_PD_N3_t/user/l00922843/design browser.
    2026/09/16 18:42:39 : [JOB_UPDATE] Update job 1649642129 wall_clock_limit from 0(s) to 2592000(s).
TASK[0].EFF_NODE_SELECT_POLICY cpu
TASK[0].USER_CPU_TIME   7974
TASK[0].SYSTEM_CPU_TIME 133
TASK[0].MEMSW_MAX       554803
TASK[0].MEM_MAX         554803
TASK[0].MEM_AVG         23475
TASK[0].MEM_REAL        239
TASK[0].RSS             195
TASK[0].CACHE           43
TASK[0].SWAP            0
TASK[0].MTHREADS        0
TASK[0].MRUN_TIME       2561
TASK[0].SSTOPPED_TIME   0
TASK[0].CPU_UTIL_AVG(%) 316
TASK[0].CPU_UTIL_RECENT(%) 0
TASK[0].GPU_SM_UTIL_AVG(%) -
TASK[0].GPU_SM_UTIL_RECENT(%) -
TASK[0].HWTREADS        -
TASK[0].TASK_CREATE_TIME 2026/09/16 18:42:35
TASK[0].TASK_START_TIME 2026/09/16 18:42:39
TASK[0].TASK_LAST_MODIFIED_TIME -
TASK[0].TASK_END_TIME   -
```

## 2. Key numbers (from the log lines as captured)

### Timeline

| event | time |
|---|---|
| submitted (PENDING) | 18:42:35.554 |
| RUNNING on `whalcld233-hs` | 18:42:39.014 — queue wait **~3.5 s** |
| stage `components` done (DEF pass 1, 3,355,697 instances; parse 36.3509 s, 5,819,128 lines) | +66.38 s |
| LEF parse done (221 files, 11.506 s) → stage `cell-index` (17,385 cells) | +12.11 s |
| stage `capacity` done (123×107 grid @ 10 um) | +0.76 s |
| stage `blockage` done (89 OBS macros) | +9.90 s |
| stage `routing` done (8 workers) | **+1,696.70 s** |
| stage `grids` done | +0.00 s |
| **job finished ≈ 19:12** | **total ≈ 1,785.9 s ≈ 29.8 min** |

### Where the time went

From the `stages_s` object of the `metal-summary` line (sum 1,785.87 s of
compute time):

| stage | seconds | share |
|---|---|---|
| `tech-lef` | 0.02 | 0.00 % |
| `components` (DEF pass 1) | 66.38 | 3.72 % |
| `cell-index` (LEF pass) | 12.11 | 0.68 % |
| `capacity` | 0.76 | 0.04 % |
| `blockage` | 9.90 | 0.55 % |
| `routing` (DEF pass 2, 8 workers) | **1,696.70** | **95.01 %** |
| `grids` | 0.00 | 0.00 % |

Routing is still the whole job. vs 09-15 (same 8 workers): routing
1,780.64 s → 1,696.70 s (−4.7 %), total compute 1,846.44 s → 1,785.87 s
(−3.3 %) — the routing gain was partly eaten by a slower components pass
(44.19 s → 66.38 s).

### Per-worker reads observed

Worker tags are visible this run, so the attribution that was guesswork on
09-15 is direct:

- **Normal slices:** ~1.8–2.0 M lines at ~60–67 k lines/s, each finishing in
  ~33–47 s (a few short ones at 12–14 s).
- **Long slices captured:** `[w1]` 19,849,157 lines (NETS 35,617/38,904) →
  **364.2037 s**; `[w7]` 19,901,290 lines (NETS 34,785/38,905) →
  **371.3069 s**; `[w2]` SPECIALNETS slice → **909.7829 s**, the largest
  single read captured. `[w3]`'s 17.9–18.1 M-line SPECIALNETS slice is
  mid-read at "6 min elapsed" (its own End line is not in the captured
  windows); `[w1]` also shows a 60,554,368-line NETS slice and `[w2]` a
  59,553,368-line one at "15 min elapsed".
- **SPECIALNETS slices read fast at first:** `[w2]` reports 27,898,515 lines
  at 929,949 lines/s and 58,035,173 at 967,252 lines/s within its first minute,
  then the same slice crawls at ~66 k lines/s up to 909.78 s (58,681,090
  lines by the 15-minute heartbeat — i.e. the last ~650 k lines took the
  remaining ~14 min). The burst-then-crawl pattern is not explained by
  anything in the log.
- The stage total (1,696.70 s) is consistent with each worker serially
  chaining ~10–20 slices of 12–910 s; `[w2]`'s visible share alone already
  sums past 1,100 s.
- Heartbeat net denominators are 38,905 / 50,000 (38,904 in two lines) — the
  split is by net count, as on 09-15.

### Shape counters — and a 2,730 residual

| class | count |
|---|---|
| emitted (measured, handed to the rasteriser) | 112,884,147 |
| filtered (M1, outside the requested range) | 86,772,912 |
| vias (points omitted, no wire area) | 108,844,474 |
| jogs (non-preferred, shorter than a track pitch) | 565,424 |
| virtual (kept as connections, not metal) | 21,175,654 |
| degenerate / diagonals / polygon_edges / unknown / usable | 0 each |
| **total (as printed)** | **330,239,881** |

The class counters sum to 330,242,611 — **2,730 more** than the printed
total, which is printed identically in two places (the `stage routing` line
and the summary's `total`). The same 2,730 appears on the other side: the
per-layer `shapes` column sums to 112,881,417, which is 2,730 **less** than
the printed `emitted` (112,884,147, also printed twice: describe line and
summary). The per-layer vias column sums to 108,844,474 and the jogs column
to 565,424 — both exact. So either a transcription is off by 2,730 somewhere,
or the build counts 2,730 emitted shapes that no layer row can hold (the
`e34c6dd` commit claims the per-layer sums equal the global counters class by
class, so a real residual would be a finding).

### Per-layer numbers (from the two tables)

| layer | dir | shapes | area um² | util | vias | jogs | signal | power | pitch um | width um |
|---|---|---|---|---|---|---|---|---|---|---|
| M2 | V | 56,409,930 | 383,287.9 | 35.2 % | 50,203,793 | 0 | 52,866,371 | 3,543,559 | 0.038 | 0.019 |
| M3 | H | 34,565,130 | 475,474.8 | 43.5 % | 29,985,644 | 0 | 29,842,206 | 4,722,924 | 0.04 | 0.02 |
| M4 | V | 6,093,689 | 464,912.6 | 38.8 % | 12,716,743 | 0 | 6,078,076 | 15,613 | 0.044 | 0.024 |
| M5 | H | 4,128,966 | 618,479.9 | 49.9 % | 5,864,061 | 0 | 4,098,823 | 30,143 | 0.076 | 0.038 |
| M6 | V | 3,311,556 | 526,935.1 | 42.5 % | 2,743,768 | 10 | 2,910,351 | 401,205 | 0.076 | 0.038 |
| M7 | H | 2,397,727 | 559,372.3 | 45.1 % | 2,025,891 | 431 | 1,999,731 | 397,996 | 0.076 | 0.038 |
| M8 | V | 1,894,029 | 397,525.9 | 32.1 % | 1,728,044 | 90 | 1,431,532 | 462,497 | 0.076 | 0.038 |
| FM1 | H | 1,839,993 | 477,524.3 | 38.6 % | 1,476,931 | 198,686 | 1,148,301 | 691,692 | 0.096 | 0.048 |
| FM2 | V | 1,319,153 | 363,602.2 | 29.3 % | 982,610 | 144,091 | 973,593 | 345,560 | 0.096 | 0.048 |
| B1 | H | 567,716 | 629,250.1 | 50.8 % | 789,625 | 128,809 | 564,100 | 3,616 | 0.126 | 0.062 |
| B2 | V | 353,528 | 611,204.6 | 49.3 % | 327,364 | 93,307 | 353,087 | 441 | 0.126 | 0.062 |

All 11 layers print `usable: true` / `unusable: 0` (the new per-layer schema
has both a `usable` bool and an `unusable` count; the 09-15 summary only had
`unusable` as a bool, true for M3/M5/M6/M7/B1/B2). Jogs are concentrated on
FM1/FM2/B1/B2 (198,686 / 144,091 / 128,809 / 93,307 — all of the 565,424);
M2 and M3 carry ~70 % of the measured shapes and ~76 % of the vias.

### Job statistics at capture

| field | value |
|---|---|
| JOB_ID / TASK_NAME | 1649642129 / rg0.0 |
| EXEC_NODE / ALLOC | `whalcld233-hs`, 4 CPU / 20,000 (mem) |
| PIDs | 7633, 7635, 9733 (main + worker group) |
| state at capture | **RUNNING**, TASK_END_TIME `-`, TASK_LAST_MODIFIED `-` |
| MRUN_TIME | 2,561 s (≈ 42.7 min; start 18:42:39 → ≈ 19:25:20) |
| USER / SYSTEM CPU | 7,974 s / 133 s → average ≈ 3.15 cores (CPU_UTIL_AVG 316 %) |
| MEM_MAX / MEMSW_MAX | 554,803 (units not stated on the page; ≈ 542 MB if KB) |
| MEM_AVG / MEM_REAL / RSS / CACHE / SWAP | 23,475 / 239 / 195 / 43 / 0 |
| wall_clock_limit | raised 0 s → 2,592,000 s (30 days) at JOB_UPDATE |

The page had not yet recorded the end state when captured: MRUN_TIME 2,561 s
is ≈ 13 min **after** the last log line (compute done ≈ 19:12), and the end
fields are blank — either the job was still winding down (the XDG
StandardPaths line prints at the very end) or the page was stale.

### Comparison vs the 09-15 run

| | 09-15 (job 1647183354) | 09-16 (job 1649642129) |
|---|---|---|
| build | pre-`e34c6dd` | `e34c6dd` (09-16 00:10) |
| host | `metalcd233-hs` | `whalcld233-hs` |
| DEF mtime | 1,788,556,810 | 1,788,556,018 (13 min older file) |
| queue wait | ~3 s | ~3.5 s |
| components | 44.19 s | 66.38 s |
| cell-index (`lef-index`) | 11.24 s | 12.11 s |
| blockage | 9.62 s | 9.90 s |
| routing (8 workers) | 1,780.64 s | **1,696.70 s** (−4.7 %) |
| total compute | 1,846.44 s | **1,785.87 s** (−3.3 %) |
| total shapes | 249,067,809 | 330,239,881 (**+81,172,072** = exactly `rects`) |
| points | 373,423,631 | 373,423,631 (identical) |
| emitted / measured | 56,375,666 | 112,884,147 |
| vias omitted | 108,844,474 | 108,844,474 (identical) |
| jogs dropped | 11,796,228 | 565,424 |
| 45-degree diagonals | 8,777,752 | 0 (counter no longer reported) |
| filtered | 72,051,441 | 86,772,912 |
| GC | 3.72 s, [21,209, 1,928, 231] | 4.27 s, [21,209, 1,928, 231] |
| rss / peak rss | 2,372 / 5,056 MB | 2,372 / 5,056 MB (identical) |

The VIRTUAL fix shows up directly: the old build read `VIRTUAL ( x y )` as a
via name, so its point became a wire corner — the 11.8 M "jogs" and 8.8 M
"45-degree shapes" of 09-15 largely collapse to 565,424 jogs / 0 diagonals,
and 21,175,654 VIRTUAL connections are now kept as connections instead of
metal. The +81,172,072 total shapes is exactly the inline `RECT` forms the new
build measures rather than drops.

## 3. Transcription notes and facts worth verifying

- The `[wN]` worker tags on the heartbeat lines are printed by the workers in
  the new build, so they are genuine attribution — but in the dense
  interleaving of snapshots 3–4 some tags and line counts are best readings;
  one line in snapshot 4 reads as `[w1] Read DEF in 46.9205s` with no line
  count and may be a torn or misread line.
- `input_text.rects` (81,172,072) and `statement_chars_max`
  (4,979,560,694) are the two digit strings I could not fully resolve in the
  screenshot; the 81,172,072 figure is independently confirmed by the
  shape-count difference vs 09-15. `statement_lines_max` is 58,549,358 — a
  single statement of ~58.5 M lines (~4.98 GB, ~85 chars/line) is the giant
  SPECIALNETS statement the `[w2]`/`[w1]` 58–60 M-line slices are reading.
  Note: the 09-15 build's `statement_chars_max` was 58,549,358 — the same
  number this run reports as `statement_lines_max`; the new build splits the
  two metrics.
- The JSON field names in the summary lines were checked against
  `vlsi_viewer/metal.py` at `e34c6dd` (`SUMMARY_SECTIONS`, `_file_note`):
  sections are `run / params / inputs / stages_s / shapes / input_text /
  layer <N> / blockage / filtered_layers / memory / warnings`; the file note
  keys are `path / mb / mtime` (the 09-15 summary's `lines`/`mftime`/`lefts`
  spellings are gone). Where the screenshot and the repo disagree on a
  spelling (e.g. `lefs` vs the old `lefts`), the repo spelling is used.
- The 2,730 residual between the printed class counters / per-layer shapes sum
  and the printed totals (see "Shape counters") — verify on the build.
- The scheduler page's MEM_MAX 554,803 does not reconcile with the tool's own
  `peak_rss_mb` 5056 (≈ 5,177,000 KB) under any obvious unit reading —
  different measurement scope (main process vs process tree) or an unmarked
  unit; MEM_AVG 23,475 / MEM_REAL 239 / RSS 195 have the same problem.
- The stats page shows `design brower` (CWD_PATH) and `design browser`
  (execution path) — the directory name is spelled inconsistently in the
  page's own fields.
- Host is `whalcld233-hs` this run vs `metalcd233-hs` on 09-15; the ~4.7 %
  routing delta may be node-dependent rather than build-dependent.
- The components pass was slower (66.38 s vs 44.19 s) even though its
  pass-1 DEF parse was faster (36.3509 s vs 26.9251 s) — the instance
  conversion after the parse is what moved.
- `XDG_RUNTIME_DIR points to non-existing path '/tmp/l00922843'` is new in
  the captured tail (StandardPaths at shutdown); 09-15's log did not show it.
- The stage is named `cell-index` in this build's log (09-15 printed
  `lef-index`); the summary key matches (`cell-index`).

## 4. GUI snapshots — the map as rendered (snapshots 7–8)

Two screenshots of the metal map in the "VLSI Hierarchy Analyzer" GUI, titled
`VLSI Hierarchy Analyzer (on wha_lcd233_hs)` — the job's own node
(`whalcld233-hs`; the title bar blurs the l/c in the font). The status bar in
both reads `Metal mode · 123×107 grid @ 10 um · die 1060.2×1226.64 um ·
layers M2..B2 (11 of 15) · top lx956c_ioe`, and the `U` column of the
"Routing layers" table matches the 09-16 `metal-summary` utilisations to the
third decimal for all 11 layers (0.352 / 0.435 / 0.388 / 0.499 / 0.425 / 0.451
/ 0.321 / 0.386 / 0.293 / 0.508 / 0.493) — this GUI is displaying the map
built by job 1649642129. Snapshot 7 shows the **All V** subset (M6, M8, FM2,
B2 checked), peak 0.744, hovering grid cell (39,48); snapshot 8 shows the
**All H** subset (M5, M7, FM1, B1 checked), peak 0.802, hovering cell (71,66).

### Snapshot 7 — All V view (M6, M8, FM2, B2), peak 0.744

```
Title:  VLSI Hierarchy Analyzer (on wha_lcd233_hs)
Toolbar: Min: 0.000   Max: 1.000   [Auto] [Fit]   peak 0.744   full = 1.000

Cell detail
  cell(39,48) x=395 y=485
  layer   D/C      U
  M6 *    60.6/100  0.606
  M8      49.1/100  0.491
  FM2     36.1/100  0.361
  B2      56.8/100  0.568
  sum(D)/sum(C) = 0.5066
  203/400
  H max 0.000   V max 0.606
  escapable
  capacity: less each macro's own OBS

Net class:  Signal + power
Routing layers (checked: M6, M8, FM2, B2)
  layer   W/S/P            dir    U
  M2      0.019/0.019/0.038  V   0.352
  M3      0.02/0.02/0.04     H   0.435
  M4      0.024/0.02/0.044   V   0.388
  M5      0.038/0.038/0.076  H   0.499
  M6  [v] 0.038/0.038/0.076  V   0.425
  M7      0.038/0.038/0.076  H   0.451
  M8  [v] 0.038/0.038/0.076  V   0.321
  FM1     0.048/0.048/0.096  H   0.386
  FM2 [v] 0.048/0.048/0.096  V   0.293
  B1      0.062/0.064/0.126  H   0.508
  B2  [v] 0.062/0.064/0.126  V   0.493

Status bar:  Metal mode · 123×107 grid @ 10 um · die 1060.2×1226.64 um ·
             layers M2..B2 (11 of 15) · top lx956c_ioe
             x=390.2  y=486.92  G:B2,FM2,M6,M8[48,39] = 0.507
```

Map (V layers): die filled mostly green/cyan at 10 um cells; the leftmost
~10 columns form a blue low-density band with a vertical-stripe pattern;
yellow-green hot spots are scattered through the central area, the brightest
in the middle and lower-left, no red — the 0.744 peak shows as yellow-orange.
The white die outline is irregular: a cut-in at the top-right corner, a
stepped bottom-left, and a narrow tab running down at the lower left; outside
the outline is black.

### Snapshot 8 — All H view (M5, M7, FM1, B1), peak 0.802

```
Title:  VLSI Hierarchy Analyzer (on wha_lcd233_hs)
Toolbar: Min: 0.000   Max: 1.000   [Auto] [Fit]   peak 0.802   full = 1.000

Cell detail
  cell(71,66) x=715 y=665
  layer   D/C      U
  M5      75.1/100  0.751
  M7      71.6/100  0.716
  FM1     70.6/100  0.706
  B1 *    84.5/100  0.845
  sum(D)/sum(C) = 0.7549
  302/400
  H max 0.845   V max 0.000
  escapable
  capacity: less each macro's own OBS

Net class:  Signal + power
Routing layers (checked: M5, M7, FM1, B1)
  layer   W/S/P            dir    U
  M2      0.019/0.019/0.038  V   0.352
  M3      0.02/0.02/0.04     H   0.435
  M4      0.024/0.02/0.044   V   0.388
  M5  [v] 0.038/0.038/0.076  H   0.499
  M6      0.038/0.038/0.076  V   0.425
  M7  [v] 0.038/0.038/0.076  H   0.451
  M8      0.038/0.038/0.076  V   0.321
  FM1 [v] 0.048/0.048/0.096  H   0.386
  FM2     0.048/0.048/0.096  V   0.293
  B1  [v] 0.062/0.064/0.126  H   0.508
  B2      0.062/0.064/0.126  V   0.493

Status bar:  Metal mode · 123×107 grid @ 10 um · die 1060.2×1226.64 um ·
             layers M2..B2 (11 of 15) · top lx956c_ioe
             x=715.18  y=668.08  G:B1,FM1,M5,M7[66,71] = 0.755
```

Map (H layers): much hotter than the V view. A horizontal orange-red band runs
along the top of the die; the lower-right quadrant is a large orange/red
mass with a red core (the 0.802 peak region); the left edge stays a cyan/blue
band; the upper-left is green/cyan. Same die outline as snapshot 7.

### Reading the GUI numbers

- `U` in the layer table is the layer-average utilisation — identical to the
  09-16 summary's per-layer `util` (this is how the two screenshots are tied
  to job 1649642129's map).
- `W/S/P` = width/spacing/pitch. The width and pitch columns equal the
  summary's `width_um`/`pitch_um` for all 11 layers; the middle (spacing)
  column differs from width on M4 (0.02 vs 0.024) and B1/B2 (0.064 vs 0.062).
- The Cell detail's per-layer `D/C` (density/capacity, /100) is the **local**
  utilisation of the hovered cell, not the layer average: B1 is 0.845 in cell
  (71,66) vs 0.508 on average, M5 0.751 vs 0.499. The `*` marks the hottest
  layer of the displayed subset (M6 in the V view, B1 in the H view).
- `sum(D)/sum(C)` = total density over total capacity across the four
  displayed layers: 203/400 = 0.5066 (V view) and 302/400 = 0.7549 (H view) —
  the status bar's `G:…[y,x] = 0.507 / 0.755` is that same sum rounded. The
  cell header is (x, y) in grid cells (die um = cell × 10 + 5); the status
  bar's `[48,39]` / `[66,71]` are [row y, column x].
- `peak` is the maximum of the currently displayed map (0.744 V-subset,
  0.802 H-subset); `full = 1.000` is the fixed top of the colour scale, with
  Min/Max at 0.000/1.000. The H layers peak 0.058 higher than the V layers —
  the hot band/mass in the H view has no counterpart in the V view.
- `H max` / `V max` in the Cell detail are the direction maxima within the
  displayed class (0.000 for the un-displayed direction).
- `escapable` is printed for both hovered cells; its meaning is not defined
  anywhere in this record (a GUI cell flag).
- `capacity: less each macro's own OBS` — the cell capacity shown is after
  subtracting each macro's own OBS, consistent with the run's blockage stage
  (89 OBS macros on layers 0–2, fallback layers M2/M3/M4).
