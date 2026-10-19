# Metrics menu: show/hide hierarchy columns

The toolbar now has a **Metrics** menu of checkboxes, one per metric column. Unchecking
hides that column; checking shows it again. The choice is per session and survives tree
rebuilds.

## Behaviour

- **Single-design mode only.** The button is added when there is no compare design
  (`MainWindow._build_toolbar`, `self._design2 is None`). Compare mode has three
  differently shaped trees (V1 / V2 / Δ) and keeps its fixed columns; the button and menu
  are `None` there. Metal mode has no hierarchy tree and uses its own toolbar.
- **Entries** are built from `schema.STD_METRICS` (Area through B/I Area), plus
  `schema.MACRO_METRICS` (Macro Cnt, Macro Area) when **Include macros** is checked, plus
  `Density%` in physical mode. The menu is rebuilt when *Include macros* changes; hidden
  macro keys are remembered while their columns are temporarily absent.
- **No rebuild on toggle.** `HierarchyTree.set_metric_hidden(key, hidden)` stores the key
  and calls `setColumnHidden` for the matching column; expansion, sorting, scroll and the
  lazy density jobs are untouched. `_apply_hidden_columns()` reapplies the set at the end
  of every `HierarchyTree.rebuild`, so threshold/macro changes keep the choice.
- **Region tree follows.** `MainWindow._on_metric_toggled` applies the same key to the
  selected-region tree; its hidden set survives new selections and is applied when the
  region view is built.
- `HierarchyTree.column_index(key)` maps a metric key to its 1-based column (or `None`);
  the Hierarchy column itself is never hideable.

## Files

| File | Change |
|---|---|
| `vlsi_viewer/ui_tree.py` | `_hidden_keys`, `set_metric_hidden`, `column_index`, `_apply_hidden_columns`; applied at the end of `rebuild`. |
| `vlsi_viewer/ui_main.py` | `QToolButton("Metrics")` + `QMenu` in `_build_toolbar` (single-design only); `_rebuild_metrics_menu`, `_on_metric_toggled`; menu rebuild when `include_macros` changes. |
| `tests/test_gui_smoke.py` | Six tests: hide/show, survival across a threshold rebuild, macro entries follow Include macros, Density% in physical mode, region tree sync, no menu in compare mode. |
| `README.md` | Feature bullet under "Read the numbers". |

## Verification

- `python -m pytest -q` → **706 passed in 70.83 s**.
- Offscreen physical sample: the menu listed 11 std metrics + Density%; unchecking
  Area/ULVT%/Density% hid columns 1/3/12; selecting a region hid Area in the region tree
  too; re-checking restored the columns.
- Manual: toggle metrics in tree-only and physical modes, change Min/Include macros, and
  select a region — hidden columns stay hidden and return when checked.
