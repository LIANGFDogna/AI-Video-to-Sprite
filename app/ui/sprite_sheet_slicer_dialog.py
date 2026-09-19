"""Sprite Sheet Slicer: live fixed-cell grid preview shared by both menu entries."""
import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSizeF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QHBoxLayout,
    QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from app.core.sprite_sheet_slice import DEFAULT_FPS, SliceConfig, detect_grid
from app.i18n import t


class SheetPreview(QWidget):
    """The original Sprite Sheet with a live grid overlay and frame numbers."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(380, 380)
        self.image = QImage()
        self.rects = []
        self.skipped = set()

    def set_sheet(self, pixels):
        data = np.ascontiguousarray(pixels)
        height, width = data.shape[:2]
        self.image = QImage(data.data, width, height, data.strides[0], QImage.Format.Format_RGBA8888).copy()
        self.update()

    def set_grid(self, rects, skipped=()):
        self.rects = list(rects)
        self.skipped = set(skipped)
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
        for index, (x, y, cell_width, cell_height) in enumerate(self.rects):
            rect = QRectF(origin.x() + x * factor, origin.y() + y * factor, cell_width * factor, cell_height * factor)
            skipped = index in self.skipped
            painter.setPen(QPen(QColor('#6b7787' if skipped else '#8fd3ff'), 1, Qt.PenStyle.DashLine if skipped else Qt.PenStyle.SolidLine))
            painter.drawRect(rect)
            label = t('skipped') if skipped else str(index)
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
        self.mode = mode
        self.setWindowTitle(t('Slice Sprite Sheet'))
        self.resize(1080, 720)
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
        row.addWidget(self.button('Create Animation', self.accept, primary=True))
        right.addLayout(row)
        layout.addLayout(right, 2)
        for widget in (self.columns, self.rows, self.cell_width, self.cell_height, self.margin_left,
                       self.margin_top, self.spacing_x, self.spacing_y, self.frame_count):
            widget.valueChanged.connect(self.update_preview)
        self.order.currentIndexChanged.connect(self.update_preview)
        self.ignore_empty.toggled.connect(self.update_preview)
        self.update_preview()

    # ------------------------------------------------------------------ helpers
    def spin(self, low, high, value):
        widget = QSpinBox()
        widget.setRange(low, high)
        widget.setValue(int(value))
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
                           ignore_empty=self.ignore_empty.isChecked())

    def empty_cells(self, rects):
        alpha = self.pixels[..., 3]
        return {index for index, (x, y, width, height) in enumerate(rects) if not alpha[y:y + height, x:x + width].any()}

    def update_preview(self, *args):
        try:
            config = self.config()
            resolved, rects = config.cells(self.size_hint())
        except ValueError as error:
            self.summary.setText(str(error))
            self.preview.set_grid([])
            return
        empty = self.empty_cells(rects)
        skipped = empty if config.ignore_empty else set()
        self.preview.set_grid(rects, skipped)
        frames = len(rects) - len(skipped)
        duration = frames / max(.1, self.fps.value())
        self.summary.setText(t('{frames} frames · Cell {width}×{height} · {fps:g} FPS · {duration:.2f}s',
                               frames=frames, width=resolved.cell_width, height=resolved.cell_height,
                               fps=self.fps.value(), duration=duration)
                               + ('\n' + t('Ignored empty cells: {count}', count=len(skipped)) if skipped else ''))

    def auto_detect(self):
        guess = detect_grid(self.pixels)
        if guess is None:
            self.summary.setText(t('No transparent separator lines were found; keep the manual grid.'))
            return
        for widget, value in ((self.columns, guess.columns), (self.rows, guess.rows),
                              (self.cell_width, guess.cell_width), (self.cell_height, guess.cell_height),
                              (self.margin_left, guess.margin_left), (self.margin_top, guess.margin_top)):
            widget.setValue(int(value))
        self.update_preview()

    def accept(self):
        try:
            config = self.config().validate()
        except ValueError as error:
            self.summary.setText(str(error))
            return
        self.result_config = config
        super().accept()
