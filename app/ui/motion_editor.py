import numpy as np
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QLabel, QVBoxLayout, QWidget
from app.i18n import t


class TrajectoryView(QGraphicsView):
    frame_selected = Signal(int)

    def __init__(self, axis, parent=None):
        super().__init__(parent)
        self.axis = axis
        self.count = 0
        self.marker = None
        self.setScene(QGraphicsScene(self))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setMinimumHeight(160)
        self.setBackgroundBrush(QColor("#121b28"))
        self._press = None

    def set_frames(self, frames):
        self.scene().clear()
        self.marker = None
        self.count = len(frames)
        if not frames:
            self.scene().addText(t("Build sprites to inspect motion curves.")).setDefaultTextColor(QColor("#bdcadc"))
            return
        curves = [[(getattr(f, key) or f.root)[self.axis] for f in frames] for key in ("raw_root", "filtered_root", "target_root")]
        low, high = min(map(min, curves)), max(map(max, curves))
        factor = 220/max(20, high-low)
        width = max(240, (len(frames)-1)*12)
        self.x_step = width/max(1, len(frames)-1)
        for values, color in zip(curves, ("#ef7d91", "#e4bf64", "#70d4aa")):
            path = QPainterPath()
            path.moveTo(0, 250-(values[0]-low)*factor)
            for i, value in enumerate(values[1:], 1):
                path.lineTo(i*self.x_step, 250-(value-low)*factor)
            pen = QPen(QColor(color), 2)
            pen.setCosmetic(True)
            self.scene().addPath(path, pen)
        for i in range(0, self.count, max(1, self.count//10)):
            label = self.scene().addText(str(i))
            label.setDefaultTextColor(QColor("#91a1b8"))
            label.setPos(i*self.x_step, 280)
        self.scene().setSceneRect(-10, -10, width+35, 320)
        pen = QPen(QColor("#dce6f4"), 1)
        pen.setCosmetic(True)
        self.marker = self.scene().addLine(0, 0, 0, 280, pen)
        self.fit_image()

    def select_frame(self, index):
        if self.marker:
            x = index*self.x_step
            self.marker.setLine(x, 0, x, 280)

    def fit_image(self):
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.IgnoreAspectRatio)

    def actual_size(self):
        self.resetTransform()

    def wheelEvent(self, event):
        factor = 1.2 if event.angleDelta().y() > 0 else 1/1.2
        self.scale(factor, factor)
        event.accept()

    def mousePressEvent(self, event):
        self._press = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self.count and self._press is not None and (event.position().toPoint()-self._press).manhattanLength() < 5:
            p = self.mapToScene(event.position().toPoint())
            self.frame_selected.emit(min(self.count-1, max(0, round(p.x()/self.x_step))))
        super().mouseReleaseEvent(event)


class MotionEditor(QWidget):
    frame_selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        legend = QLabel(t("RAW · red    FILTERED · yellow    TARGET · green"))
        legend.setWordWrap(True)
        layout.addWidget(legend)
        self.curves = []
        for axis, title in enumerate(("Root X Curve", "Root Y Curve")):
            layout.addWidget(QLabel(t(title)))
            view = TrajectoryView(axis)
            view.frame_selected.connect(self.frame_selected)
            layout.addWidget(view, 1)
            self.curves.append(view)
        self.info = QLabel(t("Curves use source pixels. Click a curve to select a frame; wheel to zoom and drag to pan."))
        self.info.setWordWrap(True)
        layout.addWidget(self.info)
        self.frames = []

    def set_frames(self, frames):
        self.frames = frames
        for view in self.curves:
            view.set_frames(frames)

    def select_frame(self, index):
        for view in self.curves:
            view.select_frame(index)
        if index < len(self.frames):
            f = self.frames[index]
            self.info.setText(t("Frame {index} · Velocity {x:.2f}, {y:.2f} px/s · Confidence {confidence:.0%}\n{warnings}",
                index=index, x=f.velocity[0], y=f.velocity[1], confidence=f.tracking_confidence,
                warnings=" · ".join(t(w) for w in f.warnings)))

    def fit_image(self):
        for view in self.curves: view.fit_image()

    def actual_size(self):
        for view in self.curves: view.actual_size()
