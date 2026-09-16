"""Frozen Group acceptance: two videos, sequence, sheet, task race, export and restart."""
import hashlib,json,logging,time,copy
from pathlib import Path
import cv2
import numpy as np
from PySide6.QtCore import QTimer
from app.core.project_workspace import create_project_workspace
from app.core.group_export import plan_group_export,export_group_plan
from app.core.final_frame_provider import FinalFrameProvider
from app.core.pipeline import Pipeline
from app.models.project import Project
from app.utils.cache import save_rgba
from app.utils.rgba_image import read_rgba
from app import __build__


def start_group_smoke(app,w,output,verify=False):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    log=logging.getLogger('aivsprite.group_smoke');state={'phase':'verify' if verify else 'create','started':time.monotonic()}
    w._failed=lambda error:setattr(w,'last_error',error)
    timer=QTimer(w);timer.setInterval(40)
    def advance(phase):state.update(phase=phase,ready=time.monotonic())
    def finish(code):
        timer.stop()
        if w.worker:w.worker.cancel();w.worker.wait();app.processEvents()
        w.editor.pause_preview();w.dirty=False;w.close();app.exit(code)
    def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    def editor_ready():return w.editor.provider and not w.editor.worker and not w.editor.pending
    def no_processing_switch(group):
        originals={name:getattr(Pipeline,name) for name in ('import_input','ensure_key','ensure_aligned','build')}
        def forbidden(*a,**kw):raise AssertionError('Group selection called a processing stage')
        try:
            for name in originals:setattr(Pipeline,name,forbidden)
            w.library_controller.select_group(group)
        finally:
            for name,method in originals.items():setattr(Pipeline,name,method)
    def poll():
        try:
            if w.last_error:raise AssertionError(w.last_error)
            if time.monotonic()-state['started']>160:raise AssertionError('Group acceptance timed out: '+state['phase'])
            if w.worker or time.monotonic()-state.get('ready',0)<.15:return
            c=w.library_controller;p=w.project;phase=state['phase']
            if phase=='create':
                assert not w.import_button.isEnabled()
                w.project,w.project_file=create_project_workspace(output,'中文 Group 项目','standard',project_canvas=(96,96));w._loaded()
                assert not w.project.library.groups and not w.import_button.isEnabled()
                root=c.new_group(name='MainCharacter');idle=c.new_group(root.id,'Idle');movement=c.new_group(root.id,'Movement');run=c.new_group(movement.id,'Run');jump=c.new_group(root.id,'Jump')
                state.update(root=root.id,idle=idle.id,movement=movement.id,run=run.id,jump=jump.id)
                for name in ('Idle A','Idle B'):
                    video=output/(name+'.mp4');writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'mp4v'),24,(96,96));assert writer.isOpened()
                    for i in range(5):
                        bgr=np.full((96,96,3),(0,255,0),np.uint8);cv2.rectangle(bgr,(36+i,25),(54+i,80),(90,50,220),-1);writer.write(bgr)
                    writer.release()
                sequence=output/'Run Frames';sequence.mkdir()
                for i in range(22):
                    rgba=np.zeros((96,96,4),np.uint8);rgba[20:80,20+i:35+i]=(220,55,90,190);save_rgba(sequence/f'{i:04d}.png',rgba)
                save_rgba(output/'Existing Sheet.png',np.full((96,192,4),(170,40,220,155),np.uint8))
                c.select_group(idle.id);w.import_video(output/'Idle A.mp4');advance('a_imported')
            elif phase=='a_imported':
                assert p.video.frame_count==5;state['a']=p.animation_id;w.process_key();advance('a_keyed')
            elif phase=='a_keyed':w.start_keyed_passthrough();advance('a_built')
            elif phase=='a_built':
                if not w.built:return
                state['a_sheet']=str(w.cache_dir/'sprite_sheet.png');state['a_hash']=digest(state['a_sheet'])
                w.import_video(output/'Idle B.mp4');advance('b_imported')
            elif phase=='b_imported':
                assert p.library.animation(state['a']).ready and p.library.animation_count(state['idle'])==2
                state['b']=p.animation_id;w.process_key();advance('b_keyed')
            elif phase=='b_keyed':w.start_keyed_passthrough();advance('b_built')
            elif phase=='b_built':
                if not w.built:return
                c.select_group(state['run']);w.import_sequence(output/'Run Frames');advance('sequence')
            elif phase=='sequence':
                if not w.sequence_dialog:return
                w.sequence_dialog.submit();advance('sequence_built')
            elif phase=='sequence_built':
                if not w.built:return
                state['run_animation']=p.animation_id;w.open_editor();advance('editor')
            elif phase=='editor':
                if not editor_ready():return
                w.editor.select(12);w.editor.timeline.pixels_per_second=1200;w.editor.preview_fps.setValue(12)
                state['run_pixel']=hashlib.sha256(w.editor.provider.get_final_frame(12).tobytes()).hexdigest()
                c.select_group(state['idle']);w.process_key();c.select_group(state['run']);advance('race')
            elif phase=='race':
                assert p.current_group_id==state['run'] and p.animation_id==state['run_animation']
                assert w.editor.index==12 and w.editor.timeline.pixels_per_second==1200
                assert hashlib.sha256(w.editor.provider.get_final_frame(12).tobytes()).hexdigest()==state['run_pixel']
                for group in (state['idle'],state['run'],state['jump']):no_processing_switch(group)
                c.import_sheet(output/'Existing Sheet.png')
                assert p.project_id==w.project.project_id and w.views.currentWidget() is w.asset_view
                w.grab().save(str(output/'group-sheet.png'));c.select_group(state['run']);advance('capture')
            elif phase=='capture':
                if not editor_ready():return
                w.grab().save(str(output/'group-editor.png'))
                assert w.library_panel.isVisible() and w.editor.index==12
                from app.ui.group_export_dialog import GroupExportDialog
                d=GroupExportDialog(w,True);d.show();app.processEvents();d.grab().save(str(output/'group-export.png'));d.reject()
                plan=plan_group_export(p,w.project_file,[state['root']]);destination=output/'Export';destination.mkdir()
                w._run(lambda progress,cancel:export_group_plan(plan,destination,progress,cancel),lambda result:state.update(export=result),'Exporting Groups')
                advance('exported')
            elif phase=='exported':
                assert len(list((output/'Export').rglob('sprite_sheet.png')))==4
                assert digest(state['a_sheet'])==state['a_hash']
                assert digest(output/'Export/MainCharacter/Idle/Idle A/sprite_sheet.png')==state['a_hash']
                assert digest(output/'Existing Sheet.png')==digest(output/'Export/MainCharacter/Jump/Existing Sheet/sprite_sheet.png')
                assert all(p.library.groups[g].status=='READY' for g in (state['idle'],state['run'],state['jump']))
                assert all(p.library.animation(a).ready for a in (state['a'],state['b'],state['run_animation']))
                assert (output/'Export/MainCharacter/Movement/Run/Run Frames/animation.json').is_file()
                sheet=read_rgba(output/'Export/MainCharacter/Movement/Run/Run Frames/sprite_sheet.png')
                log.info('Group pixel check: group=%s animation=%s layout=%s has_final=%s cache=%s json=%s',p.current_group_id,p.animation_id,bool(p.layout),p.has_final_edits,w.cache_dir,sorted(x.name for x in w.cache_dir.glob('*.json')))
                assert p.layout is not None,'Run layout missing; group=%s animation=%s cache=%s'%(p.current_group_id,p.animation_id,w.cache_dir)
                provider=FinalFrameProvider(p,w.cache_dir,live_edit=True);cols=p.export_settings.columns
                for i in range(len(provider)):
                    y,x=(i//cols)*96,(i%cols)*96
                    assert np.array_equal(provider.get_final_frame(i),sheet[y:y+96,x:x+96])
                assert p.library.animation_count(state['root'])==3
                state['project']=str(w.project_file);w.save_project();advance('saved')
            elif phase=='saved':
                expected={key:state[key] for key in ('project','root','idle','run','jump','a','b','run_animation','a_hash','run_pixel')}
                (output/'expected.json').write_text(json.dumps(expected),encoding='utf-8')
                report={'status':'passed','build':__build__,'dpr':w.devicePixelRatioF(),'multiple_videos':True,'sequence_frames':22,'imported_sheet':True,'background_owner_preserved':True,'switch_without_processing':True,'workspace_restored':True,'group_export_resources':4,'preview_export_equal':True,'group_status_ready':True}
                (output/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8');finish(0)
            elif phase=='verify':
                state.update(json.loads((output/'expected.json').read_text(encoding='utf-8')));w.open_project(state['project']);advance('verified')
            elif phase=='verified':
                assert p.current_group_id==state['run'] and p.animation_id==state['run_animation']
                assert w.editor.index==12 and w.editor.timeline.pixels_per_second==1200 and w.editor.preview_fps.value()==12
                provider=FinalFrameProvider(p,w.cache_dir,live_edit=True)
                assert hashlib.sha256(provider.get_final_frame(12).tobytes()).hexdigest()==state['run_pixel']
                assert p.library.animation_count(state['root'])==3
                no_processing_switch(state['idle']);assert w.project.library.animation_count(state['idle'])==2
                assert all(p.library.groups[g].status=='READY' for g in (state['idle'],state['run'],state['jump']))
                report=json.loads((output/'validation.json').read_text(encoding='utf-8'));report['restart_verified']=True;report['restart_status_ready']=True
                (output/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8');finish(0)
        except Exception:
            log.exception('Group acceptance failed in %s',state['phase']);(output/'failed.txt').write_text(state['phase'],encoding='utf-8');finish(1)
    timer.timeout.connect(poll);timer.start();w._group_smoke_timer=timer
