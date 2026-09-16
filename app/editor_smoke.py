"""Native/frozen editor acceptance: three workflows, exact PNG equality and reopen."""
import copy
from dataclasses import asdict
import json
import logging
from pathlib import Path
import time
import cv2
import numpy as np
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from app.core.project_workspace import create_project_workspace
from app.core.final_frame_provider import FinalFrameProvider
from app.models.project import Project
from app.utils.cache import save_rgba
from app.utils.rgba_image import read_rgba


def start_editor_smoke(app,window,output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    log=logging.getLogger('aivsprite.editor_smoke')
    folder=output/'attack';folder.mkdir()
    for i in range(39):
        frame=np.zeros((512,512,4),np.uint8)
        x=240+round(5*np.sin(i*.3))
        cv2.circle(frame,(x,145),42,(225,168,124,255),-1)
        cv2.rectangle(frame,(x-38,188),(x+38,338),(110+i*3,42,130,255),-1)
        cv2.rectangle(frame,(x-37,338),(x-7,438),(65,94,155,255),-1)
        cv2.rectangle(frame,(x+8,338),(x+37,438),(65,94,155,255),-1)
        cv2.line(frame,(x+35,220),(x+105,155+i*2),(199,226,234,255),12)
        save_rgba(folder/f'{i:04d}.png',frame)
    project,path=create_project_workspace(output,'EditorProject','standard')
    window.project,window.project_file=project,path
    window._loaded()
    window.library_controller.new_group(name="Attack")
    window._failed=lambda message:setattr(window,'last_error',message)
    state={'phase':'import','started':time.monotonic(),'reports':{}}
    timer=QTimer(window);timer.setInterval(30)

    def finish(code):
        timer.stop()
        if window.worker:window.worker.cancel();window.worker.wait();app.processEvents()
        window.editor.pause_preview();window.dirty=False;window.close();app.exit(code)

    def next_phase(name):
        state['phase']=name;state['ready']=time.monotonic()

    def compare_export(name,provider):
        dest=output/name
        metadata=json.loads((dest/'animation.json').read_text(encoding='utf-8'))
        assert metadata['frame_count']==len(provider)
        assert len(list((dest/'frames').glob('*.png')))==len(provider)
        for i in range(len(provider)):
            assert np.array_equal(read_rgba(dest/'frames'/f'{i:04d}.png'),provider.get_final_frame(i))
            assert metadata['frames'][i]['duration']==provider.duration(i)
        state['reports'][name]={'frames':len(provider),'duration':sum(provider.duration(i) for i in range(len(provider))),'pixel_equal':True}
        for dialog in list(window.export_notices):dialog.close()

    def poll():
        try:
            if window.last_error:raise AssertionError(window.last_error)
            if time.monotonic()-state['started']>150:raise AssertionError('Editor acceptance timed out')
            if window.worker:return
            if time.monotonic()-state.get('ready',0)<.15:return
            e=window.editor;p=window.project;phase=state['phase']
            if phase=='import':
                window.import_sequence(folder);next_phase('confirm')
            elif phase=='confirm':
                if not window.sequence_dialog:return
                window.sequence_dialog.submit();next_phase('imported')
            elif phase=='imported':
                if not window.built:return
                assert p.video.frame_count==39 and p.project_canvas==(512,512)
                p.export_settings.columns=10
                window.open_editor();next_phase('editor')
            elif phase in ('editor','twenty','flow2','offsets','edited','flow3','composite'):
                if not e.provider or e.worker or e.pending or e.last_pixels is None:return
                if phase=='editor':
                    assert window.steps.count()==5 and window.steps.currentIndex()==2
                    assert e.canvas.isVisible() and e.timeline.isVisible()
                    assert not window.view_toolbar_widget.isVisible()
                    assert e.inspector.widget(0).horizontalScrollBar().maximum()==0
                    assert e.tracks.columnViewportPosition(2)+e.tracks.columnWidth(2)<=e.tracks.viewport().width()+2, ([e.tracks.columnWidth(c) for c in range(3)],e.tracks.viewport().width())
                    window.grab().save(str(output/'editor-39.png'))
                    e.action('select_all');e.target_count.setValue(20)
                    e.curve.setCurrentIndex(e.curve.findData('ease_in_out'))
                    e.inspector.widget(0).ensureWidgetVisible(e.apply_count_button)
                    e.apply_count_button.click();next_phase('twenty')
                elif phase=='twenty':
                    assert len(e.provider)==20 and e.provider.source_index(0)==0 and e.provider.source_index(19)==38
                    window.grab().save(str(output/'editor-20-ease.png'))
                    state['first_preview']=e.provider
                    window.export_to(output/'count20',godot=True);next_phase('export20')
                elif phase=='flow2':
                    assert len(e.provider)==39
                    ids=[f.id for f in p.timeline_edit.frames()];state['original_ids']=ids
                    e.timeline.select_ids([ids[12]]);e.select(12);next_phase('offsets')
                elif phase=='offsets':
                    e.canvas.actual_size()
                    start=e.canvas.mapFromScene(250,250);end=e.canvas.mapFromScene(244,264)
                    QTest.mousePress(e.canvas.viewport(),Qt.MouseButton.LeftButton,pos=start)
                    QTest.mouseMove(e.canvas.viewport(),end)
                    QTest.mouseRelease(e.canvas.viewport(),Qt.MouseButton.LeftButton,pos=end)
                    assert p.timeline_edit.frame_overrides[state['original_ids'][12]].offset_x==-6
                    e.timeline.select_ids([state['original_ids'][13]])
                    e.transform_group.setChecked(True);e.x.setValue(-3);e.y.setValue(8);e.apply_transform()
                    e.timeline.select_ids(state['original_ids'][3:6]);e.action('delete')
                    e.timeline.select_ids([state['original_ids'][8]]);e.action('copy');e.paste(True)
                    e.timeline.select_ids([f.id for f in p.timeline_edit.frames()[-5:]]);e.action('reverse')
                    next_phase('edited')
                elif phase=='edited':
                    assert len(e.provider)==37
                    e.onion.setChecked(True);e.ghost.setChecked(True)
                    next_phase('ghost')
                elif phase=='flow3':
                    ids=[f.id for f in p.timeline_edit.frames()[:4]]
                    e.timeline.select_ids(ids);e.action('copy');e.paste(True)
                    e.action('reverse')
                    ids=[f.id for f in p.timeline_edit.frames()[10:20]]
                    e.timeline.select_ids(ids);e.curve.setCurrentIndex(e.curve.findData('linear'));e.speed.setValue(2);e.retime('speed')
                    ids=[f.id for f in p.timeline_edit.frames()[:4]]
                    e.timeline.select_ids(ids);e.action('copy')
                    e.track_target.setCurrentIndex(e.track_target.findData('effects'));e.ripple.setChecked(False);e.timeline.set_time(.4);e.paste()
                    e.x.setValue(24);e.y.setValue(-8);e.opacity.setValue(.4);e.apply_transform()
                    e.track_target.setCurrentIndex(e.track_target.findData('reference'));e.timeline.set_time(0);e.paste()
                    ids=[f.id for f in p.timeline_edit.frames('main')[:4]]
                    e.timeline.select_ids(ids);e.curve.setCurrentIndex(e.curve.findData('bezier'))
                    e.curve_editor.controls=(.2,.05,.8,.95);e._bezier_from_plot(e.curve_editor.controls)
                    e.duration.setValue(4/24);e.retime('duration')
                    next_phase('composite')
                elif phase=='composite':
                    e.select_time(.4)
                    e.transform_group.setChecked(False)
                    window.grab().save(str(output/'editor-multitrack.png'))
                    state['final_preview']=e.provider
                    window.export_to(output/'multitrack',godot=True);next_phase('export_final')
            elif phase=='export20':
                compare_export('count20',state['first_preview'])
                window.open_editor();next_phase('reenter')
            elif phase=='reenter':
                if not e.provider or e.worker or e.pending:return
                window.undo_edit();next_phase('flow2')
            elif phase=='ghost':
                if e.worker or e.pending:return
                assert not np.array_equal(e.last_pixels,e.provider.get_final_frame(e.index))
                window.grab().save(str(output/'editor-onion.png'))
                e.onion.setChecked(False);e.ghost.setChecked(False)
                state['second_preview']=e.provider
                window.export_to(output/'manual37',godot=True);next_phase('export37')
            elif phase=='export37':
                compare_export('manual37',state['second_preview'])
                window.open_editor();next_phase('flow3')
            elif phase=='export_final':
                compare_export('multitrack',state['final_preview'])
                state['snapshot']=asdict(p.timeline_edit)
                window.save_project(output/'review.aivsprite');next_phase('saved')
            elif phase=='saved':
                assert asdict(Project.load(output/'review.aivsprite').timeline_edit)==state['snapshot']
                window.open_project(output/'review.aivsprite');next_phase('reopened')
            elif phase=='reopened':
                if not window.built:return
                assert asdict(p.timeline_edit)==state['snapshot']
                final=FinalFrameProvider(p,window.cache_dir)
                compare_export('multitrack',final)
                report=dict(status='passed',dpr=window.devicePixelRatioF(),workflow_pages=window.steps.count(),source_frames=p.video.frame_count,
                    profiles_preserved=p.character_profile is None,source_files_preserved=len(list(folder.glob('*.png')))==39,
                    save_reopen=True,workflows=state['reports'])
                (output/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
                log.info('Editor acceptance passed: %s',report)
                finish(0)
        except Exception:
            log.exception('Editor acceptance failed in %s',state['phase']);finish(1)
    timer.timeout.connect(poll);timer.start();window._editor_smoke_timer=timer
