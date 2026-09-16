"""Real Qt / frozen acceptance of reference calibration and animation offsets."""
from dataclasses import asdict
import json
import logging
import os
from pathlib import Path
import time
import cv2
import numpy as np
from PySide6.QtCore import QTimer, Qt, QPointF
from PySide6.QtTest import QTest
from app.core.project_workspace import create_project_workspace
from app.core.final_frame_provider import FinalFrameProvider
from app.core.animation_transform import translate_rgba
from app.models.project import Project
from app.models.character_reference import AnimationTransform
from app.utils.cache import save_rgba
from app.utils.paths import frame_path
from app.utils.rgba_image import read_rgba


def start_reference_smoke(app,window,output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    log=logging.getLogger('aivsprite.reference_smoke')
    video=output/'Idle.mp4'
    writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'mp4v'),24,(1024,1536))
    assert writer.isOpened()
    for i in range(6):
        bgr=np.full((1536,1024,3),(0,255,0),np.uint8)
        cv2.circle(bgr,(506,480),92,(130,170,225),-1)
        cv2.rectangle(bgr,(428,572),(584,1018),(145,65,180),-1)
        cv2.rectangle(bgr,(428,1018),(486,1216),(160,110,75),-1)
        cv2.rectangle(bgr,(526,1018),(584,1216),(160,110,75),-1)
        cv2.line(bgr,(578,630),(672+i*3,815),(130,170,225),30)
        writer.write(bgr)
    writer.release()
    project,path=create_project_workspace(output,'ReferenceHero','ai_character')
    window.project,window.project_file=project,path;window._loaded()
    window.library_controller.new_group(name="Character")
    window._failed=lambda message:setattr(window,'last_error',message)
    state={'phase':'import_idle','started':time.monotonic()}
    timer=QTimer(window);timer.setInterval(30)

    def finish(code):
        timer.stop()
        if window.worker:window.worker.cancel();window.worker.wait();app.processEvents()
        if window.reference_dialog:window.reference_dialog.reject()
        for review in list(window.review_windows):review.close()
        window.editor.pause_preview();window.dirty=False;window.close();app.exit(code)

    def advance(phase):state.update(phase=phase,ready=time.monotonic())

    def editor_ready():
        e=window.editor
        return e.provider and not e.worker and not e.pending and e.last_pixels is not None

    def drag(view,start,end,part=None):
        a=view.mapFromScene(QPointF(*start));b=view.mapFromScene(QPointF(*end))
        assert view.viewport().rect().contains(a) and view.viewport().rect().contains(b)
        if part:assert view.hit_handle(a)==part
        actual=view.mapToScene(b)-view.mapToScene(a)
        QTest.mousePress(view.viewport(),Qt.MouseButton.LeftButton,pos=a)
        QTest.mouseMove(view.viewport(),b)
        QTest.mouseRelease(view.viewport(),Qt.MouseButton.LeftButton,pos=b)
        return round(actual.x()),round(actual.y())

    def export_equal(provider):
        dest=output/'export';sheet=read_rgba(dest/'sprite_sheet.png')
        metadata=json.loads((dest/'animation.json').read_text(encoding='utf-8'))
        assert metadata['character_reference']==asdict(state['reference'])
        assert metadata['animation_transform']==asdict(AnimationTransform(-12,4))
        for i in range(len(provider)):
            frame=provider.get_final_frame(i)
            assert np.array_equal(frame,read_rgba(dest/'frames'/f'{i:04d}.png'))
            y=(i//3)*512;x=(i%3)*512
            assert np.array_equal(frame,sheet[y:y+512,x:x+512])
        assert sheet.shape==(1024,1536,4)
        for notice in list(window.export_notices):notice.close()

    def poll():
        try:
            if window.last_error:raise AssertionError(window.last_error)
            if time.monotonic()-state['started']>155:raise AssertionError('Reference acceptance timed out')
            if window.worker:return
            if time.monotonic()-state.get('ready',0)<.2:return
            p=window.project;e=window.editor;phase=state['phase']
            if phase=='import_idle':window.import_video(video);advance('key_idle')
            elif phase=='key_idle':
                assert p.project_canvas==(1536,1536) and (p.video.width,p.video.height)==(1536,1536)
                assert not p.character_reference
                window.process_key();advance('keyed')
            elif phase=='keyed':
                if not window.keyed_ready or window.preview_worker or window.preview_pending:return
                state['idle_cache']=window.cache_dir
                state['key_times']=[frame_path(window.cache_dir/'keyed_frames',i).stat().st_mtime_ns for i in range(6)]
                state['idle_pixels']=read_rgba(frame_path(window.cache_dir/'keyed_frames',0)).copy()
                # The 1024 px source is still precisely centered in the project canvas.
                assert not state['idle_pixels'][:,:256,3].any() and not state['idle_pixels'][:,1280:,3].any()
                window.keyed_passthrough_button.click();advance('sprite_idle')
            elif phase=='sprite_idle':
                if not window.built:return
                assert p.is_keyed_passthrough
                window.open_editor();advance('editor_idle')
            elif phase=='editor_idle':
                if not editor_ready():return
                window.open_character_reference();advance('calibrate')
            elif phase=='calibrate':
                d=window.reference_dialog
                if not d:return
                v=d.view;v.fit_image();original=v.reference;key=v.pixmap_item.pixmap().cacheKey()
                state['calibration_dpr']=d.devicePixelRatioF()
                dx,dy=drag(v,(150,original.ground_y),(170,original.ground_y-30),'ground')
                assert v.reference.origin==(original.origin_x,original.ground_y+dy)
                original=v.reference
                dx,dy=drag(v,(original.origin_x,250),(original.origin_x-15,290),'y_axis')
                assert v.reference.origin==(original.origin_x+dx,original.ground_y)
                original=v.reference
                dx,dy=drag(v,original.origin,(original.origin_x+18,original.ground_y-24),'origin')
                assert v.reference.origin==(original.origin_x+dx,original.ground_y+dy)
                original=v.reference
                QTest.keyClick(v,Qt.Key.Key_Left);QTest.keyClick(v,Qt.Key.Key_Up,Qt.KeyboardModifier.ShiftModifier)
                assert v.reference.origin==(original.origin_x-1,original.ground_y-10)
                d.x.setValue(764);d.y.setValue(1218)
                assert v.pixmap_item.pixmap().cacheKey()==key and v.pixmap_item.pos()==QPointF(0,0)
                assert np.array_equal(v.original_pixels,state['idle_pixels'])
                d.grab().save(str(output/'reference-calibration.png'))
                state['reference']=v.reference;state['idle_id']=p.animation_id
                d.save_button.click();advance('locked_idle')
            elif phase=='locked_idle':
                if not editor_ready():return
                assert p.character_reference==state['reference'] and p.character_reference.locked
                assert e.drag_scope.currentData()=='animation'
                # Offset on the reference animation itself must also be excluded from its ghost.
                window.set_animation_offset(9,0);advance('idle_offset')
            elif phase=='idle_offset':
                if not editor_ready():return
                assert np.array_equal(e.canvas.ghost_pixels,state['idle_pixels'])
                folder=output/'Run';folder.mkdir()
                for i in range(6):save_rgba(folder/f'{i:04d}.png',translate_rgba(state['idle_pixels'],30+i*3,-i*2))
                state['run_folder']=folder
                window.import_sequence(folder);advance('confirm_run')
            elif phase=='confirm_run':
                if not window.sequence_dialog:return
                window.sequence_dialog.submit();advance('run_imported')
            elif phase=='run_imported':
                if not window.built:return
                assert p.character_reference==state['reference'] and not p.animation_transform.active
                assert p.select_animation(state['idle_id']).animation_transform==AnimationTransform(9,0)
                p.sprite_cell.canvas_mode='normalize_source';p.sprite_cell.target_width=p.sprite_cell.target_height=512
                p.export_settings.columns=3
                window.open_editor();advance('run_editor')
            elif phase=='run_editor':
                if not editor_ready():return
                assert p.layout.width==512 and p.layout.normalize_scale==(1/3,1/3)
                assert e.canvas.character_reference==state['reference']
                state['run_ghost']=e.canvas.ghost_pixels
                e.canvas.fit_image()
                # At fit zoom the screen delta is converted back to project canvas pixels.
                before=p.animation_transform
                dx,dy=drag(e.canvas,(254,300),(250,302))
                assert p.animation_transform==AnimationTransform(before.offset_x+dx*3,before.offset_y+dy*3)
                assert p.character_reference==state['reference'] and not p.timeline_edit.frame_overrides
                advance('keyboard')
            elif phase=='keyboard':
                if not editor_ready():return
                before=p.animation_transform
                QTest.keyClick(e.canvas,Qt.Key.Key_Left)
                assert p.animation_transform==AnimationTransform(before.offset_x-1,before.offset_y)
                advance('shift_key')
            elif phase=='shift_key':
                if not editor_ready():return
                before=p.animation_transform
                QTest.keyClick(e.canvas,Qt.Key.Key_Down,Qt.KeyboardModifier.ShiftModifier)
                assert p.animation_transform==AnimationTransform(before.offset_x,before.offset_y+10)
                window.set_animation_offset(-12,4);advance('run_offset')
            elif phase=='run_offset':
                if not editor_ready():return
                assert np.array_equal(e.canvas.ghost_pixels,state['run_ghost'])
                assert p.character_reference==state['reference']
                assert not p.timeline_edit.frame_overrides
                assert e.inspector.widget(0).horizontalScrollBar().maximum()==0
                window.grab().save(str(output/'reference-run-editor.png'))
                state['live']=e.provider
                window.undo_edit();advance('undo')
            elif phase=='undo':
                if not editor_ready():return
                assert p.animation_transform!=AnimationTransform(-12,4)
                assert p.character_reference==state['reference']
                window.redo_edit();advance('redo')
            elif phase=='redo':
                if not editor_ready():return
                assert p.animation_transform==AnimationTransform(-12,4)
                window.build_sprites();advance('built')
            elif phase=='built':
                if not window.built:return
                final=FinalFrameProvider(p,window.cache_dir)
                for i in range(6):assert np.array_equal(final.get_final_frame(i),state['live'].get_final_frame(i))
                window.grab().save(str(output/'reference-sprite.png'))
                state['review']=window.open_animation_preview();advance('preview')
            elif phase=='preview':
                review=state['review']
                if review.worker or review.last_pixels is None:return
                assert np.array_equal(review.last_pixels,state['live'].get_final_frame(0))
                review.grab().save(str(output/'reference-animation-preview.png'))
                review.toggle_play();advance('playing')
            elif phase=='playing':
                review=state['review']
                if review.index<3:return
                review.toggle_play();review.close()
                window.export_to(output/'export',godot=True);advance('exported')
            elif phase=='exported':
                export_equal(state['live'])
                window.save_project(output/'ReferenceReview.aivsprite');advance('saved')
            elif phase=='saved':
                loaded=Project.load(output/'ReferenceReview.aivsprite')
                assert loaded.character_reference==state['reference'] and loaded.animation_transform==AnimationTransform(-12,4)
                assert [frame_path(state['idle_cache']/'keyed_frames',i).stat().st_mtime_ns for i in range(6)]==state['key_times']
                assert np.array_equal(read_rgba(frame_path(state['idle_cache']/'keyed_frames',0)),state['idle_pixels'])
                window.open_project(output/'ReferenceReview.aivsprite');advance('reopened')
            elif phase=='reopened':
                if not window.built:return
                assert p.character_reference==state['reference'] and p.animation_transform==AnimationTransform(-12,4)
                export_equal(FinalFrameProvider(p,window.cache_dir))
                window.open_editor();advance('edit_reference')
            elif phase=='edit_reference':
                if not editor_ready():return
                window.open_character_reference();advance('cancel_reference')
            elif phase=='cancel_reference':
                d=window.reference_dialog
                if not d:return
                # Editing from Run still loads Idle frame 0, independent of both animation offsets.
                assert np.array_equal(d.view.original_pixels,state['idle_pixels'])
                d.x.setValue(800);d.reject()
                assert p.character_reference==state['reference']
                expected=float(os.environ.get('QT_SCREEN_SCALE_FACTORS','').split(';')[0] or window.devicePixelRatioF())
                assert abs(window.devicePixelRatioF()-expected)<.001 and abs(state['calibration_dpr']-expected)<.001
                report=dict(status='passed',dpr=window.devicePixelRatioF(),calibration_dpr=state['calibration_dpr'],reference=asdict(p.character_reference),
                    animation_transform=asdict(p.animation_transform),input='1024x1536 video -> 1536x1536 project; Run RGBA sequence',
                    calibration_pixels_fixed=True,axis_drag_hit_test=True,keyboard_project_pixels=True,
                    shared_locked_axes=True,ghost_ignores_both_offsets=True,no_rekey=True,no_per_frame_overrides=True,
                    all_6_frames_preview_export_equal=True,sheet_size=[1536,1024],undo_redo=True,save_reopen=True)
                (output/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
                log.info('Character Reference acceptance passed: %s',report);finish(0)
        except Exception:
            log.exception('Character Reference acceptance failed in %s',state['phase']);finish(1)
    timer.timeout.connect(poll);timer.start();window._reference_smoke_timer=timer
