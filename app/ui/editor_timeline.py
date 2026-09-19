import json
from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QMimeData
from PySide6.QtGui import QBrush, QColor, QPen, QPainter, QPixmap, QDrag, QFont, QFontMetrics
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsRectItem, QGraphicsItem
from app.i18n import t

FRAME_MIME = 'application/x-aivsprite-frames'


class EditorTimeline(QGraphicsView):
    selection_changed = Signal(object)
    time_selected = Signal(float)
    blocks_moved = Signal(object, float, str)
    action = Signal(str)
    frame_menu_requested = Signal(int, object)
    frames_dropped = Signal(object, object, str)
    label_width = 80
    row_height = 54
    ruler_height = 28

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setMinimumHeight(195)
        # Selection uses one lightweight rectangle item; never Qt's pixmap rubber band.
        self.setDragMode(self.DragMode.NoDrag)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.pixels_per_second = 720.
        self.edit = None
        self.items_by_id = {}
        self.anchor = None
        self.play_time = 0.
        self.drag = None
        self.scrubbing = False
        self.rebuilding = False
        self.selecting = None
        self.rubber = None
        self.animation_id = ""
        self.reference_index = None
        self.frame_drag_active = False
        self.frame_drag_payload_data = None
        self.frame_drag_point = None
        self.frame_drop_target = None
        self.drop_target_widget = None
        # Block drags move items; minimal viewport updates would leave trails behind them.
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self.scene().selectionChanged.connect(self._selection)

    def ids(self):
        return [i for i, item in self.items_by_id.items() if item.isSelected()]

    def row_layout_height(self):
        "Pixel height of the track rows, used by tests and by the drop feedback."
        rows = len(self.edit.track_layout) if self.edit else 1
        return rows * self.row_height

    def set_edit(self, edit, fps, selected=None):
        self.rebuilding = True
        selected = set(self.ids() if selected is None else selected)
        self.edit, self.fps = edit, fps or 24
        self.rubber = None
        self.selecting = None
        self.scene().clear()
        self.items_by_id.clear()
        width = max(self.viewport().width()-5, (edit.duration+1)*self.pixels_per_second)
        self.scene().setSceneRect(0, 0, width, self.ruler_height+len(edit.track_layout)*self.row_height)
        for track_index, track in enumerate(edit.track_layout):
            y = self.ruler_height+track_index*self.row_height
            background = self.scene().addRect(0, y, width, self.row_height, QPen(QColor('#526277')), QBrush(QColor('#263142' if track_index%2 else '#202b39')))
            background.setZValue(-2)
            for frame in edit.frames(track.id):
                x = self.label_width+frame.start*self.pixels_per_second
                item = QGraphicsRectItem(x, y+4, max(3, frame.duration*self.pixels_per_second-1), self.row_height-8)
                item.setBrush(QBrush(QColor('#3b526c' if track.locked else '#397f75' if track.visible else '#424750')))
                item.setPen(QPen(QColor('#90b6d0'), 1))
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
                item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape)
                item.setData(0, frame.id)
                item.setToolTip(t('Source frame {frame} · {duration:.4f}s', frame=frame.source_index, duration=frame.duration))
                self.scene().addItem(item)
                self.items_by_id[frame.id] = item
                item.setSelected(frame.id in selected)
                if item.rect().width() > 15:
                    label = ('◆' if frame.keyframe else '')+str(frame.source_index)+(' ↶' if frame.reversed else '')+(' ×' if frame.speed != 1 else '')
                    text = self.scene().addSimpleText(label)
                    text.setBrush(QBrush(QColor('#f2fbff')))
                    text.setParentItem(item)
                    text.setPos(x+3, y+13)
                    text.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.rebuilding = False
        self.viewport().update()

    def _clear_selection_overlay(self):
        self.selecting = None
        self.rubber = None
        self.viewport().update()

    def _start_selection(self, position):
        "The rubber band is painted by drawForeground, so it can never be covered by a cell."
        self.selecting = position
        self.rubber = QRectF(position, position)
        self.viewport().update()

    def _update_selection(self, position):
        if self.rubber is not None and self.selecting is not None:
            self.rubber = QRectF(self.selecting, position).normalized()
            self.viewport().update()

    def _finish_selection(self, position):
        rect = QRectF(self.selecting, position).normalized() if self.selecting is not None else None
        self._clear_selection_overlay()
        if rect is None:
            return []
        ids = [ident for ident, item in self.items_by_id.items() if item.mapRectToScene(item.rect()).intersects(rect)]
        self.select_ids(ids)
        return ids

    def cancel_active_interaction(self):
        "Remove the selection overlay and any uncommitted block drag."
        if self.frame_drag_active:
            self.cancel_frame_drag()
        changed = self.selecting is not None or self.drag is not None or self.scrubbing
        if self.drag:
            self.drag = None
            for item in self.items_by_id.values():
                item.setPos(0, 0)
        self._clear_selection_overlay()
        self.scrubbing = False
        return changed

    def _selection(self):
        if not self.rebuilding:
            self.selection_changed.emit(self.ids())
            self.viewport().update()

    def select_ids(self, ids):
        ids = set(ids)
        self.rebuilding = True
        for ident, item in self.items_by_id.items(): item.setSelected(ident in ids)
        self.rebuilding = False
        self._selection()

    def set_time(self, time):
        self.play_time = time
        self.viewport().update()

    def _block(self, position):
        item = self.itemAt(position)
        while item and not item.data(0): item = item.parentItem()
        return item

    def mousePressEvent(self, event):
        self.setFocus()
        pos = self.mapToScene(event.position().toPoint())
        if pos.y() < self.ruler_height:
            self.scrubbing = True
            self.time_selected.emit(max(0., (pos.x()-self.label_width)/self.pixels_per_second))
            event.accept(); return
        item = self._block(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and item:
            ident = item.data(0)
            frame = next(f for f in self.edit.timeline_clips if f.id == ident)
            mods = event.modifiers()
            if mods & Qt.KeyboardModifier.ShiftModifier and self.anchor in self.items_by_id:
                ordered = [f.id for f in self.edit.frames(frame.track_id)]
                if self.anchor in ordered:
                    a,b = sorted((ordered.index(self.anchor), ordered.index(ident)))
                    self.select_ids(ordered[a:b+1])
                else: self.select_ids([ident])
            elif mods & Qt.KeyboardModifier.ControlModifier:
                item.setSelected(not item.isSelected())
            elif not item.isSelected(): self.select_ids([ident])
            self.anchor = ident
            self.time_selected.emit(frame.start)
            selected = self.edit.selected(self.ids(), editable=False)
            if selected and not any(t.locked and any(f.track_id == t.id for f in selected) for t in self.edit.track_layout):
                self.drag = (pos, min(f.start for f in selected), frame.track_id, False)
            event.accept()
        elif event.button() == Qt.MouseButton.LeftButton:
            self._start_selection(pos)
            event.accept()
        else: super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        pos = self.mapToScene(event.position().toPoint())
        if self.scrubbing:
            self.time_selected.emit(max(0.,(pos.x()-self.label_width)/self.pixels_per_second)); return
        if self.selecting is not None:
            self._update_selection(pos); return
        if self.drag:
            origin, start, track, moved = self.drag
            delta = pos-origin
            if delta.manhattanLength() > 5:
                self.drag = (origin,start,track,True)
                for ident in self.ids(): self.items_by_id[ident].setPos(delta.x(), delta.y())
            if self.frame_drag_active:
                self.update_frame_drag(event.globalPosition().toPoint())
                return
            if self._outside(event) and self.start_frame_drag():
                return
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.frame_drag_active:
            self.finish_frame_drag(commit=True)
            event.accept()
            return
        if self.selecting is not None:
            self._finish_selection(self.mapToScene(event.position().toPoint()))
            event.accept(); return
        if self.drag:
            origin, start, track, moved = self.drag
            self.drag = None
            if moved:
                pos = self.mapToScene(event.position().toPoint())
                at = max(0., round((start+(pos.x()-origin.x())/self.pixels_per_second)*self.fps)/self.fps)
                row = max(0,min(len(self.edit.track_layout)-1,int((pos.y()-self.ruler_height)/self.row_height)))
                self.blocks_moved.emit(self.ids(), at, self.edit.track_layout[row].id)
            else:
                for item in self.items_by_id.values(): item.setPos(0,0)
        self.scrubbing = False
        super().mouseReleaseEvent(event)

    def _outside(self, event):
        "Leaving the widget is the gesture that hands frames to the Project Library."
        return not self.viewport().rect().contains(event.position().toPoint())

    def _context_menu(self, point):
        item = self._block(point)
        if item is None or not self.edit:
            return
        ident = item.data(0)
        frame = next((f for f in self.edit.timeline_clips if f.id == ident), None)
        if frame is not None:
            self.frame_menu_requested.emit(frame.source_index, self.viewport().mapToGlobal(point))

    def frame_drag_payload(self):
        "Selected frames in Timeline order for the in-app drag controller."
        selected = self.edit.selected(self.ids(), editable=False) if self.edit else []
        if not selected:
            return None
        ordered = sorted(selected, key=lambda frame: (frame.start, frame.id))
        return {'animation_id': self.animation_id,
                'frames': [frame.source_index for frame in ordered],
                'label': t('{count} Frames', count=len(ordered))}

    def start_frame_drag(self):
        "Internal drag: no QDrag, no native drag window, no DWM drag preview."
        payload = self.frame_drag_payload()
        if payload is None:
            return False
        self.drag = None
        for item in self.items_by_id.values():
            item.setPos(0, 0)
        self.frame_drag_active = True
        self.frame_drag_payload_data = payload
        self.frame_drag_point = None
        self.frame_drop_target = None
        self.grabMouse()
        self.viewport().update()
        return True

    def update_frame_drag(self, global_point):
        "Hit-test the Project Library with the global cursor position."
        self.frame_drag_point = global_point
        tree = getattr(self, 'drop_target_widget', None)
        target = None
        if tree is not None:
            local = tree.viewport().mapFromGlobal(global_point)
            if tree.viewport().rect().contains(local):
                kind, ident, zone = tree.drop_target(local)
                if kind == 'GROUP':
                    target = ident
            tree._set_frame_target(target)
        self.frame_drop_target = target
        self.viewport().update()
        return target

    def finish_frame_drag(self, commit=True):
        "Release commits exactly one frame move; nothing native was ever shown."
        try:
            self.releaseMouse()
        except RuntimeError:
            pass
        self.frame_drag_active = False
        payload = getattr(self, 'frame_drag_payload_data', None)
        target = getattr(self, 'frame_drop_target', None)
        tree = getattr(self, 'drop_target_widget', None)
        if tree is not None:
            tree._set_frame_target(None)
        self.frame_drop_target = None
        self.frame_drag_payload_data = None
        self.frame_drag_point = None
        self.viewport().update()
        if commit and payload and target:
            self.frames_dropped.emit(payload['animation_id'], payload['frames'], target)
            return True
        return False

    def cancel_frame_drag(self):
        return self.finish_frame_drag(commit=False)

    def zoom(self, factor):
        self.pixels_per_second = max(60.,min(8000.,self.pixels_per_second*factor))
        if self.edit: self.set_edit(self.edit, self.fps)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom(1.2 if event.angleDelta().y()>0 else 1/1.2); event.accept()
        elif event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            bar=self.horizontalScrollBar();bar.setValue(bar.value()-event.angleDelta().y());event.accept()
        else: super().wheelEvent(event)

    def focusOutEvent(self, event):
        self.cancel_active_interaction()
        super().focusOutEvent(event)

    def keyPressEvent(self, event):
        key, mods = event.key(), event.modifiers()
        if key == Qt.Key.Key_Escape:
            self.cancel_active_interaction()
            event.accept(); return
        if key == Qt.Key.Key_Delete: self.action.emit('delete')
        elif mods & Qt.KeyboardModifier.ControlModifier and key in (Qt.Key.Key_A,Qt.Key.Key_C,Qt.Key.Key_V):
            self.action.emit({Qt.Key.Key_A:'select_all',Qt.Key.Key_C:'copy',Qt.Key.Key_V:'paste'}[key])
        else: super().keyPressEvent(event)

    def drawForeground(self, painter, rect):
        painter.fillRect(QRectF(rect.left(),0,rect.width(),self.ruler_height),QColor('#303e50'))
        painter.setPen(QColor('#dce8f5'))
        spacing=max(1,round(70/(self.pixels_per_second/max(1,getattr(self,'fps',24)))))
        fps=getattr(self,'fps',24)
        first=max(0,int(rect.left()/self.pixels_per_second*fps)//spacing*spacing)
        last=int(rect.right()/self.pixels_per_second*fps)+spacing
        for frame in range(first,last,spacing):
            x=self.label_width+frame/fps*self.pixels_per_second
            painter.drawLine(QPointF(x,20),QPointF(x,28))
            painter.drawText(QPointF(x+3,17),str(frame))
        if self.edit:
            for row,track in enumerate(self.edit.track_layout):
                y=self.ruler_height+row*self.row_height
                painter.fillRect(QRectF(rect.left(),y,self.label_width,self.row_height),QColor('#303e50'))
                painter.drawText(QRectF(rect.left()+4,y,self.label_width-8,self.row_height),Qt.AlignmentFlag.AlignVCenter,t(track.name))
        for ident in self.ids():
            item=self.items_by_id[ident]
            painter.setPen(QPen(QColor('#d0fff1'),2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(item.mapRectToScene(item.rect()))
        if self.rubber is not None:
            # Topmost overlay: independent of any scene item Z-order.
            painter.setPen(QPen(QColor('#8fd3ff'),1,Qt.PenStyle.DashLine))
            painter.setBrush(QBrush(QColor(143,211,255,40)))
            painter.drawRect(self.rubber)
            painter.setBrush(Qt.BrushStyle.NoBrush)
        if self.frame_drag_active and self.frame_drag_point is not None:
            label=(getattr(self,'frame_drag_payload_data',None) or {}).get('label','')
            if label:
                scene_point=self.mapToScene(self.viewport().mapFromGlobal(self.frame_drag_point))
                font=QFont();font.setPixelSize(12);painter.setFont(font)
                metrics=QFontMetrics(font)
                width=metrics.horizontalAdvance(label)+16
                box=QRectF(scene_point.x()+12,scene_point.y()-30,width,22)
                painter.setBrush(QBrush(QColor(35,44,58,220)))
                painter.setPen(QPen(QColor('#8fd3ff')))
                painter.drawRoundedRect(box,4,4)
                painter.setPen(QColor('#e8f2ff'))
                painter.drawText(box,Qt.AlignmentFlag.AlignCenter,label)
        if self.reference_index is not None and self.edit:
            marker = next((f for f in self.edit.frames() if f.source_index == self.reference_index), None)
            if marker is not None:
                mx = self.label_width+marker.start*self.pixels_per_second
                painter.setPen(QPen(QColor('#c8a2ff'),2,Qt.PenStyle.DashLine))
                painter.drawLine(QPointF(mx,self.ruler_height),QPointF(mx,self.sceneRect().height()))
                painter.setPen(QPen(QColor('#c8a2ff')))
                painter.drawText(QPointF(mx+3,self.ruler_height+13),t('Edit Reference'))
        painter.setPen(QPen(QColor('#ffca74'),2))
        x=self.label_width+self.play_time*self.pixels_per_second
        painter.drawLine(QPointF(x,0),QPointF(x,self.sceneRect().height()))
