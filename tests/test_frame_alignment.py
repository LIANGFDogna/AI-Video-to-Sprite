"""Phase 2C: per-frame correction, reference ghost, drag stability and delta conversion."""
from dataclasses import asdict
import numpy as np
from PIL import Image
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QFocusEvent, QKeyEvent, QMouseEvent
from app.core.final_frame_provider import FinalFrameProvider
from app.i18n import t
from app.models.character_reference import AnimationTransform, CharacterReference
from app.models.character_templates import BLANK, REGISTRY
from app.models.project import Project
from app.ui.editor_canvas import screen_delta_to_canvas_delta
from test_group_workspace_ui import cached_clip, window
from test_workspace_ui import close_window, events, qt


def idle(qt,w):
    "Wait until no worker or interaction gate is active before touching the project."
    events(qt,lambda:not w.interaction_busy and w.worker is None and not w.editor.worker and not w.editor.pending)


def press(widget,x,y,button=Qt.MouseButton.LeftButton):
    widget.mousePressEvent(QMouseEvent(QEvent.Type.MouseButtonPress,QPointF(x,y),QPointF(x,y),button,button,Qt.KeyboardModifier.NoModifier))


def move(widget,x,y,button=Qt.MouseButton.LeftButton):
    widget.mouseMoveEvent(QMouseEvent(QEvent.Type.MouseMove,QPointF(x,y),QPointF(x,y),Qt.MouseButton.NoButton,button,Qt.KeyboardModifier.NoModifier))


def release(widget,x,y,button=Qt.MouseButton.LeftButton):
    widget.mouseReleaseEvent(QMouseEvent(QEvent.Type.MouseButtonRelease,QPointF(x,y),QPointF(x,y),button,Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier))


def escape(widget):
    widget.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress,Qt.Key.Key_Escape,Qt.KeyboardModifier.NoModifier))


def live_frames(w,indices):
    "Fresh live provider per call: final pixels must come from the current project, not a stale object."
    provider=FinalFrameProvider(w.project,w.cache_dir,live_edit=True)
    frames=[provider.get_final_frame(index).copy() for index in indices]
    return frames


def editor_window(qt,tmp_path,count=6):
    w=window(qt,tmp_path)
    w._export_notice=lambda result:None
    group=w.library_controller.new_group(name='Idle')
    animation_id=cached_clip(w,group.id,'Idle',count=count)
    w.open_editor();events(qt,lambda:w.editor.provider is not None)
    idle(qt,w)
    return w,group,animation_id


def scene_items(widget):
    return len(widget.scene().items())


def test_drag_100_times_item_count_stable(qt,tmp_path):
    w,group,animation_id=editor_window(qt,tmp_path)
    try:
        canvas=w.editor.canvas
        before=scene_items(canvas)
        for index in range(100):
            press(canvas,40,40);move(canvas,60+index%7,58+index%5);release(canvas,60+index%7,58+index%5)
        after=scene_items(canvas)
        assert before==after,f'GraphicsItem count changed: {before} -> {after}'
        assert canvas.drag_start is None and not canvas.dragging
        assert canvas.pixmap_item.pos().x()==0 and canvas.pixmap_item.pos().y()==0
    finally:
        close_window(qt,w)


def test_mouse_release_clears_drag(qt,tmp_path):
    w,group,animation_id=editor_window(qt,tmp_path)
    try:
        canvas=w.editor.canvas
        press(canvas,40,40);move(canvas,120,90)
        assert canvas.drag_start is not None and canvas.pixmap_item.pos()!=(0,0)
        release(canvas,120,90)
        assert canvas.drag_start is None and not canvas.dragging
        assert canvas.pixmap_item.pos().x()==0 and canvas.pixmap_item.pos().y()==0
    finally:
        close_window(qt,w)


def test_escape_clears_drag(qt,tmp_path):
    w,group,animation_id=editor_window(qt,tmp_path)
    try:
        canvas=w.editor.canvas
        press(canvas,40,40);move(canvas,120,90)
        escape(canvas)
        assert canvas.drag_start is None and canvas.dragging is False
        assert canvas.pixmap_item.pos().x()==0 and canvas.pixmap_item.pos().y()==0
    finally:
        close_window(qt,w)


def test_focus_out_clears_drag(qt,tmp_path):
    w,group,animation_id=editor_window(qt,tmp_path)
    try:
        canvas=w.editor.canvas
        press(canvas,40,40);move(canvas,120,90)
        canvas.focusOutEvent(QFocusEvent(QEvent.Type.FocusOut))
        assert canvas.drag_start is None and canvas.dragging is False
        assert canvas.pixmap_item.pos().x()==0 and canvas.pixmap_item.pos().y()==0
    finally:
        close_window(qt,w)


def test_group_switch_clears_drag(qt,tmp_path):
    w,group,animation_id=editor_window(qt,tmp_path)
    try:
        canvas=w.editor.canvas
        idle(qt,w)
        other=w.library_controller.new_group(name='Run')
        assert other is not None
        cached_clip(w,other.id,'Run',count=4)
        idle(qt,w)
        press(canvas,40,40);move(canvas,120,90)
        assert canvas.drag_start is not None
        w.library_controller.select_group(other.id)
        assert canvas.drag_start is None and not canvas.dragging
        assert canvas.pixmap_item.pos().x()==0 and canvas.pixmap_item.pos().y()==0
    finally:
        close_window(qt,w)


def test_animation_switch_clears_drag(qt,tmp_path):
    w,group,animation_id=editor_window(qt,tmp_path)
    try:
        canvas=w.editor.canvas
        idle(qt,w)
        second=cached_clip(w,group.id,'Second',count=4)
        idle(qt,w)
        w.library_controller.select_animation(animation_id)
        press(canvas,40,40);move(canvas,120,90)
        w.library_controller.select_animation(second)
        assert canvas.drag_start is None and not canvas.dragging
        assert canvas.pixmap_item.pos().x()==0 and canvas.pixmap_item.pos().y()==0
    finally:
        close_window(qt,w)


def test_character_switch_clears_drag(qt,tmp_path):
    w,group,animation_id=editor_window(qt,tmp_path)
    try:
        canvas=w.editor.canvas
        idle(qt,w)
        hero=w.library_controller.new_character(name='Hero',template_id=BLANK)
        assert hero is not None
        idle(qt,w)
        w.library_controller.select_group(group.id)
        press(canvas,40,40);move(canvas,120,90)
        w.library_controller.select_character(hero.id)
        assert canvas.drag_start is None and not canvas.dragging
        assert canvas.pixmap_item.pos().x()==0 and canvas.pixmap_item.pos().y()==0
    finally:
        close_window(qt,w)


def test_rubber_band_removed_on_release(qt,tmp_path):
    w,group,animation_id=editor_window(qt,tmp_path)
    try:
        timeline=w.editor.timeline
        press(timeline,4000,60);move(timeline,4200,150)
        assert timeline.rubber is not None and timeline.selecting is not None
        release(timeline,4200,150)
        assert timeline.rubber is None and timeline.selecting is None
        assert not any(item.zValue()==50 for item in timeline.scene().items())
    finally:
        close_window(qt,w)


def test_rubber_band_removed_on_escape(qt,tmp_path):
    w,group,animation_id=editor_window(qt,tmp_path)
    try:
        timeline=w.editor.timeline
        press(timeline,4000,60);move(timeline,4200,150)
        assert timeline.rubber is not None
        escape(timeline)
        assert timeline.rubber is None and timeline.selecting is None
        assert not any(item.zValue()==50 for item in timeline.scene().items())
    finally:
        close_window(qt,w)


def test_zoom_and_dpi_delta_conversion():
    assert screen_delta_to_canvas_delta((5,-5),view_scale=.5)==(10,-10)
    assert screen_delta_to_canvas_delta((5,-5),view_scale=1.0)==(5,-5)
    assert screen_delta_to_canvas_delta((8,4),view_scale=.5,display_scale=2.0)==(8,4)
    assert screen_delta_to_canvas_delta((5,5),view_scale=1.0,device_ratio=1.25)==(4,4)


def test_reference_axis_constraints():
    reference=CharacterReference('a'*32,0,64,80,96,96)
    assert reference.moved('ground',7,-5).origin==(64,75)
    assert reference.moved('y_axis',7,-5).origin==(71,80)
    assert reference.moved('origin',7,-5).origin==(71,75)


def test_animation_offset_affects_all_frames(qt,tmp_path):
    w,group,animation_id=editor_window(qt,tmp_path)
    try:
        plain=live_frames(w,range(3))
        assert any(np.count_nonzero(frame) for frame in plain),'fixture produced empty frames'
        idle(qt,w)
        w.set_animation_offset(3,2)
        moved=live_frames(w,range(3))
        for index in range(3):
            assert not np.array_equal(plain[index],moved[index]),'Animation Transform must move every frame'
        assert w.project.frame_corrections=={}
    finally:
        close_window(qt,w)


def test_frame_correction_affects_one_frame(qt,tmp_path):
    w,group,animation_id=editor_window(qt,tmp_path)
    try:
        plain=live_frames(w,range(3))
        idle(qt,w)
        w.add_frame_correction([1],4,-6)
        assert w.project.frame_correction(1)==(4,-6)
        assert w.project.frame_correction(0)==(0,0) and w.project.frame_correction(2)==(0,0)
        moved=live_frames(w,range(3))
        assert not np.array_equal(moved[1],plain[1]),'Frame Correction must move only its own frame'
        assert np.array_equal(moved[0],plain[0]) and np.array_equal(moved[2],plain[2])
    finally:
        close_window(qt,w)


def test_animation_plus_frame_offset_additive(qt,tmp_path):
    w,group,animation_id=editor_window(qt,tmp_path)
    try:
        plain=live_frames(w,[1])[0]
        idle(qt,w)
        w.set_animation_offset(5,-3)
        offset_only=live_frames(w,[1])[0]
        assert not np.array_equal(plain,offset_only)
        idle(qt,w)
        w.add_frame_correction([1],-5,3)
        assert np.array_equal(live_frames(w,[1])[0],plain),'Animation Offset + inverse Frame Correction returns the original pixels'
        idle(qt,w)
        w.add_frame_correction([1],2,2)
        correction=w.project.frame_correction(1)
        offset=w.project.animation_transform
        assert correction==(-3,5) and offset==AnimationTransform(5,-3)
        assert (offset.offset_x+correction[0],offset.offset_y+correction[1])==(2,2),'layers are additive' 
        assert not np.array_equal(live_frames(w,[1])[0],offset_only)
    finally:
        close_window(qt,w)


def test_multi_select_frame_correction(qt,tmp_path):
    w,group,animation_id=editor_window(qt,tmp_path)
    try:
        idle(qt,w)
        w.add_frame_correction([2,3,4],4,-7)
        assert [w.project.frame_correction(i) for i in (2,3,4)]==[(4,-7)]*3
        w.add_frame_correction([3],1,1)
        assert w.project.frame_correction(3)==(5,-6) and w.project.frame_correction(2)==(4,-7)
        assert w.project.frame_correction(1)==(0,0)
    finally:
        close_window(qt,w)


def test_reset_current_selected_frames_and_animation_offset(qt,tmp_path):
    w,group,animation_id=editor_window(qt,tmp_path)
    try:
        idle(qt,w)
        w.add_frame_correction([2,3,4],4,-7)
        w.editor.index=3;w.editor.selected_ids=[]
        w.editor.reset_correction('current')
        assert w.project.frame_correction(3)==(0,0) and w.project.frame_correction(2)==(4,-7)
        w.reset_frame_corrections([2,4])
        assert w.project.frame_corrections=={}
        idle(qt,w)
        w.set_animation_offset(5,5)
        assert w.project.animation_transform==AnimationTransform(5,5)
        w.set_animation_offset(0,0)
        assert not w.project.animation_transform.active
        assert w.project.frame_corrections=={}
    finally:
        close_window(qt,w)


def test_undo_single_drag_single_command(qt,tmp_path):
    w,group,animation_id=editor_window(qt,tmp_path)
    try:
        canvas=w.editor.canvas
        w.editor.position_frame.setChecked(True)
        history=w._history();before=history.index
        press(canvas,40,40)
        for step in range(1,101):move(canvas,40+step,40+step)
        release(canvas,140,140)
        assert history.index==before+1,'100 mouse moves must still record exactly one command'
        assert w.project.frame_corrections
        idle(qt,w)
        w.undo_edit();events(qt,lambda:not w.worker)
        assert not w.project.frame_corrections
        idle(qt,w)
        w.redo_edit();events(qt,lambda:not w.worker)
        assert w.project.frame_corrections
    finally:
        close_window(qt,w)


def test_undo_multi_frame_drag_single_command(qt,tmp_path):
    w,group,animation_id=editor_window(qt,tmp_path)
    try:
        idle(qt,w)
        w.add_frame_correction([2,3,4,5,6],1,1)
        history=w._history();before=history.index
        w.add_frame_correction([2,3,4,5,6],2,2)
        assert history.index==before+1
        assert [w.project.frame_correction(i) for i in range(2,7)]==[(3,3)]*5
        idle(qt,w)
        w.undo_edit();events(qt,lambda:not w.worker)
        assert [w.project.frame_correction(i) for i in range(2,7)]==[(1,1)]*5
        idle(qt,w)
        w.redo_edit();events(qt,lambda:not w.worker)
        assert [w.project.frame_correction(i) for i in range(2,7)]==[(3,3)]*5
    finally:
        close_window(qt,w)


def test_ghost_uses_same_character_and_never_crosses(qt,tmp_path):
    w,group,animation_id=editor_window(qt,tmp_path)
    try:
        project=w.project
        hero=project.library.add_character('Hero','blank',1)
        project.library.reassign_character(group.id,hero.id)
        hero.character_reference=CharacterReference(animation_id,0,26,26,32,32)
        project.current_character_id=hero.id
        project.sync_character_reference()
        idle(qt,w)
        second=cached_clip(w,group.id,'Second',count=4)
        idle(qt,w)
        w.editor._ghost_override=False;w.editor._sync_ghost();w.editor.request_preview()
        events(qt,lambda:w.editor.canvas.ghost_pixels is not None)
        assert w.editor.canvas.ghost_pixels is not None,'same-character non-reference Animation shows the Ghost'
        assert project.character_reference.origin_x==26
        boss=project.library.add_character('Boss','blank',1)
        boss.character_reference=CharacterReference(second,0,20,20,32,32)
        project.current_character_id=boss.id
        project.sync_character_reference()
        assert project.character_reference.origin_x==20,'Boss must use its own Reference'
        project.current_character_id=hero.id
        project.sync_character_reference()
        assert project.character_reference.origin_x==26
    finally:
        close_window(qt,w)


def test_ghost_toggle_opacity_and_no_reference_hint(qt,tmp_path):
    w,group,animation_id=editor_window(qt,tmp_path)
    try:
        w.editor._sync_ghost()
        assert w.editor.ghost_hint.text()==t('This Character has no Character Reference yet.')
        assert w.editor.show_idle_ghost.isEnabled() is False
        assert w.editor.reference_opacity.maximum()==0.7
        assert w.editor.reference_opacity.value()==0.15
        project=w.project
        hero=project.library.add_character('Hero','blank',1)
        project.library.reassign_character(group.id,hero.id)
        hero.character_reference=CharacterReference(animation_id,0,26,26,32,32)
        project.current_character_id=hero.id
        project.sync_character_reference()
        idle(qt,w)
        second=cached_clip(w,group.id,'Second',count=4)
        idle(qt,w)
        w.editor._ghost_override=False;w.editor._sync_ghost()
        assert w.editor.show_idle_ghost.isEnabled() is True
        assert w.editor.show_idle_ghost.isChecked() is True
        w.editor.show_idle_ghost.setChecked(False)
        assert w.editor.show_idle_ghost.isChecked() is False and w.editor._ghost_override is True
        w.editor.reference_opacity.setValue(.5)
        assert w.editor.reference_opacity.value()==0.5
        assert second!=animation_id
    finally:
        close_window(qt,w)


def test_ghost_hidden_for_reference_animation(qt,tmp_path):
    w,group,animation_id=editor_window(qt,tmp_path)
    try:
        project=w.project
        hero=project.library.add_character('Hero','blank',1)
        project.library.reassign_character(group.id,hero.id)
        hero.character_reference=CharacterReference(animation_id,0,16,16,32,32)
        project.current_character_id=hero.id
        project.sync_character_reference()
        w.editor._sync_ghost()
        assert w.editor.show_idle_ghost.isChecked() is False
        assert w.editor.show_idle_ghost.isEnabled() is False
        assert w.editor.ghost_hint.text()==t('Ghost is hidden while editing the Reference Animation.')
        assert w.editor.canvas.ghost_pixels is None
    finally:
        close_window(qt,w)


def test_ghost_not_in_export_and_preview_export_pixel_identical(qt,tmp_path):
    w,group,animation_id=editor_window(qt,tmp_path)
    try:
        project=w.project
        hero=project.library.add_character('Hero','blank',1)
        project.library.reassign_character(group.id,hero.id)
        hero.character_reference=CharacterReference(animation_id,0,16,16,32,32)
        project.current_character_id=hero.id
        project.sync_character_reference()
        idle(qt,w)
        cached_clip(w,group.id,'Second',count=4)
        idle(qt,w)
        w.add_frame_correction([0,2],5,-3)
        idle(qt,w)
        w.editor._ghost_override=False;w.editor._sync_ghost();w.editor.request_preview()
        events(qt,lambda:w.editor.canvas.ghost_pixels is not None)
        expected=live_frames(w,[0,2])
        destination=tmp_path/'export'
        w.export_to(destination,'frames');events(qt,lambda:not w.worker)
        assert w.last_error is None
        for position,index in enumerate((0,2)):
            with Image.open(destination/'frames'/f'{index:04d}.png') as image:
                exported=np.array(image)
            assert np.array_equal(exported,expected[position]),'export equals the provider: corrections in, Ghost out'
        assert w.editor.canvas.ghost_pixels is not None,'Ghost stays an editor overlay'
    finally:
        close_window(qt,w)


def test_frame_correction_is_animation_scoped(qt,tmp_path):
    w=window(qt,tmp_path)
    try:
        run=w.library_controller.new_group(name='Run')
        jump=w.library_controller.new_group(name='Jump')
        run_animation=cached_clip(w,run.id,'Run',count=8)
        idle(qt,w)
        jump_animation=cached_clip(w,jump.id,'Jump',count=8)
        idle(qt,w)
        w.library_controller.select_animation(run_animation)
        w.add_frame_correction([6],10,-5)
        w.library_controller.select_animation(jump_animation)
        w.add_frame_correction([6],-3,8)
        assert w.project.frame_correction(6)==(-3,8)
        w.library_controller.select_animation(run_animation)
        assert w.project.frame_correction(6)==(10,-5)
        for _ in range(3):
            w.library_controller.select_animation(jump_animation);assert w.project.frame_correction(6)==(-3,8)
            w.library_controller.select_animation(run_animation);assert w.project.frame_correction(6)==(10,-5)
        idle(qt,w)
        w.save_project();events(qt,lambda:not w.worker)
        path=w.project_file
        w.open_project(path)
        w.library_controller.select_animation(run_animation)
        assert w.project.frame_correction(6)==(10,-5)
        w.library_controller.select_animation(jump_animation)
        assert w.project.frame_correction(6)==(-3,8)
        assert w.project.frame_correction(5)==(0,0)
    finally:
        close_window(qt,w)


def test_frame_correction_and_ghost_are_character_isolated(qt,tmp_path):
    w=window(qt,tmp_path)
    try:
        script=w.library_controller
        player=script.new_character(name='Player',template_id=BLANK)
        player_group=script.new_group(name='Idle')
        player_animation=cached_clip(w,player_group.id,'PlayerIdle',count=8)
        idle(qt,w)
        boss=script.new_character(name='Boss',template_id=BLANK)
        boss_group=script.new_group(name='BossIdle')
        boss_animation=cached_clip(w,boss_group.id,'BossIdle',count=8)
        idle(qt,w)
        script.select_animation(player_animation)
        w.add_frame_correction([6],2,3)
        script.select_animation(boss_animation)
        w.add_frame_correction([6],-2,-3)
        assert w.project.frame_correction(6)==(-2,-3)
        script.select_animation(player_animation)
        assert w.project.frame_correction(6)==(2,3)
        w.project.library.characters[player.id].character_reference=CharacterReference(player_animation,0,20,20,32,32)
        w.project.library.characters[boss.id].character_reference=CharacterReference(boss_animation,0,24,24,32,32)
        w.project.sync_character_reference()
        script.select_group(player_group.id)
        assert w.project.character_reference.origin_x==20
        script.select_group(boss_group.id)
        assert w.project.character_reference.origin_x==24
        idle(qt,w)
        w.save_project();events(qt,lambda:not w.worker)
        path=w.project_file
        w.open_project(path)
        script.select_animation(player_animation)
        assert w.project.frame_correction(6)==(2,3) and w.project.character_reference.origin_x==20
        script.select_animation(boss_animation)
        assert w.project.frame_correction(6)==(-2,-3) and w.project.character_reference.origin_x==24
    finally:
        close_window(qt,w)


def test_save_reopen_and_legacy_corrections(qt,tmp_path):
    w,group,animation_id=editor_window(qt,tmp_path)
    try:
        idle(qt,w)
        w.add_frame_correction([1,2],3,-4)
        w.save_project();events(qt,lambda:not w.worker)
        path=w.project_file
        w.open_project(path)
        assert w.project.frame_correction(1)==(3,-4) and w.project.frame_correction(2)==(3,-4)
        assert w.project.frame_correction(0)==(0,0)
        legacy=asdict(Project(source_video=str(tmp_path/'legacy.mp4')))
        legacy.pop('frame_corrections',None)
        restored=Project.from_dict(legacy)
        assert restored.frame_corrections=={} and not restored.has_final_edits
    finally:
        close_window(qt,w)
