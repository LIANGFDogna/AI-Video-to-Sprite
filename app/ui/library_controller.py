"""Group workspace coordination. Selection is cache-only and never runs Pipeline stages."""
from __future__ import annotations
import copy
from dataclasses import asdict
import json
from pathlib import Path
from PIL import Image
import numpy as np
from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QDialog, QInputDialog, QLineEdit
from app.i18n import t
from app.models.project import Project
from app.models.character_templates import REGISTRY
from app.models.project_library import ProjectLibrary, WorkspaceState, unique_name
from app.ui.character_dialogs import CharacterDialog
from app.ui.character_panel import character_label
from app.models.timeline_edit import EditHistory
from app.ui.dialogs import MessageBox, FileDialog
from app.utils.paths import cache_directory
from app.utils.rgba_image import read_rgba, to_rgba8
from app.core.group_export import sheet_path


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
            neighbors=e.neighbors.value(),ghost_opacity=e.ghost_opacity.value(),playing=e.timer.isActive(),selected_frames=list(e.selected_ids))
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
            e=h.editor;e.bind();e.inspector.setCurrentIndex(state.editor_tab)
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
        clear=False
        blocking=[character for character in lib.reference_characters_for(group_id) if character.id!=character_id]
        if blocking:
            if MessageBox.question(h,t('Character Reference'),
                t('The animation is the current Character Reference. Clear the Character Reference and move it?'),
                MessageBox.StandardButton.Yes|MessageBox.StandardButton.Cancel,
                MessageBox.StandardButton.Cancel)!=MessageBox.StandardButton.Yes:return
            clear=True
        def operation(tree):
            tree.set_group_character(group_id,character_id,clear)
            tree.groups[group_id].alignment_review_required=True
            return True
        self.mutate(operation,'Move to Character')
        h.project.sync_character_reference()

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

    def character_summary(self,ident):
        lib=self.host.project.library;character=lib.characters.get(ident)
        if character is None:return t('Character does not exist')
        return t('{groups} Groups / {animations} Animations',groups=len(lib.character_members(ident)),
            animations=lib.character_animation_count(ident))

    def remove_group(self,ident,confirmed=False):
        lib=self.host.project.library;g=lib.groups[ident]
        contents=bool(lib.in_group(ident) or lib.children(ident))
        if contents and g.parent_id is None:
            MessageBox.information(self.host,'Remove Group','Group contains resources. Move them to another Group first.');return
        if not confirmed:
            message='Move contents to the parent Group and remove this Group?' if contents else 'Remove this empty Group?'
            if MessageBox.question(self.host,'Remove Group',message,MessageBox.StandardButton.Yes|MessageBox.StandardButton.Cancel,MessageBox.StandardButton.Cancel)!=MessageBox.StandardButton.Yes:return
        self.mutate(lambda tree:tree.remove_group(ident,move_to_parent=contents),'Remove Group')
        if ident not in self.host.project.library.groups:self.select_group(g.parent_id,capture=False)

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
            try:h.project.library=ProjectLibrary.from_dict(data)
            except ValueError:
                h.status.setText(t('Move newly imported resources before undoing Group creation.'));return False
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
