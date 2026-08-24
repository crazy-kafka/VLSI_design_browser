"""Layout view: 2-D heat map + boundary outlines, driven by GenericGraphicsView."""
from PyQt5.QtCore import QEvent, QPointF, Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QPainter, QPen, QPixmap, QPolygonF
from PyQt5.QtWidgets import (
    QComboBox, QDoubleSpinBox, QGraphicsPixmapItem, QGraphicsPolygonItem,
    QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from .genericView import GenericGraphicsView
from .heatmap import grid_to_image, thermal_color
from .physical import PhysicalData

HEAT_TYPES = [("density", "Cell density"), ("leakage", "Leakage power"),
              ("dynamic", "Dynamic power"), ("ulvt", "ULVT density")]


class LayoutView(QWidget):
    """Right-hand panel: GenericGraphicsView heat map + controls + legend.

    Scene coordinates are physical (x right, y up): the heat image is flipped
    vertically and boundary vertices are mapped ``(x, y) -> (x, y0 + y1 - y)``.
    """

    hover_changed = pyqtSignal(str)
    status_message = pyqtSignal(str)  # transient status (e.g. "computing contour")

    def __init__(self, physical: PhysicalData, parent=None):
        super().__init__(parent)
        self._physical = physical
        self._kind = "density"
        self._lo = 0.0
        self._hi = 1.0
        self._last_scene_pt = None

        self._build_controls()
        self._view = GenericGraphicsView(self)
        self._view.enableFitKet(Qt.Key_F)
        self._view.sigSceneMouseMoved.connect(self._on_hover)
        scene = self._view.scene()
        self._pix_item = QGraphicsPixmapItem()
        scene.addItem(self._pix_item)
        self._boundary_items = []
        self._contour_items = []
        self._contour_path = None
        self._contour_token = 0
        from .model import ContourWorker
        self._contour_worker = ContourWorker()
        self._contour_worker.contour_ready.connect(self._on_contour_ready)

        root = QVBoxLayout(self)
        root.addLayout(self._controls_row)
        root.addWidget(self._view, 1)

        self._build_legend()
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

        fit_btn = QPushButton("Fit")
        fit_btn.clicked.connect(self._fit)
        self._controls_row.addWidget(fit_btn)
        self._controls_row.addStretch(1)

    # -- fixed overlay legend ---------------------------------------------
    def _build_legend(self):
        """Create a vertical legend widget pinned to the view's top-right."""
        self._legend = LegendWidget(self._view)
        self._view.installEventFilter(self)
        self._position_legend()

    def _position_legend(self):
        m = 8
        self._legend.move(self._view.width() - self._legend.width() - m, m)

    def eventFilter(self, obj, ev):
        if obj is self._view and ev.type() == QEvent.Resize:
            self._position_legend()
        return super().eventFilter(obj, ev)

    # -- rendering ---------------------------------------------------------
    def _on_type(self, idx):
        self._kind = HEAT_TYPES[idx][0]
        self._autoset_range()
        self.refresh()
        if self._last_scene_pt is not None:
            self._on_hover(self._last_scene_pt)

    def _apply_range(self):
        self._lo = self.min_spin.value()
        self._hi = max(self.max_spin.value(), self._lo + 1e-9)
        self._legend.set_range(self._lo, self._hi)
        self.refresh()

    def _autoset_range(self):
        arr = self._physical.heat(self._kind)
        hi = float(arr.max()) if arr.size else 1.0
        lo = 0.0
        if self._kind not in ("density", "ulvt"):
            hi = max(hi, 1e-6)
        self.min_spin.blockSignals(True)
        self.max_spin.blockSignals(True)
        self.min_spin.setValue(lo)
        self.max_spin.setValue(hi if hi > 0 else 1.0)
        self.min_spin.blockSignals(False)
        self.max_spin.blockSignals(False)
        self._lo, self._hi = lo, hi if hi > 0 else 1.0
        self._legend.set_range(self._lo, self._hi)

    def _on_hover(self, scene_pt):
        """Emit the physical coordinates + heat value for the hovered scene pt."""
        self._last_scene_pt = scene_pt
        x0, y0, x1, y1 = self._physical.extent
        px = scene_pt.x()
        py = y0 + y1 - scene_pt.y()          # invert _flip_y
        g = self._physical.grid_size
        ix = int((px - x0) // g)
        iy = int((py - y0) // g)
        if 0 <= ix < self._physical.cols and 0 <= iy < self._physical.rows:
            val = self._physical.heat(self._kind)[iy, ix]
            self.hover_changed.emit(
                f"x={px:.2f}  y={py:.2f}   {self._kind}[{iy},{ix}] = {val:.3f}")
        else:
            self.hover_changed.emit(f"x={px:.2f}  y={py:.2f}")

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

    # -- hierarchy contour overlay ----------------------------------------
    def toggle_contour(self, path: str):
        """Show the contour for ``path``; click again (same path) hides it.

        The exact contour is computed on a background worker so the GUI stays
        responsive; the dashed overlay appears when the result arrives. Clicking
        the same node again clears it immediately (a stale result is discarded).
        """
        if self._contour_path == path:
            self._clear_contour()
            self.status_message.emit("")
            return
        self._clear_contour()
        self._contour_path = path
        self._contour_token += 1
        self.status_message.emit(f"Computing exact contour for {path}…")
        self._contour_worker.request(self._physical, path, self._contour_token)

    def _on_contour_ready(self, path, token, loops):
        """Draw the computed contour unless a newer selection superseded it."""
        if token != self._contour_token or path != self._contour_path:
            return  # stale result from an older click
        for loop in loops:
            poly = QPolygonF([self._flip_y(x, y) for (x, y) in loop])
            item = QGraphicsPolygonItem(poly)
            pen = QPen(QColor(0xFF, 0xD4, 0x00), 2)
            pen.setStyle(Qt.DashLine)
            item.setPen(pen)
            item.setBrush(QBrush(Qt.NoBrush))
            item.setZValue(20)  # above boundary outlines (z=10)
            self._view.scene().addItem(item)
            self._contour_items.append(item)
        self.status_message.emit(f"Contour: {path}")

    def _clear_contour(self):
        for it in self._contour_items:
            self._view.scene().removeItem(it)
        self._contour_items = []
        self._contour_path = None

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


class LegendWidget(QWidget):
    """A vertical thermal legend overlaid on the layout view.

    Paints a black(0) -> white(1) gradient bar with value ticks at 0/25/50/75/100%
    of the current (lo, hi) range. It is a child widget of the graphics view (not
    a scene item), so pan / zoom / fit never move it.
    """

    _W = 92
    _H = 200
    _BAR_W = 18
    _BAR_X = 6
    _TOP = 8
    _BOTTOM = 190

    def __init__(self, parent=None):
        super().__init__(parent)
        self._lo = 0.0
        self._hi = 1.0
        self.setFixedSize(self._W, self._H)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def set_range(self, lo, hi):
        self._lo = lo
        self._hi = hi
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 110))  # readable backdrop
        bar_h = self._BOTTOM - self._TOP

        for y in range(self._TOP, self._BOTTOM):
            t = 1.0 - (y - self._TOP) / max(1, bar_h - 1)
            p.setPen(QColor(*thermal_color(t)))
            p.drawLine(self._BAR_X, y, self._BAR_X + self._BAR_W, y)

        p.setPen(QColor(0xE8, 0xEE, 0xF2))
        p.drawRect(self._BAR_X, self._TOP, self._BAR_W, bar_h)

        for f in (0.0, 0.25, 0.5, 0.75, 1.0):
            y = self._BOTTOM - int(round(f * bar_h))  # 0% at bottom, 100% at top
            val = self._lo + f * (self._hi - self._lo)
            p.setPen(QColor(0xE8, 0xEE, 0xF2))
            p.drawLine(self._BAR_X + self._BAR_W, y, self._BAR_X + self._BAR_W + 4, y)
            p.setPen(QColor(255, 255, 255))
            p.drawText(self._BAR_X + self._BAR_W + 7, y + 4, f"{val:.3g}")
        p.end()
