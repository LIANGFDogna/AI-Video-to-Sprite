from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableView, QVBoxLayout, QWidget
from app.i18n import t


class FrameTableModel(QAbstractTableModel):
    HEADERS = ("Frame", "Root position", "Confidence", "Alpha bounding box", "Warnings")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.frames = []
        self.count = 0
        self.keyframes = {}
        self.stale = False

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else self.count

    def columnCount(self, parent=QModelIndex()):
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return t(self.HEADERS[section])
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        f = self.frames[row] if row < len(self.frames) else None
        if role == Qt.ItemDataRole.DisplayRole:
            root = self.keyframes.get(row, f.root if f else None)
            if col == 0:
                return f"{row:06d}" + ("  ◆" if row in self.keyframes else "")
            if col == 1:
                if f and f.tracking_method == "passthrough":
                    return t("Skipped")
                return f"{root[0]:.2f}, {root[1]:.2f}" if root else "—"
            if col == 2:
                if f and f.tracking_method == "passthrough":
                    return t("Skipped")
                return t("Rebuild required") if self.stale else (f"{f.tracking_confidence:.0%}" if f else "—")
            if col == 3:
                return str(f.bbox) if f and f.bbox else "—"
            if col == 4:
                return " · ".join(t(w) for w in f.warnings) if f else ""
        if role == Qt.ItemDataRole.ForegroundRole and f:
            if f.tracking_method == "passthrough" and col in (1, 2):
                return QColor("#8796aa")
            if self.stale:
                return QColor("#8796aa")
            if f.warnings:
                return QColor("#f58b9d")
            if col == 2:
                return QColor("#64d9bb" if f.tracking_confidence >= 0.7 else "#e7bb71")
        return None


class ConfidenceStrip(QWidget):
    selected = Signal(int)

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model
        self.current = 0
        self.setFixedHeight(12)
        self.setToolTip(t("Tracking confidence: green = reliable, amber = review, red = warning. Click to select a frame."))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#283243"))
        if not self.model.count:
            return
        count = self.model.count
        # Aggregate into screen-pixel buckets so very long clips remain cheap to draw.
        for x in range(self.width()):
            start, end = int(x * count / self.width()), min(count, max(int((x+1)*count/self.width()), int(x*count/self.width())+1))
            frames = self.model.frames[start:end]
            color = "#46556a"
            if frames and not self.model.stale and not all(f.tracking_method == "passthrough" for f in frames):
                if any(f.warnings or f.tracking_confidence < 0.35 for f in frames):
                    color = "#d86b7f"
                elif min(f.tracking_confidence for f in frames) < 0.7:
                    color = "#d7ad63"
                else:
                    color = "#4ab69d"
            painter.fillRect(x, 0, 1, self.height(), QColor(color))
        painter.fillRect(round(self.current / count * self.width()), 0, 2, self.height(), QColor("white"))

    def mousePressEvent(self, event):
        if self.model.count:
            self.selected.emit(min(self.model.count - 1, max(0, int(event.position().x() / self.width() * self.model.count))))


class Timeline(QWidget):
    frame_selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.model = FrameTableModel(self)
        self.strip = ConfidenceStrip(self.model)
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(25)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setShowGrid(False)
        self.table.clicked.connect(lambda index: self.frame_selected.emit(index.row()))
        self.strip.selected.connect(self.frame_selected)
        layout.addWidget(self.strip)
        layout.addWidget(self.table)
        self.setMinimumHeight(115)
        self.setMaximumHeight(205)

    def set_frames(self, frames, count, keyframes, stale=False):
        self.model.beginResetModel()
        self.model.frames, self.model.count, self.model.keyframes, self.model.stale = frames, count, keyframes, stale
        self.model.endResetModel()
        self.strip.update()

    def select(self, index):
        self.table.selectRow(index)
        self.table.scrollTo(self.model.index(index, 0), QAbstractItemView.ScrollHint.EnsureVisible)
        self.strip.current = index
        self.strip.update()
