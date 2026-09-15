"""Explicit axis calibration. The keyed Idle pixels remain stationary."""
from dataclasses import replace
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QDoubleSpinBox, QFormLayout
from app.ui.video_viewer import VideoViewer
from app.ui.reference_overlay import draw_reference
from app.i18n import t
from app.utils.rgba_image import to_rgba8


class ReferenceCalibrationView(VideoViewer):
    reference_changed=Signal(object)

    def __init__(self,reference,pixels,parent=None):
        super().__init__(parent)
        self.reference=reference
        self.original_pixels=to_rgba8(pixels).copy()
        self.set_image(self.original_pixels)
        self.overlays.update(root=False,bounds=False,ground=False,numbers=False)
        self.setDragMode(self.DragMode.NoDrag)
        self.setMouseTracking(True);self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.drag=None;self.selected_handle='origin'

    def hit_handle(self,position):
        point=self.mapToScene(position)
        x,y=self.reference.origin;zoom=max(self.transform().m11(),.001)
        if abs(point.x()-x)*zoom<=9 and abs(point.y()-y)*zoom<=9:return 'origin'
        if abs(point.y()-y)*zoom<=7:return 'ground'
        if abs(point.x()-x)*zoom<=7:return 'y_axis'
        return None

    def set_reference(self,reference):
        self.reference=reference;self.reference_changed.emit(reference);self.viewport().update()

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            self.setFocus();handle=self.hit_handle(event.position().toPoint())
            if handle:self.selected_handle=handle;self.drag=(self.mapToScene(event.position().toPoint()),self.reference,handle)
            event.accept()
        else:super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self.drag:
            start,reference,handle=self.drag;delta=self.mapToScene(event.position().toPoint())-start
            self.set_reference(reference.moved(handle,round(delta.x()),round(delta.y())))
        else:
            handle=self.hit_handle(event.position().toPoint())
            cursor={'ground':Qt.CursorShape.SizeVerCursor,'y_axis':Qt.CursorShape.SizeHorCursor,'origin':Qt.CursorShape.SizeAllCursor}.get(handle,Qt.CursorShape.ArrowCursor)
            self.viewport().setCursor(cursor)
        event.accept()

    def mouseReleaseEvent(self,event):
        if self.drag:self.mouseMoveEvent(event)
        self.drag=None;event.accept()

    def keyPressEvent(self,event):
        movement={Qt.Key.Key_Left:(-1,0),Qt.Key.Key_Right:(1,0),Qt.Key.Key_Up:(0,-1),Qt.Key.Key_Down:(0,1)}
        if event.key() in movement:
            dx,dy=movement[event.key()];step=10 if event.modifiers()&Qt.KeyboardModifier.ShiftModifier else 1
            self.set_reference(self.reference.moved(self.selected_handle,dx*step,dy*step));event.accept()
        else:super().keyPressEvent(event)

    def drawForeground(self,painter,rect):
        super().drawForeground(painter,rect)
        draw_reference(painter,self,self.reference)


class CharacterReferenceDialog(QDialog):
    saved=Signal(object)

    def __init__(self,reference,pixels,animation_name,save_uses_passthrough=False,parent=None):
        super().__init__(parent)
        self.setWindowTitle(t('Character Calibration'))
        self.setModal(False);self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        available=self.screen().availableGeometry();self.resize(min(1080,available.width()-60),min(860,available.height()-60))
        layout=QVBoxLayout(self)
        note=QLabel(t('Idle pixels stay fixed. Drag Ground vertically, Y Axis horizontally, or Origin in both directions. Arrows: 1 px; Shift: 10 px.'))
        note.setWordWrap(True);layout.addWidget(note)
        if save_uses_passthrough:
            note=QLabel(t('Saving starts manual reference editing from keyed pixels. Existing Root settings are retained; whole-canvas output resizing is retained.'))
            note.setWordWrap(True);note.setStyleSheet('color: #f0ce85');layout.addWidget(note)
        info=QLabel(t('Reference: {animation} · Frame {frame} · Canvas {width} × {height}',animation=animation_name,frame=reference.reference_frame_index,width=reference.project_canvas_width,height=reference.project_canvas_height))
        info.setWordWrap(True);layout.addWidget(info)
        self.view=ReferenceCalibrationView(reference,pixels);layout.addWidget(self.view,1)
        controls=QHBoxLayout();self.x=QDoubleSpinBox();self.y=QDoubleSpinBox()
        for field,maximum in ((self.x,reference.project_canvas_width),(self.y,reference.project_canvas_height)):
            field.setRange(0,maximum-1);field.setDecimals(0);field.setSingleStep(1)
        controls.addWidget(QLabel(t('Origin X')));controls.addWidget(self.x);controls.addWidget(QLabel(t('Ground Y')));controls.addWidget(self.y)
        layout.addLayout(controls)
        self.view.reference_changed.connect(self.sync)
        self.x.valueChanged.connect(lambda value:self.view.set_reference(replace(self.view.reference,origin_x=value)))
        self.y.valueChanged.connect(lambda value:self.view.set_reference(replace(self.view.reference,ground_y=value)))
        row=QHBoxLayout();fit=QPushButton(t('Fit'));fit.clicked.connect(self.view.fit_image);row.addWidget(fit)
        actual=QPushButton(t('100%'));actual.clicked.connect(self.view.actual_size);row.addWidget(actual);row.addStretch()
        cancel=QPushButton(t('Cancel'));cancel.clicked.connect(self.reject);row.addWidget(cancel)
        self.save_button=QPushButton(t('Save Character Reference'));self.save_button.setObjectName('primary');self.save_button.clicked.connect(self.commit);row.addWidget(self.save_button)
        layout.addLayout(row);self.sync(reference)
        for button in self.findChildren(QPushButton):button.setAutoDefault(False)

    def sync(self,reference):
        for field,value in ((self.x,reference.origin_x),(self.y,reference.ground_y)):
            field.blockSignals(True);field.setValue(value);field.blockSignals(False)

    def commit(self):
        self.saved.emit(self.view.reference);self.accept()
