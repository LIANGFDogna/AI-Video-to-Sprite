"""Sprite Sheet Slicer: live fixed-cell grid preview shared by both menu entries.

The dialog never keeps a semi-automatic Cell Size: Auto Layout recomputes the Cell Size from
Columns, Rows, Margin and Spacing on every change, and the preview, the summary and the
created Animation all read the same calculate_cells() result.
"""
import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSizeF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import (QAbstractSpinBox, QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
    QFormLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from app.core.sprite_sheet_slice import DEFAULT_FPS, SliceConfig, calculate_cells, detect_grid
from app.i18n import t


class SheetPreview(QWidget):
    """The original Sprite Sheet with a live grid overlay and frame numbers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(380, 380)
        self.image = QImage()
        self.layout_result = None

    def set_sheet(self, pixels):
        data = np.ascontiguousarray(pixels)
        height, width = data.shape[:2]
        self.image = QImage(data.data, width, height, data.strides[0], QImage.Format.Format_RGBA8888).copy()
        self.update()

    def set_layout(self, layout):
        self.layout_result = layout
        self.update()

    def scale_factor(self):
        if self.image.isNull() or not self.image.width() or not self.image.height():
            return 1.
        return max(.02, min((self.width() - 12) / self.image.width(), (self.height() - 12) / self.image.height()))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#151c26'))
        if self.image.isNull():
            painter.setPen(QColor('#9fb0c8'))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, t('No Sprite Sheet'))
            return
        factor = self.scale_factor()
        width, height = self.image.width() * factor, self.image.height() * factor
        origin = QPointF(max(6., (self.width() - width) / 2), max(6., (self.height() - height) / 2))
        painter.drawImage(QRectF(origin, QSizeF(width, height)), self.image)
        font = QFont()
        font.setPixelSize(11)
        painter.setFont(font)
        layout = self.layout_result
        cells = layout.cells if layout is not None else []
        for cell in cells:
            rect = QRectF(origin.x() + cell.x * factor, origin.y() + cell.y * factor,
                          cell.width * factor, cell.height * factor)
            if not cell.valid:
                painter.setPen(QPen(QColor('#ff6b6b'), 2))
                painter.drawRect(rect)
                painter.drawLine(rect.topLeft(), rect.bottomRight())
                painter.setPen(QColor('#ffb3b3'))
                painter.drawText(rect.adjusted(3, 2, -3, -3),
                                 Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft, t('OUT OF BOUNDS'))
                continue
            skipped = cell.skipped
            painter.setPen(QPen(QColor('#6b7787' if skipped else '#8fd3ff'), 1,
                                Qt.PenStyle.DashLine if skipped else Qt.PenStyle.SolidLine))
            painter.drawRect(rect)
            label = t('skipped') if skipped else str(cell.frame_index if cell.frame_index is not None else cell.index)
            painter.setPen(QColor('#e8f2ff'))
            painter.drawText(rect.adjusted(3, 2, -3, -3), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft, label)


class SpriteSheetSlicerDialog(QDialog):
    """Grid parameters, live preview and one result config for the controller."""

    def __init__(self, host, name, pixels, config=None, mode='new', existing=None):
        super().__init__(host)
        self.host = host
        self.name = name
        self.pixels = np.asarray(pixels)
        self.result_config = None
        self.result_layout = None
        self.mode = mode
        self.setWindowTitle(t('Slice Sprite Sheet'))
        self.resize(1120, 760)
        base = config or SliceConfig()
        self.preview = SheetPreview()
        self.preview.set_sheet(self.pixels)
        layout = QHBoxLayout(self)
        left = QVBoxLayout()
        note = QLabel(t('Every frame is a fixed Cell Rect: no alpha trim, no resize, RGBA passthrough.'))
        note.setWordWrap(True)
        left.addWidget(note)
        left.addWidget(self.preview, 1)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        left.addWidget(self.summary)
        layout.addLayout(left, 3)
        right = QVBoxLayout()
        self.auto_layout = QCheckBox(t('Calculate cell size from Columns and Rows'))
        self.auto_layout.setChecked(bool(base.auto_layout))
        right.addWidget(self.auto_layout)
        self.columns = self.spin(1, 4096, base.columns)
        self.rows = self.spin(1, 4096, base.rows)
        resolved = base.resolved(self.size_hint())
        self.cell_width = self.spin(0, 16384, resolved.cell_width)
        self.cell_height = self.spin(0, 16384, resolved.cell_height)
        self.margin_left = self.spin(0, 16384, base.margin_left)
        self.margin_top = self.spin(0, 16384, base.margin_top)
        self.spacing_x = self.spin(0, 4096, base.spacing_x)
        self.spacing_y = self.spin(0, 4096, base.spacing_y)
        self.frame_count = self.spin(0, 100000, base.frame_count)
        self.order = QComboBox()
        for value, label in (('row_major', 'Left to right, top to bottom'), ('row_major_reverse', 'Right to left')):
            self.order.addItem(t(label), value)
        self.order.setCurrentIndex(max(0, self.order.findData(base.frame_order)))
        self.fps = QDoubleSpinBox()
        self.fps.setRange(.1, 240)
        self.fps.setDecimals(3)
        self.fps.setValue(base.fps or DEFAULT_FPS)
        self.loop = QCheckBox(t('Loop playback'))
        self.loop.setChecked(bool(base.loop))
        self.ignore_empty = QCheckBox(t('Ignore fully transparent cells'))
        self.ignore_empty.setChecked(bool(base.ignore_empty))
        form = QFormLayout()
        for label, widget in (('Columns', self.columns), ('Rows', self.rows), ('Cell Width', self.cell_width),
                              ('Cell Height', self.cell_height), ('Margin Left', self.margin_left),
                              ('Margin Top', self.margin_top), ('Spacing X', self.spacing_x),
                              ('Spacing Y', self.spacing_y), ('Frame Count', self.frame_count)):
            form.addRow(t(label), widget)
        form.addRow(t('Frame Order'), self.order)
        form.addRow(t('FPS'), self.fps)
        form.addRow(self.loop)
        form.addRow(self.ignore_empty)
        right.addLayout(form)
        if existing:
            right.addWidget(self.note(t('This Sprite Sheet already created: {name}', name=existing)))
        right.addWidget(self.button('Auto Detect Grid', self.auto_detect))
        right.addStretch(1)
        row = QHBoxLayout()
        row.addWidget(self.button('Cancel', self.reject))
        self.create_button = self.button('Create Animation', self.accept, primary=True)
        row.addWidget(self.create_button)
        right.addLayout(row)
        layout.addLayout(right, 2)
        self.auto_layout.toggled.connect(self._auto_toggled)
        for widget in (self.columns, self.rows, self.cell_width, self.cell_height, self.margin_left,
                       self.margin_top, self.spacing_x, self.spacing_y, self.frame_count):
            widget.valueChanged.connect(self.update_preview)
        self.order.currentIndexChanged.connect(self.update_preview)
        self.ignore_empty.toggled.connect(self.update_preview)
        self._auto_toggled()

    # ------------------------------------------------------------------ helpers
    def spin(self, low, high, value):
        widget = QSpinBox()
        widget.setRange(low, high)
        widget.setValue(int(value))
        widget.setKeyboardTracking(True)
        return widget

    def button(self, label, callback, primary=False):
        widget = QPushButton(t(label))
        widget.setAutoDefault(False)
        widget.clicked.connect(lambda checked=False: callback())
        if primary:
            widget.setObjectName('primary')
        return widget

    def note(self, text):
        label = QLabel(text)
        label.setWordWrap(True)
        label.setObjectName('muted')
        return label

    def size_hint(self):
        return (self.pixels.shape[1], self.pixels.shape[0])

    def config(self):
        return SliceConfig(columns=self.columns.value(), rows=self.rows.value(),
                           cell_width=self.cell_width.value(), cell_height=self.cell_height.value(),
                           margin_left=self.margin_left.value(), margin_top=self.margin_top.value(),
                           spacing_x=self.spacing_x.value(), spacing_y=self.spacing_y.value(),
                           frame_count=self.frame_count.value(), frame_order=self.order.currentData(),
                           fps=self.fps.value(), loop=self.loop.isChecked(),
                           ignore_empty=self.ignore_empty.isChecked(),
                           auto_layout=self.auto_layout.isChecked())

    def _auto_toggled(self, *args):
        "Auto Layout owns the Cell Size; Manual Layout hands it back to the user."
        automatic = self.auto_layout.isChecked()
        for widget in (self.cell_width, self.cell_height):
            widget.setReadOnly(automatic)
            widget.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons if automatic
                                    else QAbstractSpinBox.ButtonSymbols.UpDownArrows)
        self.update_preview()

    def update_preview(self, *args):
        try:
            layout = calculate_cells(self.config(), self.pixels)
        except ValueError as error:
            self.result_layout = None
            self.preview.set_layout(None)
            self.summary.setText(str(error))
            self.create_button.setEnabled(False)
            return
        self.result_layout = layout
        if self.auto_layout.isChecked():
            for widget, value in ((self.cell_width, layout.config.cell_width),
                                  (self.cell_height, layout.config.cell_height),
                                  (self.spacing_x, layout.config.spacing_x),
                                  (self.spacing_y, layout.config.spacing_y)):
                if widget.value() != int(value):
                    widget.blockSignals(True)
                    widget.setValue(int(value))
                    widget.blockSignals(False)
        self.preview.set_layout(layout)
        frames = layout.frame_count
        duration = frames / max(.1, self.fps.value())
        lines = [t('{frames} frames · Cell {width}×{height} · {fps:g} FPS · {duration:.2f}s',
                   frames=frames, width=layout.config.cell_width, height=layout.config.cell_height,
                   fps=self.fps.value(), duration=duration)]
        if layout.unused:
            lines.append(t('Unused edge: {width} × {height} px', width=layout.remainder[0], height=layout.remainder[1]))
        if layout.skipped:
            lines.append(t('Ignored empty cells: {count}', count=len(layout.skipped)))
        if layout.invalid:
            lines.append(t('Cells outside the sheet: {count}', count=len(layout.invalid)))
        self.summary.setText('\n'.join(lines))
        self.create_button.setEnabled(not layout.invalid and frames > 0)

    def auto_detect(self):
        guess = detect_grid(self.pixels)
        if guess is None:
            self.summary.setText(t('No transparent separator lines were found; keep the manual grid.'))
            return
        self.auto_layout.setChecked(False)
        for widget, value in ((self.columns, guess.columns), (self.rows, guess.rows),
                              (self.cell_width, guess.cell_width), (self.cell_height, guess.cell_height),
                              (self.margin_left, guess.margin_left), (self.margin_top, guess.margin_top)):
            widget.setValue(int(value))
        self.update_preview()

    def accept(self):
        try:
            layout = calculate_cells(self.config(), self.pixels)
        except ValueError as error:
            self.summary.setText(str(error))
            return
        if layout.invalid:
            self.summary.setText(t('Cells outside the sheet: {count}', count=len(layout.invalid)))
            return
        if not layout.frames:
            self.summary.setText(t('The Sprite Sheet grid selects no frames'))
            return
        self.result_layout = layout
        self.result_config = layout.config
        super().accept()
