"""Group workspace coordination. Selection is cache-only and never runs Pipeline stages."""
from __future__ import annotations
import copy
from dataclasses import asdict
import json
import tempfile
from pathlib import Path
from PIL import Image
import numpy as np
from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QDialog, QInputDialog, QLineEdit
from app.i18n import t
from app.models.project import Project
from app.models.animation_set import AnimationSlot
from app.models.ids import now_stamp
from app.models.state_machine import Condition, State, StateMachine, StateParameter, coerce_value
from app.models.character_templates import REGISTRY
from app.models.project_library import ProjectLibrary, WorkspaceState, unique_name
from app.ui.character_dialogs import CharacterDialog
from app.ui.character_panel import character_label
from app.models.timeline_edit import EditHistory
from app.ui.dialogs import MessageBox, FileDialog, reveal_in_explorer
from app.models.project_library import SOURCE_KINDS
from app.utils.paths import cache_directory, project_cache_root
from app.utils.cache import save_rgba
from app.utils.rgba_image import read_rgba, to_rgba8
from app.core.group_export import sheet_path
from app.core.final_frame_provider import FinalFrameProvider
from app.core.frame_move import (apply_frame_state, canonical_folder, copy_canonical_frames,
    copy_raster_edits, invalidate_sheet_manifest, mark_generated_stale)
from app.core.sprite_sheet_slice import DEFAULT_FPS, SliceConfig, calculate_cells, slice_frames
from app.core.project_workspace import sanitize_project_name


class RoutedEditHistory(EditHistory):
    def __init__(self, controller, key):
        super().__init__(); self.controller=controller; self.key=key
    def record(self,before,after,label):
        super().record(before,after,label)
        if before!=after:self.controller.record(('edit',self.key,before,after,label))


class LibraryController(QObject):
    def __init__(self,host):
        super().__init__(host); self.host=host; self.restoring=False; self.asset_id=None; self.selection=None
        self.entries=[]; self.index=0; self.history_project=host.project.project_id

    @property
    def available(self):
        h=self.host
        return bool(h.project_file or h.project.project_name)

    @property
    def can_import(self):
        return self.available and self.host.project.current_group_id in self.host.project.library.groups

    def require_group(self):
        if self.can_import:return True
        self.host.status.setText(t('Please create and select a Group before importing media.'))
        return False

    def record(self,entry):
        if self.restoring:return
        if self.history_project!=self.host.project.project_id:
            self.entries=[];self.index=0;self.history_project=self.host.project.project_id
        del self.entries[self.index:];self.entries.append(copy.deepcopy(entry));self.entries=self.entries[-100:];self.index=len(self.entries)

    def capture(self):
        h=self.host;p=h.project;g=p.library.groups.get(p.current_group_id)
        if not g:return
        e=h.editor
        state=WorkspaceState(animation_id=p.animation_id if p.source_path and p.library.animation(p.animation_id) else None,
            frame=e.index,source_frame=h.current_frame,timeline_zoom=e.timeline.pixels_per_second,
            timeline_scroll_x=e.timeline.horizontalScrollBar().value(),timeline_scroll_y=e.timeline.verticalScrollBar().value(),
            editor_tab=e.inspector.currentIndex(),page=h.steps.currentIndex(),preview_mode=h.preview_mode.currentData(),
            preview_fps=e.preview_fps.value(),loop=e.loop.isChecked(),onion=e.onion.isChecked(),ghost=e.ghost.isChecked(),
            neighbors=e.neighbors.value(),ghost_opacity=e.ghost_opacity.value(),playing=e.timer.isActive(),selected_frames=list(e.selected_ids),
            reference_ghost=(e.show_idle_ghost.isChecked() if e.show_idle_ghost.isEnabled() else None),
            reference_ghost_opacity=e.reference_opacity.value(),
            frame_reference=e.frame_reference_state() if hasattr(e,'frame_reference_state') else None,
            frame_reference_visible=e.show_frame_reference.isChecked() if hasattr(e,'show_frame_reference') else True,
            frame_reference_opacity=e.frame_reference_opacity.value() if hasattr(e,'frame_reference_opacity') else .15)
        g.ui_state=state
        if state.animation_id:g.animation_states[state.animation_id]=copy.deepcopy(state)

    def refresh(self):
        h=self.host;p=h.project
        if self.history_project!=p.project_id:
            self.entries=[];self.index=0;self.history_project=p.project_id
        context=getattr(h,'task_context',None)
        p.library.refresh_status([context.animation_id] if context else [])
        if hasattr(h,'library_panel'):h.library_panel.refresh()
        if hasattr(h,'character_page'):h.character_page.refresh(p.library.characters.get(p.current_character_id))
        h.start_page.update_project(p,self.available)

    def select_group(self,ident,animation_id=None,*,capture=True):
        h=self.host
        if self.restoring or (h.interaction_busy and not getattr(h,'task_context',None)):return
        if ident is not None and ident not in h.project.library.groups:return
        h.editor.cancel_active_interaction()
        if capture:self.capture()
        p=h.project;g=p.library.groups.get(ident)
        state=copy.deepcopy(g.animation_states.get(animation_id,g.ui_state) if animation_id else g.ui_state) if g else WorkspaceState()
        animation_id=animation_id or state.animation_id
        rows=p.library.in_group(ident,kinds={'ANIMATION'}) if g else []
        if animation_id not in [r.animation_id for r in rows]:animation_id=rows[0].animation_id if rows else None
        self.restoring=True;self.asset_id=None;h.cache_only_preview=True
        try:
            h.editor.pause_preview();h.play_timer.stop();h.preview_revision+=1
            h.project=p.select_animation(animation_id) if animation_id else p.empty_context(ident)
            h.project.current_group_id=ident
            if animation_id:
                row=h.project.library.animation(animation_id)
                h.project.export_settings.animation_name=row.name
            h.cache_dir=cache_directory(h.project.project_id,h.project_file,h.project.animation_id)
            h.built=False;h._loaded()
            p=h.project
            row=p.library.animation(p.animation_id)
            h.built=bool(row and row.ready and p.layout and (h.cache_dir/'sprite_sheet.png').is_file())
            if h.built:
                preview=h.cache_dir/'sheet_preview.png'
                if preview.is_file():
                    with Image.open(preview) as image:pixels=np.array(image.convert('RGBA'))
                    factor=json.loads((h.cache_dir/'preview.json').read_text())['factor']
                else:
                    with Image.open(h.cache_dir/'sprite_sheet.png') as image:
                        size=image.size;image.thumbnail((1280,1280));pixels=np.array(image.convert('RGBA'));factor=image.width/size[0]
                h.sprite_view.project=p;h.sprite_view.set_image(pixels,factor)
            h.steps.setCurrentIndex(state.page if p.source_path else 0);h._stage_changed(h.steps.currentIndex())
            e=h.editor
            if hasattr(e,'show_idle_ghost'):
                e.show_idle_ghost.blockSignals(True)
                e.show_idle_ghost.setChecked(True if state.reference_ghost is None else bool(state.reference_ghost))
                e.show_idle_ghost.blockSignals(False)
                e.reference_opacity.setValue(min(.7,max(0.,state.reference_ghost_opacity)))
                e._ghost_override=state.reference_ghost is not None
            if hasattr(e,'set_frame_reference_state'):
                e.show_frame_reference.blockSignals(True)
                e.show_frame_reference.setChecked(bool(state.frame_reference_visible))
                e.show_frame_reference.blockSignals(False)
                e.frame_reference_opacity.blockSignals(True)
                e.frame_reference_opacity.setValue(min(.7,max(0.,state.frame_reference_opacity)))
                e.frame_reference_opacity.blockSignals(False)
                e.set_frame_reference_state(state.frame_reference,capture=False)
            e.bind();e.inspector.setCurrentIndex(state.editor_tab)
            h.preview_mode.setCurrentIndex(max(0,h.preview_mode.findData(state.preview_mode)))
            for control,value in ((e.preview_fps,state.preview_fps),(e.neighbors,state.neighbors),(e.ghost_opacity,state.ghost_opacity)):control.setValue(value)
            for control,value in ((e.loop,state.loop),(e.onion,state.onion),(e.ghost,state.ghost)):control.setChecked(value)
            e.selected_ids=list(state.selected_frames);e.timeline.pixels_per_second=state.timeline_zoom;e.refresh()
            h.select_frame(min(state.source_frame,max(0,p.video.frame_count-1)))
            if e.provider:e.select(min(state.frame,max(0,len(e.provider)-1)))
            else:e.index=state.frame
            if state.editor_tab==1:h.select_frame(min(state.source_frame,max(0,p.video.frame_count-1)))
            e.timeline.horizontalScrollBar().setValue(state.timeline_scroll_x);e.timeline.verticalScrollBar().setValue(state.timeline_scroll_y)
            if not p.source_path:h.views.setCurrentWidget(h.start_page)
            h._sync_animation_selector();h._update_state()
            if g:
                h.project.library.groups[ident].ui_state=copy.deepcopy(state)
                h.project.library.groups[ident].ui_state.animation_id=animation_id
            self.refresh()
            h.status.setText(t('Workspace restored from cache. Missing results require explicit processing.'))
            if state.playing and e.provider and state.page==2:e.toggle_play()
        except (OSError,ValueError,KeyError) as error:
            h.status.setText(t('Cached preview unavailable: {error}',error=str(error)))
        finally:self.restoring=False
        h.request_preview()

    def select_animation(self,ident):
        row=self.host.project.library.animation(ident)
        if row:self.select_group(row.group_id,ident)

    def activate(self,kind,ident):
        self.selection=(kind,ident)
        if kind=='PROJECT':self.select_group(None);return
        if kind=='LOOSE':self.select_character(None);return
        if kind=='CHARACTERS':self.select_character(None);return
        if kind=='CHARACTER':self.select_character(ident);return
        if kind=='GROUP':self.select_group(ident);return
        h=self.host;row=h.project.library.resources.get(ident)
        if not row:return
        if row.kind=='ANIMATION':self.select_animation(row.animation_id);return
        self.select_group(row.group_id)
        self.selection=(kind,ident);self.asset_id=ident;h.preview_revision+=1;h.editor.pause_preview();h.preview_timer.stop()
        h.asset_info.setPlainText(t(row.kind)+'\n'+row.name+'\n\n'+row.path+'\n\n'+json.dumps(row.metadata,ensure_ascii=False,indent=2))
        h.views.setCurrentWidget(h.asset_info);h.view_label.setText(row.name)
        if row.kind in ('SOURCE_SPRITE_SHEET','GENERATED_SPRITE_SHEET'):
            try:
                path=sheet_path(h.project,h.project_file,row)
                with Image.open(path) as image:
                    width=image.width;image.thumbnail((1600,1600));pixels=np.array(image.convert('RGBA'));factor=image.width/width
                h.asset_view.project=None;h.asset_view.set_image(pixels,factor);h.views.setCurrentWidget(h.asset_view)
            except (OSError,ValueError) as error:h.asset_info.appendPlainText(str(error))
        h.library_panel.select(kind,ident)

    def mutate(self,operation,label):
        h=self.host
        if h.interaction_busy:return None
        self.capture();before=asdict(h.project.library);current=h.project.current_group_id
        try:
            result=operation(h.project.library);h.project.library.validate()
        except (ValueError,KeyError) as error:
            h.project.library=ProjectLibrary.from_dict(before);h._failed(str(error));return None
        after=asdict(h.project.library)
        self.record(('library',before,after,current,h.project.current_group_id,label))
        h.dirty=True;self.refresh();h._update_state();return result

    def new_subgroup(self,character_id=None):
        h=self.host;p=h.project;parent=p.current_group_id if p.current_group_id in p.library.groups else None
        if parent is not None and character_id is not None and p.library.groups[parent].character_id!=character_id:
            roots=p.library.character_roots(character_id);parent=roots[0].id if roots else None
        if parent is None:
            return self.new_group(None,character_id=character_id)
        return self.new_group(parent)

    def default_character_id(self):
        "Add menu targets follow the current selection: Character, Group or Loose Groups."
        h=self.host;p=h.project;selection=self.selection
        if selection:
            if selection[0]=='CHARACTER':return selection[1]
            if selection[0]=='GROUP':return p.library.groups[selection[1]].character_id if selection[1] in p.library.groups else None
            if selection[0] in ('LOOSE','PROJECT','CHARACTERS'):return None
        return p.current_character_id

    def new_group(self,parent_id=None,name=None,character_id=None):
        if not self.available or self.host.interaction_busy:return
        if name is None:
            name,ok=QInputDialog.getText(self.host,t('New Group'),t('Group name'),QLineEdit.EchoMode.Normal,t('Group'))
            if not ok:return
        owner=None if parent_id is not None else (character_id if character_id is not None else self.default_character_id())
        group=self.mutate(lambda lib:lib.add_group(name,parent_id,character_id=owner),'New Group')
        if group:self.select_group(group.id)
        return group

    def rename(self,kind,ident,name=None):
        lib=self.host.project.library
        if kind=='CHARACTER':
            character=lib.characters.get(ident)
            if not character:return
            if name is None:
                name,ok=QInputDialog.getText(self.host,t('Rename Character'),t('Character name'),QLineEdit.EchoMode.Normal,character.name)
                if not ok:return
            self.mutate(lambda tree:tree.rename_character(ident,name),'Rename Character')
            return
        row=lib.groups.get(ident) if kind=='GROUP' else lib.resources.get(ident)
        if not row:return
        if name is None:
            name,ok=QInputDialog.getText(self.host,t('Rename'),t('Name'),QLineEdit.EchoMode.Normal,row.name)
            if not ok:return
        def operation(lib):
            if kind=='GROUP':return lib.rename_group(ident,name)
            resource=lib.resources[ident]
            resource.name=unique_name(name,[r.name for r in lib.in_group(resource.group_id) if r.kind==resource.kind and r.id!=ident])
            if resource.kind=='ANIMATION':
                for item in lib.resources.values():
                    if item.kind=='GENERATED_SPRITE_SHEET' and item.animation_id==resource.animation_id:item.name=resource.name+' Sheet'
        self.mutate(operation,'Rename')
        if self.host.project.library.animation(self.host.project.animation_id):
            self.host.project.export_settings.animation_name=self.host.project.library.animation(self.host.project.animation_id).name
        self.host._sync_animation_selector()

    def new_character(self,template_id=None,name=None):
        h=self.host
        if not self.available or h.interaction_busy:return None
        if name is None:
            dialog=CharacterDialog(h,REGISTRY,template_id or 'blank')
            if dialog.exec()!=QDialog.DialogCode.Accepted:return None
            name,template_id=dialog.character_name(),dialog.template_id()
        character=self.mutate(lambda lib:REGISTRY.create_character(lib,name,template_id),'New Character')
        if character:self.select_character(character.id)
        return character

    def select_character(self,ident,*,capture=True):
        h=self.host
        if self.restoring or (h.interaction_busy and not getattr(h,'task_context',None)):return
        if ident is not None and ident not in h.project.library.characters:return
        h.editor.cancel_active_interaction()
        if capture:self.capture()
        p=h.project;p.current_character_id=ident
        if ident is not None:
            row=p.library.groups.get(p.current_group_id)
            if row is None or row.character_id!=ident:
                roots=p.library.character_roots(ident)
                if roots:self.select_group(roots[0].id,capture=False)
        p.sync_character_reference()
        character=p.library.characters.get(ident)
        if character is not None:
            h.show_character_page(character.id)
            h.status.setText(t('Character selected: {name}',name=character_label(character)))
        self.refresh()
        h._update_state()

    def move_to_character(self,group_id,character_id):
        h=self.host;lib=h.project.library
        if h.interaction_busy or group_id not in lib.groups:return
        if lib.groups[group_id].character_id==character_id:return
        clear=False;clear_sets=False
        used=[slot for row,slot in lib.set_references_for_group(group_id) if row.character_id!=character_id]
        if used:
            if MessageBox.question(h,t('Move to Character'),
                t('The Animation is used by an Animation Set. Clear the references and move it?'),
                MessageBox.StandardButton.Yes|MessageBox.StandardButton.Cancel,
                MessageBox.StandardButton.Cancel)!=MessageBox.StandardButton.Yes:return
            clear_sets=True
        blocking=[character for character in lib.reference_characters_for(group_id) if character.id!=character_id]
        if blocking:
            if MessageBox.question(h,t('Character Reference'),
                t('The animation is the current Character Reference. Clear the Character Reference and move it?'),
                MessageBox.StandardButton.Yes|MessageBox.StandardButton.Cancel,
                MessageBox.StandardButton.Cancel)!=MessageBox.StandardButton.Yes:return
            clear=True
        def operation(tree):
            tree.set_group_character(group_id,character_id,clear,clear_sets=clear_sets)
            tree.groups[group_id].alignment_review_required=True
            return True
        self.mutate(operation,'Move to Character')
        h.project.sync_character_reference()

    def drop_group_on_character(self,group_id,character_id):
        "Drop On a Character or Loose Groups node: the Group becomes one of that owner's roots."
        h=self.host;lib=h.project.library
        if h.interaction_busy or group_id not in lib.groups:return None
        group=lib.groups[group_id]
        if group.character_id==character_id and group.parent_id is None:return group_id
        clear=False;clear_sets=False;clear_machines=False
        if [slot for row,slot in lib.set_references_for_group(group_id) if row.character_id!=character_id]:
            if MessageBox.question(h,t('Move to Character'),
                t('The Animation is used by an Animation Set. Clear the references and move it?'),
                MessageBox.StandardButton.Yes|MessageBox.StandardButton.Cancel,
                MessageBox.StandardButton.Cancel)!=MessageBox.StandardButton.Yes:return None
            clear_sets=True
        try:
            lib.check_machine_move(group_id,character_id,False)
        except ValueError:
            if MessageBox.question(h,t('Move to Character'),
                t('The Animation is used by a State Machine. Clear the references and move it?'),
                MessageBox.StandardButton.Yes|MessageBox.StandardButton.Cancel,
                MessageBox.StandardButton.Cancel)!=MessageBox.StandardButton.Yes:return None
            clear_machines=True
        if [character for character in lib.reference_characters_for(group_id) if character.id!=character_id]:
            if MessageBox.question(h,t('Character Reference'),
                t('The animation is the current Character Reference. Clear the Character Reference and move it?'),
                MessageBox.StandardButton.Yes|MessageBox.StandardButton.Cancel,
                MessageBox.StandardButton.Cancel)!=MessageBox.StandardButton.Yes:return None
            clear=True
        def operation(tree):
            tree.set_group_character(group_id,character_id,clear,clear_sets=clear_sets,clear_machines=clear_machines)
            tree.move_group(group_id,None,clear_references=clear,clear_sets=clear_sets,clear_machines=clear_machines)
            tree.groups[group_id].alignment_review_required=True
            return group_id
        result=self.mutate(operation,'Move to Character')
        h.project.sync_character_reference()
        return result

    def _derived_folder(self,project_file,name):
        "Snapshot frames live in the project workspace, never in a temporary directory."
        root=(Path(project_file).parent/'sequences') if project_file else Path(tempfile.gettempdir())/'AI Video to Sprite'/'derived'
        root.mkdir(parents=True,exist_ok=True)
        base=sanitize_project_name(name) or 'Derived Sequence'
        folder=root/base;number=2
        while folder.exists():
            folder=root/f'{base} {number}';number+=1
        folder.mkdir()
        return folder

    def move_selected_frames(self,source_animation_id,frame_indices,group_id,name=None):
        """Move canonical frames into another Group as a new Sequence.

        Only library records and canonical pixels move: the user's own media on disk is
        never touched, and nothing is rendered through the FinalFrameProvider.
        """
        h=self.host
        if h.interaction_busy:return None
        library=h.project.library
        if group_id not in library.groups:return None
        # Timeline order is the contract; only duplicates are dropped.
        frames=list(dict.fromkeys(int(index) for index in frame_indices if int(index)>=0))
        if not frames:return None
        owner=library.animation(source_animation_id)
        if owner is None:
            h.status.setText(t('The source Animation is no longer in the project.'));return None
        base=h.project
        source=base if base.animation_id==source_animation_id else base.select_animation(source_animation_id)
        count=source.video.frame_count
        frames=[index for index in frames if index<count]
        if not frames or len(frames)>=count:
            h.status.setText(t('Keep at least one frame in the source Animation.'));return None
        keep=[index for index in range(count) if index not in set(frames)]
        mapping_target={new:old for new,old in enumerate(frames)}
        mapping_keep={new:old for new,old in enumerate(keep)}
        fps=source.video.fps or base.default_fps
        directory=cache_directory(source.project_id,h.project_file,source_animation_id)
        canonical=canonical_folder(directory)
        edits_root=project_cache_root(source.project_id,h.project_file)/'pixel_edits'
        from app.core.pipeline import Pipeline
        try:
            # 1. The source keeps its remaining canonical frames and its Animation Transform.
            keep_folder=self._derived_folder(h.project_file,owner.name)
            copy_canonical_frames(canonical,keep,keep_folder)
            previous=base.current_group_id
            base.current_group_id=owner.group_id
            try:
                reduced=base.import_frame_sequence(keep_folder,fps,True,'strict')
            finally:
                base.current_group_id=previous
            reduced.motion_settings.enabled=False
            reduced.animation_transform=copy.deepcopy(source.animation_transform)
            reduced.export_settings=copy.deepcopy(source.export_settings)
            reduced_directory=cache_directory(reduced.project_id,h.project_file,reduced.animation_id)
            Pipeline(reduced,reduced_directory).import_sequence()
            Pipeline(reduced,reduced_directory).ensure_aligned()
            # Per-frame state is applied once the frame count is authoritative.
            apply_frame_state(reduced,source,mapping_keep,fps)
            # 2. The target holds only the moved frames; its own Animation Transform starts at (0,0).
            target_folder=self._derived_folder(h.project_file,name or library.groups[group_id].name)
            copy_canonical_frames(canonical,frames,target_folder)
            previous=reduced.current_group_id
            reduced.current_group_id=group_id
            try:
                final=reduced.import_frame_sequence(target_folder,fps,True,'strict')
            finally:
                reduced.current_group_id=previous
            final.motion_settings.enabled=False
            target_directory=cache_directory(final.project_id,h.project_file,final.animation_id)
            Pipeline(final,target_directory).import_sequence()
            Pipeline(final,target_directory).ensure_aligned()
            apply_frame_state(final,source,mapping_target,fps)
            # 3. Pencil / Eraser layers belong to the frame and move with it.
            copy_raster_edits(reduced,source,mapping_keep,edits_root,edits_root)
            copy_raster_edits(final,source,mapping_target,edits_root,edits_root)
        except (ValueError,OSError,KeyError) as error:
            h.status.setText(t('Cannot move frames: {error}',error=str(error)));return None
        # 4. Library records: the source keeps its identity, the target becomes a new Sequence.
        records=final.library
        original_row=records.animation(source_animation_id)
        reduced_row=records.animation(reduced.animation_id)
        target_row=records.animation(final.animation_id)
        original_source=records.resources.get(original_row.source_id) if original_row is not None else None
        reduced_source=records.resources.get(reduced_row.source_id) if reduced_row is not None else None
        target_source=records.resources.get(target_row.source_id) if target_row is not None else None
        if not all((original_row,reduced_row,target_row,reduced_source,target_source)):
            h.status.setText(t('The source Animation is no longer in the project.'));return None
        provenance={'source_animation_id':source_animation_id,'source_frame_indices':list(frames),
                    'created_at':now_stamp(),'moved':True}
        target_row.name=unique_name(name or library.groups[group_id].name,
            [row.name for row in library.in_group(group_id) if row.kind=='ANIMATION'],'_')
        target_row.metadata=dict(provenance)
        target_row.ready=False
        target_source.name=target_row.name+' Source'
        target_source.metadata=dict(provenance)
        target_source.ready=False
        final.export_settings.animation_name=target_row.name
        original_row.animation_id=reduced.animation_id
        original_row.metadata={**original_row.metadata,'moved_frames_out':len(frames)}
        original_row.ready=False
        original_source.path=reduced_source.path
        original_source.metadata={**original_source.metadata,'repacked':True}
        original_source.ready=False
        records.resources.pop(reduced_row.id,None)
        records.resources.pop(reduced_source.id,None)
        for sheet in records.generated_sheets(source_animation_id):
            sheet.animation_id=reduced.animation_id
            sheet.ready=False
        # Workspace state follows the Animation identity, never a retired id.
        for group in records.groups.values():
            owners={row.animation_id for row in records.in_group(group.id,kinds={'ANIMATION'})}
            states={}
            for key,value in group.animation_states.items():
                if key==source_animation_id and reduced.animation_id in owners:
                    moved_state=copy.deepcopy(value)
                    reference=moved_state.frame_reference
                    if reference and reference.get('animation_id')==source_animation_id:
                        # The edit reference belongs to the frame data that stayed here.
                        moved_state.frame_reference=dict(reference,animation_id=reduced.animation_id)
                    states[reduced.animation_id]=moved_state
                elif key in owners:
                    states[key]=value
            group.animation_states=states
            selected=group.ui_state.animation_id
            if selected==source_animation_id and reduced.animation_id in owners:
                group.ui_state.animation_id=reduced.animation_id
            elif selected and selected not in owners:
                group.ui_state.animation_id=None
        mark_generated_stale(records,reduced.animation_id)
        mark_generated_stale(records,final.animation_id)
        records.refresh_status()
        invalidate_sheet_manifest(reduced_directory)
        invalidate_sheet_manifest(target_directory)
        try:
            records.validate()
        except ValueError as error:
            h.status.setText(t('Cannot move frames: {error}',error=str(error)));return None
        # 5. One Undo Command for the whole move; both Animations already live on disk.
        original_snapshot=(base.animation_snapshot() if base.animation_id==source_animation_id
                           else copy.deepcopy(base.animations.get(source_animation_id) or {}))
        if not original_snapshot:
            h.status.setText(t('The source Animation is no longer in the project.'));return None
        # The retired Animation lives in the Undo entry only: a leftover snapshot would be
        # revived as a brand new library record by ensure_library().
        final.animations.pop(source_animation_id,None)
        before={'library':asdict(library),'animations':{source_animation_id:copy.deepcopy(original_snapshot)},
                'animation_id':source_animation_id,'group':owner.group_id}
        final.animations[reduced.animation_id]=reduced.animation_snapshot()
        after={'library':asdict(final.library),
               'animations':{source_animation_id:copy.deepcopy(original_snapshot),
                             reduced.animation_id:reduced.animation_snapshot(),
                             final.animation_id:final.animation_snapshot()},
               'animation_id':final.animation_id,'group':group_id}
        h._invalidate_reviews(False)
        h.project,h.cache_dir=final,target_directory
        h.project.current_group_id=owner.group_id
        h.project.current_character_id=final.library.groups[owner.group_id].character_id
        h.dirty,h.built=True,False
        self.record(('frames',before,after,'Move Frames'))
        h.preview_cache.clear()
        h._loaded()
        self.refresh()
        self.select_animation(reduced.animation_id)
        h.status.setText(t('Moved {count} frame(s) to {group}.',count=len(frames),
            group=final.library.groups[group_id].name))
        return final.library.animation(final.animation_id).id

    def remove_character(self,ident,confirmed=False):
        lib=self.host.project.library
        character=lib.characters.get(ident)
        if not character:return
        members=lib.character_members(ident)
        animations=sum(len(lib.in_group(group.id,True,{'ANIMATION'})) for group in members)
        if not confirmed:
            message=('Move contents to Loose Groups and delete this Character?' if members else 'Remove this empty Character?')
            if MessageBox.question(self.host,t('Delete Character'),message,
                MessageBox.StandardButton.Yes|MessageBox.StandardButton.Cancel,
                MessageBox.StandardButton.Cancel)!=MessageBox.StandardButton.Yes:return
        self.mutate(lambda tree:tree.remove_character(ident,move_to_loose=True),'Delete Character')
        if ident not in self.host.project.library.characters:
            self.host.project.current_character_id=None
            self.host.project.sync_character_reference()
            self.select_group(None,capture=False)

    def open_character_reference(self):
        self.host.open_character_reference()

    def animation_sets(self, character_id=None):
        h=self.host;character_id=character_id or h.project.current_character_id
        return h.project.library.animation_sets_for(character_id) if character_id else []

    def select_animation_set(self, set_id):
        "Refresh the Character panel slot list; selection is pure UI state."
        if hasattr(self.host,'character_page'):self.host.character_page.show_set(set_id)
        return set_id

    def new_animation_set(self, name=None, semantic_type=''):
        h=self.host;character_id=h.project.current_character_id
        if not character_id:return None
        if name is None:
            name,ok=QInputDialog.getText(h,t('New Animation Set'),t('Animation Set name'),QLineEdit.EchoMode.Normal,t('New Set'))
            if not ok:return None
        slots=[AnimationSlot(display_name) for display_name in ('Slot 1',)]
        row=self.mutate(lambda lib:lib.add_animation_set(character_id,name,semantic_type or 'custom',slots),'New Animation Set')
        if row:self.select_animation_set(row.id)
        return row

    def template_animation_sets(self):
        h=self.host;character=h.project.active_character()
        if character is None:return []
        registry=REGISTRY
        if character.template_id not in registry.ids():
            h.status.setText(t('This Character has no template to create Animation Sets from.'));return []
        created=self.mutate(lambda lib:registry.get(character.template_id).create_animation_sets(lib,character),'Animation Sets From Template')
        if created:self.select_animation_set(created[0].id)
        return created

    def auto_match_animation_set(self, set_id):
        matched=self.mutate(lambda lib:lib.auto_match_set(set_id),'Auto Match Animation Set')
        self.select_animation_set(set_id)
        if self.host.interaction_busy:return matched
        self.host.status.setText(t('Matched {count} slot(s).',count=matched if matched is not None else 0))
        return matched

    def slot_choices(self, set_id):
        row=self.host.project.library.animation_sets.get(set_id)
        return [(slot.display_name,slot.id) for slot in row.slots] if row else []

    def animation_choices(self, character_id):
        library=self.host.project.library
        return [(resource.name,resource.animation_id) for resource in library.resources.values()
                if resource.kind=='ANIMATION' and resource.ready and library.groups[resource.group_id].character_id==character_id]

    def bind_slot_dialog(self,set_id):
        h=self.host;row=h.project.library.animation_sets.get(set_id)
        if row is None:return None
        slots=self.slot_choices(set_id);animations=self.animation_choices(row.character_id)
        if not slots or not animations:
            h.status.setText(t('Bind at least one ready Animation first.'));return None
        slot_label,ok=QInputDialog.getItem(h,t('Bind Animation'),t('Animation Slot'),[label for label,_ in slots],0,False)
        if not ok:return None
        animation_label,ok=QInputDialog.getItem(h,t('Bind Animation'),t('Animation'),[label for label,_ in animations],0,False)
        if not ok:return None
        return self.bind_animation_to_slot(set_id,dict(slots)[slot_label],dict(animations)[animation_label])

    def clear_slot_dialog(self,set_id):
        h=self.host;slots=self.slot_choices(set_id)
        if not slots:return None
        slot_label,ok=QInputDialog.getItem(h,t('Clear Binding'),t('Animation Slot'),[label for label,_ in slots],0,False)
        if not ok:return None
        return self.clear_animation_slot(set_id,dict(slots)[slot_label])

    def bind_animation_to_slot(self,set_id,slot_id,animation_id=None):
        result=self.mutate(lambda lib:lib.bind_slot(set_id,slot_id,animation_id),'Bind Animation')
        self.select_animation_set(set_id)
        return result

    def clear_animation_slot(self,set_id,slot_id):
        self.bind_animation_to_slot(set_id,slot_id,None)

    def remove_animation_set(self,set_id,confirmed=False):
        row=self.host.project.library.animation_sets.get(set_id)
        if row is None:return None
        if not confirmed and MessageBox.question(self.host,t('Remove Animation Set'),
                t('Remove this Animation Set? Animations themselves are never deleted.'),
                MessageBox.StandardButton.Yes|MessageBox.StandardButton.Cancel,
                MessageBox.StandardButton.Cancel)!=MessageBox.StandardButton.Yes:return None
        self.mutate(lambda lib:lib.remove_animation_set(set_id),'Remove Animation Set')
        return set_id

    def state_machines(self, character_id=None):
        h=self.host;character_id=character_id or h.project.current_character_id
        return h.project.library.state_machines_for(character_id) if character_id else []

    def state_content_choices(self, sets=False):
        h=self.host;character=h.project.active_character()
        if character is None:return []
        library=h.project.library
        if sets:
            return [(row.name,row.id) for row in library.animation_sets_for(character.id)]
        return [(resource.name,resource.animation_id) for resource in library.resources.values()
                if resource.kind=='ANIMATION' and resource.ready and library.groups[resource.group_id].character_id==character.id]

    def new_state_machine(self,name=None,character_id=None):
        h=self.host;character_id=character_id or h.project.current_character_id
        if not character_id:return None
        if name is None:
            name,ok=QInputDialog.getText(h,t('New State Machine'),t('State Machine name'),QLineEdit.EchoMode.Normal,t('State Machine'))
            if not ok:return None
        machine=self.mutate(lambda lib:lib.add_state_machine(character_id,name),'New State Machine')
        self.refresh()
        return machine

    def template_state_machines(self):
        h=self.host;character=h.project.active_character()
        if character is None:return []
        if character.template_id not in REGISTRY.ids():
            h.status.setText(t('This Character has no template to create a State Machine from.'));return []
        created=self.mutate(lambda lib:REGISTRY.get(character.template_id).create_state_machines(lib,character),'State Machine From Template')
        self.refresh()
        return created or []

    def remove_state_machine(self,ident,confirmed=False):
        if self.host.project.library.state_machine(ident) is None:return None
        if not confirmed and MessageBox.question(self.host,t('Remove State Machine'),
                t('Remove this State Machine? Animations and Animation Sets are never deleted.'),
                MessageBox.StandardButton.Yes|MessageBox.StandardButton.Cancel,
                MessageBox.StandardButton.Cancel)!=MessageBox.StandardButton.Yes:return None
        self.mutate(lambda lib:lib.remove_state_machine(ident),'Remove State Machine')
        return ident

    def add_state(self,machine_id,name,kind,binding_id):
        def operation(lib):
            machine=lib.state_machine(machine_id)
            return machine.add_state(name,kind=kind,animation_id=binding_id if kind=='animation' else None,
                set_id=binding_id if kind=='set' else None)
        return self.mutate(operation,'Add State')

    def remove_state(self,machine_id,state_id):
        self.mutate(lambda lib:lib.state_machine(machine_id).remove_state(state_id),'Remove State')

    def set_entry_state(self,machine_id,state_id):
        def operation(lib):
            machine=lib.state_machine(machine_id);machine.entry_state=state_id;machine.modified_at=now_stamp();return state_id
        return self.mutate(operation,'Set Entry State')

    def add_transition(self,machine_id,from_state,to_state):
        if from_state is None or to_state is None:return None
        return self.mutate(lambda lib:lib.state_machine(machine_id).add_transition(from_state,to_state),'Add Transition')

    def remove_transition(self,machine_id,transition_id):
        self.mutate(lambda lib:lib.state_machine(machine_id).remove_transition(transition_id),'Remove Transition')

    def condition_value(self,machine_id,parameter,text):
        parameter_row=self.host.project.library.state_machine(machine_id).parameter(parameter)
        if parameter_row is None:raise ValueError('State Machine condition uses an unknown parameter')
        text=text.strip()
        if parameter_row.type=='bool':return text.casefold() in ('1','true','yes','on')
        if parameter_row.type=='int':return int(text)
        if parameter_row.type=='float':return float(text)
        return text.casefold() in ('1','true','yes','on')

    def add_condition(self,machine_id,transition_id,parameter,operator,value):
        try:
            parsed=self.condition_value(machine_id,parameter,value)
        except (ValueError,TypeError):
            self.host.status.setText(t('Condition value is invalid for this parameter.'));return None
        def operation(lib):
            row=lib.state_machine(machine_id).transition(transition_id)
            row.conditions.append(Condition(parameter,operator,parsed));row.validate({s.id for s in lib.state_machine(machine_id).states},
                {p.name:p for p in lib.state_machine(machine_id).parameters});return row
        return self.mutate(operation,'Add Condition')

    def remove_condition(self,machine_id,transition_id,index):
        def operation(lib):
            row=lib.state_machine(machine_id).transition(transition_id)
            del row.conditions[index];return row
        return self.mutate(operation,'Remove Condition')

    def save_state_positions(self,machine_id):
        "Node drags are UI state; store them on the machine and mark the project dirty."
        h=self.host;machine=h.project.library.state_machine(machine_id) if machine_id else None
        if machine is None:return
        machine.modified_at=now_stamp();h.dirty=True;self.refresh()

    def open_state_machine_dialog(self,machine_id=None):
        self.host.open_state_machine(machine_id)

    def preview_state_machine(self,machine_id):
        machine=self.host.project.library.state_machine(machine_id)
        if machine is not None:self.host.open_state_machine(machine.id)

    def export_state_machine(self,machine_id):
        machine=self.host.project.library.state_machine(machine_id)
        if machine is not None:self.host.export_state_machine(machine)

    def preview_animation_set(self,set_id):
        row=self.host.project.library.animation_sets.get(set_id)
        if row is not None:self.host.preview_animation_set(row)

    def export_animation_set(self,set_id):
        row=self.host.project.library.animation_sets.get(set_id)
        if row is not None:self.host.export_animation_set(row)

    def move(self,kind,ident,target,index=None):
        if kind=='GROUP' and target is not None:
            lib=self.host.project.library
            if target not in lib.groups:return
            owner=lib.groups[target].character_id
            clear=False
            blocking=[character for character in lib.reference_characters_for(ident) if character.id!=owner]
            if blocking:
                if MessageBox.question(self.host,t('Character Reference'),
                    t('The animation is the current Character Reference. Clear the Character Reference and move it?'),
                    MessageBox.StandardButton.Yes|MessageBox.StandardButton.Cancel,
                    MessageBox.StandardButton.Cancel)!=MessageBox.StandardButton.Yes:return
                clear=True
            operation=(lambda lib:lib.move_group(ident,target,index,clear))
        elif kind=='GROUP':
            operation=(lambda lib:lib.move_group(ident,target,index))
        else:
            operation=(lambda lib:lib.move_resource(ident,target,index))
        self.mutate(operation,'Move')
        row=self.host.project.library.animation(self.host.project.animation_id)
        if row and row.group_id!=self.host.project.current_group_id:self.select_group(row.group_id,row.animation_id,capture=False)

    def resource_related_counts(self,ident):
        lib=self.host.project.library;row=lib.resources.get(ident)
        if row is None or row.kind not in SOURCE_KINDS:return (0,0)
        animations=lib.related_animations(ident)
        return (len(animations),sum(len(lib.generated_sheets(animation.animation_id)) for animation in animations))

    def remove_resource(self,ident,confirmed=False,cascade=False):
        "Remove Project Library records only; source files, caches and exports on disk are never touched."
        h=self.host;lib=h.project.library
        if h.interaction_busy:return None
        row=lib.resources.get(ident)
        if row is None:return None
        clear=False;clear_sets=False
        if row.kind=='ANIMATION' and lib.set_references(row.animation_id):
            if not confirmed and MessageBox.question(h,t('Remove Resource'),
                    t('The Animation is used by an Animation Set. Clear the references and remove it?'),
                    MessageBox.StandardButton.Yes|MessageBox.StandardButton.Cancel,
                    MessageBox.StandardButton.Cancel)!=MessageBox.StandardButton.Yes:return None
            clear_sets=True
        if row.kind=='ANIMATION' and lib.reference_characters_for_animation(row.animation_id):
            if not confirmed and MessageBox.question(h,t('Remove Resource'),
                    t('The animation is the current Character Reference. Clear the Character Reference and remove it?'),
                    MessageBox.StandardButton.Yes|MessageBox.StandardButton.Cancel,
                    MessageBox.StandardButton.Cancel)!=MessageBox.StandardButton.Yes:return None
            clear=True
        elif row.kind in SOURCE_KINDS:
            animations,sheets=self.resource_related_counts(ident)
            if animations and not confirmed:
                index=MessageBox.choice(h,t('Remove Resource'),
                    t('Remove this resource from the project?\n\nRelated: {animations} Animations / {sheets} Sprite Sheets',
                      animations=animations,sheets=sheets),
                    ('Remove source only, keep generated results','Remove related Animations and Sprite Sheets','Cancel'),0)
                if index<0 or index==2:return None
                cascade=index==1
            elif not confirmed and MessageBox.question(h,t('Remove Resource'),
                    t('Remove this resource from the project?'),
                    MessageBox.StandardButton.Yes|MessageBox.StandardButton.Cancel,
                    MessageBox.StandardButton.Cancel)!=MessageBox.StandardButton.Yes:return None
        elif not confirmed:
            message='Remove this Sprite Sheet from the project?' if row.kind=='GENERATED_SPRITE_SHEET' else 'Remove this resource from the project?'
            if MessageBox.question(h,t('Remove Resource'),t(message),
                    MessageBox.StandardButton.Yes|MessageBox.StandardButton.Cancel,
                    MessageBox.StandardButton.Cancel)!=MessageBox.StandardButton.Yes:return None
        p=h.project
        related={row.animation_id} if row.kind in ('ANIMATION','GENERATED_SPRITE_SHEET') else {animation.animation_id for animation in lib.related_animations(ident)}
        current_animation=p.animation_id
        purged=set()
        if row.kind=='ANIMATION':purged.add(row.animation_id)
        elif row.kind in SOURCE_KINDS and cascade:purged.update(animation.animation_id for animation in lib.related_animations(ident))
        removed=self.mutate(lambda tree:tree.remove_resource(ident,cascade=cascade,clear_references=clear,clear_sets=clear_sets),'Remove Resource')
        if not removed:return None
        # The project keeps one snapshot per Animation; drop them so ensure_library() cannot revive deleted records.
        for animation_id in purged:
            p.animations.pop(animation_id,None)
            if p.animation_id==animation_id:
                p.animation_id=''
                p.source_video=''
                p.sequence_folder=''
        if ident==self.asset_id or current_animation in related:
            self.asset_id=None
            self.selection=None
            self.select_group(h.project.current_group_id,capture=False)
        else:
            self.refresh()
            h._update_state()
        h.status.setText(t('Resource removed from the project: {name}',name=row.name))
        return removed

    def reveal_resource(self,ident):
        lib=self.host.project.library;row=lib.resources.get(ident)
        if row is None:return False
        path=row.path
        if not path and row.kind=='GENERATED_SPRITE_SHEET':
            path=str(sheet_path(self.host.project,self.host.project_file,row))
        ok=reveal_in_explorer(path) if path else False
        if not ok:self.host.status.setText(t('The resource could not be found on disk.'))
        return ok

    def export_animation(self,ident):
        row=self.host.project.library.resources.get(ident)
        if row is None or row.kind not in ('ANIMATION','GENERATED_SPRITE_SHEET'):return
        self.select_animation(row.animation_id)
        self.host.choose_export('all')

    def character_summary(self,ident):
        lib=self.host.project.library;character=lib.characters.get(ident)
        if character is None:return t('Character does not exist')
        return t('{groups} Groups / {animations} Animations',groups=len(lib.character_members(ident)),
            animations=lib.character_animation_count(ident))

    def remove_group(self,ident,confirmed=False,mode=None):
        "Delete one Group; a Group with children asks before anything beyond this Group is touched."
        h=self.host;lib=h.project.library
        group=lib.groups.get(ident)
        if group is None:return None
        contents=lib.group_contents(ident)
        children=lib.children(ident)
        rows=lib.in_group(ident)
        summary=t('This Group contains: {groups} child Groups, {resources} resources, {animations} Animations',
            groups=contents['groups'],resources=contents['resources'],animations=contents['animations'])
        if mode is None:
            if confirmed:
                mode='promote' if group.parent_id is not None else ('tree' if (children or rows) else 'promote')
            elif children and group.parent_id is not None:
                choice=MessageBox.choice(h,t('Remove Group'),summary,
                    ('Remove the Group and Promote its Contents','Delete the Entire Group Tree','Cancel'),0)
                if choice<0 or choice==2:return None
                mode='promote' if choice==0 else 'tree'
            elif group.parent_id is None and (children or rows):
                choice=MessageBox.choice(h,t('Remove Group'),summary,('Delete the Entire Group Tree','Cancel'),1)
                if choice!=0:return None
                mode='tree'
            elif rows:
                if MessageBox.question(h,t('Remove Group'),
                        t('Move the contents to the parent Group and remove this Group?'),
                        MessageBox.StandardButton.Yes|MessageBox.StandardButton.Cancel,
                        MessageBox.StandardButton.Cancel)!=MessageBox.StandardButton.Yes:return None
                mode='promote'
            else:
                if MessageBox.question(h,t('Remove Group'),t('Remove this empty Group?'),
                        MessageBox.StandardButton.Yes|MessageBox.StandardButton.Cancel,
                        MessageBox.StandardButton.Cancel)!=MessageBox.StandardButton.Yes:return None
                mode='promote'
        if mode=='tree':
            if not confirmed and MessageBox.question(h,t('Delete Group Tree'),
                    t('Delete this Group with every child Group and resource record? Source files on disk are never deleted.'),
                    MessageBox.StandardButton.Yes|MessageBox.StandardButton.Cancel,
                    MessageBox.StandardButton.Cancel)!=MessageBox.StandardButton.Yes:return None
            animations={r.animation_id for r in lib.in_group(ident,True,{'ANIMATION'})}
            removed=self.mutate(lambda tree:tree.remove_group_tree(ident,clear_references=True,clear_sets=True,clear_machines=True),'Remove Group Tree')
            if removed is None:return None
            for animation_id in animations:
                h.project.animations.pop(animation_id,None)
                if h.project.animation_id==animation_id:
                    h.project.animation_id='';h.project.source_video='';h.project.sequence_folder=''
            if ident not in h.project.library.groups:
                self.asset_id=None;self.selection=None
                self.select_group(group.parent_id if group.parent_id in h.project.library.groups else None,capture=False)
            return removed
        self.mutate(lambda tree:tree.remove_group(ident,move_to_parent=bool(rows or children)),'Remove Group')
        if ident not in h.project.library.groups:
            self.select_group(group.parent_id if group.parent_id in h.project.library.groups else None,capture=False)
            return ident
        return None

    def history(self,redo=False):
        h=self.host
        if h.interaction_busy or not (self.index<len(self.entries) if redo else self.index>0):return False
        entry=self.entries[self.index if redo else self.index-1]
        if entry[0]=='edit':
            _,key,before,after,label=entry
            if h.project.animation_id!=key[1]:self.select_animation(key[1])
            state=copy.deepcopy(after if redo else before)
            if before.get("character_reference")==after.get("character_reference"):
                state["character_reference"]=asdict(h.project.character_reference) if h.project.character_reference else None
            history=h.edit_histories.get(key)
            if history:history.redo() if redo else history.undo()
            h._sync_character_owner(state["character_reference"])
            h._restore_edit(state)
        elif entry[0]=='frames':
            # A frame move keeps both Animations on disk; undo only re-points records.
            _,before,after,label=entry
            wanted=before if not redo else after
            other=after if not redo else before
            if h.project.source_path:
                h.project.animations[h.project.animation_id]=h.project.animation_snapshot()
            try:
                h.project.library=ProjectLibrary.from_dict(wanted['library'])
            except ValueError:
                h.status.setText(t('Cannot undo this frame move.'));return False
            owners={row.animation_id for row in h.project.library.resources.values()
                    if row.kind=='ANIMATION' and row.animation_id}
            for ident in set(other['animations'])|set(wanted['animations'])|owners:
                if ident in wanted['animations'] and ident in owners:
                    h.project.animations[ident]=copy.deepcopy(wanted['animations'][ident])
                elif ident not in owners:
                    h.project.animations.pop(ident,None)
            h.project.animation_id='default'
            h.project.source_video=''
            h.project.sequence_folder=''
            group=wanted['group'] if wanted['group'] in h.project.library.groups else None
            self.select_group(group,capture=False)
            if wanted['animation_id'] and h.project.library.animation(wanted['animation_id']):
                self.select_animation(wanted['animation_id'])
        else:
            _,before,after,old_group,new_group,label=entry
            # UI state, readiness and background results are not edit instructions.
            expected=after if not redo else before;wanted=before if not redo else after
            data=asdict(h.project.library)
            for collection in ('groups','resources'):
                for ident in set(expected[collection])|set(wanted[collection]):
                    a=expected[collection].get(ident);b=wanted[collection].get(ident)
                    if a==b:continue
                    if b is None:data[collection].pop(ident,None)
                    elif a is None:data[collection][ident]=copy.deepcopy(b)
                    else:
                        current=data[collection].get(ident,copy.deepcopy(b))
                        for key in set(a)|set(b):
                            if a.get(key)!=b.get(key):current[key]=copy.deepcopy(b.get(key))
                        data[collection][ident]=current
            # Workspace UI state is not an edit instruction: drop selections the restored model cannot satisfy.
            owners={row.get('animation_id'):row.get('group_id') for row in data['resources'].values()
                if row.get('kind')=='ANIMATION'}
            for ident,row in data['groups'].items():
                state=row.get('ui_state') or {}
                if state.get('animation_id') and owners.get(state['animation_id'])!=ident:
                    row.setdefault('ui_state',{})['animation_id']=None
                row['animation_states']={key:value for key,value in (row.get('animation_states') or {}).items()
                    if owners.get(key)==ident}
            try:h.project.library=ProjectLibrary.from_dict(data)
            except ValueError:
                h.status.setText(t('Move newly imported resources before undoing Group creation.'));return False
            # Snapshots of removed Animations must never revive through ensure_library().
            for animation_id in list(h.project.animations):
                if h.project.library.animation(animation_id) is None:
                    h.project.animations.pop(animation_id,None)
            if h.project.library.animation(h.project.animation_id) is None:
                # The undo removed the Animation this Project was showing; drop the pointer too.
                h.project.animation_id='default'
                h.project.source_video=''
                h.project.sequence_folder=''
            group=new_group if redo else old_group
            self.select_group(group if group in h.project.library.groups else None,capture=False)
        self.index+=1 if redo else -1;h.dirty=True;self.refresh();h._update_state();return True

    def choose_sheet(self):
        if self.host.interaction_busy or not self.require_group():return
        paths,_=FileDialog.getOpenFileNames(self.host,'Import Sprite Sheet','','Images (*.png *.webp *.tif *.tiff *.bmp *.jpg *.jpeg)',purpose='sprite_sheet_import')
        for path in paths:self.import_sheet(path)

    def import_sheet(self,path):
        h=self.host
        if h.interaction_busy or not self.require_group():return
        path=Path(path).resolve()
        try:
            pixels=read_rgba(path)
            metadata={'width':pixels.shape[1],'height':pixels.shape[0],'channels':pixels.shape[2],'bits_per_channel':pixels.dtype.itemsize*8}
            resource=self.mutate(lambda lib:lib.add_sheet(h.project.current_group_id,path.name,str(path),metadata),'Import Sprite Sheet')
            if resource:h._remember_path('sprite_sheet_import',path,file=True);self.activate('RESOURCE',resource.id)
            return resource
        except (OSError,ValueError) as error:h._failed(str(error))

    def preview_sprite_sheet(self,resource_id):
        "Show the original Sprite Sheet in the asset view."
        self.activate('RESOURCE',resource_id)
        return resource_id

    def _sheet_default_config(self,pixels):
        height,width=pixels.shape[:2]
        rows=2 if abs(width-height)<=max(1,round(max(width,height)*.05)) else 1
        return SliceConfig(columns=4,rows=rows,cell_width=max(1,width//4),cell_height=max(1,height//rows),
            fps=DEFAULT_FPS)

    def open_sprite_sheet_slicer(self,resource_id,force_new=False):
        "One dialog for Slice / Create Animation; re-slicing asks about the existing Animation."
        h=self.host;library=h.project.library
        if h.interaction_busy:return None
        row=library.resources.get(resource_id)
        if row is None or row.kind not in ('SOURCE_SPRITE_SHEET','GENERATED_SPRITE_SHEET'):
            h.status.setText(t('The Sprite Sheet is no longer in the project.'));return None
        existing=None;mode='new'
        sliced=row.metadata.get('sliced_animation')
        if sliced and not force_new and library.animation(sliced) is not None:
            choice=MessageBox.choice(h,t('Slice Sprite Sheet'),
                t('This Sprite Sheet already created an Animation.'),
                ('Create a new Animation','Replace the existing Animation','Cancel'),0)
            if choice<0 or choice==2:return None
            mode='replace' if choice==1 else 'new'
            existing=library.animation(sliced).name
        try:
            pixels=to_rgba8(read_rgba(sheet_path(h.project,h.project_file,row)))
        except (OSError,ValueError) as error:
            h.status.setText(t('Cannot read the Sprite Sheet: {error}',error=str(error)));return None
        stored=row.metadata.get('slice_config')
        try:
            config=SliceConfig.from_dict(stored) if stored else self._sheet_default_config(pixels)
        except ValueError:
            config=self._sheet_default_config(pixels)
        from app.ui.sprite_sheet_slicer_dialog import SpriteSheetSlicerDialog
        dialog=SpriteSheetSlicerDialog(h,row.name,pixels,config=config,mode=mode,existing=existing)
        if dialog.exec()!=QDialog.DialogCode.Accepted or dialog.result_config is None:return None
        return self.slice_sprite_sheet(resource_id,dialog.result_config,mode=mode)

    def slice_sprite_sheet(self,resource_id,config,mode='new'):
        """Fixed-cell slice of an imported Sprite Sheet into a sequence and an Animation.

        Cells keep their exact size, position and alpha: no trim, no resize and no second
        normalize. The original sheet resource and its PNG stay untouched.
        """
        h=self.host
        if h.interaction_busy:return None
        library=h.project.library
        row=library.resources.get(resource_id)
        if row is None or row.kind not in ('SOURCE_SPRITE_SHEET','GENERATED_SPRITE_SHEET'):
            h.status.setText(t('The Sprite Sheet is no longer in the project.'));return None
        if not isinstance(config,SliceConfig):
            config=SliceConfig.from_dict(config)
        base=h.project
        try:
            pixels=to_rgba8(read_rgba(sheet_path(base,h.project_file,row)))
            # The preview and this slice must agree: refuse a grid with cells outside the sheet.
            layout=calculate_cells(config,pixels)
            if layout.invalid:
                h.status.setText(t('Cells outside the sheet: {count}',count=len(layout.invalid)));return None
            if not layout.frames:
                h.status.setText(t('The Sprite Sheet grid selects no frames'));return None
            resolved,frames,skipped=slice_frames(pixels,config)
        except (OSError,ValueError) as error:
            h.status.setText(t('Cannot slice the Sprite Sheet: {error}',error=str(error)));return None
        name=Path(row.name).stem or 'Sprite'
        folder=self._derived_folder(h.project_file,name)
        for index,frame in enumerate(frames):
            save_rgba(folder/f'frame_{index:06d}.png',frame)
        previous=base.current_group_id
        base.current_group_id=row.group_id
        try:
            final=base.import_frame_sequence(folder,resolved.fps,True,'strict')
        finally:
            base.current_group_id=previous
        final.motion_settings.enabled=False
        final.export_settings.loop=bool(resolved.loop)
        target_directory=cache_directory(final.project_id,h.project_file,final.animation_id)
        from app.core.pipeline import Pipeline
        try:
            Pipeline(final,target_directory).import_sequence()
            Pipeline(final,target_directory).ensure_aligned()
        except (ValueError,OSError) as error:
            h.status.setText(t('Cannot slice the Sprite Sheet: {error}',error=str(error)));return None
        # The Timeline shows the sliced frames immediately, exactly like Prepare Editor does.
        final.timeline_edit.initialize(final.video.frame_count,resolved.fps)
        records=final.library
        animation_row=records.animation(final.animation_id)
        sequence_row=records.resources.get(animation_row.source_id) if animation_row is not None else None
        sheet_row=records.resources.get(resource_id)
        if animation_row is None or sequence_row is None or sheet_row is None:
            h.status.setText(t('The Sprite Sheet is no longer in the project.'));return None
        slice_metadata={'slice_config':asdict(resolved),'sliced_frames':len(frames),
                        'skipped_empty':skipped,'sliced_at':now_stamp()}
        animation_row.name=unique_name(name,[other.name for other in records.in_group(row.group_id)
            if other.kind=='ANIMATION' and other.id!=animation_row.id],'_')
        animation_row.metadata=dict(slice_metadata,slice_source=resource_id)
        animation_row.ready=False
        sequence_row.name=animation_row.name+'_Source'
        sequence_row.metadata=dict(slice_metadata,slice_source=resource_id)
        final.export_settings.animation_name=animation_row.name
        replaced=None
        if mode=='replace' and sheet_row.metadata.get('sliced_animation') not in (None,animation_row.animation_id):
            old_id=sheet_row.metadata.get('sliced_animation')
            old_row=records.animation(old_id)
            if old_row is not None:
                replaced=old_row.name
                old_sequence=records.resources.get(old_row.source_id)
                records.resources.pop(old_row.id,None)
                if old_sequence is not None:
                    records.resources.pop(old_sequence.id,None)
                for sheet in records.generated_sheets(old_id):
                    records.resources.pop(sheet.id,None)
                for group in records.groups.values():
                    group.animation_states.pop(old_id,None)
                    if group.ui_state.animation_id==old_id:group.ui_state.animation_id=None
                final.animations.pop(old_id,None)
        sheet_row.metadata=dict(sheet_row.metadata,**slice_metadata,sliced_animation=animation_row.animation_id)
        try:
            records.validate()
        except ValueError as error:
            h.status.setText(t('Cannot slice the Sprite Sheet: {error}',error=str(error)));return None
        recorded=sheet_row.metadata.get('sliced_animation')
        original_snapshot=(base.animation_snapshot() if base.source_path
                           else copy.deepcopy(base.animations.get(base.animation_id) or {}))
        before={'library':asdict(library),'animations':({base.animation_id:copy.deepcopy(original_snapshot)}
                if original_snapshot else {}),'animation_id':base.animation_id,'group':base.current_group_id}
        after={'library':asdict(final.library),
               'animations':({base.animation_id:copy.deepcopy(original_snapshot)} if original_snapshot else {}),
               'animation_id':final.animation_id,'group':row.group_id}
        after['animations'][final.animation_id]=final.animation_snapshot()
        h._invalidate_reviews(False)
        h.project,h.cache_dir=final,target_directory
        h.project.current_group_id=row.group_id
        h.project.current_character_id=final.library.groups[row.group_id].character_id
        h.dirty,h.built=True,False
        self.record(('frames',before,after,'Slice Sprite Sheet'))
        h.preview_cache.clear()
        h._loaded()
        self.refresh()
        self.select_animation(final.animation_id)
        h.status.setText(t('Created {frames}-frame animation {name} from the Sprite Sheet.',
            frames=len(frames),name=final.library.animation(final.animation_id).name))
        return final.library.animation(final.animation_id).id

    def export_groups(self,batch=False):
        if self.host.interaction_busy:return
        from app.ui.group_export_dialog import GroupExportDialog
        dialog=GroupExportDialog(self.host,batch)
        dialog.exec()

    def drop_files(self,group,paths):
        h=self.host
        if group not in h.project.library.groups or h.interaction_busy:return False
        self.select_group(group)
        queue=list(paths)
        def next_file():
            if h.worker or h.sequence_dialog:QTimer.singleShot(100,next_file);return
            if not queue:return
            self.select_group(group)
            path=Path(queue.pop(0))
            if path.is_dir():h.import_sequence(path)
            elif path.suffix.lower() in {'.mp4','.mov','.avi','.mkv','.webm'}:h.import_video(path)
            elif path.suffix.lower() in {'.png','.webp','.tif','.tiff','.bmp','.jpg','.jpeg'}:self.import_sheet(path)
            QTimer.singleShot(100,next_file)
        next_file();return True
