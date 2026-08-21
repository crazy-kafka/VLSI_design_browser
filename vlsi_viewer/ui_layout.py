"""Layout view: 2-D heat map + boundary outlines, driven by GenericGraphicsView."""
from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QBrush, QColor, QPainter, QPen, QPixmap, QPolygonF
from PyQt5.QtWidgets import (
    QComboBox, QDoubleSpinBox, QGraphicsPixmapItem, QGraphicsPolygonItem,
    QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from .genericView import GenericGraphicsView
from .heatmap import grid_to_image
from .physical import PhysicalData

HEAT_TYPES = [("density", "Cell density"), ("leakage", "Leakage power"),
              ("dynamic", "Dynamic power")]


class LayoutView(QWidget):
    """Right-hand panel: GenericGraphicsView heat map + controls + legend.

    Scene coordinates are physical (x right, y up): the heat image is flipped
    vertically and boundary vertices are mapped ``(x, y) -> (x, y0 + y1 - y)``.
    """

    def __init__(self, physical: PhysicalData, parent=None):
        super().__init__(parent)
        self._physical = physical
        self._kind = "density"
        self._lo = 0.0
        self._hi = 1.0

        self._build_controls()
        self._view = GenericGraphicsView(self)
        self._view.enableFitKet(Qt.Key_F)
        scene = self._view.scene()
        self._pix_item = QGraphicsPixmapItem()
        scene.addItem(self._pix_item)
        self._boundary_items = []

        root = QVBoxLayout(self)
        root.addLayout(self._controls_row)
        root.addWidget(self._view, 1)
        root.addLayout(self._legend_row())

        self._autoset_range()
        self.refresh()
        self._fit()

    # -- controls ----------------------------------------------------------
    def _build_controls(self):
        self._controls_row = QHBoxLayout()
        self._controls_row.addWidget(QLabel("Map:"))
        self.type_combo = QComboBox()
        for _key, label in HEAT_TYPES:
            self.type_combo.addItem(label)
        self.type_combo.currentIndexChanged.connect(self._on_type)
        self._controls_row.addWidget(self.type_combo)

        self._controls_row.addWidget(QLabel("Min:"))
        self.min_spin = QDoubleSpinBox()
        self.min_spin.setDecimals(3)
        self.min_spin.setRange(0.0, 1e12)
        self.min_spin.valueChanged.connect(self._apply_range)
        self._controls_row.addWidget(self.min_spin)
        self._controls_row.addWidget(QLabel("Max:"))
        self.max_spin = QDoubleSpinBox()
        self.max_spin.setDecimals(3)
        self.max_spin.setRange(1e-6, 1e12)
        self.max_spin.valueChanged.connect(self._apply_range)
        self._controls_row.addWidget(self.max_spin)

        self._controls_row.addWidget(QLabel("Grid:"))
        self.grid_spin = QSpinBox()
        self.grid_spin.setRange(1, 1000)
        self.grid_spin.setValue(int(self._physical.grid_size))
        self.grid_spin.valueChanged.connect(self._on_grid)
        self._controls_row.addWidget(self.grid_spin)

        fit_btn = QPushButton("Fit")
        fit_btn.clicked.connect(self._fit)
        self._controls_row.addWidget(fit_btn)
        self._controls_row.addStretch(1)

    def _legend_row(self):
        row = QHBoxLayout()
        row.addWidget(QLabel("Legend"))
        bar = QLabel()
        bar.setFixedSize(120, 14)
        bar.setPixmap(_legend_pixmap())
        row.addWidget(bar)
        self.legend_lo = QLabel("0")
        self.legend_hi = QLabel("1")
        row.addWidget(self.legend_lo)
        row.addWidget(self.legend_hi)
        row.addStretch(1)
        return row

    # -- rendering ---------------------------------------------------------
    def _on_type(self, idx):
        self._kind = HEAT_TYPES[idx][0]
        self._autoset_range()
        self.refresh()

    def _on_grid(self, _v):
        from . import physical as ph
        self._physical = ph.build_physical(
            self._physical._src_paths, self._physical._src_cell_path,
            grid_size=float(self.grid_spin.value()))
        self._autoset_range()
        self.refresh()
        self._fit()

    def _apply_range(self):
        self._lo = self.min_spin.value()
        self._hi = max(self.max_spin.value(), self._lo + 1e-9)
        self.refresh()

    def _autoset_range(self):
        arr = self._physical.heat(self._kind)
        hi = float(arr.max()) if arr.size else 1.0
        lo = 0.0
        if self._kind != "density":
            hi = max(hi, 1e-6)
        self.min_spin.blockSignals(True)
        self.max_spin.blockSignals(True)
        self.min_spin.setValue(lo)
        self.max_spin.setValue(hi if hi > 0 else 1.0)
        self.min_spin.blockSignals(False)
        self.max_spin.blockSignals(False)
        self._lo, self._hi = lo, hi if hi > 0 else 1.0
        self.legend_lo.setText(f"{self._lo:.3g}")
        self.legend_hi.setText(f"{self._hi:.3g}")

    def _flip_y(self, x, y):
        x0, y0, _x1, y1 = self._physical.extent
        return QPointF(x, y0 + y1 - y)

    def _rebuild_boundaries(self):
        for it in self._boundary_items:
            self._view.scene().removeItem(it)
        self._boundary_items = []
        for _name, pts in self._physical.boundary_polys:
            poly = QPolygonF([self._flip_y(x, y) for (x, y) in pts])
            item = QGraphicsPolygonItem(poly)
            item.setPen(QPen(QColor(0xE8, 0xEE, 0xF2), 0))
            item.setBrush(QBrush(Qt.NoBrush))
            item.setZValue(10)
            self._view.scene().addItem(item)
            self._boundary_items.append(item)

    def refresh(self):
        x0, y0, x1, y1 = self._physical.extent
        arr = self._physical.heat(self._kind)
        img = grid_to_image(arr, self._lo, self._hi).mirrored(False, True)
        self._pix_item.setPixmap(QPixmap.fromImage(img))
        self._pix_item.setOffset(QPointF(x0, y0))
        self._pix_item.setScale(self._physical.grid_size)
        self._rebuild_boundaries()
        self._view.updateBoundingRect()

    def _fit(self):
        self._view.updateBoundingRect()
        self._view.fit()


def _legend_pixmap(width=120, height=14):
    """A horizontal thermal gradient swatch for the legend."""
    from .heatmap import thermal_color
    pm = QPixmap(width, height)
    pm.fill(Qt.white)
    painter = QPainter(pm)
    for x in range(width):
        c = QColor(*thermal_color(x / (width - 1)))
        painter.setPen(c)
        painter.drawLine(x, 0, x, height)
    painter.end()
    return pm
