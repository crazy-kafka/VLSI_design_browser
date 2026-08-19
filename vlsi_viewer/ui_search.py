"""Search results popup window (single mode: one panel; compare mode: V1/V2 panels)."""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from .model import TreeView, match_paths


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
            table.setItem(r, 0, QTableWidgetItem(path))
            for ci, col in enumerate(view.columns, start=1):
                v = col.series.get(path, None)
                item = QTableWidgetItem(col.fmt(v))
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                table.setItem(r, ci, item)

        table.resizeColumnsToContents()
        table.cellDoubleClicked.connect(
            lambda row, col, v=version: self.selected.emit(matches[row], v))
        panel.addWidget(table)

        self.tables[version] = table
        return panel
