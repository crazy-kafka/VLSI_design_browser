# EDA file support (Verilog / DEF / LEF) — as built

Implements `dev_plan/EDA_file_support.md`: the viewer now reads gate-level Verilog, DEF
and LEF directly, with three CLI subcommands replacing the flat flag set.

## Rule 2: rewrite or restructure the provided parsers?

**Neither.** All three vendored trees (`DEF/`, `LEF/`, `verilog/`) already used explicit
relative imports internally (`from .defComponent import DefComponent`), so their only
external dependency was a root `utils.py` that had just one of the three names they
imported:

| site | import | outcome |
|---|---|---|
| `DEF/defParser.py:10` | `CoordinateProcess` | used **once**, at line 339, for a bbox min/max — inlined, import dropped |
| `LEF/lefParser.py:15`, `verilog/verilogParser.py:10` | `readFile` | defined nowhere in the repo — added to the new `parsers/_util.py` |
| 4 further sites | `Print` | already existed, repointed at `_util` |

They moved to `vlsi_viewer/parsers/{DEF,LEF,verilog}/` with **no changes to their parser
logic**. `DEF` keeps its spelling because `def` is a Python keyword and cannot be a
package name — which is also why the CLI's `--def` flag needs an explicit
`dest="def_files"` (the default `args.def` is a syntax error).

## What was built

| phase | change |
|---|---|
| 1 | physical-only cells now count in the **density** map only (see below) |
| 2 | parsers moved into `vlsi_viewer/parsers/`, imports fixed, old top-level dirs deleted |
| 3 | `parsers/convert.py` + `sample_data/eda/` sample + converter tests |
| 4 | CLI → strict subcommands `json` / `verilog` / `def` |
| 5 | `quickstart.py` + docs |

### Physical-only semantics (phase 1)

Previously `physical.py:244` skipped physical-only instances *before* any box existed, so
they were in no map at all. Now:

| surface | behaviour |
|---|---|
| density | **included** — filler, tap and decap are real area |
| leakage / dynamic / ULVT | excluded (their contributions are zeroed at raster time) |
| tree, contour, `Density%` | excluded — `boxes_for` masks them, and `density_for` ignores them in both the numerator and the macro term |

`is_physical_only` was added to `CELL_ATTRS` (`schema.py`) so a library marks a cell once
rather than every instance of it; an instance is physical-only if either side says so.
Two traps worth recording:

- `metrics._build_leaves` merges cells onto instances, and both frames now carry
  `is_physical_only`. Without renaming the cell-side copy first, pandas emits
  `is_physical_only_x` / `_y` and `metrics.py:142` raises `KeyError`.
- Adding boxes for density would silently have dragged filler into the contour and the
  `Density%` metric, which the requirement says must exclude it. `boxes_for`,
  `_contour`, `_contour_area` and `density_for` all mask the flag, and there is a test
  per surface.

### Converters (phase 3)

`vlsi_viewer/parsers/convert.py` — `cell_info_from_lef`, `instance_info_from_verilog`,
`instance_info_from_def`. All emit exactly `schema.CELL_ATTRS` / `INSTANCE_ATTRS` keys, so
the output is ordinary input for the existing loaders.

Defensive work around the parsers' real behaviour, each covered by a test:

- `dbUnit()` silently returns **2000** when a DEF has no `UNITS DISTANCE MICRONS`, which
  would scale the design wrong with no error — detected and warned.
- `re_pt` needs whitespace *inside* the parens: `( 0 0 )` matches, `(0 0)` does not.
- `__extractComponents` is line-at-a-time, so a wrapped component statement is dropped
  silently — the parsed count is compared against the declared `COMPONENTS` count.
- `UNPLACED` components are kept at `(0, 0)` by the parser; the converter skips them
  rather than piling them on the die origin.
- **`FILL*` is dropped**, not flagged: filler tiles every row gap, so keeping it (and
  counting physical-only cells in density) would peg the density map at 100%. Tap, decap
  and other physical-only cells are kept and flagged.

Divergences from `dev_plan/code_sample/extractCellInfo.py`, both commented in the code:

- The filtered cells (`FILL|BOUNDARY|BHD|ANTENNA|DCAP|TIE|TAP|GDCAP|HDDI`) are **emitted
  with their real LEF size and flagged physical-only**, not omitted. Omitting them breaks
  geometry resolution (`physical.py` skips cells missing from `cell_info`) and shows them
  as zero-area leaves in the tree.
- `is_macro` comes from LEF `CLASS != CORE`, not the script's `drive_size != 0`: the
  viewer's `is_macro` drives the macro columns and `Density%`, so it has to mean "hard
  macro".
- Fixed the script's `r'^MB(d)'` bug (a literal `d`, so `int('d')` raised for any `MBd…`
  cell) → `r'MB(\d+)'`. Also extended the drive rule beyond LinxCore's
  `D<n>…COT…VT` to an unanchored `_X<n>`, since Vt suffixes make an anchored match miss
  most libraries.

### Sample data (`sample_data/eda/`)

`generate_eda_sample.py` writes `cells.lef` (20 macros: SVT/LVT/ULVT logic, an SRAM
`CLASS BLOCK`, and FILL/TAP/DCAP), `core.def` and `core.v` for the same small CPU cluster
— a few thousand instances so it parses fast, with real hierarchy, filler and macros so
the GUI has something worth browsing. It self-verifies by re-parsing its own output
through the converters and the real loaders. Total ~420 KB committed, versus 7 MB for the
JSON sample.

Two things it demonstrated, worth keeping in mind: the DEF's `core.def` and the netlist's
`core.v` deliberately do **not** list the same instances (a netlist has no filler/tap),
and `int(x * dbu)` truncates — `64.6 * 1000` is `64599.999…`, which produced a 0.001 µm
overlap until it was changed to `round()`.

### CLI (phase 4)

`vlsi-viewer {json,verilog,def} …`. Breaking: the bare-flags form is now a usage error.
`--physical_mode`, `--grid_size` and `--contour_gap` exist only on `json` and `def`, so
"verilog has no physical mode" is structural rather than a runtime check. A module-level
`resolve_inputs(args)` does the conversion and returns paths, which is what makes the new
flows testable without Qt.

## Deviations from the approved plan

- Parser dirs keep the original `DEF` / `LEF` / `verilog` spelling (plan said lowercase;
  `def` is a keyword).
- `--out` takes a directory only (plan said `DIR|FILE`). The suffix is appended to the
  whole input file name (`core.def.instance_info.json`) so a `core.def` and a `core.v` in
  one directory cannot collide.
- Both converters take a single input path (the plan had the verilog one taking a list);
  the CLI loops, writing one JSON per input.
- `quickstart.py` redirects generated JSON to a temp directory so the demo cannot dirty
  the checkout, while the CLI default stays "beside the input" as chosen.

## Verification

- `python -m pytest -q` → **119 passed** (94 before this work).
- `python sample_data/eda/generate_eda_sample.py` → self-verify OK: 20 macros, DEF → 3994
  instances (4822 components less filler), verilog → 3724 (logic only), density 73 %
  mid-range, and the name heuristics agree with the generator's own physical-only list.
- Placement legality on the sample: **0 overlapping pairs**; density max 1.0 only at the
  SRAM macros.
- All three flows launch the GUI headlessly (`def` with `--physical_mode`, `verilog`
  tree-only), and the DEF flow logs the expected no-power warning.
- Real JSON sample unchanged by phase 1: 108,436 boxes, 21.0 % saturated, `Density%`
  68.4 % — identical before and after.

## Known limits

- DEF `ROWS`/`SITE` are unparsed, so row height and site pitch are unavailable. Track
  pitch *is* available (`DefParser.getTracks()`); `BLOCKAGES`/`PINS`/`NETS` can be enabled
  with the parser's existing flags if congestion or pin-density views are wanted later.
- The LEF parser keeps one RECT per pin, and its macro/pin loops have no index bounds — an
  unterminated `MACRO` raises `IndexError` (asserted in a test, as a known wart).
- `.def.gz` is supported by the parser but untested here; the sample is plain text.
- No power data reaches the DEF/verilog flows, so those heat maps are empty by design.
- `dev_plan/code_sample/extractCellInfo.py` is a reference for the upstream rules, not a
  runnable script here: it uses `tkinter` plus a hard-coded Cadence TCL setup, and its
  top-level `LEF`/`DEF` imports refer to the old layout.
