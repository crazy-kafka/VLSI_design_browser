# The search results popup: columns that sort by value

The results table listed matches in path order and nothing else, while the tree it belongs to sorts
by any metric header. Qt's click-to-sort was not quite a one-liner, for two reasons: the cells hold
*formatted* text, so `"1,062"` sorts before `"531"`; and the jump was wired as
`self.selected.emit(matches[row], version)`, which is only the row on screen while nothing has been
reordered - after a sort, a double-click would jump to a different hierarchy than the one clicked.

`ui_search.py` now has `_SortItem`, a `QTableWidgetItem` that compares the raw value it carries in
`Qt.UserRole` (normalised by the tree's own `ui_tree._sortable`, so "no value" means the same thing
in both tables). Column 0 stores the path there, the metric columns store the value, the text stays
formatted, and the double-click handler emits the clicked row's stored path rather than
`matches[row]`. Sorting is enabled after populating, with an explicit initial
`sortItems(0, AscendingOrder)` so the popup opens in the same path order it always did.

Both new tests were mutation-checked: restoring `matches[row]` makes the jump test fail with
`['TOP/a', 'TOP/d'] != ['TOP/d', 'TOP/a']`, and comparing the text instead of the value makes the
order test fail at `'TOP/b' != 'TOP/c'` (where `"1,000"` sorts before `"200"`). A missing value
sorts first ascending - the tree's existing rule, not a new one. **657 tests pass.**
