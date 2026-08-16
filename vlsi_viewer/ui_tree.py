"""Hierarchy tree-table widget (QTreeWidget) with lazy expand + per-level sort."""
import math

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QTreeWidget, QTreeWidgetItem

from .model import TreeView


def _sortable(v):
    """Convert a metric value to a Python float for sorting; NaN/None -> None."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if (math.isnan(f) or math.isinf(f)) else f


class HierarchyItem(QTreeWidgetItem):
    """Tree item that sorts numerically by the active column's raw value."""

    def __lt__(self, other):
        tree = self.treeWidget()
        col = getattr(tree, "_sort_column", 0)
        a = self.data(col, Qt.UserRole)
        b = other.data(col, Qt.UserRole)
        if a is None:
            return b is not None
        if b is None:
            return False
        return a < b


class HierarchyTree(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._view = None
        self._threshold = 0
        self._sort_column = 0
        self._populated_once = False
        self.setAlternatingRowColors(True)
        self.setUniformRowHeights(True)
        self.setColumnCount(1)
        self.setHeaderLabels(["Hierarchy"])
        self.header().setSectionsClickable(True)
        self.header().sectionClicked.connect(self._on_header_clicked)
        self.itemExpanded.connect(self._on_expand)

    # -- configuration -----------------------------------------------------
    def set_view(self, view: TreeView):
        self._view = view
        self.rebuild()

    def set_threshold(self, n: int, rebuild: bool = True):
        self._threshold = n
        if rebuild and self._view is not None:
            self.rebuild()

    # -- building ----------------------------------------------------------
    def rebuild(self):
        expanded = self._expanded_paths() if self._populated_once else None
        self.clear()
        if self._view is None:
            return
        labels = ["Hierarchy"] + [c.label for c in self._view.columns]
        self.setColumnCount(len(labels))
        self.setHeaderLabels(labels)
        for path in self._view.roots:
            self.addTopLevelItem(self._make_item(path))
        if expanded is None:
            # first population: TOP + first-level children expanded
            self._populated_once = True
            for i in range(self.topLevelItemCount()):
                item = self.topLevelItem(i)
                item.setExpanded(True)
                for j in range(item.childCount()):
                    item.child(j).setExpanded(True)
        else:
            # preserve the previously expanded nodes
            for path in expanded:
                self._locate_and_expand(path)
        self.resizeColumnToContents(0)

    def _passes_threshold(self, path: str) -> bool:
        if self._threshold <= 0:
            return True
        return float(self._view.counts.get(path, 0)) >= self._threshold

    def _make_item(self, path: str) -> HierarchyItem:
        item = HierarchyItem([path.rsplit("/", 1)[-1]])
        item.setData(0, Qt.UserRole, path)
        for ci, col in enumerate(self._view.columns, start=1):
            v = col.series.get(path, None)
            item.setText(ci, col.fmt(v))
            item.setData(ci, Qt.UserRole, _sortable(v))
        if self._visible_children(path):
            # placeholder child so the expand arrow is shown before lazy population
            item.addChild(QTreeWidgetItem())
        return item

    def _visible_children(self, path: str):
        return [c for c in self._view.children.get(path, []) if self._passes_threshold(c)]

    def _populate(self, item: HierarchyItem, path: str):
        if item.childCount() > 0 and item.child(0).data(0, Qt.UserRole) is not None:
            return  # already populated with real children
        while item.childCount() > 0:  # drop the placeholder
            item.takeChild(0)
        for child_path in self._visible_children(path):
            item.addChild(self._make_item(child_path))

    def _on_expand(self, item: HierarchyItem):
        self._populate(item, item.data(0, Qt.UserRole))

    # -- sorting -----------------------------------------------------------
    def _on_header_clicked(self, col: int):
        order = self.header().sortIndicatorOrder()
        if self.header().sortIndicatorSection() == col and order == Qt.DescendingOrder:
            order = Qt.AscendingOrder
        else:
            order = Qt.DescendingOrder
        self.header().setSortIndicator(col, order)
        self._sort_column = col
        for i in range(self.topLevelItemCount()):
            self._sort_item(self.topLevelItem(i), col, order)

    def _sort_item(self, item, col, order):
        if item.childCount() > 1:
            item.sortChildren(col, order)
        for i in range(item.childCount()):
            self._sort_item(item.child(i), col, order)

    # -- navigation --------------------------------------------------------
    def _locate_and_expand(self, path: str):
        segs = path.split("/")
        item = None
        for i in range(self.topLevelItemCount()):
            it = self.topLevelItem(i)
            if it.data(0, Qt.UserRole) == segs[0]:
                item = it
                break
        if item is None:
            return None
        for k in range(1, len(segs)):
            item.setExpanded(True)  # populates children via _on_expand
            target = "/".join(segs[: k + 1])
            found = None
            for j in range(item.childCount()):
                c = item.child(j)
                if c.data(0, Qt.UserRole) == target:
                    found = c
                    break
            if found is None:
                return None
            item = found
        item.setExpanded(True)
        return item

    def expand_to(self, path: str):
        item = self._locate_and_expand(path)
        if item is not None:
            self.setCurrentItem(item)
            self.scrollToItem(item)

    def _expanded_paths(self):
        out = []

        def walk(item):
            if item.isExpanded():
                p = item.data(0, Qt.UserRole)
                if p is not None:
                    out.append(p)
            for i in range(item.childCount()):
                walk(item.child(i))

        for i in range(self.topLevelItemCount()):
            walk(self.topLevelItem(i))
        return out
