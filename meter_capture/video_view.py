"""Graphics view for the video frame plus a draggable/resizable ROI."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
)


class RoiItem(QGraphicsRectItem):
    """Movable + resizable ROI rectangle drawn in scene (frame) coordinates."""

    HANDLE = 10  # pixel size of corner handles in scene coords

    def __init__(self, rect: QRectF) -> None:
        super().__init__(rect)
        self.setPen(QPen(QColor("#ff3b30"), 2))
        self.setBrush(QBrush(QColor(255, 59, 48, 35)))
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self._active_handle: str | None = None
        self._press_pos: QPointF | None = None
        self._press_rect: QRectF | None = None
        self.setSelected(True)

    def _handle_rects(self) -> dict[str, QRectF]:
        r = self.rect()
        s = self.HANDLE
        return {
            "tl": QRectF(r.left() - s / 2, r.top() - s / 2, s, s),
            "tr": QRectF(r.right() - s / 2, r.top() - s / 2, s, s),
            "bl": QRectF(r.left() - s / 2, r.bottom() - s / 2, s, s),
            "br": QRectF(r.right() - s / 2, r.bottom() - s / 2, s, s),
            "t": QRectF(r.center().x() - s / 2, r.top() - s / 2, s, s),
            "b": QRectF(r.center().x() - s / 2, r.bottom() - s / 2, s, s),
            "l": QRectF(r.left() - s / 2, r.center().y() - s / 2, s, s),
            "r": QRectF(r.right() - s / 2, r.center().y() - s / 2, s, s),
        }

    def boundingRect(self) -> QRectF:
        return super().boundingRect().adjusted(-self.HANDLE, -self.HANDLE, self.HANDLE, self.HANDLE)

    def paint(self, painter, option, widget=None) -> None:  # noqa: D401
        super().paint(painter, option, widget)
        if self.isSelected():
            painter.setPen(QPen(QColor("#ff3b30"), 1))
            painter.setBrush(QBrush(Qt.white))
            for h in self._handle_rects().values():
                painter.drawRect(h)

    def hoverMoveEvent(self, event) -> None:
        cursor_map = {
            "tl": Qt.SizeFDiagCursor,
            "br": Qt.SizeFDiagCursor,
            "tr": Qt.SizeBDiagCursor,
            "bl": Qt.SizeBDiagCursor,
            "t": Qt.SizeVerCursor,
            "b": Qt.SizeVerCursor,
            "l": Qt.SizeHorCursor,
            "r": Qt.SizeHorCursor,
        }
        for k, h in self._handle_rects().items():
            if h.contains(event.pos()):
                self.setCursor(cursor_map[k])
                return
        self.setCursor(Qt.SizeAllCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            for k, h in self._handle_rects().items():
                if h.contains(event.pos()):
                    self._active_handle = k
                    self._press_pos = event.pos()
                    self._press_rect = QRectF(self.rect())
                    event.accept()
                    return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._active_handle is not None and self._press_pos and self._press_rect:
            dx = event.pos().x() - self._press_pos.x()
            dy = event.pos().y() - self._press_pos.y()
            r = QRectF(self._press_rect)
            k = self._active_handle
            if "l" in k:
                r.setLeft(r.left() + dx)
            if "r" in k:
                r.setRight(r.right() + dx)
            if "t" in k:
                r.setTop(r.top() + dy)
            if "b" in k:
                r.setBottom(r.bottom() + dy)
            r = r.normalized()
            min_size = 6.0
            if r.width() < min_size:
                r.setWidth(min_size)
            if r.height() < min_size:
                r.setHeight(min_size)
            self.prepareGeometryChange()
            self.setRect(r)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._active_handle = None
        self._press_pos = None
        self._press_rect = None
        super().mouseReleaseEvent(event)

    def frame_rect(self) -> QRectF:
        """Return ROI in frame (scene) coordinates."""
        return self.mapRectToScene(self.rect())


class VideoView(QGraphicsView):
    """Displays current video frame and lets the user draw / edit a ROI."""

    roi_changed = Signal(QRectF)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHints(self.renderHints())
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setBackgroundBrush(QBrush(QColor("#1d1d1f")))
        self.setMouseTracking(True)

        self._pixmap_item = QGraphicsPixmapItem()
        self._pixmap_item.setShapeMode(QGraphicsPixmapItem.BoundingRectShape)
        self._scene.addItem(self._pixmap_item)

        self._roi: RoiItem | None = None
        self._draw_mode = False
        self._draw_origin: QPointF | None = None
        self._draw_temp: QGraphicsRectItem | None = None
        self._frame_size = (0, 0)  # (w, h)

    # ------------------------------------------------------------- frame I/O
    def set_frame_bgr(self, frame_bgr) -> None:
        if frame_bgr is None:
            return
        h, w = frame_bgr.shape[:2]
        # BGR -> RGB without copying twice
        rgb = frame_bgr[..., ::-1].copy()
        img = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888)
        pix = QPixmap.fromImage(img)
        self._pixmap_item.setPixmap(pix)
        if (w, h) != self._frame_size:
            self._scene.setSceneRect(QRectF(0, 0, w, h))
            self._frame_size = (w, h)
            self.fitInView(self._pixmap_item, Qt.KeepAspectRatio)

    def fit(self) -> None:
        if self._frame_size != (0, 0):
            self.fitInView(self._pixmap_item, Qt.KeepAspectRatio)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.fit()

    # ------------------------------------------------------------- ROI mgmt
    def set_draw_mode(self, on: bool) -> None:
        self._draw_mode = on
        self.setCursor(Qt.CrossCursor if on else Qt.ArrowCursor)

    def clear_roi(self) -> None:
        if self._roi is not None:
            self._scene.removeItem(self._roi)
            self._roi = None
            self.roi_changed.emit(QRectF())

    def get_roi_rect(self) -> QRectF:
        if self._roi is None:
            return QRectF()
        r = self._roi.frame_rect()
        # clamp to frame
        fw, fh = self._frame_size
        x1 = max(0.0, r.left())
        y1 = max(0.0, r.top())
        x2 = min(float(fw), r.right())
        y2 = min(float(fh), r.bottom())
        return QRectF(x1, y1, x2 - x1, y2 - y1).normalized()

    # ------------------------------------------------------------- mouse events
    def mousePressEvent(self, event) -> None:
        if self._draw_mode and event.button() == Qt.LeftButton and self._frame_size != (0, 0):
            self._draw_origin = self.mapToScene(event.pos())
            self.clear_roi()
            self._draw_temp = QGraphicsRectItem(QRectF(self._draw_origin, self._draw_origin))
            self._draw_temp.setPen(QPen(QColor("#ff3b30"), 2, Qt.DashLine))
            self._draw_temp.setBrush(QBrush(QColor(255, 59, 48, 25)))
            self._scene.addItem(self._draw_temp)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._draw_mode and self._draw_origin is not None and self._draw_temp is not None:
            cur = self.mapToScene(event.pos())
            r = QRectF(self._draw_origin, cur).normalized()
            self._draw_temp.setRect(r)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._draw_mode and self._draw_origin is not None and self._draw_temp is not None:
            r = self._draw_temp.rect()
            self._scene.removeItem(self._draw_temp)
            self._draw_temp = None
            self._draw_origin = None
            self.set_draw_mode(False)
            if r.width() >= 6 and r.height() >= 6:
                self._roi = RoiItem(r)
                self._scene.addItem(self._roi)
                self.roi_changed.emit(r)
            event.accept()
            return
        super().mouseReleaseEvent(event)
