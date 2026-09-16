"""Phase 2D: play an Animation Set by scheduling each bound Animation through FinalFrameProvider."""
from __future__ import annotations
from dataclasses import dataclass

from app.core.final_frame_provider import FinalFrameProvider
from app.models.project_library import unique_name
from app.utils.paths import cache_directory


@dataclass
class SetSegment:
    label: str
    animation_id: str
    repeat: int = 1
    transition: str = "cut"
    context: bool = False
    slot_id: str | None = None


def set_segments(animation_set, include_context=True):
    "Playback segments in order: optional pre context, bound slots with repeats, optional post context."
    rows = []
    if include_context and animation_set.pre_animation:
        rows.append(SetSegment("Idle (pre)", animation_set.pre_animation, 1, "cut", True))
    for slot, animation_id, repeat, transition in animation_set.preview_timeline():
        rows.append(SetSegment(slot.display_name, animation_id, repeat, transition, False, slot.id))
    if include_context and animation_set.post_animation:
        rows.append(SetSegment("Idle (post)", animation_set.post_animation, 1, "cut", True))
    return rows


class SetPreviewProvider:
    """Exposes the same interface as FinalFrameProvider but over a whole Animation Set."""

    def __init__(self, project, project_file, animation_set, include_context=True):
        self.project = project
        self.animation_set = animation_set
        self.cache_dir = cache_directory(project.project_id, project_file, project.animation_id)
        self.entries = []
        for segment in set_segments(animation_set, include_context):
            animation = project.select_animation(segment.animation_id)
            directory = cache_directory(project.project_id, project_file, segment.animation_id)
            provider = FinalFrameProvider(animation, directory, live_edit=True)
            frames = len(provider)
            for repeat in range(max(1, int(segment.repeat))):
                for frame in range(frames):
                    self.entries.append((segment, provider, frame, repeat))
            segment.provider = provider
            segment.frames = frames
        self.segments = [segment for segment in set_segments(animation_set, include_context)]

    def __len__(self):
        return len(self.entries)

    def entry(self, index):
        if not 0 <= index < len(self.entries):
            raise IndexError(index)
        return self.entries[index]

    def get_final_frame(self, index):
        _, provider, frame, _ = self.entry(index)
        return provider.get_final_frame(frame)

    def get_source_keyed_frame(self, index):
        _, provider, frame, _ = self.entry(index)
        return provider.get_source_keyed_frame(frame)

    def frame_data(self, index):
        _, provider, frame, _ = self.entry(index)
        return provider.frame_data(frame)

    def source_index(self, index):
        _, provider, frame, _ = self.entry(index)
        return provider.source_index(frame)

    def duration(self, index):
        segment, provider, frame, _ = self.entry(index)
        slot = self.animation_set.slot(segment.slot_id) if segment.slot_id else None
        if slot is not None and slot.preview_duration_override:
            return float(slot.preview_duration_override)
        return provider.duration(frame)

    def label(self, index):
        segment, _, frame, repeat = self.entry(index)
        suffix = f" x{repeat+1}" if segment.repeat > 1 else ""
        return f"{segment.label}{suffix}  {frame + 1}/{segment.frames}"
