# Metal-mode GUI: the blank sidebar, a boundary bug, and readability

The plan for the pass that followed the first look at metal mode on screen. What was built,
and what the measuring turned up along the way, is in
[`metal_density_asbuilt.md`](metal_density_asbuilt.md) under *Phase 9*.

## What the screenshot showed

Density mode works end to end and is tested, but the first look at it on screen
(`sample_data/metal`, 62×62 grid, 12 layers) showed a large blank area on the right, one
outright defect, and several places where the panel was fighting itself. The numbers were
right; this was about whether the window tells the user what it already knows.

## 1. The blank right-hand area — one root cause, measured

`QSplitter.sizes()` was `[554, 942]`: **942 px to a panel whose maximum width is 230**, so the
panel clamped itself and 712 px sat dead *inside* the splitter.

The 942 is a size hint, and it comes from one widget. `_build_controls` sets
`setRange(0.0, 1e12)` on the Min/Max spin boxes so the physical mode's power values fit, and
`QDoubleSpinBox` sizes itself for the longest string in that range: 331 px for a box that shows
three digits. That hint becomes the panel's minimum width, so the window could not shrink below
~1342 px, and the arrows sat on their own digits in a 214 px group.

**Fix.** Cap the spin boxes and stop their hint propagating, which is right for *both* modes:
`setMaximumWidth(96)` plus `QSizePolicy.Ignored` horizontally — "any width, ignore the hint".
Then `MetalPanel` becomes a *resizable* sidebar (`setMinimumWidth(250)`,
`setMaximumWidth(420)`, no `setFixedWidth`), and the splitter gives it its hint and hands all
the remaining width to the map.

## 2. Sub-block boundaries were drawn in local coordinates

`_boundary_polys` returned each block's boundary untransformed, where `physical.py` maps them
through the block's frame. The white rectangle in the lower-left of the screenshot was the
`SUB` outline drawn at `(0,0)-(260,200)` instead of at its four placements.

`_boundary_polys(assembler, blocks, root)` now walks the tree as `_macro_area` does and maps
each boundary vertex by vertex — not by bounding box, because a quarter turn swaps the
outline's extents. Four outlines appear, one per placement, which is both correct and free
hierarchy feedback.

## 3. Make the panel legible at its new width

- **Cell-detail values were clipped** because the row needed 25 characters. Three significant
  figures, and the column headings `layer | D/C | U` once instead of `D` and `C` twelve times.
- **The layer list stopped at M8.** Twelve checkbox rows competed with a detail box that grew
  to twelve rows, and the detail won. Cap the detail box and let it scroll, so the layer
  selection — the primary control, with its All H / All V buttons above it — always has room.
- **Range on two rows**, with `Auto` and `Fit` beneath the spin boxes rather than beside them,
  since a 250 px column cannot hold all four.

## 4. The map read as uniformly dark, and that is the ramp

Peak utilisation is 0.463 but typical cells are ~0.03, and the INNOVUS ramp's first third
(navy→blue) spans 0…0.33 — so nearly everything landed in the same colour. The fixed `[0, 1]`
default is deliberate (1.0 means every track consumed; autoscaling would throw that away).

Keep the default; add an **`Auto`** button that fits the range to a high percentile of the
current map, and show the map's **peak** in the panel so the absolute scale is never in doubt
while the ramp is stretched. `MetalData.max_util` already computes it.

## 5. Make the cell detail answer the question

It shows twelve rows and leaves the user to find the bottleneck and decide whether the cell is
escapable. Both are already computable:

- **bold the highest-`U` row** so the bottleneck layer is immediate;
- add the **horizontal and vertical maxima for that cell** — "can I still escape in either
  direction?" is the mode's question.

## 6. Two things the map was missing

- **A die outline.** The background is black and low utilisation is dark navy, so "outside the
  die" and "inside with no metal" look alike. After item 2, `TOP`'s boundary is in
  `boundary_polys`; draw it a shade brighter than the sub outlines.
- **A scale.** Nothing on screen said the die is 620 µm across. The status message now appends
  the extent.

## Files

| file | change |
|---|---|
| `vlsi_viewer/ui_layout.py` | cap the spin-box hints (`setMaximumWidth` + `Ignored`) — shared by both modes; a public `set_range`; the top-level boundary drawn brighter |
| `vlsi_viewer/ui_metal.py` | resizable sidebar, two-row range with `Auto`, capped/scrolling detail, compact numbers, bottleneck highlight, H/V line |
| `vlsi_viewer/metal.py` | `_boundary_polys` maps each boundary through its frame |
| `vlsi_viewer/ui_main.py` | die extent in the status message |

## Verification

1. Open the sample. The panel takes its own width, **no blank area**, the map takes the whole
   rest of the window, and the window shrinks far below 1342 px.
2. Drag the divider: the panel widens to 420 px and the map takes back the rest.
3. Four sub-block outlines, one per quadrant, plus the die outline; the stray lower-left
   rectangle is gone.
4. Hover a cell: rows are not clipped, the bottleneck row is bold, and the H/V line agrees with
   `MetalData.cell_detail` for that cell.
5. `Auto`: the map gains visible structure; the panel still reports the true peak. Reset to
   `0`/`1` and the picture returns to what the screenshot shows.
6. `python -m pytest -q` — green, with `tests/test_metal_gui.py` extended for the width policy,
   `Auto`, the highlight and the H/V line, and `tests/test_metal_metric.py` for the transformed
   boundaries.

## One thing the plan did not anticipate

The offscreen Qt platform reports **17 px per character** where a real Windows UI is ~9, so
absolute pixel widths measured in a test do not transfer to the machine the screenshot came
from — the same string measured 425 px offscreen and ~150 px on screen, and `font-size` in a
stylesheet has no effect there at all. The GUI tests therefore assert relationships rather
than pixel counts.
