"""Export review uses the same immutable plan as execution."""
import copy
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QLineEdit,
    QTreeWidget,QTreeWidgetItem,QCheckBox,QPlainTextEdit)
from app.i18n import t
from app.ui.dialogs import FileDialog
from app.core.group_export import exportable_resources,plan_group_export,export_group_plan


class GroupExportDialog(QDialog):
    def __init__(self,host,batch=False):
        super().__init__(host);self.host=host;self.project=copy.deepcopy(host.project);self.project_file=host.project_file
        self.setWindowTitle(t('Batch Export' if batch else 'Export Group'));self.resize(850,680)
        layout=QVBoxLayout(self)
        note=QLabel(t('Only existing Sprite Sheets are exported. Unbuilt sources are not processed.'));note.setWordWrap(True);layout.addWidget(note)
        self.search=QLineEdit();self.search.setPlaceholderText(t('Search Groups'));self.search.textChanged.connect(self.filter);layout.addWidget(self.search)
        self.tree=QTreeWidget();self.tree.setHeaderLabels([t('Group'),t('Status')]);self.tree.setColumnWidth(0,490);layout.addWidget(self.tree,1)
        self.rows={};self.ready={}
        for group in self.project.library.groups.values():
            eligible=bool(exportable_resources(self.project,self.project_file,group.id))
            item=QTreeWidgetItem([' / '.join(v.name for v in self.project.library.path(group.id)),t(group.status)])
            item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable)
            selected=eligible and (batch or group.id==self.project.current_group_id)
            item.setCheckState(0,Qt.CheckState.Checked if selected else Qt.CheckState.Unchecked)
            self.rows[group.id]=item;self.ready[group.id]=eligible;self.tree.addTopLevelItem(item)
        buttons=QHBoxLayout()
        for label,fn in [('Select all',lambda:self.select(False)),('Select ready',lambda:self.select(True)),('Clear selection',self.clear_selection)]:
            button=QPushButton(t(label));button.clicked.connect(fn);buttons.addWidget(button)
        layout.addLayout(buttons)
        self.preserve=QCheckBox(t('Preserve Group hierarchy'));self.preserve.setChecked(True);layout.addWidget(self.preserve)
        options=QHBoxLayout();self.formats=[]
        for label in ('Sprite Sheet','Animation JSON','Root Motion JSON'):
            check=QCheckBox(t(label));check.setChecked(True);self.formats.append(check);options.addWidget(check);check.toggled.connect(self.review)
        layout.addLayout(options)
        self.preview=QPlainTextEdit();self.preview.setReadOnly(True);self.preview.setMaximumHeight(165);layout.addWidget(self.preview)
        row=QHBoxLayout();self.cancel=QPushButton(t('Cancel'));self.cancel.clicked.connect(self.reject);row.addWidget(self.cancel)
        self.export=QPushButton(t('Choose destination and export'));self.export.setObjectName('primary');self.export.clicked.connect(self.execute);row.addWidget(self.export);layout.addLayout(row)
        for button in self.findChildren(QPushButton):button.setAutoDefault(False)
        self.tree.itemChanged.connect(self.review);self.preserve.toggled.connect(self.review);self.review()

    def selected(self):return [ident for ident,item in self.rows.items() if item.checkState(0)==Qt.CheckState.Checked]
    def select(self,ready):
        for ident,item in self.rows.items():item.setCheckState(0,Qt.CheckState.Checked if not ready or self.ready[ident] else Qt.CheckState.Unchecked)
    def clear_selection(self):
        for item in self.rows.values():item.setCheckState(0,Qt.CheckState.Unchecked)
    def filter(self,text):
        for item in self.rows.values():item.setHidden(text.casefold() not in item.text(0).casefold())
    def review(self,*args):
        selected=self.selected();self.export.setEnabled(bool(selected) and any(c.isChecked() for c in self.formats))
        if not selected:self.preview.setPlainText(t('Select one or more Groups.'));return
        try:
            plan=plan_group_export(self.project,self.project_file,selected,preserve_tree=self.preserve.isChecked())
            self.preview.setPlainText('\n'.join(str(p) for p in plan.directories)+'\n\n'+(t('Empty or source-only Groups: {groups}',groups=', '.join(plan.warnings)) if plan.warnings else ''))
        except (ValueError,OSError) as error:self.preview.setPlainText(str(error));self.export.setEnabled(False)
    def execute(self):
        try:plan=plan_group_export(self.project,self.project_file,self.selected(),preserve_tree=self.preserve.isChecked())
        except (ValueError,OSError) as error:self.preview.setPlainText(str(error));return
        destination=FileDialog.getExistingDirectory(self.host,'Choose Group export directory',purpose='group_export')
        if not destination:return
        options=dict(zip(('include_sheet','include_animation_json','include_root_motion'),[c.isChecked() for c in self.formats]))
        def success(result):
            self.host._remember_path('group_export',destination)
            self.host.status.setText(t('Group export complete: {path}',path=destination))
        self.accept()
        self.host._run(lambda progress,cancel:export_group_plan(plan,Path(destination),progress=progress,cancel=cancel,**options),success,'Exporting Groups')
