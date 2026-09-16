"""Timeline-first editing UI. Commands change data; final pixels use one provider."""
import copy
from dataclasses import asdict
from bisect import bisect_right
import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
    QSplitter, QStackedWidget, QTabWidget, QScrollArea, QListWidget, QTreeWidget, QTreeWidgetItem,
    QComboBox, QDoubleSpinBox, QSpinBox, QCheckBox, QGroupBox, QGridLayout, QHeaderView)
from app.i18n import t, translate_error
from app.models.timeline_edit import FrameOverride, TimelineFrame
from app.core.final_frame_provider import FinalFrameProvider
from app.core.timeline_renderer import compile_timeline, composite_rgba, transform_layer
from app.ui.anchor_editor import AnchorEditor
from app.core.character_reference import ReferenceSource, reference_mapping
from app.ui.editor_canvas import EditorCanvas
from app.ui.editor_timeline import EditorTimeline
from app.ui.curve_editor import CurveEditor
from app.ui.worker import Worker
from app.utils.paths import frame_path


class FrameEditor(QWidget):
    def __init__(self, host, alignment_panels, motion_editor):
        super().__init__()
        self.host = host
        self.provider = None
        self.worker = None
        self.pending = False
        self.revision = 0
        self.clipboard = []
        self.index = 0
        self.last_pixels = None
        self.selected_ids = []
        self.project_key = None
        self.reference_source = None
        self._has_reference = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.advance)
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.timeout.connect(self._start_preview)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        self.notice = QLabel(t('Prepare the current frames to start editing.'))
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        top = QHBoxLayout()
        top.addWidget(self.button('Prepare Editor', host.prepare_editor, True))
        top.addWidget(self.button('Build Sprite Sheet', host.build_sprites))
        top.addWidget(self.button('Undo', host.undo_edit))
        top.addWidget(self.button('Redo', host.redo_edit))
        self.mode_note = QLabel()
        top.addWidget(self.mode_note, 1)
        layout.addLayout(top)
        split = QSplitter(Qt.Orientation.Horizontal)
        resources = QWidget()
        resources.setMinimumWidth(140)
        resources.setMaximumWidth(225)
        res = QVBoxLayout(resources)
        res.setContentsMargins(4,4,4,4)
        res.addWidget(QLabel(t('Animations / Resources')))
        self.clip_selector=QComboBox()
        self.clip_selector.currentIndexChanged.connect(self._select_clip)
        res.addWidget(self.clip_selector)
        res.addWidget(QLabel(t('Tracks / Resources')))
        self.tracks = QTreeWidget()
        self.tracks.setColumnCount(3)
        self.tracks.setHeaderLabels([t('Track'),t('Show'),t('Lock')])
        self.tracks.setRootIsDecorated(False)
        self.tracks.setMaximumHeight(190)
        self.tracks.itemChanged.connect(self._track_changed)
        self.tracks.header().setStretchLastSection(False)
        self.tracks.header().setMinimumSectionSize(28)
        self.tracks.header().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        for column in (1,2):self.tracks.header().setSectionResizeMode(column,QHeaderView.ResizeMode.ResizeToContents)
        res.addWidget(self.tracks)
        self.resources = QListWidget()
        self.resources.setSelectionMode(self.resources.SelectionMode.ExtendedSelection)
        self.resources.itemClicked.connect(lambda item:self.select_source(self.resources.row(item)))
        self.resources.itemDoubleClicked.connect(lambda _: self.insert_sources())
        res.addWidget(self.resources,1)
        res.addWidget(self.button('Insert Selected Sources', self.insert_sources))
        split.addWidget(resources)
        center = QWidget()
        mid = QVBoxLayout(center)
        mid.setContentsMargins(0,0,0,0)
        self.canvas_stack = QStackedWidget()
        self.canvas = EditorCanvas()
        self.alignment_view = AnchorEditor()
        self.canvas_stack.addWidget(self.canvas)
        self.canvas_stack.addWidget(self.alignment_view)
        self.canvas.moved.connect(self.move_content)
        self.alignment_view.root_selected.connect(host._set_root)
        self.alignment_view.roi_selected.connect(host._set_roi)
        mid.addWidget(self.canvas_stack,1)
        tools = QHBoxLayout()
        for label,callback in (('First Frame',lambda:self.select(0)),('Previous Frame',lambda:self.step(-1)),('Next Frame',lambda:self.step(1)),('Last Frame',lambda:self.select(len(self.provider)-1 if self.provider else 0))):
            tools.addWidget(self.button(label,callback))
        self.play_button = self.button('Play',self.toggle_play)
        tools.insertWidget(2,self.play_button)
        tools.addWidget(self.button('Stop',lambda:(self.stop(),self.select(0))))
        self.loop = QCheckBox(t('Loop'));self.loop.setChecked(True);tools.addWidget(self.loop)
        mid.addLayout(tools)
        speed = QHBoxLayout()
        speed.addWidget(QLabel(t('Preview FPS')))
        self.preview_fps = QDoubleSpinBox();self.preview_fps.setRange(0,240);self.preview_fps.setSpecialValueText(t('Source'));self.preview_fps.valueChanged.connect(self._timer_interval)
        speed.addWidget(self.preview_fps)
        self.frame_label = QLabel();speed.addWidget(self.frame_label,1)
        speed.addWidget(self.button('Fit', self.canvas.fit_image))
        speed.addWidget(self.button('100%',self.canvas.actual_size))
        mid.addLayout(speed)
        self.timeline = EditorTimeline()
        self.timeline.selection_changed.connect(self._selection_changed)
        self.timeline.time_selected.connect(self.select_time)
        self.timeline.blocks_moved.connect(self.move_blocks)
        self.timeline.action.connect(self.action)
        mid.addWidget(self.timeline)
        timeline_tools = QHBoxLayout()
        for name,key in (('Select All','select_all'),('Copy','copy'),('Paste at Playhead','paste'),('Delete Frames','delete'),('Reverse','reverse')):
            timeline_tools.addWidget(self.button(name,lambda checked=False,k=key:self.action(k)))
        timeline_tools.addWidget(self.button('−',lambda:self.timeline.zoom(1/1.2)))
        timeline_tools.addWidget(self.button('+',lambda:self.timeline.zoom(1.2)))
        mid.addLayout(timeline_tools)
        split.addWidget(center)
        self.inspector = QTabWidget()
        self.inspector.setMinimumWidth(290)
        self.inspector.setMaximumWidth(360)
        self.inspector.currentChanged.connect(self._mode_changed)
        self.properties = QWidget()
        self.property_layout = QVBoxLayout(self.properties)
        self.property_layout.setContentsMargins(9,9,9,9)
        form = QFormLayout();form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        self.property_layout.addLayout(form)
        self.reference_status=QLabel();self.reference_status.setWordWrap(True);form.addRow(self.reference_status)
        self.reference_button=self.button('Set Character Reference',host.open_character_reference,True);form.addRow(self.reference_button)
        self.drag_scope=QComboBox()
        self.drag_scope.addItem(t('Animation Offset'),'animation');self.drag_scope.addItem(t('Existing Per-Frame Edit'),'frame');self.drag_scope.setCurrentIndex(1)
        self.drag_scope.currentIndexChanged.connect(self._drag_scope_changed);form.addRow(t('Drag Target'),self.drag_scope)
        self.reference_group=QGroupBox(t('Character Reference / Animation Offset'))
        self.reference_group.setCheckable(True);self.reference_group.setChecked(False)
        reference_layout=QVBoxLayout(self.reference_group);reference_body=QWidget();reference_form=QFormLayout(reference_body)
        reference_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        reference_layout.addWidget(reference_body);reference_body.hide();self.reference_group.toggled.connect(reference_body.setVisible)
        self.show_reference=QCheckBox(t('Show Character Reference'));self.show_reference.setChecked(True)
        self.show_reference_ground=QCheckBox(t('Show Ground'));self.show_reference_ground.setChecked(True)
        self.show_reference_axes=QCheckBox(t('Show XY Axis'));self.show_reference_axes.setChecked(True)
        self.show_idle_ghost=QCheckBox(t('Show Idle Ghost'));self.show_idle_ghost.setChecked(True)
        for control in (self.show_reference,self.show_reference_ground,self.show_reference_axes,self.show_idle_ghost):
            reference_form.addRow(control);control.toggled.connect(self.request_preview)
        self.reference_opacity=self.decimal(0,1,.35);reference_form.addRow(t('Reference Opacity'),self.reference_opacity);self.reference_opacity.valueChanged.connect(self.request_preview)
        self.animation_x=self.decimal(-32768,32768);self.animation_y=self.decimal(-32768,32768)
        for control in (self.animation_x,self.animation_y):control.setDecimals(0)
        reference_form.addRow(t('Animation Offset X (project px)'),self.animation_x);reference_form.addRow(t('Animation Offset Y (project px)'),self.animation_y)
        reference_form.addRow(self.button('Apply Animation Offset',lambda:host.set_animation_offset(self.animation_x.value(),self.animation_y.value())))
        reference_form.addRow(self.button('Reset Animation Offset',lambda:host.set_animation_offset(0,0)))
        form.addRow(self.reference_group)
        self.selection_label = QLabel();form.addRow(self.selection_label)
        self.track_target = QComboBox()
        for track in host.project.timeline_edit.track_layout: self.track_target.addItem(t(track.name),track.id)
        form.addRow(t('Destination Track'),self.track_target)
        main_form=form
        self.transform_group=QGroupBox(t('Frame Transform / Actions'))
        self.transform_group.setCheckable(True);self.transform_group.setChecked(False)
        transform_layout=QVBoxLayout(self.transform_group)
        transform_body=QWidget();form=QFormLayout(transform_body);form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        transform_layout.addWidget(transform_body);transform_body.hide();self.transform_group.toggled.connect(transform_body.setVisible)
        main_form.addRow(self.transform_group)
        self.ripple = QCheckBox(t('Ripple / Insert'));self.ripple.setChecked(True);form.addRow(self.ripple)
        self.x = self.decimal(-32768,32768);self.y = self.decimal(-32768,32768)
        form.addRow(t('Offset X (cell px)'),self.x);form.addRow(t('Offset Y (cell px)'),self.y)
        self.scale_value = self.decimal(.01,8,1);self.opacity = self.decimal(0,1,1)
        form.addRow(t('Frame Scale'),self.scale_value);form.addRow(t('Opacity'),self.opacity)
        form.addRow(self.button('Apply Transform to Selection',self.apply_transform))
        form.addRow(self.button('Add XY to Selection',lambda:self.command('Offset Frames',lambda e:e.offset(self.selection(),self.x.value(),self.y.value()))))
        form.addRow(self.button('Paste at End',lambda:self.paste(True)))
        form.addRow(self.button('Mark / Unmark Keyframes',self.mark_keys))
        form=main_form
        self.target_count = QSpinBox();self.target_count.setRange(1,100000);self.target_count.setValue(20)
        form.addRow(t('Target Frame Count'),self.target_count)
        self.speed = self.decimal(.01,100,2);form.addRow(t('Speed Multiplier'),self.speed)
        self.duration = self.decimal(.001,86400,.8);form.addRow(t('Target Duration (s)'),self.duration)
        self.curve = QComboBox()
        for value,label in (('linear','Linear'),('ease_in','Ease In'),('ease_out','Ease Out'),('ease_in_out','Ease In Out'),('bezier','Custom Bezier')):
            self.curve.addItem(t(label),value)
        form.addRow(t('Timing Curve'),self.curve)
        self.curve_editor = CurveEditor()
        self.curve.currentIndexChanged.connect(self._curve_changed)
        form.addRow(self.curve_editor)
        self.bezier_fields=[]
        self.bezier_widget=QWidget();controls=QGridLayout(self.bezier_widget);controls.setContentsMargins(0,0,0,0)
        for i,v in enumerate(self.curve_editor.controls):
            spin=self.decimal(0,1,v);spin.setDecimals(2);spin.setSingleStep(.05)
            spin.valueChanged.connect(self._bezier_changed);controls.addWidget(QLabel(('X1','Y1','X2','Y2')[i]),i//2,(i%2)*2);controls.addWidget(spin,i//2,(i%2)*2+1);self.bezier_fields.append(spin)
        form.addRow(self.bezier_widget)
        self.curve_editor.changed.connect(self._bezier_from_plot)
        self.keep_first=QCheckBox(t('Keep First Frame'));self.keep_first.setChecked(True)
        self.keep_last=QCheckBox(t('Keep Last Frame'));self.keep_last.setChecked(True)
        self.keep_keys=QCheckBox(t('Keep Marked Keyframes'));self.keep_keys.setChecked(True)
        for box in (self.keep_first,self.keep_last,self.keep_keys):form.addRow(box)
        self.apply_count_button=self.button('Apply Frame Count',lambda:self.retime('count'),True)
        form.addRow(self.apply_count_button)
        form.addRow(self.button('Apply Speed',lambda:self.retime('speed')))
        form.addRow(self.button('Apply Duration / Curve',lambda:self.retime('duration')))
        form.addRow(self.button('Interpolate Selected Transforms',lambda:self.command('Interpolate Transforms',lambda e:e.interpolate(self.selection(),self.curve.currentData(),self.curve_editor.controls))))
        preview_group=QGroupBox(t('Preview Overlays'))
        preview_group.setCheckable(True);preview_group.setChecked(False)
        preview_layout=QVBoxLayout(preview_group)
        preview_body=QWidget();form=QFormLayout(preview_body);form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        preview_layout.addWidget(preview_body);preview_body.hide();preview_group.toggled.connect(preview_body.setVisible)
        main_form.addRow(preview_group)
        self.onion=QCheckBox(t('Onion Skin'));self.ghost=QCheckBox(t('Motion Ghost'))
        self.neighbors=QSpinBox();self.neighbors.setRange(1,5);self.neighbors.setValue(1)
        self.ghost_opacity=self.decimal(.02,.8,.22)
        for control in (self.onion,self.ghost):control.toggled.connect(self.request_preview);form.addRow(control)
        self.neighbors.valueChanged.connect(self.request_preview);self.ghost_opacity.valueChanged.connect(self.request_preview)
        form.addRow(t('Neighbor Frames'),self.neighbors);form.addRow(t('Ghost Opacity'),self.ghost_opacity)
        for key,label in (('axes','X / Y Axes'),('ground','Ground Line'),('root','Root Point'),('bounds','Alpha Bounds'),('canvas','Cell Bounds'),('safe','Safe Area')):
            check=QCheckBox(t(label));check.setChecked(True)
            check.toggled.connect(lambda checked,k=key:self._overlay(k,checked));form.addRow(check)
        hint=QLabel(t('Drag: move frame · Arrows: 1px · Shift: 10px · Middle drag: pan'));hint.setWordWrap(True);form.addRow(hint)
        self.property_layout.addStretch()
        self.inspector.addTab(self.scroll(self.properties),t('Timeline'))
        alignment = QWidget();align_layout=QVBoxLayout(alignment);align_layout.setContentsMargins(5,5,5,5)
        for label,panel in zip(('Root / Character Space','Motion / Ground','Alignment Options'),alignment_panels):
            group=QGroupBox(t(label));group.setCheckable(True);group.setChecked(label=='Root / Character Space')
            group_layout=QVBoxLayout(group);group_layout.setContentsMargins(1,1,1,1);group_layout.addWidget(panel)
            group.toggled.connect(panel.setVisible);panel.setVisible(group.isChecked());align_layout.addWidget(group)
        curves=QGroupBox(t('Root Trajectories'));curves.setCheckable(True);curves.setChecked(False)
        curves_layout=QVBoxLayout(curves);curves_layout.addWidget(motion_editor);motion_editor.hide();curves.toggled.connect(motion_editor.setVisible);align_layout.addWidget(curves)
        debug=QGroupBox(t('OVERLAYS'));debug.setCheckable(True);debug.setChecked(False)
        debug_layout=QVBoxLayout(debug);debug_body=QWidget();debug_controls=QVBoxLayout(debug_body)
        debug_layout.addWidget(debug_body);debug_body.hide();debug.toggled.connect(debug_body.setVisible)
        for key,original in host.overlay_checks.items():
            if key=='grid':continue
            check=QCheckBox(original.text());check.setChecked(original.isChecked())
            check.toggled.connect(original.setChecked);original.toggled.connect(check.setChecked);debug_controls.addWidget(check)
        align_layout.addWidget(debug)
        align_layout.addStretch();self.inspector.addTab(self.scroll(alignment),t('Alignment'))
        split.addWidget(self.inspector);split.setSizes([170,830,320]);split.setStretchFactor(1,1)
        layout.addWidget(split,1)
        for key,action in (('Space','play'),('Home','first'),('End','last'),('Ctrl+C','copy'),('Ctrl+V','paste'),('Ctrl+A','select_all'),('Delete','delete')):
            shortcut=QShortcut(QKeySequence(key),self.timeline);shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(lambda a=action:self.action(a))
        self._curve_changed()

    def button(self,label,callback,primary=False):
        b=QPushButton(t(label));b.clicked.connect(callback);b.setAutoDefault(False)
        if primary:b.setObjectName('primary')
        return b

    def decimal(self,lo,hi,value=0):
        s=QDoubleSpinBox();s.setRange(lo,hi);s.setDecimals(3);s.setValue(value);return s

    def scroll(self,widget):
        area=QScrollArea();area.setWidgetResizable(True);area.setWidget(widget);return area

    def _mode_changed(self,index):
        self.stop()
        self.canvas_stack.setCurrentIndex(index)
        if index==1:
            self.host.select_frame(max(0,self.provider.source_index(self.index)) if self.provider and len(self.provider) else self.host.current_frame)
        else:self.request_preview()

    def alignment(self):
        self.inspector.setCurrentIndex(1)

    def fit_image(self):
        self.canvas_stack.currentWidget().fit_image()

    def actual_size(self):
        self.canvas_stack.currentWidget().actual_size()

    def bind(self, prepare=False):
        p=self.host.project
        key=(p.project_id,p.animation_id)
        if key!=self.project_key:
            self.pause_preview();self.selected_ids=[];self.index=0;self.clipboard=[];self.project_key=key
            self.loop.setChecked(p.export_settings.loop)
        if p.has_final_edits and p.layout:
            try:self.provider=FinalFrameProvider(p,self.host.cache_dir,live_edit=True)
            except (ValueError,OSError):self.provider=None
        else:self.provider=None
        self.reference_load_error=None
        if p.character_reference:
            try:
                source=ReferenceSource(p,p.character_reference,self.host.cache_dir,self.host.project_file)
                if self.reference_source is None or self.reference_source.identity!=source.identity:
                    # Group switching may read a reference cache but must never regenerate it.
                    path=frame_path(source.pipe.keyed,p.character_reference.reference_frame_index)
                    if not path.is_file():raise ValueError('Reference cache missing; process its Animation explicitly.')
                    source.pixels=source.cache.read(path)
                    self.reference_source=source
            except (KeyError,ValueError,OSError) as error:
                self.reference_source=None;self.reference_load_error=str(error)
        else:self.reference_source=None
        self.refresh()
        self.request_preview()

    def refresh(self):
        p=self.host.project;e=p.timeline_edit
        reference=p.character_reference
        self.reference_status.setText(t('Character Coordinate System: Locked') if reference else t('Character reference: not established'))
        self.reference_button.setText(t('Edit Character Reference') if reference else t('Set Character Reference'))
        self.reference_button.setEnabled(self.host.keyed_ready)
        if reference:
            self.reference_status.setText(self.reference_status.text()+"\n"+t('Origin ({x:.0f}, {y:.0f})',x=reference.origin_x,y=reference.ground_y))
        if reference and not self._has_reference:self.drag_scope.setCurrentIndex(0);self.reference_group.setChecked(True)
        self._has_reference=bool(reference)
        self._drag_scope_changed()
        for field,value in ((self.animation_x,p.animation_transform.offset_x),(self.animation_y,p.animation_transform.offset_y)):
            field.blockSignals(True);field.setValue(value);field.blockSignals(False)
        for control in (self.show_reference,self.show_reference_ground,self.show_reference_axes,self.show_idle_ghost,self.reference_opacity):control.setEnabled(bool(reference))
        self.timeline.set_edit(e,p.video.fps,self.selected_ids)
        self.clip_selector.blockSignals(True);self.clip_selector.clear()
        for row in p.library.in_group(p.current_group_id,kinds={'ANIMATION'}):
            self.clip_selector.addItem(row.name,row.animation_id)
        self.clip_selector.setCurrentIndex(self.clip_selector.findData(p.animation_id))
        self.clip_selector.blockSignals(False)
        self.tracks.blockSignals(True);self.tracks.clear()
        for track in e.track_layout:
            item=QTreeWidgetItem([t(track.name),'','']);item.setData(0,Qt.ItemDataRole.UserRole,track.id)
            item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(1,Qt.CheckState.Checked if track.visible else Qt.CheckState.Unchecked)
            item.setCheckState(2,Qt.CheckState.Checked if track.locked else Qt.CheckState.Unchecked)
            self.tracks.addTopLevelItem(item)
        self.tracks.blockSignals(False)
        if self.resources.count()!=p.video.frame_count:
            self.resources.clear()
            for i in range(p.video.frame_count):self.resources.addItem(t('Source Frame {frame}',frame=i))
        count=len(self.provider) if self.provider else 0
        self.index=max(0,min(self.index,count-1)) if self.provider else self.host.current_frame
        self.mode_note.setText(t('Source {source} → Output {output} frames',source=p.video.frame_count,output=count))
        self.notice.setText(t('Edits are non-destructive. Reference track and preview overlays are excluded from exports.') if self.provider else t('Prepare the current frames to start editing.'))
        self._selection_changed(self.timeline.ids())
        if not count:self.canvas.clear_image()

    def _select_clip(self):
        ident=self.clip_selector.currentData()
        if ident and ident!=self.host.project.animation_id:
            self.host.animation_selector.setCurrentIndex(self.host.animation_selector.findData(ident))

    def selection(self):
        ids=self.timeline.ids()
        if not ids and self.provider and len(self.provider):
            ids=self.provider.project.final_timing[self.index]['layers'][:1]
        return ids

    def _selection_changed(self,ids):
        self.selected_ids=list(ids)
        self.selection_label.setText(t('Selected: {count} frames',count=len(ids)))
        if ids:
            value=self.host.project.timeline_edit.frame_overrides.get(ids[0],FrameOverride())
            for control,v in ((self.x,value.offset_x),(self.y,value.offset_y),(self.scale_value,value.scale),(self.opacity,value.opacity)):
                control.blockSignals(True);control.setValue(v);control.blockSignals(False)

    def _drag_scope_changed(self):
        layout=self.host.project.layout
        self.canvas.key_step_scale=layout.normalize_scale if layout and self.drag_scope.currentData()=='animation' else (1.,1.)

    def move_content(self,x,y):
        if self.drag_scope.currentData()=='animation':
            if not self.host.project.layout:return
            sx,sy=self.host.project.layout.normalize_scale
            self.host.set_animation_offset(round(x/sx),round(y/sy),relative=True)
        else:self.command('Offset Frames',lambda e:e.offset(self.selection(),x,y))

    def command(self,label,fn):
        if self.host.interaction_busy:return
        self.stop()
        self.host.apply_editor_command(fn,label)

    def apply_transform(self):
        ids=self.selection();value=FrameOverride(self.x.value(),self.y.value(),self.scale_value.value(),self.opacity.value())
        def apply(e):
            for frame in e.selected(ids):e.frame_overrides[frame.id]=copy.deepcopy(value)
        self.command('Transform Frames',apply)

    def action(self,name):
        if self.host.interaction_busy:return
        e=self.host.project.timeline_edit
        if name=='select_all':self.timeline.select_ids([f.id for f in e.frames() if not next(t for t in e.track_layout if t.id==f.track_id).locked])
        elif name=='copy':self.clipboard=e.copy(self.selection())
        elif name=='paste':self.paste()
        elif name=='delete':self.command('Delete Frames',lambda e:e.delete(self.selection(),self.ripple.isChecked()))
        elif name=='reverse':self.command('Reverse Frames',lambda e:e.reverse(self.selection()))
        elif name=='play':self.toggle_play()
        elif name=='first':self.select(0)
        elif name=='last':self.select(len(self.provider)-1 if self.provider else 0)

    def paste(self,end=False):
        if not self.clipboard:return
        e=self.host.project.timeline_edit
        at=e.duration if end else self.timeline.play_time
        self.command('Paste Frames',lambda e:e.paste(self.clipboard,at,self.track_target.currentData(),self.ripple.isChecked()))

    def insert_sources(self):
        items=self.resources.selectedIndexes()
        if not items:return
        fps=self.host.project.video.fps or 24
        clipboard=[dict(frame=asdict(TimelineFrame(i.row(),n/fps,1/fps)),override=asdict(FrameOverride())) for n,i in enumerate(items)]
        self.command('Insert Sources',lambda e:e.paste(clipboard,self.timeline.play_time,self.track_target.currentData(),self.ripple.isChecked()))

    def move_blocks(self,ids,at,track):
        if self.ripple.isChecked():
            chosen=self.host.project.timeline_edit.selected(ids,False)
            at=max(0.,at-sum(f.duration for f in chosen if f.track_id==track and f.end<=at+1e-8))
        self.command('Move Frames',lambda e:e.move(ids,at,track,self.ripple.isChecked()))

    def mark_keys(self):
        ids=self.selection();selected=self.host.project.timeline_edit.selected(ids,False)
        self.command('Mark Keyframes',lambda e:e.mark_keyframes(ids,not all(f.keyframe for f in selected)))

    def _track_changed(self,item,column):
        if column not in (1,2):return
        ident=item.data(0,Qt.ItemDataRole.UserRole);field='visible' if column==1 else 'locked'
        value=item.checkState(column)==Qt.CheckState.Checked
        self.command('Track Settings',lambda e:setattr(next(t for t in e.track_layout if t.id==ident),field,value))

    def retime(self,mode):
        ids=self.selection();curve=self.curve.currentData();bezier=self.curve_editor.controls
        if mode=='count':
            self.command('Retime Frames',lambda e:e.retime_count(ids,self.target_count.value(),self.host.project.video.fps or 24,curve,bezier,self.keep_first.isChecked(),self.keep_last.isChecked(),self.keep_keys.isChecked()))
        else:
            def apply(e):
                selected=e._range(ids)
                duration=sum(f.duration for f in selected)/self.speed.value() if mode=='speed' else self.duration.value()
                e.retime_duration(ids,duration,curve,bezier)
            self.command('Retime Duration',apply)

    def _curve_changed(self):
        self.curve_editor.curve=self.curve.currentData();self.curve_editor.update()
        self.bezier_widget.setVisible(self.curve.currentData()=='bezier')
        for field in self.bezier_fields:field.setEnabled(self.curve.currentData()=='bezier')

    def _bezier_changed(self):
        values=[s.value() for s in self.bezier_fields]
        values[0]=min(values[0],values[2]);values[1]=min(values[1],values[3])
        self._bezier_from_plot(values)
        self.curve_editor.controls=tuple(values);self.curve_editor.update()

    def _bezier_from_plot(self,values):
        for field,value in zip(self.bezier_fields,values):field.blockSignals(True);field.setValue(value);field.blockSignals(False)

    def _overlay(self,key,checked):
        self.canvas.overlays[key]=checked;self.canvas.viewport().update()

    def select_source(self,index):
        if self.inspector.currentIndex()!=1:return
        self.stop()
        self.host.select_frame(index)
        if not self.provider:self.index=index
        self.frame_label.setText(t('Source Frame {frame}',frame=index))

    def select_time(self,time):
        if not self.provider or not len(self.provider):
            self.select_source(round(time*(self.host.project.video.fps or 24)));return
        starts=[f['start'] for f in self.provider.project.final_timing]
        self.select(max(0,bisect_right(starts,time+1e-9)-1))

    def select(self,index):
        if not self.provider or not len(self.provider):
            self.select_source(max(0,min(index,self.host.project.video.frame_count-1)));return
        self.index=max(0,min(index,len(self.provider)-1))
        timing=self.provider.project.final_timing[self.index]
        self.timeline.set_time(timing['start'])
        self.frame_label.setText(t('Frame {frame:02d} / {count}',frame=self.index+1,count=len(self.provider)))
        if self.inspector.currentIndex()==1:self.host.select_frame(max(0,self.provider.source_index(self.index)))
        self._timer_interval();self.request_preview()

    def _timer_interval(self):
        if self.provider and len(self.provider):
            duration=1/self.preview_fps.value() if self.preview_fps.value() else self.provider.duration(self.index)
            self.timer.setInterval(max(1,round(duration*1000)))

    def toggle_play(self):
        if self.timer.isActive():self.stop()
        elif self.provider and len(self.provider):self._timer_interval();self.timer.start();self.play_button.setText(t('Pause'))

    def stop(self):
        self.timer.stop();self.play_button.setText(t('Play'))

    def step(self,delta):
        self.stop();self.select((self.index if self.provider else self.host.current_frame)+delta)

    def advance(self):
        if self.worker or self.pending:return
        if self.index+1>=len(self.provider):
            if self.loop.isChecked():self.select(0)
            else:self.stop()
        else:self.select(self.index+1)

    def request_preview(self,*args):
        self.revision+=1;self.pending=True
        self.debounce.start(0 if self.timer.isActive() else 25)

    def _start_preview(self):
        if self.worker or self.host.current_animation_busy or not self.provider or not len(self.provider):return
        self.pending=False
        provider=self.provider;index=self.index;revision=self.revision
        onion=self.onion.isChecked();ghost=self.ghost.isChecked();count=self.neighbors.value();opacity=self.ghost_opacity.value()
        show_idle=self.show_reference.isChecked() and self.show_idle_ghost.isChecked()
        reference_source=self.reference_source if show_idle else None
        load_error=self.reference_load_error if show_idle else None
        def operation(progress,cancel):
            pixels=provider.get_final_frame(index)
            layers=[]
            if ghost:layers.extend((i,opacity*.65) for i in range(max(0,index-5),index))
            if onion:layers.extend((i,opacity) for i in range(max(0,index-count),min(len(provider),index+count+1)) if i!=index)
            images=[]
            for i,alpha in layers:
                frame=provider.get_final_frame(i).copy();frame[...,3]=np.round(frame[...,3].astype(np.float32)*alpha).astype(np.uint8);images.append(frame)
            images.append(pixels)
            output=composite_rgba(images,pixels.shape)
            # Reference track is visible only in this editor, never in provider output.
            time=provider.project.final_timing[index]['start']
            e=provider.project.timeline_edit
            if any(t.id=='reference' and t.visible for t in e.track_layout):
                refs=[f for f in e.frames('reference') if f.start<=time+1e-8<f.end]
                if refs:
                    f=refs[-1];value=copy.deepcopy(e.frame_overrides.get(f.id,FrameOverride()));value.opacity*=.3
                    ref=transform_layer(provider.cache.read(frame_path(provider.cache_dir/'aligned_frames',f.source_index)),value)
                    output=composite_rgba([output,ref],pixels.shape)
            idle=None;reference_error=load_error
            if reference_source:
                try:idle=reference_source.output(provider.project.layout,provider.project.sprite_cell.preserve_aspect_ratio,cancel)
                except (OSError,ValueError,KeyError) as error:reference_error=str(error)
            return output,copy.deepcopy(provider.frame_data(index)),revision,idle,reference_error
        self.worker=Worker(operation,self);self.worker.result.connect(self._result);self.worker.failed.connect(self._error);self.worker.finished.connect(self._finished);self.worker.start()

    def _result(self,result):
        pixels,frame,revision,idle,reference_error=result
        if revision!=self.revision:return
        self.last_pixels=pixels
        self.canvas.set_image(pixels)
        self.canvas.set_idle_ghost(idle,self.reference_opacity.value())
        frame.root,frame.bbox=frame.cell_root,frame.cell_bbox
        self.canvas.frame=frame
        p=self.provider.project
        self.canvas.root_visible=not p.is_passthrough
        self.canvas.character_profile=p.character_profile if not p.is_passthrough else None
        self.canvas.origin=p.character_profile.ground_origin if p.character_profile else None
        self.canvas.character_reference=p.character_reference
        self.canvas.reference_mapping=reference_mapping(p.character_reference,p.layout,p.sprite_cell.preserve_aspect_ratio) if p.character_reference else (1.,1.,0.,0.)
        self.canvas.overlays.update(reference=self.show_reference.isChecked(),reference_ground=self.show_reference_ground.isChecked(),reference_axes=self.show_reference_axes.isChecked())
        self.canvas.ground=None if p.character_reference else p.layout.ground_baseline if not p.is_passthrough else p.layout.height*.9
        self.canvas.viewport().update()
        self.frame_label.setText(t('Frame {frame:02d} / {count}',frame=self.index+1,count=len(self.provider)))
        if frame.warnings:self.notice.setText(' · '.join(t(w) for w in frame.warnings))
        elif reference_error:self.notice.setText(t('Idle reference unavailable: {error}',error=reference_error))
        else:self.notice.setText(t('Edits are non-destructive. Reference track and preview overlays are excluded from exports.'))

    def _finished(self):
        worker=self.worker;self.worker=None;worker.deleteLater()
        if self.pending:self.debounce.start(0)

    def _error(self,message):
        self.stop();self.notice.setText(translate_error(message))

    def pause_preview(self):
        self.stop();self.revision+=1;self.pending=False;self.debounce.stop()
        if self.worker:self.worker.cancel();self.worker.wait()
