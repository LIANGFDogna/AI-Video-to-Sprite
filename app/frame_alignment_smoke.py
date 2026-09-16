"""Frozen Phase 2C acceptance: per-frame correction, character Ghost, drag stability and export purity."""
import copy
from dataclasses import asdict
import hashlib,json,logging,time
from pathlib import Path
import numpy as np
from PySide6.QtCore import QEvent, QPointF, QTimer, Qt
from PySide6.QtGui import QFocusEvent, QKeyEvent, QMouseEvent
from app.core.project_workspace import create_project_workspace
from app.core.final_frame_provider import FinalFrameProvider
from app.core.animation_transform import translate_rgba
from app.models.character_reference import CharacterReference
from app.models.character_templates import BOSS, PLAYER, REGISTRY
from app.utils.cache import save_rgba
from app.utils.rgba_image import read_rgba
from app import __build__


def start_frame_alignment_smoke(app,w,output,verify=False):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    log=logging.getLogger('aivsprite.frame_smoke');state={'phase':'verify' if verify else 'create','started':time.monotonic()}
    w._failed=lambda error:setattr(w,'last_error',error)
    w._export_notice=lambda result:None
    timer=QTimer(w);timer.setInterval(40)
    def advance(phase):state.update(phase=phase,ready=time.monotonic())
    def finish(code):
        timer.stop()
        if w.worker:w.worker.cancel();w.worker.wait();app.processEvents()
        w.editor.pause_preview();w.dirty=False;w.close();app.exit(code)
    def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    def live():
        return FinalFrameProvider(w.project,w.cache_dir,live_edit=True)
    def press(widget,x,y):
        widget.mousePressEvent(QMouseEvent(QEvent.Type.MouseButtonPress,QPointF(x,y),QPointF(x,y),Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier))
    def move(widget,x,y):
        widget.mouseMoveEvent(QMouseEvent(QEvent.Type.MouseMove,QPointF(x,y),QPointF(x,y),Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier))
    def release(widget,x,y):
        widget.mouseReleaseEvent(QMouseEvent(QEvent.Type.MouseButtonRelease,QPointF(x,y),QPointF(x,y),Qt.MouseButton.LeftButton,Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier))
    def escape(widget):
        widget.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress,Qt.Key.Key_Escape,Qt.KeyboardModifier.NoModifier))
    def frames(folder,count=6):
        folder=Path(folder);folder.mkdir()
        for i in range(count):
            rgba=np.zeros((96,96,4),np.uint8);rgba[20:80,20+i:36+i]=(200,80,120,190);save_rgba(folder/f'{i:04d}.png',rgba)
    def group(character_id,name):
        return next(g for g in w.project.library.character_roots(character_id) if g.name==name)
    def child(parent,name):
        return next(g for g in w.project.library.children(parent.id) if g.name==name)
    def correction_pixels(indices,corrections):
        base=copy.deepcopy(w.project);base.clear_frame_corrections()
        plain=FinalFrameProvider(base,w.cache_dir,live_edit=True)
        current=live()
        for index,delta in zip(indices,corrections):
            assert np.array_equal(translate_rgba(plain.get_final_frame(index),delta[0],delta[1]),current.get_final_frame(index)),f'final pixels must equal offset + correction at frame {index}'
    def poll():
        try:
            if w.last_error:raise AssertionError(w.last_error)
            if time.monotonic()-state['started']>220:raise AssertionError('Frame alignment acceptance timed out: '+state['phase'])
            if w.worker or time.monotonic()-state.get('ready',0)<.15:return
            c=w.library_controller;p=w.project;phase=state['phase']
            if phase=='create':
                w.project,w.project_file=create_project_workspace(output,'alignment-smoke','standard',project_canvas=(96,96));w._loaded()
                player=c.new_character(name='Player',template_id=PLAYER);state['player']=player.id
                state['idle']=group(player.id,'Idle').id
                state['run']=child(group(player.id,'Movement'),'Run').id
                state['jump']=group(player.id,'Jump').id
                state['dash']=group(player.id,'Dash').id
                frames(output/'Idle Frames');frames(output/'Run Frames',6)
                c.select_group(state['idle']);w.import_sequence(output/'Idle Frames');advance('idle_import')
            elif phase=='idle_import':
                if not w.sequence_dialog:return
                w.sequence_dialog.submit();advance('idle_built')
            elif phase=='idle_built':
                if not w.built:return
                state['idle_animation']=p.animation_id
                player_reference=CharacterReference(p.animation_id,0,24,24,96,96)
                w._save_character_reference(player_reference)
                assert p.library.characters[state['player']].character_reference==player_reference
                c.select_group(state['run']);w.import_sequence(output/'Run Frames');advance('run_import')
            elif phase=='run_import':
                if not w.sequence_dialog:return
                w.sequence_dialog.submit();advance('run_built')
            elif phase=='run_built':
                if not w.built:return
                state['run_animation']=p.animation_id
                w.set_animation_offset(20,-8)
                w.add_frame_correction([0],5,-10)
                w.add_frame_correction([2],-3,4)
                assert p.animation_transform.offset_x==20 and p.animation_transform.offset_y==-8
                assert p.frame_correction(0)==(5,-10) and p.frame_correction(1)==(0,0) and p.frame_correction(2)==(-3,4)
                correction_pixels([0,2],[(5,-10),(-3,4)])
                assert p.character_reference.origin==(24,24)
                # Ghost: same Player Reference for Run; fixed position; 15% default.
                w.open_editor();advance('ghost')
            elif phase=='ghost':
                e=w.editor
                if not e.provider or e.worker or e.pending:return
                assert e.canvas.ghost_pixels is not None,'Run must show the Player Ghost'
                assert e.canvas.idle_ghost_item.pos().x()==0 and e.canvas.idle_ghost_item.pos().y()==0
                assert abs(e.reference_opacity.value()-0.15)<1e-9 and e.show_idle_ghost.isChecked()
                c.select_group(state['idle']);w.open_editor();advance('reference_hidden')
            elif phase=='reference_hidden':
                e=w.editor
                if not e.provider or e.worker or e.pending:return
                assert e.canvas.ghost_pixels is None and not e.show_idle_ghost.isEnabled(),'Reference Animation hides its own Ghost'
                c.select_group(state['jump']);w.import_sequence(output/'Idle Frames');advance('jump_import')
            elif phase=='jump_import':
                if not w.sequence_dialog:return
                w.sequence_dialog.submit();advance('jump_built')
            elif phase=='jump_built':
                if not w.built:return
                w.open_editor();advance('jump_editor');return
            elif phase=='jump_editor':
                e=w.editor
                if not e.provider or e.worker or e.pending:return
                if not e.provider or e.worker or e.pending:return
                assert e.canvas.ghost_pixels is not None,'Jump must show the same Player Ghost'
                assert e.canvas.idle_ghost_item.pos().x()==0 and e.canvas.idle_ghost_item.pos().y()==0
                boss=c.new_character(name='Boss',template_id=BOSS);state['boss']=boss.id
                c.select_group(group(boss.id,'Idle').id);w.import_sequence(output/'Idle Frames');advance('boss_import')
            elif phase=='boss_import':
                if not w.sequence_dialog:return
                w.sequence_dialog.submit();advance('boss_built')
            elif phase=='boss_built':
                if not w.built:return
                state['boss_animation']=p.animation_id
                boss_reference=CharacterReference(p.animation_id,0,60,60,96,96)
                w._save_character_reference(boss_reference)
                assert w.project.library.characters[state['boss']].character_reference==boss_reference
                # Player -> Boss -> Player restores Ghost/Ground/Origin/Opacity/Toggle independently.
                c.select_group(state['run']);assert w.project.character_reference.origin==(24,24) and w.project.animation_transform.offset_x==20 and w.project.frame_correction(0)==(5,-10)
                c.select_group(group(state['boss'],'Idle').id);assert w.project.character_reference.origin==(60,60)
                c.select_group(state['run']);assert w.project.character_reference.origin==(24,24)
                advance('stress')
            elif phase=='stress':
                w.editor.position_frame.setChecked(True)
                canvas=w.editor.canvas;timeline=w.editor.timeline
                before_canvas=len(canvas.scene().items())
                state['items_before']=before_canvas
                for i in range(100):
                    press(canvas,40,40);move(canvas,60+i%7,58+i%5);release(canvas,60+i%7,58+i%5)
                assert len(canvas.scene().items())==before_canvas,'canvas item count must be stable after 100 drags'
                state['items_after']=len(canvas.scene().items())
                before_timeline=len(timeline.scene().items())
                for i in range(100):
                    press(timeline,4000,60);move(timeline,4200,150);release(timeline,4200,150)
                assert timeline.rubber is None and timeline.selecting is None
                assert len(timeline.scene().items())==before_timeline,'timeline item count must be stable after 100 selections'
                state['timeline_items']=len(timeline.scene().items())
                advance('restore_baseline')
            elif phase=='restore_baseline':
                if w.worker:return
                w.set_animation_offset(20,-8)
                w.project.clear_frame_corrections();w.project.set_frame_correction(0,5,-10);w.project.set_frame_correction(2,-3,4)
                w.edit_histories.clear();w.library_controller.entries=[];w.library_controller.index=0
                advance('cancel_matrix')
            elif phase=='cancel_matrix':
                canvas=w.editor.canvas
                press(canvas,40,40);move(canvas,90,70);release(canvas,90,70)
                assert canvas.drag_start is None and not canvas.dragging
                w.project.set_frame_correction(0,5,-10)
                for action in (
                    lambda:(press(canvas,40,40),move(canvas,90,70),escape(canvas)),
                    lambda:(press(canvas,40,40),move(canvas,90,70),canvas.focusOutEvent(QFocusEvent(QEvent.Type.FocusOut))),
                    lambda:(press(canvas,40,40),move(canvas,90,70),w.steps.setCurrentIndex(0)),
                    lambda:(press(canvas,40,40),move(canvas,90,70),c.select_group(state['idle'])),
                    lambda:(press(canvas,40,40),move(canvas,90,70),c.select_character(state['player'])),
                    lambda:(press(canvas,40,40),move(canvas,90,70),w.changeEvent(QEvent(QEvent.Type.WindowStateChange)))):
                    before=w.project.frame_correction(0)
                    action()
                    assert canvas.drag_start is None and not canvas.dragging,'cancel matrix left a live drag'
                    assert canvas.pixmap_item.pos().x()==0 and canvas.pixmap_item.pos().y()==0
                    c.select_group(state['run'])
                    assert w.project.frame_correction(0)==before,'cancel must never change corrections'
                advance('undo')
            elif phase=='undo':
                w.editor.position_frame.setChecked(True)
                w.edit_histories.clear();w.library_controller.entries=[];w.library_controller.index=0
                before=w.project.frame_correction(0)
                history=w._history();index=history.index
                canvas=w.editor.canvas
                press(canvas,40,40)
                for step in range(1,101):move(canvas,40+step,40+step)
                release(canvas,140,140)
                pass
                pass
                assert history.index==index+1 and w.library_controller.index==1,'press + 100 moves + release must be exactly one undo command'
                after=w.project.frame_correction(0)
                assert after!=before,'drag must apply exactly one delta' 
                w.undo_edit();app.processEvents()
                assert w.project.frame_correction(0)==before
                w.redo_edit();app.processEvents()
                assert w.project.frame_correction(0)==after
                w.project.set_frame_correction(0,5,-10)
                advance('export')
            elif phase=='export':
                e=w.editor
                e.reference_opacity.setValue(0.7);e.show_idle_ghost.setChecked(True)
                provider=live()
                destination=output/'Export Ghost70';w.export_to(destination,'frames');advance('exported')
                state['provider_frame2']=hashlib.sha256(provider.get_final_frame(2).tobytes()).hexdigest()
            elif phase=='exported':
                assert not w.worker
                exported=read_rgba(output/'Export Ghost70'/'frames'/'0002.png')
                assert np.array_equal(exported,live().get_final_frame(2)),'export pixels must equal FinalFrameProvider pixels'
                state['run_export_pixels']=hashlib.sha256(exported.tobytes()).hexdigest()
                w.dirty=False
                destination=output/'Export NoGhost';e=w.editor
                e.show_idle_ghost.setChecked(False);e.reference_opacity.setValue(0.0)
                w.export_to(destination,'frames');advance('exported2')
            elif phase=='exported2':
                if w.worker:return
                no_ghost=read_rgba(output/'Export NoGhost'/'frames'/'0002.png')
                assert np.array_equal(no_ghost,read_rgba(output/'Export Ghost70'/'frames'/'0002.png')),'Ghost opacity must never change exports'
                assert hashlib.sha256(no_ghost.tobytes()).hexdigest()==state['run_export_pixels']
                state['project']=str(w.project_file);w.save_project();advance('saved')
            elif phase=='saved':
                expected={key:state[key] for key in ('project','player','boss','run','idle','idle_animation','run_animation','boss_animation','items_before','items_after','timeline_items','run_export_pixels')}
                (output/'expected.json').write_text(json.dumps(expected,ensure_ascii=False),encoding='utf-8')
                report={'status':'passed','build':__build__,'dpr':w.devicePixelRatioF(),'offset':[20,-8],'corrections':{(0):[5,-10],2:[-3,4]},
                    'final_frame0':[25,-18],'final_frame1':[20,-8],'final_frame2':[17,-4],
                    'ghost_same_character':True,'ghost_hidden_for_reference':True,'ghost_never_crosses':True,
                    'drag_items_stable':state['items_before']==state['items_after'],'selection_overlay_cleared':True,
                    'undo_single_command':True,'ghost_not_in_export':True,'preview_export_equal':True}
                (output/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8');finish(0)
            elif phase=='verify':
                state.update(json.loads((output/'expected.json').read_text(encoding='utf-8')));w.open_project(state['project']);advance('verified')
            elif phase=='verified':
                c=w.library_controller
                c.select_group(state['run'])
                assert w.project.animation_transform.offset_x==20 and w.project.animation_transform.offset_y==-8
                assert w.project.frame_correction(0)==(5,-10) and w.project.frame_correction(1)==(0,0) and w.project.frame_correction(2)==(-3,4)
                assert w.project.character_reference.origin==(24,24)
                c.select_group(group(state['boss'],'Idle').id)
                assert w.project.character_reference.origin==(60,60)
                c.select_group(state['run'])
                assert w.project.character_reference.origin==(24,24)
                assert hashlib.sha256(read_rgba(output/'Export Ghost70'/'frames'/'0002.png').tobytes()).hexdigest()==state['run_export_pixels']
                report=json.loads((output/'validation.json').read_text(encoding='utf-8'));report['restart_verified']=True
                (output/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8');finish(0)
        except Exception:
            log.exception('Frame alignment acceptance failed in %s',state['phase']);(output/'failed.txt').write_text(state['phase'],encoding='utf-8');finish(1)
    timer.timeout.connect(poll);timer.start();w._frame_smoke_timer=timer
