import numpy as np
from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import QColor, QPen, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QGraphicsItem, QGraphicsView


class ImageItem(QGraphicsItem):
    """One QImage drawn straight into the scene so a stroke can repaint a dirty rect only."""

    def __init__(self,parent=None):
        super().__init__(parent)
        self._image=QImage()
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def image(self):
        return self._image

    def set_image(self,image):
        self.prepareGeometryChange()
        self._image=image
        self.update()

    def boundingRect(self):
        return QRectF(0,0,self._image.width(),self._image.height())

    def paint(self,painter,option,widget=None):
        if not self._image.isNull():painter.drawImage(0,0,self._image)
from app.models.pixel_edit import DEFAULT_BRUSH_SIZE
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
    stroke_started = Signal(float, float)
    stroke_moved = Signal(float, float)
    stroke_finished = Signal()
    stroke_cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.overlays.update(axes=True, safe=True)
        self.idle_ghost_item=self.scene().addPixmap(QPixmap());self.idle_ghost_item.setZValue(-1)
        self.idle_ghost_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.idle_ghost_item.setCacheMode(QGraphicsItem.CacheMode.NoCache)
        # Live stroke preview and the lightweight drag preview share one slot above the frame.
        self.stroke_item=ImageItem();self.stroke_item.setZValue(.5);self.stroke_item.setVisible(False)
        self.scene().addItem(self.stroke_item)
        self.drag_item=self.scene().addPixmap(QPixmap());self.drag_item.setZValue(.5)
        self.drag_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton);self.drag_item.setVisible(False)
        # Frame Reference Overlay: above the Character Ghost, below the editable frame.
        self.frame_reference_item=self.scene().addPixmap(QPixmap());self.frame_reference_item.setZValue(-.5)
        self.frame_reference_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.frame_reference_item.setCacheMode(QGraphicsItem.CacheMode.NoCache)
        self.pixmap_item.setCacheMode(QGraphicsItem.CacheMode.NoCache)
        # A moving item must clear its whole old rect; minimal updates leave trails.
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
        self.ghost_pixels=None
        self.reference_pixels=None
        self.origin = None
        self.drag_start = None
        self.pan_start = None
        self.key_step_scale=(1.,1.)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setDragMode(self.DragMode.NoDrag)
        self.dragging = False
        self.tool = 'move'
        self.stroke_active = False
        self.brush_size = DEFAULT_BRUSH_SIZE
        self.hover_point = None

    def set_idle_ghost(self,pixels,opacity=.35):
        if pixels is not self.ghost_pixels:
            self.ghost_pixels=pixels
            if pixels is None:self.idle_ghost_item.setPixmap(QPixmap())
            else:
                data=np.ascontiguousarray(pixels);h,w=data.shape[:2]
                self.idle_ghost_item.setPixmap(QPixmap.fromImage(QImage(data.data,w,h,data.strides[0],QImage.Format.Format_RGBA8888).copy()))
        self.idle_ghost_item.setOpacity(opacity)
        self.idle_ghost_item.setPos(0,0)
        self.idle_ghost_item.setVisible(pixels is not None and opacity > 0)

    def set_frame_reference(self,pixels,opacity=.15,visible=True):
        "Editor-only overlay; it is never part of the final pixels."
        if pixels is not self.reference_pixels:
            self.reference_pixels=pixels
            if pixels is None:self.frame_reference_item.setPixmap(QPixmap())
            else:
                data=np.ascontiguousarray(pixels);h,w=data.shape[:2]
                self.frame_reference_item.setPixmap(QPixmap.fromImage(QImage(data.data,w,h,data.strides[0],QImage.Format.Format_RGBA8888).copy()))
        self.frame_reference_item.setOpacity(opacity)
        self.frame_reference_item.setPos(0,0)
        self.frame_reference_item.setVisible(pixels is not None and visible and opacity > 0)

    def set_tool(self,tool):
        "One canvas, three tools: Select / Move, Pencil and Eraser."
        self.tool = tool if tool in ('move','pencil','eraser') else 'move'
        self.hover_point = None
        self.viewport().setCursor(Qt.CursorShape.CrossCursor if self.tool != 'move' else Qt.CursorShape.OpenHandCursor)
        self.viewport().update()

    def image_point(self,position):
        "Screen position -> image pixel; Qt already applied zoom, fit and screen DPI."
        point = self.mapToScene(position.toPoint())
        scale = self.display_scale or 1.
        return (point.x()/scale, point.y()/scale)

    def _repaint_item(self,previous):
        self.scene().invalidate(previous)
        self.scene().invalidate(self.pixmap_item.sceneBoundingRect())
        self.viewport().update()

    def begin_stroke_preview(self,image):
        "One in-memory working buffer; mouse moves never touch the pipeline."
        self.stroke_item.set_image(image)
        self.stroke_item.setVisible(True)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)

    def update_stroke_preview(self,rect):
        "Partial repaint: only the brush's dirty rect leaves the item."
        if rect is None:return
        self.stroke_item.update(QRectF(float(rect[0]),float(rect[1]),float(rect[2]),float(rect[3])))

    def end_stroke_preview(self):
        self.stroke_item.setVisible(False)
        self.viewport().update()

    def clear_image(self):
        super().clear_image()
        self.set_idle_ghost(None)
        self.set_frame_reference(None,0,False)

    def set_image(self, rgba, display_scale=1.):
        self.pixmap_item.setPos(0, 0)
        super().set_image(rgba, display_scale)

    def cancel_active_interaction(self):
        "Drop every transient drag state; the single pixmap item snaps back to the origin."
        changed = self.drag_start is not None or self.pan_start is not None or self.dragging or self.stroke_active
        self.drag_start = None
        self.pan_start = None
        self.dragging = False
        try:
            self.drag_item.setVisible(False)
            self.drag_item.setPos(0, 0)
            self.pixmap_item.setVisible(True)
            self.pixmap_item.setPos(0, 0)
            self.stroke_item.setVisible(False)
        except RuntimeError:
            return False  # Qt may already have deleted the scene items during shutdown.
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
        if self.stroke_active:
            self.stroke_active = False
            self.stroke_cancelled.emit()
        if changed:
            self.scene().invalidate(self.scene().sceneRect())
            self.viewport().update()
            self.interaction_cancelled.emit()
        return changed

    def mousePressEvent(self, event):
        self.setFocus()
        if event.button() == Qt.MouseButton.LeftButton and self.tool in ('pencil','eraser'):
            self.stroke_active = True
            x, y = self.image_point(event.position())
            self.stroke_started.emit(x, y)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start = self.mapToScene(event.position().toPoint())
            self.dragging = True
            # The frame pixmap itself never moves: a lightweight preview follows the cursor.
            self.drag_item.setPixmap(self.pixmap_item.pixmap())
            self.drag_item.setPos(self.pixmap_item.pos())
            self.drag_item.setVisible(True)
            self.pixmap_item.setVisible(False)
            # While an item is being dragged the whole viewport is repainted.
            self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
            event.accept()
        elif event.button() == Qt.MouseButton.MiddleButton:
            self.pan_start = event.position()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.stroke_active:
            x, y = self.image_point(event.position())
            self.hover_point = self.mapToScene(event.position().toPoint())
            self.stroke_moved.emit(x, y)
            event.accept()
            return
        if self.drag_start is not None:
            delta = self.mapToScene(event.position().toPoint())-self.drag_start
            previous = self.drag_item.sceneBoundingRect()
            self.drag_item.setPos(delta)
            self.scene().invalidate(previous)
            self.scene().invalidate(self.drag_item.sceneBoundingRect())
            self.viewport().update()
            event.accept()
        elif self.pan_start is not None:
            delta = event.position()-self.pan_start
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value()-round(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value()-round(delta.y()))
            self.pan_start = event.position()
        else:
            if self.tool in ('pencil','eraser'):
                self.hover_point = self.mapToScene(event.position().toPoint())
                self.viewport().update()
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.stroke_active and event.button() == Qt.MouseButton.LeftButton:
            self.stroke_active = False
            self.stroke_finished.emit()
            event.accept()
            return
        if self.drag_start is not None:
            delta = self.mapToScene(event.position().toPoint())-self.drag_start
            self.drag_start = None
            self.dragging = False
            previous = self.drag_item.sceneBoundingRect()
            self.drag_item.setVisible(False)
            self.drag_item.setPos(0, 0)
            self.pixmap_item.setVisible(True)
            self.pixmap_item.setPos(0, 0)
            self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
            self.scene().invalidate(previous)
            self.scene().invalidate(self.pixmap_item.sceneBoundingRect())
            # update() alone can leave stale pixels behind on Windows; repaint once on release.
            self.viewport().repaint()
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
        if self.tool in ('pencil','eraser') and self.hover_point is not None:
            radius = max(1., self.brush_size/2.)*self.display_scale
            painter.setPen(self.pen('#ffffff' if self.tool=='pencil' else '#ff9d9d', 1))
            painter.drawEllipse(self.hover_point, radius, radius)
