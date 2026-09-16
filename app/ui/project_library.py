"""Persistent project hierarchy and the single media Add entry point."""
import json
from PySide6.QtCore import Qt, QMimeData
from PySide6.QtGui import QDrag, QColor
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLineEdit,QLabel,QPushButton,
    QTreeWidget,QTreeWidgetItem,QMenu,QAbstractItemView,QInputDialog,QStyle)
from app.i18n import t
from app.ui.character_panel import character_label

ROLE=Qt.ItemDataRole.UserRole
MIME='application/x-aivsprite-library'


def reorder_index(lib,kind,dragged_id,container,index):
    """Convert a drop index measured on the full sibling list into post-removal coordinates.

    The model removes the dragged item before inserting at index, so dropping below a
    sibling that currently sits after the dragged item must shift the index by one.
    """
    if index is None:return None
    if kind=='GROUP':
        if lib.groups[dragged_id].parent_id!=container:return index
        current=next((i for i,g in enumerate(lib.children(container)) if g.id==dragged_id),None)
    else:
        if lib.resources[dragged_id].group_id!=container:return index
        current=next((i for i,r in enumerate(lib.in_group(container)) if r.id==dragged_id),None)
    return index-1 if current is not None and current<index else index


class LibraryTree(QTreeWidget):
    def __init__(self,panel):
        super().__init__(panel);self.panel=panel
        self.setColumnCount(2);self.setHeaderLabels([t('Project Library'),t('Animations')])
        self.setColumnWidth(0,225);self.setColumnWidth(1,75)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setDragEnabled(True);self.setAcceptDrops(True);self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(panel.context_menu)
        self.currentItemChanged.connect(lambda item,old:panel.activate(item))

    def startDrag(self,actions):
        item=self.currentItem()
        if not item or item.data(0,ROLE)[0]=='PROJECT' or self.panel.host.interaction_busy:return
        kind,ident=item.data(0,ROLE)
        mime=QMimeData();mime.setData(MIME,json.dumps([kind,ident]).encode())
        drag=QDrag(self);drag.setMimeData(mime);drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self,event):
        if not self.panel.host.interaction_busy and (event.mimeData().hasFormat(MIME) or event.mimeData().hasUrls()):event.acceptProposedAction()
        else:event.ignore()

    def dragMoveEvent(self,event):
        item=self.itemAt(event.position().toPoint());data=item.data(0,ROLE) if item else ('PROJECT',None)
        if not self.panel.host.interaction_busy and (event.mimeData().hasFormat(MIME) or event.mimeData().hasUrls() and data[0]=='GROUP'):
            super().dragMoveEvent(event);event.acceptProposedAction()
        else:event.ignore()

    def dropEvent(self,event):
        if self.panel.host.interaction_busy:event.ignore();return
        item=self.itemAt(event.position().toPoint());kind,ident=item.data(0,ROLE) if item else ('PROJECT',None)
        control=self.panel.controller
        if event.mimeData().hasUrls():
            if kind!='GROUP':event.ignore();self.panel.host.status.setText(t('Drop media onto a Group, not the Project Root.'));return
            paths=[u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
            if control.drop_files(ident,paths):event.acceptProposedAction()
            return
        if not event.mimeData().hasFormat(MIME):event.ignore();return
        dragged_kind,dragged_id=json.loads(bytes(event.mimeData().data(MIME)))
        lib=self.panel.host.project.library;index=None
        position=self.dropIndicatorPosition()
        adjacent=position in (QAbstractItemView.DropIndicatorPosition.AboveItem,QAbstractItemView.DropIndicatorPosition.BelowItem)
        if dragged_kind=='GROUP':
            if kind=='CHARACTER':
                control.move_to_character(dragged_id,ident);event.acceptProposedAction();return
            if kind in ('LOOSE','CHARACTERS'):
                control.move_to_character(dragged_id,None);event.acceptProposedAction();return
            if kind=='GROUP' and adjacent:
                target=lib.groups[ident].parent_id
                siblings=lib.ordered_children(target,lib.groups[ident].character_id);index=next(i for i,g in enumerate(siblings) if g.id==ident)+(position==QAbstractItemView.DropIndicatorPosition.BelowItem)
            elif kind in ('PROJECT','GROUP'):target=ident if kind=='GROUP' else None
            else:event.ignore();return
        else:
            if kind=='PROJECT':event.ignore();return
            target=ident if kind=='GROUP' else lib.resources[ident].group_id
            if kind=='RESOURCE' and adjacent:
                rows=lib.in_group(target);index=next(i for i,r in enumerate(rows) if r.id==ident)+(position==QAbstractItemView.DropIndicatorPosition.BelowItem)
        index=reorder_index(lib,dragged_kind,dragged_id,target,index)
        control.move(dragged_kind,dragged_id,target,index);event.acceptProposedAction()


class ProjectLibraryPanel(QWidget):
    def __init__(self,host,controller):
        super().__init__();self.host=host;self.controller=controller;self.items={};self.rebuilding=False
        self.setMinimumWidth(245);self.setMaximumWidth(440)
        layout=QVBoxLayout(self);layout.setContentsMargins(4,4,8,4)
        bar=QHBoxLayout();bar.addWidget(QLabel(t('PROJECT LIBRARY')))
        self.add_button=QPushButton(t('＋ Add'));self.add_button.setObjectName('primary');self.add_button.setAutoDefault(False)
        self.menu=QMenu(self.add_button);self.actions={}
        callbacks=[('New Project',host.new_project),('Open Project',host.open_project),
            ('New Character',lambda:controller.new_character()),
            ('New Group',lambda:controller.new_group()),('New Subgroup',lambda:controller.new_subgroup()),
            ('Import Video',host.choose_video),('Import Frame Sequence',host.choose_sequence),('Import Sprite Sheet',controller.choose_sheet),
            ('Export Group',lambda:controller.export_groups()),('Batch Export',lambda:controller.export_groups(True))]
        for label,callback in callbacks:
            action=self.menu.addAction(t(label));action.triggered.connect(lambda checked=False,fn=callback:fn());self.actions[label]=action
        self.menu.aboutToShow.connect(self.update_actions);self.add_button.setMenu(self.menu);bar.addWidget(self.add_button)
        layout.addLayout(bar)
        self.search=QLineEdit();self.search.setPlaceholderText(t('Search Groups and resources'));self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.filter);layout.addWidget(self.search)
        self.tree=LibraryTree(self);layout.addWidget(self.tree,1)
        self.info=QLabel(t('Create a Group, then add media.'));self.info.setWordWrap(True);self.info.setObjectName('muted');layout.addWidget(self.info)

    def update_actions(self):
        h=self.host;idle=not h.interaction_busy;selected=self.controller.can_import
        for label,action in self.actions.items():
            enabled=idle
            if label in ('New Character','New Group'):enabled &= self.controller.available
            elif label in ('Import Video','Import Frame Sequence','Import Sprite Sheet','Export Group'):enabled &= selected
            elif label=='New Subgroup':enabled &= bool(h.project.current_group_id)
            elif label=='Batch Export':enabled &= bool(h.project.library.groups)
            action.setEnabled(enabled)

    def refresh(self):
        h=self.host;p=h.project;lib=p.library
        expanded={key for key,item in self.items.items() if item.isExpanded()}
        self.rebuilding=True;self.tree.blockSignals(True);self.tree.clear();self.items={}
        root=QTreeWidgetItem([p.project_name or t('Project'),str(sum(1 for r in lib.resources.values() if r.kind=='ANIMATION'))])
        root.setData(0,ROLE,('PROJECT',None));root.setToolTip(0,t('Project Root cannot contain media.'))
        self.tree.addTopLevelItem(root);self.items[('PROJECT',None)]=root;root.setExpanded(True)
        def add_group_node(parent_item,group):
            item=QTreeWidgetItem([group.name+'  · '+t(group.status),str(lib.animation_count(group.id))])
            item.setData(0,ROLE,('GROUP',group.id))
            tooltip=' / '.join(v.name for v in lib.path(group.id))+'\n'+t(group.status)
            if group.alignment_review_required:tooltip+='\n'+t('Alignment Review Required')
            item.setToolTip(0,tooltip)
            item.setForeground(0,QColor('#e0a3ff' if group.alignment_review_required else
                '#efcc75' if group.status=='WARNING' else '#65dbbb' if group.status=='READY' else '#ecf2fc'))
            parent_item.addChild(item);self.items[('GROUP',group.id)]=item
            for child in lib.children(group.id):add_group_node(item,child)
            for r in lib.in_group(group.id):
                if r.kind=='GENERATED_SPRITE_SHEET':continue
                row=QTreeWidgetItem([t(r.kind)+' · '+r.name,'']);row.setData(0,ROLE,('RESOURCE',r.id));row.setToolTip(0,r.name+'\n'+r.path)
                item.addChild(row);self.items[('RESOURCE',r.id)]=row
                if r.kind=='ANIMATION':
                    for sheet in lib.in_group(group.id,kinds={'GENERATED_SPRITE_SHEET'}):
                        if sheet.animation_id==r.animation_id:
                            child=QTreeWidgetItem([t('GENERATED_SPRITE_SHEET')+' · '+sheet.name,'']);child.setData(0,ROLE,('RESOURCE',sheet.id));row.addChild(child);self.items[('RESOURCE',sheet.id)]=child
                    row.setExpanded(True)
            item.setExpanded(('GROUP',group.id) in expanded or group.id==p.current_group_id or not expanded)
        characters=QTreeWidgetItem([t('Characters'),str(len(lib.characters))])
        characters.setData(0,ROLE,('CHARACTERS',None));characters.setToolTip(0,t('Characters'))
        root.addChild(characters);self.items[('CHARACTERS',None)]=characters;characters.setExpanded(True)
        for character in lib.characters.values():
            node=QTreeWidgetItem([character_label(character),str(lib.character_animation_count(character.id))])
            node.setData(0,ROLE,('CHARACTER',character.id))
            node.setToolTip(0,t('Character: {name}',name=character_label(character))+'\n'+character.template_id+' v%d'%character.template_version)
            node.setForeground(0,QColor('#8fd3ff'))
            node.setIcon(0,self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
            font=node.font(0);font.setBold(True);node.setFont(0,font)
            characters.addChild(node);self.items[('CHARACTER',character.id)]=node
            for group in lib.character_roots(character.id):add_group_node(node,group)
            node.setExpanded(('CHARACTER',character.id) in expanded or character.id==p.current_character_id or not expanded)
        loose=QTreeWidgetItem([t('Loose Groups'),str(len(lib.loose_roots()))])
        loose.setData(0,ROLE,('LOOSE',None));loose.setToolTip(0,t('Loose Groups'))
        root.addChild(loose);self.items[('LOOSE',None)]=loose;loose.setExpanded(True)
        for group in lib.loose_roots():add_group_node(loose,group)
        selection=None
        for candidate in (self.controller.selection,
                          ('RESOURCE',self.controller.asset_id) if self.controller.asset_id else None,
                          ('CHARACTER',p.current_character_id) if p.current_character_id else None,
                          ('GROUP',p.current_group_id) if p.current_group_id else None,
                          ('PROJECT',None)):
            if candidate and candidate in self.items:selection=candidate;break
        current=self.items.get(selection,root);self.tree.setCurrentItem(current)
        self.tree.blockSignals(False);self.rebuilding=False;self.filter();self.update_actions()
        group=lib.groups.get(p.current_group_id)
        character=lib.characters.get(p.current_character_id)
        if character is not None:
            self.info.setText(t('Current Character: {name}',name=character_label(character)))
        else:
            self.info.setText(t('Current Group: {name}',name=' / '.join(g.name for g in lib.path(group.id))) if group else t('Create a Group, then add media.'))
        self.tree.setEnabled(not h.interaction_busy or bool(getattr(h,'task_context',None)))

    def select(self,kind,ident):
        item=self.items.get((kind,ident))
        if item:
            self.tree.blockSignals(True);self.tree.setCurrentItem(item);self.tree.blockSignals(False)

    def filter(self,*args):
        query=self.search.text().casefold().strip()
        def visit(item):
            matches=query in item.text(0).casefold()
            for i in range(item.childCount()):matches=visit(item.child(i)) or matches
            item.setHidden(not matches)
            if query and matches:item.setExpanded(True)
            return matches
        for i in range(self.tree.topLevelItemCount()):visit(self.tree.topLevelItem(i))

    def activate(self,item):
        if self.rebuilding or not item:return
        self.controller.activate(*item.data(0,ROLE))

    def context_menu(self,point):
        item=self.tree.itemAt(point)
        if not item:return
        kind,ident=item.data(0,ROLE);h=self.host;c=self.controller
        if h.interaction_busy:return
        menu=QMenu(self)
        def action(label,fn):menu.addAction(t(label)).triggered.connect(lambda checked=False:fn())
        if kind=='PROJECT':
            action('New Character',lambda:c.new_character())
            action('New Group',lambda:c.new_group())
        elif kind=='CHARACTERS':action('New Character',lambda:c.new_character())
        elif kind=='LOOSE':action('New Group',lambda:c.new_group(None,character_id=None))
        elif kind=='CHARACTER':
            action('New Group',lambda:c.new_group(None,character_id=ident))
            action('New Subgroup',lambda:c.new_subgroup(ident))
            action('Set Character Reference',lambda:(c.select_character(ident),c.open_character_reference()))
            action('Edit Character Reference',lambda:(c.select_character(ident),c.open_character_reference()))
            action('Rename Character',lambda:c.rename('CHARACTER',ident))
            action('Delete Character',lambda:c.remove_character(ident))
        elif kind=='GROUP':
            action('New Subgroup',lambda:c.new_group(ident))
            action('Rename',lambda:c.rename(kind,ident))
            action('Remove Group',lambda:c.remove_group(ident))
            action('Export Group',lambda:(c.select_group(ident),c.export_groups()))
        else:action('Rename',lambda:c.rename(kind,ident))
        if kind=='GROUP':
            movechar=menu.addMenu(t('Move to Character'))
            movechar.addAction(t('Loose Groups')).triggered.connect(lambda checked=False:c.move_to_character(ident,None))
            for character in h.project.library.characters.values():
                if character.id==h.project.library.groups[ident].character_id:continue
                movechar.addAction(character_label(character)).triggered.connect(lambda checked=False,target=character.id:c.move_to_character(ident,target))
        if kind!='PROJECT':
            move=menu.addMenu(t('Move to Group'))
            if kind=='GROUP':move.addAction(t('Project Root')).triggered.connect(lambda:c.move(kind,ident,None))
            lib=h.project.library
            for g in lib.groups.values():
                if kind=='GROUP' and g.id in lib.descendants(ident):continue
                move.addAction(' / '.join(v.name for v in lib.path(g.id))).triggered.connect(lambda checked=False,target=g.id:c.move(kind,ident,target))
        menu.exec(self.tree.viewport().mapToGlobal(point))
