from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPainterPath, QPen, QPixmap, QFont
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView
from app.ui.character_overlay import draw_character_space
from app.ui.reference_overlay import draw_reference


class VideoViewer(QGraphicsView):
    image_clicked = Signal(float, float)
    zoom_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.pixmap_item = self.scene().addPixmap(QPixmap())
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setMinimumSize(320, 220)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.display_scale = 1.0
        self.image_size = (0, 0)
        self.frame = None
        self.character_profile = None
        self.character_reference = None
        self.reference_mapping = (1.,1.,0.,0.)
        self.root_visible = True
        self.root_path = []
        self.root_paths = {}
        self.roi_rect = None
        self.ground = None
        self.overlays = {"root": True, "bounds": True, "features": False, "path": False,
                         "ground": True, "canvas": True, "grid": True, "numbers": True,
                         "raw_path": False, "filtered_path": False, "target_path": False}
        self.interaction = None
        self.checkerboard = True
        self._auto_fit = True
        self._setup_background()

    def _setup_background(self):
        tile = QPixmap(24, 24)
        tile.fill(QColor("#242c38"))
        painter = QPainter(tile)
        painter.fillRect(0, 0, 12, 12, QColor("#303a49"))
        painter.fillRect(12, 12, 12, 12, QColor("#303a49"))
        painter.end()
        self.checker_brush = QBrush(tile)
        self.setBackgroundBrush(self.checker_brush)

    def set_background(self, checkerboard=True):
        self.checkerboard = checkerboard
        self.setBackgroundBrush(self.checker_brush if checkerboard else QBrush(QColor("#111722")))

    def set_image(self, rgba: np.ndarray, display_scale=1.0):
        pixels = np.ascontiguousarray(rgba)
        h, w = pixels.shape[:2]
        size_changed = self.image_size != (w, h)
        self.image_size = (w, h)
        self.display_scale = display_scale
        image = QImage(pixels.data, w, h, pixels.strides[0], QImage.Format.Format_RGBA8888).copy()
        self.pixmap_item.setPixmap(QPixmap.fromImage(image))
        self.scene().setSceneRect(QRectF(0, 0, w, h))
        if size_changed or self._auto_fit:
            self.fit_image()
        self.viewport().update()

    def clear_image(self):
        self.pixmap_item.setPixmap(QPixmap())
        self.image_size = (0, 0)
        self.frame = None
        self.character_profile = None
        self.character_reference = None
        self.reference_mapping = (1.,1.,0.,0.)
        self.root_path = []
        self.root_paths = {}
        self.roi_rect = None
        self.viewport().update()

    def fit_image(self):
        if self.image_size[0]:
            self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            self._auto_fit = True
            self.zoom_changed.emit(self.transform().m11() * self.display_scale)

    def actual_size(self):
        self.resetTransform()
        self.scale(1 / self.display_scale, 1 / self.display_scale)
        self._auto_fit = False
        self.zoom_changed.emit(1.0)

    def wheelEvent(self, event):
        factor = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
        value = self.transform().m11() * self.display_scale * factor
        if 0.005 <= value <= 64:
            self.scale(factor, factor)
            self._auto_fit = False
            self.zoom_changed.emit(value)
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._auto_fit:
            self.fit_image()

    def set_interaction(self, mode):
        self.interaction = mode
        self.setDragMode(QGraphicsView.DragMode.NoDrag if mode else QGraphicsView.DragMode.ScrollHandDrag)
        self.viewport().setCursor(Qt.CursorShape.CrossCursor if mode else Qt.CursorShape.OpenHandCursor)

    def mousePressEvent(self, event):
        if self.interaction and event.button() == Qt.MouseButton.LeftButton:
            p = self.mapToScene(event.position().toPoint())
            if self.sceneRect().contains(p):
                self.image_clicked.emit(p.x() / self.display_scale, p.y() / self.display_scale)
            event.accept()
        else:
            super().mousePressEvent(event)

    @staticmethod
    def pen(color, width=1):
        pen = QPen(QColor(color), width)
        pen.setCosmetic(True)
        return pen

    def drawForeground(self, painter, rect):
        if not self.image_size[0]:
            return
        s = self.display_scale
        if self.overlays["canvas"]:
            painter.setPen(self.pen("#63738d"))
            painter.drawRect(self.sceneRect())
        if self.overlays["ground"] and self.ground is not None:
            painter.setPen(self.pen("#e9b65d", 2))
            y = self.ground * s
            painter.drawLine(QPointF(0, y), QPointF(self.image_size[0], y))
        if self.overlays["path"] and self.root_path:
            painter.setPen(self.pen("#af8bfd", 2))
            path = QPainterPath()
            path.moveTo(QPointF(self.root_path[0][0] * s, self.root_path[0][1] * s))
            for x, y in self.root_path[1:]:
                path.lineTo(QPointF(x * s, y * s))
            painter.drawPath(path)
        for key, color in (("raw_path", "#ef7d91"), ("filtered_path", "#e4bf64"), ("target_path", "#70d4aa")):
            points = self.root_paths.get(key, [])
            if self.overlays.get(key) and points:
                painter.setPen(self.pen(color, 2))
                path = QPainterPath(QPointF(points[0][0]*s, points[0][1]*s))
                for x, y in points[1:]: path.lineTo(x*s, y*s)
                painter.drawPath(path)
        if self.roi_rect:
            l, top, r, b = self.roi_rect
            painter.setPen(self.pen("#78bafa", 2))
            painter.drawRect(QRectF(l*s, top*s, (r-l)*s, (b-top)*s))
        if self.character_reference and self.overlays.get('reference',True):
            draw_reference(painter,self,self.character_reference,self.reference_mapping,
                self.overlays.get('reference_ground',True),self.overlays.get('reference_axes',True))
        f = self.frame
        if f is None:
            return
        if self.overlays["numbers"]:
            zoom = max(self.transform().m11(), .001)
            font = QFont()
            font.setPixelSize(max(1, round(14/zoom)))
            painter.setFont(font)
            painter.setPen(self.pen("#ffffff"))
            painter.drawText(QPointF(8/zoom, 20/zoom), str(f.index))
        if self.overlays["bounds"] and f.bbox:
            l, t, r, b = f.bbox
            painter.setPen(self.pen("#5ad6c5", 1))
            painter.drawRect(QRectF(l*s, t*s, (r-l)*s, (b-t)*s))
        if self.overlays["features"]:
            painter.setPen(self.pen("#f3d979", 3))
            for x, y in f.features:
                painter.drawPoint(QPointF(x*s, y*s))
        if self.overlays["root"] and self.root_visible:
            self.draw_root(painter, f.root[0] * s, f.root[1] * s, "#ffcb6b" if f.manual else "#f47b93")
        if self.character_profile:
            draw_character_space(painter, self.character_profile, s, self.transform().m11())

    def draw_root(self, painter, x, y, color):
        radius = 9 / max(self.transform().m11(), 0.001)
        painter.setPen(self.pen("#101722", 4))
        painter.drawLine(QPointF(x-radius, y), QPointF(x+radius, y))
        painter.drawLine(QPointF(x, y-radius), QPointF(x, y+radius))
        painter.setPen(self.pen(color, 2))
        painter.drawLine(QPointF(x-radius, y), QPointF(x+radius, y))
        painter.drawLine(QPointF(x, y-radius), QPointF(x, y+radius))
