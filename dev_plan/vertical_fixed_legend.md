# Vertical fixed color legend (top-right) with 5 value ticks

## Change (`vlsi_viewer/ui_layout.py`)
- Replaced the horizontal bottom legend row (`_legend_row` + `_legend_pixmap`)
  with a `LegendWidget` — a vertical child widget of the `GenericGraphicsView`,
  pinned to the view's top-right via `_position_legend()` (move to
  `width()-w-margin, margin`) and re-anchored on view resize through
  `eventFilter` (`QEvent.Resize`).
- `LegendWidget.paintEvent` paints a black(0)->white(1) thermal gradient bar
  (`thermal_color`, top=white=100%, bottom=black=0%) plus value ticks at
  0/25/50/75/100% computed as `lo + f*(hi-lo)`.
- Because it is a child widget (not a scene item), pan / zoom / fit never move
  it. `WA_TransparentForMouseEvents` keeps it from blocking view interactions.
- `_autoset_range` and `_apply_range` call `legend.set_range(lo, hi)`, so the
  5 tick values update when the map type changes or the user edits Min/Max.

## Test
`tests/test_gui_smoke.py::test_layout_legend_overlay` asserts the legend is a
child of the view and that `set_range` stores the range.

## Verification
- `python -m pytest -q` -> 69 passed.
- Legend render: white at top, black at bottom, correct thermal midpoints.
- Min=0.2, Max=0.8 -> ticks 0.2 / 0.35 / 0.5 / 0.65 / 0.8.
- Mouse-transparent: True.
