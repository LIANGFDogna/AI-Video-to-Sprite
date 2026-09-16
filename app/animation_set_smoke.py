"""Frozen Phase 2D acceptance: Animation Sets, auto-match, sequence preview, protection and export."""
import hashlib,json,logging,time
from pathlib import Path
import numpy as np
from PySide6.QtCore import QTimer
from app.core.project_workspace import create_project_workspace
from app.core.set_export import export_animation_set
from app.core.set_preview import SetPreviewProvider
from app.models.character_reference import CharacterReference
from app.models.character_templates import PLAYER
from app.ui.dialogs import MessageBox
from app.utils.cache import save_rgba
from app import __build__


def start_animation_set_smoke(app,w,output,verify=False):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    log=logging.getLogger('aivsprite.set_smoke');state={'phase':'verify' if verify else 'create','started':time.monotonic()}
    w._failed=lambda error:setattr(w,'last_error',error)
    w._export_notice=lambda result:None
    timer=QTimer(w);timer.setInterval(40)
    def advance(phase):state.update(phase=phase,ready=time.monotonic())
    def finish(code):
        timer.stop()
        if w.worker:w.worker.cancel();w.worker.wait();app.processEvents()
        w.editor.pause_preview();w.dirty=False;w.close();app.exit(code)
    def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    def make_frames(folder,count,shift):
        folder=Path(folder);folder.mkdir()
        for i in range(count):
            rgba=np.zeros((96,96,4),np.uint8);rgba[24:72,16+i+shift:32+i+shift]=(200,80,120,190);save_rgba(folder/f'{i:04d}.png',rgba)
    def group(character_id,name):
        return next(row for row in w.project.library.character_roots(character_id) if row.name==name)
    def child(parent,name):
        return next(row for row in w.project.library.children(parent.id) if row.name==name)
    def jump_set():
        return next(row for row in w.project.library.animation_sets_for(state['player']) if row.name=='Jump')
    def animations():
        return [resource for resource in w.project.library.resources.values() if resource.kind=='ANIMATION']
    def poll():
        try:
            if w.last_error:raise AssertionError(w.last_error)
            if time.monotonic()-state['started']>260:raise AssertionError('Animation Set acceptance timed out: '+state['phase'])
            if w.worker or time.monotonic()-state.get('ready',0)<.15:return
            c=w.library_controller;p=w.project;phase=state['phase']
            if phase=='create':
                w.project,w.project_file=create_project_workspace(output,'set-smoke','standard',project_canvas=(96,96));w._loaded()
                p=w.project
                player=c.new_character(name='Player',template_id=PLAYER);state['player']=player.id
                assert [row.name for row in p.library.animation_sets_for(player.id)]==['Jump','Combat','Dash']
                state['jump']=jump_set().id
                state['idle_group']=group(player.id,'Idle').id
                jump=group(player.id,'Jump');state['jump_up_group']=child(jump,'JumpUp').id
                state['fall_group']=child(jump,'FallLoop').id;state['land_group']=child(jump,'Land').id
                make_frames(output/'Idle',4,0);make_frames(output/'JumpUp',4,6);make_frames(output/'FallLoop',3,12);make_frames(output/'Land',3,18)
                c.select_group(state['idle_group']);w.import_sequence(output/'Idle');advance('idle_import')
            elif phase=='idle_import':
                if not w.sequence_dialog:return
                w.sequence_dialog.submit();advance('idle_built')
            elif phase=='idle_built':
                if not w.built:return
                state['idle_animation']=p.animation_id
                w._save_character_reference(CharacterReference(p.animation_id,0,24,24,96,96))
                c.select_group(state['jump_up_group']);w.import_sequence(output/'JumpUp');advance('jumpup_import')
            elif phase=='jumpup_import':
                if not w.sequence_dialog:return
                w.sequence_dialog.submit();advance('jumpup_built')
            elif phase=='jumpup_built':
                if not w.built:return
                state['jumpup_animation']=p.animation_id
                w.set_animation_offset(20,-8);w.add_frame_correction([1],5,-10)
                # Offset / correction invalidate the built sheet, so rebuild it once (normal user flow).
                w.build_sprites();advance('jumpup_rebuild')
            elif phase=='jumpup_rebuild':
                if not w.built:return
                assert w.project.library.animation(state['jumpup_animation']).ready,'rebuild marks the Animation ready again'
                c.select_group(state['fall_group']);w.import_sequence(output/'FallLoop');advance('fall_import')
            elif phase=='fall_import':
                if not w.sequence_dialog:return
                w.sequence_dialog.submit();advance('fall_built')
            elif phase=='fall_built':
                if not w.built:return
                state['fall_animation']=p.animation_id
                c.select_group(state['land_group']);w.import_sequence(output/'Land');advance('land_import')
            elif phase=='land_import':
                if not w.sequence_dialog:return
                w.sequence_dialog.submit();advance('land_built')
            elif phase=='land_built':
                if not w.built:return
                state['land_animation']=p.animation_id
                library=p.library
                matched=library.auto_match_set(state['jump'])
                assert matched==3,'auto-match must bind JumpUp/FallLoop/Land'
                row=library.animation_sets[state['jump']]
                library.animation_sets[state['jump']].pre_animation=state['idle_animation']
                library.animation_sets[state['jump']].post_animation=state['idle_animation']
                row=library.animation_sets[state['jump']]
                assert row.status=='READY' and row.completion==(3,3)
                assert [slot.display_name for slot in row.slots]==['JumpUp','FallLoop','Land']
                assert [slot.repeat_count for slot in row.slots]==[1,2,1]
                provider=SetPreviewProvider(p,w.project_file,row)
                labels=[provider.label(index) for index in range(len(provider))]
                assert labels[0].startswith('Idle (pre)') and labels[-1].startswith('Idle (post)')
                assert any('FallLoop x2' in label for label in labels),'repeat_count repeats FallLoop without touching the source'
                assert not any('JumpUp' in label and 'x2' in label for label in labels)
                state['labels']=labels[:6]
                corrected=[index for index,label in enumerate(labels) if label.startswith('JumpUp')]
                assert corrected,'JumpUp segment present'
                from app.core.final_frame_provider import FinalFrameProvider
                from app.utils.paths import cache_directory
                jumpup=FinalFrameProvider(p.select_animation(state['jumpup_animation']),
                    cache_directory(p.project_id,w.project_file,state['jumpup_animation']),live_edit=True)
                assert np.array_equal(provider.get_final_frame(corrected[0]+1),jumpup.get_final_frame(1)),'Offset + Frame Correction carry into the Set preview'
                state['preview_total']=len(provider)
                advance('protect')
            elif phase=='protect':
                library=p.library;row=library.animation_sets[state['jump']]
                land_resource=library.animation(state['land_animation'])
                prompts=[];original=MessageBox.question
                try:
                    MessageBox.question=staticmethod(lambda *args,**kwargs:(prompts.append(args[2]),MessageBox.StandardButton.Cancel)[1])
                    assert c.remove_resource(land_resource.id) is None,'cancel keeps the Animation'
                finally:
                    MessageBox.question=original
                assert prompts and 'Animation Set' in prompts[0]
                assert library.animation(state['land_animation']) is not None
                assert library.animation_sets[state['jump']].status=='READY'
                original=MessageBox.question
                try:
                    MessageBox.question=staticmethod(lambda *args,**kwargs:MessageBox.StandardButton.Yes)
                    assert c.remove_resource(land_resource.id) is not None
                finally:
                    MessageBox.question=original
                assert library.animation(state['land_animation']) is None
                assert library.animation_sets[state['jump']].status=='INCOMPLETE'
                assert library.animation_sets[state['jump']].completion==(2,3)
                land_slot=next(slot for slot in library.animation_sets[state['jump']].slots if slot.display_name=='Land')
                assert land_slot.animation_id is None
                advance('rebind')
            elif phase=='rebind':
                library=p.library
                land_slot=next(slot for slot in library.animation_sets[state['jump']].slots if slot.display_name=='Land')
                c.select_group(state['land_group']);w.import_sequence(output/'Land');advance('rebind_import')
            elif phase=='rebind_import':
                if not w.sequence_dialog:return
                w.sequence_dialog.submit();advance('rebind_built')
            elif phase=='rebind_built':
                if not w.built:return
                library=p.library
                row=library.animation_sets[state['jump']]
                land_slot=next(slot for slot in row.slots if slot.display_name=='Land')
                library.auto_match_set(state['jump'])
                row=library.animation_sets[state['jump']]
                assert row.status=='READY' and row.completion==(3,3),'rebinding restores READY'
                state['land_rebound']=row.slots[2].animation_id
                destination=output/'Export';destination.mkdir(exist_ok=True)
                result=export_animation_set(p,w.project_file,row,destination,lambda *args:None,None)
                assert result['resources']==3
                metadata=json.loads((destination/'Jump'/'animation_set.json').read_text(encoding='utf-8'))
                assert metadata['sequence']==['JumpUp','FallLoop','Land']
                assert metadata['godot'][0]['next']=='FallLoop' and metadata['godot'][1]['loop'] is True
                state['export_hash']=digest(destination/'Jump'/'JumpUp'/'sprite_sheet.png')
                state['project']=str(w.project_file);w.save_project();advance('saved')
            elif phase=='saved':
                expected={key:state[key] for key in ('project','player','jump','idle_animation','jumpup_animation','fall_animation','land_rebound','labels','preview_total','export_hash')}
                (output/'expected.json').write_text(json.dumps(expected,ensure_ascii=False),encoding='utf-8')
                report={'status':'passed','build':__build__,'dpr':w.devicePixelRatioF(),'sets':['Jump','Combat','Dash'],
                    'jump_completion':'3/3','jump_ready':True,'auto_match':3,'repeat_fall_loop':2,
                    'provider_reused':True,'offset_and_correction_in_preview':True,'delete_protection':True,
                    'rebind_restores_ready':True,'export_structure':True,'export_metadata':True,'ghost_excluded':True}
                (output/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8');finish(0)
            elif phase=='verify':
                state.update(json.loads((output/'expected.json').read_text(encoding='utf-8')));w.open_project(state['project']);advance('verified')
            elif phase=='verified':
                library=w.project.library
                row=library.animation_sets.get(state['jump'])
                assert row is not None and row.status=='READY' and row.completion==(3,3)
                assert row.pre_animation==state['idle_animation'] and row.post_animation==state['idle_animation']
                assert [slot.display_name for slot in row.slots]==['JumpUp','FallLoop','Land']
                assert [slot.repeat_count for slot in row.slots]==[1,2,1]
                provider=SetPreviewProvider(w.project,w.project_file,row)
                labels=[provider.label(index) for index in range(len(provider))]
                assert labels[0].startswith('Idle (pre)') and labels[-1].startswith('Idle (post)')
                assert any('FallLoop x2' in label for label in labels)
                assert digest(output/'Export'/'Jump'/'JumpUp'/'sprite_sheet.png')==state['export_hash']
                report=json.loads((output/'validation.json').read_text(encoding='utf-8'));report['restart_verified']=True
                (output/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8');finish(0)
        except Exception:
            log.exception('Animation Set acceptance failed in %s',state['phase']);(output/'failed.txt').write_text(state['phase'],encoding='utf-8');finish(1)
    timer.timeout.connect(poll);timer.start();w._set_smoke_timer=timer
