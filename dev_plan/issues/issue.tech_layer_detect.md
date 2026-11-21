# Metal mode — M*_FB1 region layers listed as routing layers;wrong W/S/P extracted for M1, M5–M8 and B1/B2
**Target:** metal mode — tech LEF layer table ("Routing layers" panel, `W/S/P dir` columns)
**Reproduced:** 2026-09-13, design `wha1cd082-hs` (die 1060.2 × 1226.64 µm, 18 layers, top `lx956c_joe`, 123×107 grid @ 10 µm)
**Evidence:** GUI snapshot of the "Routing layers" panel + tech LEF stanzas for `M1`, `M2_FB1`, `M3_FB1`, `M4_FB1`, `M5`, `B1` (attached as screenshots)

---

## Problem Summary

| # | Problem | Layers | Observed (GUI) | Expected |
|---|---------|--------|----------------|----------|
| 1 | Region/filler layers declared `TYPE ROUTING` in the tech LEF are listed as routing layers | `M2_FB1`, `M3_FB1`, `M4_FB1` | listed with W/S/P 0.019/0.019/0.038 V, 0.019/0.029/0.04 H, 0.024/0.02/0.044 V | **excluded** from the routing layer list |
| 2 | No default `SPACING <value> ;` statement in the LEF → tool extracts a wrong spacing | `M5`, `M6`, `M7`, `M8` | `0.038/0.076/0.076` | `0.038/0.038/0.076` |
| 2 | (same, `B` band) | `B1`, `B2` | `0.062/0.089/0.126` | `0.062/0.064/0.126` |
| 3 | Two-value `PITCH` read as the x-pitch even for a `HORIZONTAL` layer (spec: x-pitch = space between *vertical* tracks, y-pitch = space between *horizontal* tracks) | `M1` | `0.016/0.016/`**`0.02`** | `0.016/0.016/`**`0.032`** |

All three defects come from the tech LEF layer scan: it keeps *every* `TYPE ROUTING`
layer (Issue 1), fabricates a spacing from content that is not a layer statement
(Issue 2), and always takes the x-value of a two-value `PITCH` even when the layer is
horizontal (Issue 3). Details, evidence and a verified reproduction follow.

---

## Issue 1 — `M2_FB1` / `M3_FB1` / `M4_FB1` are not real routing layers

### Observed

The "Routing layers" panel lists them alongside the real routing layers:

```
M2_FB1   0.019/ 0.019/ 0.038  V
M3_FB1   0.019/ 0.029/ 0.04   H
M4_FB1   0.024/ 0.02 / 0.044  V
```

### Expected

They must **not** appear as routing layers. They are region-defined layers of the
`FB1` region (a filler/bonding-type region defined *on* M2/M3/M4), not global routing
layers of the stack.

### Evidence — LEF stanzas

`M2_FB1` (M3_FB1 / M4_FB1 are identical in shape; `REGION FB1 BASEDLAYER M3` / `M4`):

```
LAYER M2_FB1
   TYPE ROUTING ;
   MASK 2 ;
   DIRECTION VERTICAL ;
   PITCH 0.038 0.038 ;
   OFFSET 0.000 0.000 ;
   PROPERTY LEF58_REGION " REGION FB1 BASEDLAYE R M2 ; " ;     <- region-defined layer
   ## Rule(s): M2CA.W.1
   WIDTH 0.0190 ;
   MAXWIDTH 0.5 ;
   ## Rule(s): M2CA.B.S.2a_STC
   SPACING 0.0190 ;
   ...
   AREA 0.00228 ;
   ...
END M2_FB1
```

Reference — a *valid* routing layer, `M1` (why it *should* be in the list):

```
LAYER M1
   TYPE ROUTING ;
   MASK 2 ;
   DIRECTION HORIZONTAL ;
   PITCH 0.020 0.032 ;
   OFFSET 0.0 ;
   ...
   WIDTH 0.016 ;
   ...
   SPACING 0.016 ;
   ...
END M1
```

`M1` has a direction, a pitch, a width and a plain `SPACING` statement, and **no**
`REGION` property. The `M*_FB1` stanzas differ by the `PROPERTY LEF58_REGION
"REGION FB1 BASEDLAYER Mx ;"` line — that is what marks them as region layers.

### Root cause

`TechRouting.read()` (`vlsi_viewer/parsers/routing.py` L139–141) filters **only** on the
`TYPE` statement:

```python
for name, layer in parsed.items():
    if (layer.type or "").upper() != "ROUTING":
        continue
```

The `M*_FB1` stanzas declare `TYPE ROUTING`, so they pass. The parser *does* capture the
region property into `LefLayer.region` / `LefLayer.based_layer` (`lefParser.py` L129–131,
fields in `leflayer.py` L25–26) — nothing downstream uses it for exclusion.

**Exclusion criterion:** a `TYPE ROUTING` layer carrying a
`PROPERTY LEF58_REGION "REGION … BASEDLAYER …"` (i.e. a region-defined layer with a base
layer) is not a routing layer of the stack and must be dropped from
`TechRouting.read()`. Layers without such a property (including `TM1`, `TM2`, `ALPA` in
the panel) are unaffected.

### Caveat — the parser currently misses `M2_FB1`'s region property

The region regex is exact (`compiledRe.py` L83):

```python
re_LEF58_region = re.compile(rf'PROPERTY\s+LEF58_REGION\s+"\s*REGION\s+(?P<REGION>\S+)\s+BASEDLAYER\s+(?P<BASEDLAYER>\S+)\s*;\s*"\s+;')
```

In the tech LEF the `M2_FB1` line is spelled with an internal space —
`REGION FB1 BASEDLAYE R M2` — while `M3_FB1` / `M4_FB1` are spelled cleanly
(`REGION FB1 BASEDLAYER M3` / `M4`). Verified against the current code:

| stanza in file | parsed `region` / `based_layer` |
|---|---|
| `REGION FB1 BASEDLAYER M2` (clean) | `'FB1'` / `'M2'` |
| `REGION FB1 BASEDLAYE R M2` (as in file) | `None` / `None` |

So an exclusion keyed on the parsed `layer.region` field would drop `M3_FB1`/`M4_FB1` but
**miss `M2_FB1`**. Whatever form the exclusion takes, it must also be robust to that
line (fix the regex to tolerate the split token, or match on the property text), or the
defect survives for exactly one of the three layers.

---

## Issue 2 — wrong spacing for layers without a default `SPACING <value> ;`

### Affected layers, observed vs expected (from the "Routing layers" panel)

| layer | GUI now (W/S/P) | expected (W/S/P) | spacing now | spacing expected |
|-------|-----------------|------------------|-------------|------------------|
| `M5` | 0.038/ **0.076** / 0.076 H | 0.038/ **0.038** / 0.076 | 0.076 | 0.038 |
| `M6` | 0.038/ **0.076** / 0.076 V | 0.038/ **0.038** / 0.076 | 0.076 | 0.038 |
| `M7` | 0.038/ **0.076** / 0.076 H | 0.038/ **0.038** / 0.076 | 0.076 | 0.038 |
| `M8` | 0.038/ **0.076** / 0.076 V | 0.038/ **0.038** / 0.076 | 0.076 | 0.038 |
| `B1` | 0.062/ **0.089** / 0.126 H | 0.062/ **0.064** / 0.126 | 0.089 | 0.064 |
| `B2` | 0.062/ **0.089** / 0.126 V | 0.062/ **0.064** / 0.126 | 0.089 | 0.064 |

None of these stanzas contains a plain/default `SPACING <value> ;` statement. The
expected spacing equals `pitch − width` for every one of them
(`M5–M8`: 0.076 − 0.038 = 0.038; `B1/B2`: 0.126 − 0.062 = 0.064), which is also the
base-row spacing in `B1`'s table (`WIDTH 0.0 → 0.064`) — i.e. the value the existing
fallback in `routing.py` L145–146 would already produce **if the parser did not
fabricate a spacing first**.

### Evidence — LEF stanzas

`M5` (M6/M7/M8 same pattern — no `SPACING` statement anywhere in the stanza):

```
LAYER M5
   TYPE ROUTING ;
   DIRECTION HORIZONTAL ;
   PITCH 0.076 0.076 ;
   OFFSET 0.000 ;
   ## My.W.1
   WIDTH 0.038 ;
   MINWIDTH 0.038 ;
   ## My.W.2
   MAXWIDTH 2.1 ;
   ...
   PROPERTY LEF58_SPACINGTABLE "
   SPACINGTABLE
   DIRECTIONALSPANLENGTH
   EXACTSPANLENGTHSPACING 0.0380 TO 0.038 PRL -0.0765 0.038 0.114 0.180
   EXACTSPANLENGTHSPACING 0.0380 TO 0.060 PRL -0.2000 0.199
   ...
   SPANLENGTH   0.0000       0.1800    0.1800 0.1800
   ...
   SPANLENGTH   0.2305       0.0800   0.1300 0.1590 ;
   ";
END M5
```

`B1` (B2 same pattern — spacing only in conditional clauses and a table):

```
LAYER B1
   TYPE ROUTING ;
   DIRECTION HORIZONTAL ;
   PITCH 0.126 0.126 ;
   OFFSET 0.000 0.000 ;
   WIDTH 0.062 ;
   ...
   PROPERTY LEF58_SPACINGTABLE "
   SPACINGTABLE TWOWIDTHS
   WIDTH 0.0            0.064  0.089  0.110  0.133   0.190   0.450
   WIDTH 0.155 PRL 0.25   0.089  0.089  0.110  0.133   0.190   0.450
   ...
   ";
   ...
   PROPERTY LEF58_SPACING "
   SPACING 0.089 ENDINLINE 0.09 WITHIN 0.0335 PARALLELEDGE 0.089 WITHIN 0.0985 MINLENGTH 0.063 ;
   SPACING 0.126 ENDINLINE 0.09 WITHIN 0.0335 PARALLELEDGE 0.1055 WITHIN 0.0985 MINLENGTH 0.063 ENCLOSECUT BELOW 0.045 CUTSPACING 0.152 ;
   ";
END B1
```

There is **no** `SPACING <value> ;` default clause in either stanza. The spacing the
tool shows is not stated anywhere as the layer's default spacing: `0.076` is `M5`'s
*pitch*, `0.089` is the first *conditional* clause in `B1`'s `LEF58_SPACING` string.

### Root cause — the stanza scanner has no concept of quoted PROPERTY strings

`TlefParser.__parseLayer()` (`lefParser.py` L66–146) scans the stanza line by line, and
three things then go wrong:

1. **Conditional `SPACING` clauses inside a property string are collected as spacing
   candidates.** `re_layer_spacing` (`compiledRe.py` L63) matches any line-initial
   `SPACING <number>` — so the two lines inside `B1`'s
   `PROPERTY LEF58_SPACING " … "` string match. Resolution order
   (`lefParser.py` L139–144) prefers them over the table:

   ```
   default SPACING            -> none
   min(conditional clauses)   -> min(0.089, 0.126) = 0.089   <- used
   min(SPACINGTABLE)          -> 0.064                        (never reached)
   ```

   This is exactly the failure mode documented in the `__parseLayer` docstring
   (L76–79): *"a layer whose final clause is a conditional one ends up with a spacing
   several times too large."* Verified: removing the `LEF58_SPACING` property from the
   stanza makes the parser return `0.064`.

2. **A `SPACINGTABLE` line *inside* a property string opens table mode.**
   `re_layer_spacing_table` (`compiledRe.py` L71) matches the bare `SPACINGTABLE` line in
   `M5`'s `PROPERTY LEF58_SPACINGTABLE " … "`. `__readTableLine()` (L148–162) then
   ingests **every** number from every following line that is not a `WIDTH` row —
   including `PRL` breakpoint values and negative numbers (e.g. `-0.2000`, `-0.0765`
   from the `EXACTSPANLENGTHSPACING … PRL …` rows). Spacing resolves to
   `min(table_spacings)` — an artifact of the table body, not a declared rule.

3. **What the GUI then shows depends on which artifact survives.**
   - `B1/B2`: the conditional-clause path wins → `0.089` (reproduced exactly).
   - `M5–M8`: with the exact `M5` stanza from the screenshot, the ingested table minimum
     is `-0.2` (negative), which the `spacing <= 0` guard in `routing.py` L145–146
     catches and replaces with `pitch − width = 0.038` — so the *current* build
     coincidentally shows the right number for `M5` through a wrong path, while the
     build that produced the snapshot shows `0.076` (the pitch — likewise not a
     declared spacing). Either way the displayed S is a parser artifact; the value is
     not `0.038` *because the LEF states it*.

### Verified reproduction (current code, exact stanzas from the screenshots)

```
$ python - <<'EOF'
  ... TlefParser('/tmp/lef_repro/tech_test.lef') + TechRouting.read() ...
EOF
M1:     W=0.016 S=0.016 P=0.02   dir=HORIZONTAL   usable=True   <- P should be pitch_y = 0.032 (Issue 3)
M2_FB1: W=0.019 S=0.019 P=0.038  dir=VERTICAL     usable=True   <- listed, should be excluded (Issue 1)
M5:     W=0.038 S=0.038 P=0.076  dir=HORIZONTAL   usable=True   <- 0.038 only via the <=0 fallback (artifact path)
B1:     W=0.062 S=0.089 P=0.126  dir=HORIZONTAL   usable=True   <- expected 0.064
```

(Test stanzas built 1:1 from the attached LEF screenshots, `M6/M7/M8` stanzas not
provided — same pattern assumed from the panel values.)

### Expected behaviour after the fix

1. A layer whose stanza has **no** plain `SPACING <value> ;` default and whose
   conditional clauses / `SPACINGTABLE` live inside `PROPERTY … " … "` strings must not
   inherit a spacing from that property-string content. No declared spacing ⇒
   `layer.spacing = 0`, and the existing `pitch − width` fallback in
   `routing.py` L145–146 applies — which yields exactly `0.038` for `M5–M8` and
   `0.064` for `B1/B2` (and `0.064` also matches the `WIDTH 0.0 → 0.064` base table row
   in `B1`).
2. Concretely, the panel must read:

   ```
   M5  0.038/0.038/0.076 H
   M6  0.038/0.038/0.076 V
   M7  0.038/0.038/0.076 H
   M8  0.038/0.038/0.076 V
   B1  0.062/0.064/0.126 H
   B2  0.062/0.064/0.126 V
   ```

---

## Issue 3 — `M1`'s displayed pitch is the x-pitch, not the y-pitch

### Observed

`M1` is `DIRECTION HORIZONTAL` with `PITCH 0.020 0.032 ;`, and the panel shows
`0.016/0.016/0.02` — i.e. the **x** pitch.

### LEF spec

```
PITCH {distance | xDistance yDistance}
    distance:        one pitch value, used for both the x and y pitch.
    xDistance yDistance:
                     the x pitch (the space between each VERTICAL routing track),
                     and the y pitch (the space between each HORIZONTAL routing track).
```

`M1`'s tracks are horizontal, so the pitch that applies to `M1` is the **y** pitch:
`0.032`.

### Root cause

`routing.py` L142:

```python
pitch = layer.pitch_x or layer.pitch_y
```

always takes the x value whenever one exists, regardless of direction. It should be
chosen by direction: `HORIZONTAL` → `pitch_y`, `VERTICAL` → `pitch_x`. A single-value
`PITCH` sets both equal, so no other layer in this design is affected — `M1` is the
only layer whose two values differ (0.020 vs 0.032), which is why only `M1` is
wrong in the panel.

### Impact beyond the panel

The same scalar feeds the heatmap: `MetalData.pitch_factor()` (`metal.py` L157–169)
computes `(W + S) / P`. With P = 0.020 the factor is 1.6, so `M1`'s capacity is
overstated 60% and its utilisation map reads too low. With the correct P = 0.032 the
factor is exactly 1.0 — 0.016 + 0.016 = 0.032, pitch equals width-plus-spacing, the
usual case the factor is documented to target.

### Expected

Panel row `M1  0.016/0.016/0.032 H`, and `M1`'s utilisation computed with P = 0.032.

---

## Acceptance Criteria

1. **`M2_FB1`, `M3_FB1`, `M4_FB1` absent** from the "Routing layers" panel (and from
   `TechRouting` / heatmap composition); all other routing layers unchanged. The
   exclusion must also hold for `M2_FB1` despite its property line being spelled
   `REGION FB1 BASEDLAYE R M2` (see Issue 1 caveat).
2. **Panel values** as in the "Expected behaviour" table above; `M1` reads
   `0.016/0.016/0.032 H` (the y-pitch for a `HORIZONTAL` layer, Issue 3) and `M1`'s
   utilisation is computed with P = 0.032.
3. No regression for the other layers that *do* declare a plain `SPACING <value> ;`
   (`M2`–`M4`, `FM1`, `FM2`, `TM1`, `TM2`, `ALPA`; `M*_FB1` excluded) — their W/S/P
   values must be identical before and after.

---


