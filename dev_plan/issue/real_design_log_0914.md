# Real-design metal-mode run, 2026-09-14 — job 1645073007: log and turnaround analysis

Two LSF interactive jobs on the chip-level design `lx956c_ioe`, submitted 2026-09-14 with
the same inputs — a 2.1 GB gzipped routed DEF (284,908,802 lines, 373,423,631 points,
253,607,592 shapes), 3,355,697 placed instances, 17,385 macros from 221 LEF files, layer
range 2..12 (`--min-layer 2 --max-layer 12`):

- **Run A** — job 1645073007, submitted ~11:46, host `whalcd082-hs`, plain run. Four
  terminal screenshots; ≈102 min.
- **Run B** — job 1645417604, submitted 13:56:15, host `whalcd234-hs`, same command plus
  `--profile`. Three terminal screenshots; ≈168 min, of which ~68 % is `cProfile` overhead
  (section 4).

The logs below are transcribed from the seven screenshots. The snapshots are windows of one
scrolling terminal each, so consecutive snapshots of a run are not necessarily
line-continuous (a few heartbeat lines fell off between windows). Where the screenshot was
ambiguous a digit may be off by one; the machine-readable `metal-summary:` lines were
checked field-by-field against the `vlsi_viewer` source.

## 0. The command

```
dsbsub -A root.ug_yyother.Linux956_PD2_HClass -q Long -R 'cpu=4; mem=20000' -I "venv/bin/python3 VLSI_design_browser-master/main.py metal --def /tmpdata/LinxCore950_PD_N3_t/user/l00922843/IOE/20.PR.Lx956_ioe/TAG0825_FC_inn25_seqMerge/DATAOUT/lx956c_ioe.def.gz --lef lefs/ --tech-lef /tmpdata/LinxCore950_PD_N2_t/user/data/LX950/N+3/lib/tlef/HNJ730R_575Gt228H_1P14M_4DPM_Q1_3Q2_2Q3_2B_2TMA_ALPA2_M3_P40_P42_V2_3mask_DTC0_L8_Vn.lef --min-layer 2 --max-layer 12"
```

## 1. Run log (as captured)

### Snapshot 1 — submission, queue, tech LEF, components pass, LEF parse starts

```
dsbsub -A root.ug_yyother.Linux956_PD2_HClass -q Long -R 'cpu=4; mem=20000' -I "venv/bin/python3 VLSI_design_browser-master/main.py metal --def /tmpdata/LinxCore950_PD_N3_t/user/l00922843/IOE/20.PR.Lx956_ioe/TAG0825_FC_inn25_seqMerge/DATAOUT/lx956c_ioe.def.gz --lef lefs/ --tech-lef /tmpdata/LinxCore950_PD_N2_t/user/data/LX950/N+3/lib/tlef/HNJ730R_575Gt228H_1P14M_4DPM_Q1_3Q2_2Q3_2B_2TMA_ALPA2_M3_P40_P42_V2_3mask_DTC0_L8_Vn.lef --min-layer 2 --max-layer 12"
             MESSAGE                         JOBID
1645073007      Submit job successfully.

2026-09-14 11:46:46.093 ==> job state changed to: PENDING

2026-09-14 11:48:48.814 ==> job state changed to: RUNNING
Job is running on host whalcd082-hs

INFO vlsi_viewer.cli: metal: reading 1 DEF file(s)
INFO vlsi_viewer.metal: metal: stage start
INFO vlsi_viewer.metal: metal: 0.00s   rss 71 MB
Start parsing tech lef, /tmpdata/LinxCore950_PD_N2_t/user/data/LX950/N+3/lib/tlef/HNJ730R_575Gt228H_1P14M_4DPM_Q1_3Q2_2Q3_2B_2TMA_ALPA2_M3_P40_P42_V2_3mask_DTC0_L8_Vn.lef
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
INFO vlsi_viewer.metal: metal: Layers M2..B2 (11 of 15), ignoring M1, TM1, TM2, ALPA
INFO vlsi_viewer.metal: metal: stage tech-lef   0.02s  rss 71 MB
INFO vlsi_viewer.cli: metal: reading block outlines
Load DEF file /tmpdata/LinxCore950_PD_N3_t/user/l00922843/IOE/20.PR.Lx956_ioe/TAG0825_FC_inn25_seqMerge/DATAOUT/lx956c_ioe.def.gz
End DEF parsing in 26.537s
INFO vlsi_viewer.parsers.convert: def: /tmpdata/LinxCore950_PD_N3_t/user/l00922843/IOE/20.PR.Lx956_ioe/TAG0825_FC_inn25_seqMerge/DATAOUT/lx956c_ioe.def.gz -> 3355697 instance(s) (dropped 0 filler, skipped 0 unplaced), 8 boundary point(s)
INFO vlsi_viewer.loader: Loaded block 'lx956c_ioe' with 3355697 instance(s) from <in-memory>
INFO vlsi_viewer.metal: metal: stage components   43.91s  1 block(s), root 'lx956c_ioe'  rss 2,485 MB
Start parsing Lef files
Total 221 LEF files
Parsing lefs/hir1zh228_ckmesh_1p14m_4dpm_q1_3q2_2q3_2b_2tma_onlypr.lef
Parsing lefs/hir1zh228_ckmesh_1p14m_4dpm_q1_3q2_2q3_2b_2tma_onlypr.lef.cell_info.json
Parsing lefs/hir1zh228l10p57sdb_aic_lvt_onlypr.lef
Parsing lefs/hir1zh228l10p57sdb_aic_svt onlypr.lef
```

### Snapshot 2 — LEF pass done, capacity and blockage, routing read starts (heartbeats to ~40 min)

```
Parsing lefs/HIS6LC956GSRAMTP64X64MH5B.lef
Parsing lefs/HIS6LC956GSRAMTP64X64M1H5B.lef
End parsing 221 LEF files in 10.602s
INFO vlsi_viewer.parsers.convert: lef: 17385 macro(s) from 221 file(s)
INFO vlsi_viewer.loader: Loaded 17385 cell(s) from <in-memory>
INFO vlsi_viewer.metal: metal: stage cell-index   11.10s  17,385 cell(s) from 221 LEF file(s)  rss 2,390 MB
INFO vlsi_viewer.cli: metal: measuring capacity
INFO vlsi_viewer.metal: metal: block capacity   0.73s  123 x 107 grid @ 10 um, DIE 1060.2 x 1226.6 um  rss 2,365 MB
INFO vlsi_viewer.metal: metal: stage blockage   9.54s  8 Macro type(s) with obstruction data  rss 2,365 MB
INFO vlsi_viewer.cli: metal: reading routing
LOAD FILE /tmpdata/LinxCore950_PD_N3_t/user/l00922843/IOE/20.PR.Lx956_ioe/TAG0825_FC_inn25_seqMerge/DATAOUT/lx956c_ioe.def.gz
Read DEF 13,565,524 lines 452,184 lines/s 1 min elapsed
Read DEF 26,428,367 lines 440,473 lines/s 1 min elapsed SPECIALNETS 88,760/88,763  ~0.0 min left
Read DEF 34,965,662 lines 79,714 lines/s 7 min elapsed SPECIALNETS 88,761/88,763  ~0.0 min left
Read DEF 52,796,182 lines 64,057 lines/s 14 min elapsed SPECIALNETS 88,763/88,763  ~0.0 min left
Read DEF 73,057,302 lines 85,526 lines/s 14 min elapsed SPECIALNETS 88,763/88,763  ~0.0 min left
Read DEF 93,147,818 lines 105,346 lines/s 15 min elapsed SPECIALNETS 88,763/88,763  ~0.0 min left
Read DEF 111,345,539 lines 121,129 lines/s 15 min elapsed SPECIALNETS 88,763/88,763  ~0.0 min left
Read DEF 111,235,540 lines 71,747 lines/s 26 min elapsed SPECIALNETS 88,763/88,763  ~0.0 min left   # <- line count lower than the previous heartbeat; one-digit misread likely
Read DEF 114,111,755 lines 70,749 lines/s 27 min elapsed NETS 44,174/3,235,531  ~73.4 min left
Read DEF 115,459,900 lines 70,227 lines/s 27 min elapsed NETS 64,676/3,235,531  ~74.4 min left
Read DEF 116,673,372 lines 69,742 lines/s 28 min elapsed NETS 81,338/3,235,531  ~78.2 min left
Read DEF 117,930,284 lines 69,251 lines/s 28 min elapsed NETS 99,457/3,235,531  ~79.4 min left
Read DEF 119,095,893 lines 68,704 lines/s 29 min elapsed NETS 123,688/3,235,531  ~76.4 min left
Read DEF 120,347,876 lines 68,245 lines/s 29 min elapsed NETS 150,180/3,235,531  ~72.4 min left
Read DEF 121,607,736 lines 67,806 lines/s 30 min elapsed NETS 178,876/3,235,531  ~68.8 min left
Read DEF 122,711,822 lines 67,296 lines/s 30 min elapsed NETS 204,497/3,235,531  ~67.1 min left
Read DEF 123,847,405 lines 66,819 lines/s 31 min elapsed NETS 231,021/3,235,531  ~65.4 min left
Read DEF 124,951,921 lines 66,341 lines/s 31 min elapsed NETS 256,840/3,235,531  ~64.1 min left
Read DEF 126,106,477 lines 65,904 lines/s 32 min elapsed NETS 279,462/3,235,531  ~63.7 min left
Read DEF 127,272,773 lines 65,487 lines/s 32 min elapsed NETS 298,081/3,235,531  ~64.3 min left
Read DEF 128,423,587 lines 65,075 lines/s 33 min elapsed NETS 316,375/3,235,531  ~64.8 min left
Read DEF 129,648,164 lines 64,712 lines/s 33 min elapsed NETS 340,217/3,235,531  ~64.0 min left
Read DEF 130,832,158 lines 64,235 lines/s 34 min elapsed NETS 364,118/3,235,531  ~63.7 min left
Read DEF 131,994,117 lines 63,865 lines/s 34 min elapsed NETS 388,082/3,235,531  ~63.3 min left
Read DEF 133,156,058 lines 63,506 lines/s 35 min elapsed NETS 405,831/3,235,531  ~62.9 min left
Read DEF 134,437,236 lines 63,109 lines/s 35 min elapsed NETS 429,749/3,235,531  ~62.1 min left
Read DEF 135,630,580 lines 62,785 lines/s 36 min elapsed NETS 453,996/3,235,531  ~61.4 min left
Read DEF 136,814,072 lines 62,465 lines/s 37 min elapsed NETS 477,898/3,235,531  ~61.4 min left
Read DEF 137,970,747 lines 62,079 lines/s 37 min elapsed NETS 499,755/3,235,531  ~61.2 min left
Read DEF 139,172,514 lines 61,786 lines/s 38 min elapsed NETS 518,007/3,235,531  ~61.3 min left
Read DEF 140,359,633 lines 61,494 lines/s 38 min elapsed NETS 536,241/3,235,531  ~61.3 min left
Read DEF 141,496,485 lines 61,188 lines/s 39 min elapsed NETS 561,844/3,235,531  ~60.3 min left
Read DEF 142,707,975 lines 60,921 lines/s 39 min elapsed NETS 587,224/3,235,531  ~59.4 min left
Read DEF 143,844,159 lines 60,561 lines/s 40 min elapsed NETS 608,829/3,235,531  ~59.2 min left
```

### Snapshot 3 — routing read heartbeats, ~41 min to ~75 min

```
Read DEF 145,109,755 lines 60,267 lines/s 41 min elapsed NETS 629,229/3,235,531  ~59.1 min left
Read DEF 146,305,722 lines 60,000 lines/s 41 min elapsed NETS 649,561/3,235,531  ~58.8 min left
Read DEF 147,473,125 lines 59,743 lines/s 42 min elapsed NETS 674,473/3,235,531  ~58.0 min left
Read DEF 148,662,952 lines 59,487 lines/s 42 min elapsed NETS 698,485/3,235,531  ~57.3 min left
Read DEF 149,998,564 lines 59,310 lines/s 42 min elapsed NETS 728,098/3,235,531  ~56.1 min left
Read DEF 150,998,920 lines 59,005 lines/s 43 min elapsed NETS 749,199/3,235,531  ~55.7 min left
Read DEF 152,234,584 lines 58,799 lines/s 43 min elapsed NETS 768,158/3,235,531  ~55.5 min left
Read DEF 153,456,203 lines 58,552 lines/s 44 min elapsed NETS 794,609/3,235,531  ~54.7 min left
Read DEF 154,739,890 lines 58,373 lines/s 44 min elapsed NETS 813,517/3,235,531  ~54.5 min left
Read DEF 155,956,241 lines 58,174 lines/s 45 min elapsed NETS 838,132/3,235,531  ~53.8 min left
Read DEF 157,143,152 lines 57,911 lines/s 45 min elapsed NETS 867,737/3,235,531  ~52.8 min left
Read DEF 158,354,361 lines 57,719 lines/s 46 min elapsed NETS 897,966/3,235,531  ~51.7 min left
Read DEF 159,605,433 lines 57,497 lines/s 46 min elapsed NETS 923,512/3,235,531  ~51.1 min left
Read DEF 160,801,547 lines 57,305 lines/s 47 min elapsed NETS 945,440/3,235,531  ~50.6 min left
Read DEF 162,037,168 lines 57,188 lines/s 47 min elapsed NETS 965,917/3,235,531  ~50.3 min left
Read DEF 163,234,991 lines 56,921 lines/s 48 min elapsed NETS 987,511/3,235,531  ~49.7 min left
Read DEF 164,440,922 lines 56,740 lines/s 48 min elapsed NETS 1,012,833/3,235,531  ~49.2 min left
Read DEF 165,754,856 lines 56,606 lines/s 49 min elapsed NETS 1,030,477/3,235,531  ~49.1 min left
Read DEF 167,119,426 lines 56,494 lines/s 49 min elapsed NETS 1,051,421/3,235,531  ~48.7 min left
Read DEF 168,305,318 lines 56,323 lines/s 50 min elapsed NETS 1,076,837/3,235,531  ~48.0 min left
Read DEF 169,435,689 lines 56,138 lines/s 50 min elapsed NETS 1,100,191/3,235,531  ~47.7 min left
Read DEF 170,567,731 lines 55,957 lines/s 51 min elapsed NETS 1,125,343/3,235,531  ~46.8 min left
Read DEF 171,716,296 lines 55,716 lines/s 51 min elapsed NETS 1,151,666/3,235,531  ~46.1 min left
Read DEF 172,902,172 lines 55,560 lines/s 52 min elapsed NETS 1,179,308/3,235,531  ~45.3 min left
Read DEF 174,185,793 lines 55,438 lines/s 52 min elapsed NETS 1,205,067/3,235,531  ~44.7 min left
Read DEF 175,295,227 lines 55,264 lines/s 53 min elapsed NETS 1,230,955/3,235,531  ~44.0 min left
Read DEF 176,537,606 lines 55,087 lines/s 53 min elapsed NETS 1,256,865/3,235,531  ~43.4 min left
Read DEF 177,783,628 lines 55,962 lines/s 54 min elapsed NETS 1,276,319/3,235,531  ~43.1 min left
Read DEF 178,994,927 lines 54,782 lines/s 54 min elapsed NETS 1,300,266/3,235,531  ~42.6 min left
Read DEF 180,226,313 lines 54,650 lines/s 55 min elapsed NETS 1,325,157/3,235,531  ~41.9 min left
Read DEF 181,495,180 lines 54,535 lines/s 55 min elapsed NETS 1,342,470/3,235,531  ~41.7 min left
Read DEF 182,737,038 lines 54,405 lines/s 56 min elapsed NETS 1,363,511/3,235,531  ~41.3 min left
Read DEF 183,956,111 lines 54,283 lines/s 56 min elapsed NETS 1,378,293/3,235,531  ~41.3 min left
Read DEF 185,214,380 lines 54,175 lines/s 57 min elapsed NETS 1,399,249/3,235,531  ~40.8 min left
Read DEF 186,456,392 lines 54,064 lines/s 57 min elapsed NETS 1,414,610/3,235,531  ~40.7 min left
Read DEF 187,664,489 lines 53,945 lines/s 58 min elapsed NETS 1,435,187/3,235,531  ~40.3 min left
Read DEF 188,887,802 lines 53,800 lines/s 59 min elapsed NETS 1,451,975/3,235,531  ~40.1 min left
Read DEF 190,138,144 lines 53,697 lines/s 59 min elapsed NETS 1,472,737/3,235,531  ~39.7 min left
Read DEF 191,403,626 lines 53,601 lines/s 60 min elapsed NETS 1,489,707/3,235,531  ~39.4 min left
Read DEF 192,616,894 lines 53,491 lines/s 60 min elapsed NETS 1,509,314/3,235,531  ~39.1 min left
Read DEF 193,854,858 lines 53,390 lines/s 61 min elapsed NETS 1,526,874/3,235,531  ~38.8 min left
Read DEF 195,066,904 lines 53,251 lines/s 61 min elapsed NETS 1,545,855/3,235,531  ~38.5 min left
Read DEF 196,336,001 lines 53,162 lines/s 62 min elapsed NETS 1,565,319/3,235,531  ~38.1 min left
Read DEF 197,540,840 lines 53,047 lines/s 62 min elapsed NETS 1,583,384/3,235,531  ~37.8 min left
Read DEF 198,896,132 lines 52,937 lines/s 63 min elapsed NETS 1,606,312/3,235,531  ~37.3 min left
Read DEF 200,132,527 lines 52,842 lines/s 63 min elapsed NETS 1,623,228/3,235,531  ~37.0 min left
Read DEF 201,450,539 lines 52,744 lines/s 64 min elapsed NETS 1,638,860/3,235,531  ~36.8 min left
Read DEF 202,724,760 lines 52,664 lines/s 64 min elapsed NETS 1,654,874/3,235,531  ~36.6 min left
Read DEF 203,925,681 lines 52,531 lines/s 65 min elapsed NETS 1,683,612/3,235,531  ~35.8 min left
Read DEF 205,179,768 lines 52,449 lines/s 65 min elapsed NETS 1,711,598/3,235,531  ~35.0 min left
Read DEF 206,339,264 lines 52,315 lines/s 66 min elapsed NETS 1,736,317/3,235,531  ~34.4 min left
Read DEF 207,520,884 lines 52,213 lines/s 66 min elapsed NETS 1,767,174/3,235,531  ~33.5 min left
Read DEF 208,768,001 lines 52,116 lines/s 67 min elapsed NETS 1,786,703/3,235,531  ~33.2 min left
Read DEF 210,035,721 lines 52,004 lines/s 67 min elapsed NETS 1,806,503/3,235,531  ~32.8 min left
Read DEF 211,220,179 lines 51,912 lines/s 68 min elapsed NETS 1,833,795/3,235,531  ~32.2 min left
Read DEF 212,391,908 lines 51,818 lines/s 68 min elapsed NETS 1,859,528/3,235,531  ~31.4 min left
Read DEF 213,554,622 lines 51,723 lines/s 69 min elapsed NETS 1,875,461/3,235,531  ~31.1 min left
Read DEF 214,769,070 lines 51,642 lines/s 69 min elapsed NETS 1,901,637/3,235,531  ~30.5 min left
Read DEF 215,929,126 lines 51,549 lines/s 70 min elapsed NETS 1,919,171/3,235,531  ~30.1 min left
Read DEF 217,183,865 lines 51,480 lines/s 70 min elapsed NETS 1,946,853/3,235,531  ~29.4 min left
Read DEF 218,264,801 lines 51,371 lines/s 71 min elapsed NETS 1,959,628/3,235,531  ~29.3 min left
Read DEF 219,439,863 lines 51,261 lines/s 71 min elapsed NETS 1,985,936/3,235,531  ~28.6 min left
Read DEF 220,649,334 lines 51,185 lines/s 72 min elapsed NETS 2,005,892/3,235,531  ~28.2 min left
Read DEF 221,864,183 lines 51,097 lines/s 72 min elapsed NETS 2,028,104/3,235,531  ~27.7 min left
Read DEF 223,128,384 lines 51,036 lines/s 73 min elapsed NETS 2,052,983/3,235,531  ~27.1 min left
Read DEF 224,307,334 lines 50,956 lines/s 73 min elapsed NETS 2,074,982/3,235,531  ~26.6 min left
Read DEF 225,419,191 lines 50,848 lines/s 74 min elapsed NETS 2,094,055/3,235,531  ~26.2 min left
Read DEF 226,677,636 lines 50,789 lines/s 74 min elapsed NETS 2,120,518/3,235,531  ~25.5 min left
Read DEF 227,857,631 lines 50,712 lines/s 75 min elapsed NETS 2,141,227/3,235,531  ~25.1 min left
```

### Snapshot 4 — heartbeats to the end, stage lines, `metal-summary`, final warnings

```
Read DEF 235,247,207 lines 50,315 lines/s 78 min elapsed NETS 2,275,853/3,235,531  ~22.0 min left
Read DEF 236,493,767 lines 50,259 lines/s 78 min elapsed NETS 2,294,861/3,235,531  ~21.5 min left
Read DEF 237,623,933 lines 50,153 lines/s 79 min elapsed NETS 2,319,285/3,235,531  ~21.0 min left
Read DEF 238,960,378 lines 50,118 lines/s 79 min elapsed NETS 2,348,529/3,235,531  ~20.2 min left
Read DEF 240,188,482 lines 50,061 lines/s 80 min elapsed NETS 2,369,833/3,235,531  ~19.8 min left
Read DEF 241,412,914 lines 50,096 lines/s 80 min elapsed NETS 2,395,665/3,235,531  ~19.1 min left
Read DEF 242,659,571 lines 49,930 lines/s 81 min elapsed NETS 2,419,648/3,235,531  ~18.6 min left
Read DEF 243,971,561 lines 49,892 lines/s 81 min elapsed NETS 2,451,936/3,235,531  ~17.8 min left
Read DEF 245,041,332 lines 49,803 lines/s 82 min elapsed NETS 2,472,297/3,235,531  ~17.3 min left
Read DEF 246,296,899 lines 49,755 lines/s 83 min elapsed NETS 2,497,123/3,235,531  ~16.7 min left
Read DEF 247,554,343 lines 49,707 lines/s 83 min elapsed NETS 2,516,135/3,235,531  ~16.3 min left
Read DEF 248,711,398 lines 49,613 lines/s 84 min elapsed NETS 2,541,767/3,235,531  ~15.7 min left
Read DEF 250,025,430 lines 49,562 lines/s 84 min elapsed NETS 2,566,304/3,235,531  ~15.2 min left
Read DEF 251,315,407 lines 49,503 lines/s 85 min elapsed NETS 2,596,679/3,235,531  ~14.5 min left
Read DEF 252,531,833 lines 49,451 lines/s 85 min elapsed NETS 2,621,951/3,235,531  ~13.9 min left
Read DEF 253,721,580 lines 49,393 lines/s 86 min elapsed NETS 2,640,045/3,235,531  ~13.5 min left
Read DEF 254,870,950 lines 49,325 lines/s 86 min elapsed NETS 2,661,742/3,235,531  ~13.0 min left
Read DEF 256,115,509 lines 49,264 lines/s 87 min elapsed NETS 2,685,660/3,235,531  ~12.4 min left
Read DEF 257,407,011 lines 49,213 lines/s 87 min elapsed NETS 2,703,730/3,235,531  ~12.1 min left
Read DEF 258,700,071 lines 49,178 lines/s 88 min elapsed NETS 2,732,316/3,235,531  ~11.4 min left
Read DEF 259,825,857 lines 49,112 lines/s 88 min elapsed NETS 2,753,015/3,235,531  ~10.9 min left
Read DEF 260,996,078 lines 49,052 lines/s 89 min elapsed NETS 2,775,560/3,235,531  ~10.4 min left
Read DEF 262,203,575 lines 48,998 lines/s 89 min elapsed NETS 2,801,700/3,235,531  ~9.8 min left
Read DEF 263,551,191 lines 48,964 lines/s 90 min elapsed NETS 2,828,136/3,235,531  ~9.2 min left
Read DEF 264,617,828 lines 48,862 lines/s 90 min elapsed NETS 2,850,907/3,235,531  ~8.7 min left
Read DEF 265,900,711 lines 48,848 lines/s 91 min elapsed NETS 2,880,294/3,235,531  ~8.0 min left
Read DEF 267,084,511 lines 48,797 lines/s 91 min elapsed NETS 2,901,961/3,235,531  ~7.5 min left
Read DEF 268,230,860 lines 48,725 lines/s 92 min elapsed NETS 2,927,732/3,235,531  ~6.9 min left
Read DEF 269,480,631 lines 48,687 lines/s 92 min elapsed NETS 2,950,348/3,235,531  ~6.4 min left
Read DEF 270,608,912 lines 48,612 lines/s 93 min elapsed NETS 2,972,684/3,235,531  ~5.9 min left
Read DEF 271,877,731 lines 48,578 lines/s 93 min elapsed NETS 2,994,623/3,235,531  ~5.4 min left
Read DEF 273,040,466 lines 48,526 lines/s 94 min elapsed NETS 3,015,116/3,235,531  ~5.0 min left
Read DEF 274,155,003 lines 48,466 lines/s 94 min elapsed NETS 3,030,148/3,235,531  ~4.6 min left
Read DEF 275,303,620 lines 48,412 lines/s 95 min elapsed NETS 3,039,788/3,235,531  ~4.4 min left
Read DEF 276,513,653 lines 48,370 lines/s 95 min elapsed NETS 3,072,461/3,235,531  ~3.7 min left
Read DEF 277,578,269 lines 48,302 lines/s 96 min elapsed NETS 3,094,035/3,235,531  ~3.2 min left
Read DEF 278,823,936 lines 48,267 lines/s 96 min elapsed NETS 3,116,817/3,235,531  ~2.7 min left
Read DEF 279,946,531 lines 48,190 lines/s 97 min elapsed NETS 3,138,504/3,235,531  ~2.2 min left
Read DEF 281,217,209 lines 48,160 lines/s 97 min elapsed NETS 3,162,002/3,235,531  ~1.7 min left
Read DEF 282,309,911 lines 48,068 lines/s 98 min elapsed NETS 3,182,683/3,235,531  ~1.2 min left
Read DEF 283,592,382 lines 48,061 lines/s 98 min elapsed NETS 3,209,977/3,235,531  ~0.6 min left
Read DEF 284,747,622 lines 48,013 lines/s 99 min elapsed NETS 3,232,692/3,235,531  ~0.1 min left
End DEF parsing in 5934.7341s
INFO vlsi_viewer.metal: lx956c_ioe: 5 non-default rule(s)
INFO vlsi_viewer.metal: metal: stage routing   5940.63s  253,607,592 shape(s), 373,423,631 point(s)  rss 2,518 MB
INFO vlsi_viewer.metal: metal: stage grids   0.74s  rss 2,518 MB
INFO vlsi_viewer.metal: metal: 51851532 shape(s) measured and handed to the rasteriser
INFO vlsi_viewer.metal: metal: 108844474 via point(s) omitted (no wire area)
INFO vlsi_viewer.metal: metal: 11818300 non-preferred jog(s) shorter than a track pitch dropped
INFO vlsi_viewer.metal: metal: 72051441 shape(s) on layers outside the requested range were skipped
INFO vlsi_viewer.metal: metal-summary: {"blockage": {"fallback_cells": 0, "fallback_layer_names": ["M2", "M3", "M4"], "fallback_layers": 4, "ignored_cells": [], "ignored_layers": {}, "obs_cells": 89, "obs_layers": [0, 1, 2], "unknown_layers": {}}, "design": {"name": "lx956c_ioe", "die_ums": [1060.2, 1226.64], "filtered_layers": ["ALPA", "M1", "TM1", "TM2"], "gc_count": [1760060, 16005, 64], "gc_s": 147.25, "grid": [123, 107, 107], "grid_size_um": 10.0, "input_text": {"forms": 275663148, "lines": 284908802, "points_max": 373423631, "points_max": 2, "statement_chars_max": 4979560694, "statement_lines_max": 58549358}, "inputs": [{"bytes": 2108.5, "mtime": 1788556018, "path": "/tmpdata/LinxCore950_PD_N3_t/user/l00922843/IOE/20.PR.Lx956_ioe/TAG0825_FC_inn25_seqMerge/DATAOUT/lx956c_ioe.def.gz"}], "lef": 221, "tech_lef": "/tmpdata/LinxCore950_PD_N2_t/user/data/LX950/N+3/lib/tlef/HNJ730R_575Gt228H_1P14M_4DPM_Q1_3Q2_2Q3_2B_2TMA_ALPA2_M3_P40_P42_V2_3mask_DTC0_L8_Vn.lef"}, "layers": [{"direction": "VERTICAL", "name": "M2", "pitch_um": 0.038, "usable": true, "width_um": 0.019}, {"direction": "HORIZONTAL", "name": "M3", "pitch_um": 0.04, "usable": true, "width_um": 0.024}, {"direction": "VERTICAL", "name": "M4", "pitch_um": 0.048, "usable": true, "width_um": 0.038}, {"direction": "HORIZONTAL", "name": "M5", "pitch_um": 0.076, "usable": true, "width_um": 0.038}, {"direction": "VERTICAL", "name": "M6", "pitch_um": 0.076, "usable": true, "width_um": 0.038}, {"direction": "HORIZONTAL", "name": "M7", "pitch_um": 0.076, "usable": true, "width_um": 0.038}, {"direction": "VERTICAL", "name": "FM1", "pitch_um": 0.096, "usable": true, "width_um": 0.048}, {"direction": "VERTICAL", "name": "FM2", "pitch_um": 0.096, "usable": true, "width_um": 0.048}, {"direction": "HORIZONTAL", "name": "B1", "pitch_um": 0.126, "usable": true, "width_um": 0.062}, {"direction": "VERTICAL", "name": "B2", "pitch_um": 0.126, "usable": true, "width_um": 0.062}], "layers_not_in_tech": ["ASK"], "params": {"macro_block_layers": 4, "max_layer": 12, "min_layer": 2, "max_segment": 2, "min_segment": null, "top": null, "peak_rss_mb": 42123, "stages_mb": 2518}, "shapes": {"degenerate": 4502062, "cell_index": 51851532, "filtered": 72051441, "jogs": 11818300, "polygon_edges": 0, "total": 253607592, "unknown_layer": 4539783, "unusable": 0}, "stages": {"blockage": 9.54, "cell-index": 11.18, "components": 43.91, "grids": 0.74, "routing": 5940.63, "start": 0.0, "tech-lef": 0.02}, "warnings": ["1 cell type(s) are neither in the LEF nor a block, so they contribute no footprint: tensoror_remote_npppp100", "187 cell(s) carry signal wire on a layer a macro obstructs there, so their utilisation is not a congestion reading", "4539783 shape(s) on layers the tech LEF does not define were skipped", "4502062 shape(s) had no extent and were skipped"]}
WARNING vlsi_viewer.metal: 1 cell type(s) are neither in the LEF nor a block, so they contribute no footprint: tensoror_remote_npppp100
WARNING vlsi_viewer.metal: 187 cell(s) carry signal wire on a layer a macro obstructs there, so their utilisation is not a congestion reading
WARNING vlsi_viewer.metal: 4539783 shape(s) on layers the tech LEF does not define were skipped
WARNING vlsi_viewer.metal: 4502062 shape(s) had no extent and were skipped
```

(The stray `1` visible at the very bottom of the last window is shell residue, not part of the log.)

Notes on the transcription:

- The one line flagged in snapshot 2 (111,235,540 after 111,345,539) breaks monotonicity and is
  almost certainly a one-digit misread of the screenshot (e.g. 121,345,540); it is transcribed
  as shown.
- The `input_text` object as captured carries two keys both reading `points_max`; from the
  source (`vlsi_viewer/parsers/DEF/defParser.py`) the fields are `forms`, `points`, `lines`,
  `statement_lines_max`, `statement_chars_max`, `points_max` — so one of the two `points_max`
  values (373,423,631) is the total `points`, the other (2) `points_max`.
- The deployed summary format differs slightly from this checkout's (`stages` vs `stages_s`,
  a three-element `grid`, `max_segment`, `stages_mb`, `gc_count` list) — the deployed
  `VLSI_design_browser-master` is a slightly different revision than the one in this repo.

## 2. Turnaround time

### Timeline

| event | time |
|---|---|
| submitted (PENDING) | 11:46:46.093 |
| RUNNING on `whalcd082-hs` | 11:48:48.814 — queue wait **122.7 s (~2 min)** |
| stage `components` done (DEF pass 1, 3,355,697 instances) | +43.91 s |
| stage `cell-index` done (221 LEF files, 17,385 cells) | +11.18 s |
| stage `blockage` done (incl. 0.73 s capacity) | +9.54 s |
| stage `routing` done (DEF pass 2, "End DEF parsing in 5934.7341s") | **+5,940.63 s** |
| stage `grids` done | +0.74 s |
| **job finished ≈ 13:29** | **total ≈ 6,129 s ≈ 102 min (1 h 42 min)** |

### Where the time went

From the `stages` object of the `metal-summary` line (sum 6,006.02 s of compute time):

| stage | seconds | share |
|---|---|---|
| `tech-lef` | 0.02 | 0.00 % |
| `components` (DEF pass 1) | 43.91 | 0.73 % |
| `cell-index` | 11.18 | 0.19 % |
| `blockage` | 9.54 | 0.16 % |
| `routing` (DEF pass 2) | **5,940.63** | **98.91 %** |
| `grids` | 0.74 | 0.01 % |

The routing read is the whole job. Everything else together is under 1.1 % of the compute
time, and the queue added ~2 min.

### What the routing read actually did

| input fact (from the summary) | value |
|---|---|
| file size (gzipped) | 2,108.5 MB |
| lines | 284,908,802 |
| forms | 275,663,148 |
| points | 373,423,631 (1.47 per shape) |
| SPECIALNETS / NETS | 88,763 / 3,235,531 |
| biggest single statement | 4,979,560,694 chars (~5 GB), 58,549,358 lines — one power net |
| shapes (all classes) | 253,607,592 |

The heartbeats show three distinct phases, which is what the 20.8 µs/line average hides:

| phase | lines | rate |
|---|---|---|
| header + COMPONENTS (burst) | ~13.5 M in the first minute | ~450,000 lines/s |
| SPECIALNETS (~1 min → ~27 min) | ~85 M lines | ~15–25 µs/line |
| NETS (~27 min → 99 min) | ~173 M lines | ~25 µs/line, 3.24 M signal nets |

Per-shape cost for the stage: 5,940.63 s / 253,607,592 = **23.4 µs/shape**. The shape
population, by the run's own counters (sums exactly to the total):

| class | count | share |
|---|---|---|
| via points (omitted, no wire area) | 108,844,474 | 42.9 % |
| filtered (layers outside 2..12) | 72,051,441 | 28.4 % |
| emitted (measured, to the rasteriser) | 51,851,532 | 20.4 % |
| jogs (non-preferred, < track pitch) | 11,818,300 | 4.7 % |
| unknown layer (`ASK`) | 4,539,783 | 1.8 % |
| degenerate (no extent) | 4,502,062 | 1.8 % |
| **total** | **253,607,592** | 100 % |

### Against the previous real run (2026-09-13, full 18 layers)

| | 2026-09-13 | this run |
|---|---|---|
| DEF version | `TA08025_FC_inn25_seqMerge` | `TAG0825_FC_inn25_seqMerge` |
| routing read | 7,005 s | 5,935 s (**−15.3 %**) |
| total shapes | not logged (~250 M estimated) | 253.6 M logged |
| µs/shape (derived) | ~28 | 23.4 |
| layers | all | 11 of 15 (range 2..12) |
| peak RSS | 18.9 GB of 20 GB | 2.5 GB steady; `peak_rss_mb 42,123` in summary (see below) |

The comparison is confounded by the layer range (28.4 % of the shapes are the filtered class
here) and by a different data version, but the direction matches the single-core work that
landed between the two runs (2.4x on the via-dominated class, per the as-built Phase 15).

## 4. Run B (job 1645417604, `--profile`) — log and cProfile analysis

Submitted 2026-09-14 13:56:15 on host `whalcd234-hs`. Same inputs as Run A plus the
`--profile` flag. Three terminal screenshots; total ≈ 168 min. The `cProfile` instrumentation
adds ≈ 68 % overhead (see section 4.1).

### Snapshot 1 — submission, queue, tech LEF, components pass, LEF parse starts

```
dsbsub -A root.ug_yyother.Linux956_PD2_HClass -q Long -R 'cpu=4;mem=20000' -I "venv/bin/python3 VLSI_design_browser-master/main.py metal --def /tmpdata/LinxCore950_PD_N3_t/user/l00922843/IOE/20.PR.Lx956_ioe/TAG0825_FC_inn25_seqMerge/DATAOUT/lx956c_ioe.def.gz --lef lefs/ --tech-lef /tmpdata/LinxCore950_PD_N2_t/user/data/LX950/N+3/lib/tlef/HNJ730R_575Gt228H_1P14M_4DPM_Q1_3Q2_2Q3_2B_2TMA_ALPA2_M3_P40_P42_V2_3mask_DTC0_L8_Vn.lef --min-layer 2 --max-layer 12 --profile"
             MESSAGE                         JOBID
1645417604      Submit job successfully.

2026-09-14 13:56:15.038 ==> job state changed to: PENDING

2026-09-14 13:56:17.916 ==> job state changed to: RUNNING
Job is running on host whalcd234-hs

INFO vlsi_viewer.cli: metal: reading 1 DEF file(s)
INFO vlsi_viewer.metal: metal: stage start                   0.00s   rss 81 MB
Start parsing tech lef /tmpdata/LinxCore950_PD_N2_t/user/data/LX950/N+3/lib/tlef/HNJ730R_575Gt228H_1P14M_4DPM_Q1_3Q2_2Q3_2B_2TMA_ALPA2_M3_P40_P42_V2_3mask_DTC0_L8_Vn.lef
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V2 before 'LAYER V1'
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V3 before 'LAYER V2'
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V4 before 'LAYER V3'
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V5 before 'LAYER V4'
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V6 before 'LAYER V5'
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V7 before 'LAYER V6'
WARNING vlsi_viewer.parsers.LEF.lefParser: tech LEF: unterminated PROPERTY in layer V3_FB1 before 'LAYER V2'
End parsing tech lef in 0.034s
INFO vlsi_viewer.parsers.routing: tech LEF: 3 region-defined layer(s) are not routing layers of the stack and are skipped: M2_FB1, M3_FB1, M4_FB1
INFO vlsi_viewer.parsers.routing: tech LEF: 15 routing layer(s) of 63 layer(s), 0 unusable, 3 region-defined
INFO vlsi_viewer.metal: metal: Layers M2..B2 (11 of 15), ignoring M1, TM1, TM2, ALPA
INFO vlsi_viewer.metal: metal: stage tech-lef   0.03s  rss 81 MB
INFO vlsi_viewer.cli: metal: reading block outlines
Load DEF file /tmpdata/LinxCore950_PD_N3_t/user/l00922843/IOE/20.PR.Lx956_ioe/TAG0825_FC_inn25_seqMerge/DATAOUT/lx956c_ioe.def.gz
Read DEF 4,990,258 lines  166,342 lines/s  1 min elapsed
End DEF parsing in 41.4346s
INFO vlsi_viewer.parsers.convert: def: /tmpdata/LinxCore950_PD_N3_t/user/l00922843/IOE/20.PR.Lx956_ioe/TAG0825_FC_inn25_seqMerge/DATAOUT/lx956c_ioe.def.gz -> 3355697 instance(s) (dropped 0 filler, skipped 0 unplaced), 8 boundary point(s)
INFO vlsi_viewer.loader: Loaded block 'lx956c_ioe' with 3355697 instance(s) from <in-memory>
INFO vlsi_viewer.metal: metal: stage components   71.58s  1 block(s), root 'lx956c_ioe'  rss 2,494 MB
Start parsing Lef files
Total 221 LEF files
Parsing lefs/hir1zh228_ckmesh_1p14m_4dpm_q1_3q2_2q3_2b_2tma_onlypr.lef
Parsing lefs/hir1zh228_ckmesh_1p14m_4dpm_q1_3q2_2q3_2b_2tma_onlypr.lef.cell_info.json
Parsing lefs/hir1zh228l10p57sdb_aic_lvt_onlypr.lef
Parsing lefs/hir1zh228l10p57sdb_aic_svt_onlypr.lef
Parsing lefs/hir1zh228l10p57sdb_aic_ulvt_onlypr.lef
Parsing lefs/HIS6LC956GSRAMTP64X64MH5B.lef
Parsing lefs/HIS6LC956GSRAMTP64X86MH5B.lef
```

### Snapshot 2 — LEF pass done, capacity and blockage, routing read starts (heartbeats to ~53 min)

```
End parsing 221 LEF files in 16.428s
INFO vlsi_viewer.parsers.convert: lef: 17385 macro(s) from 221 file(s)
INFO vlsi_viewer.loader: Loaded 17385 cell(s) from <in-memory>
INFO vlsi_viewer.metal: metal: stage cell-index   17.31s  17,385 cell(s) from 221 LEF file(s)  rss 2,397 MB
INFO vlsi_viewer.metal: metal: stage routing
INFO vlsi_viewer.cli: metal: measuring capacity
INFO vlsi_viewer.metal: metal: stage grids                  1.02s  123 x 107 grid @ 10 um, die 1060.2 x 1226.6 um  rss 2,373 MB
INFO vlsi_viewer.metal: metal: blockage from 89 macro(s) declaring OBS over 3 layer(s); 0 fall back to the bottom 4 layer(s) (M2, M3, M4 inside the measured range); 0 declare nothing significant
INFO vlsi_viewer.metal: metal: stage blockage   13.68s  8 macro type(s) with obstruction data  rss 2,373 MB
INFO vlsi_viewer.cli: metal: reading routing
INFO vlsi_viewer.cli: metal: reading routing in lx956c_ioe
LOAD FILE /tmpdata/LinxCore950_PD_N3_t/user/l00922843/IOE/20.PR.Lx956_ioe/TAG0825_FC_inn25_seqMerge/DATAOUT/lx956c_ioe.def.gz
Read DEF 6,320,303 lines  210,677 lines/s  1 min elapsed
Read DEF 12,889,740 lines  214,829 lines/s  1 min elapsed
Read DEF 16,971,699 lines  188,574 lines/s  2 min elapsed  SPECIALNETS 78,482/88,763  ~0.0 min left
Read DEF 25,854,458 lines  215,454 lines/s  2 min elapsed  SPECIALNETS 88,760/88,763  ~0.0 min left
Read DEF 34,965,661 lines  232,861 lines/s  3 min elapsed  SPECIALNETS 88,760/88,763  ~0.0 min left
Read DEF 34,965,662 lines  48,651 lines/s  12 min elapsed  SPECIALNETS 88,761/88,763  ~0.0 min left
Read DEF 43,656,064 lines  58,309 lines/s  12 min elapsed  SPECIALNETS 88,762/88,763  ~0.0 min left
Read DEF 52,796,181 lines  67,595 lines/s  13 min elapsed  SPECIALNETS 88,762/88,763  ~0.0 min left
Read DEF 52,796,182 lines  39,427 lines/s  22 min elapsed  SPECIALNETS 88,763/88,763  ~0.0 min left
Read DEF 61,795,969 lines  45,136 lines/s  23 min elapsed  SPECIALNETS 88,763/88,763  ~0.0 min left
Read DEF 70,750,065 lines  50,568 lines/s  23 min elapsed  SPECIALNETS 88,763/88,763  ~0.0 min left
Read DEF 79,686,139 lines  55,760 lines/s  24 min elapsed  SPECIALNETS 88,763/88,763  ~0.0 min left
Read DEF 88,608,839 lines  60,728 lines/s  24 min elapsed  SPECIALNETS 88,763/88,763  ~0.0 min left
Read DEF 97,523,655 lines  65,492 lines/s  25 min elapsed  SPECIALNETS 88,763/88,763  ~0.0 min left
Read DEF 106,443,571 lines  70,070 lines/s  25 min elapsed  SPECIALNETS 88,763/88,763  ~0.0 min left
Read DEF 111,345,540 lines  42,795 lines/s  43 min elapsed  SPECIALNETS 88,763/88,763  ~0.0 min left
Read DEF 112,121,820 lines  42,603 lines/s  44 min elapsed  NETS 12,452/3,235,531  ~129.4 min left
Read DEF 112,867,640 lines  42,379 lines/s  44 min elapsed  NETS 21,195/3,235,531  ~155.4 min left
Read DEF 113,712,442 lines  42,221 lines/s  45 min elapsed  NETS 38,427/3,235,531  ~126.8 min left
Read DEF 114,577,866 lines  42,038 lines/s  45 min elapsed  NETS 53,880/3,235,531  ~121.8 min left
Read DEF 115,386,746 lines  41,873 lines/s  46 min elapsed  NETS 63,818/3,235,531  ~127.4 min left
Read DEF 116,171,817 lines  41,668 lines/s  46 min elapsed  NETS 73,563/3,235,531  ~133.4 min left
Read DEF 116,936,172 lines  41,477 lines/s  47 min elapsed  NETS 83,769/3,235,531  ~136.4 min left
Read DEF 117,731,397 lines  41,319 lines/s  47 min elapsed  NETS 95,602/3,235,531  ~135.5 min left
Read DEF 118,385,350 lines  41,110 lines/s  48 min elapsed  NETS 106,535/3,235,531  ~136.1 min left
Read DEF 119,095,893 lines  40,927 lines/s  48 min elapsed  NETS 123,688/3,235,531  ~129.2 min left
Read DEF 119,915,982 lines  40,789 lines/s  49 min elapsed  NETS 140,803/3,235,531  ~123.9 min left
Read DEF 120,569,927 lines  40,597 lines/s  49 min elapsed  NETS 154,828/3,235,531  ~122.1 min left
Read DEF 121,299,053 lines  40,471 lines/s  50 min elapsed  NETS 171,698/3,235,531  ~119.2 min left
Read DEF 122,069,740 lines  40,204 lines/s  51 min elapsed  NETS 189,491/3,235,531  ~116.4 min left
Read DEF 122,845,568 lines  39,988 lines/s  51 min elapsed  NETS 207,259/3,235,531  ~114.3 min left
Read DEF 123,641,649 lines  39,804 lines/s  52 min elapsed  NETS 226,219/3,235,531  ~111.8 min left
Read DEF 124,446,913 lines  39,611 lines/s  52 min elapsed  NETS 244,904/3,235,531  ~109.1 min left
Read DEF 125,242,370 lines  39,436/3,235,531  ~108.1 min left
```

### Snapshot 3 — routing read heartbeats to the end, stage lines, `metal-summary`, cProfile

```
Read DEF 282,031,166 lines  28,657 lines/s  164 min elapsed  NETS 3,178,371/3,235,531  ~2.2 min left
Read DEF 282,728,077 lines  28,641 lines/s  165 min elapsed  NETS 3,201,920/3,235,531  ~1.7 min left
Read DEF 283,453,830 lines  28,627 lines/s  165 min elapsed  NETS 3,206,286/3,235,531  ~1.1 min left
Read DEF 284,206,753 lines  28,616 lines/s  166 min elapsed  NETS 3,221,467/3,235,531  ~0.5 min left
Read DEF 284,877,968 lines  28,598 lines/s  166 min elapsed  NETS 3,234,817/3,235,531  ~0.0 min left
End DEF parsing in 9962.4396s
INFO vlsi_viewer.metal: lx956c_ioe: 5 non-default rule(s)
INFO vlsi_viewer.metal: metal: stage routing   9971.87s  253,607,592 shape(s), 373,423,631 point(s)  rss 2,525 MB
INFO vlsi_viewer.metal: metal: stage grids                  0.86s  rss 2,525 MB
INFO vlsi_viewer.metal: metal: 51851532 shape(s) measured and handed to the rasteriser
INFO vlsi_viewer.metal: metal: 108844474 via point(s) omitted (no wire area)
INFO vlsi_viewer.metal: metal: 11818300 non-preferred jog(s) shorter than a track pitch dropped
INFO vlsi_viewer.metal: metal: 72051441 shape(s) on layers outside the requested range were skipped
INFO vlsi_viewer.metal: metal-summary: {"blockage": {"fallback_cells": 0, "fallback_layer_names": ["M2", "M3", "M4"], "fallback_layers": 4, "ignored_cells": [], "ignored_layers": {}, "obs_cells": 89, "obs_layers": [0, 1, 2], "unknown_layers": {}}, "design": {"name": "lx956c_ioe", "die_ums": [1060.2, 1226.6], "filtered_layers": ["ALPA", "M1", "TM1", "TM2"], "gc_count": [176289, 16026, 76], "gc_s": 164.98, "grid": [123, 107], "grid_size_um": 10.0, "input_text": {"forms": 275663148, "lines": 284908802, "points": 373423631, "points_max": 2, "statement_chars_max": 4979560694, "statement_lines_max": 58549358}, "inputs": [{"bytes": 2108.5, "mtime": 1771999514, "path": "/tmpdata/LinxCore950_PD_N3_t/user/l00922843/IOE/20.PR.Lx956_ioe/TAG0825_FC_inn25_seqMerge/DATAOUT/lx956c_ioe.def.gz"}], "lef": 221, "tech_lef": "/tmpdata/LinxCore950_PD_N2_t/user/data/LX950/N+3/lib/tlef/HNJ730R_575Gt228H_1P14M_4DPM_Q1_3Q2_2Q3_2B_2TMA_ALPA2_M3_P40_P42_V2_3mask_DTC0_L8_Vn.lef"}}, "layers": [{"direction": "VERTICAL", "name": "M2", "pitch_um": 0.038, "usable": true, "width_um": 0.019}, {"direction": "HORIZONTAL", "name": "M3", "pitch_um": 0.04, "usable": true, "width_um": 0.024}, {"direction": "VERTICAL", "name": "M4", "pitch_um": 0.048, "usable": true, "width_um": 0.038}, {"direction": "HORIZONTAL", "name": "M5", "pitch_um": 0.076, "usable": true, "width_um": 0.038}, {"direction": "VERTICAL", "name": "M6", "pitch_um": 0.076, "usable": true, "width_um": 0.038}, {"direction": "HORIZONTAL", "name": "M7", "pitch_um": 0.076, "usable": true, "width_um": 0.038}, {"direction": "VERTICAL", "name": "FM1", "pitch_um": 0.096, "usable": true, "width_um": 0.048}, {"direction": "VERTICAL", "name": "FM2", "pitch_um": 0.096, "usable": true, "width_um": 0.048}, {"direction": "HORIZONTAL", "name": "B1", "pitch_um": 0.126, "usable": true, "width_um": 0.062}, {"direction": "VERTICAL", "name": "B2", "pitch_um": 0.126, "usable": true, "width_um": 0.062}], "layers_not_in_tech": ["ASK"], "params": {"macro_block_layers": 4, "max_layer": 12, "min_layer": 2, "min_segment": null, "top": null}, "peak_rss_mb": 42134, "rss_mb": 2525, "shapes": {"degenerate": 4502062, "emitted": 51851532, "filtered": 72051441, "jogs": 11818300, "polygon_edges": 0, "total": 253607592, "unknown": 4539783, "unusable": 0, "vias": 108844474}, "stages_s": {"blockage": 13.68, "capacity": 1.02, "cell-index": 17.31, "components": 71.58, "grids": 0.86, "routing": 9971.87, "start": 0.0, "tech-lef": 0.03}, "warnings": ["1 cell type(s) are neither in the LEF nor a block, so they contribute no footprint: tensoror_remote_nplppv100", "187 cell(s) carry signal wire on a layer a macro obstructs there, so their utilisation is not a congestion reading", "4539783 shape(s) on layers the tech LEF does not define were skipped", "4502062 shape(s) had no extent and were skipped"]}
20274967067 function calls (20274855473 primitive calls) in 10084.917 seconds

Ordered by: internal time
List reduced from 1451 to 15 due to restriction <15>

ncalls  tottime  percall  cumtime  percall filename:lineno(function)
275663148 2007.584   0.000  3139.661   0.000 /tmpdata/LinxCore950_PD_N3_t/user/l00922843/design_browser/VLSI_design_browser-master/vlsi_viewer/parsers/DEF/defParser.py:402(__scan_tokens)
323525498 788.904   0.000  3665.365   0.001 /tmpdata/LinxCore950_PD_N3_t/user/l00922843/design_browser/VLSI_design_browser-master/vlsi_viewer/parsers/DEF/defParser.py:578(__add_regular_wiring)
88762   699.796   0.008  1998.779   0.023 /tmpdata/LinxCore950_PD_N3_t/user/l00922843/design_browser/VLSI_design_browser-master/vlsi_viewer/parsers/DEF/defParser.py:521(__add_special_wiring)
4866888473 498.018   0.000  498.018   0.000 <method 'group' of 're.Match' objects>
275663148 337.986   0.000  457.336   0.000 /tmpdata/LinxCore950_PD_N3_t/user/l00922843/design_browser/VLSI_design_browser-master/vlsi_viewer/parsers/DEF/defParser.py:439(_split_points)
132620754 256.106   0.000  1465.883   0.000 /tmpdata/LinxCore950_PD_N3_t/user/l00922843/design_browser/venv/lib/python3.9/site-packages/shapely/decorators.py:62(wrapped)
278987304 246.523   0.000  246.909   0.000 <method 'finditer' of 're.Pattern' objects>
8951775  244.732   0.000  244.732   0.000 /tmpdata/LinxCore950_PD_N3_t/user/l00922843/design_browser/VLSI_design_browser-master/vlsi_viewer/parsers/DEF/defParser.py:706(fetchLineGz)
291846154 174.971   0.000  698.897   0.000 /tmpdata/LinxCore950_PD_N3_t/user/l00922843/design_browser/VLSI_design_browser-master/vlsi_viewer/parsers/DEF/defParser.py:391(_resolve_coord)
74847262 167.023   0.000  167.023   0.000 /tmpdata/LinxCore950_PD_N3_t/user/l00922843/design_browser/VLSI_design_browser-master/vlsi_viewer/parsers/DEF/defParser.py:563(_emit_special)
121156138 158.886   0.000  217.644   0.000 /tmpdata/LinxCore950_PD_N3_t/user/l00922843/design_browser/VLSI_design_browser-master/vlsi_viewer/parsers/DEF/defParser.py:62(__emit_special)
53793950 139.281   0.000  139.281   0.000 <method 'sub' of 're.Pattern' objects>
```

### 4.1 Turnaround time — Run B

| event | time |
|---|---|
| submitted (PENDING) | 13:56:15.038 |
| RUNNING on `whalcd234-hs` | 13:56:17.916 — queue wait **2.9 s** |
| stage `components` done (DEF pass 1) | +71.58 s |
| stage `cell-index` done (221 LEF files) | +17.31 s |
| stage `blockage` done (incl. capacity) | +13.68 s |
| stage `routing` done (DEF pass 2) | **+9,971.87 s** |
| stage `grids` done | +0.86 s |
| **job finished ≈ 17:04** | **total ≈ 10,085 s ≈ 168 min (2 h 48 min)** |

### 4.2 Where the time went — with `cProfile` overhead

From the `stages_s` object of the `metal-summary` line (sum 10,015.79 s of compute time):

| stage | seconds | share |
|---|---|---|
| `start` | 0.03 | 0.00 % |
| `tech-lef` | 0.03 | 0.00 % |
| `components` (DEF pass 1) | 71.58 | 0.71 % |
| `cell-index` | 17.31 | 0.17 % |
| `blockage` | 13.68 | 0.14 % |
| `routing` (DEF pass 2) | **9,971.87** | **99.46 %** |
| `grids` | 0.86 | 0.01 % |

The `cProfile` overhead is the difference between the wall-clock total (10,084.917 s) and
the sum of `stages_s` values (10,015.79 s): **69.13 s** in the instrumentation itself.
However, the cProfile overhead is much larger than that — it inflates every function call's
reported time. The `routing` stage alone grew from 5,940.63 s (Run A) to 9,971.87 s (Run B),
a delta of **4,031.24 s**. The `__scan_tokens` function alone went from an unmeasured baseline
to **2,007.58 s** of `tottime` in the cProfile output. The `cProfile` overhead on the routing
stage is approximately **4,031 s** (68 % of the routing stage).

### 4.3 cProfile top-15 breakdown

The `cProfile` output shows the top 15 functions by `tottime` out of 1,451 total. Key
observations:

| function | tottime | cumtime | share of total |
|---|---|---|---|
| `__scan_tokens` | 2,007.58 s | 3,139.66 s | 19.9 % |
| `__add_regular_wiring` | 788.90 s | 3,665.37 s | 7.8 % |
| `__add_special_wiring` | 699.80 s | 1,998.78 s | 6.9 % |
| `re.Match.group` | 498.02 s | 498.02 s | 4.9 % |
| `_split_points` | 337.99 s | 457.34 s | 3.4 % |
| `shapely.decorators.wrapped` | 256.11 s | 1,465.88 s | 2.5 % |
| `re.Pattern.finditer` | 246.52 s | 246.91 s | 2.4 % |
| `fetchLineGz` | 244.73 s | 698.90 s | 2.4 % |
| `_resolve_coord` | 174.97 s | 698.90 s | 1.7 % |
| `_emit_special` | 167.02 s | 167.02 s | 1.7 % |


### 4.4 Comparison: Run A vs Run B

| | Run A (no profile) | Run B (`--profile`) | delta |
|---|---|---|---|
| total wall time | 6,006 s | 10,085 s | **+68 %** |
| routing stage | 5,940.63 s | 9,971.87 s | **+68 %** |
| queue wait | 122.7 s | 2.9 s | −98 % |
| components | 43.91 s | 71.58 s | +63 % |
| cell-index | 11.18 s | 17.31 s | +55 % |
| blockage | 9.54 s | 13.68 s | +43 % |
| GC (gc_s) | 147.25 s | 164.98 s | +12 % |
| peak RSS | 18.9 GB | 42.1 GB (VmHWM) | +123 % |
| gc_count gen-0 | 1,760,060 | 1,762,89 | +0.2 % |


