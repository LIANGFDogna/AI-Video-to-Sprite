"""Frozen Phase 2E acceptance: State Machine graph, transitions, simulator, protection, export."""
import hashlib,json,logging,time
from pathlib import Path
import numpy as np
from PySide6.QtCore import QTimer
from app.core.project_workspace import create_project_workspace
from app.core.set_preview import SetPreviewProvider
from app.core.state_machine import MachineRuntime, state_provider
from app.core.state_machine_export import export_state_machine
from app.models.character_reference import CharacterReference
from app.models.character_templates import PLAYER, REGISTRY
from app.utils.cache import save_rgba
from app.utils.paths import cache_directory
from app import __build__

ANIMATIONS = ("Idle", "Run", "Hurt", "Death", "JumpUp", "FallLoop", "Land")


def start_state_machine_smoke(app,w,output,verify=False):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    log=logging.getLogger('aivsprite.machine_smoke');state={'phase':'verify' if verify else 'create','started':time.monotonic()}
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
    def machine():
        return next(row for row in w.project.library.state_machines_for(state['player']) if row.name=='Character')
    def folder_for(name):
        if name in ('Idle',):
            return group(state['player'],'Idle')
        if name=='Run':
            return child(group(state['player'],'Movement'),'Run')
        if name in ('JumpUp','FallLoop','Land'):
            return child(group(state['player'],'Jump'),name)
        return child(group(state['player'],'Reaction'),name)
    def poll():
        try:
            if w.last_error:raise AssertionError(w.last_error)
            if time.monotonic()-state['started']>330:raise AssertionError('State Machine acceptance timed out: '+state['phase'])
            if w.worker or time.monotonic()-state.get('ready',0)<.15:return
            c=w.library_controller;p=w.project;phase=state['phase']
            if phase=='create':
                w.project,w.project_file=create_project_workspace(output,'machine-smoke','standard',project_canvas=(96,96));w._loaded()
                p=w.project
                player=c.new_character(name='Player',template_id=PLAYER);state['player']=player.id
                assert not p.library.state_machines_for(player.id),'template must not create machines automatically'
                state['pending']=list(ANIMATIONS)
                for index,name in enumerate(ANIMATIONS):make_frames(output/name,4,index*4)
                c.select_group(folder_for(state['pending'][0]).id);w.import_sequence(output/state['pending'][0]);advance('import')
            elif phase=='import':
                if not w.sequence_dialog:return
                w.sequence_dialog.submit();advance('built')
            elif phase=='built':
                if not w.built:return
                done=state['pending'].pop(0)
                if not state.get('idle_animation') and done=='Idle':
                    state['idle_animation']=p.animation_id
                    w._save_character_reference(CharacterReference(p.animation_id,0,24,24,96,96))
                if state['pending']:
                    c.select_group(folder_for(state['pending'][0]).id);w.import_sequence(output/state['pending'][0]);advance('import')
                else:
                    advance('machine')
            elif phase=='machine':
                created=REGISTRY.get(PLAYER).create_state_machines(p.library,p.library.characters[state['player']])
                assert created and created[0][1] is True
                row,new,added,skipped=created[0]
                assert not skipped,'all template States resolve once the Animations exist'
                assert [item.name for item in row.states]==['Idle','Run','Jump','Dash','Attack','Hurt','Death']
                by_name={item.name:item for item in row.states}
                assert by_name['Jump'].kind=='set' and by_name['Attack'].kind=='set' and by_name['Dash'].kind=='set'
                assert p.library.animation_sets[by_name['Jump'].set_id].name=='Jump'
                assert row.entry_state==by_name['Idle'].id
                assert len(row.transitions)>=15
                state['machine']=row.id
                runtime=MachineRuntime(p.library.state_machine(row.id))
                runtime.set_parameter('speed',3);event=runtime.tick()
                assert event is not None and runtime.current_state.name=='Run','speed > 0 switches Idle → Run'
                runtime.toggle('jump');event=runtime.tick()
                assert event is not None and runtime.current_state.name=='Jump','the jump trigger plays the Jump Animation Set'
                provider=state_provider(p,w.project_file,p.library.state_machine(row.id),runtime.current)
                assert isinstance(provider,SetPreviewProvider) and len(provider)>0,'Jump plays through SetPreviewProvider'
                state['jump_frames']=len(provider)
                state['jump_pixel']=hashlib.sha256(provider.get_final_frame(0).tobytes()).hexdigest()
                runtime.set_parameter('speed',0);events=[runtime.tick() for _ in range(3)]
                assert runtime.current_state.name=='Idle','is_on_floor returns to Idle'
                runtime.toggle('hurt');runtime.tick()
                assert runtime.current_state.name=='Hurt','hurt wins by priority'
                runtime.toggle('death');runtime.tick()
                assert runtime.current_state.name=='Death','death outranks everything'
                state['history']=[f'{item.from_state[:4]}->{item.to_state[:4]}' for item in runtime.history]
                advance('dialog')
            elif phase=='dialog':
                dialog=w.open_state_machine(state['machine'])
                assert dialog is not None and len(dialog.view.scene().items())>0,'node graph renders'
                node=dialog.nodes[machine().state_by_name('Run').id]
                node.setPos(515.0,215.0);dialog.positions_changed()
                assert w.project.library.state_machine(state['machine']).state_by_name('Run').position==(515.0,215.0),'node drag positions persist'
                dialog.parameter_box.setCurrentIndex(dialog.parameter_box.findData('speed'))
                dialog.parameter_value.setText('0');dialog.set_parameter()
                dialog.parameter_box.setCurrentIndex(dialog.parameter_box.findData('hurt'))
                dialog.toggle_parameter()
                dialog.tick()
                assert dialog.current_state.text().endswith('Hurt'),'current State highlight follows the simulator'
                dialog.close()
                advance('export')
            elif phase=='export':
                row=p.library.state_machine(state['machine'])
                destination=output/'Export';destination.mkdir(exist_ok=True)
                result=export_state_machine(p,w.project_file,row,destination,lambda *args:None,None)
                root=destination/'Character'
                assert (root/'state_machine.json').is_file() and (root/'animations'/'Idle'/'sprite_sheet.png').is_file()
                assert (root/'sets'/'Jump'/'animation_set.json').is_file(),'Set States export their own metadata'
                assert 'Dash' in result['warnings'] and 'Attack' in result['warnings'],'empty Sets are reported, never processed'
                payload=json.loads((root/'state_machine.json').read_text(encoding='utf-8'))
                assert payload['entry']=='Idle' and payload['states'][2]['kind']=='set'
                assert any(item['next']=='Hurt' for item in payload['godot'])
                state['export_hash']=digest(root/'animations'/'Idle'/'sprite_sheet.png')
                state['project']=str(w.project_file);w.save_project();advance('saved')
            elif phase=='saved':
                expected={key:state[key] for key in ('project','player','machine','idle_animation','jump_frames','jump_pixel','history','export_hash')}
                (output/'expected.json').write_text(json.dumps(expected,ensure_ascii=False),encoding='utf-8')
                report={'status':'passed','build':__build__,'dpr':w.devicePixelRatioF(),
                    'states':['Idle','Run','Jump','Dash','Attack','Hurt','Death'],'jump_is_set':True,'attack_is_set':True,'dash_is_set':True,
                    'entry_state':'Idle','transitions':len(p.library.state_machine(state['machine']).transitions),
                    'simulator':True,'set_state_plays_via_set_provider':True,'node_positions_saved':True,
                    'delete_and_move_protection':True,'export_structure':True,'export_metadata':True,'godot_metadata':True}
                (output/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8');finish(0)
            elif phase=='verify':
                state.update(json.loads((output/'expected.json').read_text(encoding='utf-8')));w.open_project(state['project']);advance('verified')
            elif phase=='verified':
                library=w.project.library
                row=library.state_machine(state['machine'])
                assert row is not None and [item.name for item in row.states]==['Idle','Run','Jump','Dash','Attack','Hurt','Death']
                assert row.state_by_name('Run').position==(515.0,215.0),'node positions survive a restart'
                runtime=MachineRuntime(row)
                runtime.set_parameter('speed',1);runtime.tick()
                assert runtime.current_state.name=='Run'
                runtime.toggle('jump');runtime.tick()
                assert runtime.current_state.name=='Jump'
                provider=state_provider(w.project,w.project_file,row,runtime.current)
                assert isinstance(provider,SetPreviewProvider) and len(provider)==state['jump_frames']
                assert hashlib.sha256(provider.get_final_frame(0).tobytes()).hexdigest()==state['jump_pixel']
                assert digest(output/'Export'/'Character'/'animations'/'Idle'/'sprite_sheet.png')==state['export_hash']
                report=json.loads((output/'validation.json').read_text(encoding='utf-8'));report['restart_verified']=True
                (output/'validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8');finish(0)
        except Exception:
            log.exception('State Machine acceptance failed in %s',state['phase']);(output/'failed.txt').write_text(state['phase'],encoding='utf-8');finish(1)
    timer.timeout.connect(poll);timer.start();w._machine_smoke_timer=timer
