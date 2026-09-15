"""The single source of final pixels for animation review, sheets, and export."""
import copy
from collections import OrderedDict
import json
from pathlib import Path

from app.utils.cache import FrameCache
from app.utils.paths import frame_path
from app.utils.rgba_image import to_rgba8


class FinalFrameProvider:
    def __init__(self, project, cache_dir: Path, expected_signature=None, live_edit=False):
        self.project = copy.deepcopy(project)
        self.live_edit = live_edit and self.project.has_final_edits
        self.rendered = OrderedDict()
        self.rendered_bytes = 0
        self.live_metadata = {}
        if self.live_edit:
            from app.core.timeline_renderer import compile_final_timing
            self.project.final_timing = compile_final_timing(self.project)

        self.cache_dir = Path(cache_dir)
        self.cache = FrameCache(96 * 1024 * 1024)
        self.expected_signature = expected_signature or self._signature()
        if not self.project.layout or not self.expected_signature:
            raise ValueError("Build sprites before previewing final frames")

    def _signature(self):
        try:
            return json.loads((self.cache_dir / ("final.json" if self.project.has_final_edits and not self.live_edit else "align.json")).read_text(encoding="utf-8")).get("signature")
        except (OSError, ValueError):
            return None

    def validate(self):
        if self._signature() != self.expected_signature:
            raise RuntimeError("Final frames changed. Rebuild and reopen the preview.")

    def __len__(self):
        return self.project.output_count

    def final_path(self, index):
        self.validate()
        if not 0 <= index < len(self):
            raise IndexError(index)
        return frame_path(self.cache_dir / ("final_frames" if self.project.has_final_edits else "aligned_frames"), index)

    def get_final_frame(self, index):
        if self.live_edit:
            self.validate()
            if not 0 <= index < len(self): raise IndexError(index)
            if index in self.rendered:
                self.rendered.move_to_end(index)
                return self.rendered[index]
            from app.core.timeline_renderer import render_timeline_frame
            pixels, frame = render_timeline_frame(self.project, self.project.final_timing[index],
                lambda i: self.cache.read(frame_path(self.cache_dir / "aligned_frames", i)), index,
                lambda i:self.cache.read(frame_path(self.cache_dir / ("raw_frames" if self.project.input_mode=="frame_sequence" else "keyed_frames"),i)))
            self.live_metadata[index] = frame
            while self.rendered and self.rendered_bytes + pixels.nbytes > 96*1024*1024:
                _, previous = self.rendered.popitem(last=False)
                self.rendered_bytes -= previous.nbytes
            self.rendered[index] = pixels
            self.rendered_bytes += pixels.nbytes
            return pixels
        frame = self.cache.read(self.final_path(index))
        if frame.shape[:2] != (self.project.layout.height, self.project.layout.width):
            raise ValueError("Final frame dimensions do not match the sprite cell")
        return frame

    def frame_data(self, index):
        if self.live_edit:
            if index not in self.live_metadata: self.get_final_frame(index)
            return self.live_metadata[index]
        return self.project.output_frames[index]

    def source_index(self, index):
        return self.project.final_timing[index]['source_index'] if self.project.has_final_edits else index

    def duration(self, index):
        return self.project.final_timing[index]['duration'] if self.project.has_final_edits else 1/(self.project.video.fps or 24)

    def get_source_keyed_frame(self, index):
        self.validate()
        if not 0 <= index < len(self):
            raise IndexError(index)
        source_index = self.source_index(index)
        if source_index < 0:
            import numpy as np
            return np.zeros((self.project.video.height, self.project.video.width, 4), np.uint8)
        folder = "raw_frames" if self.project.input_mode == "frame_sequence" else "keyed_frames"
        return to_rgba8(self.cache.read(frame_path(self.cache_dir / folder, source_index)))
