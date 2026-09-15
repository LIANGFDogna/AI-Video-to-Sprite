from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QRadioButton, QDoubleSpinBox, QFormLayout, QComboBox, QDialogButtonBox, QScrollArea
from app.i18n import t
from app.ui.sequence_info import format_summary, alpha_warning
from app.ui.canvas_fit_info import canvas_fit_summary


class SequenceImportDialog(QDialog):
    import_requested = Signal(object, bool, float, str)

    def __init__(self, scan, parent=None, project_canvas=None):
        super().__init__(parent)
        self.scan = scan
        self.project_canvas = project_canvas
        self.setWindowTitle(t("Import Frame Sequence"))
        self.setModal(False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setStyleSheet("QRadioButton { spacing: 8px; padding: 4px; } QRadioButton::indicator { width: 14px; height: 14px; border-radius: 8px; border: 1px solid #71869e; background: #101722; } QRadioButton::indicator:checked { background: #4ab6a4; border: 2px solid #d4fff6; }")
        self.resize(620, 420)
        layout = QVBoxLayout(self)
        w, h = project_canvas or scan.canvas_size
        summary = QLabel(t("Folder: {folder}\nDetected: {count} frames\nSize: {width} × {height}\nAlpha: {alpha}",
            folder=scan.folder, count=len(scan.names), width=w, height=h, alpha=t(scan.alpha)))
        summary.setWordWrap(True)
        layout.addWidget(summary)
        if project_canvas:
            self.canvas_info = QLabel("\n\n".join(canvas_fit_summary(size, project_canvas) for size in sorted(set(scan.sizes))[:8]))
            self.canvas_info.setWordWrap(True)
            area = QScrollArea()
            area.setWidgetResizable(True)
            area.setWidget(self.canvas_info)
            area.setMinimumHeight(140)
            area.setMaximumHeight(220)
            layout.addWidget(area)
        formats = [info.to_dict() for info in scan.formats]
        self.format_info = QLabel(format_summary(formats))
        self.format_info.setWordWrap(True)
        layout.addWidget(self.format_info)
        self.alpha_warning = QLabel(alpha_warning(formats))
        self.alpha_warning.setWordWrap(True)
        self.alpha_warning.setStyleSheet("color: #f2cf75")
        self.alpha_warning.setVisible(bool(self.alpha_warning.text()))
        layout.addWidget(self.alpha_warning)
        layout.addWidget(QLabel(t("Are these frames already aligned?")))
        self.aligned = QRadioButton(t("Already aligned — build sprites directly"))
        self.process = QRadioButton(t("Process with Root / Motion / Align"))
        self.aligned.setChecked(True)
        layout.addWidget(self.aligned)
        layout.addWidget(self.process)
        note = QLabel(t("Project canvas fit runs first. Passthrough preserves the fitted positions and skips Root / Motion / Align.") if project_canvas else t("PNG is recommended. Alpha is preserved. Passthrough keeps every pixel in place, including in Character Profile projects."))
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.fps = QDoubleSpinBox()
        self.fps.setRange(.1, 240)
        self.fps.setDecimals(3)
        self.fps.setValue(24.)
        form.addRow(t("Animation FPS"), self.fps)
        layout.addLayout(form)
        self.size_policy = QComboBox()
        self.size_policy.addItem(t("Cancel import"), "strict")
        self.size_policy.addItem(t("Place on a shared canvas"), "pad")
        if scan.mixed_sizes:
            warning = QLabel(t("Sequence frame dimensions are inconsistent"))
            warning.setStyleSheet("color: #ef7d91; font-weight: bold")
            layout.addWidget(warning)
            sizes = sorted(set(scan.sizes))
            layout.addWidget(QLabel(" / ".join(f"{w} × {h}" for w, h in sizes[:8])))
            if not project_canvas:
                layout.addWidget(self.size_policy)
            note = QLabel(t("Each frame is center-cropped or padded to the project canvas. No scaling; RGBA padding is transparent.") if project_canvas else t("Shared canvas: {width} × {height}. Keep top-left coordinates; add transparency to the right and bottom. No per-frame scaling.", width=w, height=h))
            note.setWordWrap(True)
            layout.addWidget(note)
        else:
            self.size_policy.hide()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.import_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.import_button.setText(t("Import Frame Sequence"))
        self.import_button.setAutoDefault(False)
        self._submitted=False
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(t("Cancel"))
        self.import_button.setEnabled(bool(project_canvas) or not scan.mixed_sizes)
        self.size_policy.currentIndexChanged.connect(lambda: self.import_button.setEnabled(not scan.mixed_sizes or self.size_policy.currentData() == "pad"))
        buttons.accepted.connect(self.submit)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)

    def submit(self):
        if self._submitted:return
        if self.scan.mixed_sizes and self.size_policy.currentData() != "pad" and not self.project_canvas:
            return
        self._submitted=True
        self.import_requested.emit(self.scan, self.aligned.isChecked(), self.fps.value(), self.size_policy.currentData())
        self.close()
