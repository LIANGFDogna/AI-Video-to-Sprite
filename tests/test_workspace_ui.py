"""Native Qt event-loop tests: folder browsing, confirmation and empty projects."""
from pathlib import Path
import time
import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit

from app.i18n import t, manager
from app.ui.main_window import MainWindow, QMessageBox
from app.ui.folder_picker import FolderPickerDialog
from app.ui.sequence_import_dialog import SequenceImportDialog
from app.core.frame_sequence import scan_sequence
from app.core.project_workspace import create_project_workspace
from app.models.project import Project


@pytest.fixture(scope='module')
def qt():
    return QApplication.instance() or QApplication([])


def events(qt, condition=lambda: True, timeout=8):
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        qt.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        if condition():
            return
        time.sleep(.01)  # Let Python workers run; QTest.qWait can hold their GIL.
    raise AssertionError('Qt operation timed out')


def close_window(qt, window):
    if window.worker:
        window.worker.cancel()
        events(qt, lambda: window.worker is None)
    window.dirty = False
    window.close()
    window.deleteLater()
    events(qt)


@pytest.mark.parametrize('host_color', ['#ffffff', '#161d28'])
def test_folder_selection_history_path_and_double_click(qt, tmp_path, host_color):
    root = tmp_path / '中文目录'
    target = root / 'jump'
    target.mkdir(parents=True)
    sibling = root / 'run'
    sibling.mkdir()
    original_palette = qt.palette()
    light = QPalette(original_palette)
    light.setColor(QPalette.ColorRole.Base, QColor(host_color))
    light.setColor(QPalette.ColorRole.Text, QColor('#000000' if host_color == '#ffffff' else '#ffffff'))
    qt.setPalette(light)
    picker = FolderPickerDialog(path=str(root), sequence=True)
    picker.show()
    try:
        events(qt, lambda: picker.model.rowCount(picker.tree.rootIndex()) == 2)
        index = picker.model.index(str(target))
        rectangle = picker.tree.visualRect(index)
        QTest.mouseClick(picker.tree.viewport(), Qt.MouseButton.LeftButton, pos=rectangle.center())
        events(qt)
        assert picker.current_directory == root and picker.selection_path() == target
        assert picker.result() == QDialog.DialogCode.Rejected and picker.isVisible()
        assert picker.tree.palette().color(QPalette.ColorRole.Highlight).name() == '#287e71'
        assert picker.tree.palette().color(QPalette.ColorRole.HighlightedText).name() == '#ffffff'
        assert 'jump' in picker.current_label.text()
        QTest.mouseDClick(picker.tree.viewport(), Qt.MouseButton.LeftButton, pos=rectangle.center())
        events(qt, lambda: picker.current_directory == target)
        assert picker.isVisible() and not picker.selected_folder
        picker.back_button.click()
        assert picker.current_directory == root
        picker.forward_button.click()
        assert picker.current_directory == target
        picker.up_button.click()
        assert picker.current_directory == root
        picker.path_edit.setText(str(root / '不存在'))
        QTest.keyClick(picker.path_edit, Qt.Key.Key_Return)
        assert picker.error.isVisible() and picker.current_directory == root
        picker.path_edit.setText(str(target))
        QTest.keyClick(picker.path_edit, Qt.Key.Key_Return)
        assert picker.current_directory == target and not picker.error.isVisible()
        events(qt, lambda: picker.worker is None and not picker.hint_pending)
        assert picker.hint.text() == t('No sequence frames detected')
        picker.select_button.click()
        assert picker.selected_folder == str(target) and picker.result() == QDialog.DialogCode.Accepted
    finally:
        picker.reject()
        picker.deleteLater()
        events(qt)
        qt.setPalette(original_palette)


def test_new_project_ui_empty_home_save_reload_and_import_inherits(qt, tmp_path):
    window = MainWindow(tmp_path / 'app.log')
    window.show()
    try:
        assert window.views.currentWidget() is window.start_page
        window.new_button.click()
        dialog = window.new_project_dialog
        assert dialog is not None and not dialog.isModal()
        dialog.name.setText('Main:Character')
        dialog.directory.setText(str(tmp_path))
        dialog.create_button.click()
        events(qt, lambda: window.new_project_dialog is None)
        assert window.project.project_name == 'Main_Character'
        assert window.project_file.is_file() and not window.project.character_profile
        assert window.views.currentWidget() is window.start_page
        assert 'Main_Character' in window.project_status.text()
        assert t('Character reference: not established') in window.project_status.text()
        assert window.project.default_fps == 24 and window.project.source_canvas == (1536, 1536)
        window.project.default_fps = 12.5
        window.dirty = True
        window.save_project()
        events(qt, lambda: window.worker is None)
        path = window.project_file
        window.open_project(path)
        events(qt, lambda: window.worker is None)
        assert window.project.default_fps == 12.5 and window.views.currentWidget() is window.start_page
        folder = tmp_path / 'idle'
        folder.mkdir()
        source = np.full((32, 32, 4), (220, 50, 90, 128), np.uint8)
        Image.fromarray(source).save(folder / '0.png')
        project_id = window.project.project_id
        window.import_sequence(folder)
        events(qt, lambda: window.sequence_dialog is not None and window.worker is None)
        assert window.sequence_dialog.fps.value() == 12.5
        window.sequence_dialog.submit()
        events(qt, lambda: window.worker is None and window.built and window.sequence_dialog is None)
        assert window.project_file == path and window.project.project_id == project_id
        assert window.project.project_name == 'Main_Character' and not window.project.character_profile
        assert window.cache_dir.is_relative_to(path.parent / 'cache')
        assert window.project.layout.width == 1536  # Project canvas precedes passthrough.
        review = window.open_animation_preview()
        events(qt, lambda: review.last_pixels is not None and review.worker is None)
        expected = np.zeros((1536, 1536, 4), np.uint8)
        expected[752:784, 752:784] = source
        assert np.array_equal(review.last_pixels, expected)
        review.close()
    finally:
        close_window(qt, window)


@pytest.mark.parametrize('answer', ['Cancel', 'Discard', 'Save'])
def test_new_project_reuses_unsaved_confirmation(qt, tmp_path, monkeypatch, answer):
    window = MainWindow(tmp_path / 'app.log')
    calls = []
    window.project, window.project_file = create_project_workspace(tmp_path, 'Previous')
    window.project.default_fps = 30
    window.dirty = True
    def question(*args):
        calls.append(args)
        return getattr(QMessageBox.StandardButton, answer)
    monkeypatch.setattr(QMessageBox, 'question', question)
    try:
        window.new_project()
        if answer == 'Save':
            events(qt, lambda: window.worker is None and window.new_project_dialog is not None)
            assert Project.load(window.project_file).default_fps == 30
        assert len(calls) == 1
        assert calls[0][2] == 'The project has unsaved changes. Save before continuing?'
        assert (window.new_project_dialog is None) == (answer == 'Cancel')
        if window.new_project_dialog:
            window.new_project_dialog.close()
            events(qt, lambda: window.new_project_dialog is None)
    finally:
        close_window(qt, window)


def test_rgb_import_dialog_warns_and_distinguishes_total_bits(qt, tmp_path):
    Image.new('RGB', (8, 8), (10, 30, 50)).save(tmp_path / '0.png')
    dialog = SequenceImportDialog(scan_sequence(tmp_path))
    dialog.show()
    try:
        events(qt)
        assert '8-bit/channel' in dialog.format_info.text()
        assert '24' in dialog.format_info.text() and '24-bit/channel' not in dialog.format_info.text()
        assert dialog.alpha_warning.isVisible() and '#f2cf75' in dialog.alpha_warning.styleSheet()
        assert dialog.import_button.isEnabled()
    finally:
        dialog.close()
        events(qt)
