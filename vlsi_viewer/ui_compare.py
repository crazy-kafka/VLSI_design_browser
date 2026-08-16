"""Two-version comparison: V1 / V2 / Diff tabs."""
from PyQt5.QtWidgets import QTabWidget

from .model import view_for_diff, view_for_single
from .ui_tree import HierarchyTree


class CompareWidget(QTabWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.v1 = HierarchyTree()
        self.v2 = HierarchyTree()
        self.diff = HierarchyTree()
        self.addTab(self.v1, "V1")
        self.addTab(self.v2, "V2")
        self.addTab(self.diff, "Diff")
        self._d1 = None
        self._d2 = None
        self._include_macros = False
        self._threshold = 0

    def set_designs(self, d1, d2):
        self._d1 = d1
        self._d2 = d2
        self._refresh()

    def configure(self, threshold, include_macros):
        self._threshold = threshold
        self._include_macros = include_macros
        self._refresh()

    def set_include_macros(self, flag):
        self._include_macros = flag
        self._refresh()

    def set_threshold(self, n):
        self._threshold = n
        self._refresh()

    def _refresh(self):
        if self._d1 is None:
            return
        for t in (self.v1, self.v2, self.diff):
            t.set_threshold(self._threshold, rebuild=False)
        self.v1.set_view(view_for_single(self._d1, self._include_macros))
        self.v2.set_view(view_for_single(self._d2, self._include_macros))
        self.diff.set_view(view_for_diff(self._d1, self._d2, self._include_macros))
