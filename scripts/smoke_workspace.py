"""Real Qt screenshots and interactions for project creation and directory browsing."""
import argparse
import json
from pathlib import Path
import time
import numpy as np
from PySide6.QtCore import QCoreApplication, QEvent, QPointF, Qt
from PySide6.QtGui import QColor, QPalette, QHoverEvent, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.core.frame_sequence import scan_sequence
from app.i18n import manager, t
from app.ui.folder_picker import FolderPickerDialog
from app.ui.main_window import MainWindow
from app.ui.sequence_import_dialog import SequenceImportDialog
from app.utils.cache import save_rgba


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--host-palette', choices=['light', 'dark'], default='dark')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    manager().set_language('zh_CN')
    palette = app.palette()
    for role in (QPalette.ColorRole.Window, QPalette.ColorRole.Base, QPalette.ColorRole.Button):
        palette.setColor(role, QColor('#ffffff' if args.host_palette == 'light' else '#161d28'))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        palette.setColor(role, QColor('#000000' if args.host_palette == 'light' else '#ffffff'))
    app.setPalette(palette)
    def wait(condition=lambda: True, timeout=15):
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            if condition():
                return
            time.sleep(.01)
        raise AssertionError('Qt validation timed out')
    root = args.output / '中文角色动画'
    for name in ('idle', 'jump', 'run', 'attack'):
        (root / name).mkdir(parents=True, exist_ok=True)
    native = np.zeros((120, 120, 4), np.uint16)
    native[20:110, 40:85] = (50000, 12000, 20000, 38000)
    for i in range(4):
        save_rgba(root / 'jump' / f'{i:04d}.png', native)
    picker = FolderPickerDialog(path=str(root), sequence=True)
    picker.show()
    wait(lambda: picker.model.rowCount(picker.tree.rootIndex()) == 4)
    index = picker.model.index(str((root / 'jump').resolve()))
    rect = picker.tree.visualRect(index)
    QTest.mouseClick(picker.tree.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    wait(lambda: not picker.worker and not picker.hint_pending)
    assert picker.current_directory == root.resolve() and picker.selection_path().name == 'jump'
    hover = picker.tree.visualRect(picker.model.index(str((root / 'run').resolve())))
    QTest.mouseMove(picker.tree.viewport(), hover.center())
    local = QPointF(hover.center())
    QCoreApplication.sendEvent(picker.tree.viewport(), QMouseEvent(QEvent.Type.MouseMove, local, local,
        Qt.MouseButton.NoButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier))
    QCoreApplication.sendEvent(picker.tree.viewport(), QHoverEvent(QEvent.Type.HoverMove, local, local, local))
    wait()
    hover_color = picker.tree.viewport().grab(hover.adjusted(3, 3, -3, -3)).toImage().pixelColor(2, 2).name()
    assert hover_color == '#34485f', hover_color
    picker.grab().save(str(args.output / 'folder-selected-hover.png'))
    QTest.mouseDClick(picker.tree.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    wait(lambda: picker.current_directory.name == 'jump')
    picker.back_button.click()
    assert picker.forward_button.isEnabled()
    picker.grab().save(str(args.output / 'folder-history.png'))
    picker.forward_button.click()
    long_path = root / ('超长中文路径用于检查路径栏文字与光标可读性' * 3) / ('角色动作与最终帧' * 12) / ('目录与最终序列帧' * 7)
    long_path.mkdir(parents=True, exist_ok=True)
    picker.path_edit.setText(str(long_path.resolve()))
    QTest.keyClick(picker.path_edit, Qt.Key.Key_Return)
    wait(lambda: picker.current_directory == long_path.resolve())
    assert picker.path_edit.text() == str(long_path.resolve())
    picker.grab().save(str(args.output / 'folder-long-path.png'))
    picker.select_button.click()
    assert picker.selected_folder == str(long_path.resolve())
    picker.deleteLater()
    wait()
    formats = scan_sequence(root / 'jump')
    dialog = SequenceImportDialog(formats)
    from app.ui.theme import STYLE
    dialog.setStyleSheet(STYLE + dialog.styleSheet())
    dialog.show()
    wait()
    assert '16-bit/channel' in dialog.format_info.text() and '8-bit/channel' in dialog.format_info.text()
    dialog.grab().save(str(args.output / 'rgba16-import.png'))
    dialog.close()
    wait()
    window = MainWindow(args.output / 'app.log')
    window.resize(1440, 850)
    window.show()
    wait()
    window.grab().save(str(args.output / 'start-page.png'))
    window.new_button.click()
    wait(lambda: window.new_project_dialog is not None)
    create = window.new_project_dialog
    create.name.setText('MainCharacter')
    create.directory.setText(str(args.output.resolve()))
    wait()
    create.grab().save(str(args.output / 'new-project.png'))
    create.create_button.click()
    wait(lambda: window.new_project_dialog is None)
    assert window.project_file.is_file() and not window.project.character_profile
    assert window.project.scale == 1 / 3 and not window.project.root_keyframes
    assert window.views.currentWidget() is window.start_page
    window.grab().save(str(args.output / 'empty-project.png'))
    window.close()
    wait()
    report = dict(host_palette=args.host_palette, dpr=app.devicePixelRatio(), unicode=True,
        folder_single_select=True, double_click_navigates=True, history=True, long_path_length=len(str(long_path.resolve())),
        selection_color='#287e71', hover_color=hover_color, rgba16_disclosed=True, empty_project_created=True, no_automatic_root=True)
    (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
