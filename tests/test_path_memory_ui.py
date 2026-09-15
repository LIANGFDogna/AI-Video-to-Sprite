from pathlib import Path
import json
import numpy as np
from PIL import Image
import pytest
from PySide6.QtCore import QTimer,Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QDialog,QFileDialog as QtFileDialog
from PySide6.QtTest import QTest
from app.ui.main_window import MainWindow
from app.ui.dialogs import FileDialog
from app.ui.new_project_dialog import NewProjectDialog
from app.ui.folder_picker import FolderPickerDialog
from app.core.project_workspace import create_project_workspace
from app.models.project import Project
from app.i18n import t
from test_workspace_ui import qt,events,close_window


def test_new_project_default_remember_cancel_and_existing_open(qt,tmp_path):
    w=MainWindow(tmp_path/'app.log');w.show()
    parent=tmp_path/'Custom Projects';parent.mkdir()
    try:
        w.path_memory.remember('video_import',tmp_path)
        w.new_project();d=w.new_project_dialog
        assert Path(d.directory.text())==tmp_path/'work' and not d.directory.isReadOnly()
        d.directory.setText(str(parent));d.name.setText('Hero')
        assert str(parent/'Hero') in d.destination.text() and d.destination.toolTip()==str(parent/'Hero')
        QTest.keyClick(d.name,Qt.Key.Key_Return)
        assert not (parent/'Hero').exists()
        QTest.keyClick(d,Qt.Key.Key_Escape);events(qt,lambda:w.new_project_dialog is None)
        assert 'project_create' not in w.path_memory.state.get('recent_paths',{})
        w.new_project();d=w.new_project_dialog;d.directory.setText(str(parent));d.name.setText('Hero');d.create_button.click()
        events(qt,lambda:w.new_project_dialog is None)
        path=parent/'Hero/Hero.aivsprite';assert w.project_file==path
        assert w.path_memory.initial('project_create')==parent
        w.new_project();d=w.new_project_dialog
        assert Path(d.directory.text())==parent
        d.name.setText('Hero');d.create_button.click()
        assert d.open_existing_button.isVisible() and d.rename_button.isVisible()
        previous=path.read_bytes();d.open_existing_button.click()
        events(qt,lambda:not w.worker and w.new_project_dialog is None)
        assert w.project_file==path and path.read_bytes()==previous
    finally:close_window(qt,w)


@pytest.mark.parametrize('width,height',[(870,450),(1024,600),(1280,660)])
def test_new_project_small_screen_scroll_and_footer(qt,tmp_path,width,height):
    d=NewProjectDialog(initial_directory=str(tmp_path));d.resize(width,height);d.show()
    try:
        events(qt)
        assert d.create_button.visibleRegion().contains(d.create_button.rect())
        assert d.cancel_button.visibleRegion().contains(d.cancel_button.rect())
        assert d.height()<=height
        if height==450:assert d.scroll_area.verticalScrollBar().maximum()>0
        d.scroll_area.ensureWidgetVisible(d.directory)
        assert d.directory.isVisible() and d.browse_button.isEnabled()
    finally:d.reject();events(qt)


def test_file_picker_purpose_sidebar_cancel_and_save_filename(qt,tmp_path,monkeypatch):
    w=MainWindow(tmp_path/'app.log');a=tmp_path/'视频 A';a.mkdir();b=tmp_path/'输出 B';b.mkdir()
    w.project,w.project_file=create_project_workspace(tmp_path,'Hero')
    w.path_memory.remember('video_import',a);w.path_memory.remember('sprite_sheet_export',b)
    before=w.path_memory.settings.path.read_bytes()
    try:
        d=FileDialog.create(w,'Import Video',purpose='video_import');d.show();events(qt)
        assert d.testOption(QtFileDialog.Option.DontUseNativeDialog)
        assert Path(d.directory().absolutePath())==a
        urls=[u.toLocalFile() for u in d.sidebarUrls()]
        assert str(w.project_file.parent).replace('\\','/') in [u.replace('\\','/') for u in urls]
        assert str(b).replace('\\','/') in [u.replace('\\','/') for u in urls]
        QTest.keyClick(d,Qt.Key.Key_Escape);assert d.result()==QDialog.DialogCode.Rejected;d.deleteLater();events(qt)
        real_create=FileDialog.create
        def cancelled(*args,**kwargs):
            dialog=real_create(*args,**kwargs);QTimer.singleShot(0,dialog.reject);return dialog
        monkeypatch.setattr(FileDialog,'create',cancelled)
        assert FileDialog.getOpenFileName(w,'Import Video',purpose='video_import')[0]==''
        assert w.path_memory.settings.path.read_bytes()==before
        d=real_create(w,'Save Project As','Hero.aivsprite',save=True,purpose='project_save')
        assert Path(d.selectedFiles()[0]).name=='Hero.aivsprite'
        from PySide6.QtWidgets import QToolButton
        for name in ('backButton','forwardButton','toParentButton','newFolderButton'):
            button=d.findChild(QToolButton,name)
            assert button and button.minimumWidth()>=button.fontMetrics().horizontalAdvance(button.text())
        assert len(d.sidebarUrls())<=5
        d.deleteLater();events(qt)
        picker=FolderPickerDialog(w,path=str(b));picker.show();events(qt)
        data={picker.sidebar.item(i).text():picker.sidebar.item(i).data(Qt.ItemDataRole.UserRole) for i in range(picker.sidebar.count())}
        assert Path(data[t('Current Project')])==w.project_file.parent
        picker._shortcut_selected(picker.sidebar.item(picker.sidebar.count()-1))
        assert not picker.select_button.isEnabled()
        picker._shortcut_selected(picker.sidebar.item(0));assert picker.new_folder_button.isEnabled()
        picker.reject();events(qt)
    finally:close_window(qt,w)


def test_success_sequence_export_save_as_and_failure_do_not_pollute(qt,tmp_path,monkeypatch):
    w=MainWindow(tmp_path/'app.log');w.show()
    folder=tmp_path/'中文 素材/Idle';folder.mkdir(parents=True)
    Image.fromarray(np.full((24,24,4),(100,70,20,128),np.uint8)).save(folder/'0.png')
    try:
        w._failed=lambda error:setattr(w,'last_error',error)
        w.import_sequence(folder);events(qt,lambda:w.sequence_dialog is not None and not w.worker)
        assert 'image_sequence_import' not in w.path_memory.state.get('recent_paths',{})
        w.sequence_dialog.reject();events(qt,lambda:w.sequence_dialog is None)
        assert not w.path_memory.settings.path.exists()
        w.import_sequence(folder);events(qt,lambda:w.sequence_dialog is not None and not w.worker);w.sequence_dialog.submit()
        events(qt,lambda:not w.worker and w.built and w.sequence_dialog is None)
        assert w.path_memory.initial('image_sequence_import')==folder
        output=tmp_path/'中文 Export';output.mkdir();w.export_to(output/'Sheet',kind='sheet')
        events(qt,lambda:not w.worker)
        assert w.path_memory.initial('sprite_sheet_export')==output
        before=w.path_memory.settings.path.read_bytes()
        w.export_to(output/'Sheet',kind='sheet');events(qt,lambda:not w.worker)
        assert w.last_error and w.path_memory.settings.path.read_bytes()==before
        dest=tmp_path/'工程 路径/另存.aivsprite';dest.parent.mkdir()
        monkeypatch.setattr(FileDialog,'getSaveFileName',lambda *a,**kw:(str(dest),''))
        w.save_project_as();events(qt,lambda:not w.worker)
        assert w.project_file==dest and w.path_memory.initial('project_save')==dest.parent
        assert Project.load(dest).video.frame_count==1
        w.dirty=False;w.open_project(dest);events(qt,lambda:not w.worker)
        assert w.path_memory.initial('project_open')==dest.parent
        assert w.path_memory.initial('image_sequence_import')==folder
    finally:close_window(qt,w)


def test_disabled_shortcuts_and_empty_controls(qt,tmp_path,monkeypatch):
    w=MainWindow(tmp_path/'app.log');w.show()
    try:
        assert not w.process_button.isEnabled() and not w.build_button.isEnabled() and not w.export_button.isEnabled()
        w.new_project();events(qt)
        assert all(not action.isEnabled() for action,button in w.file_shortcuts)
        called=[];monkeypatch.setattr(FileDialog,'getOpenFileName',lambda *a,**kw:called.append(1) or ('',''))
        w.choose_video();assert not called
        w.undo_edit();w.redo_edit();assert w.new_project_dialog
        w.new_project_dialog.reject();events(qt,lambda:w.new_project_dialog is None)
        assert all(action.isEnabled() for action,button in w.file_shortcuts)
    finally:close_window(qt,w)
