"""The "Selected region" pane: a summary and the second hierarchy tree."""
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QGroupBox, QLabel, QVBoxLayout, QWidget

from .model import view_for_region
from .ui_tree import HierarchyTree


class RegionPanel(QWidget):
    """Region tree below the main hierarchy tree.

    The pane is hidden while nothing is selected; the first selection shows it
    and clearing the selection hides it again. It retains the empty-state hint
    for the next time it is shown.
    """

    node_clicked = pyqtSignal(str)
    sort_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.summary = QLabel("Drag on the heat map to select a region")
        self.summary.setWordWrap(True)
        self.tree = HierarchyTree()
        self.tree.set_threshold(0, rebuild=False)
        self.tree.node_clicked.connect(self.node_clicked.emit)
        self.tree.sort_changed.connect(self.sort_changed.emit)

        box = QGroupBox("Selected region")
        layout = QVBoxLayout(box)
        layout.addWidget(self.summary)
        layout.addWidget(self.tree, 1)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(box)
        # Nothing is selected at start-up; the pane appears with the first selection.
        self.hide()

    def show_region(self, region, include_macros: bool = False,
                    reset_expansion: bool = True):
        """Populate the tree from a RegionData, update the summary and show the pane."""
        if reset_expansion:
            self.tree.reset_first_population()
        self.tree.set_view(view_for_region(region, include_macros))
        self.summary.setText(region.summary_text())
        self.show()

    def clear(self):
        """Empty the tree, return to the hint and hide the pane."""
        self.tree.clear_view()
        self.summary.setText("Drag on the heat map to select a region")
        self.hide()
