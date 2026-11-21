# Metal mode on a real design — run log and GUI snapshot
Five snapshots from one real-design run of the metal-density mode, taken 2026-09-13:
four terminal windows of the job log (submitted 14:53, running on `wha1cd082-hs`) and
one window of the resulting GUI. The design is `lx956c_ioe` (die 1060.2 × 1226.64 µm,
18 layers, 123×107 grid @ 10 µm, 3,355,697 placed instances, 17,385 macros from 221 LEF
files), fed by a routed DEF of ~30 million lines.

---

## 1. Run log (verbatim)

The four snapshots below repeat the log text exactly as shown. They were captured at
different moments of the same run, so they are not necessarily line-continuous between
snapshots.

### Snapshot 1 — job submission, tech-LEF scan, first DEF pass, start of LEF parse

```
[dsu22843@wha1cd03-hs: /tmpdata/LinxCores950_PD_N3_t/user/l00922843/design_browser [2026/09/13 14:53:00] >
dsb -A root_um_07000 -q metal -R 'cpu=4;mem=20000' -I "venv/bin/python3 VLSI_design_browser-master/main.py metal --def /tmpdata/LinxCores950_PD_N3_t/user/l00922843/IOE/20.PR.lx956_ioe/TA08025_FC_inn25_seqMerge/DATAOUT/lx956c_ioe.def.gz --lef lefs/* --tech-lef /tmpdata/LinxCores950_PD_N2_t/user/data/LX950/N+3/lib/lefl/HN3730R_5756T228H_1P14M_4DPM_Q1_3Q2_2Q3_2B_2Tma_ALPA2_M3_P40_P42_V2_3mask_DTCD_L8_Vn.lef"
JOBID       MESSAGE
1643737850  Submit job successfully.

2026-09-13 14:53:27.310 ==> job state changed to: PENDING

2026-09-13 14:53:29.016 ==> job state changed to: RUNNING
Job is running on host wha1cd082-hs

INFO vlsi_viewer.cli: metal: reading 1 DEF file(s)
Start parsing tech lef in 0.025s
INFO vlsi_viewer.parsers.routing: tech: 18 routing layer(s) of 63 layer(s), 0 unusable
INFO vlsi_viewer.cli: metal: reading block outlines
Load DEF file /tmpdata/LinxCores950_PD_N3_t/user/l00922843/IOE/20.PR.lx956_ioe/TA08025_FC_inn25_seqMerge/DATAOUT/lx956c_ioe.def.gz
Read DEF 1000000 lines
Read DEF 2000000 lines
Read DEF 3000000 lines
Read DEF 4000000 lines
Read DEF 5000000 lines
Read DEF 6000000 lines
End DEF parsing in 25.16725s
INFO vlsi_viewer.parsers.convert: def: /tmpdata/LinxCores950_PD_N3_t/user/l00922843/IOE/20.PR.lx956_ioe/TA08025_FC_inn25_seqMerge/DATAOUT/lx956c_ioe.def.gz -> 3355697 instance(s) (dropped 0 filler, skipped 0 upcasted), 8 boundary point(s)
INFO vlsi_viewer.loader: Loaded block 'lx956c_ioe' with 3355697 instance(s) from <in-memory>
Start parsing Lef files
Total 221 LEF files
Parsing lefs/hir1zh228_ckmesh_1p14m_4dpm_q1_3q2_2q3_2b_2tma_onlypr.lef
Parsing lefs/hir1zh228_ckmesh_1p14m_4dpm_q1_3q2_2q3_2b_2tma_onlypr.lef.cell_info.json
Parsing lefs/hir1zh228l0p57sdB_aic_lvt_onlypr.lef
Parsing lefs/hir1zh228l0p57sdB_aic_svt_onlypr.lef
Parsing lefs/hir1zh228l0p57sdB_aic_ulvt_onlypr.lef
Parsing lefs/hir1zh228l0p57sdB_base_lvt_onlypr.lef
Parsing lefs/hir1zh228l0p57sdB_baseopt_lvt_onlypr.lef
Parsing lefs/hir1zh228l0p57sdB_baseoptm_lvt_onlypr.lef
Parsing lefs/hir1zh228l0p57sdB_baseoptm_svt_onlypr.lef
Parsing lefs/hir1zh228l0p57sdB_baseopt_ulvt_onlypr.lef
Parsing lefs/hir1zh228l0p57sdB_base_svt_onlypr.lef
Parsing lefs/hir1zh228l0p57sdB_base_ulvt_onlypr.lef
Parsing lefs/hir1zh228l0p57sdB_basevia_lvt_onlypr.lef
Parsing lefs/hir1zh228l0p57sdB_basevia_svt_onlypr.lef
Parsing lefs/hir1zh228l0p57sdB_basevia_ulvt_onlypr.lef
Parsing lefs/hir1zh228l0p57sdB_cklvl_lvt_onlypr.lef
Parsing lefs/hir1zh228l0p57sdB_cklvl_ulvt_onlypr.lef
```

### Snapshot 2 — first LEF pass done; capacity measurement starts a second LEF pass

```
Parsing lefs/HIS6LC956CSCRAMTP64X64M1HSB.lef
Parsing lefs/HIS6LC956CSCRAMTP64X64M11HSB.lef
End parsing 221 LEF file in 11.343s
INFO vlsi_viewer.parsers.convert: lef: 17385 macro(s) from 221 file(s)
INFO vlsi_viewer.loader: Loaded 17385 cell(s) from <in-memory>
INFO vlsi_viewer.cli: metal: measuring capacitance
Start parsing Lef files
Total 221 LEF files
Parsing lefs/hir1zh228_ckmesh_1p14m_4dpm_q1_3q2_2q3_2b_2tma_onlypr.lef
Parsing lefs/hir1zh228_ckmesh_1p14m_4dpm_q1_3q2_2q3_2b_2tma_onlypr.lef.cell_info.json
Parsing lefs/hir1zh228l0p57sdB_aic_lvt_onlypr.lef
Parsing lefs/hir1zh228l0p57sdB_aic_svt_onlypr.lef
Parsing lefs/hir1zh228l0p57sdB_base_lvt_onlypr.lef
Parsing lefs/hir1zh228l0p57sdB_baseopt_lvt_onlypr.lef
Parsing lefs/hir1zh228l0p57sdB_baseoptm_lvt_onlypr.lef
Parsing lefs/hir1zh228l0p57sdB_baseoptm_svt_onlypr.lef
Parsing lefs/hir1zh228l0p57sdB_base_svt_onlypr.lef
```

### Snapshot 3 — second LEF pass done; routing read starts on the DEF

```
Parsing lefs/HIS6LC956CSCRAMTP32X96M1HSB.lef
Parsing lefs/HIS6LC956CSCRAMTP64X116M1HSB.lef
Parsing lefs/HIS6LC956CSCRAMTP64X120M1HSB.lef
Parsing lefs/HIS6LC956CSCRAMTP64X160M1HSB.lef
Parsing lefs/HIS6LC956CSCRAMTP64X40M1HSB.lef
Parsing lefs/HIS6LC956CSCRAMTP64X48M1HSB.lef
End parsing 221 LEF file in 10.16s
INFO vlsi_viewer.metal: metal: blockage from 89 macro(s) declaring OBS over 4 layer(s); 0 fall back to the bottom 4 layer(s); 0 declare nothing significant
INFO vlsi_viewer.metal: metal: reading routing
Load DEF file /tmpdata/LinxCores950_PD_N3_t/user/l00922843/IOE/20.PR.lx956_ioe/TA08025_FC_inn25_seqMerge/DATAOUT/lx956c_ioe.def.gz
Read DEF 1000000 lines
Read DEF 2000000 lines
Read DEF 3000000 lines
Read DEF 4000000 lines
Read DEF 5000000 lines
Read DEF 6000000 lines
```

### Snapshot 4 — routing read done; run finishes with its warnings

```
Read DEF 27000000 lines
Read DEF 27500000 lines
Read DEF 28000000 lines
Read DEF 28500000 lines
Read DEF 29000000 lines
Read DEF 29500000 lines
Read DEF 30000000 lines
End DEF parsing in 7005.1248s
INFO vlsi_viewer.metal: lx956c_ioe: 5 non-default rule(s)
INFO vlsi_viewer.metal: metal: 124711987 via point(s) omitted (no wire area)
INFO vlsi_viewer.metal: metal: 12964342 non-preferred jog(s) shorter than a track pitch dropped
WARNING vlsi_viewer.cli: metal: 1 cell type(s) are neither in the LEF nor a block, so they contribute no footprint: tsenor_remote_npIppv100
WARNING vlsi_viewer.cli: metal: 187 cell(s) carry signal wire on a layer a macro obstructs there, so their utilisation is not a congestion reading
WARNING vlsi_viewer.cli: metal: 4539783 shape(s) on layers the tech LEF does not define were skipped
WARNING vlsi_viewer.cli: metal: 4517711 shape(s) had no extent and were skipped
```

---

## 2. GUI window — `VLSI Hierarchy Analyzer (on wha1cd082-hs)`

Single window, dark theme, three columns: a left **Cell detail** readout, a central
utilisation map of the die, and a right control panel (**Net class** + **Routing
layers**). A toolbar runs along the top and a status bar along the bottom.

### Window title

`VLSI Hierarchy Analyzer (on wha1cd082-hs)` — the parenthetical names the compute host
the job ran on (the window is rendered on that host).

### Top toolbar (left to right)

- `Min:` spin box, value `0.000` and `Max:` spin box, value `1.000` — the range of the
  colour ramp (0 = empty, 1 = every track in a bin consumed).
- `Auto` button — stretches the ramp to the map's occupied range without changing what
  the colours measure.
- `Fit` button — fits the whole die into the view.
- Live text readout to their right: `peak 0.795   full = 1.000` — the peak cell
  utilisation of the current net class (0.795) beside the fixed saturation value, so
  the absolute scale stays visible even when `Auto` has stretched the ramp.

### Left panel — Cell detail

The arithmetic behind the colour under the mouse. Shown content:

- Header: `cell (19,24) x=195 y=245` — the hovered grid cell's (column, row) index and
  its µm position on the die.
- A small monospace table, one row per *checked* routing layer, headings `layer`, `D/C`,
  `U`:

  | layer | D/C | U |
  |---|---|---|
  | `M5 *` (bold) | 78.8/150 | 0.525 |
  | `M7` | 74.9/150 | 0.500 |
  | `FM1` | 42.3/100 | 0.423 |
  | `B1` | 51.1/120 | 0.427 |

  D = demand (µm of routed wire), C = capacity (µm of routable area), U = D/C.
  `M5` carries a `*` and is bolded as the **bottleneck** — the checked layer with the
  highest utilisation in this cell.
- `sum(D)/sum(C) = 0.4755` — the group utilisation, i.e. what the map colour encodes.
- `247/520` — total demand over total capacity across the checked layers.
- `H max 0.525   V max 0.000` — the peak utilisation of the horizontal and vertical
  checked layers separately.
- `escapable` — the verdict word: vertical layers are empty, so a full horizontal cell
  can still be routed by escaping upward (it is not a dead cell).
- `capacity: less each macro's own OBS` — note on what took capacity away: the macros'
  own OBSTRUCTION blockage geometry (here no fallback-to-bottom-layers guessing is in
  play, matching the log's "0 fall back").

### Centre — utilisation map

- The die rasterised on a 123×107 grid (10 µm bins) over a black background; the die
  outline — taller than wide (1226.64 µm × 1060.2 µm), with a couple of notched corners —
  is bordered by a faint blue frame.
- Each bin is coloured by group utilisation on the INNOVUS-style ramp
  dark blue → blue → cyan → green → yellow → orange → red (0 → 1).
- The high-density region (green/yellow/red) is concentrated in the centre and right
  half of the die; a compact red/orange hot spot sits near the top-left corner; the
  bottom-left and far margins are dark blue (near-empty).
- A thin white rectangle outlines one cell near the middle of the die — the cell the
  cursor is reading out (consistent with the `(19,24)` header and the status bar).
- A vertical colour bar sits at the right edge of the canvas, labelled `0`, `0.25`,
  `0.5`, `0.75`, `1` bottom to top.

### Right panel

- **Net class** group box: a combo box set to `Signal + power` (other scopes: signal
  only / power only).
- **Routing layers** group box:
  - buttons `All H`, `All V`, `None` for checking horizontal/vertical/none of the layers;
  - a table with columns: (checkbox), `layer`, `W/S/P` (width / spacing / pitch, µm),
    `dir` (H or V), `U` (whole-die mean utilisation of that layer under the current net
    class), listed bottom of stack to top — 18 rows:

  | | layer | W/S/P (µm) | dir | U |
  |---|---|---|---|---|
  |  | M1 | 0.016 / 0.016 / 0.02 | H | 0.027 |
  |  | M2 | 0.019 / 0.019 / 0.038 | V | 0.187 |
  |  | M3 | 0.02 / 0.02 / 0.04 | H | 0.302 |
  |  | M4 | 0.024 / 0.02 / 0.044 | V | 0.229 |
  | ✔ | M5 | 0.038 / 0.076 / 0.076 | V | 0.471 |
  |  | M6 | 0.038 / 0.076 / 0.076 | V | 0.397 |
  | ✔ | M7 | 0.038 / 0.076 / 0.076 | H | 0.440 |
  |  | M8 | 0.038 / 0.076 / 0.076 | V | 0.303 |
  | ✔ | FM1 | 0.048 / 0.048 / 0.096 | H | 0.383 |
  |  | FM2 | 0.048 / 0.048 / 0.096 | V | 0.291 |
  | ✔ | B1 | 0.062 / 0.089 / 0.126 | H | 0.499 |
  |  | B2 | 0.062 / 0.089 / 0.126 | V | 0.462 |
  |  | TM1 | 0.36 / 0.36 / 0.72 | H | 0.000 |
  |  | TM2 | 0.36 / 0.36 / 0.72 | V | 0.000 |
  |  | ALPA | 1.8 / 2.25 / 4.95 | H | 0.000 |
  |  | M2_FB1 | 0.019 / 0.019 / 0.038 | V | 0.000 |
  |  | M3_FB1 | 0.019 / 0.029 / 0.04 | H | 0.000 |
  |  | M4_FB1 | 0.024 / 0.02 / 0.044 | V | 0.000 |

  Only `M5`, `M7`, `FM1`, `B1` are checked in this snapshot — the map therefore shows
  the group utilisation of those four layers (`G:B1,FM1,M5,M7` in the status bar). The
  `TM1/TM2/ALPA` and `M*_FB1` rows read 0.000: no wire was measured on those layers in
  this net class.

### Status bar (bottom)

- Left: `Metal mode · 123×107 grid @ 10 um · die 1060.2×1226.64 um · 18 layers · top lx956c_ioe`
- Right (hover readout): `x=190.59 y=241.61   G:B1,FM1,M5,M7[24,19] = 0.476` — the
  cursor's µm position and the checked-layer group value at grid cell [row 24, column
  19]. It is the same cell the Cell detail panel describes: `cell (19,24)` with
  `sum(D)/sum(C) = 0.4755` (the group value rounded to three digits is 0.476).

### Glossary of the abbreviations

| Symbol | Meaning |
|---|---|
| D / C / U | demand / capacity / utilisation (D/C) per layer, in µm |
| W / S / P | layer width / spacing / pitch, in µm |
| H / V | routing direction: horizontal / vertical |
| `G:B1,FM1,M5,M7` | group of the checked layers, alphabetically sorted |
| `peak …  full = 1.000` | max bin utilisation / the saturation value of the ramp |
| `*` | bottleneck layer (highest U among the checked ones) |
| `escapable` | at least one direction (here vertical) is still free in the cell |
