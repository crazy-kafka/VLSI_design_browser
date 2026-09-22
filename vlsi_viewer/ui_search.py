"""Search results popup window (single mode: one panel; compare mode: V1/V2 panels)."""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from .model import TreeView, match_paths
# The tree's own "how do these two values compare" rule, so a missing value sorts the same way in
# both tables rather than in two subtly different ways.
from .ui_tree import _sortable


class _SortItem(QTableWidgetItem):
    """A cell that sorts by the value behind it, not by the text it shows.

    Every metric here is formatted by the time it reaches the table - ``1,062``, ``531``,
    ``19.68%`` - and sorted as text ``"1,062"`` comes before ``"531"``. So the raw value travels in
    ``Qt.UserRole`` and this compares that, exactly as ``HierarchyItem`` does for the tree
    (``ui_tree.py``), including its rule that an unset value sorts first ascending.
    """

    def __lt__(self, other):
        a = self.data(Qt.UserRole)
        b = other.data(Qt.UserRole)
        if a is None:
            return b is not None
        if b is None:
            return False
        return a < b


class SearchDialog(QDialog):
    """Lists hierarchy matches; double-clicking a row emits ``selected(path, version)``.

    In compare mode (``view2`` given) results are split into V1 / V2 panels.
    """

    selected = pyqtSignal(str, str)

    def __init__(self, view1: TreeView, view2, pattern: str, mode: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Search Results")
        self.resize(1200, 520)

        self.tables = {}

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f'"{pattern}" → matches'))

        panels = QHBoxLayout()
        panels.addLayout(self._panel("V1", view1, pattern, mode, "v1"))
        if view2 is not None:
            panels.addLayout(self._panel("V2", view2, pattern, mode, "v2"))
        layout.addLayout(panels)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _panel(self, title, view, pattern, mode, version):
        matches = match_paths(view.paths, pattern, mode)

        panel = QVBoxLayout()
        panel.addWidget(QLabel(f"{title} — {len(matches)} matches"))

        table = QTableWidget()
        table.setColumnCount(1 + len(view.columns))
        table.setHorizontalHeaderLabels(["Hierarchy"] + [c.label for c in view.columns])
        table.setRowCount(len(matches))
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setAlternatingRowColors(True)

        for r, path in enumerate(matches):
            name = _SortItem(path)
            # The path is the column's sort key and what a jump needs - not `matches[row]`, which
            # stops being the row once the table is reordered.
            name.setData(Qt.UserRole, path)
            table.setItem(r, 0, name)
            for ci, col in enumerate(view.columns, start=1):
                v = col.series.get(path, None)
                item = _SortItem(col.fmt(v))
                item.setData(Qt.UserRole, _sortable(v))     # sort by the value, not the text
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                table.setItem(r, ci, item)

        table.resizeColumnsToContents()
        # Enabled after populating (Qt would otherwise re-sort on every insertion), and given an
        # explicit initial order so the popup opens in the path order the matches came in.
        table.setSortingEnabled(True)
        table.sortItems(0, Qt.AscendingOrder)

        def on_double_click(row, _col, v=version, widget=table):
            item = widget.item(row, 0)
            if item is not None:
                self.selected.emit(item.data(Qt.UserRole), v)

        table.cellDoubleClicked.connect(on_double_click)
        panel.addWidget(table)

        self.tables[version] = table
        return panel
