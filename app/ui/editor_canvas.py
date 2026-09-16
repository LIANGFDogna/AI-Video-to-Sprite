import numpy as np
from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import QColor, QPen, QImage, QPixmap
from app.ui.video_viewer import VideoViewer


def screen_delta_to_canvas_delta(screen_delta, view_scale=1.0, display_scale=1.0, device_ratio=1.0):
    """One conversion for every alignment tool: screen pixels -> project canvas pixels.

    view_scale is the editor zoom (0.5 = 50%), display_scale the image/canvas ratio and
    device_ratio the screen DPI factor. Callers that already mapped the event through
    QGraphicsView.mapToScene pass view_scale=1 because Qt applied the zoom there.
    """
    factor = max(view_scale, 1e-9) * max(device_ratio, 1e-9) * max(display_scale, 1e-9)
    return (screen_delta[0] / factor, screen_delta[1] / factor)


class EditorCanvas(VideoViewer):
    moved = Signal(float, float)
    interaction_cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.overlays.update(axes=True, safe=True)
        self.idle_ghost_item=self.scene().addPixmap(QPixmap());self.idle_ghost_item.setZValue(-1)
        self.idle_ghost_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.ghost_pixels=None
        self.origin = None
        self.drag_start = None
        self.pan_start = None
        self.key_step_scale=(1.,1.)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setDragMode(self.DragMode.NoDrag)
        self.dragging = False

    def set_idle_ghost(self,pixels,opacity=.35):
        if pixels is not self.ghost_pixels:
            self.ghost_pixels=pixels
            if pixels is None:self.idle_ghost_item.setPixmap(QPixmap())
            else:
                data=np.ascontiguousarray(pixels);h,w=data.shape[:2]
                self.idle_ghost_item.setPixmap(QPixmap.fromImage(QImage(data.data,w,h,data.strides[0],QImage.Format.Format_RGBA8888).copy()))
        self.idle_ghost_item.setOpacity(opacity)
        self.idle_ghost_item.setPos(0,0)

    def clear_image(self):
        super().clear_image()
        self.set_idle_ghost(None)

    def set_image(self, rgba, display_scale=1.):
        self.pixmap_item.setPos(0, 0)
        super().set_image(rgba, display_scale)

    def cancel_active_interaction(self):
        "Drop every transient drag state; the single pixmap item snaps back to the origin."
        changed = self.drag_start is not None or self.pan_start is not None or self.dragging
        self.drag_start = None
        self.pan_start = None
        self.dragging = False
        self.pixmap_item.setPos(0, 0)
        if changed:
            self.viewport().update()
            self.interaction_cancelled.emit()
        return changed

    def mousePressEvent(self, event):
        self.setFocus()
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start = self.mapToScene(event.position().toPoint())
            self.dragging = True
            event.accept()
        elif event.button() == Qt.MouseButton.MiddleButton:
            self.pan_start = event.position()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drag_start is not None:
            delta = self.mapToScene(event.position().toPoint())-self.drag_start
            self.pixmap_item.setPos(delta)
            event.accept()
        elif self.pan_start is not None:
            delta = event.position()-self.pan_start
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value()-round(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value()-round(delta.y()))
            self.pan_start = event.position()
        else: super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.drag_start is not None:
            delta = self.mapToScene(event.position().toPoint())-self.drag_start
            self.drag_start = None
            self.dragging = False
            self.pixmap_item.setPos(0, 0)
            if delta.manhattanLength() > 1:
                dx, dy = screen_delta_to_canvas_delta((delta.x(), delta.y()), display_scale=self.display_scale)
                self.moved.emit(round(dx), round(dy))
            event.accept()
        self.pan_start = None

    def focusOutEvent(self, event):
        self.cancel_active_interaction()
        super().focusOutEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancel_active_interaction()
            event.accept()
            return
        directions = {Qt.Key.Key_Left: (-1,0), Qt.Key.Key_Right: (1,0), Qt.Key.Key_Up: (0,-1), Qt.Key.Key_Down: (0,1)}
        if event.key() in directions:
            x, y = directions[event.key()]
            step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
            self.moved.emit(x*step*self.key_step_scale[0], y*step*self.key_step_scale[1])
            event.accept()
        else: super().keyPressEvent(event)

    def drawForeground(self, painter, rect):
        super().drawForeground(painter, rect)
        if not self.image_size[0]: return
        w, h = self.image_size
        if self.overlays.get('axes') and not self.character_reference:
            x, y = self.origin or (w/2/self.display_scale, .9*h/self.display_scale)
            x, y = x*self.display_scale, y*self.display_scale
            painter.setPen(self.pen('#d99c72', 1))
            painter.drawLine(QPointF(0,y), QPointF(w,y))
            painter.setPen(self.pen('#86b7ef', 1))
            painter.drawLine(QPointF(x,0), QPointF(x,h))
            painter.drawEllipse(QPointF(x,y), 3,3)
        if self.overlays.get('safe'):
            pen = self.pen('#9b8db8')
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(QRectF(w*.05,h*.05,w*.9,h*.9))
