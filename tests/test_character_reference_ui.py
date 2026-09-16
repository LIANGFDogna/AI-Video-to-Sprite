from dataclasses import asdict
from pathlib import Path
import numpy as np
from PySide6.QtCore import Qt, QPointF
from PySide6.QtTest import QTest
from app.ui.main_window import MainWindow
from app.models.project import Project
from app.models.character_reference import AnimationTransform
from app.core.final_frame_provider import FinalFrameProvider
from app.utils.paths import frame_path
from app.utils.rgba_image import read_rgba
from test_workspace_ui import qt,events,close_window
from test_editor_ui import settle
from test_character_reference import reference_pipe


def make_window(pipe,qt):
    w=MainWindow(pipe.cache_dir/'ui.log');w.project=pipe.project;w.project_file=pipe.project_path;w.cache_dir=pipe.cache_dir
    w._loaded();w.show();w.open_editor();settle(qt,w)
    return w


def drag(view,start,end):
    QTest.mousePress(view.viewport(),Qt.MouseButton.LeftButton,pos=view.mapFromScene(QPointF(*start)))
    QTest.mouseMove(view.viewport(),view.mapFromScene(QPointF(*end)))
    QTest.mouseRelease(view.viewport(),Qt.MouseButton.LeftButton,pos=view.mapFromScene(QPointF(*end)))


def test_fixed_idle_axis_drag_keyboard_cancel_and_locked_save(qt,reference_pipe):
    w=make_window(reference_pipe,qt)
    try:
        e=w.editor;before=read_rgba(frame_path(reference_pipe.keyed,0)).copy()
        w.open_character_reference();events(qt,lambda:w.reference_dialog is not None and not w.worker)
        dialog=w.reference_dialog;v=dialog.view
        assert not dialog.isModal() and w.project.character_reference is None
        key=v.pixmap_item.pixmap().cacheKey();origin=v.reference.origin
        drag(v,(4,origin[1]),(14,origin[1]-4))
        assert v.reference.origin==(origin[0],origin[1]-4)
        origin=v.reference.origin
        drag(v,(origin[0],8),(origin[0]+6,18))
        assert v.reference.origin==(origin[0]+6,origin[1])
        origin=v.reference.origin
        drag(v,origin,(origin[0]+2,origin[1]-3))
        assert v.reference.origin==(origin[0]+2,origin[1]-3)
        before_key=v.reference.origin
        QTest.keyClick(v,Qt.Key.Key_Left)
        QTest.keyClick(v,Qt.Key.Key_Up,Qt.KeyboardModifier.ShiftModifier)
        assert v.reference.origin==(before_key[0]-1,before_key[1]-10)
        assert v.pixmap_item.pixmap().cacheKey()==key and v.pixmap_item.pos()==QPointF(0,0)
        assert np.array_equal(v.original_pixels,before) and w.project.character_reference is None
        draft=v.reference
        dialog.save_button.click();events(qt,lambda:w.reference_dialog is None);settle(qt,w)
        assert w.project.character_reference==draft and draft.locked
        assert e.drag_scope.currentData()=='animation'
        assert np.array_equal(e.provider.get_final_frame(0),before)
        # Phase 2C rule: the Reference Animation itself never shows its own Ghost.
        assert e.canvas.ghost_pixels is None and not e.show_idle_ghost.isEnabled()
        assert not e.show_idle_ghost.isChecked()
        w.open_character_reference();events(qt,lambda:w.reference_dialog is not None and not w.worker)
        w.reference_dialog.x.setValue(10);w.reference_dialog.reject();events(qt,lambda:w.reference_dialog is None)
        assert w.project.character_reference==draft
    finally:close_window(qt,w)


def test_locked_axes_animation_drag_ghost_undo_export_and_save(qt,reference_pipe,tmp_path):
    w=make_window(reference_pipe,qt)
    try:
        w.open_character_reference();events(qt,lambda:w.reference_dialog is not None and not w.worker)
        w.reference_dialog.save_button.click();events(qt,lambda:w.reference_dialog is None);settle(qt,w)
        e=w.editor;reference=w.project.character_reference
        # Phase 2C rule: the Reference Animation hides its own Ghost.
        assert e.canvas.ghost_pixels is None and not e.show_idle_ghost.isEnabled()
        before=read_rgba(frame_path(reference_pipe.keyed,0)).copy()
        # Ordinary dragging at the axis intersection changes animation offset, never the axes.
        e.canvas.actual_size()
        origin=e.canvas.reference_mapping;start=reference.origin
        end=(start[0]-12,start[1]+4)
        QTest.mousePress(e.canvas.viewport(),Qt.MouseButton.LeftButton,pos=e.canvas.mapFromScene(QPointF(*start)))
        QTest.mouseMove(e.canvas.viewport(),e.canvas.mapFromScene(QPointF(*end)))
        assert e.canvas.idle_ghost_item.pos()==QPointF(0,0)
        QTest.mouseRelease(e.canvas.viewport(),Qt.MouseButton.LeftButton,pos=e.canvas.mapFromScene(QPointF(*end)))
        settle(qt,w)
        assert w.project.animation_transform==AnimationTransform(-12,4)
        assert w.project.character_reference==reference
        assert not w.project.timeline_edit.frame_overrides
        # The Reference Animation keeps its own Ghost hidden through the whole drag.
        assert e.canvas.ghost_pixels is None and e.canvas.idle_ghost_item.pos()==QPointF(0,0)
        for i in range(4):
            frame=e.provider.get_final_frame(i)
            assert tuple(frame[34,16+i])==(220,70,130,191)
        w.undo_edit();settle(qt,w)
        assert not w.project.animation_transform.active and w.project.character_reference==reference
        w.redo_edit();settle(qt,w)
        assert w.project.animation_transform==AnimationTransform(-12,4)
        preview=[e.provider.get_final_frame(i).copy() for i in range(4)]
        w.export_to(tmp_path/'out',godot=True);events(qt,lambda:not w.worker)
        for i in range(4):assert np.array_equal(preview[i],read_rgba(tmp_path/'out/frames'/f'{i:04d}.png'))
        assert np.array_equal(read_rgba(frame_path(reference_pipe.keyed,0)),before)
        w.save_project(reference_pipe.project_path);events(qt,lambda:not w.worker)
        loaded=Project.load(reference_pipe.project_path)
        assert loaded.character_reference==reference and loaded.animation_transform==AnimationTransform(-12,4)
    finally:close_window(qt,w)


def test_reference_cancel_and_old_history_cannot_revert_other_animation_reference(qt,reference_pipe):
    w=make_window(reference_pipe,qt)
    try:
        w.open_character_reference();events(qt,lambda:w.reference_dialog is not None and not w.worker)
        w.reference_dialog.reject();events(qt,lambda:w.reference_dialog is None)
        assert w.project.character_reference is None
        w.open_character_reference();events(qt,lambda:w.reference_dialog is not None and not w.worker)
        w.reference_dialog.save_button.click();events(qt,lambda:w.reference_dialog is None);settle(qt,w)
        w.set_animation_offset(3,0);settle(qt,w)
        # Equivalent to a project-level reference change while another animation is active.
        newer=w.project.character_reference.moved('origin',5,-3)
        w.project.character_reference=newer
        w.undo_edit();settle(qt,w)
        assert w.project.character_reference==newer and not w.project.animation_transform.active
    finally:close_window(qt,w)


def test_missing_reference_animation_is_nonblocking(qt,reference_pipe):
    from dataclasses import replace
    from test_character_reference import reference
    w=make_window(reference_pipe,qt)
    try:
        w.project.character_reference=replace(reference(w.project),reference_animation_id='missing-reference')
        w.editor.bind();settle(qt,w)
        assert w.editor.reference_source is None and w.editor.reference_load_error
        w.open_character_reference()
        assert w.reference_dialog is None and not w.worker
        assert w.editor.notice.text()
    finally:close_window(qt,w)
