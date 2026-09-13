# Real DEF/LEF sources, and which ones are worth testing against

The real-world files this project has found during its web research, with what each is worth,
and the reasoning behind the five that are now vendored in `sample_data/real/`.

## Why this exists

Everything under `sample_data/` was synthesized by a committed `generate_*.py`. That is fine for
the shape of a map and useless for parser correctness: this project's worst parser bug — nine of
OpenROAD's ten Nangate45 routing layers arriving with `spacing == 0.0`, because their rules live
in a `SPACINGTABLE` block and there is no plain `SPACING` anywhere on them — was invisible against
the sample and appeared the moment a real tech LEF was read. The same exercise refuted two
behaviours that had been *planned* from tutorials (`routeWidth 0` as "use the layer width", glued
`*` coordinates), and found that half of all parsed segments in a routed DEF are via points.

Those measurements were made on files fetched into a scratch directory and thrown away, so the
tests that cite them inline stanzas instead. `sample_data/real/` and `tests/test_real_samples.py`
make them re-checkable.

## Tech LEF / PDK

| source | node | licence | size | worth |
|---|---|---|---|---|
| **ORFS `flow/platforms/nangate45/lef/NangateOpenCellLibrary.tech.lef`** | 45 nm | Nangate OCL — non-commercial, redistribution permitted with the licence text, benchmarking against other libraries prohibited | 19 KB | 22 layers, 10 routing; `SPACINGTABLE` on 9; metal1 spacing 0.065; metal2 `f = 0.737` — **the file that found the worst bug, and the reason the capacity normalisation exists** |
| **ORFS `flow/platforms/sky130hd/lef/sky130_fd_sc_hd.tlef`** | 130 nm | Apache-2.0 | 18 KB | layers named `li1`, `met1`…`met5` — name variance nothing else here has; two real `W + S < P` cases (`li1` 0.739, `met1` 0.824) |
| **`The-OpenROAD-Project/asap7sc7p5t_27` `techlef_misc/asap7_tech_4x_201209.lef`** | 7 nm predictive | BSD-3-Clause | 21 KB | **the closest openly licensed analogue to a modern foundry node**; 10 layers `M1`–`M9` + `Pad`, pitches down to 0.144; another `W + S < P` case |
| ORFS `flow/platforms/asap7/`, `gf180mcu`, IHP `sg13g2` | various | Apache-2.0 / BSD | KB–MB | unexamined; `gf180mcu` would add a second non-`M<digit>` naming scheme and IHP a 130 nm BiCMOS stack |

## Designs / DEFs

| source | routed? | licence | worth |
|---|---|---|---|
| **OpenROAD `test/gcd_nangate45.def`** | **yes** | Apache-2.0 | the only real *routed* DEF in reach: 497 nets, 2 SPECIALNETS (POWER/GROUND), 734 components, 2,504 via points, `*` coordinate reuse, 32.74 µm die |
| OpenROAD `src/drt/test/gcd_nangate45_preroute.def` | no — placed + PDN | Apache-2.0 | the same design before signal routing; `+ SHAPE FOLLOWPIN`/`STRIPE` only |
| OpenROAD `src/gpl/test/*.def` (e.g. `simple10.def`) | no — placed | Apache-2.0 | ROW/TRACK/component geometry for physical mode |
| ORFS `flow/designs/{nangate45,asap7,sky130hd}/*` | needs `make` | Apache-2.0 | a real `6_final.def`, but results are deliberately not committed — a whole toolchain for one file the gcd DEF already provides |
| TILOS MacroPlacement `Flows/<pdk>/<design>/` | partly | per-file | real chips (Ariane, MemPool, NVDLA, BlackParrot) on all three PDKs; MBs each, and the routed results are the interesting part |
| ISPD 2018 contest | `sample` only (11 nets) | research use, from ispd.cc | LEF + DEF + guide; **power, NDRs and timing were removed**, so it is a placement fixture, not a density one |

## Gaps that no open source fills

- **`NONDEFAULTRULES`.** ORFS uses them for clock nets, but its results are not published, and the
  ISPD contest stripped them. The parser's NDR support is tested against a forum-derived fixture
  only, and the real gcd DEF contains none.
- **`+ POLYGON`.** The gcd DEF has none. The parser's "edges cannot be reassembled into a filled
  shape" limit has no real-file coverage.
- **A modern-node routed DEF.** ASAP7 gives the tech LEF but no routed design; the closest real
  input for an N7-class stack remains the companion LinxCore950 PD flow
  (`dev_plan/code_sample/extractCellInfo.py`), which is not redistributable.

## Recommendation, and what was done

Five files, 616 KB, in `sample_data/real/` — see `sample_data/real/PROVENANCE.md` for revisions,
hashes and licences:

| file | why it earned its place |
|---|---|
| `nangate45/NangateOpenCellLibrary.tech.lef` | the worst parser bug came from here |
| `nangate45/NangateOpenCellLibrary.macro.mod.lef` | real `CLASS` modifiers, 107 real `OBS` blocks, real cell sizes |
| `nangate45/gcd_nangate45.def` | the only real routed DEF; both via-point forms, `*` reuse, a real power grid |
| `asap7/asap7_tech_4x_201209.lef` | modern-node stack, permissively licensed |
| `sky130/sky130_fd_sc_hd.tlef` | layer-name variance and two more `W + S < P` cases |

Deliberately **not** included: the ISPD18 test cases (unrouted, stripped, large, contest terms),
the MacroPlacement tarballs (MBs of bulk for coverage the gcd DEF already gives), a placed DEF
(the gcd DEF is placed *and* routed), and a `6_final.def` built by running ORFS (a full toolchain
for a file we already have).

The two Nangate45 files are the only ones with restrictive terms: the file itself says it is
"provided pursuant to a License Agreement containing restrictions on its use" and contains
"trade secrets". They are vendored because this repository is private — **remove
`sample_data/real/nangate45/` before publishing it.**

## What the vendored files changed

- `is_macro` read the whole `CLASS` string, so the 6 `CLASS CORE SPACER` fill cells plus one
  `CORE ANTENNACELL` and one `CORE WELLTAP` were all hard macros. A macro takes capacity away from
  the layers it blocks, and on the gcd design that removed **1 % of the block's bottom-layer
  capacity** (10.8 of 1071.9 µm²). The grammar is
  `CORE [FEEDTHRU|TIEHIGH|TIELOW|SPACER|ANTENNACELL|WELLTAP]`, so only the first word names the
  class. Fixed in `parsers/convert.py`, with a real-file assertion and an inline fixture in
  `tests/test_parsers_eda.py`.
- The comment in `parsers/DEF/defParser.py` claiming glued `*` coordinates "occur in real DEF"
  now says what the measurement says: zero occurrences, handled defensively.
- `README.md` and `dev_plan/metal_density_asbuilt.md` point at the directory.

## Two things to know before adding more real files

- **Fetch at a recorded revision and record the `sha256`.** Fetching from a default branch means
  the file can change under you; this repository pins `sample_data/real/** -text` in
  `.gitattributes` so the vendored bytes are the bytes that were hashed, on any platform.
- **Check the encoding.** `DefParser` opens DEFs with no encoding argument, so the locale decides:
  a single non-ASCII byte raises `UnicodeDecodeError` on a cp936 Windows box and would decode as
  mojibake on a UTF-8 CI. All five vendored files are pure ASCII, and a test asserts it.
