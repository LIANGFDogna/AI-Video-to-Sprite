"""Non-modal review of the exact cached PNGs consumed by the exporters."""
import copy
import numpy as np
from PySide6.QtCore import QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QBrush, QKeySequence, QShortcut, QDesktopServices
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QDoubleSpinBox, QCheckBox, QSlider, QColorDialog, QMenu)

from app.i18n import t, translate_error
from app.ui.video_viewer import VideoViewer
from app.ui.worker import Worker


def composite_layers(layers):
    if len(layers) == 1 and layers[0][1] == 1:
        return layers[0][0]
    shape = layers[-1][0].shape
    output = np.zeros(shape, np.float32)
    for image, opacity in layers:
        source = image.astype(np.float32)/255
        alpha = source[..., 3:4]*opacity
        output[..., :3] = source[..., :3]*alpha + output[..., :3]*(1-alpha)
        output[..., 3:4] = alpha + output[..., 3:4]*(1-alpha)
    output[..., :3] /= np.maximum(output[..., 3:4], 1e-8)
    return np.clip(output*255+.5, 0, 255).astype(np.uint8)


class AnimationPreview(QDialog):
    export_requested = Signal()

    def __init__(self, provider, export_folder=None, parent=None):
        super().__init__(parent)
        self.provider = provider
        self.project = provider.project
        self.export_folder = export_folder
        self.index = 0
        self.stale = False
        self.worker = None
        self.pending = False
        self.revision = 0
        self.last_pixels = None
        self.setWindowTitle(t("Animation Preview / Export Review"))
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setModal(False)
        self.resize(1050, 820)
        self.setMinimumSize(800, 620)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance)
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.comparison = QComboBox()
        self.comparison.addItem(t("Final sprite frame") if self.project.is_passthrough else t("Final aligned sprite"), "final")
        self.comparison.addItem(t("Imported frame") if self.project.input_mode == "frame_sequence" else t("Source keyed frame"), "source")
        self.comparison.currentIndexChanged.connect(self.request_frame)
        row.addWidget(QLabel(t("Before / After")))
        row.addWidget(self.comparison)
        self.background = QComboBox()
        for key in ("Checkerboard", "Black", "White", "Custom Color"):
            self.background.addItem(t(key), key)
        self.background.currentIndexChanged.connect(self._background)
        row.addWidget(self.background)
        for label, zoom in (("Fit", None), ("100%", 1), ("200%", 2), ("400%", 4)):
            row.addWidget(self.button(label, lambda checked=False, z=zoom: self.zoom(z)))
        layout.addLayout(row)
        self.viewer = VideoViewer()
        self.viewer.overlays.update(root=False, bounds=False, canvas=False, ground=False, numbers=True, path=False)
        layout.addWidget(self.viewer, 1)
        overlays = QHBoxLayout()
        self.overlay_controls = {}
        for key, label in (("root", "Root Point"), ("ground", "Ground Reference"), ("bounds", "Alpha Bounds"),
                ("canvas", "Cell Bounds"), ("numbers", "Frame Number"), ("path", "Root Path")):
            check = QCheckBox(t(label))
            if key == "root": check.setToolTip(t("tooltip.root_point"))
            check.setChecked(key == "numbers")
            check.toggled.connect(lambda value, k=key: self.overlay(k, value))
            overlays.addWidget(check)
            self.overlay_controls[key] = check
            if self.project.is_passthrough and key in ("root", "ground", "path"):
                check.setEnabled(False)
        layout.addLayout(overlays)
        options = QHBoxLayout()
        self.onion = QCheckBox(t("Onion Skin"))
        self.ghost = QCheckBox(t("Motion Ghost"))
        self.seam = QCheckBox(t("Loop Seam"))
        self.loop = QCheckBox(t("Loop"))
        self.loop.setChecked(self.project.export_settings.loop)
        for control in (self.onion, self.ghost, self.seam, self.loop):
            options.addWidget(control)
            control.toggled.connect(self.request_frame)
        options.addStretch()
        options.addWidget(QLabel(t("Playback FPS")))
        self.fps = QComboBox()
        for value in ("Source", 6, 8, 10, 12, 15, 20, 24, 30, 60, "Custom"):
            self.fps.addItem(t(str(value)), value)
        self.fps.currentIndexChanged.connect(self.update_speed)
        self.custom_fps = QDoubleSpinBox()
        self.custom_fps.setRange(.1, 240)
        self.custom_fps.setValue(self.project.video.fps or 24)
        self.custom_fps.valueChanged.connect(self.update_speed)
        options.addWidget(self.fps)
        options.addWidget(self.custom_fps)
        layout.addLayout(options)
        playback = QHBoxLayout()
        for label, callback in (("First Frame", lambda: self.select(0)), ("Previous Frame", lambda: self.step(-1))):
            playback.addWidget(self.button(label, callback))
        self.play = self.button("Play", self.toggle_play)
        playback.addWidget(self.play)
        playback.addWidget(self.button("Next Frame", lambda: self.step(1)))
        playback.addWidget(self.button("Last Frame", lambda: self.select(len(provider)-1)))
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, max(0, len(provider)-1))
        self.slider.valueChanged.connect(self.select)
        playback.addWidget(self.slider, 1)
        self.frame_label = QLabel()
        playback.addWidget(self.frame_label)
        layout.addLayout(playback)
        footer = QHBoxLayout()
        self.warning_button = self.button("Warnings", self.show_warnings)
        footer.addWidget(self.warning_button)
        self.warning_label = QLabel()
        self.warning_label.setWordWrap(True)
        footer.addWidget(self.warning_label, 1)
        footer.addWidget(self.button("Back to Edit", self.close))
        self.export_button = self.button("Export", self.export_requested.emit)
        footer.addWidget(self.export_button)
        self.folder_button = self.button("Open Export Folder", self.open_folder)
        self.folder_button.setVisible(export_folder is not None)
        footer.addWidget(self.folder_button)
        layout.addLayout(footer)
        for key, callback in (("Space", self.toggle_play), ("Left", lambda: self.step(-1)), ("Right", lambda: self.step(1)),
                               ("Home", lambda: self.select(0)), ("End", lambda: self.select(len(provider)-1))):
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.activated.connect(callback)
        self.update_speed()
        self.request_frame()

    def button(self, text, callback):
        button = QPushButton(t(text))
        button.setAutoDefault(False)
        button.clicked.connect(callback)
        return button

    def update_speed(self):
        choice = self.fps.currentData()
        self.custom_fps.setVisible(choice == "Custom")
        value = self.project.video.fps if choice == "Source" else self.custom_fps.value() if choice == "Custom" else float(choice)
        self.timer.setInterval(max(1, round(1000*self.provider.duration(self.index)))) if choice == "Source" else self.timer.setInterval(max(1, round(1000/max(.1, value))))

    def sequence(self):
        n = len(self.provider)
        return list(dict.fromkeys([*range(max(0, n-3), n), *range(min(3, n))])) if self.seam.isChecked() else list(range(n))

    def toggle_play(self):
        if self.stale: return
        if self.timer.isActive():
            self.timer.stop()
            self.play.setText(t("Play"))
        else:
            if self.seam.isChecked() and self.index not in self.sequence():
                self.select(self.sequence()[0])
            self.timer.start()
            self.play.setText(t("Pause"))

    def advance(self):
        if self.worker or self.pending or self.stale:
            return
        sequence = self.sequence()
        position = sequence.index(self.index) if self.index in sequence else -1
        if position+1 >= len(sequence):
            if self.loop.isChecked() or self.seam.isChecked():
                self.select(sequence[0])
            else:
                self.toggle_play()
        else:
            self.select(sequence[position+1])

    def step(self, delta):
        self.timer.stop()
        self.play.setText(t("Play"))
        self.select(min(len(self.provider)-1, max(0, self.index+delta)))

    def select(self, index):
        self.index = min(len(self.provider)-1, max(0, index))
        self.slider.blockSignals(True)
        self.slider.setValue(self.index)
        self.slider.blockSignals(False)
        self.update_speed()
        self.request_frame()

    def request_frame(self, *args):
        self.revision += 1
        self.pending = True
        if self.worker or self.stale:
            return
        self.pending = False
        index, revision = self.index, self.revision
        before = self.comparison.currentData() == "source"
        onion, ghost = self.onion.isChecked(), self.ghost.isChecked()
        loop = self.loop.isChecked()
        def operation(progress, cancel):
            read = self.provider.get_source_keyed_frame if before else self.provider.get_final_frame
            current = read(index)
            layers = []
            if ghost:
                layers.extend((read(i), .10+.03*(i-max(0, index-4))) for i in range(max(0, index-4), index))
            if onion:
                neighbors = ((index-1) % len(self.provider), (index+1) % len(self.provider)) if loop else (max(0, index-1), min(len(self.provider)-1, index+1))
                layers.extend((read(i), .22) for i in neighbors if i != index)
            layers.append((current, 1.))
            return composite_layers(layers), before, index, revision
        self.worker = Worker(operation, self)
        self.worker.result.connect(self._result)
        self.worker.failed.connect(self._error)
        self.worker.finished.connect(self._finished)
        self.worker.start()

    def _result(self, result):
        pixels, before, index, revision = result
        if revision != self.revision or self.stale:
            return
        self.last_pixels = pixels
        self.viewer.set_image(pixels)
        frame = copy.deepcopy(self.provider.frame_data(index))
        if before:
            self.viewer.character_profile = None
            frame.root = frame.raw_root or frame.root
            self.viewer.root_path = [f.raw_root or f.root for f in self.project.output_frames]
            self.viewer.ground = self.project.output_frames[0].ground
        else:
            self.viewer.character_profile = self.project.character_profile
            frame.root, frame.bbox = frame.cell_root, frame.cell_bbox
            self.viewer.root_path = [f.cell_root for f in self.project.output_frames]
            self.viewer.ground = self.project.layout.ground_baseline
        self.viewer.character_reference=self.project.character_reference
        if self.project.character_reference:
            from app.core.character_reference import reference_mapping
            self.viewer.reference_mapping=(1.,1.,0.,0.) if before else reference_mapping(self.project.character_reference,self.project.layout,self.project.sprite_cell.preserve_aspect_ratio)
        self.viewer.frame = frame
        if self.project.is_passthrough:
            self.viewer.root_visible = False
            self.viewer.root_path, self.viewer.ground, self.viewer.character_profile = [], None, None
        self.viewer.viewport().update()
        self.frame_label.setText(t("Frame {frame:02d} / {count}", frame=index+1, count=len(self.provider)))
        self.warning_label.setText(" · ".join(t(w) for w in frame.warnings))
        self.warning_button.setText(t("Warnings: {count}", count=sum(bool(f.warnings) for f in self.project.output_frames)))

    def _finished(self):
        worker = self.worker
        self.worker = None
        worker.deleteLater()
        if self.pending:
            self.request_frame()

    def _error(self, message):
        self.mark_stale()
        self.warning_label.setText(translate_error(message))

    def mark_stale(self):
        self.stale = True
        self.timer.stop()
        self.play.setEnabled(False)
        self.export_button.setEnabled(False)
        self.warning_label.setText(t("Final frames changed. Rebuild and reopen the preview."))

    def overlay(self, key, value):
        self.viewer.overlays[key] = value
        self.viewer.viewport().update()

    def zoom(self, value):
        if value is None:
            self.viewer.fit_image()
        else:
            self.viewer.resetTransform()
            self.viewer.scale(value, value)
            self.viewer._auto_fit = False

    def _background(self):
        value = self.background.currentData()
        if value == "Checkerboard":
            self.viewer.set_background(True)
        else:
            color = QColor("black" if value == "Black" else "white")
            if value == "Custom Color":
                color = QColorDialog.getColor(QColor("#273346"), self, t("Custom Color"))
                if not color.isValid(): return
            self.viewer.setBackgroundBrush(QBrush(color))

    def show_warnings(self):
        menu = QMenu(self)
        for f in self.project.output_frames:
            if f.warnings:
                action = menu.addAction(t("Frame {frame}: {warnings}", frame=f.index, warnings=" · ".join(t(w) for w in f.warnings)))
                action.triggered.connect(lambda checked=False, i=f.index: self.select(i))
        menu.exec(self.warning_button.mapToGlobal(self.warning_button.rect().bottomLeft()))

    def open_folder(self):
        if self.export_folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.export_folder)))

    def closeEvent(self, event):
        self.timer.stop()
        self.stale = True
        if self.worker:
            self.worker.cancel()
            self.worker.wait()
        event.accept()
