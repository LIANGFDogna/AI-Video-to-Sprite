"""The single source of final pixels for animation review, sheets, and export."""
import copy
import json
from pathlib import Path

from app.utils.cache import FrameCache
from app.utils.paths import frame_path
from app.utils.rgba_image import to_rgba8


class FinalFrameProvider:
    def __init__(self, project, cache_dir: Path, expected_signature=None):
        self.project = copy.deepcopy(project)
        self.cache_dir = Path(cache_dir)
        self.cache = FrameCache(96 * 1024 * 1024)
        self.expected_signature = expected_signature or self._signature()
        if not self.project.layout or not self.expected_signature:
            raise ValueError("Build sprites before previewing final frames")

    def _signature(self):
        try:
            return json.loads((self.cache_dir / "align.json").read_text(encoding="utf-8")).get("signature")
        except (OSError, ValueError):
            return None

    def validate(self):
        if self._signature() != self.expected_signature:
            raise RuntimeError("Final frames changed. Rebuild and reopen the preview.")

    def __len__(self):
        return self.project.video.frame_count

    def final_path(self, index):
        self.validate()
        if not 0 <= index < len(self):
            raise IndexError(index)
        return frame_path(self.cache_dir / "aligned_frames", index)

    def get_final_frame(self, index):
        frame = self.cache.read(self.final_path(index))
        if frame.shape[:2] != (self.project.layout.height, self.project.layout.width):
            raise ValueError("Final frame dimensions do not match the sprite cell")
        return frame

    def get_source_keyed_frame(self, index):
        self.validate()
        if not 0 <= index < len(self):
            raise IndexError(index)
        folder = "raw_frames" if self.project.input_mode == "frame_sequence" else "keyed_frames"
        return to_rgba8(self.cache.read(frame_path(self.cache_dir / folder, index)))
