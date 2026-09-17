import copy
import json
from threading import Event
import numpy as np
from PIL import Image
from app.core.pipeline import Pipeline
from app.core.project_workspace import create_project_workspace
from app.core.final_frame_provider import FinalFrameProvider
from app.utils.paths import cache_directory
from app.ui.main_window import MainWindow
from app.ui.group_export_dialog import GroupExportDialog
from app.ui.dialogs import FileDialog
from PySide6.QtCore import Qt,QMimeData,QUrl,QPointF
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QAbstractItemView
from app.ui.project_library import MIME
from test_workspace_ui import qt,events,close_window


def window(qt,tmp_path):
    w=MainWindow(tmp_path/'ui.log');w._failed=lambda error:setattr(w,'last_error',error)
    w.project,w.project_file=create_project_workspace(tmp_path,'中文项目','standard',project_canvas=(32,32))
    w._loaded();w.show();return w


def cached_clip(w,group,name,count=5,generated=True):
    folder=w.project_file.parent/'sequences'/name;folder.mkdir(parents=True,exist_ok=True)
    for i in range(count):
        rgba=np.zeros((32,32,4),np.uint8);rgba[8+i:15+i,5+i:13+i]=(160,70,90,180);Image.fromarray(rgba).save(folder/f'{i}.png')
    w.library_controller.select_group(group)
    p=w.project.import_frame_sequence(folder)
    directory=cache_directory(p.project_id,w.project_file,p.animation_id)
    pipe=Pipeline(p,directory);pipe.import_sequence();p.timeline_edit.initialize(count,24)
    pipe.build()
    if generated:p.library.mark_generated(p.animation_id)
    w.project=p;w.cache_dir=directory;w.built=True;w._loaded();return p.animation_id


def test_no_group_import_guards_and_single_add_entry(qt,tmp_path,monkeypatch):
    w=MainWindow(tmp_path/'ui.log');w.show();calls=[]
    monkeypatch.setattr(FileDialog,'getOpenFileName',lambda *a,**k:calls.append('file'))
    monkeypatch.setattr(FileDialog,'getExistingDirectory',lambda *a,**k:calls.append('folder'))
    try:
        assert not w.import_button.isEnabled() and not w.import_sequence_button.isEnabled()
        w.choose_video();w.choose_sequence();w.library_controller.choose_sheet();w.import_video(tmp_path/'no.mp4');w.import_sequence(tmp_path)
        assert not calls and not w.worker
        w.project,w.project_file=create_project_workspace(tmp_path,'Hero');w._loaded()
        assert not w.project.library.groups and not w.import_button.isEnabled()
        g=w.library_controller.new_group(name='Idle')
        assert g and w.project.current_group_id==g.id and w.import_button.isEnabled()
        assert not w.new_button.isVisible() and not w.import_button.isVisible() and not w.export_button.isVisible()
        assert w.library_panel.add_button.isVisible()
        w.library_controller.select_group(None);assert not w.import_button.isEnabled()
        data=QMimeData();data.setUrls([QUrl.fromLocalFile(str(tmp_path))])
        event=QDropEvent(QPointF(3,3),Qt.DropAction.CopyAction,data,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        w.dropEvent(event);assert not event.isAccepted() and not w.worker
    finally:close_window(qt,w)


def test_multiple_sources_sheet_tree_search_move_and_undo(qt,tmp_path):
    w=window(qt,tmp_path)
    try:
        c=w.library_controller;idle=c.new_group(name='Idle');a=cached_clip(w,idle.id,'a');b=cached_clip(w,idle.id,'b')
        path=tmp_path/'sheet.png';Image.new('RGBA',(64,32),(200,90,30,128)).save(path);c.import_sheet(path)
        assert len(w.project.library.in_group(idle.id))==7 and w.project.library.animation_count(idle.id)==2
        assert w.views.currentWidget() is w.asset_view
        run=c.new_group(name='Run');c.move('RESOURCE',w.project.library.animation(b).id,run.id)
        assert w.project.library.animation(b).group_id==run.id
        c.rename('GROUP',run.id,'Run / Dash');w.undo_edit();assert w.project.library.groups[run.id].name=='Run'
        w.redo_edit();assert w.project.library.groups[run.id].name=='Run / Dash'
        c.move('GROUP',run.id,idle.id);assert w.project.library.animation_count(idle.id)==2
        c.remove_group(run.id,confirmed=True);assert run.id not in w.project.library.groups and w.project.library.animation(b).group_id==idle.id
        w.undo_edit();assert w.project.library.animation(b).group_id==run.id and path.is_file()
        w.library_panel.search.setText('Dash');assert not w.library_panel.items[('GROUP',run.id)].isHidden()
        source=w.project.library.resources[w.project.library.animation(a).source_id]
        w.library_panel.search.clear();c.activate('RESOURCE',source.id)
        assert w.views.currentWidget() is w.asset_info and source.path in w.asset_info.toPlainText()
    finally:close_window(qt,w)


def test_group_switch_restores_frame_zoom_tabs_and_never_processes(qt,tmp_path,monkeypatch):
    w=window(qt,tmp_path)
    try:
        c=w.library_controller;idle=c.new_group(name='Idle');a=cached_clip(w,idle.id,'Idle')
        run=c.new_group(name='Run');b=cached_clip(w,run.id,'Run')
        def forbidden(*a,**k):raise AssertionError('Selection must never process source pixels')
        for method in ('import_input','import_video','import_sequence','ensure_key','ensure_roots','ensure_motion','ensure_aligned','build'):
            if hasattr(Pipeline,method):monkeypatch.setattr(Pipeline,method,forbidden)
        c.select_animation(a);w.steps.blockSignals(True);w.steps.setCurrentIndex(2);w.steps.blockSignals(False)
        c.restoring=True;w._stage_changed(2);c.restoring=False
        w.editor.select(3);w.editor.timeline.pixels_per_second=1400;w.editor.onion.setChecked(True);w.editor.preview_fps.setValue(12)
        c.select_animation(b);w.editor.inspector.setCurrentIndex(1);w.select_frame(2);w.editor.timeline.pixels_per_second=480
        c.select_group(idle.id);events(qt,lambda:not w.editor.worker)
        assert w.project.animation_id==a and w.editor.index==3 and w.editor.timeline.pixels_per_second==1400
        assert w.editor.onion.isChecked() and w.editor.preview_fps.value()==12 and w.editor.inspector.currentIndex()==0
        c.select_group(run.id);assert w.project.animation_id==b and w.current_frame==2 and w.editor.inspector.currentIndex()==1
        assert w.editor.timeline.pixels_per_second==480 and not w.worker and w.last_error is None
        c.select_group(None);assert not w.project.source_path and not w.project.current_group_id
        c.select_group(idle.id);assert w.project.animation_id==a
    finally:close_window(qt,w)


def test_background_result_updates_owner_without_switching_current(qt,tmp_path):
    w=window(qt,tmp_path);release=Event()
    try:
        c=w.library_controller;idle=c.new_group(name='Idle');a=cached_clip(w,idle.id,'Idle')
        run=c.new_group(name='Run');b=cached_clip(w,run.id,'Run')
        result=copy.deepcopy(w.project);result.root_keyframes[0]=(4,7);called=[]
        def operation(progress,cancel):release.wait(5);return result
        w._run(operation,lambda p:called.append(p.animation_id),'Test Key',animation_task='key')
        assert w.task_context.animation_id==b and w.task_context.group_id==run.id
        c.select_group(idle.id)
        assert w.project.animation_id==a and w.project.library.groups[run.id].status=='PROCESSING'
        release.set();events(qt,lambda:not w.worker)
        assert not called and w.project.animation_id==a and w.project.current_group_id==idle.id
        assert not w.project.root_keyframes and w.project.select_animation(b).root_keyframes[0]==(4,7)
        assert w.project.library.groups[run.id].status=='READY'
    finally:release.set();close_window(qt,w)


def test_save_restart_restores_group_workspace_without_decode(qt,tmp_path,monkeypatch):
    w=window(qt,tmp_path)
    try:
        c=w.library_controller;idle=c.new_group(name='Idle');a=cached_clip(w,idle.id,'Idle')
        run=c.new_group(name='Run');b=cached_clip(w,run.id,'Run')
        c.select_animation(a);w.select_frame(3);w.editor.timeline.pixels_per_second=1600
        w.save_project();events(qt,lambda:not w.worker)
        path=w.project_file;before=FinalFrameProvider(w.project,w.cache_dir).get_final_frame(2).copy()
        def forbidden(*a,**k):raise AssertionError('Reopening must not decode or rebuild')
        for method in ('import_input','ensure_key','ensure_aligned','build'):monkeypatch.setattr(Pipeline,method,forbidden)
        w.open_project(path)
        assert w.project.current_group_id==idle.id and w.project.animation_id==a and w.current_frame==3
        assert w.editor.timeline.pixels_per_second==1600
        assert np.array_equal(before,FinalFrameProvider(w.project,w.cache_dir).get_final_frame(2))
        assert w.project.library.animation(b).group_id==run.id
    finally:close_window(qt,w)


def test_group_export_dialog_eligibility_and_force_empty(qt,tmp_path):
    w=window(qt,tmp_path)
    try:
        c=w.library_controller;empty=c.new_group(name='Empty');ready=c.new_group(name='Ready');cached_clip(w,ready.id,'Idle')
        d=GroupExportDialog(w,True);d.show()
        assert d.rows[ready.id].checkState(0)==Qt.CheckState.Checked
        assert d.rows[empty.id].checkState(0)==Qt.CheckState.Unchecked
        d.select(False);assert d.rows[empty.id].checkState(0)==Qt.CheckState.Checked
        assert d.preview.toPlainText();d.reject()
    finally:close_window(qt,w)

def drop_item(w,monkeypatch,dragged,target,position):
    tree=w.library_panel.tree
    zone={QAbstractItemView.DropIndicatorPosition.AboveItem:'above',
          QAbstractItemView.DropIndicatorPosition.BelowItem:'below'}.get(position,'on')
    monkeypatch.setattr(tree,'drop_target',lambda point:(target[0],target[1],zone))
    mime=QMimeData();mime.setData(MIME,json.dumps([dragged[0],dragged[1]]).encode())
    event=QDropEvent(QPointF(4,4),Qt.DropAction.MoveAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
    tree.dropEvent(event);return event


def test_group_drag_reorder_compensates_downward_and_upward_indexes(qt,tmp_path,monkeypatch):
    w=window(qt,tmp_path)
    try:
        c=w.library_controller;a=c.new_group(name='A');b=c.new_group(name='B');d=c.new_group(name='C')
        names=lambda:[g.name for g in w.project.library.children()]
        assert names()==['A','B','C']
        assert drop_item(w,monkeypatch,('GROUP',a.id),('GROUP',b.id),QAbstractItemView.DropIndicatorPosition.BelowItem).isAccepted()
        assert names()==['B','A','C']
        c.move('GROUP',a.id,None,0);assert names()==['A','B','C']
        assert drop_item(w,monkeypatch,('GROUP',a.id),('GROUP',d.id),QAbstractItemView.DropIndicatorPosition.BelowItem).isAccepted()
        assert names()==['B','C','A']
        c.move('GROUP',a.id,None,0);assert names()==['A','B','C']
        assert drop_item(w,monkeypatch,('GROUP',d.id),('GROUP',a.id),QAbstractItemView.DropIndicatorPosition.AboveItem).isAccepted()
        assert names()==['C','A','B']
    finally:close_window(qt,w)


def test_resource_drag_reorder_compensates_downward_and_upward_indexes(qt,tmp_path,monkeypatch):
    w=window(qt,tmp_path)
    try:
        c=w.library_controller;g=c.new_group(name='Idle');ids=[]
        for name in ('a','b','c'):
            path=tmp_path/('sheet-'+name+'.png');Image.new('RGBA',(32,32),(90,120,200,160)).save(path);ids.append(c.import_sheet(path).id)
        names=lambda:[r.name for r in w.project.library.in_group(g.id)]
        assert names()==['sheet-a.png','sheet-b.png','sheet-c.png']
        assert drop_item(w,monkeypatch,('RESOURCE',ids[0]),('RESOURCE',ids[1]),QAbstractItemView.DropIndicatorPosition.BelowItem).isAccepted()
        assert names()==['sheet-b.png','sheet-a.png','sheet-c.png']
        c.move('RESOURCE',ids[0],g.id,0);assert names()==['sheet-a.png','sheet-b.png','sheet-c.png']
        assert drop_item(w,monkeypatch,('RESOURCE',ids[0]),('RESOURCE',ids[2]),QAbstractItemView.DropIndicatorPosition.BelowItem).isAccepted()
        assert names()==['sheet-b.png','sheet-c.png','sheet-a.png']
        c.move('RESOURCE',ids[0],g.id,0);assert names()==['sheet-a.png','sheet-b.png','sheet-c.png']
        assert drop_item(w,monkeypatch,('RESOURCE',ids[2]),('RESOURCE',ids[0]),QAbstractItemView.DropIndicatorPosition.AboveItem).isAccepted()
        assert names()==['sheet-c.png','sheet-a.png','sheet-b.png']
    finally:close_window(qt,w)


def test_export_syncs_group_status_to_ready_and_survives_reopen(qt,tmp_path,monkeypatch):
    w=window(qt,tmp_path)
    try:
        c=w.library_controller;idle=c.new_group(name='Idle');aid=cached_clip(w,idle.id,'Idle',generated=False)
        assert not w.project.library.animation(aid).ready and w.project.library.groups[idle.id].status=='SOURCE_ONLY'
        monkeypatch.setattr(w,'_export_notice',lambda result:None)
        w.export_to(tmp_path/'exported','sheet');events(qt,lambda:not w.worker)
        assert w.last_error is None and (w.cache_dir/'sprite_sheet.png').is_file()
        assert w.project.library.animation(aid).ready and w.project.library.groups[idle.id].status=='READY'
        w.save_project();events(qt,lambda:not w.worker)
        path=w.project_file;w.open_project(path)
        assert w.project.library.animation(aid).ready and w.project.library.groups[idle.id].status=='READY'
    finally:close_window(qt,w)

