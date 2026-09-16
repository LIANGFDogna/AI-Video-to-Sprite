from __future__ import annotations

import copy
from dataclasses import asdict, replace
from datetime import datetime
import json
import logging
from pathlib import Path
import re

import cv2
import numpy as np
from PIL import Image
from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDialog, QFileDialog,
    QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
    QScrollArea, QSlider, QSpinBox, QSplitter, QStackedWidget, QTabBar, QVBoxLayout, QWidget, QSizePolicy)

from app.core.alpha_utils import alpha_bbox
from app.core.chroma_key import chroma_key
from app.core.pipeline import Pipeline
from app.core.video_decoder import SUPPORTED_EXTENSIONS
from app.core.motion import PRESETS
from app.core.final_frame_provider import FinalFrameProvider
from app.core.canvas_normalizer import premultiplied_resize
from app.core.character_space import prepare_character_calibration, review_reference_bounds
from app.ui.character_space_editor import CharacterSpaceEditor
from app.ui.sequence_import_dialog import SequenceImportDialog
from app.ui.sequence_info import format_summary, alpha_warning
from app.ui.canvas_fit_info import canvas_fit_summary
from app.ui.new_project_dialog import NewProjectDialog
from app.ui.start_page import StartPage
from app.ui.character_panel import CharacterPanel, character_label
from app.ui.library_controller import LibraryController, RoutedEditHistory
from app.ui.project_library import ProjectLibraryPanel
from app.models.project_library import TaskContext, now_stamp
from app.utils.rgba_image import to_rgba8
from app.core.frame_sequence import scan_sequence
from app.i18n import t, manager, translate_error
from app.ui.dialogs import MessageBox as QMessageBox, FileDialog as QFileDialog
from app.ui.animation_preview import AnimationPreview
from app.ui.motion_editor import MotionEditor
from app.exporters.image_exporter import copy_file, export_images
from app.models.frame_data import FrameData
from app.models.project import ALIGNMENT_MODES, Project
from app.ui.anchor_editor import AnchorEditor
from app.ui.controls import ParameterPanel
from app.ui.frame_editor import FrameEditor
from app.models.timeline_edit import EditHistory
from app import __version__, __build__
from app.models.character_reference import CharacterReference, AnimationTransform
from app.core.character_reference import ReferenceSource
from app.ui.character_reference_dialog import CharacterReferenceDialog
from app.ui.sprite_preview import SpritePreview
from app.ui.theme import STYLE
from app.ui.timeline import Timeline
from app.ui.worker import Worker
from app.utils.cache import FrameCache
from app.utils.paths import cache_directory, frame_path
from app.utils.path_memory import PathMemoryService

log = logging.getLogger("aivsprite.ui")


class MainWindow(QMainWindow):
    def __init__(self, log_path: Path, parent=None):
        super().__init__(parent)
        self.log_path = log_path
        self.path_memory=PathMemoryService(manager().settings_path)
        self.path_memory.work_root
        self.project = Project()
        self.project_file = None
        self.cache_dir = cache_directory(self.project.project_id)
        self.worker = None
        self.task_context = None
        self.cache_only_preview = False
        self.preview_worker = None
        self.preview_pending = False
        self.preview_revision = 0
        self.preview_cache = FrameCache(64 * 1024 * 1024)
        self.current_frame = 0
        self.edit_histories = {}
        self.dirty = False
        self.built = False
        self.keyed_ready = False
        self._raw_for_pick = None
        self._preview_frame_index = -1
        self._close_after_work = False
        self._after_save = None
        self._resume_after_work = None
        self.last_error = None
        self.last_export = None
        self.review_windows = []
        self.export_notices = []
        self.character_editor = None
        self.reference_dialog = None
        self.sequence_dialog = None
        self.new_project_dialog = None
        self.setAcceptDrops(True)
        self.setMinimumSize(1080, 720)
        self.resize(1480, 960)
        self.setStyleSheet(STYLE)
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self._start_preview)
        self.play_timer = QTimer(self)
        self.play_timer.timeout.connect(self._advance)
        self._create_ui()
        self.library_controller = LibraryController(self)
        self.character_page.controller = self.library_controller
        self.library_panel = ProjectLibraryPanel(self, self.library_controller)
        self.splitter.insertWidget(0, self.library_panel)
        self.left_scroll.hide()
        self.splitter.setSizes([280, 0, 860, 330])
        self.library_controller.refresh()
        self._sync_controls()
        self._update_title()

    def _create_ui(self):
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(14, 10, 14, 10)
        outer.setSpacing(9)
        toolbar = QHBoxLayout()
        brand = QLabel(t("AI VIDEO  /  SPRITE"))
        brand.setObjectName("brand")
        toolbar.addWidget(brand)
        toolbar.addStretch()
        self.import_button = self._button("Import Video", self.choose_video)
        self.new_button = self._button("New Project", self.new_project)
        self.import_sequence_button = self._button("Import Frame Sequence", self.choose_sequence)
        self.open_button = self._button("Open Project", self.open_project)
        self.save_button = self._button("Save Project", self.save_project)
        self.export_button = self._button("Export", lambda: self.steps.setCurrentIndex(4), primary=True)
        for button in (self.open_button, self.save_button):
            toolbar.addWidget(button)
        for button in (self.new_button,self.import_button,self.import_sequence_button,self.export_button):
            button.setParent(central);button.hide()
        self.undo_button = self._button("Undo", self.undo_edit)
        self.redo_button = self._button("Redo", self.redo_edit)
        toolbar.addWidget(self.undo_button)
        toolbar.addWidget(self.redo_button)
        toolbar.addWidget(self._button("Diagnostics", self.show_diagnostics))
        self.language = QComboBox()
        self.language.addItem("简体中文", "zh_CN")
        self.language.addItem("English", "en_US")
        self.language.setCurrentIndex(self.language.findData(manager().language))
        self.language.setToolTip(t("Language / 语言"))
        self.language.currentIndexChanged.connect(self._change_language)
        toolbar.addWidget(self.language)
        outer.addLayout(toolbar)
        self.steps = QTabBar()
        self.steps.setExpanding(True)
        for text in ("1  Import", "2  Key", "3  Edit", "4  Sprite", "5  Export"):
            self.steps.addTab(t(text))
        self.steps.currentChanged.connect(self._stage_changed)
        outer.addWidget(self.steps)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left.setMinimumWidth(170)
        left.setMaximumWidth(235)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(10, 14, 12, 12)
        title = QLabel(t("SOURCE / FRAME"))
        title.setObjectName("muted")
        left_layout.addWidget(title)
        self.project_status = QLabel()
        self.project_status.setWordWrap(True)
        self.project_status.setObjectName("status")
        left_layout.addWidget(self.project_status)
        self.source_name = QLabel(t("Drop a green-screen video\nto begin"))
        self.source_name.setWordWrap(True)
        left_layout.addWidget(self.source_name)
        self.animation_selector = QComboBox()
        self.animation_selector.setToolTip(t("Animations share one Character Profile. Switching never recalculates the Canonical Root."))
        self.animation_selector.currentIndexChanged.connect(self._select_animation)
        self.animation_selector.hide()
        left_layout.addWidget(self.animation_selector)
        self.source_info = QLabel(t("Resolution   —\nFPS   —\nFrame Count   —\nDuration   —"))
        self.source_info.setObjectName("muted")
        self.source_info.setWordWrap(True)
        left_layout.addWidget(self.source_info)
        self.source_warning = QLabel()
        self.source_warning.setWordWrap(True)
        self.source_warning.setStyleSheet("color: #f2cf75")
        self.source_warning.hide()
        left_layout.addWidget(self.source_warning)
        left_layout.addSpacing(16)
        left_layout.addWidget(QLabel(t("PREVIEW")))
        self.preview_mode = QComboBox()
        for value in ("Original", "Transparent", "Alpha Matte", "Checkerboard"):
            self.preview_mode.addItem(t(value), value)
        self.preview_mode.setCurrentIndex(self.preview_mode.findData("Checkerboard"))
        self.preview_mode.currentIndexChanged.connect(lambda _: self.request_preview())
        left_layout.addWidget(self.preview_mode)
        self.preview_note = QLabel(t("Preview ≤1280 px.\nExports keep full resolution.\n\nWheel: zoom\nDrag: pan"))
        self.preview_note.setWordWrap(True)
        self.preview_note.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.preview_note.setMinimumHeight(150)
        self.preview_note.setObjectName("muted")
        left_layout.addWidget(self.preview_note)
        left_layout.addSpacing(14)
        left_layout.addWidget(QLabel(t("OVERLAYS")))
        self.overlay_checks = {}
        for key, label, checked in (("grid", "Sheet grid", True), ("numbers", "Frame number", True),
                ("root", "Root point", True), ("ground", "Ground line", True), ("bounds", "Alpha bounds", True),
                ("features", "Tracked features", False), ("path", "Root path", False), ("canvas", "Canvas bounds", True),
                ("raw_path", "Raw Root Path", False), ("filtered_path", "Filtered Root Path", False), ("target_path", "Target Root Path", False)):
            check = QCheckBox(t(label))
            if key == "root":
                check.setToolTip(t("tooltip.root_point"))
            check.setChecked(checked)
            check.toggled.connect(lambda value, name=key: self._overlay_changed(name, value))
            self.overlay_checks[key] = check
            left_layout.addWidget(check)
        left_layout.addStretch()
        self.summary = QLabel(t("No sprites built"))
        self.summary.setWordWrap(True)
        self.summary.setObjectName("status")
        left_layout.addWidget(self.summary)
        for label in left.findChildren(QLabel):
            label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setWidget(left)
        left_scroll.setMinimumWidth(180)
        left_scroll.setMaximumWidth(250)
        self.left_scroll = left_scroll
        self.splitter.addWidget(left_scroll)
        middle = QWidget()
        middle_layout = QVBoxLayout(middle)
        middle_layout.setContentsMargins(0, 0, 0, 0)
        view_toolbar = QHBoxLayout()
        self.view_label = QLabel(t("Import a video to see its frames"))
        self.view_label.setObjectName("muted")
        view_toolbar.addWidget(self.view_label, 1)
        self.review_button = self._button("Preview Animation", lambda: self.open_animation_preview(), True)
        self.review_button.setVisible(False)
        view_toolbar.addWidget(self.review_button)
        self.zoom_label = QLabel(t("Fit"))
        view_toolbar.addWidget(self.zoom_label)
        view_toolbar.addWidget(self._button("Fit", lambda: self.active_view().fit_image()))
        view_toolbar.addWidget(self._button("100%", lambda: self.active_view().actual_size()))
        self.view_toolbar_widget=QWidget();self.view_toolbar_widget.setLayout(view_toolbar)
        middle_layout.addWidget(self.view_toolbar_widget)
        self.views = QStackedWidget()
        self.viewer = AnchorEditor()
        self.sprite_view = SpritePreview()
        self.viewer.root_selected.connect(self._set_root)
        self.viewer.color_selected.connect(self._pick_color)
        self.viewer.roi_selected.connect(self._set_roi)
        for view in (self.viewer, self.sprite_view):
            view.zoom_changed.connect(lambda zoom: self.zoom_label.setText(t('{p0:.0f}%', p0=zoom * 100)))
            self.views.addWidget(view)
        self.motion_editor = MotionEditor()
        self.motion_editor.frame_selected.connect(self.select_frame)
        self.views.addWidget(self.motion_editor)
        self.start_page = StartPage(self)
        self.views.addWidget(self.start_page)
        self.asset_info = QPlainTextEdit();self.asset_info.setReadOnly(True);self.views.addWidget(self.asset_info)
        self.asset_view = SpritePreview();self.views.addWidget(self.asset_view)
        self.character_page = CharacterPanel(self);self.views.addWidget(self.character_page)
        self.views.setCurrentWidget(self.start_page)
        middle_layout.addWidget(self.views, 1)
        self.context_hint = QLabel(t("Import → Chroma key → Root → Alignment → Sprite sheet → Export"))
        self.context_hint.setObjectName("muted")
        self.context_hint.setWordWrap(True)
        middle_layout.addWidget(self.context_hint)
        self.splitter.addWidget(middle)
        self.panels = QStackedWidget()
        self.panels.setMinimumWidth(320)
        self.panels.setMaximumWidth(395)
        self.parameter_panels = []
        self._create_panels()
        for widget in (self.project_status,self.source_name,self.animation_selector,self.source_info,self.source_warning,self.preview_mode,self.summary):
            self.parameter_panels[0].layout.addWidget(widget)
        for widget in self.overlay_checks.values():self.parameter_panels[5].layout.addWidget(widget)
        alignment_panels = [self.panels.widget(i).takeWidget() for i in (2, 3, 4)]
        self.views.removeWidget(self.motion_editor)
        self.editor = FrameEditor(self, alignment_panels, self.motion_editor)
        self.views.addWidget(self.editor)
        self.splitter.addWidget(self.panels)
        self.splitter.setSizes([190, 880, 330])
        self.splitter.setStretchFactor(1, 1)
        outer.addWidget(self.splitter, 1)
        playback = QHBoxLayout()
        self.play_button = self._button("▶ Play", self.toggle_play)
        playback.addWidget(self._button("‹", lambda: self.select_frame(self.current_frame - 1)))
        playback.addWidget(self.play_button)
        playback.addWidget(self._button("›", lambda: self.select_frame(self.current_frame + 1)))
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setRange(0, 0)
        self.seek.valueChanged.connect(self.select_frame)
        playback.addWidget(self.seek, 1)
        self.frame_spin = QSpinBox()
        self.frame_spin.setPrefix(t("Frame "))
        self.frame_spin.setMaximum(0)
        self.frame_spin.valueChanged.connect(self.select_frame)
        playback.addWidget(self.frame_spin)
        self.process_button = self._button("Extract / Process", self.process_key, primary=True)
        self.build_button = self._button("Analyze / Build", self.build_sprites, primary=True)
        playback.addWidget(self.process_button)
        playback.addWidget(self.build_button)
        self.playback_widget = QWidget()
        self.playback_widget.setLayout(playback)
        outer.addWidget(self.playback_widget)
        self.timeline = Timeline()
        self.timeline.frame_selected.connect(self.select_frame)
        outer.addWidget(self.timeline)
        status = QHBoxLayout()
        self.status = QLabel(t("Ready · FFmpeg required for video import"))
        status.addWidget(self.status, 1)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(235)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        status.addWidget(self.progress)
        self.cancel_button = self._button("Cancel", self.cancel_work)
        self.cancel_button.setEnabled(False)
        status.addWidget(self.cancel_button)
        outer.addLayout(status)
        toolbar.insertWidget(3,self.save_as_button)
        self.setCentralWidget(central)
        for sequence, callback in (("Ctrl+Z",self.undo_edit),("Ctrl+Shift+Z",self.redo_edit),("Ctrl+Y",self.redo_edit)):
            action = QAction(self);action.setShortcut(QKeySequence(sequence));action.triggered.connect(callback);self.addAction(action)
        self.file_shortcuts=[]
        for sequence, button in ((QKeySequence.StandardKey.New,self.new_button),(QKeySequence.StandardKey.Open,self.open_button),(QKeySequence.StandardKey.Save,self.save_button),(QKeySequence.StandardKey.SaveAs,self.save_as_button)):
            action = QAction(self)
            action.setShortcut(QKeySequence(sequence))
            action.triggered.connect(button.click)
            self.addAction(action);self.file_shortcuts.append((action,button))

    @property
    def viewer(self):
        if hasattr(self, 'editor') and self.steps.currentIndex() == 2:
            return self.editor.alignment_view
        return self.source_viewer

    @viewer.setter
    def viewer(self, value):
        self.source_viewer = value

    def _history(self):
        key = (self.project.project_id, self.project.animation_id)
        return self.edit_histories.setdefault(key, RoutedEditHistory(self.library_controller,key) if hasattr(self,"library_controller") else EditHistory())

    def _edit_snapshot(self):
        p = asdict(self.project)
        keys = ('timeline_edit','root_keyframes','motion_settings','tracking_settings','alignment_mode','sprite_cell',
                'scale','character_profile','processing_mode','full_processing_canvas_mode','passthrough_alignment',
                'chroma_key_settings','sequence_fps','export_settings','character_reference','animation_transform','frame_corrections')
        return {k:p[k] for k in keys}

    def add_frame_correction(self,indices,dx,dy):
        "One drag or nudge becomes exactly one undo command."
        p=self.project;dx,dy=int(round(dx)),int(round(dy))
        if (not dx and not dy) or not indices:return
        before=self._edit_snapshot()
        for index in list(indices):
            x,y=p.frame_correction(index);p.set_frame_correction(index,x+dx,y+dy)
        if before==self._edit_snapshot():return
        self._history().record(before,self._edit_snapshot(),'Frame Correction')
        self.dirty=True;self.built=False;self._invalidate_reviews();self._refresh_editor();self._update_state()

    def reset_frame_corrections(self,indices):
        if not indices:return
        before=self._edit_snapshot()
        self.project.clear_frame_corrections(list(indices))
        if before==self._edit_snapshot():return
        self._history().record(before,self._edit_snapshot(),'Reset Frame Correction')
        self.dirty=True;self.built=False;self._invalidate_reviews();self._refresh_editor();self._update_state()

    def _cancel_editor_interaction(self):
        if hasattr(self,'editor'):self.editor.cancel_active_interaction()

    def changeEvent(self,event):
        if hasattr(self,'editor') and event.type()==QEvent.Type.WindowStateChange:self.editor.cancel_active_interaction()
        super().changeEvent(event)

    def _sync_character_owner(self,value):
        "Undo/redo of an animation must not revert another Animation Reference; keep the owner in step."
        character=self.project.active_character()
        if character is not None:
            character.character_reference=CharacterReference.from_dict(value)
        return character

    def _restore_edit(self, state):
        self.editor.pause_preview()
        data = asdict(self.project);data.update(state)
        self.project = Project.from_dict(data)
        self.dirty, self.built = True, False
        self._invalidate_reviews()
        self._sync_controls();self._refresh_timeline()
        self._refresh_editor()
        self.request_preview()

    def undo_edit(self):
        if hasattr(self,"library_controller") and self.library_controller.index>0:
            self.library_controller.history();return
        if self.interaction_busy:return
        history=self._history();state=history.undo()
        if state is not None:
            if 'character_reference' not in history.last_changed_fields:state['character_reference']=asdict(self.project.character_reference) if self.project.character_reference else None
            self._sync_character_owner(state['character_reference'])
            self._restore_edit(state)

    def redo_edit(self):
        if hasattr(self,"library_controller") and self.library_controller.index<len(self.library_controller.entries):
            self.library_controller.history(True);return
        if self.interaction_busy:return
        history=self._history();state=history.redo()
        if state is not None:
            if 'character_reference' not in history.last_changed_fields:state['character_reference']=asdict(self.project.character_reference) if self.project.character_reference else None
            self._sync_character_owner(state['character_reference'])
            self._restore_edit(state)

    def _refresh_editor(self):
        p = self.project
        if p.source_path and p.layout and p.has_final_edits:
            pipe = Pipeline(p,self.cache_dir)
            if pipe._manifest('align').get('signature') == pipe.align_signature():
                self.editor.bind()
                return
        self.editor.provider = None
        self.editor.refresh()

    def apply_editor_command(self, operation, label):
        if self.worker or not self.project.timeline_edit.enabled:return
        before = self._edit_snapshot()
        self.editor.pause_preview()
        try:
            created = operation(self.project.timeline_edit)
            self.project.timeline_edit.validate(self.project.video.frame_count)
        except Exception as error:
            self._restore_edit(before)
            self.editor.notice.setText(translate_error(str(error)))
            return
        self._history().record(before,self._edit_snapshot(),label)
        if isinstance(created,list):self.editor.selected_ids = created
        self.dirty,self.built = True,False
        self._invalidate_reviews();self._update_state()
        self.editor.bind()

    def open_editor(self):
        self.steps.setCurrentIndex(2)
        self.editor.inspector.setCurrentIndex(0)
        if not self.worker:self.prepare_editor()

    def edit_keyed_frames(self):
        if not self.keyed_ready or self.worker:return
        if self.project.input_mode == 'video' and not self.project.is_passthrough:
            self.project.set_processing_mode('keyed_passthrough')
        self.open_editor()

    def prepare_editor(self):
        if self.steps.currentIndex() != 2:return
        if self.worker or not self.project.video.frame_count:return
        if not self.keyed_ready:
            self.editor.notice.setText(t('Process all keyed frames before editing.'))
            return
        if not self.project.is_passthrough and 0 not in self.project.root_keyframes:
            self.editor.alignment()
            self.editor.notice.setText(t('Set the first Root for alignment, or use Edit Keyed Frames on the Key page.'))
            return
        self.editor.pause_preview()
        p = copy.deepcopy(self.project)
        p.timeline_edit.initialize(p.video.frame_count,p.video.fps or 24)
        directory = self.cache_dir
        def operation(progress,cancel):
            Pipeline(p,directory,progress,cancel).ensure_aligned()
            return p
        def success(project):
            self.project=project;self.dirty=True;self.built=False
            self._sync_controls();self.editor.bind();self._refresh_timeline()
            self.status.setText(t('Editor ready'))
            self.views.setCurrentWidget(self.editor)
        self._run(operation,success,t('Preparing animation editor'),animation_task="editor")

    def _button(self, text, callback, primary=False):
        button = QPushButton(t(text))
        button.setAutoDefault(False)
        button.setToolTip(t(text))
        if primary:
            button.setObjectName("primary")
        button.clicked.connect(callback)
        return button

    def _create_panels(self):
        p = ParameterPanel("Import video", "Every original video frame is decoded and numbered. Playback speed never changes extracted frames.")
        self.project_canvas_info = p.note("")
        p.layout.insertWidget(2, self.project_canvas_info)
        self.project_canvas_description = p.note("All media are fitted by resolution center to the project canvas, without moving content based on character position.")
        p.layout.insertWidget(3, self.project_canvas_description)
        p.decimal("sequence_fps", "Animation FPS", .1, 240)
        p.note("MP4 · MOV · AVI · MKV · WebM\n\nCreate a Group in the Project Library, then add media.\n\nRotated video is decoded in its stored pixel orientation to preserve source resolution.")
        self._add_panel(p)
        p = ParameterPanel("Chroma key", "Adjust the matte, then Extract / Process to create full-resolution transparent PNG frames.")
        self.color_button = p.button("color", "Green Color")
        self.edit_keyed_button = p.button("edit_keyed", "Edit Keyed Frames", True)
        p.layout.insertWidget(2, self.edit_keyed_button)
        self.keyed_continue_button = p.button("full_processing", "Continue Root / Motion Processing")
        self.keyed_passthrough_button = p.button("keyed_passthrough", "Build Sprites Directly", True)
        p.layout.insertWidget(2, self.keyed_continue_button)
        p.layout.insertWidget(3, self.keyed_passthrough_button)
        p.button("eyedropper", "Eyedropper · click background")
        for key, label, lo, hi, step in (("tolerance", "Tolerance", 0, 1, .01), ("softness", "Softness", 0, 1, .01),
            ("edge_feather", "Edge Feather (px)", 0, 5, .1), ("despill_strength", "Despill Strength", 0, 1, .01),
            ("minimum_alpha", "Minimum Alpha", 0, 64, 1), ("noise_removal", "Noise Removal (pixels)", 0, 200, 1),
            ("morphology", "Open / Close Radius", 0, 3, 1)):
            p.slider("chroma_key_settings." + key, label, lo, hi, step)
        p.check("chroma_key_settings.spill_suppression", "Green Spill Suppression")
        p.button("process", "Extract / Process", True)
        self.rgba_key_export_button = p.button("export_rgba", "Export source-size RGBA PNGs")
        self._add_panel(p)
        p = ParameterPanel("Anchor editor", "Select frame 0 and click a stable point on the body. Corrections on later frames restart forward tracking.")
        self.anchor_resume_button = p.button("full_processing", "Enable Root / Motion / Align", True)
        p.layout.insertWidget(2, self.anchor_resume_button)
        p.button("character_space", "Character Space / Reference Box", True)
        self.character_note = p.note("Import Idle to establish a project-level character reference.")
        p.button("root", "Set / Correct Root · click subject", True).setToolTip(t("tooltip.root_point"))
        p.button("delete_root", "Delete Current Correction")
        p.combo("tracking_settings.roi_size", "Tracking ROI", ["Auto", 64, 96, 128, 192, 256])
        p.slider("tracking_settings.min_confidence", "Minimum Confidence", .05, .95, .01)
        p.combo("tracking_settings.estimation", "Motion Estimation", ["affine", "translation"])
        p.button("body_roi", "Define Body ROI")
        p.button("clear_body_roi", "Reset Body ROI")
        self.root_note = p.note("No Root selected.\n\n◆ marks manual keyframes.\n\nLow confidence uses phase correlation or bounded prediction and flags the frame for review.")
        p.button("build", "Track / Analyze / Build", True)
        self._add_panel(p)
        p = ParameterPanel("Motion", "Separate pose, intentional Root Motion and tracking noise. EXTRACT creates in-place sprites and saves displacement for the game state machine.")
        p.check("motion_settings.enabled", "Use axis motion policies")
        p.combo("motion_settings.preset", "Motion Preset", list(PRESETS))
        p.combo("motion_settings.x_policy", "X Motion Policy", ["LOCK", "PRESERVE", "EXTRACT"])
        p.combo("motion_settings.y_policy", "Y Motion Policy", ["LOCK", "GROUND_LOCK", "PRESERVE", "EXTRACT"])
        p.integer("motion_settings.smoothing_window", "Smoothing Window", 1, 51)
        p.slider("motion_settings.spike_threshold", "Spike Threshold (px)", 1, 100, 1)
        p.check("motion_settings.loop_correction", "Loop Drift Correction")
        for field, label in (("takeoff_frame", "Takeoff Frame"), ("apex_frame", "Apex Frame"), ("landing_frame", "Landing Frame")):
            p.integer("motion_settings."+field, label, -1, 10000000)
        p.note("Jump phase -1 means unset. Airborne frames override Ground Lock; extracted movement stays in Root Motion JSON.")
        p.button("ground_roi", "Define Ground ROI")
        p.button("clear_ground_roi", "Reset Ground ROI")
        p.button("build", "Track / Analyze / Build", True)
        self._add_panel(p)
        p = ParameterPanel("Alignment", "Choose which position stays fixed. Root XY and ground contact are separate rules.")
        p.combo("alignment_mode", "Alignment Mode", ALIGNMENT_MODES)
        p.slider("sprite_cell.alpha_threshold", "Alpha Bounding Threshold", 0, 254, 1)
        p.integer("sprite_cell.min_component_size", "Minimum Connected Component Size", 0, 100000)
        p.integer("sprite_cell.bottom_margin", "Bottom Margin (px)", 0, 1024)
        self.alignment_note = p.note("")
        p.button("build", "Analyze / Build", True)
        self._add_panel(p)
        p = ParameterPanel("Sprite cell & sheet", "AUTO uses every frame's aligned bounds. The same scale applies to the entire animation.")
        self.keyed_passthrough_note = p.note("Video passthrough mode\nRoot tracking and position alignment are skipped. Original keyed frame positions are preserved.")
        self.keyed_passthrough_note.setObjectName("status")
        self.sprite_resume_button = p.button("full_processing", "Enable Root / Motion / Align")
        p.layout.insertWidget(2, self.keyed_passthrough_note)
        p.layout.insertWidget(3, self.sprite_resume_button)
        self.sprite_keyed_choice_note = p.note("RGBA frames are ready. Build sprites directly to preserve positions, or continue Root / Motion processing for alignment.")
        self.sprite_direct_button = p.button("keyed_passthrough", "Build Sprites Directly", True)
        self.sprite_continue_button = p.button("full_processing", "Continue Root / Motion Processing")
        for position, widget in enumerate((self.sprite_keyed_choice_note, self.sprite_direct_button, self.sprite_continue_button), 4):
            p.layout.insertWidget(position, widget)
        self.passthrough_resolution = QComboBox()
        for label, value in (("Native Resolution", "native"), ("1536×1536", 1536), ("1024×1024", 1024),
                             ("768×768", 768), ("512×512", 512), ("Custom", "custom")):
            self.passthrough_resolution.addItem(t(label), value)
        self.passthrough_resolution.currentIndexChanged.connect(self._passthrough_resolution_changed)
        p.form.addRow(t("Output Resolution"), self.passthrough_resolution)
        p.combo("sprite_cell.canvas_mode", "Canvas Mode", ["auto_bounds", "normalize_source"])
        p.integer("sprite_cell.target_width", "Target Width", 1, 16384)
        p.integer("sprite_cell.target_height", "Target Height", 1, 16384)
        p.check("sprite_cell.preserve_aspect_ratio", "Preserve Aspect Ratio")
        self.normalize_preset_button = p.button("normalize_preset", "512×512 (1/3)")
        p.combo("sprite_cell.mode", "Cell Size", ["AUTO", "256x256", "512x512", "1024x1024", "CUSTOM"])
        p.integer("sprite_cell.width", "Custom Width", 1, 16384)
        p.integer("sprite_cell.height", "Custom Height", 1, 16384)
        p.combo("sprite_cell.round_up", "Round Up To", ["None", 32, 64, 128, 256])
        p.integer("sprite_cell.padding", "Padding (px)", 0, 1024)
        p.slider("scale", "Character Scale (%)", 10, 400, 1)
        lock = p.check("lock_character_scale", "Lock Character Scale")
        lock.setEnabled(False)
        lock.setToolTip(t("This version always uses one shared scale for all frames."))
        p.integer("export_settings.columns", "Columns (rows are automatic)", 1, 256)
        p.button("build", "Analyze / Build Sheet", True)
        p.button("edit", "Edit Animation")
        p.button("preview", "Preview Animation")
        self.cell_note = p.note("Build to calculate cell dimensions and clipping.")
        self._add_panel(p)
        p = ParameterPanel("Export", "PNG exports contain only the artwork. Grid, root markers and debug overlays stay in the editor.")
        p.text("export_settings.animation_name", "Animation Name")
        p.check("export_settings.loop", "Loop animation")
        p.button("preview", "Preview Export")
        p.button("export_all", "Export for Godot · PNG + JSON + Frames", True)
        p.button("export_sheet", "Export Sprite Sheet")
        p.button("export_frames", "Export Individual Frames")
        self.rgba_export_button = p.button("export_rgba", "Export Source-size RGBA Frames")
        p.button("save", "Save Project")
        self.save_as_button=p.button("save_as", "Save Project As")
        p.note("Choose an output parent folder. Each export creates a new named folder. Godot JSON records source indices, cell regions, roots, bounds and tracking confidence.\n\nVFR input retains all frames; animation playback uses the source average FPS.")
        self._add_panel(p)

    def _add_panel(self, panel):
        panel.changed.connect(self._setting_changed)
        panel.action.connect(self._action)
        panel.finish()
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.Shape.NoFrame)
        area.setWidget(panel)
        self.panels.addWidget(area)
        self.parameter_panels.append(panel)

    def _action(self, name):
        actions = {"import": self.choose_video, "open": self.open_project, "save": self.save_project, "save_as": self.save_project_as,
            "color": self.choose_color, "eyedropper": lambda: self._arm("color"), "root": lambda: self._arm("root"),
            "delete_root": self.delete_root, "process": self.process_key, "build": self.build_sprites,
            "export_all": lambda: self.choose_export("all", True), "export_sheet": lambda: self.choose_export("sheet"),
            "export_frames": lambda: self.choose_export("frames"), "export_rgba": lambda: self.choose_export("rgba")}
        actions.update(preview=self.open_animation_preview, normalize_preset=self._normalize_preset,
            keyed_passthrough=self.start_keyed_passthrough, full_processing=self.enable_full_processing,
            import_sequence=self.choose_sequence, edit=self.open_editor, edit_keyed=self.edit_keyed_frames,
            character_space=self.open_character_space,
            ground_roi=lambda: self._arm_roi("ground_roi"), body_roi=lambda: self._arm_roi("body_roi"),
            clear_ground_roi=lambda: self._clear_roi("ground_roi"), clear_body_roi=lambda: self._clear_roi("body_roi"))
        if not self.interaction_busy:
            actions[name]()

    @property
    def interaction_busy(self):
        return any((self.worker,self.character_editor,self.reference_dialog,self.sequence_dialog,self.new_project_dialog))

    def _remember_path(self,purpose,path,file=False):
        if not self.path_memory.remember(purpose,path,file=file) and self.path_memory.last_error:
            QMessageBox.warning(self,"Path history",t("The operation succeeded, but path history could not be saved. Check Diagnostics."))

    @staticmethod
    def export_purpose(kind,godot=False):
        return 'project_export' if godot else {'sheet':'sprite_sheet_export','frames':'frame_export','rgba':'png_export','all':'sprite_sheet_export'}[kind]

    def _get_setting(self, key):
        obj = self.project
        for part in key.split("."):
            obj = getattr(obj, part)
        if key == "scale":
            return round(obj * 100)
        if key == "sprite_cell.round_up" and obj == 0:
            return "None"
        if key == "tracking_settings.roi_size" and obj == 0:
            return "Auto"
        return obj

    def open_character_reference(self):
        if self.reference_dialog:self.reference_dialog.raise_();return
        if self.worker:return
        if not self.project.video.frame_count:
            self.context_hint.setText(t('Select a Group with an animation before setting the Character Reference.'));return
        if not self.keyed_ready:
            self.editor.notice.setText(t('Process all keyed frames before editing.'));return
        p=self.project
        ref=p.character_reference
        if ref is None:
            w,h=p.project_canvas or (p.video.width,p.video.height)
            ref=CharacterReference(p.animation_id,0,w//2,min(h-1,round(h*.9)),w,h)
        self.editor.pause_preview()
        try:source=ReferenceSource(p,ref,self.cache_dir,self.project_file)
        except (OSError,ValueError,KeyError) as error:
            self.editor.notice.setText(t("Idle reference unavailable: {error}",error=str(error)));return
        def operation(progress,cancel):return source.get(cancel)
        def success(pixels):
            dialog=CharacterReferenceDialog(ref,pixels,source.project.export_settings.animation_name,
                save_uses_passthrough=not p.character_reference and not p.is_passthrough,parent=self)
            self.reference_dialog=dialog
            dialog.saved.connect(self._save_character_reference)
            dialog.finished.connect(self._reference_closed)
            dialog.show();self._update_state()
        self._run(operation,success,t('Loading Character Reference'))

    def _save_character_reference(self,reference):
        before=self._edit_snapshot();p=self.project
        character=p.active_character()
        if character is None:
            character=p.library.add_character('Default Character','blank',1)
            if p.current_group_id in p.library.groups:
                p.library.reassign_character(p.current_group_id,character.id)
            p.current_character_id=character.id
        first=character.character_reference is None
        character.character_reference=reference
        character.modified_at=now_stamp()
        p.sync_character_reference()
        # This explicit calibration workflow starts at stationary keyed pixels.
        # Keep old tracking data/settings available for the separate legacy workflow.
        mode_changed=False
        if first and not p.is_passthrough:
            mode_changed=True
            canvas_mode=p.sprite_cell.canvas_mode
            if p.input_mode=='video':p.set_processing_mode('keyed_passthrough')
            else:p.passthrough_alignment=True;p.alignment_mode='passthrough';p.layout=None
            p.sprite_cell.canvas_mode=canvas_mode if canvas_mode=='normalize_source' else 'source_canvas'
            self.built=False
        self._history().record(before,self._edit_snapshot(),'Character Reference')
        # Reference axes are metadata; only a mode switch invalidates the built sheet.
        self.dirty=True;self._invalidate_reviews(mode_changed);self._sync_controls();self._refresh_editor()
        self.status.setText(t('Character Coordinate System: Locked'))

    def _reference_closed(self,*args):
        self.reference_dialog=None;self._update_state()
        if self.project.character_reference and self.steps.currentIndex()==2 and not self.editor.provider:
            QTimer.singleShot(0,self.prepare_editor)

    def set_animation_offset(self,x,y,relative=False):
        if self.worker or self.reference_dialog:return
        before=self._edit_snapshot();value=self.project.animation_transform
        self.editor.pause_preview()
        self.project.animation_transform=AnimationTransform(value.offset_x+x if relative else x,value.offset_y+y if relative else y)
        if before==self._edit_snapshot():return
        self._history().record(before,self._edit_snapshot(),'Animation Offset')
        self.dirty=True;self.built=False;self._invalidate_reviews();self._refresh_editor();self._update_state()

    def open_character_space(self):
        if self.project.is_passthrough:
            return
        if self.character_editor:
            self.character_editor.raise_()
            return
        if self.worker or not self.project.video.frame_count:
            return
        if self.project.character_profile and 0 not in self.project.root_keyframes:
            self.select_frame(0)
            self._arm("root")
            self.context_hint.setText(t("Set this animation's tracked Root on frame 0. The project Canonical Root will stay fixed."))
            return
        p, directory = copy.deepcopy(self.project), self.cache_dir
        def operation(progress, cancel):
            pipe = Pipeline(p, directory, progress, cancel)
            if p.character_profile:
                pipe.ensure_aligned()
                pixels = FinalFrameProvider(p, directory).get_final_frame(0)
                return p, p.character_profile, pixels, (0., 0.), None
            pipe.ensure_key()
            source = pipe.cache.read(frame_path(pipe.keyed, 0))
            profile, placement, pixels = prepare_character_calibration(source, (p.sprite_cell.target_width, p.sprite_cell.target_height))
            return p, profile, pixels, placement, source
        def success(data):
            p, profile, pixels, placement, source = data
            self.project = p
            self.keyed_ready = True
            editor = CharacterSpaceEditor(profile, pixels, placement, source, self)
            self.character_editor = editor
            editor.profile_saved.connect(self._save_character_profile)
            editor.destroyed.connect(self._character_editor_closed)
            editor.show()
            self._update_state()
        self._run(operation, success, t("Preparing Character Space"))

    def _character_editor_closed(self):
        self.character_editor = None
        self._update_state()

    def _save_character_profile(self, profile, source_root):
        p = self.project
        self._invalidate_reviews()
        p.character_profile = profile
        self.dirty = True
        if source_root is not None:
            p.root_keyframes[0] = tuple(source_root)
            p.motion_settings.enabled = True
            p.sprite_cell.canvas_mode = "normalize_source"
            p.sprite_cell.target_width, p.sprite_cell.target_height = profile.canvas_size
            self.built = False
        else:
            # Width edits only refresh metadata warnings, never image transforms/cache.
            review_reference_bounds(p)
        self.sprite_view.project = p
        self.sprite_view.viewport().update()
        self._sync_controls()
        self._sync_animation_selector()
        self._refresh_timeline()
        self.request_preview()
        self.context_hint.setText(t("Character reference saved. All animations share this Canonical Root; width changes only affect warnings."))

    def _select_animation(self):
        animation_id=self.animation_selector.currentData()
        if animation_id and animation_id!=self.project.animation_id and hasattr(self,'library_controller'):
            self.library_controller.select_animation(animation_id)

    def _sync_animation_selector(self):
        p=self.project
        self.animation_selector.blockSignals(True);self.animation_selector.clear()
        for row in p.library.in_group(p.current_group_id,kinds={'ANIMATION'}):
            self.animation_selector.addItem(row.name,row.animation_id)
        self.animation_selector.setCurrentIndex(self.animation_selector.findData(p.animation_id))
        self.animation_selector.blockSignals(False)
        self.animation_selector.setVisible(self.animation_selector.count()>1)

    def _change_language(self):
        try:
            manager().save_language(self.language.currentData())
        except OSError as error:
            self._failed(str(error))
            return
        QMessageBox.information(self, "Language", "Language saved. Restart the application to apply it. Your project settings are unchanged.")

    def _invalidate_reviews(self, invalidate_result=True):
        p=self.project
        for row in p.library.resources.values():
            if invalidate_result and row.animation_id==p.animation_id and row.kind in ('ANIMATION','GENERATED_SPRITE_SHEET'):row.ready=False
        for review in self.review_windows:
            review.mark_stale()

    def _normalize_preset(self):
        if self.project.character_profile and not self.project.is_passthrough:
            return
        settings = self.project.sprite_cell
        settings.target_width = settings.target_height = 512
        settings.preserve_aspect_ratio = True
        self._setting_changed("sprite_cell.canvas_mode", "normalize_source")

    def _passthrough_resolution_changed(self):
        if not self.project.is_passthrough:
            return
        value = self.passthrough_resolution.currentData()
        settings = self.project.sprite_cell
        if isinstance(value, int):
            settings.target_width = settings.target_height = value
            settings.preserve_aspect_ratio = True
        self._setting_changed("sprite_cell.canvas_mode", "source_canvas" if value == "native" else "normalize_source")
        if value == "custom":
            self.passthrough_resolution.blockSignals(True)
            self.passthrough_resolution.setCurrentIndex(self.passthrough_resolution.findData("custom"))
            self.passthrough_resolution.blockSignals(False)

    def start_keyed_passthrough(self):
        if self.worker or self.project.input_mode != "video" or not self.keyed_ready:
            return
        self._invalidate_reviews()
        self.project.set_processing_mode("keyed_passthrough")
        self.built, self.dirty = False, True
        self._sync_controls()
        self._refresh_timeline()
        self.steps.setCurrentIndex(3)
        self.build_sprites()

    def enable_full_processing(self):
        if self.worker:
            return
        if self.project.input_mode == "frame_sequence" and self.project.is_passthrough:
            self.project.passthrough_alignment = False
            self.project.alignment_mode = ALIGNMENT_MODES[2]
            self.project.sprite_cell.canvas_mode = "auto_bounds"
            self.built, self.dirty = False, True
        if self.project.is_keyed_passthrough:
            self._invalidate_reviews()
            self.project.set_processing_mode("full")
            self.built, self.dirty = False, True
        self._sync_controls()
        self._refresh_timeline()
        self.steps.setCurrentIndex(2)
        self.editor.alignment()
        self.viewer.set_interaction("root")
        self.select_frame(0)
        self.request_preview()

    def _arm_roi(self, mode):
        if not self.project.video.frame_count:
            return
        self.play_timer.stop()
        self.play_button.setText(t("▶ Play"))
        # Body ROI is relative to the first manual anchor used by the tracker.
        if mode == "body_roi":
            self.select_frame(0)
        self.steps.setCurrentIndex(2)
        self.editor.alignment()
        self.viewer.set_interaction(mode)
        self.context_hint.setText(t("Click two opposite corners around the lower body and feet; exclude weapons and effects.") if mode == "ground_roi" else t("Click two opposite corners around the textured torso; transparent pixels are always excluded."))

    def _set_roi(self, mode, roi):
        if self.worker or self._preview_frame_index != self.current_frame:
            return
        if mode == "ground_roi":
            settings = self.project.motion_settings
            settings.ground_roi = tuple(roi)
            settings.roi_reference_root = self.project.root_keyframes.get(self.current_frame,
                self.project.tracking_results[self.current_frame].root if self.current_frame < len(self.project.tracking_results) else None)
            settings.enabled = True
        else:
            self.project.tracking_settings.body_roi = tuple(roi)
        self._invalidate_reviews()
        self.dirty, self.built = True, False
        self.viewer.roi_rect = tuple(roi)
        self.viewer.viewport().update()
        self.context_hint.setText(t("ROI saved in source pixels. Analyze / Build to update tracking and ground detection."))
        self._sync_controls()
        self._refresh_timeline()

    def _clear_roi(self, mode):
        if mode == "ground_roi":
            self.project.motion_settings.ground_roi = None
            self.project.motion_settings.roi_reference_root = None
        else:
            self.project.tracking_settings.body_roi = None
        self._invalidate_reviews()
        self.dirty, self.built = True, False
        self.viewer.roi_rect = None
        self.viewer.viewport().update()
        self._update_state()
        self._refresh_timeline()

    def open_animation_preview(self, export_folder=None):
        if isinstance(export_folder, bool):
            export_folder = None
        if self.project.is_passthrough and not self.worker and not self.built and self.project.video.frame_count:
            self.build_sprites(after=lambda: self.open_animation_preview(export_folder))
            return None
        if self.worker or not self.built or not self.project.layout:
            self.context_hint.setText(t("Settings changed or sprites are not built. Analyze / Build before previewing."))
            self.steps.setCurrentIndex(3)
            return None
        try:
            provider = FinalFrameProvider(self.project, self.cache_dir)
            review = AnimationPreview(provider, export_folder, self)
        except Exception as error:
            self._failed(str(error))
            return None
        review.export_requested.connect(lambda: self.choose_export("all", True))
        self.review_windows.append(review)
        review.destroyed.connect(lambda: self.review_windows.remove(review) if review in self.review_windows else None)
        review.show()
        return review

    def _export_notice(self, result):
        for review in self.review_windows:
            if not review.stale:
                review.export_folder = result
                review.folder_button.setVisible(True)
        dialog = QDialog(self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.setWindowTitle(t("Export complete"))
        layout = QVBoxLayout(dialog)
        label = QLabel(t("Export complete: {folder}", folder=str(result)))
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(label)
        def open_review():
            self.open_animation_preview(result)
            dialog.close()
        layout.addWidget(self._button("Open Animation Preview", open_review, True))
        layout.addWidget(self._button("Close", dialog.close))
        self.export_notices.append(dialog)
        dialog.destroyed.connect(lambda: self.export_notices.remove(dialog) if dialog in self.export_notices else None)
        dialog.show()

    def _sync_controls(self):
        p = self.project
        passthrough = p.is_passthrough
        self.rgba_key_export_button.setText(t("Export Project Canvas RGBA Frames") if p.project_canvas else t("Export source-size RGBA PNGs"))
        self.rgba_export_button.setText(t("Export Project Canvas RGBA Frames") if p.project_canvas else t("Export Source-size RGBA Frames"))
        self.keyed_passthrough_note.setVisible(p.is_keyed_passthrough)
        self.sprite_resume_button.setVisible(p.is_keyed_passthrough)
        self.anchor_resume_button.setVisible(p.is_passthrough)
        for button in (self.keyed_continue_button, self.keyed_passthrough_button, self.edit_keyed_button):
            button.setVisible(p.input_mode == "video" and self.keyed_ready)
        for widget in (self.sprite_keyed_choice_note, self.sprite_direct_button, self.sprite_continue_button):
            widget.setVisible(p.input_mode == "video" and self.keyed_ready and not passthrough)
        self.parameter_panels[5].form.setRowVisible(self.passthrough_resolution, passthrough)
        resolution = "native" if p.sprite_cell.canvas_mode != "normalize_source" else p.sprite_cell.target_width if p.sprite_cell.target_width == p.sprite_cell.target_height and p.sprite_cell.target_width in (512, 768, 1024, 1536) else "custom"
        self.passthrough_resolution.blockSignals(True)
        self.passthrough_resolution.setCurrentIndex(self.passthrough_resolution.findData(resolution))
        self.passthrough_resolution.blockSignals(False)
        self.passthrough_resolution.setItemText(0, t("Project Canvas (no output resize)") if p.project_canvas else t("Native Resolution"))
        canvas_modes = ("source_canvas", "normalize_source") if passthrough else ("auto_bounds", "normalize_source")
        combo = self.parameter_panels[5].fields["sprite_cell.canvas_mode"]
        if tuple(combo.itemData(i) for i in range(combo.count())) != canvas_modes:
            combo.blockSignals(True)
            combo.clear()
            for key in canvas_modes:
                combo.addItem(t(key), key)
            combo.blockSignals(False)
        if combo.findData("source_canvas") >= 0:
            combo.setItemText(combo.findData("source_canvas"), t("Project Canvas (no output resize)") if p.project_canvas else t("source_canvas"))
        for panel in self.parameter_panels:
            panel.set_values({key: self._get_setting(key) for key in panel.fields})
        self.parameter_panels[0].form.setRowVisible(self.parameter_panels[0].fields["sequence_fps"], p.input_mode == "frame_sequence")
        for index, key in enumerate(("1  Import", "2  Key", "3  Edit", "4  Sprite", "5  Export")):
            skipped = p.input_mode == "frame_sequence" and index == 1
            self.steps.setTabText(index, t("{step} · Skipped", step=t(key)) if skipped else t(key))
            self.steps.setTabEnabled(index, not skipped)
        for index in (2, 3, 4):
            self.parameter_panels[index].setEnabled(True)
            for widget in (*self.parameter_panels[index].fields.values(), *self.parameter_panels[index].findChildren(QPushButton)):
                widget.setEnabled(not passthrough or widget is self.anchor_resume_button)
        color = self.project.chroma_key_settings.green_color
        self.color_button.setText(t('Green Color   RGB {p0}, {p1}, {p2}', p0=color[0], p1=color[1], p2=color[2]))
        custom = self.project.sprite_cell.mode == "CUSTOM"
        for key in ("sprite_cell.width", "sprite_cell.height"):
            self.parameter_panels[5].fields[key].setEnabled(custom and self.project.sprite_cell.canvas_mode == "auto_bounds")
        normalize = self.project.sprite_cell.canvas_mode == "normalize_source"
        for key in ("sprite_cell.target_width", "sprite_cell.target_height", "sprite_cell.preserve_aspect_ratio"):
            self.parameter_panels[5].fields[key].setEnabled(normalize)
        for key in ("sprite_cell.mode", "sprite_cell.round_up", "sprite_cell.padding", "scale"):
            self.parameter_panels[5].fields[key].setEnabled(not normalize)
        for key in ("sprite_cell.mode", "sprite_cell.round_up", "sprite_cell.padding", "scale", "lock_character_scale", "sprite_cell.width", "sprite_cell.height"):
            self.parameter_panels[5].form.setRowVisible(self.parameter_panels[5].fields[key], not normalize)
        self.parameter_panels[4].fields["alignment_mode"].setEnabled(not passthrough and not self.project.motion_settings.enabled)
        profile = self.project.character_profile if not passthrough else None
        self.normalize_preset_button.setEnabled(profile is None)
        self.normalize_preset_button.setVisible(not passthrough or (p.video.width, p.video.height) == (1536, 1536))
        self.parameter_panels[5].fields["sprite_cell.canvas_mode"].setEnabled(profile is None)
        if profile:
            for key in ("sprite_cell.canvas_mode", "sprite_cell.target_width", "sprite_cell.target_height", "sprite_cell.preserve_aspect_ratio"):
                self.parameter_panels[5].fields[key].setEnabled(False)
            for key in ("motion_settings.enabled", "motion_settings.x_policy", "motion_settings.y_policy"):
                self.parameter_panels[3].fields[key].setEnabled(False)
            motion_values = {key: self._get_setting(key) for key in self.parameter_panels[3].fields}
            motion_values.update({"motion_settings.enabled": True,
                "motion_settings.x_policy": "EXTRACT", "motion_settings.y_policy": "EXTRACT"})
            self.parameter_panels[3].set_values(motion_values)
            self.parameter_panels[4].fields["alignment_mode"].setEnabled(False)
            self.character_note.setText(t("Fixed Canonical Root ({x:.2f}, {y:.2f}); Y Axis X = {x:.2f}. Every animation uses In-Place alignment. Edit reference width in Character Space.", x=profile.canonical_root[0], y=profile.canonical_root[1]))
        else:
            for key in ("motion_settings.enabled", "motion_settings.x_policy", "motion_settings.y_policy"):
                self.parameter_panels[3].fields[key].setEnabled(not passthrough)
            self.character_note.setText(t("Import Idle to establish a project-level character reference."))
        mode = ALIGNMENT_MODES[0] if passthrough else self.project.alignment_mode
        self.alignment_note.setText(t("Axis motion policies are active. Configure X and Y on the Motion page. Legacy alignment applies only when motion policies are disabled.") if self.project.motion_settings.enabled else t({ALIGNMENT_MODES[0]: "Root X and Y stay fixed. Foot height can vary with the pose.",
            ALIGNMENT_MODES[1]: "Only the lowest effective alpha pixel stays on the ground. Source X motion is preserved.",
            ALIGNMENT_MODES[2]: "Root X stays fixed; the lowest effective alpha pixel stays on the ground. Anatomical root Y may vary."}[mode]))
        if profile:
            self.alignment_note.setText(self.character_note.text())
        if passthrough:
            for key in ("sprite_cell.mode", "sprite_cell.round_up", "sprite_cell.padding", "scale", "lock_character_scale", "sprite_cell.width", "sprite_cell.height"):
                self.parameter_panels[5].fields[key].setEnabled(False)
                self.parameter_panels[5].form.setRowVisible(self.parameter_panels[5].fields[key], False)
            self.alignment_note.setText(self.keyed_passthrough_note.text() if p.is_keyed_passthrough else t("Frame sequence passthrough — pixels stay in place. Root, Motion, Align and Character Profile alignment are skipped."))
        for key in ("root", "ground", "features", "path", "raw_path", "filtered_path", "target_path"):
            self.overlay_checks[key].setEnabled(not passthrough)
        self.parameter_panels[5].description.setText(t("Frame sequence passthrough — pixels stay in place. Root, Motion, Align and Character Profile alignment are skipped.") if passthrough else t("AUTO uses every frame's aligned bounds. The same scale applies to the entire animation."))
        if p.is_keyed_passthrough:
            self.parameter_panels[5].description.setText(t("Every keyed frame keeps its source position. Resize applies one shared canvas transform to all frames."))
        self._refresh_source_info()
        self._update_state()

    def _setting_changed(self, key, value):
        self.cache_only_preview=False
        obj = self.project
        parts = key.split(".")
        for part in parts[:-1]:
            obj = getattr(obj, part)
        previous = getattr(obj, parts[-1])
        if key == "scale":
            value = value / 100
        elif key in ("sprite_cell.round_up", "tracking_settings.roi_size"):
            value = 0 if value in ("None", "Auto") else int(value)
        elif isinstance(previous, int) and not isinstance(previous, bool):
            value = int(value)
        setattr(obj, parts[-1], value)
        if key == "sequence_fps":
            self.project.sync_sequence_timing()
            self._refresh_source_info()
        if key == "motion_settings.preset" and value != "custom":
            self.project.motion_settings.x_policy, self.project.motion_settings.y_policy = PRESETS[value]
            self.project.motion_settings.enabled = True
        if key in ("motion_settings.x_policy", "motion_settings.y_policy"):
            self.project.motion_settings.preset = "custom"
        self.dirty = True
        if key == "export_settings.animation_name":
            row=self.project.library.animation(self.project.animation_id)
            if row:row.name=str(value).strip() or row.name
        if key != "export_settings.animation_name":
            self._invalidate_reviews()
            self.built = False
            if key.startswith("chroma_key_settings"):
                self.keyed_ready = False
            self.summary.setText(t("Settings changed\nBuild required"))
        self._sync_controls()
        self._refresh_timeline()
        self.request_preview()

    def _update_title(self):
        name = self.project_file.name if self.project_file else t("Untitled")
        self.setWindowTitle(t('AI Video to Sprite — {p0}{p1}', p0=name, p1=' *' if self.dirty else '') + f' · v{__version__} · {__build__}')
        display = self.project.project_name or (self.project_file.stem if self.project_file else t("Untitled"))
        self.project_status.setText(t("Project: {name}", name=display) + "\n" + t("Character Coordinate System: Locked" if self.project.character_reference else "Character Profile: locked" if self.project.character_profile else "Character reference: not established"))
        self.start_page.update_project(self.project, self.project_file is not None)

    def _update_state(self):
        busy = self.worker is not None or self.character_editor is not None or self.reference_dialog is not None or self.sequence_dialog is not None or self.new_project_dialog is not None
        has_video = self.project.video.frame_count > 0
        for button in (self.new_button, self.import_button, self.import_sequence_button, self.open_button, self.save_button, self.export_button, *self.start_page.buttons):
            button.setEnabled(not busy)
        self.panels.setEnabled(not busy)
        self.editor.setEnabled(not self.current_animation_busy and has_video)
        for index in (1,2,3,4,5):self.parameter_panels[index].setEnabled(not busy and has_video)
        for button in self.parameter_panels[6].findChildren(QPushButton):
            button.setEnabled(not busy and (has_video or button.property('uiAction') in ('save','save_as')))
        history = self._history()
        self.undo_button.setEnabled(not busy and history.index > 0)
        self.redo_button.setEnabled(not busy and history.index < len(history.entries))
        self.process_button.setEnabled(has_video and not busy and self.project.input_mode != "frame_sequence")
        self.build_button.setEnabled(has_video and not busy)
        self.cancel_button.setEnabled(self.worker is not None)
        self.play_button.setEnabled(has_video and not self.current_animation_busy)
        self.viewer.setEnabled(not self.current_animation_busy)
        self.animation_selector.setEnabled(not busy or bool(self.task_context))
        self.review_button.setEnabled((self.built or self.project.is_passthrough and has_video) and not busy)
        self.export_button.setEnabled(has_video and not busy)
        for action,button in self.file_shortcuts:action.setEnabled(button.isEnabled() and not busy)
        if hasattr(self,'library_controller'):
            for button in (self.import_button,self.import_sequence_button):button.setEnabled(not busy and self.library_controller.can_import)
            self.undo_button.setEnabled(not busy and (self.library_controller.index>0 or history.index>0))
            self.redo_button.setEnabled(not busy and (self.library_controller.index<len(self.library_controller.entries) or history.index<len(history.entries)))
            self.library_controller.refresh()
        self._update_title()

    @property
    def current_animation_busy(self):
        return bool(self.worker and (self.task_context is None or self.task_context.animation_id==self.project.animation_id))

    def active_view(self):
        return self.editor if self.steps.currentIndex() == 2 else self.views.currentWidget()

    def _stage_changed(self, index):
        if not hasattr(self, 'editor'): return
        self._cancel_editor_interaction()
        if hasattr(self,"library_controller"):self.library_controller.asset_id=None
        editing = index == 2
        self.view_toolbar_widget.setVisible(not editing)
        self.left_scroll.hide()
        self.panels.setVisible(not editing)
        self.timeline.setVisible(not editing)
        self.playback_widget.setVisible(not editing)
        self.context_hint.setVisible(not editing)
        self.panels.setCurrentIndex({0:0, 1:1, 3:5, 4:6}.get(index,0))
        self.source_viewer.set_interaction(None)
        if editing:
            self.views.setCurrentWidget(self.editor)
            self.editor.bind()
            if not self.worker and not getattr(getattr(self,"library_controller",None),"restoring",False) and self.keyed_ready and (self.project.is_passthrough or 0 in self.project.root_keyframes):
                QTimer.singleShot(0, self.prepare_editor)
        else:
            self.editor.pause_preview()
            self.views.setCurrentWidget(self.sprite_view if index in (3,4) and self.built else self.source_viewer)
            if not self.project.video.frame_count:self.views.setCurrentWidget(self.start_page)
        self.preview_mode.setEnabled(not editing and not (index in (3,4) and self.built))
        self.review_button.setVisible(index in (3,4))
        if index in (3,4) and self.built:self.view_label.setText(t("Sprite Sheet · overlays are preview only"))
        self.request_preview()
        self._update_state()

    def _overlay_changed(self, key, value):
        for view in (self.viewer, self.sprite_view):
            view.overlays[key] = value
            view.viewport().update()

    def select_frame(self, index):
        if not self.project.video.frame_count:
            return
        self.current_frame = min(self.project.video.frame_count - 1, max(0, index))
        for control in (self.seek, self.frame_spin):
            control.blockSignals(True)
            control.setValue(self.current_frame)
            control.blockSignals(False)
        self.timeline.select(self.current_frame)
        self.motion_editor.select_frame(self.current_frame)
        if self.project.project_canvas and self.project.input_mode == "frame_sequence":
            self._refresh_source_info()
        self.request_preview()

    def toggle_play(self):
        if self.play_timer.isActive():
            self.play_timer.stop()
            self.play_button.setText(t("▶ Play"))
        elif self.project.video.fps:
            self.play_timer.start(max(1, round(1000 / self.project.video.fps)))
            self.play_button.setText(t("Ⅱ Pause"))

    def _advance(self):
        # Each playback tick advances one source index; decode/export never depends on this timer.
        if self.preview_worker:
            return
        self.select_frame((self.current_frame + 1) % self.project.video.frame_count)

    def _refresh_timeline(self):
        p = self.project
        self.timeline.set_frames(p.tracking_results, p.video.frame_count, p.root_keyframes, not self.built)
        self.timeline.select(self.current_frame)
        roots = ", ".join(str(n) for n in sorted(p.root_keyframes))
        self.root_note.setText(t("Manual keyframes: {roots}\n\nClick a stable point on the body. Root paths reveal drift. Low confidence triggers fallback and a warning.", roots=roots or t("none")))

    def request_preview(self):
        self.preview_revision += 1
        self.preview_pending = True
        self.preview_timer.start(0 if self.play_timer.isActive() else 65)

    def _start_preview(self):
        if hasattr(self,"library_controller") and self.library_controller.asset_id:return
        if self.steps.currentIndex() == 2 and self.editor.inspector.currentIndex() == 0:
            self.editor.request_preview()
            return
        if self.current_animation_busy or not self.project.video.frame_count:
            return
        if self.preview_worker:
            return
        if self.steps.currentIndex() in (3, 4) and self.built:
            self.views.setCurrentWidget(self.sprite_view)
            self.view_label.setText(t("Sprite Sheet · overlays are preview only"))
            return
        self.views.setCurrentWidget(self.editor if self.steps.currentIndex() == 2 else self.source_viewer)
        index, revision = self.current_frame, self.preview_revision
        settings = copy.deepcopy(self.project.chroma_key_settings)
        sequence = self.project.input_mode == "frame_sequence"
        aligned = False  # Root interaction always uses the fitted source canvas.
        path = frame_path(self.cache_dir / ("aligned_frames" if aligned else "raw_frames"), index)
        if not path.exists():
            return
        mode = "Original" if self.steps.currentIndex() == 0 else self.preview_mode.currentData()
        keyed_path = frame_path(self.cache_dir / "keyed_frames", index)
        use_keyed_cache = self.keyed_ready and keyed_path.is_file()
        cache_only=self.cache_only_preview
        self.preview_pending = False
        preview_cache = self.preview_cache
        def operation(progress, cancel):
            full = preview_cache.read(path)
            factor = min(1, 1280 / max(full.shape[:2]))
            if aligned or sequence:
                pixels = full.copy()
            elif mode == "Original":
                pixels = full.copy()
                pixels[..., 3] = 255
            elif use_keyed_cache:
                pixels = preview_cache.read(keyed_path).copy()
            elif cache_only:
                pixels = full.copy()
            else:
                pixels = chroma_key(full[..., :3], settings)
            if factor < 1:
                pixels = premultiplied_resize(pixels, max(1, round(full.shape[1]*factor)), max(1, round(full.shape[0]*factor)))
            pixels = to_rgba8(pixels)
            bbox = alpha_bbox(pixels, 16, 1)
            if mode == "Alpha Matte":
                pixels = np.repeat(pixels[..., 3:4], 4, axis=2)
                pixels[..., 3] = 255
            return {"pixels": pixels, "factor": factor, "raw": full if not aligned else None,
                    "index": index, "revision": revision, "mode": mode, "aligned": aligned, "bbox": bbox}
        worker = Worker(operation, self)
        self.preview_worker = worker
        worker.result.connect(self._preview_result)
        worker.failed.connect(self._preview_failed)
        worker.finished.connect(self._preview_finished)
        worker.start()

    def _preview_result(self, data):
        if data["revision"] != self.preview_revision or self.current_animation_busy:
            return
        self._raw_for_pick = data["raw"]
        self._preview_frame_index = data["index"]
        self.viewer.set_background(data["mode"] == "Checkerboard")
        self.viewer.set_image(data["pixels"], data["factor"])
        p, index = self.project, self.current_frame
        if self.built and index < len(p.tracking_results):
            frame = copy.deepcopy(p.tracking_results[index])
            if data["aligned"]:
                frame.root, frame.bbox = frame.cell_root, frame.cell_bbox
                sx, sy = p.layout.normalize_scale if p.sprite_cell.canvas_mode == "normalize_source" else (p.scale, p.scale)
                frame.features = [(x*sx+frame.offset[0], y*sy+frame.offset[1]) for x, y in frame.features]
        else:
            bbox = tuple(round(v / data["factor"]) for v in data["bbox"]) if data["bbox"] else None
            known_root = p.root_keyframes.get(index)
            if known_root is None and index < len(p.tracking_results):
                known_root = p.tracking_results[index].root
            frame = FrameData(index, bbox=bbox, root=known_root or (0, 0), manual=index in p.root_keyframes)
        self.viewer.frame = frame if p.root_keyframes or frame.bbox else None
        self.viewer.root_visible = not p.is_passthrough and bool(p.root_keyframes or p.tracking_results)
        self.viewer.ground = p.layout.ground_baseline if data["aligned"] else frame.ground
        self.viewer.character_profile = p.character_profile if data["aligned"] and not p.is_passthrough else None
        self.viewer.root_path = [] if data["aligned"] else [f.root for f in p.tracking_results]
        self.viewer.root_paths = {} if data["aligned"] else {key: [getattr(f, name) or f.root for f in p.tracking_results]
            for key, name in (("raw_path", "raw_root"), ("filtered_path", "filtered_root"), ("target_path", "target_root"))}
        self.viewer.roi_rect = None if data["aligned"] else frame.ground_roi
        if p.is_passthrough:
            self.viewer.ground, self.viewer.root_path, self.viewer.root_paths = None, [], {}
        self.viewer.viewport().update()
        self.view_label.setText(t("Frame {index:06d} · {mode}", index=index, mode=t("Aligned cell" if data["aligned"] else data["mode"])))

    def _preview_failed(self, message):
        self.status.setText(t("Preview error · see Diagnostics"))
        self.last_error = message

    def _preview_finished(self):
        worker = self.preview_worker
        self.preview_worker = None
        if worker:
            worker.deleteLater()
        if self.preview_pending:
            self.preview_timer.start(1)

    def _arm(self, mode):
        if self.project.is_passthrough or self.project.input_mode == "frame_sequence" and mode == "color":
            return
        if not self.project.video.frame_count:
            return
        self.play_timer.stop()
        self.play_button.setText(t("▶ Play"))
        self.steps.setCurrentIndex(2 if mode == "root" else 1)
        if mode == "root": self.editor.alignment()
        self.viewer.set_interaction(mode)
        self.context_hint.setText(t("Click the stable body root. Coordinates are stored in source pixels.") if mode == "root" else t("Click the green-screen background to sample its RGB color."))

    def _set_root(self, x, y):
        if self.worker or self._preview_frame_index != self.current_frame:
            return
        self.project.root_keyframes[self.current_frame] = (float(x), float(y))
        self._invalidate_reviews()
        self.dirty, self.built = True, False
        self.summary.setText(t("Root keyframe changed\nBuild required"))
        self.context_hint.setText(t('Manual Root at frame {p0}: ({p1:.2f}, {p2:.2f}). Analyze / Build to track forward.', p0=self.current_frame, p1=x, p2=y))
        self._refresh_timeline()
        self._update_state()
        self.request_preview()

    def delete_root(self):
        if self.current_frame in self.project.root_keyframes:
            del self.project.root_keyframes[self.current_frame]
            self._invalidate_reviews()
            self.dirty, self.built = True, False
            self._refresh_timeline()
            self._update_state()
            self.request_preview()

    def _pick_color(self, x, y):
        if self._raw_for_pick is None or self._preview_frame_index != self.current_frame:
            return
        image = self._raw_for_pick
        x, y = min(image.shape[1]-1, max(0, round(x))), min(image.shape[0]-1, max(0, round(y)))
        self._apply_color(tuple(int(v) for v in image[y, x, :3]))
        self.viewer.set_interaction(None)

    def choose_color(self):
        from PySide6.QtGui import QColor
        color = QColorDialog.getColor(QColor(*self.project.chroma_key_settings.green_color), self, t("Green Screen Color"))
        if color.isValid():
            self._apply_color((color.red(), color.green(), color.blue()))

    def _apply_color(self, color):
        self._invalidate_reviews()
        self.project.chroma_key_settings.green_color = color
        self.built, self.keyed_ready, self.dirty = False, False, True
        self._sync_controls()
        self._refresh_timeline()
        self.request_preview()

    def _run(self, operation, success, label, *, animation_task=None):
        if self.worker:return
        self.last_error=None;self.preview_revision+=1;self.play_timer.stop()
        self.play_button.setText(t("▶ Play"));self.status.setText(t(label))
        context=TaskContext(self.project.project_id,self.project.current_group_id,self.project.animation_id,animation_task or label,
            self.project.current_character_id)
        self.task_context=context if animation_task else None
        worker=Worker(operation,self);worker.task_context=context;self.worker=worker
        def receive(result):
            if animation_task:
                processed=result if isinstance(result,Project) else result[0]
                if self.project.project_id!=context.project_id or not self.project.library.animation(context.animation_id):return
                active=(self.project.animation_id==context.animation_id and self.project.current_group_id==context.group_id
                    and self.project.current_character_id==context.character_id)
                self.project=self.project.merge_animation_result(processed)
                if animation_task=='build':self.project.library.mark_generated(context.animation_id,True)
                row=self.project.library.animation(context.animation_id);row.warning=''
                self.dirty=True
                if active:
                    merged=self.project
                    result=merged if isinstance(result,Project) else (merged,*result[1:])
                    success(result)
                else:
                    self.status.setText(t('Background result saved to {name}.',name=row.name))
                self.library_controller.refresh()
            else:
                success(result)
                self.library_controller.refresh()
        def failed(message):
            row=self.project.library.animation(context.animation_id)
            if row and context.project_id==self.project.project_id:row.warning=message
            self._failed(message)
        worker.progress.connect(self._on_progress);worker.result.connect(receive);worker.failed.connect(failed)
        worker.cancelled.connect(lambda:self.status.setText(t("Cancelled · completed cache stages retained")))
        worker.finished.connect(self._finished);self._update_state();worker.start()

    def _on_progress(self, value, total, message):
        self.status.setText(t("{stage} · {value}/{total}", stage=t(message), value=value, total=total or "?"))
        self.progress.setRange(0, total if total else 0)
        if total:
            self.progress.setValue(min(value, total))

    def _failed(self, message):
        self._after_save = None
        self.last_error = message
        self.status.setText(t("Operation failed · see Diagnostics"))
        QMessageBox.critical(self, "AI Video to Sprite", translate_error(message))

    def _finished(self):
        worker = self.worker
        self.worker = None
        self.task_context = None
        if worker:
            worker.deleteLater()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self._update_state()
        self.request_preview()
        if self._resume_after_work:
            callback = self._resume_after_work
            self._resume_after_work = None
            QTimer.singleShot(0, callback)
        if self._close_after_work:
            self._close_after_work = False
            QTimer.singleShot(0, self.close)

    def cancel_work(self):
        if self.worker:
            self.worker.cancel()
            self.cancel_button.setEnabled(False)
            self.status.setText(t("Cancelling…"))

    def choose_video(self):
        if not self.library_controller.require_group():return
        self.library_controller.capture()
        self.cache_only_preview=False
        if self.interaction_busy:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Import Video", "", "Video (*.mp4 *.mov *.avi *.mkv *.webm)",purpose="video_import")
        if path:
            self.import_video(Path(path))

    def choose_sequence(self):
        if not self.library_controller.require_group():return
        self.library_controller.capture()
        self.cache_only_preview=False
        if self.worker or self.character_editor or self.reference_dialog or self.sequence_dialog or self.new_project_dialog:
            return
        folder = QFileDialog.getExistingDirectory(self, "Choose an animation frame folder (PNG recommended)", self._project_folder("sequences"), sequence=True,purpose="image_sequence_import")
        if folder:
            self.import_sequence(Path(folder))

    def import_sequence(self, folder):
        if not self.library_controller.require_group():return
        self.library_controller.capture()
        self.cache_only_preview=False
        if self.worker or self.character_editor or self.reference_dialog or self.sequence_dialog or self.new_project_dialog:
            return
        if not self._inherits_project() and not self._confirm_discard(lambda: self.import_sequence(folder)):
            return
        def success(scan):
            dialog = SequenceImportDialog(scan, self, self.project.project_canvas if self._inherits_project() else None)
            dialog.fps.setValue(self.project.default_fps)
            self.sequence_dialog = dialog
            dialog.import_requested.connect(self._accept_sequence)
            dialog.destroyed.connect(self._sequence_dialog_closed)
            dialog.show()
            self._update_state()
        self._run(lambda progress, cancel: scan_sequence(folder, progress, cancel), success, "Scanning sequence frames")

    def _sequence_dialog_closed(self):
        self.sequence_dialog = None
        self._update_state()

    def _accept_sequence(self, scan, passthrough, fps, size_policy):
        inherit = self._inherits_project()
        origin = self.project if inherit else Project()
        p = origin.import_frame_sequence(Path(scan.folder), fps, passthrough, size_policy)
        project_file = self.project_file if inherit else None
        directory = cache_directory(p.project_id, project_file, p.animation_id)
        def success(project):
            self._invalidate_reviews(False)
            self.project, self.cache_dir, self.project_file = project, directory, project_file
            self._remember_path("image_sequence_import",project.sequence_folder)
            self.dirty, self.built, self.keyed_ready = True, False, True
            self._loaded()
            self.steps.setCurrentIndex(3 if project.is_passthrough else 2)
            if project.is_passthrough:
                self._resume_after_work = self.build_sprites
        self._run(lambda progress, cancel: Pipeline(p, directory, progress, cancel).import_sequence(), success, "Importing sequence RGBA frames")

    def import_video(self, path: Path):
        if not self.library_controller.require_group():return
        self.library_controller.capture()
        self.cache_only_preview=False
        if self.worker or self.character_editor or self.reference_dialog or self.sequence_dialog or self.new_project_dialog:
            return
        inherit = self._inherits_project()
        if not inherit and not self._confirm_discard(lambda: self.import_video(path)):
            return
        p = self.project.import_animation(path) if inherit else Project(source_video=str(path.resolve()))
        p.motion_settings.enabled = True
        project_file = self.project_file if inherit else None
        directory = cache_directory(p.project_id, project_file, p.animation_id)
        def operation(progress, cancel):
            return Pipeline(p, directory, progress, cancel).import_video()
        def success(project):
            self._invalidate_reviews(False)
            self.project, self.cache_dir, self.project_file = project, directory, project_file
            self._remember_path("video_import",project.source_video,file=True)
            if not project.character_profile and (project.video.width, project.video.height) == (1536, 1536):
                project.sprite_cell.canvas_mode = "normalize_source"
            self.dirty, self.built, self.keyed_ready = True, False, False
            self._loaded()
            self.steps.setCurrentIndex(1)
            self.status.setText(t('Imported {p0} original frames · adjust key, then Extract / Process', p0=project.video.frame_count))
        self._run(operation, success, t("Importing / decoding original video"))

    def show_character_page(self,ident):
        character=self.project.library.characters.get(ident)
        self.character_page.refresh(character)
        self.editor.pause_preview();self.play_timer.stop()
        self.views.setCurrentWidget(self.character_page)
        self.view_label.setText(character_label(character) if character else t('Characters'))
        self._update_state()

    def _loaded(self):
        self.project.ensure_library()
        p = self.project
        self.keyed_ready = p.input_mode == "frame_sequence" or bool(p.video.frame_count and Pipeline(p, self.cache_dir).key_cache_ready())
        self.play_timer.stop()
        self.play_button.setText(t("▶ Play"))
        self.preview_revision += 1
        self.last_export = None
        if not self.built:
            self.summary.setText(t("No sprites built"))
        self.views.setCurrentWidget(self.source_viewer if p.video.frame_count else self.start_page)
        self.current_frame = 0
        self.preview_cache = FrameCache(64 * 1024 * 1024)
        self.viewer.clear_image()
        self.sprite_view.clear_image()
        self._raw_for_pick = None
        self._preview_frame_index = -1
        self.source_name.setText(Path(p.source_path).name)
        self.source_name.setToolTip(p.source_path)
        v = p.video
        self._refresh_source_info()
        self.seek.setMaximum(max(0, v.frame_count-1))
        self.frame_spin.setMaximum(max(0, v.frame_count-1))
        self._sync_controls()
        self._sync_animation_selector()
        self._refresh_timeline()
        self.motion_editor.set_frames(p.tracking_results)
        self.select_frame(0)

    def _refresh_source_info(self):
        p, v = self.project, self.project.video
        self.project_canvas_info.setVisible(bool(p.project_canvas))
        self.project_canvas_description.setVisible(bool(p.project_canvas))
        warning = alpha_warning(p.sequence_formats) if p.input_mode == "frame_sequence" else ""
        self.source_warning.setText(warning)
        self.source_warning.setVisible(bool(warning))
        if p.input_mode == "frame_sequence":
            text = t("Folder: {folder}\nDetected: {count} frames\nSize: {width} × {height}\nAlpha: {alpha}",
                folder=Path(p.sequence_folder).name, count=v.frame_count, width=v.width, height=v.height, alpha=t(p.sequence_alpha))
            text += "\n"+t("Animation FPS: {fps:g}", fps=p.sequence_fps)
            text += "\n"+format_summary(p.sequence_formats)
            text += "\n\n"+t("Frame sequence passthrough" if p.is_passthrough else "Frame sequence · Root / Motion / Align")
            self.source_info.setText(text)
        else:
            self.source_info.setText(t('Resolution   {p0} × {p1}\nFPS   {p2:.5g}\nFrame Count   {p3}\nDuration   {p4:.3f} s', p0=v.width, p1=v.height, p2=v.fps, p3=v.frame_count, p4=v.duration))
            if p.is_keyed_passthrough:
                self.source_info.setText(self.source_info.text() + "\n\n" + t("Video passthrough mode"))
        if p.project_canvas:
            original = p.sequence_sizes[min(self.current_frame, len(p.sequence_sizes)-1)] if p.input_mode == "frame_sequence" and p.sequence_sizes else p.original_size
            summary = canvas_fit_summary(original, p.project_canvas)
            self.project_canvas_info.setText(summary)
            self.source_info.setText(self.source_info.text() + "\n\n" + summary)

    def process_key(self):
        if not self.project.video.frame_count or self.worker or self.project.input_mode == "frame_sequence":
            return
        p = copy.deepcopy(self.project)
        directory = self.cache_dir
        def operation(progress, cancel):
            pipe = Pipeline(p, directory, progress, cancel)
            pipe.ensure_key()
            return p
        def success(project):
            self.project = project
            self.keyed_ready, self.dirty = True, True
            self.status.setText(t('{count} RGBA frames ready · continue Root processing or build sprites directly', count=project.video.frame_count))
            self._sync_controls()
            self.steps.setCurrentIndex(1)
            self.panels.widget(1).verticalScrollBar().setValue(0)
            self.select_frame(0)
        self._run(operation, success, t("Extracting transparent frames"),animation_task="key")

    def build_sprites(self, after=None):
        if not self.project.video.frame_count or self.worker:
            return
        if not self.project.is_passthrough and 0 not in self.project.root_keyframes:
            if self.project.input_mode == "video" and self.keyed_ready:
                # A keyed video can build without a root. Keep both workflows
                # accessible instead of forcing users back to the anchor page.
                self._sync_controls()
                self.steps.setCurrentIndex(3)
                self.panels.widget(5).verticalScrollBar().setValue(0)
                self.status.setText(t("RGBA frames are ready. Build sprites directly to preserve positions, or continue Root / Motion processing for alignment."))
                return
            self.steps.setCurrentIndex(2)
            self.select_frame(0)
            self._arm("root")
            self.context_hint.setText(t("Select a Root on frame 0 to begin tracking and alignment."))
            return
        p = copy.deepcopy(self.project)
        self._invalidate_reviews()
        directory = self.cache_dir
        def operation(progress, cancel):
            pipe = Pipeline(p, directory, progress, cancel)
            pipe.build()
            with Image.open(directory / "sheet_preview.png") as image:
                pixels = np.array(image.convert("RGBA"))
            factor = json.loads((directory / "preview.json").read_text())["factor"]
            return p, pixels, factor
        def success(result):
            self.project, pixels, factor = result
            self.built, self.keyed_ready, self.dirty = True, True, True
            self._sync_controls()
            self.sprite_view.project = self.project
            self.sprite_view.set_image(pixels, factor)
            layout = self.project.layout
            warning_count = sum(bool(f.warnings) for f in self.project.tracking_results)
            self.summary.setText(t('{p0} × {p1} px / cell\n{p2} frames · {p3} warnings', p0=layout.width, p1=layout.height, p2=self.project.output_count, p3=warning_count))
            if self.project.is_passthrough:
                text = t("Cell {width} × {height}\nPassthrough: tracking and alignment skipped.", width=layout.width, height=layout.height)
            elif layout.clipped_frames:
                text = t("FRAME CLIPPING DETECTED\nFrames: {frames}", frames=", ".join(str(i) for i in layout.clipped_frames))
            else:
                text = t("Cell {width} × {height}\nRequired {required_width} × {required_height}\nGround {ground:g}\nNo clipping detected.", width=layout.width, height=layout.height, required_width=layout.required_width, required_height=layout.required_height, ground=layout.ground_baseline)
            self.cell_note.setText(t(text))
            self.context_hint.setText(t(text.replace("\n", " · ")))
            self.status.setText(t("Passthrough sprites ready · preview or export") if self.project.is_passthrough else t("Build complete · review confidence and warnings before export"))
            self._refresh_timeline()
            self.motion_editor.set_frames(self.project.tracking_results)
            self.steps.setCurrentIndex(3)
            self.views.setCurrentIndex(1)
            if callable(after):
                self._resume_after_work = after
        self._run(operation, success, t("Tracking / aligning / building sprites"),animation_task="build")

    def _confirm_discard(self, continuation=None):
        if not self.dirty:
            return True
        answer = QMessageBox.question(self, "Unsaved Project", "The project has unsaved changes. Save before continuing?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save)
        if answer == QMessageBox.StandardButton.Save:
            self._after_save = continuation
            self.save_project()
            return False
        return answer == QMessageBox.StandardButton.Discard

    def _inherits_project(self):
        return bool(self.project_file or self.project.project_name or self.project.character_profile)

    def _project_folder(self, kind):
        return str(self.project_file.parent / kind) if self.project_file else ""

    def new_project(self):
        if self.worker or self.character_editor or self.reference_dialog or self.sequence_dialog or self.new_project_dialog:
            return
        if not self._confirm_discard(self.new_project):
            return
        dialog = NewProjectDialog(self)
        self.new_project_dialog = dialog
        dialog.project_created.connect(self._project_created)
        dialog.project_open_requested.connect(self._open_existing_project)
        dialog.destroyed.connect(self._new_project_closed)
        self.play_timer.stop()
        dialog.show()
        self._update_state()

    def _open_existing_project(self,path):
        self.new_project_dialog=None
        QTimer.singleShot(0,lambda:self.open_project(path,confirmed=True))

    def _new_project_closed(self):
        self.new_project_dialog = None
        self._update_state()

    def _project_created(self, project, path):
        self._cancel_editor_interaction()
        self._invalidate_reviews(False)
        self.project, self.project_file = project, path
        self.cache_dir = cache_directory(project.project_id, path, project.animation_id)
        self.dirty, self.built, self.keyed_ready = False, False, False
        self._loaded()
        self.steps.setCurrentIndex(0)
        self.views.setCurrentWidget(self.start_page)
        self.status.setText(t("Project created"))

    def save_project_as(self):
        if not self.interaction_busy:self.save_project(force_dialog=True)

    def save_project(self, path=None, *, force_dialog=False):
        if self.worker or self.character_editor or self.reference_dialog or self.sequence_dialog or self.new_project_dialog:
            return
        if isinstance(path, bool):
            path = None
        path = None if force_dialog else Path(path) if path else self.project_file
        if not path:
            value, _ = QFileDialog.getSaveFileName(self, "Save Project As" if force_dialog else "Save Project", (self.project_file.name if self.project_file else self.project.project_name or self.project.export_settings.animation_name)+("" if self.project_file else ".aivsprite"), "AI Video to Sprite (*.aivsprite)",purpose="project_save")
            if not value:
                self._after_save = None
                return
            path = Path(value)
        if path.suffix.lower() != ".aivsprite":
            path = path.with_suffix(".aivsprite")
        path = path.resolve()
        self.library_controller.capture()
        project = copy.deepcopy(self.project)
        source_cache = cache_directory(project.project_id, self.project_file)
        target_cache = cache_directory(project.project_id, path)
        active_target = cache_directory(project.project_id, path, project.animation_id)
        def operation(progress, cancel):
            if source_cache.resolve() != target_cache.resolve():
                for animation_id in (project.animation_id, *project.animations):
                    stage_directory = cache_directory(project.project_id, path, animation_id)
                    for stage in ("raw", "key", "root", "motion", "source_align", "align", "final", "sheet", "preview"):
                        (stage_directory / f"{stage}.json").unlink(missing_ok=True)
                # Copy stage outputs first, manifests last. A cancellation never publishes partial stages.
                files = list(source_cache.rglob("*"))
                files = sorted((p for p in files if p.is_file()), key=lambda p: p.suffix == ".json")
                for i, source in enumerate(files):
                    copy_file(source, target_cache / source.relative_to(source_cache), cancel)
                    progress(i+1, len(files), "Saving project cache")
            project.save(path)
            return path, active_target
        def success(result):
            self.project_file, self.cache_dir = result
            self._remember_path("project_save",self.project_file,file=True)
            self.dirty = False
            self.status.setText(t('Saved {p0}', p0=self.project_file.name))
            self._update_title()
            self._resume_after_work = self._after_save
            self._after_save = None
        self._run(operation, success, t("Saving project"))

    def open_project(self, path=None, *, confirmed=False):
        if self.interaction_busy or not confirmed and not self._confirm_discard(lambda: self.open_project(path)):
            return
        if isinstance(path, bool):
            path = None
        if not path:
            value, _ = QFileDialog.getOpenFileName(self, "Open Project", "", "AI Video to Sprite (*.aivsprite)",purpose="project_open")
            if not value:
                return
            path = Path(value)
        path = Path(path).resolve()
        try:
            project = Project.load(path)
        except Exception as error:
            self._failed(str(error))
            return
        self._cancel_editor_interaction()
        self.editor.pause_preview();self._invalidate_reviews(False)
        self.project,self.project_file=project,path
        self.cache_dir=cache_directory(project.project_id,path,project.animation_id)
        self._remember_path('project_open',path,file=True)
        self.dirty=False
        self.library_controller.select_group(project.current_group_id,capture=False)
        if project.input_mode!='frame_sequence' and project.source_path and not project.video.frame_count:
            self._verify_source_metadata(project);return
        self.status.setText(t('Workspace restored from cache. Missing results require explicit processing.'))

    def _verify_source_metadata(self,project):
        """Script-authored or legacy projects may store no video info; re-read the source once so cached stages stay reachable."""
        directory=self.cache_dir
        def operation(progress,cancel):
            Pipeline(project,directory,progress,cancel).import_input(auto_color=False)
            return project
        def success(p):
            self._invalidate_reviews(False)
            self.project=p
            self.built,self.keyed_ready=False,p.input_mode=='frame_sequence'
            self._loaded()
            self.steps.setCurrentIndex(3 if p.is_passthrough else 2 if p.root_keyframes else 1)
            self.status.setText(t('Project restored · manual roots retained; Analyze / Build reuses valid cache'))
        self._run(operation,success,t('Opening project / verifying source cache'))

    def choose_export(self, kind="all", godot=False):
        if self.interaction_busy or not self.project.video.frame_count:
            return
        if self.project.is_passthrough and kind != "rgba" and not self.built:
            self.build_sprites(after=lambda: self.choose_export(kind, godot))
            return
        if kind != "rgba" and not self.built:
            self.context_hint.setText(t("Settings changed or sprites are not built. Analyze / Build before exporting."))
            self.steps.setCurrentIndex(3)
            return
        allow_clipping = False
        if kind != "rgba" and self.project.layout.clipped_frames:
            frames = ", ".join(str(i) for i in self.project.layout.clipped_frames[:50])
            answer = QMessageBox.warning(self, "FRAME CLIPPING DETECTED", t('Clipped frames: {p0}\nUse AUTO or a larger cell to preserve them. Export this clipped result?', p0=frames),
                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
            allow_clipping = True
        title="Export Godot Bundle" if godot else {"all":"Export Sprite Bundle","sheet":"Export Sprite Sheet","frames":"Export PNG Sequence","rgba":"Export RGBA Frames"}[kind]
        parent = QFileDialog.getExistingDirectory(self,title,self._project_folder("exports"),purpose=self.export_purpose(kind,godot))
        if not parent:
            return
        name = re.sub(r"[^\w.-]+", "_", self.project.export_settings.animation_name, flags=re.UNICODE).strip(" ._")[:60] or "animation"
        destination = Path(parent) / f"{name}-{datetime.now():%Y%m%d-%H%M%S}"
        number = 1
        while destination.exists():
            destination = Path(parent) / f"{name}-{datetime.now():%Y%m%d-%H%M%S}-{number}"
            number += 1
        self.export_to(destination, kind, godot, allow_clipping)

    def export_to(self, destination, kind="all", godot=False, allow_clipping=False):
        p = copy.deepcopy(self.project)
        directory = self.cache_dir
        def operation(progress, cancel):
            return export_images(Pipeline(p, directory, progress, cancel), Path(destination), kind, godot, allow_clipping)
        def success(result):
            if kind != "rgba" and self.project.library.animation(p.animation_id):
                self.project=self.project.merge_animation_result(p)
                self.project.library.mark_generated(p.animation_id,True)
                self.built,self.keyed_ready,self.dirty=True,True,True
                with Image.open(directory/'sheet_preview.png') as image:pixels=np.array(image.convert('RGBA'))
                factor=json.loads((directory/'preview.json').read_text())['factor']
                self.sprite_view.project=self.project;self.sprite_view.set_image(pixels,factor)
                self._refresh_timeline()
            self.last_export = result
            self._remember_path(self.export_purpose(kind,godot),Path(result).parent)
            self.status.setText(t('Export complete: {p0}', p0=result))
            self.context_hint.setText(t('Exported to {p0}', p0=result))
            if kind != "rgba":
                self._export_notice(result)
        self._run(operation, success, t("Exporting sprites"))

    def show_diagnostics(self):
        from app.utils.ffmpeg import executable
        dialog = QDialog(self)
        dialog.setWindowTitle(t("Diagnostics"))
        dialog.resize(840, 560)
        layout = QVBoxLayout(dialog)
        view = QPlainTextEdit()
        view.setReadOnly(True)
        layout.addWidget(view)
        def refresh():
            tools = []
            for name in ("ffmpeg", "ffprobe"):
                try:
                    tools.append(f"{name}: {executable(name)}")
                except RuntimeError as error:
                    tools.append(str(error))
            content = self.log_path.read_text(encoding="utf-8", errors="replace")[-60000:] if self.log_path.exists() else t("No log entries.")
            view.setPlainText("\n".join(tools) + t("\nCache: {cache}\nLog: {log}\n\n", cache=self.cache_dir, log=self.log_path) + content)
            view.verticalScrollBar().setValue(view.verticalScrollBar().maximum())
        layout.addWidget(self._button("Refresh", refresh))
        refresh()
        dialog.exec()

    def dragEnterEvent(self, event):
        if self.library_controller.can_import and not self.worker and not self.new_project_dialog and event.mimeData().hasUrls():
            paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
            if any(p.is_dir() or p.suffix.lower() in SUPPORTED_EXTENSIONS | {".aivsprite"} for p in paths):
                event.acceptProposedAction()

    def dropEvent(self, event):
        if not self.library_controller.require_group():event.ignore();return
        for url in event.mimeData().urls():
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if path.is_dir():
                self.import_sequence(path)
                event.acceptProposedAction()
                break
            if path.suffix.lower() == ".aivsprite":
                self.open_project(path)
                event.acceptProposedAction()
                break
            if path.suffix.lower() in SUPPORTED_EXTENSIONS:
                self.import_video(path)
                event.acceptProposedAction()
                break

    def closeEvent(self, event: QCloseEvent):
        self.editor.pause_preview()
        if self.worker:
            answer = QMessageBox.question(self, "Processing", "Cancel the current operation and close after it stops?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer == QMessageBox.StandardButton.Yes:
                self._close_after_work = True
                self.cancel_work()
            event.ignore()
            return
        if not self._confirm_discard(self.close):
            event.ignore()
            return
        self.play_timer.stop()
        if self.reference_dialog:
            self.reference_dialog.close()
        if self.sequence_dialog:
            self.sequence_dialog.close()
        if self.new_project_dialog:
            self.new_project_dialog.close()
        for review in list(self.review_windows):
            review.close()
        self.preview_timer.stop()
        if self.preview_worker:
            self.preview_worker.cancel()
            self.preview_worker.wait()
        event.accept()


def _with_edit_history(method):
    def tracked(self,*args,**kwargs):
        before=self._edit_snapshot()
        result=method(self,*args,**kwargs)
        after=self._edit_snapshot()
        if before!=after:
            self._history().record(before,after,method.__name__)
            self._update_state()
            self._refresh_editor()
        return result
    return tracked

for _method in ('_set_root','delete_root','_setting_changed','_set_roi','_clear_roi','_save_character_profile','_apply_color','_normalize_preset','enable_full_processing'):
    setattr(MainWindow,_method,_with_edit_history(getattr(MainWindow,_method)))
