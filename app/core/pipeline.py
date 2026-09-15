from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import logging
from pathlib import Path

from app.core.chroma_key import chroma_key, estimate_background
from app.core.root_tracker import RootTracker
from app.core.ground_detection import detect_ground
from app.core.motion import process_motion, review_warnings
from app.core.character_space import apply_character_motion, review_reference_bounds, character_transform
from app.core.final_canvas import source_corrections, normalized_layout, normalize_frame, motion_auto_layout
from app.core.alignment import warp_rgba
from app.core.alpha_utils import alpha_bbox
from app.core.frame_sequence import sequence_paths, scan_sequence, read_sequence_frame
from app.core.canvas_normalizer import canvas_transform, normalize_canvas
from app.core.canvas_fit import CanvasFit
from app.core.sprite_canvas import calculate_layout, render_cell
from app.core.sprite_sheet import build_sheet, sheet_preview
from app.core.video_decoder import decode_video, probe_video
from app.models.frame_data import CellLayout, FrameData
from app.models.project import Project, VideoInfo
from app.utils.cache import FrameCache, save_rgba
from app.utils.rgba_image import to_rgba8, read_rgba
from app.utils.ffmpeg import check_cancel
from app.utils.paths import frame_path

log = logging.getLogger("aivsprite.pipeline")
PIPELINE_VERSION = 3


def signature(*values) -> str:
    payload = json.dumps((PIPELINE_VERSION, values), sort_keys=True, ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


class Pipeline:
    """Single-worker orchestrator. A completed manifest is the only cache authority."""

    def __init__(self, project: Project, cache_dir: Path, progress=lambda n, total, message: None, cancel=None):
        self.project, self.cache_dir = project, Path(cache_dir)
        self.progress, self.cancel = progress, cancel
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache = FrameCache(96 * 1024 * 1024)
        self.raw = self.cache_dir / "raw_frames"
        self.decoded = self.cache_dir / "decoded_frames"
        self.keyed = self.raw if project.input_mode == "frame_sequence" else self.cache_dir / "keyed_frames"
        self.aligned = self.cache_dir / "aligned_frames"
        self.source_aligned = self.cache_dir / "source_aligned_frames"
        self.sheet = self.cache_dir / "sprite_sheet.png"

    def _manifest(self, stage: str):
        path = self.cache_dir / f"{stage}.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _commit(self, stage: str, sig: str, **data):
        check_cancel(self.cancel)
        path = self.cache_dir / f"{stage}.json"
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps({"signature": sig, **data}, allow_nan=False), encoding="utf-8")
        temp.replace(path)
        log.info("Completed stage %s (%s)", stage, sig[:12])

    def _invalidate(self, stage: str):
        (self.cache_dir / f"{stage}.json").unlink(missing_ok=True)

    def _files_valid(self, directory: Path, count: int) -> bool:
        for index in range(count):
            check_cancel(self.cancel)
            if not frame_path(directory, index).is_file():
                return False
        return count > 0

    def raw_signature(self):
        base = self.input_signature()
        return signature(base, "project_canvas_fit_v1", self.project.project_canvas) if self.project.project_canvas else base

    def input_signature(self):
        if self.project.input_mode == "frame_sequence":
            paths = sequence_paths(self.project.sequence_folder)
            identities = [(p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in paths]
            return signature("frame_sequence_v2_depth", str(Path(self.project.sequence_folder).resolve()), identities, self.project.sequence_size_policy)
        path = Path(self.project.source_video)
        stat = path.stat()
        return signature(str(path.resolve()), stat.st_size, stat.st_mtime_ns)

    def key_signature(self):
        if self.project.input_mode == "frame_sequence":
            return signature(self.raw_signature(), "already_keyed_rgba")
        return signature(self.raw_signature(), asdict(self.project.chroma_key_settings))

    def root_signature(self):
        p = self.project
        return signature(self.key_signature(), p.root_keyframes, asdict(p.tracking_settings),
                         p.sprite_cell.alpha_threshold, p.sprite_cell.min_component_size)

    def align_signature(self):
        p = self.project
        if p.is_passthrough:
            s = p.sprite_cell
            transform = (s.target_width, s.target_height, s.preserve_aspect_ratio) if s.canvas_mode == "normalize_source" else None
            if p.is_keyed_passthrough:
                return signature(self.key_signature(), "keyed_passthrough_v1", transform)
            return signature(self.raw_signature(), "passthrough_v1", transform)
        return signature(self.motion_signature(), p.alignment_mode, asdict(p.sprite_cell), p.scale, p.export_settings.loop)

    def motion_signature(self):
        profile = self.project.character_profile
        inputs = (self.root_signature(), asdict(self.project.motion_settings), profile.transform_key() if profile else None)
        return signature(*inputs, self.project.sequence_fps) if self.project.input_mode == "frame_sequence" else signature(*inputs)

    def final_signature(self):
        p = self.project
        base=signature(self.align_signature(),asdict(p.timeline_edit),p.video.fps,p.export_settings.loop,"editor_v1") if p.timeline_edit.enabled else self.align_signature()
        return signature(base,"animation_offset_v1",asdict(p.animation_transform)) if p.animation_transform.active else base

    def sheet_signature(self):
        return signature(self.final_signature(), self.project.export_settings.columns)

    def ensure_final(self):
        self.ensure_aligned()
        p = self.project
        if not p.has_final_edits:
            p.final_frames, p.final_timing = [], []
            return
        from app.core.timeline_renderer import compile_final_timing, render_timeline_frame
        p.timeline_edit.validate(p.video.frame_count)
        timing = compile_final_timing(p)
        if not timing:
            raise ValueError("Timeline has no visible frames")
        sig = self.final_signature()
        folder = self.cache_dir / "final_frames"
        cached = self._manifest("final")
        if cached.get("signature") == sig and self._files_valid(folder, len(timing)):
            p.final_frames = [FrameData(**f) for f in cached['frames']]
            p.final_timing = cached['timing']
        else:
            self._invalidate("final")
            frames = []
            for index, item in enumerate(timing):
                check_cancel(self.cancel)
                pixels, frame = render_timeline_frame(p, item, lambda i: self.cache.read(frame_path(self.aligned, i)), index, lambda i:self.cache.read(frame_path(self.keyed,i)))
                save_rgba(frame_path(folder, index), pixels)
                frames.append(frame)
                self.progress(index+1, len(timing), "Rendering timeline frames")
            review_warnings(frames, p.export_settings.loop, root_tracked=not p.is_passthrough)
            self._commit("final", sig, frames=[asdict(f) for f in frames], timing=timing)
            p.final_frames, p.final_timing = frames, timing
        p.layout.clipped_frames = [f.index for f in p.final_frames if 'Clipping' in f.warnings]


    def ensure_raw(self):
        if self.project.input_mode == "frame_sequence":
            return self.ensure_sequence_raw()
        if self.project.project_canvas:
            return self.ensure_video_canvas()
        sig = self.raw_signature()
        cached = self._manifest("raw")
        if cached.get("signature") == sig and self._files_valid(self.raw, cached["video"]["frame_count"]):
            self.project.video = VideoInfo(**cached["video"])
            return
        self._invalidate("raw")
        info = probe_video(Path(self.project.source_video), self.cancel)
        self.raw.mkdir(parents=True, exist_ok=True)
        # Only generated frames inside this project's raw cache are removed.
        for path in self.raw.glob("frame_*.png"):
            check_cancel(self.cancel)
            path.unlink()
        info.frame_count = decode_video(Path(self.project.source_video), self.raw, info, self.progress, self.cancel)
        self.project.video = info
        self._commit("raw", sig, video=asdict(info))

    def ensure_decoded(self):
        """Keep original video pixels separate from the project's working canvas."""
        sig = self.input_signature()
        cached = self._manifest("decoded")
        if cached.get("signature") == sig and self._files_valid(self.decoded, cached["video"]["frame_count"]):
            return VideoInfo(**cached["video"])
        self._invalidate("decoded")
        info = probe_video(Path(self.project.source_video), self.cancel)
        self.decoded.mkdir(parents=True, exist_ok=True)
        info.frame_count = decode_video(Path(self.project.source_video), self.decoded, info, self.progress, self.cancel)
        self.cache.clear()
        self._commit("decoded", sig, video=asdict(info))
        return info

    def ensure_video_canvas(self):
        p = self.project
        p.validate()
        info = self.ensure_decoded()
        p.original_size = (info.width, info.height)
        sig, cached = self.raw_signature(), self._manifest("raw")
        if cached.get("signature") == sig and self._files_valid(self.raw, info.frame_count):
            p.video = VideoInfo(**cached["video"])
            return
        self._invalidate("raw")
        transform = CanvasFit(p.original_size, p.project_canvas)
        first = self.cache.read(frame_path(self.decoded, 0))
        fill = (*estimate_background(first[..., :3]), 255)
        for index in range(info.frame_count):
            check_cancel(self.cancel)
            pixels = self.cache.read(frame_path(self.decoded, index))
            save_rgba(frame_path(self.raw, index), transform.apply(pixels, fill))
            self.progress(index+1, info.frame_count, "Fitting project canvas")
        self.cache.clear()
        info.width, info.height = p.project_canvas
        p.video = info
        self._commit("raw", sig, video=asdict(info), original_size=p.original_size, fill_color=fill)

    def ensure_sequence_raw(self):
        p = self.project
        p.validate()
        sig = self.raw_signature()
        cached = self._manifest("raw")
        if cached.get("signature") == sig and self._files_valid(self.raw, cached["video"]["frame_count"]):
            p.video = VideoInfo(**cached["video"])
            p.sequence_files, p.sequence_sizes, p.sequence_alpha = cached["names"], cached["sizes"], cached["alpha"]
            p.sequence_formats = cached["formats"]
            p.original_size = tuple(p.sequence_sizes[0])
            p.sync_sequence_timing()
            return
        scan = scan_sequence(p.sequence_folder, self.progress, self.cancel)
        if scan.mixed_sizes and p.sequence_size_policy != "pad" and not p.project_canvas:
            raise ValueError("Sequence frame dimensions differ. Cancel or explicitly choose a shared canvas.")
        self._invalidate("raw")
        for index, name in enumerate(scan.names):
            check_cancel(self.cancel)
            if p.project_canvas:
                pixels = read_rgba(Path(scan.folder) / name)
                pixels = CanvasFit((pixels.shape[1], pixels.shape[0]), p.project_canvas).apply(pixels)
            else:
                pixels = read_sequence_frame(Path(scan.folder) / name, scan.canvas_size)
            save_rgba(frame_path(self.raw, index), pixels)
            self.progress(index+1, len(scan.names), "Importing sequence RGBA frames")
        if self.raw_signature() != sig:
            raise ValueError("Sequence images changed during import. Scan the folder again.")
        p.video = VideoInfo(*(p.project_canvas or scan.canvas_size), frame_count=len(scan.names))
        p.original_size = tuple(scan.sizes[0])
        p.sync_sequence_timing()
        p.sequence_files, p.sequence_sizes, p.sequence_alpha = list(scan.names), list(scan.sizes), scan.alpha
        p.sequence_formats = [info.to_dict() for info in scan.formats]
        self._commit("raw", sig, video=asdict(p.video), names=p.sequence_files, sizes=p.sequence_sizes, alpha=p.sequence_alpha, formats=p.sequence_formats)

    def import_sequence(self):
        self.project.validate()
        self.ensure_raw()
        return self.project

    def import_input(self, auto_color=True):
        return self.import_sequence() if self.project.input_mode == "frame_sequence" else self.import_video(auto_color)

    def import_video(self, auto_color=True):
        self.ensure_raw()
        if auto_color:
            first = self.cache.read(frame_path(self.decoded if self.project.project_canvas else self.raw, 0))
            self.project.chroma_key_settings.green_color = estimate_background(first[..., :3])
        return self.project

    def ensure_key(self):
        self.ensure_raw()
        self.project.validate()
        if self.project.input_mode == "frame_sequence":
            return
        sig = self.key_signature()
        count = self.project.video.frame_count
        if self._manifest("key").get("signature") == sig and self._files_valid(self.keyed, count):
            return
        self._invalidate("key")
        for index in range(count):
            check_cancel(self.cancel)
            try:
                raw = self.cache.read(frame_path(self.raw, index))
                save_rgba(frame_path(self.keyed, index), chroma_key(raw[..., :3], self.project.chroma_key_settings))
            except Exception:
                log.exception("Chroma key failed at source frame %06d", index)
                raise
            self.progress(index + 1, count, "Extracting transparent RGBA frames")
        self.cache.clear()
        self._commit("key", sig, frame_count=count)

    def key_cache_ready(self):
        """Read-only readiness check; no decode, key or tracking work is started."""
        count = self.project.video.frame_count
        return bool(count and self._manifest("key").get("signature") == self.key_signature()
                    and self._files_valid(self.keyed, count))

    def ensure_roots(self):
        self.ensure_key()
        sig = self.root_signature()
        cached = self._manifest("root")
        if cached.get("signature") == sig:
            self.project.tracking_results = [FrameData(**f) for f in cached["frames"]]
            return
        self._invalidate("root")
        p = self.project
        p.tracking_results = RootTracker(p.tracking_settings).track(p.video.frame_count,
            lambda i: to_rgba8(self.cache.read(frame_path(self.keyed, i))), p.root_keyframes,
            p.sprite_cell.alpha_threshold, p.sprite_cell.min_component_size, self.progress, self.cancel)
        self._commit("root", sig, frames=[asdict(f) for f in p.tracking_results])

    def ensure_aligned(self):
        if self.project.is_passthrough:
            return self.ensure_passthrough()
        self.ensure_motion()
        sig = self.align_signature()
        cached = self._manifest("align")
        p = self.project
        if cached.get("signature") == sig and self._files_valid(self.aligned, p.video.frame_count):
            p.layout = CellLayout(**cached["layout"])
            p.tracking_results = [FrameData(**f) for f in cached["frames"]]
            review_reference_bounds(p)
            return
        self._invalidate("align")
        normalize = bool(p.character_profile) or p.sprite_cell.canvas_mode == "normalize_source"
        if normalize:
            self.ensure_source_aligned()
            p.layout, transform = normalized_layout(p)
        elif p.motion_settings.enabled:
            p.layout = motion_auto_layout(p)
        else:
            p.layout = calculate_layout(p.tracking_results, p.alignment_mode, p.video.width, p.sprite_cell, p.scale)
            p.layout.normalize_scale = (p.scale, p.scale)
        for frame in p.tracking_results:
            check_cancel(self.cancel)
            try:
                rgba = self.cache.read(frame_path(self.source_aligned if normalize else self.keyed, frame.index))
                if normalize:
                    result = normalize_frame(rgba, frame, transform, p.sprite_cell)
                    if p.character_profile:
                        frame.cell_root = p.character_profile.canonical_root
                elif p.motion_settings.enabled:
                    result = to_rgba8(warp_rgba(rgba, p.layout.width, p.layout.height, p.scale, frame.offset))
                    frame.cell_bbox = alpha_bbox(result, p.sprite_cell.alpha_threshold, max(1, round(p.sprite_cell.min_component_size*p.scale*p.scale)))
                else:
                    result = render_cell(rgba, frame, p.layout, p.scale, p.alignment_mode,
                                          p.sprite_cell.alpha_threshold, p.sprite_cell.min_component_size)
                    frame.cell_ground = (frame.ground*p.scale+frame.offset[1]) if frame.ground is not None else None
                save_rgba(frame_path(self.aligned, frame.index), result)
            except Exception:
                log.exception("Alignment failed at source frame %06d", frame.index)
                raise
            self.progress(frame.index + 1, p.video.frame_count, "Aligning / normalizing sprite cells")
        review_warnings(p.tracking_results, p.export_settings.loop)
        review_reference_bounds(p)
        self._commit("align", sig, layout=asdict(p.layout), frames=[asdict(f) for f in p.tracking_results])

    def ensure_passthrough(self):
        """Both sources share final cells; no tracking, alignment or Character Profile."""
        p = self.project
        p.validate()
        if p.is_keyed_passthrough:
            self.ensure_key()
            source = self.keyed
        else:
            self.ensure_raw()
            source = self.raw
        sig = self.align_signature()
        cached = self._manifest("align")
        if cached.get("signature") == sig and self._files_valid(self.aligned, p.video.frame_count):
            p.layout = CellLayout(**cached["layout"])
            p.tracking_results = [FrameData(**f) for f in cached["frames"]]
            return
        self._invalidate("align")
        s = p.sprite_cell
        transform = canvas_transform(p.video.width, p.video.height, s.target_width, s.target_height, s.preserve_aspect_ratio) if s.canvas_mode == "normalize_source" else None
        width, height = (s.target_width, s.target_height) if transform else (p.video.width, p.video.height)
        p.layout = CellLayout(width, height, (0., 0.), 0., width, height, canvas_mode="normalize_source" if transform else "source_canvas",
            normalize_scale=(transform.scale_x, transform.scale_y) if transform else (1., 1.),
            normalize_offset=(transform.offset_x, transform.offset_y) if transform else (0., 0.), source_width=p.video.width, source_height=p.video.height)
        p.tracking_results = []
        for index in range(p.video.frame_count):
            check_cancel(self.cancel)
            rgba = self.cache.read(frame_path(source, index))
            result = normalize_canvas(rgba, transform) if transform else to_rgba8(rgba)
            save_rgba(frame_path(self.aligned, index), result)
            # Bounds are diagnostics only; zero Root values are placeholders, never detected anchors.
            p.tracking_results.append(FrameData(index, bbox=alpha_bbox(rgba, 0, 0), cell_bbox=alpha_bbox(result, 0, 0),
                tracking_method="passthrough", effective_policy=("PASSTHROUGH", "PASSTHROUGH")))
            self.progress(index+1, p.video.frame_count, "Preparing passthrough sprite cells")
        self._commit("align", sig, layout=asdict(p.layout), frames=[asdict(f) for f in p.tracking_results])

    def ensure_motion(self):
        self.ensure_roots()
        sig = self.motion_signature()
        cached = self._manifest("motion")
        p = self.project
        if cached.get("signature") == sig:
            p.tracking_results = [FrameData(**f) for f in cached["frames"]]
            return
        self._invalidate("motion")
        m = p.motion_settings
        for f in p.tracking_results:
            check_cancel(self.cancel)
            f.raw_root = tuple(f.root)
            f.filtered_root = f.target_root = f.motion_root = tuple(f.root)
            if m.enabled or p.character_profile:
                roi = m.ground_roi
                if roi:
                    reference = m.roi_reference_root or p.root_keyframes[0]
                    dx, dy = f.root[0]-reference[0], f.root[1]-reference[1]
                    roi = (roi[0]+dx, roi[1]+dy, roi[2]+dx, roi[3]+dy)
                f.ground, f.ground_roi = detect_ground(self.cache.read(frame_path(self.keyed, f.index)), f.root, roi,
                                                      p.sprite_cell.alpha_threshold, p.sprite_cell.min_component_size)
                if f.ground is None:
                    f.warnings.append("Ground Detection Failed")
            else:
                f.ground = f.bbox[3]-1 if f.bbox else None
            self.progress(f.index+1, p.video.frame_count, "Analyzing body ground support")
        if m.enabled or p.character_profile:
            process_motion(p.tracking_results, m, p.video.fps)
        if p.character_profile:
            apply_character_motion(p.tracking_results, p.character_profile)
        self._commit("motion", sig, frames=[asdict(f) for f in p.tracking_results])

    def ensure_source_aligned(self):
        p = self.project
        sig = signature(self.motion_signature(), p.alignment_mode)
        cached = self._manifest("source_align")
        if cached.get("signature") == sig and self._files_valid(self.source_aligned, p.video.frame_count):
            p.tracking_results = [FrameData(**f) for f in cached["frames"]]
            return
        self._invalidate("source_align")
        source_corrections(p)
        transform = character_transform(p.character_profile) if p.character_profile else None
        width, height = (transform.source_width, transform.source_height) if transform else (p.video.width, p.video.height)
        for f in p.tracking_results:
            check_cancel(self.cancel)
            rgba = self.cache.read(frame_path(self.keyed, f.index))
            result = warp_rgba(rgba, width, height, 1., f.correction)
            save_rgba(frame_path(self.source_aligned, f.index), result)
            self.progress(f.index+1, p.video.frame_count, "Aligning source canvas")
        self._commit("source_align", sig, frames=[asdict(f) for f in p.tracking_results])

    def build(self):
        self.ensure_final()
        p = self.project
        sig = self.sheet_signature()
        from app.core.final_frame_provider import FinalFrameProvider
        provider = FinalFrameProvider(p, self.cache_dir, self.final_signature())
        paths = [provider.final_path(i) for i in range(len(provider))]
        if self._manifest("sheet").get("signature") != sig or not self.sheet.is_file():
            self._invalidate("sheet")
            build_sheet(paths, self.sheet, p.layout.width, p.layout.height, p.export_settings.columns, self.progress, self.cancel)
            self._commit("sheet", sig)
        preview, factor = sheet_preview(paths, p.layout.width, p.layout.height, p.export_settings.columns, cancel=self.cancel)
        save_rgba(self.cache_dir / "sheet_preview.png", preview)
        self._commit("preview", sig, factor=factor)
        return self.project
