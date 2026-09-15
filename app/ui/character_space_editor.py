"""Idle calibration and symmetric project-level reference editing."""
from dataclasses import replace
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QDoubleSpinBox, QComboBox
from app.i18n import t
from app.ui.video_viewer import VideoViewer
from app.ui.character_overlay import draw_character_space
from app.core.alpha_utils import alpha_bbox, root_inside


class CharacterSpaceView(VideoViewer):
    half_width_changed = Signal(float)
    canonical_changed = Signal(float, float)
    placement_changed = Signal(object)

    def __init__(self, profile, pixels, placement, calibrating, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.calibrating = calibrating
        self.pick_root = False
        self.placement = tuple(placement)
        self._drag = None
        self._press_position = None
        self._start_placement = None
        self.overlays.update(root=False, bounds=False, canvas=False, numbers=False, ground=False)
        self.set_image(pixels)
        self.pixmap_item.setPos(QPointF(*placement))
        self.scene().setSceneRect(QRectF(0, 0, *profile.canvas_size))
        self.alpha_bounds = alpha_bbox(pixels, 16, 1)
        self.fit_image()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        point = self.mapToScene(event.position().toPoint())
        l, top, r, bottom = self.profile.reference_box
        radius = 12/max(self.transform().m11(), .001)
        if abs(point.y()-(top+bottom)/2) <= radius and min(abs(point.x()-l), abs(point.x()-r)) <= radius:
            self._drag = "width"
        elif self.calibrating and self.pick_root:
            self.canonical_changed.emit(point.x(), point.y())
            self.pick_root = False
        elif self.calibrating:
            self._drag = "frame"
            self._press_position = point
            self._start_placement = self.placement
        else:
            return super().mousePressEvent(event)
        event.accept()

    def mouseMoveEvent(self, event):
        point = self.mapToScene(event.position().toPoint())
        if self._drag == "width":
            self.half_width_changed.emit(self.profile.with_edge(point.x()).reference_box_half_width)
        elif self._drag == "frame":
            delta = point-self._press_position
            self.placement = (self._start_placement[0]+delta.x(), self._start_placement[1]+delta.y())
            self.pixmap_item.setPos(QPointF(*self.placement))
            self.viewport().update()
        else:
            return super().mouseMoveEvent(event)
        event.accept()

    def mouseReleaseEvent(self, event):
        mode, self._drag = self._drag, None
        if mode == "frame":
            self.placement_changed.emit(self.placement)
        if mode:
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def drawForeground(self, painter, rect):
        if not hasattr(self, "profile"):
            return
        painter.setPen(self.pen("#63738d"))
        painter.drawRect(self.sceneRect())
        if self.alpha_bounds:
            l, top, r, bottom = self.alpha_bounds
            dx, dy = self.placement
            painter.setPen(self.pen("#5ad6c5", 1))
            painter.drawRect(QRectF(l+dx, top+dy, r-l, bottom-top))
        draw_character_space(painter, self.profile, zoom=self.transform().m11(), handles=True)


class CharacterSpaceEditor(QDialog):
    profile_saved = Signal(object, object)

    def __init__(self, profile, pixels, placement=(0., 0.), source_rgba=None, parent=None):
        super().__init__(parent)
        self.profile = profile
        self.source_rgba = source_rgba
        self.calibrating = source_rgba is not None
        self.root_set = not self.calibrating
        self.setWindowTitle(t("Character Space / Character Reference Box"))
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setModal(False)
        self.resize(1000, 850)
        layout = QVBoxLayout(self)
        note = QLabel(t("First Idle: drag the whole frame to confirm standing position, then set Canonical Root. Its X always snaps to the Y Axis.") if self.calibrating else t("Project reference is fixed. Drag either blue handle to change only the symmetric width; Alpha Bounds remain per-frame."))
        note.setWordWrap(True)
        layout.addWidget(note)
        self.view = CharacterSpaceView(profile, pixels, placement, self.calibrating)
        self.view.half_width_changed.connect(self.set_half_width)
        self.view.canonical_changed.connect(self.set_canonical)
        self.view.placement_changed.connect(self.moved_frame)
        layout.addWidget(self.view, 1)
        legend = QLabel(t("Blue dashed: Character Reference Box · Green solid: Alpha Bounds · Pink: Canonical Root · Gold: Ground Origin"))
        legend.setWordWrap(True)
        layout.addWidget(legend)
        controls = QHBoxLayout()
        self.pick_button = QPushButton(t("Set Canonical Root · X snaps to Y Axis"))
        self.pick_button.setEnabled(self.calibrating)
        self.pick_button.clicked.connect(self.arm_root)
        controls.addWidget(self.pick_button)
        controls.addWidget(QLabel(t("Reference Box Width")))
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setDecimals(2)
        self.width_spin.setRange(1, 65536)
        self.width_spin.setValue(profile.reference_box_half_width*2)
        self.width_spin.setToolTip(t("Symmetric about Y Axis. Changing this width never changes scale, Ground Origin or Canonical Root."))
        self.width_spin.valueChanged.connect(lambda v: self.set_half_width(v/2))
        controls.addWidget(self.width_spin)
        controls.addWidget(QLabel(t("Facing")))
        self.facing = QComboBox()
        for key in ("right", "left"):
            self.facing.addItem(t(key), key)
        self.facing.setCurrentIndex(self.facing.findData(profile.facing))
        self.facing.setEnabled(self.calibrating)
        self.facing.currentIndexChanged.connect(self.set_facing)
        controls.addWidget(self.facing)
        layout.addLayout(controls)
        self.details = QLabel()
        self.details.setWordWrap(True)
        layout.addWidget(self.details)
        footer = QHBoxLayout()
        self.status = QLabel(t("Confirm the standing position, then click Canonical Root.")) if self.calibrating else QLabel(t("Reference Box extends from the canvas top to Ground Origin. Only its width is editable."))
        self.status.setWordWrap(True)
        footer.addWidget(self.status, 1)
        self.save_button = QPushButton(t("Set as Character Reference") if self.calibrating else t("Save Reference Box"))
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self.save_profile)
        footer.addWidget(self.save_button)
        close = QPushButton(t("Cancel"))
        close.clicked.connect(self.close)
        for button in (self.pick_button,self.save_button,close):button.setAutoDefault(False)
        footer.addWidget(close)
        layout.addLayout(footer)
        self.update_profile()

    def update_profile(self):
        self.view.profile = self.profile
        self.view.viewport().update()
        self.width_spin.blockSignals(True)
        self.width_spin.setValue(self.profile.reference_box_half_width*2)
        self.width_spin.blockSignals(False)
        p = self.profile
        self.details.setText(t("Canvas {width} × {height} · Scale {scale:.10g} · Ground Origin ({ox:.2f}, {oy:.2f}) · Canonical Root ({rx:.2f}, {ry:.2f})",
            width=p.canvas_size[0], height=p.canvas_size[1], scale=p.character_scale, ox=p.ground_origin[0], oy=p.ground_origin[1], rx=p.canonical_root[0], ry=p.canonical_root[1]))
        self.save_button.setEnabled(self.root_set)

    def set_half_width(self, half_width):
        self.profile = replace(self.profile, reference_box_half_width=float(half_width))
        self.update_profile()

    def arm_root(self):
        self.view.pick_root = True
        self.status.setText(t("Click the stable body Root. X is locked to the Y Axis."))

    def set_canonical(self, x, y):
        self.profile = self.profile.with_canonical_root(x, y)
        raw = self.source_root()
        self.root_set = bool(root_inside(self.source_rgba, raw, 16))
        self.status.setText(t("Canonical Root X is snapped to the Y Axis. Adjust the reference width, then confirm.") if self.root_set else t("Snapped Root is outside the subject. Drag the frame onto the Y Axis and set Root again."))
        self.update_profile()

    def moved_frame(self, placement):
        self.root_set = False
        self.status.setText(t("Standing position changed. Set Canonical Root again before confirming."))
        self.update_profile()

    def set_facing(self):
        self.profile = replace(self.profile, facing=self.facing.currentData())
        self.update_profile()

    def source_root(self):
        return tuple((self.profile.canonical_root[a]-self.view.placement[a])/self.profile.character_scale for a in (0, 1))

    def save_profile(self):
        if not self.root_set:
            return
        self.profile_saved.emit(self.profile, self.source_root() if self.calibrating else None)
        self.close()
