"""Search results popup window."""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from .model import TreeView, match_paths


class SearchDialog(QDialog):
    """Lists hierarchy matches; double-clicking a row emits ``selected``."""

    selected = pyqtSignal(str)

    def __init__(self, view: TreeView, pattern: str, mode: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Search Results")
        self.resize(960, 520)

        self._matches = match_paths(view.paths, pattern, mode)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f'"{pattern}" → {len(self._matches)} matches'))

        self.table = QTableWidget()
        self.table.setColumnCount(1 + len(view.columns))
        self.table.setHorizontalHeaderLabels(["Hierarchy"] + [c.label for c in view.columns])
        self.table.setRowCount(len(self._matches))
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)

        for r, path in enumerate(self._matches):
            self.table.setItem(r, 0, QTableWidgetItem(path))
            for ci, col in enumerate(view.columns, start=1):
                v = col.series.get(path, None)
                item = QTableWidgetItem(col.fmt(v))
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(r, ci, item)

        self.table.resizeColumnsToContents()
        self.table.cellDoubleClicked.connect(self._on_double)
        layout.addWidget(self.table)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _on_double(self, row, col):
        self.selected.emit(self._matches[row])
