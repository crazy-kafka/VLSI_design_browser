# Tech-LEF layer extraction: three defects from a real design

The plan for the three defects reported in [`issue.tech_layer_detect.md`](issue.tech_layer_detect.md)
from a real 18-layer design (`wha1cd082-hs`, top `lx956c_joe`). What was built, and what the
measuring turned up, is in [`metal_density_asbuilt.md`](metal_density_asbuilt.md) under *Phase 14*.

## What prompted it

Three defects, all in the tech-LEF routing-layer extraction that feeds the metal-density metric.
Every number below was reproduced with the real parser before anything was changed:

| # | defect | reproduced |
|---|---|---|
| 1 | region layers `M2_FB1`/`M3_FB1`/`M4_FB1` declare `TYPE ROUTING` and carry `PROPERTY LEF58_REGION`, and were listed as routing layers | they pass `TechRouting.read`'s TYPE-only filter. The old `re_LEF58_region` matched the clean `BASEDLAYER M3` spelling but not the file's `BASEDLAYE R M2` |
| 2 | a layer with no plain `SPACING` inherited a spacing from inside a quoted `PROPERTY` payload | `M5` → the quoted table's PRL breakpoints went into the spacing reader, minimum **−0.2**; `B1` → **0.089**, from a conditional clause inside the quoted `LEF58_SPACING` |
| 3 | a two-value `PITCH` was read as the x value whatever the direction | `M1` (HORIZONTAL, `PITCH 0.020 0.032`) → pitch 0.020, so `(W+S)/P = 1.6`: **capacity overstated 60 %**, and the map read too low |

Defect 2's root cause is one missing concept: `__parseLayer` scans line by line with no notion of a
quoted `PROPERTY` payload, so statements belonging to a *property's own mini-language* were read as
the layer's base statements. The repository had already been bitten by this once - `PROPERTY
LEF58_TYPE` clobbering `TYPE` - and that was patched narrowly rather than generally.

Defect 3 mattered most: it is the only one that silently changes what the map *means*.

## 1. A `PROPERTY` statement is consumed as a unit

`parsers/LEF/lefParser.py`, with patterns in `compiledRe.py`.

In `__parseLayer`'s scan, before the attribute chain, a line opening a `PROPERTY` statement is
consumed whole: `__readProperty(lines, cursor, layer)` finds the terminator and `__applyProperty`
reads the two properties by name. Payloads span lines, and the opening quote may sit on the
statement line *or* a later one - all four real spellings have to terminate correctly:

- `PROPERTY LEF58_TYPE "TYPE NWELL ;" ;` - one line (`asap7`, `sky130`);
- `PROPERTY LEF58_SPACING` with the quote on the **next** line (`asap7_tech_4x_201209.lef:137`);
- the report's `PROPERTY LEF58_SPACINGTABLE "` whose payload ends `";` on its own line;
- `PROPERTY propName propVal ;` - an *unquoted* value, consumed as one unit.

Two mechanisms, because one does not cover both shapes. An unquoted statement is self-terminating,
so a one-line regex (`re_property_one_line`) ends it where a quote-parity reader would run on to the
next quoted line. Everything else is read by **quote parity plus a semicolon**: the statement ends
on the first line with an even number of quotes that also contains `;`. Since a payload can contain
any of the base statements, the fallback guard is the stanza's own end - `END <layer>` or the next
`LAYER` line breaks the read with a `logger.warning`, so a malformed library loses one property
instead of the rest of the layer.

Nothing inside a payload sets a base attribute, which kills the quoted `SPACINGTABLE` opening table
mode (`M5`), the quoted conditional `SPACING` clauses (`B1`), and the same class of leak for quoted
`WIDTH`/`MINWIDTH`/`AREA` rows. The **unquoted** forms - Nangate45's `SPACINGTABLE`, sky130's
tables, the synthetic sample's - are base statements and are untouched.

With no spacing collected, `M5` and `B1` fall to the existing `pitch - width` fallback
(`routing.py:178`), which yields exactly the report's expected 0.038 and 0.064. That fallback is a
documented decision, which is why the parser has to report "no spacing stated" (0.0) rather than
letting a number out of a payload pass for one. `M5` is the sharp case: its old 0.038 came from the
`spacing <= 0` guard catching −0.2 - the right number for the wrong reason.

`LEF58_TYPE` (existing behaviour → `lef58_type`) and `LEF58_REGION` (fix 2) are still consulted by
name, deliberately, because they carry values this project uses. Everything else in a payload is
ignored. Reading a *pitch* out of a payload was considered and rejected: ASAP7's bare `PITCH`
already gives 0.180/0.144, so it would be a second mini-language to model for no gain.

## 2. Region layers are not routing layers

`parsers/routing.py`, `parsers/LEF/leflayer.py`.

`TechRouting.read` drops a `TYPE ROUTING` layer whose stanza carried a `PROPERTY LEF58_REGION`. The
criterion keys on the **property name, not the payload grammar**, so the file's `BASEDLAYE R M2`
spelling cannot matter; the region and base-layer names are parsed best-effort for the log line
only, and the exclusion does not depend on them. A new `LefLayer.region_layer` flag carries the
marker, because the existing `region`/`based_layer` fields are exactly what the broken spelling
leaves empty.

Skipped layers are logged (`logger.info`, with names) so three layers vanishing from the panel has
a visible reason in `-v` output rather than looking like a parse failure.

## 3. The pitch is the one perpendicular to the layer's own tracks

`parsers/routing.py` (`_routing_pitch`).

`pitch = layer.pitch_x or layer.pitch_y` became direction-aware:

    HORIZONTAL  -> pitch_y            VERTICAL -> pitch_x
    missing / unknown / DIAG45 / DIAG135 -> pitch_x or pitch_y   (the old rule)
    chosen value 0 -> the other one

A horizontal layer's wires are stacked vertically, so the distance between its tracks is the y
value. One scalar feeds `RouteLayer.pitch`, hence `MetalData.pitch_factor` (the metric), the jog
threshold (`ShapeStream._is_jog`) and the GUI's W/S/P column and tooltip.

The axis convention is not cited from a document in this repository - the reference in `dev_plan/`
is a syntax card with no prose - so the plan named the two real-file corroborations instead, and
both hold:

- `M1`'s `WIDTH 0.016` + `SPACING 0.016` equals exactly its y-pitch 0.032, i.e. its factor is 1.000,
  the value track rules normally produce;
- ASAP7's `M2` carries `PITCH 0.180 0.144` beside a quoted `LEF58_PITCH " PITCH 0.144
  FIRSTLASTPITCH 0.180 ;"` - the payload names 0.144, the y value, as the layer's pitch.

## Tests

- **The report's stanzas, verbatim**, in `test_tech_lef.py` (`M1`, `M5`, `B1`) and `test_routing.py`
  (`M2_FB1` in *both* spellings): a quoted table and quoted conditional clauses set no spacing; the
  fallback yields 0.038 / 0.064; a region layer is excluded whether or not its payload is spelled
  cleanly; `M1`'s W/S/P is `0.016/0.016/0.032` and its factor 1.0.
- **The report's acceptance table asserted as one check**, so the criteria are pinned rather than
  described.
- **Regressions the existing fixtures must keep passing**: Nangate45's 10 layers unchanged
  including metal2's `f = 0.737`; sky130's `li1`/`met1` unchanged; the synthetic sample's unquoted
  `SPACINGTABLE` still supplying spacing; `test_unqualified_spacing_wins_over_conditional_clauses`
  (an unquoted conditional clause) still holding.
- **A `PROPERTY` statement's own limits**: the unquoted form, the next-line-quote form, and an
  unterminated property at the end of a stanza.
- **New real-file assertions**: no layer of any vendored tech LEF comes out with negative spacing;
  ASAP7's `M2` factor is 1.0. `test_real_samples.py` also gained a check that the size and `sha256`
  in `PROVENANCE.md` are what the vendored bytes actually are - parsed from the document, so the
  record cannot rot away from the files it describes.
- **One vendored expectation moves with the fix**: `test_real_samples.py` asserted ASAP7 `M2`'s
  factor is `0.144/0.18`, which encoded defect 3. It is 1.0 after the fix, and the docstring says
  why.

## Verification

A measurement over all three vendored tech LEFs - 26 routing layers, printing direction, pitch_x,
pitch_y, the chosen pitch, width, spacing and `f` - confirms exactly one row moves: ASAP7's `M2`,
0.180 → 0.144. Nangate45's ten and sky130's six are unchanged, and sky130's `li1` (VERTICAL,
0.46/0.34) keeps the x value as the positive control for a layer whose two pitches differ and whose
direction is the other one.

`python -m pytest -q` → **500 passed**.

## What this does not fix

- **Acceptance criterion 3 of the report cannot be verified from this repository.** It names
  `M2`-`M4`, `FM1`, `FM2`, `TM1`, `TM2` and `ALPA`, which live in the reporting design's tech LEF
  and are not vendored here. Those stanzas (or the file) would let them be pinned as a fixture; the
  closest check that exists today is the invariant "a layer with a plain `SPACING` keeps it".
- **`Pad` has `f = 25.5`.** ASAP7's `Pad` declares `WIDTH 0.16`, `PITCH 0.32` and a spacing *table*
  whose values are 8 and 12 µm. All three come straight out of the file: a pad plane is not a track
  system, and its `PITCH` is the distance between pads rather than between routing tracks, so
  `(W + S) / P` is meaningless for it and its capacity exceeds its own area. Recorded in
  `PROVENANCE.md` rather than fixed - the honest fixes are to exclude it from the routing stack the
  way a region layer is, or to clamp the factor at 1.0, and neither is decided. It was found by a
  new sanity assertion (`spacing <= pitch`) failing on a real file; that assertion is now
  `spacing >= 0`, because the LEF genuinely does not guarantee the stronger one.
