"""Project parameters and explicit empty-directory reuse; no media selection here."""
from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QDoubleSpinBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout)
from app.i18n import t, translate_error
from app.core.project_workspace import create_project_workspace, sanitize_project_name, TEMPLATES
from app.ui.folder_picker import FolderPickerDialog
from app.ui.theme import STYLE

CANVAS_PRESETS = {"1536x1536": (1536, 1536), "1024x1536": (1024, 1536), "512x512": (512, 512)}


class NewProjectDialog(QDialog):
    project_created = Signal(object, object)

    def __init__(self, parent=None, initial_directory=""):
        super().__init__(parent)
        self.setWindowTitle(t("New Project"))
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setModal(False)
        self.setStyleSheet(STYLE)
        self.resize(660, 580)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("MainCharacter")
        self.name.editingFinished.connect(self._sanitize_name)
        form.addRow(t("Project Name"), self.name)
        row = QHBoxLayout()
        self.directory = QLineEdit(initial_directory or str(Path.home() / "Documents"))
        self.browse_button = QPushButton(t("Choose project directory"))
        self.browse_button.clicked.connect(self.choose_directory)
        row.addWidget(self.directory, 1)
        row.addWidget(self.browse_button)
        form.addRow(t("Project Save Directory"), row)
        self.project_type = QComboBox()
        self.project_type.addItem(t("Character Animation Project"), "character_animation")
        form.addRow(t("Project Type"), self.project_type)
        self.template = QComboBox()
        for label, key in (("Standard 512×512", "standard"), ("1536→512 AI Character", "ai_character"), ("Custom", "custom")):
            self.template.addItem(t(label), key)
        form.addRow(t("Project Template"), self.template)
        self.canvas_preset = QComboBox()
        for label, key in (("1536×1536", "1536x1536"), ("1024×1536", "1024x1536"), ("512×512", "512x512"), ("Custom", "custom")):
            self.canvas_preset.addItem(t(label), key)
        form.addRow(t("Project Canvas Preset"), self.canvas_preset)
        self.source_width, self.source_height, self.output_width, self.output_height = [QSpinBox() for _ in range(4)]
        for spin in (self.source_width, self.source_height, self.output_width, self.output_height):
            spin.setRange(1, 16384)
        self.source_width.setAccessibleName(t("Project Canvas Width"))
        self.source_height.setAccessibleName(t("Project Canvas Height"))
        for title, width, height in (("Project Standard Canvas", self.source_width, self.source_height), ("Default Output Resolution", self.output_width, self.output_height)):
            row = QHBoxLayout()
            row.addWidget(width)
            row.addWidget(QLabel("×"))
            row.addWidget(height)
            form.addRow(t(title), row)
        self.fps = QDoubleSpinBox()
        self.fps.setRange(.1, 240)
        self.fps.setDecimals(3)
        self.fps.setValue(24.)
        form.addRow(t("Default Animation FPS"), self.fps)
        layout.addLayout(form)
        canvas_note = QLabel(t("All media are fitted by resolution center to the project canvas, without moving content based on character position."))
        canvas_note.setWordWrap(True)
        layout.addWidget(canvas_note)
        self.template_info = QLabel()
        layout.addWidget(self.template_info)
        note = QLabel(t("Import Idle later to establish Ground Origin, Canonical Root and Character Reference Box. No Character Profile is created automatically."))
        note.setWordWrap(True)
        layout.addWidget(note)
        self.destination = QLabel()
        self.destination.setWordWrap(True)
        self.destination.setMinimumWidth(0)
        layout.addWidget(self.destination)
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setStyleSheet("color: #f2cf75")
        layout.addWidget(self.message)
        self.reuse_button = QPushButton(t("Use existing empty directory"))
        self.reuse_button.clicked.connect(lambda: self.create_project(use_existing_empty=True))
        self.reuse_button.hide()
        layout.addWidget(self.reuse_button)
        bottom = QHBoxLayout()
        bottom.addStretch()
        self.create_button = QPushButton(t("Create Project"))
        self.create_button.setObjectName("primary")
        self.create_button.clicked.connect(lambda: self.create_project())
        self.cancel_button = QPushButton(t("Cancel"))
        self.cancel_button.clicked.connect(self.close)
        bottom.addWidget(self.create_button)
        bottom.addWidget(self.cancel_button)
        layout.addLayout(bottom)
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)
        self.template.currentIndexChanged.connect(self._apply_template)
        self.canvas_preset.currentIndexChanged.connect(self._apply_canvas_preset)
        self.template.setCurrentIndex(1)
        self.name.textChanged.connect(self._destination_changed)
        self.directory.textChanged.connect(self._destination_changed)
        for spin in (self.source_width, self.source_height, self.output_width, self.output_height):
            spin.valueChanged.connect(self._update_template_info)
        self._destination_changed()

    def _sanitize_name(self):
        current = self.name.text()
        safe = sanitize_project_name(current)
        if current != safe:
            self.name.setText(safe)
            self.message.setText(t("Windows filename characters were adjusted: {name}", name=safe))

    def _apply_template(self):
        key = self.template.currentData()
        if key in TEMPLATES:
            source, output = TEMPLATES[key]
            for spin, value in zip((self.source_width, self.source_height, self.output_width, self.output_height), (*source, *output)):
                spin.setValue(value)
            self.fps.setValue(24.)
        for spin in (self.output_width, self.output_height):
            spin.setEnabled(key == "custom")
        self._update_template_info()

    def _apply_canvas_preset(self):
        size = CANVAS_PRESETS.get(self.canvas_preset.currentData())
        if size:
            self.source_width.setValue(size[0])
            self.source_height.setValue(size[1])
            self._update_template_info()

    def _update_template_info(self):
        self.canvas_preset.blockSignals(True)
        key = f"{self.source_width.value()}x{self.source_height.value()}"
        self.canvas_preset.setCurrentIndex(self.canvas_preset.findData(key if key in CANVAS_PRESETS else "custom"))
        self.canvas_preset.blockSignals(False)
        scale = min(self.output_width.value() / self.source_width.value(), self.output_height.value() / self.source_height.value())
        self.template_info.setText(t("Canvas scale: {scale:.6f}% · Alpha: RGBA · Preserve aspect ratio", scale=scale * 100))

    def _destination_changed(self):
        target = str(Path(self.directory.text()) / self.name.text())
        self.destination.setText(t("Project location: {path}", path=target))
        self.reuse_button.hide()

    def choose_directory(self):
        folder = FolderPickerDialog.choose(self, "Choose project directory", self.directory.text())
        if folder:
            self.directory.setText(folder)

    def create_project(self, use_existing_empty=False):
        self._sanitize_name()
        try:
            project, path = create_project_workspace(self.directory.text(), self.name.text(), self.template.currentData(),
                (self.output_width.value(), self.output_height.value()), self.fps.value(),
                (self.source_width.value(), self.source_height.value()), use_existing_empty)
        except (ValueError, OSError) as error:
            self.message.setText(translate_error(str(error)))
            target = Path(self.directory.text()) / self.name.text()
            try:
                empty = target.is_dir() and next(target.iterdir(), None) is None
            except OSError:
                empty = False
            self.reuse_button.setVisible(empty)
            return
        self.project_created.emit(project, path)
        self.close()
