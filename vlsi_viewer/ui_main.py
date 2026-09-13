"""Main window: toolbar (search / threshold / macros); designs injected by the CLI."""
import logging

from PyQt5.QtWidgets import (
    QAction, QCheckBox, QComboBox, QLabel, QLineEdit, QMainWindow, QSpinBox,
    QSplitter, QStackedWidget, QToolBar,
)

from . import config
from .model import view_for_single
from .ui_compare import CompareWidget
from .ui_layout import LayoutView
from .ui_metal import CellDetailPanel, MetalPanel
from .ui_search import SearchDialog
from .ui_tree import HierarchyTree

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, design1=None, design2=None, physical=None, metal=None,
                 threshold=config.DEFAULT_MIN_INST_COUNT, include_macros=False):
        """``metal`` is a :class:`~vlsi_viewer.metal.MetalData`, and its own mode.

        Metal mode shows no hierarchy: the tree, the compare view and the hierarchy toolbar
        are not built at all. That is not just tidiness - the tree drives the contour and
        the ``Density%`` column, neither of which means anything for a routing map, and a
        search box that filters a tree nobody can see is worse than no search box. It has a
        toolbar of its own, holding the map's value range and nothing else.

        Its central widget is three panes: the cell readout, the map, and the layer selection.
        The readout is on the opposite side from the selection because in one column the two
        tables fought over the same height, and the loser went behind a scrollbar.
        """
        super().__init__()
        self.setWindowTitle("VLSI Hierarchy Analyzer")
        self.resize(1400, 800)

        self._design1 = design1
        self._design2 = design2
        self._physical = physical
        self._metal = metal
        self._layout = None
        self._panel = None
        self._detail = None
        self._density = None

        self._stack = QStackedWidget()
        self._tree = HierarchyTree()
        self._compare = CompareWidget()
        self._stack.addWidget(self._tree)
        self._stack.addWidget(self._compare)

        if metal is not None:
            self._layout = LayoutView(metal, external_controls=True)
            self._panel = MetalPanel(metal, self._layout)
            # The readout is its own pane on the other side of the map: in one column the
            # layer list and the cell detail competed for the same height, and whichever lost
            # went behind a scrollbar.
            self._detail = CellDetailPanel(metal, self._panel.current_kind)
            splitter = QSplitter()
            splitter.addWidget(self._detail)
            splitter.addWidget(self._layout)
            splitter.addWidget(self._panel)
            # 1:4:1, not 0:1:0. With the side panes at zero stretch they never give up a pixel:
            # the map absorbed the whole loss as the window narrowed, down to a 292 px sliver
            # against a 400 px layer list. A small share for each side pane makes them yield
            # proportionally, while the map keeps the largest share of everything left over.
            splitter.setStretchFactor(0, 1)
            splitter.setStretchFactor(1, 4)
            splitter.setStretchFactor(2, 1)
            # A pane is sized from its *hint* by default, and the layer table's hint grows with
            # the font - under a wide one it asked for 519 px and the map opened 200 px narrower
            # than it needed to be. These are the starting widths; the stretch above sets how
            # they move, and the divider overrides both.
            splitter.setSizes([300, 680, 400])
            splitter.setChildrenCollapsible(False)
            self.setCentralWidget(splitter)
            self._hover_label = QLabel("")
            self.statusBar().addPermanentWidget(self._hover_label)
            self._layout.hover_changed.connect(self._hover_label.setText)
            self._layout.cell_hovered.connect(self._detail.on_cell)
            self._panel.selection_changed.connect(self._detail.refresh)
        elif physical is not None:
            self._layout = LayoutView(physical)
            splitter = QSplitter()
            splitter.addWidget(self._stack)
            splitter.addWidget(self._layout)
            splitter.setStretchFactor(0, 3)
            splitter.setStretchFactor(1, 4)
            self.setCentralWidget(splitter)
            self._hover_label = QLabel("")
            self.statusBar().addPermanentWidget(self._hover_label)
            self._layout.hover_changed.connect(self._hover_label.setText)
            self._layout.status_message.connect(self._on_physical_status)
            from .model import density_column
            self._density = density_column(physical)
            self._density.series.ready.connect(self._on_density_ready)
            self._density.series.status.connect(self._on_density_status)
        else:
            self.setCentralWidget(self._stack)

        self._tree.sort_changed.connect(self._on_sort_changed)
        self._tree.node_clicked.connect(self._on_node_clicked)
        for t in (self._compare.v1, self._compare.v2, self._compare.diff):
            t.sort_changed.connect(self._on_sort_changed)

        if metal is None:
            self._build_toolbar()
            self._set_initial_options(threshold, include_macros)
        else:
            self._build_metal_toolbar()

        if design2 is not None:
            self._compare.set_designs(design1, design2)
            self._stack.setCurrentWidget(self._compare)

        self._apply_settings()
        self._show_status()

    # -- toolbar -----------------------------------------------------------
    def _build_toolbar(self):
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(tb)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search hierarchy…")
        self.search_edit.setFixedWidth(220)
        self.search_edit.returnPressed.connect(self._do_search)
        tb.addWidget(self.search_edit)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Exact", "Wildcard", "Regex"])
        tb.addWidget(self.mode_combo)

        find = QAction("Find", self)
        find.triggered.connect(self._do_search)
        tb.addAction(find)

        tb.addSeparator()

        tb.addWidget(QLabel("Min:"))
        self.min_spin = QSpinBox()
        self.min_spin.setRange(0, 10 ** 9)
        self.min_spin.valueChanged.connect(self._apply_settings)
        tb.addWidget(self.min_spin)

        self.macro_check = QCheckBox("Include macros")
        self.macro_check.stateChanged.connect(self._apply_settings)
        tb.addWidget(self.macro_check)

    def _build_metal_toolbar(self):
        """Metal mode's toolbar: the map's value range, and nothing about hierarchy.

        The widgets belong to `LayoutView` and `MetalPanel` - the view owns the ramp, the panel
        owns what the ramp is over - and neither places them; this is the only mode with a
        toolbar to put them in. They keep their names on those objects, so nothing that pokes
        at ``layer.min_spin`` has to care, and `window.min_spin` stays free for the hierarchy
        toolbar's instance-count threshold.
        """
        tb = QToolBar("Range")
        tb.setObjectName("metal_range_toolbar")
        tb.setMovable(False)
        # It is the only route to the ramp, so a right-click must not be able to hide it.
        tb.toggleViewAction().setVisible(False)
        self.addToolBar(tb)
        tb.addWidget(QLabel("Min:"))
        tb.addWidget(self._layout.min_spin)
        tb.addWidget(QLabel("Max:"))
        tb.addWidget(self._layout.max_spin)
        tb.addWidget(self._panel.auto_btn)
        tb.addWidget(self._layout.fit_btn)
        tb.addSeparator()
        # The peak, so the absolute scale is never in doubt while Auto has the ramp stretched.
        tb.addWidget(self._panel.peak_label)

    def _set_initial_options(self, threshold, include_macros):
        self.min_spin.blockSignals(True)
        self.macro_check.blockSignals(True)
        self.min_spin.setValue(threshold)
        self.macro_check.setChecked(include_macros)
        self.min_spin.blockSignals(False)
        self.macro_check.blockSignals(False)

    # -- actions -----------------------------------------------------------
    def _apply_settings(self):
        # Metal mode has no toolbar to read a threshold or a macro toggle from, and no tree
        # to apply them to.
        if self._metal is not None:
            return
        threshold = self.min_spin.value()
        include_macros = self.macro_check.isChecked()
        if self._design2 is None:
            self._tree.set_threshold(threshold)
            if self._design1 is not None:
                view = view_for_single(self._design1, include_macros)
                if self._density is not None:
                    view.columns.append(self._density)  # shared cache across rebuilds
                self._tree.set_view(view)
        else:
            self._compare.configure(threshold, include_macros)

    def _on_sort_changed(self, msg: str):
        self.statusBar().showMessage(msg)

    def _on_node_clicked(self, path: str):
        """Clicking a hierarchy node toggles its contour in the layout view."""
        if getattr(self, "_layout", None) is not None:
            self._layout.toggle_contour(path)

    def _on_density_ready(self, path: str, value: float):
        """A background density computation finished -> refresh that tree row."""
        self._tree.update_density(path, value)

    def _on_density_status(self, pending: int):
        """Report background density progress in the status bar."""
        if pending > 0:
            self.statusBar().showMessage(f"Computing density… ({pending} pending)")
        else:
            self.statusBar().showMessage("Physical mode · density up to date")

    def _on_physical_status(self, msg: str):
        self.statusBar().showMessage(msg)

    def _do_search(self):
        if self._design1 is None:
            return
        include_macros = self.macro_check.isChecked()
        v1 = view_for_single(self._design1, include_macros)
        v2 = view_for_single(self._design2, include_macros) if self._design2 is not None else None
        dlg = SearchDialog(v1, v2, self.search_edit.text().strip(),
                           self.mode_combo.currentText().lower(), self)
        dlg.selected.connect(self._jump_to)
        dlg.exec_()

    def _jump_to(self, path: str, version: str):
        if self._design2 is None:
            self._tree.expand_to(path)
        else:
            tree = self._compare.v1 if version == "v1" else self._compare.v2
            self._compare.setCurrentWidget(tree)
            tree.expand_to(path)

    def _show_status(self):
        if self._metal is not None:
            # The die size, because nothing else on screen says the grid is 620 um across and
            # a density map is read at a physical scale.
            x0, y0, x1, y1 = self._metal.extent
            self.statusBar().showMessage(
                f"Metal mode · {self._metal.rows}×{self._metal.cols} grid @ "
                f"{self._metal.grid_size:g} um · die {x1 - x0:g}×{y1 - y0:g} um · "
                f"{self._metal.stack_note} · top {self._metal.top_name}")
            return
        if self._physical is not None:
            self.statusBar().showMessage(
                f"Physical mode · {self._physical.rows}×{self._physical.cols} grid · "
                f"top {self._physical.top_name}")
            return
        if self._design1 is None:
            self.statusBar().showMessage("No data loaded.")
            return
        if self._design2 is not None:
            self.statusBar().showMessage(
                f"Comparing {len(self._design1.instance_paths)} vs "
                f"{len(self._design2.instance_paths)} blocks")
            return
        msg = (f"{len(self._design1.instance_paths)} block(s) · "
               f"{self._design1.hier.shape[0]} hierarchies")
        if self._design1.missing_cells:
            msg += f" · {len(self._design1.missing_cells)} missing cell(s)"
        self.statusBar().showMessage(msg)
