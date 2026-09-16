from __future__ import annotations

import json
import math
import os
import uuid
import copy
from fractions import Fraction
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.models.frame_data import CellLayout, FrameData
from app.models.character_profile import CharacterProfile
from app.models.timeline_edit import TimelineEdit
from app.models.character_reference import CharacterReference, AnimationTransform
from app.models.project_library import ProjectLibrary

ALIGNMENT_MODES = ("ROOT XY LOCK", "GROUND LOCK", "ROOT X + GROUND Y")
PROJECT_FIELDS = ("project_name", "project_version", "project_type", "default_fps", "source_canvas", "output_canvas",
                  "project_canvas_width", "project_canvas_height", "canvas_fit_mode", "character_reference")
PROJECT_STATE_FIELDS = ("library", "current_group_id")


@dataclass
class ChromaSettings:
    green_color: tuple[int, int, int] = (0, 255, 0)
    tolerance: float = 0.22
    softness: float = 0.16
    edge_feather: float = 0.6
    spill_suppression: bool = True
    despill_strength: float = 0.85
    minimum_alpha: int = 4
    noise_removal: int = 12
    morphology: int = 0


@dataclass
class TrackingSettings:
    roi_size: int = 0
    min_confidence: float = 0.35
    max_features: int = 100
    estimation: str = "affine"
    body_roi: tuple[float, float, float, float] | None = None
    fallback: bool = True


@dataclass
class MotionSettings:
    enabled: bool = False
    preset: str = "idle"
    x_policy: str = "LOCK"
    y_policy: str = "GROUND_LOCK"
    smoothing_window: int = 7
    spike_threshold: float = 8.0
    loop_correction: bool = False
    takeoff_frame: int = -1
    apex_frame: int = -1
    landing_frame: int = -1
    ground_roi: tuple[float, float, float, float] | None = None
    roi_reference_root: tuple[float, float] | None = None


@dataclass
class SpriteSettings:
    mode: str = "AUTO"
    width: int = 512
    height: int = 512
    round_up: int = 0
    padding: int = 16
    bottom_margin: int = 16
    alpha_threshold: int = 16
    min_component_size: int = 12
    canvas_mode: str = "auto_bounds"
    target_width: int = 512
    target_height: int = 512
    preserve_aspect_ratio: bool = True


@dataclass
class ExportSettings:
    animation_name: str = "animation"
    columns: int = 8
    loop: bool = True


@dataclass
class VideoInfo:
    width: int = 0
    height: int = 0
    fps: float = 0.0
    fps_rational: str = "0/1"
    frame_count: int = 0
    duration: float = 0.0


@dataclass
class Project:
    schema_version: int = 1
    project_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    source_video: str = ""
    video: VideoInfo = field(default_factory=VideoInfo)
    chroma_key_settings: ChromaSettings = field(default_factory=ChromaSettings)
    root_keyframes: dict[int, tuple[float, float]] = field(default_factory=dict)
    tracking_settings: TrackingSettings = field(default_factory=TrackingSettings)
    motion_settings: MotionSettings = field(default_factory=MotionSettings)
    tracking_results: list[FrameData] = field(default_factory=list)
    alignment_mode: str = ALIGNMENT_MODES[2]
    sprite_cell: SpriteSettings = field(default_factory=SpriteSettings)
    scale: float = 1.0
    lock_character_scale: bool = True
    export_settings: ExportSettings = field(default_factory=ExportSettings)
    layout: CellLayout | None = None
    character_profile: CharacterProfile | None = None
    animation_id: str = "default"
    animations: dict[str, dict] = field(default_factory=dict)
    input_mode: str = "video"
    sequence_folder: str = ""
    sequence_fps: float = 24.0
    passthrough_alignment: bool = False
    sequence_size_policy: str = "strict"
    sequence_files: list[str] = field(default_factory=list)
    sequence_sizes: list[list[int]] = field(default_factory=list)
    sequence_alpha: str = "RGBA"
    sequence_formats: list[dict] = field(default_factory=list)
    project_name: str = ""
    project_version: str = "0.4"
    project_type: str = "character_animation"
    default_fps: float = 24.
    source_canvas: tuple[int, int] = (1536, 1536)
    output_canvas: tuple[int, int] = (512, 512)
    processing_mode: str = "full"
    full_processing_canvas_mode: str = "auto_bounds"
    project_canvas_width: int = 0
    project_canvas_height: int = 0
    canvas_fit_mode: str = "none"
    original_size: tuple[int, int] = (0, 0)
    character_reference: CharacterReference | None = None
    animation_transform: AnimationTransform = field(default_factory=AnimationTransform)
    timeline_edit: TimelineEdit = field(default_factory=TimelineEdit)
    final_frames: list[FrameData] = field(default_factory=list)
    final_timing: list[dict] = field(default_factory=list)
    library: ProjectLibrary = field(default_factory=ProjectLibrary)
    current_group_id: str | None = None

    @property
    def has_final_edits(self):
        return self.timeline_edit.enabled or self.animation_transform.active

    @property
    def output_frames(self):
        return self.final_frames if self.has_final_edits else self.tracking_results

    @property
    def output_count(self):
        return len(self.final_timing) if self.has_final_edits else self.video.frame_count


    @property
    def project_canvas(self):
        if self.canvas_fit_mode == "center_crop_or_pad":
            return self.project_canvas_width, self.project_canvas_height
        return None

    def project_metadata(self):
        return {name: copy.deepcopy(getattr(self, name)) for name in PROJECT_FIELDS}

    def project_context(self):
        return {**self.project_metadata(), **{name: copy.deepcopy(getattr(self, name)) for name in PROJECT_STATE_FIELDS}}

    @property
    def is_passthrough(self):
        return self.is_keyed_passthrough or self.input_mode == "frame_sequence" and self.passthrough_alignment

    @property
    def is_keyed_passthrough(self):
        return self.input_mode == "video" and self.processing_mode == "keyed_passthrough"

    def set_processing_mode(self, mode):
        if self.input_mode != "video" or mode not in ("full", "keyed_passthrough"):
            raise ValueError("Invalid video processing mode")
        if mode == self.processing_mode:
            return
        if mode == "keyed_passthrough":
            self.full_processing_canvas_mode = self.sprite_cell.canvas_mode
            # A prior auto-selected 1536→512 preset is not consent to resize here.
            self.sprite_cell.canvas_mode = "source_canvas"
        else:
            self.sprite_cell.canvas_mode = self.full_processing_canvas_mode
        self.processing_mode = mode
        self.layout = None
        self.tracking_results = []

    @property
    def source_path(self):
        return self.sequence_folder if self.input_mode == "frame_sequence" else self.source_video

    def sync_sequence_timing(self):
        if self.input_mode == "frame_sequence":
            self.video.fps = float(self.sequence_fps)
            self.video.fps_rational = str(Fraction(str(self.sequence_fps)).limit_denominator(100000))
            self.video.duration = self.video.frame_count / self.sequence_fps

    def validate(self) -> None:
        self.library.validate()
        if self.current_group_id is not None and self.current_group_id not in self.library.groups:
            raise ValueError("Selected Group does not exist")
        self.timeline_edit.validate(self.video.frame_count)
        AnimationTransform.from_dict(self.animation_transform)
        if self.character_reference:self.character_reference.validate()
        if self.canvas_fit_mode not in ("none", "center_crop_or_pad"):
            raise ValueError("Invalid project canvas fit mode")
        if not self.project_canvas and (self.project_canvas_width, self.project_canvas_height) != (0, 0):
            raise ValueError("Invalid project canvas dimensions")
        if self.project_type != "character_animation":
            raise ValueError("Unsupported project type")
        if not math.isfinite(self.default_fps) or not .1 <= self.default_fps <= 240:
            raise ValueError("Default animation FPS must be between 0.1 and 240")
        for canvas in (self.source_canvas, self.output_canvas, *((self.project_canvas,) if self.project_canvas else ())):
            if len(canvas) != 2 or not all(isinstance(v, int) and 1 <= v <= 16384 for v in canvas) or canvas[0] * canvas[1] > 64_000_000:
                raise ValueError("Invalid project canvas dimensions")
        if self.input_mode not in ("video", "frame_sequence"):
            raise ValueError("Invalid input mode")
        if self.processing_mode not in ("full", "keyed_passthrough") or self.processing_mode == "keyed_passthrough" and self.input_mode != "video":
            raise ValueError("Invalid video processing mode")
        if self.full_processing_canvas_mode not in ("auto_bounds", "normalize_source", "source_canvas"):
            raise ValueError("Invalid normalization settings")
        if not math.isfinite(self.sequence_fps) or not .1 <= self.sequence_fps <= 240:
            raise ValueError("Animation FPS must be between 0.1 and 240")
        if self.sequence_size_policy not in ("strict", "pad"):
            raise ValueError("Invalid sequence canvas policy")
        if (self.input_mode == "frame_sequence" and self.passthrough_alignment) != (self.alignment_mode == "passthrough"):
            raise ValueError("Sequence passthrough settings are inconsistent")
        if self.character_profile:
            self.character_profile.validate()
        for key in (self.animation_id, *self.animations):
            if key != "default" and (len(key) != 32 or any(c not in "0123456789abcdef" for c in key)):
                raise ValueError("Invalid animation identifier")
        if any("character_profile" in data or "character_reference" in data or "animations" in data for data in self.animations.values()):
            raise ValueError("Character Profile must be stored once per project")
        if self.schema_version != 1:
            raise ValueError("Unsupported project schema version")
        if len(self.project_id) != 32 or any(c not in "0123456789abcdef" for c in self.project_id):
            raise ValueError("Invalid project identifier")
        if self.alignment_mode not in (*ALIGNMENT_MODES, "passthrough"):
            raise ValueError("Invalid alignment mode")
        if not 0.1 <= self.scale <= 4.0:
            raise ValueError("Scale must be between 10% and 400%")
        if not 1 <= self.export_settings.columns <= 256:
            raise ValueError("Columns must be between 1 and 256")
        s, c, t = self.sprite_cell, self.chroma_key_settings, self.tracking_settings
        m = self.motion_settings
        if s.canvas_mode not in ("auto_bounds", "normalize_source", "source_canvas") or not all(1 <= n <= 16384 for n in (s.target_width, s.target_height)):
            raise ValueError("Invalid normalization settings")
        if t.estimation not in ("affine", "translation"):
            raise ValueError("Invalid tracking estimation mode")
        if m.x_policy not in ("LOCK", "PRESERVE", "EXTRACT") or m.y_policy not in ("LOCK", "GROUND_LOCK", "PRESERVE", "EXTRACT"):
            raise ValueError("Invalid motion policy")
        if not 1 <= m.smoothing_window <= 51 or not 0 < m.spike_threshold <= 1000:
            raise ValueError("Invalid trajectory filter settings")
        phases = (m.takeoff_frame, m.apex_frame, m.landing_frame)
        if any(v < -1 or (self.video.frame_count and v >= self.video.frame_count) for v in phases):
            raise ValueError("Jump phase frame is out of range")
        present = [v for v in phases if v >= 0]
        if present != sorted(present):
            raise ValueError("Jump phases must be ordered: takeoff, apex, landing")
        for roi in (m.ground_roi, t.body_roi):
            if roi is not None and (len(roi) != 4 or not all(math.isfinite(v) for v in roi) or roi[2] <= roi[0] or roi[3] <= roi[1]):
                raise ValueError("Invalid body or ground ROI")
        if s.mode not in ("AUTO", "256x256", "512x512", "1024x1024", "CUSTOM"):
            raise ValueError("Invalid cell mode")
        if not all(1 <= n <= 16384 for n in (s.width, s.height)):
            raise ValueError("Cell dimensions must be between 1 and 16384")
        if not (0 <= s.padding <= 1024 and 0 <= s.bottom_margin <= 1024):
            raise ValueError("Invalid padding or bottom margin")
        if s.round_up not in (0, 32, 64, 128, 256):
            raise ValueError("Invalid rounding increment")
        if not 0 <= s.alpha_threshold <= 254 or not 0 <= s.min_component_size <= 100000:
            raise ValueError("Invalid alpha bounds settings")
        if len(c.green_color) != 3 or not all(0 <= x <= 255 for x in c.green_color):
            raise ValueError("Invalid key color")
        if not all(0 <= x <= 1 for x in (c.tolerance, c.softness, c.despill_strength)):
            raise ValueError("Invalid chroma key settings")
        if not (0 <= c.edge_feather <= 10 and 0 <= c.minimum_alpha <= 254 and 0 <= c.noise_removal <= 100000 and 0 <= c.morphology <= 5):
            raise ValueError("Invalid alpha cleanup settings")
        if t.roi_size not in (0, 64, 96, 128, 192, 256) or not 0 <= t.min_confidence <= 1 or not 3 <= t.max_features <= 500:
            raise ValueError("Invalid tracking settings")
        for index, point in self.root_keyframes.items():
            if index < 0 or (self.video.frame_count and index >= self.video.frame_count) or len(point) != 2 or not all(math.isfinite(v) for v in point):
                raise ValueError("Invalid root keyframe")

    def save(self, path: Path) -> None:
        self.ensure_library()
        self.validate()
        self.sync_sequence_timing()
        path = Path(path).resolve()
        data = asdict(self)
        for animation in (data, *data["animations"].values()):
            for field_name in ("source_video", "sequence_folder"):
                if animation.get(field_name):
                    try:
                        animation[field_name] = os.path.relpath(animation[field_name], path.parent)
                    except ValueError:
                        pass
        for resource in data["library"]["resources"].values():
            if resource.get("path"):
                try:
                    resource["path"] = os.path.relpath(resource["path"], path.parent)
                except ValueError:
                    pass
        data.update(fps=self.video.fps, frame_count=self.video.frame_count,
                    green_color=list(self.chroma_key_settings.green_color), padding=self.sprite_cell.padding)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        temp.replace(path)

    @classmethod
    def load(cls, path: Path) -> Project:
        path = Path(path).resolve()
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("animations") == []:
            data["animations"] = {}
        for animation in (data, *data.get("animations", {}).values()):
            for field_name in ("source_video", "sequence_folder"):
                if animation.get(field_name):
                    animation[field_name] = str((path.parent / animation[field_name]).resolve())
        for resource in data.get("library", {}).get("resources", {}).values():
            if resource.get("path"):
                resource["path"] = str((path.parent / resource["path"]).resolve())
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data):
        data = copy.deepcopy(data)
        legacy_library = "library" not in data
        data["library"] = ProjectLibrary.from_dict(data.get("library"))
        if data.get("animations") == []:
            data["animations"] = {}
        for name in ("source_canvas", "output_canvas", "original_size"):
            if name in data:
                data[name] = tuple(data[name])
        if data.get("input_mode") == "frame_sequence":
            data.setdefault("passthrough_alignment", data.get("alignment_mode", "passthrough") == "passthrough")
            if data["passthrough_alignment"]:
                data["alignment_mode"] = "passthrough"
        for name in ("fps", "frame_count", "green_color", "padding"):
            data.pop(name, None)
        data["video"] = VideoInfo(**data.get("video", {}))
        for name, model in (("chroma_key_settings", ChromaSettings), ("sprite_cell", SpriteSettings),
                            ("export_settings", ExportSettings), ("tracking_settings", TrackingSettings), ("motion_settings", MotionSettings)):
            data[name] = model(**data.get(name, {}))
        data["root_keyframes"] = {int(k): tuple(v) for k, v in data.get("root_keyframes", {}).items()}
        data["tracking_results"] = [FrameData(**v) for v in data.get("tracking_results", [])]
        data["final_frames"] = [FrameData(**v) for v in data.get("final_frames", [])]
        data["timeline_edit"] = TimelineEdit.from_dict(data.get("timeline_edit"))
        data["character_reference"] = CharacterReference.from_dict(data.get("character_reference"))
        data["animation_transform"] = AnimationTransform.from_dict(data.get("animation_transform"))
        data["layout"] = CellLayout(**data["layout"]) if data.get("layout") else None
        data["character_profile"] = CharacterProfile.from_dict(data["character_profile"]) if data.get("character_profile") else None
        project = cls(**data)
        if legacy_library:
            project.ensure_library()
        if project.is_keyed_passthrough and project.sprite_cell.canvas_mode == "auto_bounds":
            project.sprite_cell.canvas_mode = "source_canvas"
        project.validate()
        project.sync_sequence_timing()
        return project

    def animation_snapshot(self):
        data = asdict(self)
        for key in ("schema_version", "project_id", "character_profile", "animation_id", "animations", *PROJECT_FIELDS, *PROJECT_STATE_FIELDS):
            data.pop(key)
        return data

    def import_animation(self, path: Path):
        """Add an animation without cloning or re-deriving the character reference."""
        archive = copy.deepcopy(self.animations)
        if self.source_path:
            archive[self.animation_id] = self.animation_snapshot()
        result = Project(project_id=self.project_id, source_video=str(path.resolve()), character_profile=self.character_profile,
                         animation_id=uuid.uuid4().hex, animations=archive, **self.project_context())
        result.chroma_key_settings = copy.deepcopy(self.chroma_key_settings)
        result.motion_settings.enabled = True
        result.export_settings.animation_name = path.stem
        result.sequence_fps = self.default_fps
        if self.project_name:
            result.sprite_cell.canvas_mode = "normalize_source"
            result.sprite_cell.target_width, result.sprite_cell.target_height = self.output_canvas
            result.scale = self.scale
        if self.character_profile:
            result.sprite_cell.canvas_mode = "normalize_source"
            result.sprite_cell.target_width, result.sprite_cell.target_height = self.character_profile.canvas_size
        if self.character_reference:
            result.set_processing_mode("keyed_passthrough")
        if result.current_group_id in result.library.groups:
            resource = result.library.add_source_animation(result.current_group_id, result.animation_id,
                result.export_settings.animation_name, result.source_video, "SOURCE_VIDEO")
            result.export_settings.animation_name = resource.name
        return result

    def import_frame_sequence(self, folder: Path, fps=None, passthrough=True, size_policy="strict"):
        result = self.import_animation(folder)
        result.source_video = ""
        result.input_mode = "frame_sequence"
        result.processing_mode = "full"
        result.sequence_folder = str(folder.resolve())
        result.sequence_fps = float(self.default_fps if fps is None else fps)
        result.sequence_size_policy = size_policy
        owner = result.library.animation(result.animation_id)
        if owner:
            source = result.library.resources[owner.source_id]
            source.kind, source.path = "SOURCE_SEQUENCE", result.sequence_folder
        result.passthrough_alignment = bool(passthrough)
        if passthrough:
            result.alignment_mode = "passthrough"
            result.motion_settings.enabled = False
            result.sprite_cell.canvas_mode = "source_canvas"
        return result

    def select_animation(self, animation_id):
        if animation_id == self.animation_id:
            return copy.deepcopy(self)
        archive = copy.deepcopy(self.animations)
        selected = archive.pop(animation_id)
        if self.source_path:
            archive[self.animation_id] = self.animation_snapshot()
        selected.update(project_id=self.project_id, animation_id=animation_id, animations=archive,
                        character_profile=asdict(self.character_profile) if self.character_profile else None, **self.project_context())
        result = Project.from_dict(selected)
        owner = result.library.animation(animation_id)
        if owner:
            result.current_group_id = owner.group_id
        return result


    def all_animation_snapshots(self):
        result = copy.deepcopy(self.animations)
        if self.source_path:
            result[self.animation_id] = self.animation_snapshot()
        return result

    def ensure_library(self):
        """Migrate legacy content without changing animation parameters or cache IDs."""
        snapshots = self.all_animation_snapshots()
        if not snapshots:
            return
        if not self.library.groups:
            group = self.library.add_group("Imported Animations")
            self.current_group_id = group.id
        fallback = self.current_group_id if self.current_group_id in self.library.groups else next(iter(self.library.groups))
        for ident, data in snapshots.items():
            if self.library.animation(ident):
                continue
            sequence = data.get("input_mode") == "frame_sequence"
            path = data.get("sequence_folder" if sequence else "source_video", "")
            if not path:
                continue
            self.library.add_source_animation(fallback, ident,
                data.get("export_settings", {}).get("animation_name", "Animation"), path,
                "SOURCE_SEQUENCE" if sequence else "SOURCE_VIDEO")
            if data.get("layout"):
                self.library.mark_generated(ident)
        active = self.library.animation(self.animation_id) if self.source_path else None
        if active:
            self.current_group_id = active.group_id
            if not self.library.groups[active.group_id].ui_state.animation_id:
                self.library.groups[active.group_id].ui_state.animation_id = self.animation_id

    def empty_context(self, group_id=None):
        """Keep every animation while showing an empty Group or the Project Root."""
        result = Project(project_id=self.project_id, character_profile=self.character_profile,
                         animations=self.all_animation_snapshots(), **self.project_context())
        result.current_group_id = group_id
        return result

    def merge_animation_result(self, result):
        """Commit only the task's animation; project-wide state remains authoritative."""
        if result.project_id != self.project_id:
            raise ValueError("Background task belongs to another Project")
        if self.library.animation(result.animation_id) is None:
            raise ValueError("Background task Animation no longer exists")
        if result.animation_id == self.animation_id and self.source_path:
            data = asdict(self)
            data.update(result.animation_snapshot())
            return Project.from_dict(data)
        self.animations[result.animation_id] = result.animation_snapshot()
        return self
