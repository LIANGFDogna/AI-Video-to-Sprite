from pathlib import Path
from dataclasses import asdict
import numpy as np
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from app.ui.main_window import MainWindow
from app.core.final_frame_provider import FinalFrameProvider
from test_workspace_ui import qt,events,close_window
from test_editor_pipeline import editor_pipe


def settle(qt,window):
    events(qt,lambda: not window.worker and window.editor.provider is not None and not window.editor.worker and not window.editor.pending and window.editor.last_pixels is not None,15)


def test_editor_retime_copy_reverse_history_and_export(qt,editor_pipe,tmp_path):
    w=MainWindow(tmp_path/'app.log');w.project=editor_pipe.project;w.cache_dir=editor_pipe.cache_dir
    w._loaded();w.show();w.open_editor()
    try:
        settle(qt,w);e=w.editor
        assert w.steps.count()==5 and w.steps.currentIndex()==2
        assert e.isVisible() and e.timeline.isVisible() and not w.panels.isVisible()
        assert e.tracks.topLevelItemCount()==4
        e.action('select_all');assert len(e.selection())==39
        e.target_count.setValue(20);e.curve.setCurrentIndex(e.curve.findData('ease_in_out'))
        e.apply_count_button.click();settle(qt,w)
        assert len(e.provider)==20
        assert e.provider.source_index(0)==0 and e.provider.source_index(19)==38
        w.undo_button.click();settle(qt,w);assert len(e.provider)==39
        w.redo_button.click();settle(qt,w);assert len(e.provider)==20
        e.timeline.select_ids([w.project.timeline_edit.frames()[5].id]);e.action('copy');e.paste(True);settle(qt,w)
        assert len(e.provider)==21
        ordered=w.project.timeline_edit.frames();e.timeline.select_ids([f.id for f in ordered[-5:]])
        prior=[f.source_index for f in ordered[-5:]];e.action('reverse');settle(qt,w)
        assert [f.source_index for f in w.project.timeline_edit.frames()][-5:]==list(reversed(prior))
        e.select(12);settle(qt,w);pixels=e.last_pixels.copy()
        w.build_sprites();events(qt,lambda:not w.worker and w.built)
        assert w.steps.currentIndex()==3 and w.project.output_count==21
        assert np.array_equal(FinalFrameProvider(w.project,w.cache_dir).get_final_frame(12),pixels)
        w.save_project(tmp_path/'attack.aivsprite');events(qt,lambda:not w.worker)
        w.export_to(tmp_path/'export',godot=True);events(qt,lambda:not w.worker)
        assert len(list((tmp_path/'export/frames').glob('*.png')))==21
        assert w.last_error is None
    finally:close_window(qt,w)


def test_canvas_drag_nudge_multi_delete_and_root_undo(qt,editor_pipe,tmp_path):
    w=MainWindow(tmp_path/'app.log');w.project=editor_pipe.project;w.cache_dir=editor_pipe.cache_dir
    w._loaded();w.show();w.open_editor()
    try:
        settle(qt,w);e=w.editor
        ids=[f.id for f in w.project.timeline_edit.frames()]
        e.timeline.select_ids([ids[12]]);e.select(12);settle(qt,w)
        canvas=e.canvas
        start=canvas.mapFromScene(15,15);end=canvas.mapFromScene(18,11)
        QTest.mousePress(canvas.viewport(),Qt.MouseButton.LeftButton,pos=start)
        QTest.mouseMove(canvas.viewport(),end)
        QTest.mouseRelease(canvas.viewport(),Qt.MouseButton.LeftButton,pos=end)
        settle(qt,w)
        value=w.project.timeline_edit.frame_overrides[ids[12]]
        assert (value.offset_x,value.offset_y)==(3,-4)
        QTest.keyClick(canvas,Qt.Key.Key_Right,Qt.KeyboardModifier.ShiftModifier);settle(qt,w)
        assert w.project.timeline_edit.frame_overrides[ids[12]].offset_x==13
        e.timeline.select_ids(ids[2:5]);e.action('delete');settle(qt,w)
        assert len(e.provider)==36
        QTest.keyClick(e.timeline,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier);settle(qt,w)
        assert len(e.provider)==39
        w.enable_full_processing();events(qt,lambda:not w.preview_worker and w._preview_frame_index==0)
        assert e.inspector.currentIndex()==1 and not w.project.is_passthrough
        w._set_root(13,15);assert w.project.root_keyframes[0]==(13,15)
        w.undo_edit();assert 0 not in w.project.root_keyframes
        w.redo_edit();assert w.project.root_keyframes[0]==(13,15)
        # Editing Root invalidates aligned pixels; source browsing must still work before rebuilding.
        assert e.provider is None
        e.select_source(12)
        events(qt,lambda:w._preview_frame_index==12 and not w.preview_worker)
        assert w.current_frame==12 and e.alignment_view.isVisible()
        w._set_root(14,16)
        assert w.project.root_keyframes[12]==(14,16)
        e.step(1)
        events(qt,lambda:w._preview_frame_index==13 and not w.preview_worker)
        assert w.current_frame==13
    finally:close_window(qt,w)


def test_timeline_ctrl_shift_drag_tracks_lock_and_pixel_preview(qt,editor_pipe,tmp_path):
    w=MainWindow(tmp_path/'app.log');w.project=editor_pipe.project;w.cache_dir=editor_pipe.cache_dir
    w._loaded();w.show();w.open_editor()
    try:
        settle(qt,w);e=w.editor;timeline=e.timeline
        frames=w.project.timeline_edit.frames();ids=[f.id for f in frames]
        def point(ident):
            item=timeline.items_by_id[ident]
            return timeline.mapFromScene(item.mapRectToScene(item.rect()).center())
        QTest.mouseClick(timeline.viewport(),Qt.MouseButton.LeftButton,pos=point(ids[0]))
        QTest.mouseClick(timeline.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.ControlModifier,pos=point(ids[2]))
        assert set(timeline.ids())=={ids[0],ids[2]}
        QTest.mouseClick(timeline.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.ShiftModifier,pos=point(ids[4]))
        assert set(timeline.ids())==set(ids[2:5])
        # Drag a rectangle from the empty strip under the main track across three blocks.
        timeline.select_ids([])
        a=timeline.items_by_id[ids[1]].rect();b=timeline.items_by_id[ids[3]].rect()
        start=timeline.mapFromScene(a.left()+2,a.bottom()+2)
        end=timeline.mapFromScene(b.right()-2,b.top()-2)
        QTest.mousePress(timeline.viewport(),Qt.MouseButton.LeftButton,pos=start)
        QTest.mouseMove(timeline.viewport(),end)
        QTest.mouseRelease(timeline.viewport(),Qt.MouseButton.LeftButton,pos=end)
        assert set(timeline.ids())==set(ids[1:4])
        e.ripple.setChecked(False)
        timeline.select_ids([ids[2]])
        start=point(ids[2]);end=start+QPoint(0,timeline.row_height*2)
        QTest.mousePress(timeline.viewport(),Qt.MouseButton.LeftButton,pos=start)
        QTest.mouseMove(timeline.viewport(),end)
        QTest.mouseRelease(timeline.viewport(),Qt.MouseButton.LeftButton,pos=end)
        settle(qt,w)
        assert next(f for f in w.project.timeline_edit.frames() if f.id==ids[2]).track_id=='effects'
        item=e.tracks.topLevelItem(2);item.setCheckState(2,Qt.CheckState.Checked)
        settle(qt,w)
        before=asdict(w.project.timeline_edit)
        timeline.select_ids([ids[2]]);e.action('delete');settle(qt,w)
        assert asdict(w.project.timeline_edit)==before
        assert not w.last_error
        w.undo_edit();settle(qt,w)
        assert not w.project.timeline_edit.track_layout[2].locked
        e.curve.setCurrentIndex(e.curve.findData('bezier'))
        editor=e.curve_editor
        start=editor.point(*editor.controls[:2]).toPoint()
        QTest.mousePress(editor,Qt.MouseButton.LeftButton,pos=start)
        QTest.mouseMove(editor,start+QPoint(10,-12))
        QTest.mouseRelease(editor,Qt.MouseButton.LeftButton,pos=start+QPoint(10,-12))
        assert editor.controls[0]>.25 and editor.controls[1]>.1
    finally:close_window(qt,w)
