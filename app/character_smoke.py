"""Frozen Character acceptance: templates, per-Character Reference, ownership moves and restart."""
import hashlib,json,logging,time
from pathlib import Path
import cv2
import numpy as np
from PySide6.QtCore import QTimer
from app.core.project_workspace import create_project_workspace
from app.core.group_export import plan_group_export,export_group_plan
from app.core.final_frame_provider import FinalFrameProvider
from app.core.pipeline import Pipeline
from app.i18n import t
from app.models.character_reference import AnimationTransform, CharacterReference
from app.models.character_templates import BOSS, ENEMY, PLAYER, REGISTRY
from app.utils.cache import save_rgba
from app.ui.dialogs import MessageBox
from app.utils.rgba_image import read_rgba
from app import __build__


def start_character_smoke(app,w,output,verify=False):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    log=logging.getLogger('aivsprite.character_smoke');state={'phase':'verify' if verify else 'create','started':time.monotonic()}
    w._failed=lambda error:setattr(w,'last_error',error)
    timer=QTimer(w);timer.setInterval(40)
    def advance(phase):state.update(phase=phase,ready=time.monotonic())
    def finish(code):
        timer.stop()
        if w.worker:w.worker.cancel();w.worker.wait();app.processEvents()
        w.editor.pause_preview();w.dirty=False;w.close();app.exit(code)
    def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    def editor_ready():return w.editor.provider and not w.editor.worker and not w.editor.pending
    def no_processing(action):
        originals={name:getattr(Pipeline,name) for name in ('import_input','ensure_key','ensure_aligned','build')}
        def forbidden(*a,**kw):raise AssertionError('Character switching called a processing stage')
        try:
            for name in originals:setattr(Pipeline,name,forbidden)
            action()
        finally:
            for name,method in originals.items():setattr(Pipeline,name,method)
    def roots(character_id):return [g.name for g in w.project.library.character_roots(character_id)]
    def group(character_id,name):
        return next(g for g in w.project.library.character_roots(character_id) if g.name==name)
    def write_video(path,color):
        writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'mp4v'),24,(96,96));assert writer.isOpened()
        for i in range(5):
            bgr=np.full((96,96,3),(0,255,0),np.uint8)
            cv2.rectangle(bgr,(30+i,20),(60+i,80),color,-1);writer.write(bgr)
        writer.release()
    def poll():
        try:
            if w.last_error:raise AssertionError(w.last_error)
            if time.monotonic()-state['started']>200:raise AssertionError('Character acceptance timed out: '+state['phase'])
            if w.worker or time.monotonic()-state.get('ready',0)<.15:return
            c=w.library_controller;p=w.project;phase=state['phase']
            if phase=='create':
                w.project,w.project_file=create_project_workspace(output,'metroidvania-forge','standard',project_canvas=(96,96));w._loaded()
                p=w.project
                assert not p.library.characters and not w.import_button.isEnabled()
                hero=c.new_character(name='主角玩家',template_id=PLAYER)
                assert hero.template_id==PLAYER and hero.template_version==1
                assert roots(hero.id)==['Idle','Movement','Jump','Dash','Wall','Combat','AirCombat','Interaction','Reaction']
                assert len(p.library.character_members(hero.id))==39
                state['hero']=hero.id
                write_video(output/'Hero Idle.mp4',(90,50,220));write_video(output/'Boss Idle.mp4',(200,60,60))
                jumps=output/'Jump Frames';jumps.mkdir()
                for i in range(6):
                    rgba=np.zeros((96,96,4),np.uint8);rgba[30:70,30+i:46+i]=(120,200,90,190);save_rgba(jumps/f'{i:04d}.png',rgba)
                sequence=output/'Loose Frames';sequence.mkdir()
                for i in range(8):
                    rgba=np.zeros((96,96,4),np.uint8);rgba[20:80,20+i:36+i]=(210,60,120,190);save_rgba(sequence/f'{i:04d}.png',rgba)
                c.select_group(group(hero.id,'Idle').id);w.import_video(output/'Hero Idle.mp4');advance('hero_imported')
            elif phase=='hero_imported':
                assert p.video.frame_count==5;state['hero_animation']=p.animation_id;w.process_key();advance('hero_keyed')
            elif phase=='hero_keyed':w.start_keyed_passthrough();advance('hero_built')
            elif phase=='hero_built':
                if not w.built:return
                hero_reference=CharacterReference(state['hero_animation'],0,48,86,96,96)
                w._save_character_reference(hero_reference)
                assert w.project.library.characters[state['hero']].character_reference==hero_reference
                assert w.project.character_reference==hero_reference and w.project.current_character_id==state['hero']
                state['hero_reference']=hero_reference
                boss=c.new_character(name='Boss',template_id=BOSS)
                state['boss']=boss.id
                assert roots(boss.id)==['Idle','Move','Phase','Attack','Special','Hurt','Stagger','Death','Intro']
                c.select_group(group(boss.id,'Idle').id);w.import_video(output/'Boss Idle.mp4');advance('boss_imported')
            elif phase=='boss_imported':
                assert p.video.frame_count==5;state['boss_animation']=p.animation_id;w.process_key();advance('boss_keyed')
            elif phase=='boss_keyed':w.start_keyed_passthrough();advance('boss_built')
            elif phase=='boss_built':
                if not w.built:return
                boss_reference=CharacterReference(state['boss_animation'],0,64,80,96,96)
                w._save_character_reference(boss_reference)
                assert w.project.library.characters[state['boss']].character_reference==boss_reference
                assert w.project.library.characters[state['hero']].character_reference==state['hero_reference']
                assert boss_reference.origin!=state['hero_reference'].origin
                state['boss_reference']=boss_reference
                no_processing(lambda:(c.select_character(state['hero']),c.select_character(state['boss']),c.select_character(state['hero'])))
                assert w.project.current_character_id==state['hero']
                assert w.project.character_reference==state['hero_reference']
                c.select_character(state['boss']);assert w.project.character_reference==state['boss_reference']
                c.select_character(state['hero']);assert w.project.character_reference==state['hero_reference']
                state['hero_pixels']=hashlib.sha256(w.project.character_reference.origin.__repr__().encode()).hexdigest()
                c.activate('LOOSE',None);loose=c.new_group(name='Loose Run')
                p=w.project
                assert p.library.groups[loose.id].character_id is None
                c.select_group(loose.id);w.import_sequence(output/'Loose Frames');advance('loose_sequence')
            elif phase=='loose_sequence':
                if not w.sequence_dialog:return
                w.sequence_dialog.submit();advance('loose_built')
            elif phase=='loose_built':
                if not w.built:return
                state['loose_group']=p.current_group_id;state['loose_animation']=p.animation_id
                w.set_animation_offset(-12,4);assert p.animation_transform==AnimationTransform(-12,4)
                state['loose_sheet']=str(w.cache_dir/'sprite_sheet.png');state['loose_hash']=digest(state['loose_sheet'])
                state['loose_pixel']=hashlib.sha256(FinalFrameProvider(w.project,w.cache_dir,live_edit=True).get_final_frame(0).tobytes()).hexdigest()
                enemy=c.new_character(name='Enemy',template_id=ENEMY)
                state['enemy']=enemy.id
                assert roots(enemy.id)==['Idle','Walk','Run','Attack','Hurt','Knockback','Death']
                c.move_to_character(state['loose_group'],enemy.id);advance('moved')
            elif phase=='moved':
                moved=p.library.groups[state['loose_group']]
                assert moved.character_id==state['enemy'] and moved.alignment_review_required
                assert not p.library.loose_roots()
                assert digest(state['loose_sheet'])==state['loose_hash']
                assert p.select_animation(state['loose_animation']).animation_transform==AnimationTransform(-12,4)
                assert p.library.character_animation_count(state['enemy'])==1
                plan=plan_group_export(p,w.project_file,[g.id for g in p.library.character_roots(state['hero'])])
                assert plan.items and str(plan.items[0].relative_directory).replace('\\','/').startswith('主角玩家/')
                destination=output/'Export';destination.mkdir()
                w._run(lambda progress,cancel:export_group_plan(plan,destination,progress,cancel),lambda result:state.update(export=result),'Exporting Groups')
                advance('exported')
            elif phase=='exported':
                exported=output/'Export'/'主角玩家'/'Idle'/'Hero Idle'/'sprite_sheet.png'
                assert exported.is_file(),'Character export path missing: '+str(exported)
                result=p.library.characters[state['hero']].character_reference
                assert result==state['hero_reference'] and p.library.characters[state['boss']].character_reference==state['boss_reference']
                c.select_group(next(g.id for g in p.library.children(group(state['hero'],'Jump').id) if g.name=='JumpUp'))
                w.import_sequence(output/'Jump Frames');advance('prune_import')
            elif phase=='prune_import':
                if not w.sequence_dialog:return
                w.sequence_dialog.submit();advance('prune_built')
            elif phase=='prune_built':
                if not w.built:return
                row=p.library.animation(p.animation_id);source=p.library.resources[row.source_id]
                state['prune_animation']=row.animation_id;state['prune_source']=source.id;state['prune_folder']=str(source.path)
                state['prune_group']=p.current_group_id
                actions=[action.text() for action in w.library_panel.build_context_menu('RESOURCE',source.id).actions()]
                assert t('Remove from Project') in actions,'Resource context menu is missing Remove from Project'
                original=MessageBox.choice
                MessageBox.choice=staticmethod(lambda *args,**kwargs:0)
                try:c.remove_resource(source.id)
                finally:MessageBox.choice=original
                advance('pruned')
            elif phase=='pruned':
                animation=p.library.animation(state['prune_animation'])
                assert animation is not None and animation.ready,'Removing the source must keep the generated Animation'
                assert state['prune_source'] not in p.library.resources
                assert Path(state['prune_folder']).is_dir(),'Source folder must stay on disk'
                assert p.current_group_id==state['prune_group'] and p.animation_id==state['prune_animation']
                assert p.library.groups[state['prune_group']].status=='READY'
                assert not w.library_panel.items.get(('RESOURCE',state['prune_source']))
                state['project']=str(w.project_file);w.save_project();advance('saved')
            elif phase=='saved':
                expected={key:state[key] for key in ('project','hero','boss','enemy','hero_animation','boss_animation','loose_group','loose_animation','loose_hash','loose_pixel','loose_sheet','prune_animation','prune_source','prune_folder','prune_group')}
                expected['hero_reference']=list(state['hero_reference'].origin);expected['boss_reference']=list(state['boss_reference'].origin)
                (output/'expected.json').write_text(json.dumps(expected,ensure_ascii=False),encoding='utf-8')
                report={'status':'passed','build':__build__,'dpr':w.devicePixelRatioF(),'player_template_groups':39,
                    'character_reference_isolation':True,'character_switch_without_processing':True,'loose_group_moved_with_offsets':True,
                    'export_path_includes_character':True,'characters':3,'resource_removal_keeps_source_files':True}
                (output/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8');finish(0)
            elif phase=='verify':
                state.update(json.loads((output/'expected.json').read_text(encoding='utf-8')));w.open_project(state['project']);advance('verified')
            elif phase=='verified':
                assert len(p.library.characters)==3
                hero=p.library.characters[state['hero']];boss=p.library.characters[state['boss']];enemy=p.library.characters[state['enemy']]
                assert hero.template_id==PLAYER and boss.template_id==BOSS and enemy.template_id==ENEMY
                assert [hero.character_reference.origin_x,hero.character_reference.ground_y]==state['hero_reference']
                assert [boss.character_reference.origin_x,boss.character_reference.ground_y]==state['boss_reference']
                assert roots(state['hero'])[0]=='Idle' and p.library.character_animation_count(state['hero'])==2
                assert p.library.character_animation_count(state['enemy'])==1
                moved=p.library.groups[state['loose_group']]
                assert moved.character_id==state['enemy'] and moved.alignment_review_required
                assert p.library.animation(state['prune_animation']) is not None
                assert state['prune_source'] not in p.library.resources
                assert Path(state['prune_folder']).is_dir()
                assert p.library.groups[state['prune_group']].status=='READY'
                cached=Path(state['loose_sheet'])
                assert cached.is_file() and digest(cached)==state['loose_hash']
                c.select_group(state['loose_group'])
                p=w.project
                provider=FinalFrameProvider(p,w.cache_dir,live_edit=True)
                assert hashlib.sha256(provider.get_final_frame(0).tobytes()).hexdigest()==state['loose_pixel']
                assert w.project.select_animation(state['loose_animation']).animation_transform==AnimationTransform(-12,4)
                report=json.loads((output/'validation.json').read_text(encoding='utf-8'));report['restart_verified']=True;report['resource_removal_verified']=True
                (output/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8');finish(0)
        except Exception:
            log.exception('Character acceptance failed in %s',state['phase']);(output/'failed.txt').write_text(state['phase'],encoding='utf-8');finish(1)
    timer.timeout.connect(poll);timer.start();w._character_smoke_timer=timer
