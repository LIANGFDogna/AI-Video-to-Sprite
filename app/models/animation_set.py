"""Phase 2D Animation Sets: a character-level logical layer over Groups and Animations."""
from __future__ import annotations
from dataclasses import dataclass, field
import re

from app.models.ids import new_id, now_stamp, valid_id

SET_STATES = ("EMPTY", "INCOMPLETE", "READY")
TRANSITION_TYPES = ("cut",)


def normalize_key(value):
    "jump_up / jump-up / JumpUp / Jump Up all compare equal."
    return re.sub(r"[^0-9a-z]+", "", (value or "").casefold())


@dataclass
class AnimationSlot:
    display_name: str
    id: str = field(default_factory=new_id)
    semantic_type: str = ""
    required: bool = True
    animation_id: str | None = None
    repeat_count: int = 1
    preview_duration_override: float | None = None
    enabled: bool = True

    @property
    def aliases(self):
        return {normalize_key(self.display_name), normalize_key(self.id), normalize_key(self.semantic_type)} - {""}

    @property
    def bound(self):
        return bool(self.animation_id)

    def validate(self):
        if not valid_id(self.id) or not isinstance(self.display_name, str) or not self.display_name.strip():
            raise ValueError("Invalid Animation Slot")
        if not isinstance(self.repeat_count, int) or not 1 <= self.repeat_count <= 100:
            raise ValueError("Invalid Animation Slot repeat count")
        if self.preview_duration_override is not None and not 0 < float(self.preview_duration_override) <= 60:
            raise ValueError("Invalid Animation Slot duration")
        if not isinstance(self.semantic_type, str):
            raise ValueError("Invalid Animation Slot")
        return self


@dataclass
class AnimationSet:
    name: str
    character_id: str
    id: str = field(default_factory=new_id)
    semantic_type: str = ""
    slots: list[AnimationSlot] = field(default_factory=list)
    preview_sequence: list[str] = field(default_factory=list)
    pre_animation: str | None = None
    post_animation: str | None = None
    transition_type: str = "cut"
    created_at: str = field(default_factory=now_stamp)
    modified_at: str = field(default_factory=now_stamp)

    @property
    def required_slots(self):
        return [slot for slot in self.slots if slot.required]

    @property
    def optional_slots(self):
        return [slot for slot in self.slots if not slot.required]

    @property
    def slot_bindings(self):
        return {slot.id: slot.animation_id for slot in self.slots if slot.animation_id}

    @property
    def bound_required(self):
        return [slot for slot in self.required_slots if slot.animation_id]

    @property
    def completion(self):
        return (len(self.bound_required), len(self.required_slots))

    @property
    def missing_required(self):
        return [slot for slot in self.required_slots if not slot.animation_id]

    @property
    def status(self):
        if not any(slot.animation_id for slot in self.slots):
            return "EMPTY"
        return "READY" if not self.missing_required else "INCOMPLETE"

    @property
    def bound_animation_ids(self):
        return {slot.animation_id for slot in self.slots if slot.animation_id}

    def slot(self, ident):
        return next((slot for slot in self.slots if slot.id == ident), None)

    def ordered_slots(self, include_disabled=False):
        "Preview order: preview_sequence first, then declaration order."
        lookup = {slot.id: slot for slot in self.slots}
        ordered = [lookup[ident] for ident in self.preview_sequence if ident in lookup]
        ordered += [slot for slot in self.slots if slot.id not in set(self.preview_sequence)]
        return [slot for slot in ordered if include_disabled or slot.enabled]

    def preview_timeline(self):
        "Segments in playback order: (slot, animation_id, repeat_count, transition)."
        rows = []
        bound = [slot for slot in self.ordered_slots() if slot.animation_id]
        for index, slot in enumerate(bound):
            repeat = max(1, int(slot.repeat_count))
            if self.semantic_type == "jump" and normalize_key(slot.semantic_type) == "fallloop" and repeat == 1:
                repeat = 2
            rows.append((slot, slot.animation_id, repeat, self.transition_type if index else "cut"))
        return rows

    def preview_animation_ids(self, include_context=True):
        ids = [animation_id for _, animation_id, _, _ in self.preview_timeline()]
        if include_context:
            ids = [self.pre_animation] if self.pre_animation else [] + ids
            ids = ids + ([self.post_animation] if self.post_animation else [])
        return [ident for ident in ids if ident]

    def clear_animation(self, animation_id):
        "Drop every reference to one Animation (used by delete / cross-character moves)."
        changed = False
        for slot in self.slots:
            if slot.animation_id == animation_id:
                slot.animation_id = None
                changed = True
        for field_name in ("pre_animation", "post_animation"):
            if getattr(self, field_name) == animation_id:
                setattr(self, field_name, None)
                changed = True
        if changed:
            self.modified_at = now_stamp()
        return changed

    def validate(self):
        if not valid_id(self.id) or not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Invalid Animation Set")
        if not valid_id(self.character_id):
            raise ValueError("Invalid Animation Set")
        if self.transition_type not in TRANSITION_TYPES:
            raise ValueError("Invalid Animation Set transition")
        identifiers = [slot.id for slot in self.slots]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Animation Set slots must be unique")
        for slot in self.slots:
            slot.validate()
        known = set(identifiers)
        if any(ident not in known for ident in self.preview_sequence):
            raise ValueError("Animation Set preview sequence is invalid")
        return self
