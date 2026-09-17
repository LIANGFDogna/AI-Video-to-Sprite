"""Per-frame raster edits: one Pencil paint layer plus one Eraser mask per Animation frame.

The layers are stored next to the project cache, never inside the project JSON and never
on top of the original media: an edit only records metadata, a relative reference and a
revision number.
"""
from __future__ import annotations

from dataclasses import dataclass

MIN_BRUSH_SIZE = 1
MAX_BRUSH_SIZE = 64
DEFAULT_BRUSH_SIZE = 8
MAX_REFERENCE_OPACITY = .7
DEFAULT_REFERENCE_OPACITY = .15


@dataclass
class PerFrameRasterEdit:
    """Animation + frame scoped edit; the pixels themselves live in two PNG layers."""

    animation_id: str
    frame_index: int
    paint_layer: str = ""
    erase_mask: str = ""
    revision: int = 0

    @property
    def active(self):
        return bool(self.paint_layer or self.erase_mask)

    @classmethod
    def from_dict(cls, data):
        if isinstance(data, cls):
            return data
        data = dict(data or {})
        return cls(str(data.get("animation_id", "")), int(data.get("frame_index", 0)),
                   str(data.get("paint_layer", "") or ""), str(data.get("erase_mask", "") or ""),
                   int(data.get("revision", 0)))

    def validate(self):
        value = self.animation_id
        if len(value) != 32 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("Invalid raster edit Animation")
        if not isinstance(self.frame_index, int) or self.frame_index < 0:
            raise ValueError("Invalid raster edit frame")
        if not isinstance(self.revision, int) or self.revision < 0:
            raise ValueError("Invalid raster edit revision")
        if bool(self.paint_layer) != bool(self.erase_mask):
            raise ValueError("Raster edit layers must be stored together")
        return self


def frame_key(frame_index):
    "JSON object keys are text; the frame index stays the only identity."
    return str(int(frame_index))


def edits_from_dict(data):
    """{animation_id: {frame_index: PerFrameRasterEdit}} with JSON string keys."""
    result = {}
    for animation_id, frames in (data or {}).items():
        rows = {}
        for index, row in (frames or {}).items():
            value = PerFrameRasterEdit.from_dict(row)
            value.animation_id = str(animation_id)
            value.frame_index = int(index)
            rows[int(index)] = value
        if rows:
            result[str(animation_id)] = rows
    return result


def edits_to_dict(data):
    return {animation_id: {frame_key(index): row for index, row in rows.items()}
            for animation_id, rows in (data or {}).items()}
