"""Project containers and resource ownership; independent from pixel processing."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
import copy
import math
import uuid

SOURCE_KINDS = {"SOURCE_VIDEO", "SOURCE_SEQUENCE", "SOURCE_SPRITE_SHEET"}
RESOURCE_KINDS = SOURCE_KINDS | {"ANIMATION", "GENERATED_SPRITE_SHEET"}
GROUP_STATES = {"EMPTY", "SOURCE_ONLY", "PROCESSING", "READY", "WARNING"}


def new_id():
    return uuid.uuid4().hex


def valid_id(value):
    return isinstance(value, str) and len(value) == 32 and all(c in "0123456789abcdef" for c in value)


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

    @classmethod
    def from_dict(cls, data):
        if isinstance(data, cls):
            return copy.deepcopy(data)
        result = cls(**(data or {}))
        if not math.isfinite(result.timeline_zoom) or not 1 <= result.timeline_zoom <= 100000:
            raise ValueError("Invalid Group timeline zoom")
        if result.frame < 0 or result.source_frame < 0 or result.page not in range(5) or result.editor_tab not in (0, 1):
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


@dataclass
class ProjectLibrary:
    version: int = 1
    groups: dict[str, Group] = field(default_factory=dict)
    resources: dict[str, LibraryResource] = field(default_factory=dict)

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
        result = cls(data.get("version", 1), groups, {k: LibraryResource(**v) for k, v in data.get("resources", {}).items()})
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
            key = group.parent_id, group.name.casefold()
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

    def add_group(self, name, parent_id=None, index=None):
        if parent_id is not None and parent_id not in self.groups:
            raise ValueError("Please create a Group first")
        siblings = self.children(parent_id)
        group = Group(unique_name(name, [g.name for g in siblings]), parent_id=parent_id, order=len(siblings))
        self.groups[group.id] = group
        if index is not None:
            self.move_group(group.id, parent_id, index)
        return group

    def rename_group(self, ident, name):
        group = self.groups[ident]
        group.name = unique_name(name, [g.name for g in self.children(group.parent_id) if g.id != ident])
        return group.name

    def move_group(self, ident, parent_id, index=None):
        if parent_id is not None and parent_id not in self.groups:
            raise ValueError("Group parent does not exist")
        if parent_id in self.descendants(ident):
            raise ValueError("Cannot move a Group into itself or its children")
        group = self.groups[ident]
        siblings = [g for g in self.children(parent_id) if g.id != ident]
        group.name = unique_name(group.name, [g.name for g in siblings])
        group.parent_id = parent_id
        siblings.insert(len(siblings) if index is None else max(0, min(index, len(siblings))), group)
        for order, item in enumerate(siblings):
            item.order = order

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
        self.refresh_status()

    def refresh_status(self, processing=()):
        processing = set(processing)
        for group in self.groups.values():
            rows = self.in_group(group.id, True)
            group.status = "PROCESSING" if any(r.animation_id in processing for r in rows) else "WARNING" if any(r.warning for r in rows) else "READY" if any(r.ready and r.kind in {"ANIMATION", "SOURCE_SPRITE_SHEET", "GENERATED_SPRITE_SHEET"} for r in rows) else "SOURCE_ONLY" if rows else "EMPTY"
