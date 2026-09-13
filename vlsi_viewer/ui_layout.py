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
    cell_hovered = pyqtSignal(int, int)   # grid cell under the cursor, or (-1, -1)

    def __init__(self, physical: PhysicalData, parent=None, external_controls=False):
        """``physical`` is any render source, not just :class:`PhysicalData`.

        It must expose ``extent``, ``grid_size``, ``rows``, ``cols``, ``boundary_polys`` and
        ``heat(kind)``. A source may also expose ``kinds()`` to supply its own map list -
        which is how metal mode replaces the combo entirely - and ``contour_for`` if it has
        contours at all. Duck-typing rather than a base class because the two grids have
        almost nothing else in common.

        ``external_controls`` leaves the controls row unparented so a side panel can adopt
        the min/max and Fit widgets; the attributes stay here either way, so nothing that
        pokes at ``layer.min_spin`` has to care.
        """
        super().__init__(parent)
        self._physical = physical
        self._external_controls = external_controls
        self._kinds = physical.kinds() if hasattr(physical, "kinds") else HEAT_TYPES
        self._contour_enabled = hasattr(physical, "contour_for")
        # A source whose values are ratios gets a fixed [0, 1] ramp: the whole point of the
        # metal metric is that 1.0 means every track consumed, so autoscaling to the data
        # would throw away the calibration.
        self._fixed_ratio = hasattr(physical, "kinds")
        self._kind = self._kinds[0][0]
        self._lo = 0.0
        self._hi = 1.0
        self._ranges = {}  # kind -> (lo, hi) the user last saw for that heat map
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
        if not external_controls:
            root.addLayout(self._controls_row)
        root.addWidget(self._view, 1)

        self._build_legend()
        self._autoset_range()
        self.refresh()
        self._fit()

    # -- controls ----------------------------------------------------------
    def _build_controls(self):
        # With ``external_controls`` the widgets below are placed by someone else - the metal
        # toolbar adopts the ramp's - so they are gathered into a throwaway layout instead of
        # the row this view would otherwise show. A widget left listed in a layout that is
        # never installed is a trap: adding that row to a layout later would pull the widgets
        # straight back out of the toolbar, which then silently has no Min/Max at all.
        self._controls_row = QHBoxLayout()
        row = self._controls_row if not self._external_controls else QHBoxLayout()
        row.addWidget(QLabel("Map:"))
        self.type_combo = QComboBox()
        for _key, label in self._kinds:
            self.type_combo.addItem(label)
        self.type_combo.currentIndexChanged.connect(self._on_type)
        row.addWidget(self.type_combo)

        row.addWidget(QLabel("Min:"))
        self.min_spin = QDoubleSpinBox()
        self.min_spin.setDecimals(3)
        self.min_spin.setRange(0.0, 1e12)
        self.min_spin.valueChanged.connect(self._apply_range)
        row.addWidget(self.min_spin)
        row.addWidget(QLabel("Max:"))
        self.max_spin = QDoubleSpinBox()
        self.max_spin.setDecimals(3)
        self.max_spin.setRange(1e-6, 1e12)
        self.max_spin.valueChanged.connect(self._apply_range)
        row.addWidget(self.max_spin)
        for box in (self.min_spin, self.max_spin):
            self._constrain(box)

        self.fit_btn = QPushButton("Fit")
        self.fit_btn.clicked.connect(self._fit)
        row.addWidget(self.fit_btn)
        row.addStretch(1)

    @staticmethod
    def _constrain(box):
        """Stop a spin box claiming the width of its widest possible value.

        A QDoubleSpinBox sizes itself for the longest string its range can produce, and the
        range here reaches 1e12 so the physical mode's power values fit. That is a 331 px hint
        for a box that shows three digits, and a hint is not free: it becomes the panel's
        minimum width, so the window could not shrink below ~1342 px, and a layout that hands
        a widget its size hint (a QSplitter does) reserved 942 px for a 230 px panel and left
        the difference as dead space.

        `setMaximumWidth` alone is the whole fix: both a QBoxLayout and a QToolBar bound the
        slot they give a widget by its maximum, so 96 px is what the layout reserves and the
        331 px hint never reaches the window's minimum. Do **not** add
        ``QSizePolicy.Ignored`` as well - it makes ``QWidgetItem::sizeHint()`` return zero
        width, and every row these boxes sit in ends with ``addStretch(1)``, which then takes
        the entire row and leaves the boxes 0 px wide and invisible.
        """
        box.setMaximumWidth(96)

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
        self.set_kind(self._kinds[idx][0])

    def set_kind(self, kind):
        """Select a map by key, keeping the per-map range the user left behind.

        Public because the metal panel drives the map from its layer checkboxes rather than
        from the combo, and both routes have to go through the same range bookkeeping or the
        min/max would reset depending on how the map was chosen.
        """
        self._ranges[self._kind] = (self._lo, self._hi)  # remember where we came from
        self._kind = kind
        saved = self._ranges.get(kind)
        if saved is None:
            self._autoset_range()   # first visit to this map: derive from the data
        else:
            self._set_range(*saved)  # revisit: restore what the user left behind
        self.refresh()
        if self._last_scene_pt is not None:
            self._on_hover(self._last_scene_pt)

    def _apply_range(self):
        self._lo = self.min_spin.value()
        self._hi = max(self.max_spin.value(), self._lo + 1e-9)
        self._legend.set_range(self._lo, self._hi)
        self.refresh()

    def set_range(self, lo, hi):
        """Set the ramp explicitly, the way the metal panel's Auto button does.

        Public counterpart of ``_set_range``: same push into the spin boxes and legend, plus
        the repaint, so a caller outside this class cannot land in a half-updated state.
        """
        self._set_range(lo, hi)
        self.refresh()

    def _set_range(self, lo, hi):
        """Push a range into the spin boxes and legend without re-entering _apply_range."""
        self.min_spin.blockSignals(True)
        self.max_spin.blockSignals(True)
        self.min_spin.setValue(lo)
        self.max_spin.setValue(hi)
        self.min_spin.blockSignals(False)
        self.max_spin.blockSignals(False)
        self._lo, self._hi = lo, hi
        self._legend.set_range(lo, hi)

    def _autoset_range(self):
        if self._fixed_ratio:
            # A ratio map is read against the top of its ramp, not against its own maximum.
            self._set_range(0.0, 1.0)
            return
        arr = self._physical.heat(self._kind)
        hi = float(arr.max()) if arr.size else 1.0
        lo = 0.0
        if self._kind not in ("density", "ulvt"):
            hi = max(hi, 1e-6)
        self._set_range(lo, hi if hi > 0 else 1.0)

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
            self.cell_hovered.emit(ix, iy)
        else:
            self.hover_changed.emit(f"x={px:.2f}  y={py:.2f}")
            self.cell_hovered.emit(-1, -1)

    def _flip_y(self, x, y):
        x0, y0, _x1, y1 = self._physical.extent
        return QPointF(x, y0 + y1 - y)

    def _rebuild_boundaries(self):
        for it in self._boundary_items:
            self._view.scene().removeItem(it)
        self._boundary_items = []
        top = getattr(self._physical, "top_name", None)
        for name, pts in self._physical.boundary_polys:
            poly = QPolygonF([self._flip_y(x, y) for (x, y) in pts])
            item = QGraphicsPolygonItem(poly)
            # The die outline is brighter than the sub-block ones. On a dark map "outside the
            # die" and "inside with no metal" are the same colour, so the edge is the only
            # thing separating them.
            item.setPen(QPen(QColor(0xE8, 0xEE, 0xF2) if name == top
                             else QColor(0x5A, 0x6A, 0x7A), 0))
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

        A no-op for a source with no contours - the metal grids have no instance boxes to
        outline. Nothing reaches here in metal mode anyway, since the tree that would call
        it is not shown, but a no-op is cheaper to reason about than an unreachable one.
        """
        if not self._contour_enabled:
            return
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

    Paints a navy(0) -> near-white(1) gradient bar (the INNOVUS ramp) with value ticks
    at 0/25/50/75/100% of the current (lo, hi) range. It is a child widget of the
    graphics view (not a scene item), so pan / zoom / fit never move it.
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
