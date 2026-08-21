from __future__ import annotations
from typing import AnyStr, List, Tuple, Dict, Union, Set, Iterable, TYPE_CHECKING

if TYPE_CHECKING:
    pass

from PyQt5 import QtGui, QtCore, QtWidgets
from .Point import Point
from utils import Print


class GenericGraphicsView(QtWidgets.QGraphicsView):

    sigDeviceRangeChanged = QtCore.pyqtSignal(QtCore.QObject, QtCore.QRectF)
    sigDeviceTransformChanged = QtCore.pyqtSignal(QtWidgets.QGraphicsView)
    sigMouseReleased = QtCore.pyqtSignal(QtGui.QMouseEvent)
    sigSceneMouseMoved = QtCore.pyqtSignal(QtCore.QPointF)
    sigSelectPos = QtCore.pyqtSignal(QtCore.QPoint)
    sigSelectArea = QtCore.pyqtSignal(QtCore.QRect)
    sigScaleChanged = QtCore.pyqtSignal(QtCore.QObject)
    lastFileDir = None

    def __init__(self, parent=None):
        super(GenericGraphicsView, self).__init__(parent=parent)
        self.closed = False
        self.setCacheMode(self.CacheBackground)

        self.setBackgroundRole(QtGui.QPalette.NoRole)

        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.NoAnchor)
        self.setResizeAnchor(QtWidgets.QGraphicsView.AnchorViewCenter)
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.MinimalViewportUpdate)

        self.lockedViewports = []
        self.fit_key = None
        self.lastMousePos = None
        self.mousePressPos = None
        self.mouseReleasePos = None
        self.zoomBoxLastPos = None
        self.scaleCenter = None

        self.setDragMode(QtWidgets.QGraphicsView.NoDrag)
        self.setMouseTracking(True)
        self.range = QtCore.QRectF(0, 0, 100 ,100)
        self.clearMouse()
        self.updateMatrix()
        self.setBackgroundBrush(QtGui.QColor(0, 0, 0, 255))
        self.sceneObj = QtWidgets.QGraphicsScene(self)
        self.setScene(self.sceneObj)
        self.boundingRect = QtCore.QRectF(0.0, 0.0, 1.0, 1.0)

    def flipY(self):
        self.setTransform(self.transform().scale(1, -1))

    def setAntialiasing(self, aa):
        if aa:
            self.setRenderHints(self.renderHints() | QtGui.QPainter.Antialiasing)
        else:
            self.setRenderHints(self.renderHints() & ~QtGui.QPainter.Antialiasing)

    def render(self, *args, **kwds):
        self.scene().prepareForPaint()
        return super().render(*args, **kwds)

    def close(self):
        self.scene().clear()
        self.sceneObj = None
        self.closed = True
        self.setViewport(None)
        super(GenericGraphicsView, self).close()

    def enableFitKet(self, key=QtCore.Qt.Key_F):
        self.fit_key = key

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if self.fit_key is not None and event.key() == self.fit_key:
            self.fit()
        self.scene().keyPressEvent(event)

    def updateBoundingRect(self, rect=None):
        if rect is None:
            self.boundingRect = self.scene().itemsBoundingRect()
        elif type(rect) == QtCore.QRectF:
            self.boundingRect = rect
        else:
            Print(f'Invalid rect({rect}) input for updateBoundingRect function of genericView')

    def fit(self):
        self.setRange(self.boundingRect)
        self.updateMatrix()

    def clearMouse(self):
        self.mouseTrail = []
        self.lastButtonReleased = None

    def resizeEvent(self, ev: QtGui.QKeyEvent) -> None:
        if self.closed:
            return
        GenericGraphicsView.setRange(self, self.range, padding=0)
        self.updateMatrix()

    def updateMatrix(self):
        self.setSceneRect(self.range)
        self.fitInView(self.range, QtCore.Qt.KeepAspectRatio)

        self.sigDeviceRangeChanged.emit(self, self.range)
        self.sigDeviceTransformChanged.emit(self)

    def viewRect(self):
        r = QtCore.QRectF(self.rect())
        return self.viewportTransform().inverted()[0].mapRect(r)

    def visibleRange(self):
        return self.viewRect()

    def translate(self, dx: float, dy: float) -> None:
        self.range.adjust(dx, dy, dx, dy)
        self.updateMatrix()

    def scale(self, sx: float, sy: float, center=None):
        scale = [sx, sy]
        scale[0] = scale[1]

        if self.scaleCenter:
            center = None
        if center is None:
            center = self.range.center()

        w = self.range.width() / scale[0]
        h = self.range.height() / scale[1]
        self.range = QtCore.QRectF(center.x() - (center.x() - self.range.left()) / scale[0], center.y() - (center.y() - self.range.top()) / scale[1], w, h)

        self.updateMatrix()
        self.sigScaleChanged.emit(self)

    def setRange(self, newRect=None, padding=0.05):
        if newRect is None:
            newRect = self.visibleRange()
            padding = 0

        padding = Point(padding)
        newRect = QtCore.QRectF(newRect)
        pw = newRect.width() * padding[0]
        ph = newRect.height() * padding[1]
        newRect = newRect.adjusted(-pw, -ph, pw, ph)
        scaleChanged = False
        if self.range.width() != newRect.width() or self.range.height() != newRect.height():
            scaleChanged = True
        self.range = newRect
        self.updateMatrix()
        if scaleChanged:
            self.sigScaleChanged.emit(self)

    def scaleToImage(self, image):
        pxSize = image.pixelSize()
        image.setPxMode(True)
        try:
            self.sigScaleChanged.disconncet(image.setScaleMode)
        except (TypeError, RuntimeError):
            pass
        tl = image.sceneBoundingRect().topLeft()
        w = self.size().width() * pxSize[0]
        h = self.size().height() * pxSize[1]
        range = QtCore.QRectF(tl.x(), tl.y(), w, h)
        GenericGraphicsView.setRange(self, range, padding=0)
        self.sigScaleChanged.connect(image.setScaleMode)

    def lockXRange(self, v1):
        if not v1 in self.lockedViewports:
            self.lockedViewports.append(v1)

    def setXRange(self, r, padding=0.05):
        r1 = QtCore.QRectF(self.range)
        r1.setLeft(r.left())
        r1.setRight(r.right())
        GenericGraphicsView.setRange(self, r1, padding=[padding, 0])

    def setYRange(self, r, padding=0.05):
        r1 = QtCore.QRectF(self.range)
        r1.setTop(r.top())
        r1.setBottom(r.bottom())
        GenericGraphicsView.setRange(self, r1, padding=[0, padding])

    def wheelEvent(self, ev: QtGui.QWheelEvent) -> None:
        super().wheelEvent(ev)

        delta = ev.angleDelta().x()
        if delta == 0:
            delta = ev.angleDelta().y()

        sc = 1.001 ** delta
        self.scale(sc, sc)

    def mousePressEvent(self, ev: QtGui.QMouseEvent) -> None:
        super().mousePressEvent(ev)

        lpos = ev.localPos()
        self.lastMousePos = lpos
        self.mousePressPos = ev.pos()
        self.clickAccepted = ev.isAccepted()
        if not self.clickAccepted:
            self.scene().clearSelection()
        if ev.buttons() == QtCore.Qt.RightButton:
            self.zoomBoxLastPos = self.mapToScene(ev.pos())
        return

    def mouseReleaseEvent(self, ev: QtGui.QMouseEvent):

        self.sigMouseReleased.emit(ev)
        self.lastButtonReleased = ev.button()

        if ev.button() == QtCore.Qt.RightButton and self.zoomBoxLastPos is not None:
            zoomBoxCurrentPos = self.mapToScene(ev.pos())
            x0 = zoomBoxCurrentPos.x()
            y0 = zoomBoxCurrentPos.y()
            x1 = self.zoomBoxLastPos.x()
            y1 = self.zoomBoxLastPos.y()
            scene_rect = QtCore.QRectF(min(x0, x1), min(y0, y1), abs(x0 - x1), abs(y0 - y1))
        elif ev.button() == QtCore.Qt.LeftButton:
            cur_pos = ev.pos()
            x0 = cur_pos.x()
            y0 = cur_pos.y()
            self.mouseReleasePos = ev.pos()
            x1 = self.mouseReleasePos.x()
            y1 = self.mouseReleasePos.y()

            width = abs(x0 - x1)
            height = abs(y0 - y1)
            if width > 3 and height > 3:
                aleft = min(x0, x1)
                atop = min(y0, y1)
                self.sigSelectArea.emit(QtCore.QRect(aleft, atop, width, height))
            else:
                self.sigSelectPos.emit(self.mousePressPos)

        super().mouseReleaseEvent(ev)
        return

    def mouseMoveEvent(self, ev: QtGui.QMouseEvent) -> None:
            lpos = ev.pos()
            if self.lastMousePos is None:
                self.lastMousePos = lpos
            delta = Point(lpos - self.lastMousePos)
            self.lastMousePos = lpos

            super().mouseMoveEvent(ev)

            self.sigSceneMouseMoved.emit(self.mapToScene(lpos))

            if ev.buttons() in [QtCore.Qt.MiddleButton]:
                px = self.pixelSize()
                tr = -delta * px

                self.translate(tr[0], tr[1])
                self.sigDeviceRangeChanged.emit(self, self.range)

    def pixelSize(self):
        p0 = Point(0, 0)
        p1 = Point(1, 1)
        tr = self.transform().inverted()[0]
        p01 = tr.map(p0)
        p11 = tr.map(p1)
        return Point(p11 - p01)

    def dragEnterEvent(self, ev):
        ev.ignore()













