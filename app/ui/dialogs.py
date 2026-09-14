from PySide6.QtWidgets import QMessageBox as QtMessageBox, QFileDialog as QtFileDialog
from app.i18n import t


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


class FileDialog:
    @staticmethod
    def _dialog(parent, title, path="", filter="", save=False, directory=False):
        dialog = QtFileDialog(parent, t(title), path, t(filter))
        dialog.setOption(QtFileDialog.Option.DontUseNativeDialog, True)
        dialog.setAcceptMode(QtFileDialog.AcceptMode.AcceptSave if save else QtFileDialog.AcceptMode.AcceptOpen)
        dialog.setFileMode(QtFileDialog.FileMode.Directory if directory else (QtFileDialog.FileMode.AnyFile if save else QtFileDialog.FileMode.ExistingFile))
        for role, label in ((QtFileDialog.DialogLabel.LookIn, "Look in"), (QtFileDialog.DialogLabel.FileName, "File name"),
                (QtFileDialog.DialogLabel.FileType, "File type"), (QtFileDialog.DialogLabel.Accept, "Save" if save else "Open"),
                (QtFileDialog.DialogLabel.Reject, "Cancel")):
            dialog.setLabelText(role, t(label))
        if dialog.exec():
            return dialog.selectedFiles()[0], dialog.selectedNameFilter()
        return "", ""

    @staticmethod
    def getOpenFileName(parent, title, path="", filter=""):
        return FileDialog._dialog(parent, title, path, filter)

    @staticmethod
    def getSaveFileName(parent, title, path="", filter=""):
        return FileDialog._dialog(parent, title, path, filter, save=True)

    @staticmethod
    def getExistingDirectory(parent, title, path="", sequence=False):
        from app.ui.folder_picker import FolderPickerDialog
        return FolderPickerDialog.choose(parent, title, path, sequence)
