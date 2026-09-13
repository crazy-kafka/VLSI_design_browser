# Real files, vendored

Five unmodified files from three upstream projects, kept here so that the parser behaviour
this project was *measured* against can be re-checked on every run. Everything else under
`sample_data/` is synthesized by a committed `generate_*.py`; these are not.

They are stored byte-for-byte as fetched. `.gitattributes` pins `sample_data/real/** -text` so
no checkout converts their line endings and the `sha256` below stays meaningful on any platform.
The tests in `tests/test_real_samples.py` assert the properties listed here, so a file that is
replaced or re-fetched from a different revision fails loudly rather than quietly changing what
"the real file" means.

Total 616 KB.

---

## `nangate45/NangateOpenCellLibrary.tech.lef` — 19,485 B

| | |
|---|---|
| upstream | `The-OpenROAD-Project/OpenROAD-flow-scripts` |
| path | `flow/platforms/nangate45/lef/NangateOpenCellLibrary.tech.lef` |
| revision | `244d277a3711` (latest commit touching this path) |
| sha256 | `834a79295054cd4209178d1bade67c353863c47bb4b3c22ee38b862b7cec37f2` |
| licence | Nangate Open Cell Library — see the warning below |

The file that found the worst parser bug in this project. Its nine upper routing layers declare
their spacing rules in a `SPACINGTABLE` block and **no plain `SPACING` at all**, so a parser that
only reads `SPACING` statements leaves `spacing == 0.0` on every one of them and the metric's
spacing expansion silently does nothing. `metal1` is the only layer with a plain clause.

Properties a test may rely on:

- 22 `LAYER` blocks, of which 10 are `TYPE ROUTING`; all 10 usable.
- `metal1` pitch 0.14, width 0.07, **spacing 0.065**; `metal2` 0.19 / 0.07 / 0.07; `metal3` 0.14;
  `metal4`–`metal6` 0.28; `metal7`–`metal8` 0.80; `metal9`–`metal10` 1.60.
- `f = (W + S) / P` is **0.964** on metal1, **0.737** on metal2, and 1.000 above — the reason the
  capacity normalisation exists at all. On metal2 it changes the reading by 36 %.

## `nangate45/NangateOpenCellLibrary.macro.mod.lef` — 255,903 B

| | |
|---|---|
| upstream | `The-OpenROAD-Project/OpenROAD-flow-scripts` |
| path | `flow/platforms/nangate45/lef/NangateOpenCellLibrary.macro.mod.lef` |
| revision | latest on `master` at the time of writing |
| sha256 | `a43aea339f12a57a63497783e508ba16f3da2dc056d3247dec7d99707c2dedef` |
| licence | Nangate Open Cell Library — see the warning below |

LEF 5.6. Passed to `build_metal` so that the design's cells resolve; it is what keeps the
"cell types neither in the LEF nor a block" warning away from the gcd run.

- 107 real `OBS` blocks. **This project does not parse `OBS`** — a macro is taken to block its
  whole outline — so the file is here to document that limit against real data rather than to
  exercise it.
- Every cell is `CLASS CORE`: no `CLASS BLOCK` macro, which is what makes the gcd run produce no
  stranded-cell warning.

## `nangate45/gcd_nangate45.def` — 300,205 B

| | |
|---|---|
| upstream | `The-OpenROAD-Project/OpenROAD` |
| path | `test/gcd_nangate45.def` |
| revision | `7cb0c0c1757c` (latest commit touching this path) |
| sha256 | `5eb7b2197a635df30ea97871b6b69cb5d64da919de8fb898b53bf8cf89bdeb66` |
| licence | Apache-2.0 (the OpenROAD repository) |

DEF 5.8, `DESIGN gcd`, `UNITS DISTANCE MICRONS 2000`, `DIEAREA ( 0 0 ) ( 65480 65480 )` —
32.74 µm square. The only real **routed** DEF this project has: placed and detailed-routed
output of the OpenROAD flow on Nangate45.

Contents, all verified:

| section | count |
|---|---|
| `COMPONENTS` | 734 |
| `PINS` | 54 |
| `SPECIALNETS` | 2 — `VDD` `+ USE POWER`, `VSS` `+ USE GROUND`, both connected as `( * VDD )` |
| `NETS` | 497, all `+ USE SIGNAL` |
| `TRACKS` | 20 |
| `NONDEFAULTRULES` | none |
| `POLYGON` | none |

What it exercises that nothing synthetic here does:

- **2,504 via points** = 2,438 single-point forms (`NEW metal1 ( 53770 55580 ) via1_7` — one
  point and a via name, no width field) **+ 66** zero-width shapes
  (`NEW metal2 0 + SHAPE STRIPE ( 62280 61600 ) via2_3_…`). Half of all parsed segments are
  these, and each must contribute no area *and take no end extension*, or every via becomes a
  phantom wire-width square.
- **`*` coordinate reuse**, 7 times, in the spaced form real tools write
  (`( 52630 55580 ) ( 53770 * )`) — the glued forms sometimes quoted in tutorials do not occur.
- 5 non-preferred jogs are dropped by the metric's pitch-length rule.
- `ROW`/`SITE` statements are present and are **not** parsed (a recorded limit of the vendored
  parser).

## `asap7/asap7_tech_4x_201209.lef` — 20,771 B

| | |
|---|---|
| upstream | `The-OpenROAD-Project/asap7sc7p5t_27` |
| path | `techlef_misc/asap7_tech_4x_201209.lef` |
| revision | `e270fbf483a2` (latest commit touching this path) |
| sha256 | `c0ef354be5c807f11950a81fef19cd8efc45b907d000c22eedfc424d557e9b97` |
| licence | BSD 3-Clause — "Copyright 2020 Lawrence T. Clark, Vinay Vashishtha, or Arizona State University" |

ASAP7, the 7 nm predictive PDK: the closest openly licensed analogue to a modern foundry node.
10 routing layers named `M1`–`M9` plus `Pad`, all usable, pitches 0.144–0.4 µm.

`M2` is the only layer here - and in any vendored file - whose two `PITCH` values differ:
`PITCH 0.180 0.144` on a `HORIZONTAL` layer. The pitch a layer's tracks are separated by is the
*y* value, 0.144, which its own quoted `LEF58_PITCH` payload agrees with
(`PITCH 0.144 FIRSTLASTPITCH 0.180`), and `0.072 + 0.072` equals it exactly — `f = 1.0`. Reading
the x value gave 0.8 and overstated the layer's capacity; that was the old behaviour.

**Known consequence, recorded rather than fixed: `Pad` has `f = 25.5`.** It declares
`WIDTH 0.16`, `PITCH 0.32` and a spacing *table* whose values are 8 and 12 µm
(`PARALLELRUNLENGTH 0 47.999` / `WIDTH 0 8 8` / `WIDTH 47.999 8 12`). All three come straight out
of the file: a pad plane is not a track system, and its `PITCH` is the distance between pads
rather than between routing tracks. The metric's `(W + S) / P` is meaningless for it, and since
its capacity then exceeds its own area the layer reads as almost unused. `Pad` should arguably
be excluded from the routing stack the way a region layer is, or its factor clamped at 1.0.

## `sky130/sky130_fd_sc_hd.tlef` — 18,031 B

| | |
|---|---|
| upstream | `The-OpenROAD-Project/OpenROAD-flow-scripts` |
| path | `flow/platforms/sky130hd/lef/sky130_fd_sc_hd.tlef` |
| revision | `97a7c114404e` (latest commit touching this path) |
| sha256 | `8e99b4e8b016db0713029ebcae6b2cc2aedd9c2c49682e2f23521dd0b1a2085e` |
| licence | Apache-2.0 — "Copyright 2020 The SkyWater PDK Authors" |

The layer-*naming* variance nothing else here has: 6 routing layers called `li1`, `met1`…`met5`,
not `M1`…, and neither is a prefix of the other's names. Two real `W + S < P` cases:
`li1` 0.34 against 0.46 (`f = 0.739`) and `met1` 0.28 against 0.34 (`f = 0.824`).

---

## Warning: the two Nangate45 files are not open-licensed

The Si2/Nangate Open Cell Library is free for universities, research and non-commercial use, and
its licence does permit distribution — but the file itself states, verbatim:

> This file has been provided pursuant to a License Agreement containing restrictions on its
> use. This file contains valuable trade secrets and proprietary information of Nangate Inc.,
> and is protected by U.S. and international laws and/or treaties.

The licence also prohibits benchmarking the library against another library or standard cell set,
and commercial use. They are vendored here because this repository is private; **remove
`sample_data/real/nangate45/` before publishing it.** The other three files (ASAP7 BSD-3, sky130
Apache-2.0, the OpenROAD DEF Apache-2.0) carry no such restriction.

## Re-fetching

```sh
B=https://raw.githubusercontent.com
curl -sS -o nangate45/NangateOpenCellLibrary.tech.lef \
  $B/The-OpenROAD-Project/OpenROAD-flow-scripts/244d277a3711/flow/platforms/nangate45/lef/NangateOpenCellLibrary.tech.lef
curl -sS -o nangate45/gcd_nangate45.def \
  $B/The-OpenROAD-Project/OpenROAD/7cb0c0c1757c295a07df4bf84e4d059d888bfcb9/test/gcd_nangate45.def
```

`sha256sum sample_data/real/*/*` must match the hashes above. But the bytes were fetched from
each repository's default branch, whose content for a path *is* the content of that path's latest
commit — the hashes are the authority; the revisions record where they came from.
