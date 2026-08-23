"""Hierarchy tree-table widget (QTreeWidget) with lazy expand + per-level sort."""
import math

from PyQt5.QtCore import Qt, QRect, pyqtSignal
from PyQt5.QtGui import QFont, QFontDatabase
from PyQt5.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QHeaderView, QMenu, QMessageBox, QStyle, QStyledItemDelegate,
    QStyleOptionViewItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
)

from . import schema, theme
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


class GradientRangeDialog(QDialog):
    """Dialog to edit a percentage metric's gradient [min, max] range."""

    def __init__(self, label, lo, hi, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Gradient range — {label}")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.min_spin = QDoubleSpinBox()
        self.min_spin.setRange(-1.0, 1.0)
        self.min_spin.setDecimals(2)
        self.min_spin.setSingleStep(0.01)
        self.min_spin.setValue(lo)
        self.max_spin = QDoubleSpinBox()
        self.max_spin.setRange(-1.0, 1.0)
        self.max_spin.setDecimals(2)
        self.max_spin.setSingleStep(0.01)
        self.max_spin.setValue(hi)
        form.addRow("Min", self.min_spin)
        form.addRow("Max", self.max_spin)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self):
        if self.min_spin.value() > self.max_spin.value():
            QMessageBox.warning(self, "Invalid range", "Min must be ≤ Max.")
            return
        self.accept()

    def range(self):
        return self.min_spin.value(), self.max_spin.value()


class HierarchyTree(QTreeWidget):
    sort_changed = pyqtSignal(str)  # human-readable sort summary
    gradient_range_changed = pyqtSignal()  # a gradient range was edited here
    node_clicked = pyqtSignal(str)  # a hierarchy path was clicked (for contours)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._view = None
        self._threshold = 0
        self._sort_column = 0
        self._sort_order = Qt.AscendingOrder
        self._sort_active = False
        self._populated_once = False
        self._path_items = {}   # hierarchy path -> item (for lazy density updates)
        self._density_col = None
        self.setAlternatingRowColors(True)
        self.setUniformRowHeights(True)
        self.setItemDelegate(BarDelegate(self))
        self.setColumnCount(1)
        self.setHeaderLabels(["Hierarchy"])
        self.header().setSectionsClickable(True)
        self.header().sectionClicked.connect(self._on_header_clicked)
        self.itemExpanded.connect(self._on_expand)
        self.itemClicked.connect(self._on_item_clicked)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.header().setContextMenuPolicy(Qt.CustomContextMenu)
        self.header().customContextMenuRequested.connect(self._on_header_context_menu)

    def _on_item_clicked(self, item, _col):
        """Emit the clicked hierarchy path (skip the lazy-expand placeholder)."""
        path = item.data(0, Qt.UserRole)
        if path is not None:
            self.node_clicked.emit(path)

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
        self._path_items = {}
        if self._view is None:
            return
        labels = ["Hierarchy"] + [c.label for c in self._view.columns]
        self.setColumnCount(len(labels))
        self.setHeaderLabels(labels)
        # the density column is the last (physical-only); refresh it via update_density
        self._density_col = next((ci for ci, c in enumerate(self._view.columns, 1)
                                  if c.key == "density"), None)
        # hierarchy name fits its content; metric columns stretch evenly
        self.header().setSectionResizeMode(0, QHeaderView.Interactive)
        for ci in range(1, len(labels)):
            self.header().setSectionResizeMode(ci, QHeaderView.Stretch)
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
        self._path_items[path] = item
        for ci, col in enumerate(self._view.columns, start=1):
            v = col.series.get(path, None)
            item.setText(ci, col.fmt(v))
            item.setData(ci, Qt.UserRole, _sortable(v))
            if col.gradient:
                self._set_gradient_bar(item, ci, col, v)
            elif col.bar is not None:
                self._set_ratio_bar(item, ci, col, path)
        if self._visible_children(path):
            # placeholder child so the expand arrow is shown before lazy population
            item.addChild(QTreeWidgetItem())
        return item

    def update_density(self, path: str, value: float):
        """Refresh one hierarchy's Density% cell after a background computation."""
        item = self._path_items.get(path)
        col = self._density_col
        if item is None or col is None or self._view is None:
            return
        column = self._view.columns[col - 1]
        item.setText(col, column.fmt(value))
        item.setData(col, Qt.UserRole, _sortable(value))
        self._set_gradient_bar(item, col, column, value)

    def _set_gradient_bar(self, item, ci, col, v):
        if v is None:
            return
        try:
            f = float(v)
        except (TypeError, ValueError):
            return
        if math.isnan(f):
            return
        lo, hi = schema.gradient_range(col.key)
        t = (f - lo) / (hi - lo) if hi > lo else 0.0
        t = max(0.0, min(1.0, t))
        item.setData(ci, BAR_ROLE, t)
        goodness = t if col.gradient == "higher_better" else 1.0 - t
        item.setData(ci, BAR_COLOR_ROLE, theme.quality_color(goodness))

    def _set_ratio_bar(self, item, ci, col, path):
        r = col.bar.get(path, None)
        if r is None:
            return
        try:
            f = float(r)
            if not math.isnan(f):
                item.setData(ci, BAR_ROLE, f)
                item.setData(ci, BAR_COLOR_ROLE,
                             theme.MACRO_BAR_COLOR if col.is_macro else theme.BAR_COLOR)
        except (TypeError, ValueError):
            pass

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
        if self._sort_active and item.childCount() > 1:
            item.sortChildren(self._sort_column, self._sort_order)
        self.resizeColumnToContents(0)

    # -- sorting -----------------------------------------------------------
    def _on_header_clicked(self, col: int):
        order = self.header().sortIndicatorOrder()
        if self.header().sortIndicatorSection() == col and order == Qt.DescendingOrder:
            order = Qt.AscendingOrder
        else:
            order = Qt.DescendingOrder
        self.header().setSortIndicator(col, order)
        self._sort_column = col
        self._sort_order = order
        self._sort_active = True
        for i in range(self.topLevelItemCount()):
            self._sort_item(self.topLevelItem(i), col, order)
        label = self.headerItem().text(col)
        direction = "desc" if order == Qt.DescendingOrder else "asc"
        self.sort_changed.emit(f"Sorted by {label} ({direction})")

    def _sort_item(self, item, col, order):
        if item.childCount() > 1:
            item.sortChildren(col, order)
        for i in range(item.childCount()):
            self._sort_item(item.child(i), col, order)

    # -- context menu ------------------------------------------------------
    def _on_context_menu(self, pos):
        item = self.itemAt(pos)
        if item is None:
            return
        col_idx = self.columnAt(pos.x())
        if col_idx != 0:
            return
        path = item.data(0, Qt.UserRole)
        if path is None:
            return
        menu = QMenu(self)
        menu.addAction("Copy full name", lambda: self._copy(path.split('/', 1)[1]))
        menu.addAction("Copy base name", lambda: self._copy(path.rsplit("/", 1)[-1]))
        menu.exec_(self.viewport().mapToGlobal(pos))

    def _on_header_context_menu(self, pos):
        col_idx = self.header().logicalIndexAt(pos)
        if self._view is None or not (0 < col_idx <= len(self._view.columns)):
            return
        column = self._view.columns[col_idx - 1]
        if not column.gradient:
            return
        menu = QMenu(self)
        menu.addAction("Set gradient range…", lambda: self._edit_gradient_range(column))
        menu.exec_(self.header().viewport().mapToGlobal(pos))

    def _edit_gradient_range(self, column):
        lo, hi = schema.gradient_range(column.key)
        dlg = GradientRangeDialog(column.label, lo, hi, self)
        if dlg.exec_() == QDialog.Accepted:
            schema.set_gradient_range(column.key, *dlg.range())
            self.rebuild()
            self.gradient_range_changed.emit()

    @staticmethod
    def _copy(text: str):
        QApplication.clipboard().setText(text)

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
