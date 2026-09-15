"""Source/frozen UI audit and true second-process path memory acceptance."""
from pathlib import Path
import json,logging,time,math
import cv2
import numpy as np
from PySide6.QtCore import QTimer,Qt
from PySide6.QtGui import QAction,QShortcut
from PySide6.QtWidgets import QAbstractButton,QPushButton,QDialog,QDialogButtonBox,QFileDialog,QColorDialog,QInputDialog,QMessageBox,QLineEdit
from PySide6.QtTest import QTest
from app.i18n import t,manager
from app.ui.dialogs import FileDialog,MessageBox
from app.ui.folder_picker import FolderPickerDialog
from app.ui.new_project_dialog import NewProjectDialog
from app.ui.character_reference_dialog import CharacterReferenceDialog
from app.ui.character_space_editor import CharacterSpaceEditor
from app.models.character_reference import CharacterReference
from app.models.project import Project
from app.utils.cache import save_rgba


def start_path_smoke(app,window,output,verify=False):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    log=logging.getLogger('aivsprite.path_smoke')
    state={'phase':'verify' if verify else 'new','started':time.monotonic()}
    audit={};dialogs=[];sizes=[];language=manager().language
    timer=QTimer(window);timer.setInterval(40)
    window._failed=lambda message:setattr(window,'last_error',message)
    original_create=FileDialog.create
    modal_task=None
    expected_file=output/'expected.json'
    if verify:
        expected=json.loads(expected_file.read_text(encoding='utf-8'))
        folders={key:Path(value) for key,value in expected['folders'].items()}
    else:
        folders={key:output/name for key,name in [('project','项目 工作区'),('video','视频 Assets A'),('sequence','透明 PNG B'),('export','导出 Sprite C'),('open','工程 Project D')]}
        for folder in folders.values():folder.mkdir()
        writer=cv2.VideoWriter(str(folders['video']/'Idle.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),24,(96,96));assert writer.isOpened()
        for i in range(3):
            frame=np.full((96,96,3),(0,255,0),np.uint8);cv2.rectangle(frame,(30+i,20),(55+i,75),(160,30,210),-1);writer.write(frame)
            rgba=np.zeros((96,96,4),np.uint8);rgba[20:75,30+i:55+i]=(210,30,160,255);save_rgba(folders['sequence']/f'{i:04d}.png',rgba)
        writer.release()

    def record(name,widget):
        rows=[]
        for button in widget.findChildren(QAbstractButton):
            if button.window()!=widget:continue
            rows.append(dict(type=type(button).__name__,text=button.text(),object=button.objectName(),
                tooltip=button.toolTip(),enabled=button.isEnabled(),auto_default=button.autoDefault() if isinstance(button,QPushButton) else False,
                connections=sum(button.receivers(signal) for signal in ('2clicked(bool)','2toggled(bool)','2pressed()'))))
        for action in widget.findChildren(QAction):
            if action.shortcut().toString() or action.text():rows.append(dict(type='QAction',text=action.text(),shortcut=action.shortcut().toString(),enabled=action.isEnabled(),connections=action.receivers('2triggered(bool)')))
        for shortcut in widget.findChildren(QShortcut):rows.append(dict(type='QShortcut',text=shortcut.key().toString(),enabled=shortcut.isEnabled(),connections=shortcut.receivers('2activated()')))
        audit[name]=rows

    def finish(code):
        timer.stop();FileDialog.create=original_create
        if window.worker:window.worker.cancel();window.worker.wait();app.processEvents()
        if window.new_project_dialog:window.new_project_dialog.reject()
        if window.sequence_dialog:window.sequence_dialog.reject()
        for review in list(window.review_windows):review.close()
        window.dirty=False;window.close();app.exit(code)

    def advance(phase):
        state.update(phase=phase,ready=time.monotonic())
        (output/'progress.txt').write_text(phase,encoding='utf-8')

    def choose_file(callback,purpose,target=None):
        expected_dir=window.path_memory.initial(purpose,window.project_file.parent if window.project_file else None)
        def create(*args,**kwargs):
            d=original_create(*args,**kwargs)
            assert Path(d.directory().absolutePath())==expected_dir
            assert d.testOption(QFileDialog.Option.DontUseNativeDialog)
            def choose():
                record('file_'+purpose,d)
                d.grab().save(str(output/('file-'+purpose+('-restart' if verify else '')+'.png')))
                dialogs.append(dict(purpose=purpose,initial=str(expected_dir),accepted=bool(target)))
                if target:
                    d.setDirectory(str(target.parent))
                    # QFileDialog.selectFile after show can defer to the filesystem model.
                    # Enter the visible filename as a user would, then activate Open/Save.
                    entry=d.findChild(QLineEdit,'fileNameEdit');assert entry is not None
                    entry.setText(target.name)
                    QTimer.singleShot(250,d.accept)
                else:QTest.keyClick(d,Qt.Key.Key_Escape)
            QTimer.singleShot(80,choose)
            return d
        FileDialog.create=create
        if purpose=='project_open' and window.dirty:
            def discard_test_edits():
                d=app.activeModalWidget();assert isinstance(d,QMessageBox)
                record('unsaved_confirmation',d)
                d.button(QMessageBox.StandardButton.Discard).click()
            QTimer.singleShot(80,discard_test_edits)
        try:callback()
        finally:FileDialog.create=original_create

    def choose_folder(callback,purpose,target=None):
        expected_dir=window.path_memory.initial(purpose,window.project_file.parent if window.project_file else None)
        def choose():
            try:
                d=app.activeModalWidget();assert isinstance(d,FolderPickerDialog)
                assert d.current_directory==expected_dir,(d.current_directory,expected_dir)
                record('folder_'+purpose,d);d.grab().save(str(output/('folder-'+purpose+('-restart' if verify else '')+'.png')))
                dialogs.append(dict(purpose=purpose,initial=str(expected_dir),accepted=bool(target)))
                if target:d.navigate(target);d.select_button.click()
                else:QTest.keyClick(d,Qt.Key.Key_Escape)
            except Exception:
                log.exception('Folder dialog acceptance failed');window.last_error='Folder acceptance failed'
                if app.activeModalWidget():app.activeModalWidget().reject()
        QTimer.singleShot(80,choose);callback()

    def footer_matrix(d):
        dpr=window.devicePixelRatioF()
        for width,height in ((1366,768),(1920,1080),(2560,1440)):
            wanted=(min(760,math.floor(width/dpr)-50),min(760,math.floor(height/dpr)-80))
            d.resize(*wanted);app.processEvents()
            assert d.height()<=wanted[1] and d.width()<=wanted[0]
            assert d.create_button.visibleRegion().contains(d.create_button.rect())
            assert d.cancel_button.visibleRegion().contains(d.cancel_button.rect())
            assert d.scroll_area.horizontalScrollBar().maximum()==0
            sizes.append(dict(screen=[width,height],dpr=dpr,dialog=[d.width(),d.height()],footer_visible=True))
            if width==1366:d.grab().save(str(output/('new-project-small'+('-restart' if verify else '')+'.png')))

    def other_windows():
        pixels=np.zeros((96,96,4),np.uint8);pixels[20:70,35:55]=(210,40,130,255)
        ref=CharacterReference(window.project.animation_id,0,48,75,96,96)
        d=CharacterReferenceDialog(ref,pixels,'Idle',parent=window);d.show();record('character_reference',d)
        assert all(not b.autoDefault() for b in d.findChildren(QPushButton));QTest.keyClick(d,Qt.Key.Key_Escape)
        from app.models.character_profile import CharacterProfile
        profile=Project.load(Path('examples/character_profile.aivsprite')).character_profile
        d=CharacterSpaceEditor(profile,pixels,parent=window);d.show();record('character_profile',d);QTest.keyClick(d,Qt.Key.Key_Escape)
        def close_modal(name,enter=False):
            def close():
                d=app.activeModalWidget();assert d is not None;record(name,d)
                (output/'modal-progress.txt').write_text(name+' '+d.windowTitle(),encoding='utf-8')
                QTest.keyClick(d,Qt.Key.Key_Return if enter else Qt.Key.Key_Escape)
            QTimer.singleShot(60,close)
        close_modal('diagnostics');window.show_diagnostics()
        close_modal('message_box',True)
        assert MessageBox.question(window,'New Project','Cancel',MessageBox.StandardButton.Yes|MessageBox.StandardButton.No,MessageBox.StandardButton.No)==MessageBox.StandardButton.No
        d=QColorDialog(window);d.show();record('color_dialog',d);QTest.keyClick(d,Qt.Key.Key_Escape);d.deleteLater()
        d=FolderPickerDialog(window,path=str(output));d.show()
        close_modal('new_folder');d.new_folder_button.click();d.reject()
        # Deep Unicode directory, beyond MAX_PATH, with a real RGBA sequence.
        deep=output
        while len(str(deep))<275:deep=deep/'长目录 LongFolder'
        deep.mkdir(parents=True);save_rgba(deep/'0000.png',pixels)
        d=FolderPickerDialog(window,path=str(deep),sequence=True);d.show();app.processEvents()
        assert d.current_directory==deep and d.path_edit.toolTip()==str(deep)
        assert not d.navigate('')
        record('deep_folder',d);d.reject()

    def poll():
        if state.get('polling'):return
        state['polling']=True
        try:
            if window.last_error:raise AssertionError(window.last_error)
            if time.monotonic()-state['started']>150:raise AssertionError('Path acceptance timed out')
            if window.worker or time.monotonic()-state.get('ready',0)<.2:return
            phase=state['phase'];p=window.project
            if phase=='new':
                assert window.path_memory.work_root.is_dir()
                assert not window.process_button.isEnabled() and not window.export_button.isEnabled()
                record('main_empty',window);window.new_project();advance('create')
            elif phase=='create':
                d=window.new_project_dialog;assert d and Path(d.directory.text())==window.path_memory.work_root
                footer_matrix(d);record('new_project',d)
                d.directory.setText(str(folders['project']));d.name.setText('MainCharacter');d.template.setCurrentIndex(0)
                assert str(folders['project']/'MainCharacter') in d.destination.toolTip()
                QTest.keyClick(d.name,Qt.Key.Key_Return);assert not (folders['project']/'MainCharacter').exists()
                d.create_button.click();advance('video')
            elif phase=='video':
                assert window.project_file==folders['project']/'MainCharacter/MainCharacter.aivsprite'
                choose_file(window.choose_video,'video_import',folders['video']/'Idle.mp4');advance('video_reopen')
            elif phase=='video_reopen':
                assert window.path_memory.initial('video_import')==folders['video']
                state['before_cancel']=window.path_memory.settings.path.read_bytes()
                choose_file(window.choose_video,'video_import')
                assert window.path_memory.settings.path.read_bytes()==state['before_cancel']
                choose_folder(window.choose_sequence,'image_sequence_import',folders['sequence']);advance('sequence_confirm')
            elif phase=='sequence_confirm':
                if not window.sequence_dialog:return
                record('sequence_import',window.sequence_dialog);window.sequence_dialog.submit();advance('sequence_ready')
            elif phase=='sequence_ready':
                if not window.built:return
                choose_folder(window.choose_sequence,'image_sequence_import')
                assert window.path_memory.initial('image_sequence_import')==folders['sequence']
                choose_folder(lambda:window.choose_export('sheet'),'sprite_sheet_export',folders['export']);advance('exported')
            elif phase=='exported':
                assert window.path_memory.initial('sprite_sheet_export')==folders['export']
                for d in list(window.export_notices):record('export_notice',d);d.close()
                choose_folder(lambda:window.choose_export('sheet'),'sprite_sheet_export')
                choose_file(window.choose_video,'video_import')
                target=folders['open']/'Player.aivsprite';state['project']=str(target)
                choose_file(window.save_project_as,'project_save',target);advance('saved')
            elif phase=='saved':
                choose_file(window.open_project,'project_open',Path(state['project']));advance('opened')
            elif phase=='opened':
                if not window.built:return
                choose_file(window.open_project,'project_open')
                assert window.path_memory.initial('project_create')==folders['project']
                other_windows()
                window.open_editor();advance('editor')
            elif phase=='editor':
                if not window.editor.provider or window.editor.worker or window.editor.pending:return
                record('main_ready',window)
                window.build_sprites();advance('review')
            elif phase=='review':
                if not window.built:return
                state['review']=window.open_animation_preview();advance('review_ready')
            elif phase=='review_ready':
                d=state['review']
                if d.worker or d.last_pixels is None:return
                record('animation_preview',d)
                assert all(not b.autoDefault() for b in d.findChildren(QPushButton))
                QTest.keyClick(d,Qt.Key.Key_Space);assert d.timer.isActive()
                QTest.keyClick(d,Qt.Key.Key_Space);assert not d.timer.isActive()
                d.mark_stale();QTest.keyClick(d,Qt.Key.Key_Space);assert not d.timer.isActive()
                d.close()
                # Language saves must merge, not erase persistent directories.
                manager().save_language('en_US');assert window.path_memory.initial('video_import')==folders['video']
                manager().save_language('zh_CN')
                saved_expected=dict(folders={key:str(value) for key,value in folders.items()},project=state['project'])
                expected_file.write_text(json.dumps(saved_expected,ensure_ascii=False,indent=2),encoding='utf-8')
                report=dict(status='passed',stage='exercise',language=language,dpr=window.devicePixelRatioF(),work_root=str(window.path_memory.work_root),
                    paths=window.path_memory.state,dialogs=dialogs,screen_matrix=sizes,ui_audit=audit,
                    buttons_actions=sum(len(v) for v in audit.values()),unicode_spaces=True,long_path=True)
                (output/'exercise.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
                log.info('Path/UI exercise passed: %s',output);finish(0)
            elif phase=='verify':
                # A fresh executable process constructs a new PathMemoryService from disk.
                assert window.path_memory.initial('project_create')==folders['project']
                assert window.path_memory.initial('video_import')==folders['video']
                assert window.path_memory.initial('image_sequence_import')==folders['sequence']
                assert window.path_memory.initial('sprite_sheet_export')==folders['export']
                assert window.path_memory.initial('project_open')==folders['open']
                window.new_project();d=window.new_project_dialog
                assert Path(d.directory.text())==folders['project'];footer_matrix(d);d.reject();advance('verify_dialogs')
            elif phase=='verify_dialogs':
                choose_file(window.choose_video,'video_import');choose_folder(window.choose_sequence,'image_sequence_import')
                choose_file(window.open_project,'project_open',Path(expected['project']));advance('verify_export')
            elif phase=='verify_export':
                if not window.built:return
                choose_folder(lambda:window.choose_export('sheet'),'sprite_sheet_export')
                choose_file(window.open_project,'project_open')
                record('restart_main',window)
                report=dict(status='passed',stage='fresh_process',dpr=window.devicePixelRatioF(),dialogs=dialogs,screen_matrix=sizes,independent_paths=True,new_project_parent_remembered=True)
                (output/'restart.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
                log.info('Path/UI restart passed: %s',output);finish(0)
        except Exception:
            log.exception('Path/UI acceptance failed in %s',state['phase']);finish(1)
        finally:state['polling']=False
    def watchdog():
        log.error('Path smoke watchdog: %s',state['phase'])
        d=app.activeModalWidget()
        if d:d.grab().save(str(output/'timeout-modal.png'));d.reject()
        finish(1)
    QTimer.singleShot(170000,watchdog)
    timer.timeout.connect(poll);timer.start();window._path_smoke_timer=timer
