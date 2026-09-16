import sys
from PySide6.QtWidgets import QMessageBox as QtMessageBox, QFileDialog as QtFileDialog
from pathlib import Path
from PySide6.QtCore import QProcess, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QPushButton, QToolButton, QSplitter, QListView, QComboBox
from PySide6.QtGui import QIcon
from app.i18n import t, manager
from app.utils.path_memory import PathMemoryService
from app.ui.theme import STYLE


class MessageBox:
    StandardButton = QtMessageBox.StandardButton

    @staticmethod
    def _show(icon, parent, title, text, buttons=None, default=None):
        buttons = buttons or QtMessageBox.StandardButton.Ok
        box = QtMessageBox(icon, t(title), t(text), buttons, parent)
        for kind, label in ((QtMessageBox.StandardButton.Save, "Save"), (QtMessageBox.StandardButton.Discard, "Don't Save"),
                (QtMessageBox.StandardButton.Cancel, "Cancel"), (QtMessageBox.StandardButton.Yes, "Yes"),
                (QtMessageBox.StandardButton.No, "No"), (QtMessageBox.StandardButton.Ok, "OK")):
            button = box.button(kind)
            if button:
                button.setText(t(label))
        if default:
            box.setDefaultButton(default)
        elif buttons & QtMessageBox.StandardButton.Cancel:box.setDefaultButton(QtMessageBox.StandardButton.Cancel)
        elif buttons & QtMessageBox.StandardButton.No:box.setDefaultButton(QtMessageBox.StandardButton.No)
        return QtMessageBox.StandardButton(box.exec())

    @staticmethod
    def question(parent, title, text, buttons=None, default=None):
        return MessageBox._show(QtMessageBox.Icon.Question, parent, title, text, buttons, default)

    @staticmethod
    def warning(parent, title, text, buttons=None, default=None):
        return MessageBox._show(QtMessageBox.Icon.Warning, parent, title, text, buttons, default)

    @staticmethod
    def critical(parent, title, text, buttons=None, default=None):
        return MessageBox._show(QtMessageBox.Icon.Critical, parent, title, text, buttons, default)

    @staticmethod
    def information(parent, title, text, buttons=None, default=None):
        return MessageBox._show(QtMessageBox.Icon.Information, parent, title, text, buttons, default)

    @staticmethod
    def choice(parent, title, text, options, default=0):
        """Ask with custom labels; the last option is the cancel role. Returns the index or -1."""
        box = QtMessageBox(QtMessageBox.Icon.Question, t(title), t(text), QtMessageBox.StandardButton.NoButton, parent)
        buttons = []
        for index, label in enumerate(options):
            role = QtMessageBox.ButtonRole.RejectRole if index == len(options) - 1 else QtMessageBox.ButtonRole.AcceptRole
            buttons.append(box.addButton(t(label), role))
        box.setDefaultButton(buttons[min(max(default, 0), len(buttons) - 1)])
        box.exec()
        clicked = box.clickedButton()
        return buttons.index(clicked) if clicked in buttons else -1


def reveal_in_explorer(path):
    """Open the OS file manager at a Project Library resource without touching the file."""
    target = Path(path)
    if not target.exists():
        return False
    if sys.platform.startswith("win"):
        if target.is_dir():
            QProcess.startDetached("explorer", [str(target)])
        else:
            QProcess.startDetached("explorer", ["/select," + str(target)])
        return True
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(target if target.is_dir() else target.parent)))


def path_context(parent=None):
    current=parent
    while current is not None:
        if hasattr(current,'path_memory'):
            project=getattr(current,'project_file',None)
            return current.path_memory,project.parent if project else None
        current=current.parent() if hasattr(current,'parent') else None
    return PathMemoryService(manager().settings_path),None


class FileDialog:
    @staticmethod
    def create(parent,title,path="",filter="",save=False,purpose=None,multiple=False):
        memory,project=path_context(parent)
        purpose=purpose or ('generic_save' if save else 'generic_open')
        directory=memory.initial(purpose,project)
        dialog=QtFileDialog(parent,t(title),str(directory),t(filter))
        dialog.setOption(QtFileDialog.Option.DontUseNativeDialog,True)
        dialog.setStyleSheet(STYLE)
        dialog.setAcceptMode(QtFileDialog.AcceptMode.AcceptSave if save else QtFileDialog.AcceptMode.AcceptOpen)
        dialog.setFileMode(QtFileDialog.FileMode.AnyFile if save else QtFileDialog.FileMode.ExistingFiles if multiple else QtFileDialog.FileMode.ExistingFile)
        if save and path:dialog.selectFile(Path(path).name)
        # Qt restores its own sidebar from prior dialogs; keep only built-in roots.
        # App dynamic shortcuts must be rebuilt, not accumulated on every opening.
        defaults=[url for url in dialog.sidebarUrls() if not url.toLocalFile() or Path(url.toLocalFile())==Path.home()]
        computer=QUrl('file:')
        if computer not in defaults:defaults.append(computer)
        urls=[]
        for _,folder in memory.shortcuts(project):
            url=QUrl.fromLocalFile(str(folder))
            if url not in urls:urls.append(url)
        dialog.setSidebarUrls(urls+[url for url in defaults if url not in urls])
        for role,label in ((QtFileDialog.DialogLabel.LookIn,"Look in"),(QtFileDialog.DialogLabel.FileName,"File name"),
                (QtFileDialog.DialogLabel.FileType,"File type"),(QtFileDialog.DialogLabel.Accept,"Save" if save else "Open"),
                (QtFileDialog.DialogLabel.Reject,"Cancel")):
            dialog.setLabelText(role,t(label))
        # Text navigation remains legible with either Windows host palette.
        for name,label in (("backButton","← Back"),("forwardButton","→ Forward"),
                ("toParentButton","↑ Parent folder"),("newFolderButton","New folder")):
            button=dialog.findChild(QToolButton,name)
            if button:
                button.setIcon(QIcon());button.setText(t(label));button.setToolTip(t(label))
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
                button.setFixedWidth(button.fontMetrics().horizontalAdvance(t(label))+24)
        for button in dialog.findChildren(QToolButton):
            if button.objectName() in ("listModeButton","detailModeButton"):button.hide()
        sidebar=dialog.findChild(QListView,"sidebar")
        if sidebar:sidebar.setMinimumWidth(150)
        splitter=dialog.findChild(QSplitter)
        if splitter:splitter.setSizes([180,660])
        screen=dialog.screen().availableGeometry()
        dialog.resize(min(1000,screen.width()-50),min(650,screen.height()-80))
        location=dialog.findChild(QComboBox,'lookInCombo')
        if location:
            location.setToolTip(str(directory))
            dialog.directoryEntered.connect(location.setToolTip)
        dialog.setProperty('pathPurpose',purpose)
        return dialog

    @staticmethod
    def _dialog(parent,title,path="",filter="",save=False,purpose=None,multiple=False):
        dialog=FileDialog.create(parent,title,path,filter,save,purpose,multiple)
        selected=[];selected_filter=""
        if dialog.exec():selected=dialog.selectedFiles();selected_filter=dialog.selectedNameFilter()
        if selected and (purpose is None or purpose=='generic_open') and not save:
            path_context(parent)[0].remember(purpose or 'generic_open',selected[0],file=True)
        dialog.deleteLater()
        return (selected if multiple else selected[0] if selected else ""),selected_filter

    @staticmethod
    def getOpenFileName(parent,title,path="",filter="",*,purpose=None):
        return FileDialog._dialog(parent,title,path,filter,purpose=purpose)

    @staticmethod
    def getOpenFileNames(parent,title,path="",filter="",*,purpose=None):
        return FileDialog._dialog(parent,title,path,filter,purpose=purpose,multiple=True)

    @staticmethod
    def getSaveFileName(parent,title,path="",filter="",*,purpose=None):
        return FileDialog._dialog(parent,title,path,filter,save=True,purpose=purpose)

    @staticmethod
    def getExistingDirectory(parent,title,path="",sequence=False,*,purpose=None):
        from app.ui.folder_picker import FolderPickerDialog
        memory,project=path_context(parent)
        purpose=purpose or 'generic_folder'
        directory=path if purpose=='project_create' and path else str(memory.initial(purpose,project))
        result=FolderPickerDialog.choose(parent,title,directory,sequence)
        if result and purpose=='generic_folder':memory.remember(purpose,result)
        return result
