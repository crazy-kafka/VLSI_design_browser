"""Main window: toolbar (search / threshold / macros); designs injected by the CLI."""
import logging
import os

from PyQt5.QtWidgets import (
    QAction, QCheckBox, QComboBox, QLabel, QLineEdit, QMainWindow, QSpinBox,
    QStackedWidget, QToolBar,
)

from . import config
from .model import view_for_single
from .ui_compare import CompareWidget
from .ui_search import SearchDialog
from .ui_tree import HierarchyTree

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self, design1=None, design2=None,
                 threshold=config.DEFAULT_MIN_INST_COUNT, include_macros=False):
        super().__init__()
        self.setWindowTitle("VLSI Hierarchy Analyzer")
        self.resize(1200, 700)

        self._design1 = design1
        self._design2 = design2

        self._stack = QStackedWidget()
        self._tree = HierarchyTree()
        self._compare = CompareWidget()
        self._stack.addWidget(self._tree)
        self._stack.addWidget(self._compare)
        self.setCentralWidget(self._stack)

        self._build_toolbar()
        self._set_initial_options(threshold, include_macros)

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

    def _set_initial_options(self, threshold, include_macros):
        self.min_spin.blockSignals(True)
        self.macro_check.blockSignals(True)
        self.min_spin.setValue(threshold)
        self.macro_check.setChecked(include_macros)
        self.min_spin.blockSignals(False)
        self.macro_check.blockSignals(False)

    # -- actions -----------------------------------------------------------
    def _apply_settings(self):
        threshold = self.min_spin.value()
        include_macros = self.macro_check.isChecked()
        if self._design2 is None:
            self._tree.set_threshold(threshold)
            if self._design1 is not None:
                self._tree.set_view(view_for_single(self._design1, include_macros))
        else:
            self._compare.configure(threshold, include_macros)

    def _do_search(self):
        if self._design1 is None:
            return
        view = view_for_single(self._design1, self.macro_check.isChecked())
        dlg = SearchDialog(view, self.search_edit.text().strip(), self.mode_combo.currentText().lower(), self)
        dlg.selected.connect(self._jump_to)
        dlg.exec_()

    def _jump_to(self, path: str):
        if self._design2 is None:
            self._tree.expand_to(path)
        else:
            self._compare.currentWidget().expand_to(path)

    def _show_status(self):
        if self._design1 is None:
            self.statusBar().showMessage("No data loaded.")
            return
        if self._design2 is not None:
            self.statusBar().showMessage(
                f"Comparing {os.path.basename(self._design1.instance_path)} vs "
                f"{os.path.basename(self._design2.instance_path)}")
            return
        msg = (f"{os.path.basename(self._design1.instance_path)} · "
               f"{self._design1.hier.shape[0]} hierarchies")
        if self._design1.missing_cells:
            msg += f" · {len(self._design1.missing_cells)} missing cell(s)"
        self.statusBar().showMessage(msg)
