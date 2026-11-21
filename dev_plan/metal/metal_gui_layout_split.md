# Metal mode: cell detail to the left, the range to the toolbar

The plan for the pass that followed the second look at metal mode on screen. What was built,
and what the measuring turned up, is in
[`metal_density_asbuilt.md`](metal_density_asbuilt.md) under *Phase 10*.

## What prompted it

Everything lived in one right-hand column: net class, value range, the 12-row layer list, then
the 12-row cell-detail readout. The two long lists fought over the same vertical space - the
layer list stopped at M5 behind a scrollbar while the detail sat below it - so the layer list
and the hovered cell's numbers could not be read at the same time.

The screenshot also showed a defect: **the Min/Max spin boxes rendered as nothing**, just the
"Min:" and "Max:" labels with blank space beside them.

## 1. Why the spin boxes vanished — measured

`LayoutView._constrain` set `setMaximumWidth(96)` **and** `QSizePolicy.Ignored`. Measured in
both places they are laid out, with `1e12` ranges:

| horizontal policy | max width | resulting width |
|---|---|---|
| `Preferred` | 96 | **96** ✓ |
| `Ignored` | 96 | **0** ✗ |
| `Preferred` | none | 331 |

`QWidgetItem::sizeHint()` zeroes the width when the policy is `Ignored`, and every row these
boxes sit in ends in `addStretch(1)`, so the stretch took the row and the boxes were given
nothing. The original problem - a `QDoubleSpinBox` claiming 331 px because it sizes itself for
the longest string a `1e12` range can produce - needs **only** `setMaximumWidth`: both a
QBoxLayout and a QToolBar honour the maximum, and neither lets the 331 px `minimumSizeHint`
reach the window's own minimum.

**Fix:** delete the `Ignored` line, keep `setMaximumWidth(96)`. This was a regression from the
previous pass, and it affected physical mode too.

## 2. The range moves to a toolbar

`MainWindow._build_metal_toolbar()`, called instead of the hierarchy toolbar:

```
[Min: <spin>] [Max: <spin>] [Auto] [Fit] | [peak 0.463  full = 1.000]
```

`MetalPanel` keeps creating `auto_btn` and `peak_label` but stops placing them, because it owns
their logic (`_auto_range` needs `current_kind()`; the peak is `max_util(kind)`). That is the
pattern the view already uses — `LayoutView(external_controls=True)` builds its controls row and
never adds it. Measured before relying on it: a toolbar taking widgets from a never-added layout,
or with no parent at all, raises no Qt warnings, reparents them, and lays them out at the right
widths.

The widgets keep their names on the objects that own them (`window._layout.min_spin`,
`window._panel.auto_btn`). They must not become `window.min_spin` / `window.max_spin` — those are
the hierarchy toolbar's integer instance-count threshold, and a test asserts they do not exist in
metal mode.

## 3. Cell detail becomes its own pane on the left

Three panes, `[Cell detail | heat map | layers]`, stretch 0:1:0. Measured on stand-in panes: the
side panes keep their width, the map absorbs every spare pixel and yields first when the window
shrinks; the splitter's minimum is ~630 px, against ~1342 px two passes ago.

- New `CellDetailPanel(data, kind_of)` — the detail box entire, with `on_cell` and `refresh`.
- `MetalPanel` keeps the selection and gains `selection_changed`, emitted from `_apply_kind` and
  `_on_scope`.
- The window wires `cell_hovered -> detail.on_cell` and `selection_changed -> detail.refresh`.
  The second is what makes the readout follow a layer tick; in one widget that was an internal
  call, and splitting the classes silently drops it.

## 4. Each layer row gains its width / spacing / pitch

```
layer          W/S/P   dir    U
☑ M1   0.10/0.10/0.20  H  0.026
```

Capacity is `routable area × (W + S) / P`, so the three rules that produce the factor belong
beside the number they explain. Formatted with `:g`, not the three-significant-figure rule —
a real 0.065 µm width must not print as `0.06`. The factor `f` goes in the row's tooltip
rather than as a fourth column, since it reads `1.000` on most layers; the tooltip carries it
plus the reason a layer is disabled. `MetalData._pitch_factor` became public as
`pitch_factor` so the tooltip reports the metric's own factor instead of a copy of the formula
re-derived in the GUI.

## Files

| file | change |
|---|---|
| `vlsi_viewer/ui_layout.py` | `_constrain`: drop the `Ignored` policy; fix the docstring that argued for it |
| `vlsi_viewer/metal.py` | `_pitch_factor` → public `pitch_factor` |
| `vlsi_viewer/ui_metal.py` | split out `CellDetailPanel`; the panel loses the range and detail boxes, gains `selection_changed`; layer rows gain W/S/P |
| `vlsi_viewer/ui_main.py` | `_build_metal_toolbar()`; three-pane splitter; the two new connections |

## Verification

1. `python -m pytest -q` — green.
2. A headless geometry script: splitter sizes, each spin box's width, the toolbar's contents,
   the layer table's cells and one row's tooltip.
3. A rendered PNG to eyeball the three panes.
4. `python sample_data/metal/quickstart.py --check` — the CLI path is untouched, and its
   numbers for cell (9, 8) are the reference the readout must agree with.

## What a review of the design turned up

Four things that were not in the plan, all now fixed:

- **A pane is sized from its `sizeHint()`, and a hint can beat a maximum.** The layer table's
  hint grows with the font — under a wide one it asked for 519 px, over the pane's own 460 px
  ceiling, and the splitter handed it over anyway, leaving the map 623 px of 1400. Explicit
  `splitter.setSizes([260, 800, 340])` is honoured exactly and gave the map back 169 px. These
  are starting widths, not limits: the divider still moves.
- **A widget left in a layout that is never installed is a trap.** `_controls_row` still listed
  the ramp widgets after the toolbar adopted them, so adding that row to a layout later would
  pull them straight back out of the toolbar — which would then silently have no Min/Max. With
  `external_controls` the widgets now go into a throwaway layout instead.
- **Two emission paths for one signal.** `_on_scope` repeated `_apply_kind`'s body rather than
  calling it, so "emits once" was a coincidence of two methods staying in sync. It calls
  `_apply_kind` now.
- **The toolbar's last item absorbs all the slack** — the peak label sat in a few hundred
  invisible pixels of it. It is `Fixed` now, which also means a narrow toolbar cannot clip it.
  The toolbar also got an `objectName` and a hidden `toggleViewAction`, since it is the only
  route to the ramp and a right-click must not be able to hide it.

## What the first look at the new layout turned up

Three defects, one of them from before this pass:

- **The map drawn at start-up was not the map the panel selected.** The tick boxes said every
  layer; the view drew `L:M1`, because nothing pushed the selection into the view at
  construction. On this sample M1 alone carries almost nothing, so the window opened on a nearly
  empty map and only showed the real one after the scope was changed and changed back. The
  toolbar's peak (0.463) described the group while the map was M1, so the panel contradicted the
  picture. `MetalPanel.__init__` now ends with `_apply_kind()`.
- **The readout table was three rows tall in a half-empty pane.** A `QScrollArea`'s hint is the
  size its widget had when the policy was last consulted; a `QGridLayout` measures itself against
  the geometry it finds itself in, and the scroll area resizes its widget to the viewport - so a
  table installed while the area was a few pixels tall measured *nothing* and the two kept each
  other small. The table is now built detached, measured, and only then installed. 243 px of
  scroll area for 241 px of rows, where before it was 2 px.
- **The layer table overflowed its pane** (hence the missing `U` heading and the cut values),
  and the W/S/P column was ragged. The panes went 260→300 and 340→400, the stretch factors
  became 1:4:1 so the side panes yield instead of the map taking the whole loss, each rule field
  is padded so the slashes line up, and the leftover width goes to an empty column so each
  heading stays over its numbers.

## Two things the plan did not anticipate

**A spin box is built around its own `QLineEdit`.** The obvious assertion for "no search box in
the metal toolbar" — `toolbar.findChildren(QLineEdit) == []` — fails against the two range spin
boxes, which each contain one. The check has to filter by parent: a toolbar widget is parented
to the toolbar, a spin box's editor to the spin box.

**Qt lets a widget's minimum beat its maximum.** With a very wide font the layer buttons alone
exceed `MetalPanel`'s 460 px ceiling, so the pane comes out wider than its stated maximum. The
GUI tests therefore assert the font-independent invariants (the map is the widest pane, the
panes and handles account for the window) rather than pixel bounds.
