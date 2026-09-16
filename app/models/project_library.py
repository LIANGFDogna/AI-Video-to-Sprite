"""Project containers and resource ownership; independent from pixel processing."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
import copy
import math

from app.models.animation_set import AnimationSet, AnimationSlot, normalize_key
from app.models.character_reference import CharacterReference
from app.models.state_machine import Condition, State, StateMachine, StateParameter, Transition

SOURCE_KINDS = {"SOURCE_VIDEO", "SOURCE_SEQUENCE", "SOURCE_SPRITE_SHEET"}
RESOURCE_KINDS = SOURCE_KINDS | {"ANIMATION", "GENERATED_SPRITE_SHEET"}
GROUP_STATES = {"EMPTY", "SOURCE_ONLY", "PROCESSING", "READY", "WARNING"}


from app.models.ids import new_id, now_stamp, valid_id  # noqa: F401  (re-exported for existing imports)


def unique_name(name, existing, separator=" "):
    name = name.strip()
    if not name:
        raise ValueError("Name cannot be empty")
    taken = {v.casefold() for v in existing}
    result, number = name, 2
    while result.casefold() in taken:
        result = f"{name}{separator}{number}"
        number += 1
    return result


@dataclass
class WorkspaceState:
    animation_id: str | None = None
    frame: int = 0
    source_frame: int = 0
    timeline_zoom: float = 720.
    timeline_scroll_x: int = 0
    timeline_scroll_y: int = 0
    editor_tab: int = 0
    page: int = 0
    preview_mode: str = "Checkerboard"
    preview_fps: float = 0.
    loop: bool = True
    onion: bool = False
    ghost: bool = False
    neighbors: int = 1
    ghost_opacity: float = .25
    playing: bool = False
    selected_frames: list[str] = field(default_factory=list)
    reference_ghost: bool | None = None
    reference_ghost_opacity: float = .15

    @classmethod
    def from_dict(cls, data):
        if isinstance(data, cls):
            return copy.deepcopy(data)
        result = cls(**(data or {}))
        if not math.isfinite(result.timeline_zoom) or not 1 <= result.timeline_zoom <= 100000:
            raise ValueError("Invalid Group timeline zoom")
        if result.frame < 0 or result.source_frame < 0 or result.page not in range(5) or result.editor_tab not in (0, 1):
            raise ValueError("Invalid Group workspace state")
        if result.reference_ghost not in (None, True, False) or not 0 <= result.reference_ghost_opacity <= .7:
            raise ValueError("Invalid Group workspace state")
        return result


@dataclass
class Group:
    name: str
    id: str = field(default_factory=new_id)
    parent_id: str | None = None
    order: int = 0
    character_id: str | None = None
    status: str = "EMPTY"
    ui_state: WorkspaceState = field(default_factory=WorkspaceState)
    animation_states: dict[str, WorkspaceState] = field(default_factory=dict)
    character_id: str | None = None
    semantic_type: str = ""
    alignment_review_required: bool = False


@dataclass
class Character:
    name: str
    id: str = field(default_factory=new_id)
    template_id: str = "blank"
    template_version: int = 1
    character_reference: CharacterReference | None = None
    group_ids: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=now_stamp)
    modified_at: str = field(default_factory=now_stamp)


@dataclass
class LibraryResource:
    kind: str
    name: str
    group_id: str
    id: str = field(default_factory=new_id)
    order: int = 0
    path: str = ""
    animation_id: str | None = None
    source_id: str | None = None
    ready: bool = False
    warning: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class TaskContext:
    project_id: str
    group_id: str | None
    animation_id: str
    operation: str
    character_id: str | None = None


@dataclass
class ProjectLibrary:
    version: int = 1
    groups: dict[str, Group] = field(default_factory=dict)
    resources: dict[str, LibraryResource] = field(default_factory=dict)
    characters: dict[str, Character] = field(default_factory=dict)
    animation_sets: dict[str, AnimationSet] = field(default_factory=dict)
    state_machines: dict[str, StateMachine] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data):
        if isinstance(data, cls):
            return copy.deepcopy(data)
        data = copy.deepcopy(data or {})
        groups = {}
        for ident, value in data.get("groups", {}).items():
            value["ui_state"] = WorkspaceState.from_dict(value.get("ui_state"))
            value["animation_states"] = {k: WorkspaceState.from_dict(v) for k, v in value.get("animation_states", {}).items()}
            groups[ident] = Group(**value)
        characters = {}
        for ident, value in data.get("characters", {}).items():
            value = copy.deepcopy(value)
            value["character_reference"] = CharacterReference.from_dict(value.get("character_reference"))
            characters[ident] = Character(**value)
        sets = {}
        for ident, value in (data.get("animation_sets") or {}).items():
            value = copy.deepcopy(value)
            value["slots"] = [AnimationSlot(**slot) for slot in value.get("slots", [])]
            sets[ident] = AnimationSet(**value)
        machines = {}
        for ident, value in (data.get("state_machines") or {}).items():
            value = copy.deepcopy(value)
            value["states"] = [State(**state) for state in value.get("states", [])]
            value["transitions"] = [Transition(from_state=row["from_state"], to_state=row["to_state"], id=row.get("id"),
                conditions=[Condition(**condition) for condition in row.get("conditions", [])], priority=row.get("priority", 0),
                exit_time=row.get("exit_time", 0.0), interruptible=row.get("interruptible", True)) for row in value.get("transitions", [])]
            value["parameters"] = [StateParameter(**parameter) for parameter in value.get("parameters", [])]
            machines[ident] = StateMachine(**value)
        result = cls(data.get("version", 1), groups, {k: LibraryResource(**v) for k, v in data.get("resources", {}).items()}, characters, sets, machines)
        result.refresh_character_groups()
        result.validate()
        return result

    def validate(self):
        if self.version != 1:
            raise ValueError("Unsupported Group library version")
        for ident, group in self.groups.items():
            if not valid_id(ident) or ident != group.id or not group.name.strip() or group.status not in GROUP_STATES:
                raise ValueError("Invalid Group")
            if group.parent_id is not None and group.parent_id not in self.groups:
                raise ValueError("Group parent does not exist")
            self.path(ident)
            WorkspaceState.from_dict(group.ui_state)
        names = set()
        for group in self.groups.values():
            key = group.parent_id, group.character_id, group.name.casefold()
            if key in names:
                raise ValueError("Sibling Group names must be unique")
            names.add(key)
        animations = {}
        for ident, resource in self.resources.items():
            if not valid_id(ident) or resource.id != ident or resource.kind not in RESOURCE_KINDS or resource.group_id not in self.groups:
                raise ValueError("Resource must belong to a Group")
            if not resource.name.strip():
                raise ValueError("Name cannot be empty")
            if resource.kind == "ANIMATION":
                if not resource.animation_id or resource.animation_id in animations:
                    raise ValueError("Animation ownership must be unique")
                animations[resource.animation_id] = resource
            if resource.source_id and (resource.source_id not in self.resources or self.resources[resource.source_id].kind not in SOURCE_KINDS):
                raise ValueError("Resource source reference is invalid")
        for resource in self.resources.values():
            if resource.kind == "GENERATED_SPRITE_SHEET":
                owner = animations.get(resource.animation_id)
                if owner is None or owner.group_id != resource.group_id:
                    raise ValueError("Generated Sheet must follow its Animation Group")
        for group in self.groups.values():
            selected = group.ui_state.animation_id
            if selected and (selected not in animations or animations[selected].group_id != group.id):
                raise ValueError("Selected Animation does not belong to the Group")
        for ident, character in self.characters.items():
            if not valid_id(ident) or ident != character.id or not character.name.strip():
                raise ValueError("Invalid Character")
            if not character.template_id.strip() or not isinstance(character.template_version, int) or character.template_version < 1:
                raise ValueError("Invalid Character template")
        names = set()
        for character in self.characters.values():
            if character.name.casefold() in names:
                raise ValueError("Character names must be unique")
            names.add(character.name.casefold())
        for group in self.groups.values():
            if group.character_id is not None and group.character_id not in self.characters:
                raise ValueError("Group Character does not exist")
            if group.parent_id is not None and self.groups[group.parent_id].character_id != group.character_id:
                raise ValueError("Nested Groups must belong to the same Character")
            if not isinstance(group.semantic_type, str):
                raise ValueError("Invalid Group metadata")
        names = set()
        for ident, animation_set in self.animation_sets.items():
            animation_set.validate()
            if ident != animation_set.id or animation_set.character_id not in self.characters:
                raise ValueError("Animation Set Character does not exist")
            key = animation_set.character_id, animation_set.name.casefold()
            if key in names:
                raise ValueError("Animation Set names must be unique per Character")
            names.add(key)
            for animation_id in animation_set.bound_animation_ids | {animation_set.pre_animation, animation_set.post_animation} - {None}:
                owner = next((r for r in self.resources.values() if r.kind == "ANIMATION" and r.animation_id == animation_id), None)
                if owner is None or self.groups[owner.group_id].character_id != animation_set.character_id:
                    raise ValueError("Animation Set bindings must belong to the same Character")
        machine_names = set()
        for ident, machine in self.state_machines.items():
            machine.validate()
            if ident != machine.id or machine.character_id not in self.characters:
                raise ValueError("State Machine Character does not exist")
            key = machine.character_id, machine.name.casefold()
            if key in machine_names:
                raise ValueError("State Machine names must be unique per Character")
            machine_names.add(key)
            for animation_id in machine.bound_animation_ids():
                owner = next((r for r in self.resources.values() if r.kind == "ANIMATION" and r.animation_id == animation_id), None)
                if owner is None or self.groups[owner.group_id].character_id != machine.character_id:
                    raise ValueError("State Machine bindings must belong to the same Character")
            for set_id in machine.bound_set_ids():
                row = self.animation_sets.get(set_id)
                if row is None or row.character_id != machine.character_id:
                    raise ValueError("State Machine bindings must belong to the same Character")
        for ident, character in self.characters.items():
            members = {g.id for g in self.groups.values() if g.character_id == ident}
            if set(character.group_ids) != members:
                raise ValueError("Character Group index is stale")
            reference = character.character_reference
            if reference is not None:
                owner = next((r for r in self.resources.values()
                    if r.kind == "ANIMATION" and r.animation_id == reference.reference_animation_id), None)
                if owner is None or self.groups[owner.group_id].character_id != ident:
                    raise ValueError("Character Reference animation must belong to the same Character")

    def ordered_children(self, parent_id=None, character_id=None):
        "Siblings inside one Character tree; top-level rows are scoped per Character."
        rows = self.children(parent_id)
        if parent_id is None:
            rows = [group for group in rows if group.character_id == character_id]
        return rows

    def children(self, parent_id=None):
        return sorted((g for g in self.groups.values() if g.parent_id == parent_id), key=lambda g: (g.order, g.id))

    def path(self, group_id):
        result, seen = [], set()
        while group_id is not None:
            if group_id in seen or group_id not in self.groups:
                raise ValueError("Group hierarchy contains a cycle or missing parent")
            seen.add(group_id)
            group = self.groups[group_id]
            result.append(group)
            group_id = group.parent_id
        return list(reversed(result))

    def descendants(self, group_id, include_self=True):
        self.path(group_id)
        result = [group_id] if include_self else []
        for group in self.children(group_id):
            result.extend(self.descendants(group.id))
        return result

    def add_group(self, name, parent_id=None, index=None, character_id=None, semantic_type=""):
        if parent_id is not None and parent_id not in self.groups:
            raise ValueError("Please create a Group first")
        parent = self.groups[parent_id] if parent_id is not None else None
        owner = parent.character_id if parent is not None else character_id
        if owner is not None and owner not in self.characters:
            raise ValueError("Character does not exist")
        siblings = self.ordered_children(parent_id, owner)
        group = Group(unique_name(name, [g.name for g in siblings]), parent_id=parent_id, order=len(siblings),
                      character_id=owner, semantic_type=semantic_type)
        self.groups[group.id] = group
        if index is not None:
            self.move_group(group.id, parent_id, index)
        self.refresh_character_groups()
        return group

    def rename_group(self, ident, name):
        group = self.groups[ident]
        group.name = unique_name(name, [g.name for g in self.ordered_children(group.parent_id, group.character_id) if g.id != ident])
        return group.name

    def move_group(self, ident, parent_id, index=None, clear_references=False, clear_sets=False, clear_machines=False):
        if parent_id is not None and parent_id not in self.groups:
            raise ValueError("Group parent does not exist")
        if parent_id in self.descendants(ident):
            raise ValueError("Cannot move a Group into itself or its children")
        owner = self.groups[parent_id].character_id if parent_id is not None else self.groups[ident].character_id
        previous = self.groups[ident].character_id
        self.check_reference_move(ident, owner, clear_references)
        self.check_set_move(ident, owner, clear_sets)
        self.check_machine_move(ident, owner, clear_machines)
        group = self.groups[ident]
        siblings = [g for g in self.ordered_children(parent_id, owner) if g.id != ident]
        group.name = unique_name(group.name, [g.name for g in siblings])
        group.parent_id = parent_id
        siblings.insert(len(siblings) if index is None else max(0, min(index, len(siblings))), group)
        for order, item in enumerate(siblings):
            item.order = order
        self.reassign_character(ident, owner)
        if previous != owner:
            self.mark_alignment_review(ident)
        self.refresh_character_groups()

    def in_group(self, group_id, recursive=False, kinds=None):
        ids = set(self.descendants(group_id) if recursive else [group_id])
        return sorted((r for r in self.resources.values() if r.group_id in ids and (kinds is None or r.kind in kinds)), key=lambda r: (r.order, r.id))

    def animation_count(self, group_id):
        return len(self.in_group(group_id, True, {"ANIMATION"}))

    def animation(self, animation_id):
        return next((r for r in self.resources.values() if r.kind == "ANIMATION" and r.animation_id == animation_id), None)

    def add_source_animation(self, group_id, animation_id, name, source_path, kind):
        if group_id not in self.groups:
            raise ValueError("Please create a Group first")
        if kind not in ("SOURCE_VIDEO", "SOURCE_SEQUENCE") or self.animation(animation_id):
            raise ValueError("Invalid new Animation resource")
        rows = self.in_group(group_id)
        name = unique_name(name, [r.name for r in rows if r.kind == "ANIMATION"], "_")
        source = LibraryResource(kind, source_path.replace("\\", "/").rstrip("/").split("/")[-1], group_id,
            path=source_path, animation_id=animation_id, order=len(rows))
        animation = LibraryResource("ANIMATION", name, group_id, animation_id=animation_id, source_id=source.id, order=len(rows)+1)
        self.resources[source.id] = source
        self.resources[animation.id] = animation
        self.refresh_status()
        return animation

    def add_sheet(self, group_id, name, path, metadata=None):
        if group_id not in self.groups:
            raise ValueError("Please create a Group first")
        row = LibraryResource("SOURCE_SPRITE_SHEET", name, group_id, path=path, ready=True,
            order=len(self.in_group(group_id)), metadata=metadata or {})
        self.resources[row.id] = row
        self.refresh_status()
        return row

    def mark_generated(self, animation_id, ready=True, metadata=None):
        owner = self.animation(animation_id)
        if owner is None:
            raise ValueError("Animation ownership is missing")
        owner.ready = ready
        sheet = next((r for r in self.resources.values() if r.kind == "GENERATED_SPRITE_SHEET" and r.animation_id == animation_id), None)
        if sheet is None:
            sheet = LibraryResource("GENERATED_SPRITE_SHEET", owner.name + " Sheet", owner.group_id,
                animation_id=animation_id, order=owner.order, ready=ready)
            self.resources[sheet.id] = sheet
        sheet.ready, sheet.metadata = ready, metadata or sheet.metadata
        self.refresh_status()
        return sheet

    def move_resource(self, ident, target_group, index=None):
        if target_group not in self.groups:
            raise ValueError("Resources cannot be moved to the Project Root")
        row = self.resources[ident]
        if row.kind == "GENERATED_SPRITE_SHEET":
            raise ValueError("Move the owning Animation to move its generated Sheet")
        previous = self.groups[row.group_id]
        row.group_id = target_group
        siblings = [r for r in self.in_group(target_group) if r.id != ident]
        siblings.insert(len(siblings) if index is None else max(0, min(index, len(siblings))), row)
        for order, sibling in enumerate(siblings):
            sibling.order = order
        if row.kind == "ANIMATION":
            row.name = unique_name(row.name, [r.name for r in siblings if r.kind == "ANIMATION" and r.id != ident], "_")
            for sheet in self.resources.values():
                if sheet.kind == "GENERATED_SPRITE_SHEET" and sheet.animation_id == row.animation_id:
                    sheet.group_id = target_group
            if previous.id != target_group and previous.ui_state.animation_id == row.animation_id:
                previous.ui_state = WorkspaceState()
            saved = previous.animation_states.pop(row.animation_id, None) if previous.id != target_group else None
            if saved:
                self.groups[target_group].animation_states[row.animation_id] = saved
        self.refresh_status()

    def reassign_character(self, group_id, character_id):
        "Apply ownership to a Group and every descendant without touching pixels or offsets."
        for member in self.descendants(group_id):
            self.groups[member].character_id = character_id
        self.refresh_character_groups()

    def reference_characters_for(self, group_id):
        "Characters whose Reference Animation lives inside this Group subtree."
        members = set(self.descendants(group_id))
        owners = {r.animation_id for r in self.resources.values() if r.kind == "ANIMATION" and r.group_id in members}
        return [character for character in self.characters.values()
                if character.character_reference and character.character_reference.reference_animation_id in owners]

    def check_reference_move(self, group_id, character_id, clear_references=False):
        blocking = [character for character in self.reference_characters_for(group_id) if character.id != character_id]
        if blocking and not clear_references:
            raise ValueError("Animation is the Character Reference")
        for character in blocking:
            character.character_reference = None
            character.modified_at = now_stamp()
        return blocking

    def mark_alignment_review(self, group_id):
        "Ownership changes keep every offset but require a manual alignment review."
        for member in self.descendants(group_id):
            self.groups[member].alignment_review_required = True

    def set_group_character(self, group_id, character_id, clear_references=False, clear_sets=False, clear_machines=False):
        if character_id is not None and character_id not in self.characters:
            raise ValueError("Character does not exist")
        previous = self.groups[group_id].character_id
        self.check_reference_move(group_id, character_id, clear_references)
        self.check_set_move(group_id, character_id, clear_sets)
        self.check_machine_move(group_id, character_id, clear_machines)
        self.reassign_character(group_id, character_id)
        if previous != character_id:
            self.mark_alignment_review(group_id)
        if character_id is not None:
            self.characters[character_id].modified_at = now_stamp()

    def refresh_character_groups(self):
        for ident, character in self.characters.items():
            character.group_ids = sorted(g.id for g in self.groups.values() if g.character_id == ident)
        return self

    def add_character(self, name, template_id="blank", template_version=1, reference=None):
        character = Character(unique_name(name, [c.name for c in self.characters.values()]),
            template_id=template_id, template_version=template_version, character_reference=reference)
        self.characters[character.id] = character
        return character

    def rename_character(self, ident, name):
        character = self.characters[ident]
        character.name = unique_name(name, [c.name for c in self.characters.values() if c.id != ident])
        character.modified_at = now_stamp()
        return character.name

    def remove_character(self, ident, move_to_loose=True):
        character = self.characters[ident]
        roots = [g.id for g in self.children(None) if g.character_id == ident]
        if roots and not move_to_loose:
            raise ValueError("Character contains Groups")
        for group_id in roots:
            self.reassign_character(group_id, None)
        character.character_reference = None
        del self.characters[ident]
        self.refresh_character_groups()

    def character_roots(self, ident):
        return [g for g in self.children(None) if g.character_id == ident]

    def loose_roots(self):
        return [g for g in self.children(None) if g.character_id is None]

    def character_members(self, ident):
        return [g for g in self.groups.values() if g.character_id == ident]

    def character_animation_count(self, ident):
        return sum(len(self.in_group(group.id, True, {"ANIMATION"})) for group in self.character_roots(ident))

    def character_for_animation(self, animation_id):
        owner = self.animation(animation_id)
        if owner is None:
            return None
        return self.characters.get(self.groups[owner.group_id].character_id)

    def animation_sets_for(self, character_id):
        return [row for row in self.animation_sets.values() if row.character_id == character_id]

    def animation_set(self, ident):
        return self.animation_sets.get(ident)

    def set_references(self, animation_id):
        "[(set, slot)] referencing one Animation, for delete / move protection."
        result = []
        for row in self.animation_sets.values():
            for slot in row.slots:
                if slot.animation_id == animation_id:
                    result.append((row, slot))
        return result

    def clear_animation_set_references(self, animation_id):
        return [row for row in self.animation_sets.values() if row.clear_animation(animation_id)]

    def add_animation_set(self, character_id, name, semantic_type="", slots=(), preview_sequence=None, pre_animation=None, post_animation=None):
        if character_id not in self.characters:
            raise ValueError("Character does not exist")
        existing = [row.name for row in self.animation_sets_for(character_id)]
        row = AnimationSet(unique_name(name, existing), character_id, semantic_type=semantic_type,
            slots=[slot if isinstance(slot, AnimationSlot) else AnimationSlot(**slot) for slot in slots],
            preview_sequence=list(preview_sequence or [slot.id for slot in slots]),
            pre_animation=pre_animation, post_animation=post_animation)
        self.animation_sets[row.id] = row
        row.validate()
        return row

    def rename_animation_set(self, ident, name):
        row = self.animation_sets[ident]
        row.name = unique_name(name, [other.name for other in self.animation_sets_for(row.character_id) if other.id != ident])
        row.modified_at = now_stamp()
        return row.name

    def remove_animation_set(self, ident, clear_machines=False):
        users = self.state_machine_references(set_id=ident)
        if users and not clear_machines:
            raise ValueError("Animation Set is used by a State Machine")
        if users:
            self.clear_state_machine_references(set_id=ident)
        row = self.animation_sets.pop(ident, None)
        if row is None:
            raise ValueError("Animation Set does not exist")
        return row

    def bind_slot(self, set_id, slot_id, animation_id=None):
        row = self.animation_sets[set_id]
        slot = row.slot(slot_id)
        if slot is None:
            raise ValueError("Animation Set slot does not exist")
        if animation_id is not None:
            owner = next((r for r in self.resources.values() if r.kind == "ANIMATION" and r.animation_id == animation_id), None)
            if owner is None:
                raise ValueError("Resource does not exist")
            if self.groups[owner.group_id].character_id != row.character_id:
                raise ValueError("Animation Set bindings must belong to the same Character")
        slot.animation_id = animation_id
        row.modified_at = now_stamp()
        return slot

    def auto_match_set(self, set_id):
        "Bind unbound slots by semantic_type first, then by name; results are stored as animation_id."
        row = self.animation_sets[set_id]
        candidates = []
        for resource in self.resources.values():
            if resource.kind != "ANIMATION":
                continue
            group = self.groups[resource.group_id]
            if group.character_id != row.character_id:
                continue
            candidates.append((normalize_key(resource.name), normalize_key(group.name), normalize_key(group.semantic_type), resource))
        used = set()
        matched = 0
        for slot in row.slots:
            if slot.animation_id:
                used.add(slot.animation_id)
        for slot in row.slots:
            if slot.animation_id:
                continue
            wanted = slot.aliases
            semantic = normalize_key(slot.semantic_type)
            for name_key, group_key, group_semantic, resource in candidates:
                if resource.animation_id in used:
                    continue
                if semantic and semantic in (group_semantic, name_key):
                    slot.animation_id = resource.animation_id
                    used.add(resource.animation_id)
                    matched += 1
                    break
            else:
                for name_key, group_key, group_semantic, resource in candidates:
                    if resource.animation_id in used:
                        continue
                    if wanted & ({name_key, group_key} - {""}):
                        slot.animation_id = resource.animation_id
                        used.add(resource.animation_id)
                        matched += 1
                        break
        if matched:
            row.modified_at = now_stamp()
        return matched

    def related_animations(self, source_id):
        return [row for row in self.resources.values() if row.kind == "ANIMATION" and row.source_id == source_id]

    def generated_sheets(self, animation_id):
        return [row for row in self.resources.values() if row.kind == "GENERATED_SPRITE_SHEET" and row.animation_id == animation_id]

    def reference_characters_for_animation(self, animation_id):
        return [character for character in self.characters.values()
                if character.character_reference and character.character_reference.reference_animation_id == animation_id]

    def state_machines_for(self, character_id):
        return [row for row in self.state_machines.values() if row.character_id == character_id]

    def state_machine(self, ident):
        return self.state_machines.get(ident)

    def state_machine_references(self, animation_id=None, set_id=None):
        "[(machine, state)] bound to one Animation or Animation Set."
        result = []
        for machine in self.state_machines.values():
            for state in machine.states:
                if animation_id is not None and state.kind == "animation" and state.animation_id == animation_id:
                    result.append((machine, state))
                if set_id is not None and state.kind == "set" and state.set_id == set_id:
                    result.append((machine, state))
        return result

    def clear_state_machine_references(self, animation_id=None, set_id=None):
        changed = []
        for machine in self.state_machines.values():
            if animation_id is not None and machine.clear_animation(animation_id):
                changed.append(machine)
            if set_id is not None and machine.clear_set(set_id):
                changed.append(machine)
        return changed

    def add_state_machine(self, character_id, name, states=(), transitions=(), parameters=(), entry_state=None):
        if character_id not in self.characters:
            raise ValueError("Character does not exist")
        existing = [row.name for row in self.state_machines_for(character_id)]
        machine = StateMachine(unique_name(name, existing), character_id,
            states=[row if isinstance(row, State) else State(**row) for row in states],
            transitions=[row if isinstance(row, Transition) else Transition(**row) for row in transitions],
            parameters=[row if isinstance(row, StateParameter) else StateParameter(**row) for row in parameters],
            entry_state=entry_state)
        self.state_machines[machine.id] = machine
        if machine.entry_state is None and machine.states:
            machine.entry_state = machine.states[0].id
        machine.validate()
        return machine

    def rename_state_machine(self, ident, name):
        machine = self.state_machines[ident]
        machine.name = unique_name(name, [other.name for other in self.state_machines_for(machine.character_id) if other.id != ident])
        machine.modified_at = now_stamp()
        return machine.name

    def remove_state_machine(self, ident):
        machine = self.state_machines.pop(ident, None)
        if machine is None:
            raise ValueError("State Machine does not exist")
        return machine

    def set_references_for_group(self, group_id):
        "[(set, slot)] bound to Animations inside this Group subtree."
        members = set(self.descendants(group_id))
        owners = {r.animation_id for r in self.resources.values() if r.kind == "ANIMATION" and r.group_id in members}
        return [(row, slot) for row in self.animation_sets.values() for slot in row.slots if slot.animation_id in owners]

    def check_machine_move(self, group_id, character_id, clear_machines=False):
        "State Machines may never reference another Character; moving out requires an explicit clear."
        members = set(self.descendants(group_id))
        owners = {r.animation_id for r in self.resources.values() if r.kind == "ANIMATION" and r.group_id in members}
        blocking = [(machine, state) for machine in self.state_machines.values() if machine.character_id != character_id
                    for state in machine.states if state.kind == "animation" and state.animation_id in owners]
        if blocking and not clear_machines:
            raise ValueError("Animation is used by a State Machine")
        for animation_id in owners:
            if clear_machines:
                self.clear_state_machine_references(animation_id=animation_id)
        return blocking

    def check_set_move(self, group_id, character_id, clear_sets=False):
        "Animation Sets may never reference another Character; moving out requires an explicit clear."
        members = set(self.descendants(group_id))
        owners = {r.animation_id for r in self.resources.values() if r.kind == "ANIMATION" and r.group_id in members}
        blocking = [(row, slot) for row in self.animation_sets.values() if row.character_id != character_id
                    for slot in row.slots if slot.animation_id in owners]
        if blocking and not clear_sets:
            raise ValueError("Animation is used by an Animation Set")
        for animation_id in owners:
            if clear_sets:
                self.clear_animation_set_references(animation_id)
        return blocking

    def remove_animation(self, ident, clear_references=False, clear_sets=False, clear_machines=False):
        "Drop one Animation record with its generated sheet, history and workspace references."
        row = self.resources.get(ident)
        if row is None:
            raise ValueError("Resource does not exist")
        if row.kind != "ANIMATION":
            del self.resources[ident]
            self.refresh_status()
            return [ident]
        blocking = self.reference_characters_for_animation(row.animation_id)
        if blocking and not clear_references:
            raise ValueError("Animation is the Character Reference")
        set_users = self.set_references(row.animation_id)
        if set_users and not clear_sets:
            raise ValueError("Animation is used by an Animation Set")
        if set_users:
            self.clear_animation_set_references(row.animation_id)
        machine_users = self.state_machine_references(animation_id=row.animation_id)
        if machine_users and not clear_machines:
            raise ValueError("Animation is used by a State Machine")
        if machine_users:
            self.clear_state_machine_references(animation_id=row.animation_id)
        for character in blocking:
            character.character_reference = None
            character.modified_at = now_stamp()
        removed = [ident]
        for sheet in self.generated_sheets(row.animation_id):
            removed.append(sheet.id)
            del self.resources[sheet.id]
        for group in self.groups.values():
            if group.ui_state.animation_id == row.animation_id:
                group.ui_state = WorkspaceState()
            group.animation_states.pop(row.animation_id, None)
        del self.resources[ident]
        source_id = row.source_id
        if source_id and not self.related_animations(source_id):
            # The source record only exists to feed Animations; disk files are never touched.
            removed.append(source_id)
            del self.resources[source_id]
        self.refresh_status()
        return removed

    def remove_resource(self, ident, cascade=False, clear_references=False, clear_sets=False, clear_machines=False):
        """Remove Project Library records only; source files and caches on disk stay untouched."""
        row = self.resources.get(ident)
        if row is None:
            raise ValueError("Resource does not exist")
        removed = []
        if row.kind in SOURCE_KINDS:
            animations = self.related_animations(ident)
            if cascade:
                for animation in animations:
                    removed.extend(self.remove_animation(animation.id, clear_references, clear_sets=clear_sets, clear_machines=clear_machines))
            else:
                for animation in animations:
                    animation.source_id = None
            if ident in self.resources:
                removed.append(ident)
                del self.resources[ident]
        else:
            removed.extend(self.remove_animation(ident, clear_references, clear_sets=clear_sets, clear_machines=clear_machines))
        self.refresh_character_groups()
        self.refresh_status()
        return removed

    def remove_group(self, ident, move_to_parent=False):
        group = self.groups[ident]
        contents = self.in_group(ident)
        children = self.children(ident)
        if contents or children:
            if not move_to_parent or group.parent_id is None:
                raise ValueError("Group contains resources. Move them to another Group first.")
            # Move animations before generated sheets; generated ownership follows automatically.
            for resource in list(contents):
                if resource.kind != "GENERATED_SPRITE_SHEET":
                    self.move_resource(resource.id, group.parent_id)
            for child in children:
                self.move_group(child.id, group.parent_id)
        del self.groups[ident]
        self.refresh_character_groups()
        self.refresh_status()

    def refresh_status(self, processing=()):
        processing = set(processing)
        for group in self.groups.values():
            rows = self.in_group(group.id, True)
            group.status = "PROCESSING" if any(r.animation_id in processing for r in rows) else "WARNING" if any(r.warning for r in rows) else "READY" if any(r.ready and r.kind in {"ANIMATION", "SOURCE_SPRITE_SHEET", "GENERATED_SPRITE_SHEET"} for r in rows) else "SOURCE_ONLY" if rows else "EMPTY"
