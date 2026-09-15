Real-design metal-mode run, 2026-09-15 — job 1647183354, first --jobs 8 run: log snapshot
# Real-design metal-mode run, 2026-09-15 — job 1647183354, first `--jobs 8` run: log snapshot

The first multi-worker metal-mode run of the chip-level design `lx956c_ioe`:
`dsh ... metal --lef lefs/* ... --jobs 8`, submitted 2026-09-15 12:40:07 to `-q long`
with `cpu=4;mem=20000`, host `metalcd233-hs`, queue wait ~3 s. Same DEF path as the
09-14 run recorded in `real-design-metal-mode.md`, but a newer file (summary mtime
1,788,556,810; SPECIALNETS 11,096 vs 88,763; 249,067,809 shapes vs 253,607,592). The
routing read finished in **1,780.64 s** with 8 workers vs **5,940.63 s** single-core
on 09-14 — **3.34x** on the routing stage, the first real-design datapoint for
`--jobs`.

The log below is transcribed from the six terminal screenshots. The routing phase is
eight concurrent workers whose per-minute heartbeats interleave on one stream, so the
"Load DEF file … / Read DEF … / End DEF parsing in …" triples are not line-continuous
between windows and the worker-to-line attribution is not visible in the terminal.
Where a screenshot was ambiguous a digit may be off by one.

## 0. The command

```
dsh -A root.ug.yyother.Linx956_PD_HClass -q long -R 'cpu=4;mem=20000' -I 'venv/bin/python3 VLSI_design_browser-master/main.py metal --def /tmpdata/LinxCore950_PD_N3_t/user/l00922843/IOE/20.PR_Lx956_ioe/TAG0825_FC_inn25_seqMerge/DATAOUT/lx956c_ioe.def.gz --lef lefs/* --tech-lef /tmpdata/LinxCore950_PD_N2_t/user/data/LX950/N43/lib/lef/HN3J30R_575GT228H_1P14M_4DPM_Q1_3Q2_2Q3_2B_2TMa_ALPA2_M3_P40_P42_V2_3mask_DTCO_L8_Vn.lef' --min-layer 2 --max-layer 12 --jobs 8"
```

Differences vs the 09-14 command: `dsh` instead of `dsbsub`; account string
`root.ug.yyother.Linx956_PD_HClass` / `-q long`; `--lef lefs/*` instead of `--lef lefs/`;
and the new `--jobs 8` flag (8 routing workers).

## 1. Run log (as captured)

### Snapshot 1 — submission, queue, tech LEF, components pass, LEF parse starts

```
        MESSAGE
JOBID      Submit job successfully.
1647183354  Submit job successfully.

2026-09-15 12:40:07.328 ==> job state changed (to: PENDING

2026-09-15 12:40:10.314 ==> job state changed to: RUNNING
Job is running on host metalcd233-hs
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
End DEF parsing in 26.9251s
INFO vlsi_viewer.parsers.convert: def: /tmpdata/LinxCore950_PD_N3_t/user/l00922843/IOE/20.PR_Lx956_ioe/TAG0825_FC_inn25_seqMerge/DATAOUT/lx956c_ioe.def.gz -> 3355697 instance(s) (dropped 0 filler, skipped 0 unplcaced), 8 boundary point(s)
INFO vlsi_viewer.loader: Loaded block 'lx956c_ioe' with 3355697 instance(s) from <in-memory>
INFO vlsi_viewer.metal: metal: stage components          44.19s   1 block(s), root 'lx956c_ioe'    rss 2,485 MB
Start parsing lef files
Total 221 LEF files
Parsing lefs/hirizh228_ckmesh_1p14m_4dpm_q1_3q2_2q3_2b_2tma_onlypr.lef
Parsing lefs/hirizh228_ckmesh_1p14m_4dpm_q1_3q2_2q3_2b_2tma_onlypr.lef.cell_info.json
Parsing lefs/hirizh228l10p57sdb_aic_lvt_onlypr.lef
```

### Snapshot 2 — LEF pass done, capacity and blockage, 8-worker routing read starts

```
Parsing lefs/HI56LC956C6SRA4MTP6X46M1HSB.lef
Parsing lefs/HI56LC956C6SRA4MTP6X46M6MIHSB.lef
End parsing 221 LEF file in 10.717s
INFO vlsi_viewer.parsers.convert: lef: 17385 macro(s) from 221 file(s)
INFO vlsi_viewer.loader: loaded 17385 cell(s) from <in-memory>
INFO vlsi_viewer.metal: metal: stage lef-index           11.24s  17,385 cell(s) from 221 LEF file(s)    rss 2,389 MB
INFO vlsi_viewer.cli: metal: measuring capacity
INFO vlsi_viewer.metal: metal: stage capacity             0.75s   123 x 107 grid @ 18 um, die 1060.2 x 1226.6 um    rss 2,365 MB
INFO vlsi_viewer.metal: metal: blockage from 89 macro(s) declaring OBS over 3 layer(s); 0 fall back to the bottom 4 layer(s); 0 declare nothing significant
INFO vlsi_viewer.metal: metal: 2108 Mb of DEF (uncompressed); 8 worker(s)
INFO vlsi_viewer.metal: metal: stage blockage              9.62s    8 macro type(s) with obstruction data    rss 2,365 MB
INFO vlsi_viewer.cli: metal: reading routing in lx956c_ioe
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Read DEF 1,428,104 lines   47,603 lines/s   1 min elapsed   NETS 22,861/38,905   ~0.3 min left
Read DEF 1,428,171 lines   47,605 lines/s   1 min elapsed   NETS 22,866/38,905   ~0.3 min left
Read DEF 1,426,066 lines   47,535 lines/s   1 min elapsed   NETS 22,505/38,905   ~0.4 min left
Read DEF 1,431,355 lines   47,712 lines/s   1 min elapsed   NETS 22,751/38,904   ~0.3 min left
Read DEF 1,421,836 lines   47,394 lines/s   1 min elapsed   NETS 22,571/38,904   ~0.3 min left
Read DEF 24,574,995 lines  819,166 lines/s   1 min elapsed   SPECIALNETS 11,096/11,096   ~0.0 min left
End DEF parsing in 50.1872s
End DEF parsing in 50.5270s
End DEF parsing in 50.2602s
End DEF parsing in 50.2219s
End DEF parsing in 50.4137s
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Read DEF 53,801,505 lines  896,692 lines/s   1 min elapsed   SPECIALNETS 11,096/11,096   ~0.0 min left
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Read DEF 1,292,248 lines   43,369 lines/s   1 min elapsed   NETS 23,472/50,000   ~0.6 min left
Read DEF 1,299,103 lines   43,302 lines/s   1 min elapsed   NETS 23,573/50,000   ~0.6 min left
Read DEF 1,291,949 lines   43,064 lines/s   1 min elapsed   NETS 23,502/50,000   ~0.6 min left
Read DEF 1,302,131 lines   43,402 lines/s   1 min elapsed   NETS 23,573/50,000   ~0.6 min left
Read DEF 1,298,267 lines   43,275 lines/s   1 min elapsed   NETS 23,439/50,000   ~0.6 min left
Read DEF 2,405,750 lines   39,592 lines/s   1 min elapsed   NETS 39,599/50,000   ~0.1 min left
Read DEF 2,406,865 lines   39,798 lines/s   1 min elapsed   NETS 43,813/50,000   ~0.1 min left
Read DEF 2,409,365 lines   39,681 lines/s   1 min elapsed   NETS 43,700/50,000   ~0.1 min left
Read DEF 2,409,813 lines   39,597 lines/s   1 min elapsed   NETS 43,928/50,000   ~0.1 min left
End DEF parsing in 64.9247s
End DEF parsing in 65.4594s
End DEF parsing in 65.2680s
End DEF parsing in 65.4647s
Read DEF 2,395,740 lines   39,722 lines/s   1 min elapsed   NETS 42,947/50,000   ~0.2 min left
End DEF parsing in 65.2334s
End DEF parsing in 65.4647s
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Read DEF 1,333,647 lines   42,213 lines/s   1 min elapsed   NETS 25,587/50,000   ~0.5 min left
Read DEF 1,342,106 lines   41,941 lines/s   1 min elapsed   NETS 25,832/50,000   ~0.5 min left
Read DEF 1,344,178 lines   41,915 lines/s   1 min elapsed   NETS 25,890/50,000   ~0.5 min left
Read DEF 1,340,378 lines   41,937 lines/s   1 min elapsed   NETS 25,924/50,000   ~0.5 min left
Read DEF 1,335,978 lines   42,091 lines/s   1 min elapsed   NETS 25,971/50,000   ~0.5 min left
Read DEF 2,627,358 lines   42,656 lines/s   1 min elapsed   NETS 48,853/50,000   ~0.0 min left
Read DEF 2,626,995 lines   42,369 lines/s   1 min elapsed   NETS 48,090/50,000   ~0.0 min left
End DEF parsing in 62.3655s
End DEF parsing in 62.7286s
End DEF parsing in 62.6736s
Read DEF 2,618,784 lines   42,264 lines/s   1 min elapsed   NETS 48,987/50,000   ~0.0 min left
```

### Snapshot 3 — worker heartbeats, two long (SPECIALNETS-heavy) slices running 5–6 min

```
Read DEF 2,618,784 lines   42,264 lines/s   1 min elapsed   NETS 48,987/50,000   ~0.0 min left
End DEF parsing in 62.6835s
Read DEF 2,615,690 lines   42,365 lines/s   1 min elapsed   NETS 48,578/50,000   ~0.0 min left
End DEF parsing in 62.7312s
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Read DEF 17,962,586 lines   59,618 lines/s   5 min elapsed   SPECIALNETS 11,096/11,096   ~0.0 min left
Read DEF 18,074,408 lines   59,478 lines/s   5 min elapsed   SPECIALNETS 11,095/11,095   ~0.0 min left
Read DEF 1,337,407 lines   44,577 lines/s   1 min elapsed   NETS 26,269/50,000   ~0.4 min left
Read DEF 1,341,121 lines   44,704 lines/s   1 min elapsed   NETS 26,381/50,000   ~0.4 min left
Read DEF 1,337,209 lines   44,573 lines/s   1 min elapsed   NETS 26,328/50,000   ~0.4 min left
Read DEF 1,336,853 lines   44,560 lines/s   1 min elapsed   NETS 26,260/50,000   ~0.4 min left
Read DEF 1,340,309 lines   44,676 lines/s   1 min elapsed   NETS 26,420/50,000   ~0.4 min left
Read DEF 19,522,554 lines   57,801 lines/s   6 min elapsed   NETS 24,220/38,905   ~0.3 min left
Read DEF 15,544,355 lines   42,403 lines/s   1 min elapsed   NETS 44,390/50,000   ~0.1 min left
Read DEF 2,542,063 lines   42,367 lines/s   1 min elapsed   NETS 44,245/50,000   ~0.1 min left
Read DEF 2,539,045 lines   42,317 lines/s   1 min elapsed   NETS 44,449/50,000   ~0.1 min left
Read DEF 2,505,992 lines   41,765 lines/s   1 min elapsed   NETS 43,125/50,000   ~0.2 min left
Read DEF 2,530,449 lines   42,173 lines/s   1 min elapsed   NETS 44,187/50,000   ~0.1 min left
End DEF parsing in 353.1227s
End DEF parsing in 353.8039s
End DEF parsing in 71.0839s
End DEF parsing in 71.4543s
End DEF parsing in 71.1481s
End DEF parsing in 72.0233s
End DEF parsing in 71.2512s
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Read DEF 1,308,673 lines   43,622 lines/s   1 min elapsed   NETS 23,650/50,000   ~0.6 min left
Read DEF 1,297,735 lines   43,254 lines/s   1 min elapsed   NETS 23,572/50,000   ~0.6 min left
Read DEF 1,370,056 lines   45,669 lines/s   0 min elapsed   NETS 18,962/50,000   ~0.8 min left
Read DEF 1,367,585 lines   45,586 lines/s   1 min elapsed   NETS 19,072/50,000   ~0.8 min left
Read DEF 1,361,855 lines   45,394 lines/s   1 min elapsed   NETS 18,889/50,000   ~0.8 min left
Read DEF 1,384,340 lines   46,145 lines/s   1 min elapsed   NETS 19,470/50,000   ~0.8 min left
Read DEF 1,357,782 lines   45,259 lines/s   1 min elapsed   NETS 18,658/50,000   ~0.8 min left
Read DEF 2,410,486 lines   40,172 lines/s   1 min elapsed   NETS 43,766/50,000   ~0.2 min left
Read DEF 2,408,829 lines   39,849 lines/s   1 min elapsed   NETS 43,877/50,000   ~0.2 min left
End DEF parsing in 64.4964s
Read DEF 2,534,330 lines   41,261 lines/s   1 min elapsed   NETS 43,500/50,000   ~0.2 min left
Read DEF 2,528,806 lines   41,229 lines/s   1 min elapsed   NETS 43,590/50,000   ~0.2 min left
Read DEF 2,526,928 lines   41,081 lines/s   1 min elapsed   NETS 43,534/50,000   ~0.2 min left
Read DEF 2,526,596 lines   41,377 lines/s   1 min elapsed   NETS 43,445/50,000   ~0.2 min left
Read DEF 2,524,265 lines   41,186 lines/s   1 min elapsed   NETS 43,354/50,000   ~0.2 min left
End DEF parsing in 70.2705s
End DEF parsing in 70.0977s
End DEF parsing in 70.413s
End DEF parsing in 70.0038s
End DEF parsing in 70.2854s
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Read DEF 1,335,518 lines   41,921 lines/s   1 min elapsed   NETS 25,883/50,000   ~0.5 min left
Read DEF 1,334,264 lines   41,804 lines/s   1 min elapsed   NETS 25,882/50,000   ~0.5 min left
Read DEF 1,344,622 lines   41,626 lines/s   1 min elapsed   NETS 22,906/50,000   ~0.7 min left
Read DEF 1,346,422 lines   41,518 lines/s   1 min elapsed   NETS 22,507/50,000   ~0.8 min left
Read DEF 1,349,450 lines   41,730 lines/s   1 min elapsed   NETS 22,955/50,000   ~0.7 min left
```

### Snapshot 4 — more slices finishing (62–71 s reads), heartbeats continue

```
Read DEF 1,345,394 lines   41,444 lines/s   1 min elapsed   NETS 22,640/50,000   ~0.7 min left
Read DEF 1,353,482 lines   41,231 lines/s   1 min elapsed   NETS 22,962/50,000   ~0.6 min left
Read DEF 2,607,762 lines   42,155 lines/s   1 min elapsed   NETS 48,583/50,000   ~0.0 min left
End DEF parsing in 62.7743s
Read DEF 2,605,741 lines   41,823 lines/s   1 min elapsed   NETS 46,299/50,000   ~0.1 min left
Read DEF 2,598,053 lines   41,616 lines/s   1 min elapsed   NETS 45,600/50,000   ~0.1 min left
Read DEF 2,611,382 lines   41,891 lines/s   1 min elapsed   NETS 46,299/50,000   ~0.1 min left
End DEF parsing in 68.0648s
End DEF parsing in 68.0935s
End DEF parsing in 68.6776s
End DEF parsing in 68.7023s
Read DEF 2,610,158 lines   41,545 lines/s   1 min elapsed   NETS 46,359/50,000   ~0.1 min left
End DEF parsing in 68.4494s
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Read DEF 1,351,249 lines   45,041 lines/s   1 min elapsed   NETS 26,590/50,000   ~0.4 min left
Read DEF 1,351,068 lines   45,034 lines/s   1 min elapsed   NETS 26,557/50,000   ~0.4 min left
Read DEF 1,315,405 lines   43,845 lines/s   1 min elapsed   NETS 26,450/50,000   ~0.5 min left
Read DEF 1,292,115 lines   43,066 lines/s   1 min elapsed   NETS 24,450/50,000   ~0.5 min left
Read DEF 1,291,851 lines   43,061 lines/s   1 min elapsed   NETS 24,635/50,000   ~0.5 min left
Read DEF 1,227,807 lines   42,427 lines/s   1 min elapsed   NETS 44,612/50,000   ~0.1 min left
Read DEF 2,500,180 lines   41,041 lines/s   1 min elapsed   NETS 47,574/50,000   ~0.1 min left
Read DEF 2,501,144 lines   41,463 lines/s   1 min elapsed   NETS 47,650/50,000   ~0.1 min left
Read DEF 2,505,449 lines   41,293 lines/s   1 min elapsed   NETS 47,493/50,000   ~0.1 min left
End DEF parsing in 62.6496s
End DEF parsing in 70.7129s
End DEF parsing in 62.583s
End DEF parsing in 63.1865s
End DEF parsing in 70.5869s
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Read DEF 2,498,349 lines   41,237 lines/s   1 min elapsed   NETS 47,673/50,000   ~0.0 min left
Read DEF 2,505,601 lines   40,997 lines/s   1 min elapsed   NETS 47,677/50,000   ~0.0 min left
End DEF parsing in 62.8364s
End DEF parsing in 63.3493s
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Read DEF 1,338,020 lines   41,784 lines/s   1 min elapsed   NETS 26,075/50,000   ~0.5 min left
Read DEF 1,360,837 lines   45,360 lines/s   1 min elapsed   NETS 18,591/50,000   ~0.8 min left
Read DEF 1,341,559 lines   41,794 lines/s   1 min elapsed   NETS 25,980/50,000   ~0.8 min left
Read DEF 1,337,538 lines   41,929 lines/s   1 min elapsed   NETS 26,181/50,000   ~0.5 min left
Read DEF 1,369,901 lines   45,696 lines/s   1 min elapsed   NETS 18,856/50,000   ~0.5 min left
Read DEF 1,346,849 lines   41,651 lines/s   1 min elapsed   NETS 26,018/50,000   ~0.5 min left
Read DEF 2,534,699 lines   40,983 lines/s   1 min elapsed   NETS 43,353/50,000   ~0.2 min left
Read DEF 2,612,593 lines   40,593 lines/s   1 min elapsed   NETS 48,990/50,000   ~0.0 min left
End DEF parsing in 65.3303s
End DEF parsing in 65.9455s
End DEF parsing in 65.9609s
Read DEF 2,614,766 lines   40,820 lines/s   1 min elapsed   NETS 48,814/50,000   ~0.0 min left
Read DEF 2,526,529 lines   41,220 lines/s   1 min elapsed   NETS 43,307/50,000   ~0.2 min left
Read DEF 2,626,908 lines   40,445 lines/s   1 min elapsed   NETS 49,180/50,000   ~0.0 min left
Read DEF 2,631,170 lines   40,385 lines/s   1 min elapsed   NETS 49,188/50,000   ~0.0 min left
End DEF parsing in 71.0304s
End DEF parsing in 65.8323s
```

### Snapshot 5 — heartbeats to the end; the two 13-min slices still running

```
End DEF parsing in 70.4714s
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Read DEF 2,616,191 lines   40,256 lines/s   1 min elapsed   NETS 48,899/50,000   ~0.0 min left
End DEF parsing in 66.0629s
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
End DEF parsing in 19.3317s
End DEF parsing in 19.2385s
End DEF parsing in 19.4515s
End DEF parsing in 19.2975s
End DEF parsing in 19.3426s
Load DEF file lx956c_ioe
Read DEF 58,681,090 lines   75,233 lines/s   13 min elapsed   SPECIALNETS 11,096/11,096   ~0.0 min left
End DEF parsing in 19.3426s
Load DEF file lx956c_ioe
Read DEF 59,903,470 lines   74,067 lines/s   13 min elapsed   NETS 23,057/38,904   ~0.3 min left
Read DEF 1,351,545 lines   40,949 lines/s   1 min elapsed   NETS 22,811/50,000   ~0.7 min left
Read DEF 1,347,427 lines   41,296 lines/s   1 min elapsed   NETS 22,506/50,000   ~0.7 min left
End DEF parsing in 829.6177s
Read DEF 2,598,003 lines   41,234 lines/s   1 min elapsed   NETS 45,973/50,000   ~0.1 min left
Read DEF 2,587,109 lines   41,308 lines/s   1 min elapsed   NETS 45,375/50,000   ~0.1 min left
End DEF parsing in 69.0185s
End DEF parsing in 69.1281s
Load DEF file lx956c_ioe
Read DEF 1,308,204 lines   43,603 lines/s   1 min elapsed   NETS 23,594/50,000   ~0.6 min left
Load DEF file lx956c_ioe
Read DEF 1,294,277 lines   43,139 lines/s   1 min elapsed   NETS 24,483/50,000   ~0.5 min left
Read DEF 2,403,466 lines   39,735 lines/s   1 min elapsed   NETS 43,368/50,000   ~0.2 min left
Read DEF 1,283,406 lines   42,779 lines/s   1 min elapsed   NETS 24,403/50,000   ~0.5 min left
Read DEF 2,492,245 lines   41,498 lines/s   1 min elapsed   NETS 47,389/50,000   ~0.1 min left
Read DEF 2,496,464 lines   41,205 lines/s   1 min elapsed   NETS 47,497/50,000   ~0.1 min left
End DEF parsing in 63.0575s
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Load DEF file lx956c_ioe
Read DEF 1,339,295 lines   41,666 lines/s   1 min elapsed   NETS 25,895/50,000   ~0.5 min left
Read DEF 1,335,814 lines   41,702 lines/s   1 min elapsed   NETS 25,962/50,000   ~0.5 min left
Read DEF 1,335,611 lines   42,116 lines/s   1 min elapsed   NETS 25,842/50,000   ~0.5 min left
Read DEF 2,615,205 lines   40,884 lines/s   1 min elapsed   NETS 48,892/50,000   ~0.0 min left
Read DEF 2,611,456 lines   40,643 lines/s   1 min elapsed   NETS 48,958/50,000   ~0.0 min left
End DEF parsing in 65.2689s
Load DEF file lx956c_ioe
Read DEF 1,337,187 lines   44,572 lines/s   1 min elapsed   NETS 26,320/50,000   ~0.4 min left
Read DEF 2,563,532 lines   41,350 lines/s   1 min elapsed   NETS 44,556/50,000   ~0.1 min left
Load DEF file lx956c_ioe
Read DEF 1,359,348 lines   45,311 lines/s   1 min elapsed   NETS 18,707/50,000   ~0.8 min left
Read DEF 1,341,757 lines   44,723 lines/s   1 min elapsed   NETS 22,359/50,000   ~0.6 min left
Read DEF 2,507,758 lines   40,835 lines/s   1 min elapsed   NETS 44,415/50,000   ~0.1 min left
End DEF parsing in 68.3003s
Load DEF file lx956c_ioe
Read DEF 1,316,184 lines   43,871 lines/s   1 min elapsed   NETS 24,844/50,000   ~0.5 min left
Read DEF 2,522,335 lines   42,038 lines/s   1 min elapsed   NETS 47,879/50,000   ~0.0 min left
Load DEF file lx956c_ioe
End DEF parsing in 61.8395s
```

### Snapshot 6 — routing stage done, `metal-summary`, final warnings

```
Read DEF 1,342,918 lines   41,927 lines/s   1 min elapsed   NETS 26,087/50,000   ~0.5 min left
Read DEF 2,630,626 lines   40,604 lines/s   1 min elapsed   NETS 49,231/50,000   ~0.0 min left
End DEF parsing in 65.3377s
Load DEF file lx956c_ioe
End DEF parsing in 19.0728s
INFO vlsi_viewer.metal: lx956c_ioe: 5 non-default rule(s)
INFO vlsi_viewer.metal: metal: stage routing             1780.64s  249,067,809 shape(s), 373,423,631 point(s)    rss 2,372 MB
INFO vlsi_viewer.metal: metal: stage grids                 0.00s    rss 2,372 MB
INFO vlsi_viewer.metal: metal: 56375666 shape(s) measured and handed to the rasteriser
INFO vlsi_viewer.metal: metal: 108844474 via point(s) omitted (no wire area)
INFO vlsi_viewer.metal: metal: 11796228 non-preferred jog(s) shorter than a track pitch dropped
INFO vlsi_viewer.metal: metal: 8777752 of the measured shape(s) are 45-degree segments that rasterise through shapely rather than rectangles
INFO vlsi_viewer.metal: metal: 72051441 block(s) on layers outside the requested range were skipped
INFO vlsi_viewer.metal: metal:summary: {"blockage": {"fallback_layers": 4, "fallback cells": 0, "ignored cells": [], "ignored layers": {}, "obs cells": 89, "obs layers": [0, 1, 2]}, "unknown_layers": {}, "design": "lx956c_ioe", "die um": [1060.2, 1226.64], "filtered_layers": ["ALPA", "M1", "TM1", "TM2"], "gc_counts": [21209, 1928, 231], "gc s": 3.72, "grid": [123, 107], "grid size um": 10.0, "input text": {"forms": 249067089, "layers_used": 12, "line": 284908024, "points": 373423631, "points_max": 2, "statement_chars_max": 58549358}, "defs": [  {  "lines": 2108,  "mftime": 1788556810,  "path": "/tmpdata/LinxCore950_PD_N3_t/user/l00922843/IOE/20.PR_Lx956_ioe/TAG0825_FC_inn25_seqMerge/DATAOUT/lx956c_ioe.def.gz"  }], "lefts": 221, "tech_lefts": [  {  "mtime": 1771999514,  "path": "/tmpdata/LinxCore950_PD_N2_t/user/data/LX950/N43/lib/lef/HN3J30R_575GT228H_1P14M_4DPM_Q1_3Q2_2Q3_2B_2TMa_ALPA2_M3_P40_P42_V2_3mask_DTCO_L8_Vn.lef"  }], "layers": [ {  "direction": "VERTICAL",  "name": "M2",  "pitch um": 0.038,  "unusable": false,  "width um": 0.013  }, {  "direction": "HORIZONTAL",  "name": "M3",  "pitch um": 0.04,  "unusable": true,  "width um": 0.024  }, {  "direction": "VERTICAL",  "name": "M4",  "pitch um": 0.076,  "unusable": false,  "width um": 0.038  }, {  "direction": "HORIZONTAL",  "name": "M5",  "pitch um": 0.076,  "unusable": true,  "width um": 0.038  }, {  "direction": "VERTICAL",  "name": "M6",  "pitch um": 0.076,  "unusable": true,  "width um": 0.038  }, {  "direction": "VERTICAL",  "name": "M7",  "pitch um": 0.076,  "unusable": true,  "width um": 0.048  }, {  "direction": "HORIZONTAL",  "name": "B1",  "pitch um": 0.126,  "unusable": true,  "width um": 0.062  }, {  "direction": "HORIZONTAL",  "name": "B2",  "pitch um": 0.126,  "unusable": true,  "width um": 0.062  }, {  "layers_not_in_tech": 4,  "params": {"macro_block_layers": 4, "max_layer": 12, "min_layer": 2, "min_segment": null, "top": null, "peak_rss_mb": 5056,  "rss_mb": 2372,  "shapes": [ {  "degenerate": 0,  "diagonals": 8777752,  "emitted": 56375666,  "filtered": 72051441,  "jogs": 108844474,  "polygon_edges": 0,  "total": 249067809,  "unknown": 0,  "unusable": 0  } ]  },  "stages_s": {"blockage": 9.62,  "capacity": 0.75,  "cell-index": 11.24,  "components": 44.19,  "grids": 0,  "routing": 1780.64,  "start": 0.0,  "tech-lef": 0.02}  },  "version": "0.1.0",  "warnings": ["1 cell type(s) are neither in the LEF nor a block, so they contribute no footprint: tensor_remote_npnpv100"]}
WARNING vlsi_viewer.cli: metal: 1 cell type(s) are neither in the LEF nor a block, so they contribute no footprint: tensor_remote_npnpv100
WARNING vlsi_viewer.cli: metal: 187 cell(s) carry signal wire on a layer a macro obstructs there, so their utilisation is not a congestion reading
```

## 2. Key numbers (from the log lines as captured)

### Timeline

| event | time |
|---|---|
| submitted (PENDING) | 12:40:07.328 |
| RUNNING on `metalcd233-hs` | 12:40:10.314 — queue wait **~3 s** |
| stage `components` done (DEF pass 1, 3,355,697 instances) | +44.19 s |
| stage `lef-index` done (221 LEF files, 17,385 cells) | +11.24 s |
| stage `capacity` done (123×107 grid) | +0.75 s |
| stage `blockage` done (89 OBS macros) | +9.62 s |
| stage `routing` done (8 workers) | **+1,780.64 s** |
| stage `grids` done | +0.00 s |
| **job finished ≈ 13:11** | **total ≈ 1,849 s ≈ 30.8 min** |

### Where the time went

From the `stages_s` object of the `metal-summary` line (sum 1,846.44 s of compute time):

| stage | seconds | share |
|---|---|---|
| `tech-lef` | 0.02 | 0.00 % |
| `components` (DEF pass 1) | 44.19 | 2.39 % |
| `lef-index` | 11.24 | 0.61 % |
| `capacity` | 0.75 | 0.04 % |
| `blockage` | 9.62 | 0.52 % |
| `routing` (DEF pass 2, 8 workers) | **1,780.64** | **96.44 %** |
| `grids` | 0 | 0.00 % |

Routing is still the whole job, but 8 workers took it from 5,940.63 s to 1,780.64 s
(**3.34x** vs the 09-14 single-core run of the same design — the 09-14 opinion section had
predicted ~3.3x / ~33 min at 8 workers).

### Per-worker reads observed

Each worker's slice read runs from ~19 s to 829.6 s; most finish in ~50–72 s at
~40 k lines/s over ~2–2.6 M-line slices. Two slices (the SPECIALNETS-heavy ones,
~18–20 M lines each, running 5–6 min) and two ~53–60 M-line slices (13 min at ~75 k lines/s)
dominate the tail: 353.12 s, 353.80 s and 829.62 s are the largest single-read times
captured. The heartbeats carry per-worker net denominators of 38,905 and 50,000, i.e. the
split is by net count, not by line range.

## 3. Transcription notes and facts worth verifying

- The "15,544,355 lines 42,403 lines/s 1 min elapsed" line (snapshot 3) breaks
  monotonicity against its own rate (~2.5 M lines in one minute at that rate); transcribed
  as shown, almost certainly 2,554,435.
- The capacity line reads "123 x 107 grid @ 18 um" while the summary says
  `"grid size um": 10.0`; one is a misread (the 09-14 run printed "10 um" for the same
  grid; a 123×107 grid over a 1060.2×1226.6 um die is ~8.6×11.5 um cells).
- The stage line prints "stage lef-index" while the summary key is "cell-index" (11.24 s
  either way).
- `"defs": [{"lines": 2108, ...}]` matches the "2108 Mb of DEF (uncompressed); 8
  worker(s)" line; the key is almost certainly `bytes` (the 09-14 summary spelled it
  `"bytes": 2108.5`).
- The summary `layers` array has 8 entries (M2–M7, B1, B2) with `"layers_used": 12`, while
  the stage line says "layers M2..B2 (11 of 15)" — the array apparently lists only layers
  that carried shape data. Note the field is now `"unusable"` where 09-14 printed
  `"usable"`.
- The shape-class counters (emitted 56,375,666; via 108,844,474; jogs 11,796,228;
  diagonals 8,777,752; filtered 72,051,441; unknown 0; degenerate 0) sum to
  257,845,561 = total 249,067,809 **+ diagonals 8,777,752**: the 45-degree segments are
  a subset of the measured shapes, so the classes are exhaustive once that overlap is
  subtracted.
- The `input_text` object reads `{"forms": 249067089, "line": 284908024, "points":
  373423631, "points_max": 2, "statement_chars_max": 58549358}` — `forms` equals the total
  shape count, and 58,549,358 was `statement_lines_max` in the 09-14 summary. The deployed
  summary revision has renamed/reshuffled fields again (as with `stages` vs `stages_s` on
  09-14); the line count is 284,908,024 here vs 284,908,802 on 09-14 (newer file at the
  same path).
- GC is 3.72 s with counts [21,209, 1,928, 231] — far below the 09-14 run's 147.25 s /
  1.76 M gen-0 collections, consistent with smaller per-worker in-memory work.
- Per-worker net denominators are 38,905 / 50,000 (38,904 in two lines): total nets of
  this DEF version are on the order of ~390 k, vs 3,235,531 in the 09-14 DEF version —
  the 0825-tagged file at the same path is a substantially different netlist version
  (also: 11,096 SPECIALNETS vs 88,763).
