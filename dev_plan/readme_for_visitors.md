# README for visitors: three real captures, and a top rebuilt around them

`README.md` was 620 lines of unusually specific documentation with **no image at all**, while the
thing it documents is a GUI whose whole point is what it looks like. A visitor also met 36 lines of
feature bullets before the first command, and a maintainer note ("remove the research-licensed
samples before publishing") sat in the middle of the reference.

Two decisions taken with the user: **three real captures**, committed under `docs/`, and a
**rebuilt top** with every reference section kept in place, so the anchors other docs point at —
`PARSERS.md` links `README.md#input-format` — keep working. The voice follows the rest of the
repo: a number per claim, a pointer per number, no badges (there is no CI), no marketing verbs.

## What changed

- **`docs/capture.py`** (new) — regenerates the three screenshots the README shows. It builds each
  window through the same code path its CLI subcommand drives, offscreen, and takes the argv from
  `quickstart.argv_for` rather than restating it, so an image cannot show a command line the README
  does not. It loads system fonts by hand *before* importing the application: offscreen Qt starts
  with an empty font database (text renders as boxes) and `ui_tree` picks its monospace family at
  import time — that ordering is why the imports are not at the top of the file.
- **`docs/compare.png`, `docs/physical.png`, `docs/metal.png`** (new; 62 / 99 / 57 KB, 1600×900) —
  the app's own windows on the bundled samples, each left on its first screen: no clicking, no
  picking a nicer map.
- **The first 106 lines of `README.md`** are new — title and one-line, the image strip, "Try it in
  60 seconds", a `mode | reads | shows` table, three record-backed numbers, the features regrouped
  by what a user is looking for, and a nav line. Everything from `## Requirements & install` down
  is unchanged.
- `physical.png` appears again at the top of `## Physical layout mode` and `metal.png` at the top
  of `## Metal density mode` — a screenshot where the reader is already interested.
- The Nangate45 sentence was **deleted rather than moved**: `dev_plan/real_sample_sources.md`
  already carried the note, in more detail and with the directory named, and the README paragraph
  already linked to it.

## Deviations from the plan, and why

| plan | built | why |
|---|---|---|
| capture at 1400×800 | 1600×900 | At 1400 the physical window gave the tree only its column-sum hint and the columns came out 3–22 px wide, every value clipped to `1.60`, `68%`. The physical capture now sets `splitter.setSizes([700, 900])` after `show()`; metal mode sets its own widths in `ui_main.py`, and compare has no splitter at all. |
| physical = `quickstart.py def` (power filled) | `quickstart.py physical` | `sample_data/eda/core.def` is three rows of tree beside a map; the CPU-cluster sample fills the tree, and it is the command the README's own Quick start advertises for the heat map. The `--json` fill it drops is documented in prose, not in the image. |
| three feature groups | four | "Pickle cache" and "Four input flows" are neither finding, measuring nor silicon — they are loading. They got their own heading instead of being forced into one of the three. |
| `compare.png` repeated inline in its mode's section | not repeated | there is no compare *section* to repeat it in; the other two images have one. |
| "220 LEF files, 17,380 macros" | 221, 17,385 | the sources say 221 and 17,385 (`dev_plan/real_design_case_record.md`, and the 09-16 log for the timings). |

The three numbers in the top are the recorded ones, not estimates: 3,355,697 placed instances /
17,385 macros / 221 LEF files / 18 routing layers (`real_design_case_record.md`); 1,785.87 s of
which 1,696.70 s is the routing parse of 112.9 M shapes, and ~23 s for a db rebuild
(`metal_def_db.md`); 0.50 µs a replayed shape against 19.45 µs to parse it, both measured on the
same fixture (`metal_def_db_eval.md`).

## Verification

- `python docs/capture.py` writes all three, and each was **read back and checked against its
  caption**: the map painted, the legend and layer panel present, values legible, no half-drawn
  pane.
- Every link in the new top resolves and every anchor matches a heading — 25 headings and 31
  links, checked by slugging the headings the way GitHub does and resolving each target.
- `python -m pytest -q` → **657 passed** in 80 s. Docs-only, but the run is the repo's habit.
