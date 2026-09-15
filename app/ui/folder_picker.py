"""Application-owned directory picker; never creates a native Windows dialog."""
from pathlib import Path
import os

from PySide6.QtCore import QDir, QModelIndex, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QFileIconProvider, QFileSystemModel,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QPushButton, QTreeView, QVBoxLayout, QListWidget, QListWidgetItem)

from app.i18n import t, translate_error
from app.ui.theme import STYLE
from app.ui.worker import Worker


PICKER_STYLE = """
QTreeView { background: #111925; color: #eef5ff; border: 1px solid #455a72;
    selection-background-color: #287e71; selection-color: #ffffff; outline: none; }
QTreeView::item { min-height: 32px; padding: 3px 8px; }
QTreeView::item:hover { background: #34485f; color: #ffffff; }
QTreeView::item:selected, QTreeView::item:selected:hover, QTreeView::item:selected:!active {
    background: #287e71; color: #ffffff; }
QLineEdit { color: #f2f6fd; selection-background-color: #287e71; selection-color: #ffffff; }
QLabel#pickerError { color: #ffb1bc; }
"""


class FolderIcons(QFileIconProvider):
    def __init__(self):
        super().__init__()
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setPen(QColor("#ffe6a3"))
        painter.setBrush(QColor("#dfb861"))
        painter.drawRoundedRect(3, 5, 9, 6, 1, 1)
        painter.drawRoundedRect(3, 8, 18, 12, 2, 2)
        painter.end()
        self.folder_icon = QIcon(pixmap)

    def icon(self, _):
        return self.folder_icon


class FolderPickerDialog(QDialog):
    def __init__(self, parent=None, title="Choose folder", path="", sequence=False):
        super().__init__(parent)
        self.setWindowTitle(t(title))
        self.setStyleSheet(STYLE + PICKER_STYLE)
        # All palette groups remain readable even with a light host system palette.
        palette = self.palette()
        for role, color in ((QPalette.ColorRole.Window, "#161d28"), (QPalette.ColorRole.WindowText, "#eef5ff"),
                (QPalette.ColorRole.Base, "#111925"), (QPalette.ColorRole.Text, "#eef5ff"),
                (QPalette.ColorRole.Highlight, "#287e71"), (QPalette.ColorRole.HighlightedText, "#ffffff")):
            palette.setColor(role, QColor(color))
        self.setPalette(palette)
        self.resize(820, 600)
        self.setMinimumSize(620, 440)
        self.sequence = sequence
        self.current_directory = None
        self.selected_folder = ""
        self.history = []
        self.history_position = -1
        self.worker = None
        self.hint_revision = 0
        self.hint_pending = False
        outer = QVBoxLayout(self)
        nav = QHBoxLayout()
        self.back_button = self._button("← Back", lambda: self.go_history(-1))
        self.forward_button = self._button("→ Forward", lambda: self.go_history(1))
        self.up_button = self._button("↑ Parent folder", self.go_up)
        self.new_folder_button = self._button("New folder", self.new_folder)
        for button in (self.back_button, self.forward_button, self.up_button, self.new_folder_button):
            nav.addWidget(button)
        nav.addStretch()
        self.drives = QComboBox()
        for drive in QDir.drives():
            self.drives.addItem(drive.absoluteFilePath(), drive.absoluteFilePath())
        self.drives.activated.connect(lambda: self.navigate(self.drives.currentData()))
        nav.addWidget(self.drives)
        outer.addLayout(nav)
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(t("Enter a folder path, then press Enter"))
        self.path_edit.returnPressed.connect(lambda: self.navigate(self.path_edit.text()))
        outer.addWidget(self.path_edit)
        self.error = QLabel()
        self.error.setWordWrap(True)
        self.error.setObjectName("pickerError")
        self.error.hide()
        outer.addWidget(self.error)
        self.model = QFileSystemModel(self)
        self.icons = FolderIcons()
        self.model.setIconProvider(self.icons)
        self.model.setFilter(QDir.Filter.AllDirs | QDir.Filter.NoDotAndDotDot)
        self.model.setReadOnly(True)
        self.model.setRootPath("")
        self.tree = QTreeView()
        self.tree.setModel(self.model)
        for column in range(1, self.model.columnCount()):
            self.tree.hideColumn(column)
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setItemsExpandable(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setMouseTracking(True)
        self.tree.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.tree.setIconSize(QSize(24, 24))
        self.tree.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.tree.doubleClicked.connect(lambda index: self.navigate(self.model.filePath(index)))
        self.tree.selectionModel().currentChanged.connect(self._selection_changed)
        self.sidebar=QListWidget()
        self.sidebar.setMinimumWidth(125);self.sidebar.setMaximumWidth(200)
        from app.ui.dialogs import path_context
        memory,project=path_context(parent)
        for label,folder in memory.shortcuts(project):
            item=QListWidgetItem(t(label));item.setData(Qt.ItemDataRole.UserRole,str(folder));item.setToolTip(str(folder));self.sidebar.addItem(item)
        computer=QListWidgetItem(t("Computer"));computer.setData(Qt.ItemDataRole.UserRole,None);self.sidebar.addItem(computer)
        self.sidebar.itemClicked.connect(self._shortcut_selected)
        content=QHBoxLayout();content.addWidget(self.sidebar);content.addWidget(self.tree,1);outer.addLayout(content,1)
        self.current_label = QLabel()
        self.current_label.setMinimumWidth(0)
        self.current_label.setWordWrap(True)
        outer.addWidget(self.current_label)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setVisible(sequence)
        outer.addWidget(self.hint)
        bottom = QHBoxLayout()
        bottom.addStretch()
        self.select_button = self._button("Select this folder", self.select_folder)
        self.select_button.setObjectName("primary")
        self.cancel_button = self._button("Cancel", self.reject)
        bottom.addWidget(self.select_button)
        bottom.addWidget(self.cancel_button)
        outer.addLayout(bottom)
        self.hint_timer = QTimer(self)
        self.hint_timer.setSingleShot(True)
        self.hint_timer.timeout.connect(self._start_hint)
        from app.utils.path_memory import valid_directory
        candidate=valid_directory(path,True) or memory.initial('generic_folder',project)
        self.navigate(candidate)

    def _shortcut_selected(self,item):
        value=item.data(Qt.ItemDataRole.UserRole)
        if value:self.navigate(value)
        else:
            self.tree.setRootIndex(QModelIndex());self.current_directory=None
            self.tree.clearSelection();self.tree.setCurrentIndex(QModelIndex())
            self.hint_timer.stop();self.hint_pending=False;self.hint_revision+=1;self.hint.clear()
            self.path_edit.clear();self.current_label.setText(t("Computer"));self.current_label.setToolTip("")
            self.select_button.setEnabled(False);self.new_folder_button.setEnabled(False);self.up_button.setEnabled(False)

    def _button(self, label, callback):
        button = QPushButton(t(label))
        button.setAutoDefault(False)
        button.clicked.connect(callback)
        return button

    def show_error(self, text):
        self.error.setText(text)
        self.error.setVisible(bool(text))

    def navigate(self, path, record=True):
        try:
            if not str(path).strip():raise ValueError("Folder path does not exist")
            destination=Path(path).expanduser()
            if not destination.is_absolute():
                if self.current_directory is None:raise ValueError("Folder path does not exist")
                destination=self.current_directory/destination
            destination=destination.resolve()
            if not destination.is_dir():
                raise ValueError("Folder path does not exist")
            # Detect inaccessible directories before replacing the current location.
            with os.scandir(destination):
                pass
        except (OSError, ValueError) as error:
            self.show_error(translate_error(str(error)))
            return False
        self.current_directory = destination
        self.new_folder_button.setEnabled(True)
        self.path_edit.setText(str(destination))
        self.path_edit.setToolTip(str(destination))
        self.path_edit.setCursorPosition(len(str(destination)))
        drive_index = self.drives.findData(destination.anchor.replace("\\", "/"))
        if drive_index >= 0:
            self.drives.setCurrentIndex(drive_index)
        self.tree.setRootIndex(self.model.index(str(destination)))
        self.tree.selectionModel().clear()
        self.tree.setCurrentIndex(QModelIndex())
        if record:
            self.history = self.history[:self.history_position + 1]
            self.history.append(destination)
            self.history_position = len(self.history) - 1
        self.back_button.setEnabled(self.history_position > 0)
        self.forward_button.setEnabled(self.history_position + 1 < len(self.history))
        self.up_button.setEnabled(destination.parent != destination)
        self.show_error("")
        self._selection_changed()
        return True

    def go_history(self, delta):
        position = self.history_position + delta
        if 0 <= position < len(self.history):
            old = self.history_position
            self.history_position = position
            if not self.navigate(self.history[position], record=False):
                self.history_position = old

    def go_up(self):
        if self.current_directory:
            self.navigate(self.current_directory.parent)

    def selection_path(self):
        index = self.tree.currentIndex()
        return Path(self.model.filePath(index)) if index.isValid() else self.current_directory

    def _selection_changed(self, *_):
        folder = self.selection_path()
        if folder is None:
            return
        self.select_button.setEnabled(True)
        name = folder.name or str(folder)
        shown = name if len(name) <= 90 else name[:42] + "…" + name[-42:]
        self.current_label.setText(t("Current selection: {folder}", folder=shown))
        self.current_label.setToolTip(str(folder))
        if self.sequence:
            self.hint_revision += 1
            self.hint_pending = True
            self.hint.setText(t("Checking sequence images…"))
            self.hint_timer.start(120)

    def _start_hint(self):
        if self.worker or not self.hint_pending:
            return
        folder, revision = self.selection_path(), self.hint_revision
        self.hint_pending = False
        if folder is None:return
        def operation(progress, cancel):
            from app.core.frame_sequence import IMAGE_EXTENSIONS, natural_key
            from app.utils.ffmpeg import check_cancel
            from app.utils.rgba_image import read_rgba_with_format
            files = []
            for file in folder.iterdir():
                check_cancel(cancel)
                if file.is_file() and file.suffix.lower() in IMAGE_EXTENSIONS:
                    files.append(file)
            if not files:
                return revision, None
            files.sort(key=lambda file: natural_key(file.name))
            pixels, info = read_rgba_with_format(files[0])
            return revision, (len(files), sum(f.suffix.lower() == ".png" for f in files), pixels.shape, info.to_dict())
        worker = Worker(operation, self)
        self.worker = worker
        worker.result.connect(self._hint_result)
        worker.failed.connect(lambda error: self.hint.setText(translate_error(error)) if revision == self.hint_revision else None)
        worker.finished.connect(self._hint_finished)
        worker.start()

    def _hint_result(self, result):
        revision, data = result
        if revision != self.hint_revision:
            return
        if data is None:
            self.hint.setText(t("No sequence frames detected"))
            return
        count, png, shape, info = data
        self.hint.setText(t("Images: {count} · PNG: {png}\nFirst frame: {width} × {height} · {mode} · {bits}-bit/channel", count=count, png=png,
            width=shape[1], height=shape[0], mode=info["color_mode"], bits=info["bits_per_channel"]))

    def _hint_finished(self):
        worker, self.worker = self.worker, None
        if worker:
            worker.deleteLater()
        if self.hint_pending:
            self.hint_timer.start(0)

    def new_folder(self):
        if self.current_directory is None:return
        from app.core.project_workspace import validate_project_name
        name, ok = QInputDialog.getText(self, t("New folder"), t("Folder name"))
        if not ok:
            return
        try:
            validate_project_name(name)
            (self.current_directory / name).mkdir()
            self.navigate(self.current_directory / name)
        except (ValueError, OSError) as error:
            self.show_error(translate_error(str(error)))

    def select_folder(self):
        path = self.selection_path()
        if path is None or not path.is_dir():
            self.show_error(t("Folder path does not exist"))
            return
        self.selected_folder = str(path.resolve())
        self.accept()

    def done(self, result):
        self.hint_timer.stop()
        self.hint_pending = False
        if self.worker:
            self.worker.cancel()
            self.worker.wait()
        super().done(result)

    def closeEvent(self, event):
        self.hint_timer.stop()
        self.hint_pending = False
        if self.worker:
            self.worker.cancel()
            self.worker.wait()
        super().closeEvent(event)

    @classmethod
    def choose(cls, parent=None, title="Choose folder", path="", sequence=False):
        dialog = cls(parent, title, path, sequence)
        result = dialog.selected_folder if dialog.exec() == QDialog.DialogCode.Accepted else ""
        dialog.deleteLater()
        return result
