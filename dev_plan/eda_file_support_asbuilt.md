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
- `--out` takes a directory only (plan said `DIR|FILE`), and names each dump after the
  **design** rather than the input file:

  | written | name | example |
  |---|---|---|
  | the cell library | `cell_info.json` | — |
  | a block | `<top>.instance_info.json` | `core.instance_info.json` |
  | the second design | `<top>.instance_info.compare.json` | `core.instance_info.compare.json` |

  The top is the DEF `DESIGN` name, or `--top` when given (`--top` renames the design
  itself, and so the dump with it); for a netlist `--top` is the only source, since a
  netlist names no design. The cell library needs no design name because several LEF files
  are **one** library.
- Both converters take a single input path (the plan had the verilog one taking a list);
  the CLI loops, writing one JSON per input.
  *Superseded: `instance_info_from_verilog` takes a list again and several `--verilog`
  files are one design — see "Real-usage fixes" below.*
- `quickstart.py` redirects generated JSON to a temp directory so the demo cannot dirty
  the checkout, while the CLI default stays "beside the input" as chosen.
  *Superseded: nothing is written unless `--out` is given, so the redirect is gone.*

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

## Real-usage fixes

Four defects surfaced by running the flows on real files.

### `.gz` inputs (verilog, and the macro LEF)

`_util.readFile` was a plain text read, so a compressed netlist failed immediately. It
now reads through gzip for a `.gz` name and falls back to a plain read on
`gzip.BadGzipFile`, mirroring the companion project's `utils/readFile.py` — a mislabelled
file stays usable. `LefParser.getAllLefLines` had the same gap from the other direction:
it opened each LEF directly instead of via `readFile`, so a compressed *macro* LEF failed
even after the helper was fixed. It now goes through `readFile(...).splitlines(keepends=True)`,
which preserves the line-with-newline contract the macro search relies on. That made
`import os.path` unused, so it went.

### `TRACKS` crashed the whole DEF parse

`re_track`'s optional MASK group was `(?:MASK\s+(?P<mask_num>\d+)\s+(?:SAMEMASK)?\s+)?` —
it demands **two** whitespace runs after the mask number, so
`TRACKS X 41 DO 24095 STEP 88 MASK 1 LAYER M4 ;` never matched while the same line *with*
`SAMEMASK` did. Since the reference makes `[SAMEMASK]` separately optional (line 514), the
shape that broke is the normal one. `__extractTracks` then indexed the failed match, and
the resulting `TypeError` aborted the entire parse — components, DIEAREA and density with
it, which is why it presented as "DEF processing crash" rather than as missing tracks.

Fixed the whitespace handling, and while in there: `DO numtracks` is now captured
(`DefTrack.num_tracks`) instead of discarded, a `LAYER` clause naming several layers yields
one `DefTrack` per layer, and an unrecognised clause is **reported and skipped** rather
than raised. That last part is the real fix: no single track variant can take the design
down again.

*Not* done: consuming continuation clauses that omit the `TRACKS` keyword. That needs
reading lines ahead of the caller, and a line that turns out not to belong to the section
has already been consumed and would be silently dropped by the dispatch loop — a worse
failure. Repeated `TRACKS` lines (what real tools emit) are already handled.

### No JSON unless `--out` is given

The flows used to write `<design>.def.instance_info.json` beside the input, which put a
file in the user's source tree on every run. Now nothing is written at all: the converters
hand their structures straight to the pipeline in memory.

That required the loaders to accept in-memory data — `loader.load_block` /
`load_cell_info` take a path **or** an already-parsed dict, which covers
`metrics.load_blocks` and `physical._load_blocks_and_cells` unchanged since both only
forward to them. The one genuinely path-bound piece was `load_or_build`: its cache key comes
from `os.stat`, so it now skips the pickle cache for in-memory input. Not a loss — the
conversion itself was never cached, so a run already re-parsed the DEF or netlist every
time. `--cache-dir`/`--force` therefore do nothing for these flows, and the README says so.

`--out DIR` still dumps the JSON, as a copy for inspection or for feeding back to the
`json` subcommand; the pipeline reads the in-memory structures either way.
`quickstart.py` lost the `--out` redirect it had as a workaround for the old behaviour.

### Multiple Verilog files are one design

A netlist is normally split across files, one per module. `InstExtractor` now takes a path
**or a sequence**: it parses each file, merges the module tables, and walks from `top_name`
once, so the split netlist resolves as a single design. A module defined in more than one
file is a real error, so it warns (once, listing the names) and keeps the first definition
rather than letting the result depend silently on file order.

`instance_info_from_verilog` takes the list and returns one dict, and the CLI converts the
whole `--verilog` list once. **The multi-file flags deliberately differ:** several `--def`
files stay one block each (each DEF is a complete design), while several `--verilog` files
are one netlist.

## Verification of the fixes

- `python -m pytest -q` → **161 passed** (144 before these four fixes).
- `tests/test_def_tracks.py` (new, 6 tests): the reported line parses to one `DefTrack`
  (`X, 41, 24095, 88, mask 1, M4`), `SAMEMASK` still parses, multi-layer clauses yield one
  track per layer, and an unreadable clause warns while components and DIEAREA still parse.
- `tests/test_parsers_eda.py`: gzipped netlist and LEF match their plain-text runs; a file
  merely *named* `.gz` still reads; a netlist split one-module-per-file matches the
  single-file extraction; a duplicate module warns.
- `tests/test_cli.py`: no file appears in the input directory for a def/verilog run, and
  `--out DIR` still writes both JSON files, which load back equal to the in-memory data.
- End-to-end: `main.py verilog --verilog core.v.gz …` extracts 3724 instances (same as
  plain text); the def and verilog flows log `from <in-memory>` and leave the tracked
  `sample_data/eda/` byte-identical; `--out` writes there instead.

### `--out` content check (and a compare collision)

Asked whether `--out` "generates instance json and cell json correctly", the honest answer
was *partly verified*: only the DEF path, only that the files existed, and only `top_name`
plus an instance count. Checking properly found a real bug.

**The bug.** `--out` named each dump after its source file alone, so a compare run with the
same file name on both sides (`v1/core.v` against `v2/core.v` — the ordinary case for a
version diff) wrote the *same* path twice and the second silently replaced the first.
Measured: a compare run left one `core.v.instance_info.json` in `--out` instead of two, with
the log showing "wrote …" twice and no complaint.

The naming was then **revised rather than patched** (at the user's request): a dump is named
after the design's top cell — `cell_info.json`, `<top>.instance_info.json`,
`<top>.instance_info.compare.json`. That removes the collision by construction, because the
two sides of a diff are precisely the case where the *files* share a name and only a suffix
can tell them apart. `_dump_json` still tracks the paths it has written and warns if two
inputs still map to one name (two same-named DEFs given as separate `--def` blocks).

**What is verified now**, per flow (`tests/test_cli.py`, parametrized over `def` and
`verilog`):

- the dumped `cell_info` and `instance_info` are **content-identical** to the in-memory
  structures (`json.loads(written) == in_memory`);
- loading the dumped *pair* reproduces the same design as the in-memory pair
  (`build_design(...).hier` frame-equal, same roots) — which is the real question, since a
  dump is only useful if the two files work together;
- a compare dump leaves both sides on disk under distinct names;
- two inputs sharing an output name produce a warning rather than a silent overwrite;
- merged inputs (several LEFs, several Verilog files) write **one** dump — pinned by
  `test_merged_lefs_write_one_cell_dump` and `test_merged_verilog_files_write_one_dump`;
- the name follows the top cell, `--top` override included — pinned by
  `test_block_dump_is_named_after_the_top_cell`.

The rule was checked by running every input combination rather than by reasoning about it,
which is how these got pinned: two LEFs give **two** files, not three (one library); a
compare run whose sides share a top gives `cell_info.json`, `core.instance_info.json` and
`core.instance_info.compare.json`; `--top renamed` renames the dump to
`renamed.instance_info.json` along with the design; and a compare side with `--compare_top`
takes its own name (`core2.instance_info.compare.json`).

Also confirmed by hand on a real compare run: `--out` then holds `cell_info.json` (20
cells), `core.instance_info.json` and `core.instance_info.compare.json` (3724 instances
each), every one loading independently through `load_block` / `load_cell_info` — the netlist
ones with no boundary, as expected for a netlist.

`python -m pytest -q` → **168 passed**.
