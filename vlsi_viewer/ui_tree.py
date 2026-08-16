"""Hierarchy tree-table widget (QTreeWidget) with lazy expand + per-level sort."""
import math

from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QFont, QFontDatabase
from PyQt5.QtWidgets import (
    QStyle, QStyledItemDelegate, QStyleOptionViewItem, QTreeWidget, QTreeWidgetItem,
)

from . import theme
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


BAR_ROLE = Qt.UserRole + 1
BAR_COLOR_ROLE = Qt.UserRole + 2
_MONO_FAMILY = QFontDatabase.systemFont(QFontDatabase.FixedFont).family()


class BarDelegate(QStyledItemDelegate):
    """Paints a background progress bar for cells carrying a BAR_ROLE ratio."""

    def paint(self, painter, option, index):
        ratio = index.data(BAR_ROLE)
        if ratio is None:
            super().paint(painter, option, index)
            return

        painter.save()
        if option.state & QStyle.State_Selected:
            bg = theme.SELECTION_C
        elif option.features & QStyleOptionViewItem.Alternate:
            bg = theme.SURFACE_ALT_C
        else:
            bg = theme.SURFACE_C
        painter.fillRect(option.rect, bg)

        bar_color = index.data(BAR_COLOR_ROLE)
        if bar_color is None:
            bar_color = theme.BAR_COLOR
        try:
            r = float(ratio)
        except (TypeError, ValueError):
            r = 0.0
        r = max(0.0, min(1.0, r))
        if r > 0.0:
            w = int(option.rect.width() * r)
            painter.fillRect(QRect(option.rect.left(), option.rect.top(), w, option.rect.height()), bar_color)

        text = index.data(Qt.DisplayRole)
        if text is not None and text != "":
            painter.setPen(theme.TEXT_C)
            f = QFont(option.font)
            f.setFamily(_MONO_FAMILY)
            painter.setFont(f)
            painter.drawText(option.rect.adjusted(4, 0, -4, 0),
                             Qt.AlignVCenter | Qt.AlignRight, str(text))
        painter.restore()


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
        self.setItemDelegate(BarDelegate(self))
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
            # first population: expand the root node one level only
            self._populated_once = True
            for i in range(self.topLevelItemCount()):
                self.topLevelItem(i).setExpanded(True)
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
            if col.bar is not None:
                r = col.bar.get(path, None)
                if r is not None:
                    try:
                        f = float(r)
                        if not math.isnan(f):
                            item.setData(ci, BAR_ROLE, f)
                            item.setData(ci, BAR_COLOR_ROLE,
                                         theme.MACRO_BAR_COLOR if col.is_macro else theme.BAR_COLOR)
                    except (TypeError, ValueError):
                        pass
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
