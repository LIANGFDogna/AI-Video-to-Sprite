"""Data-driven Character templates: Group trees plus the Animation Sets they preset (Phase 2D)."""
from __future__ import annotations
from dataclasses import dataclass, field

from app.models.animation_set import AnimationSlot, normalize_key

BLANK = "blank"
PLAYER = "player_metroidvania"
ENEMY = "enemy_basic"
BOSS = "boss_basic"


@dataclass(frozen=True)
class TemplateGroup:
    path: tuple[str, ...]
    semantic_type: str = ""


def group(path, semantic_type=""):
    return TemplateGroup(tuple(path.split("/")), semantic_type)


@dataclass(frozen=True)
class TemplateSetSlot:
    key: str
    display_name: str
    semantic_type: str = ""
    required: bool = True
    repeat_count: int = 1


@dataclass(frozen=True)
class TemplateMachineState:
    name: str
    animation_name: str | None = None
    set_name: str | None = None
    position: tuple[float, float] = (0.0, 0.0)


@dataclass(frozen=True)
class TemplateMachineTransition:
    from_state: str
    to_state: str
    conditions: tuple = ()
    priority: int = 0
    exit_time: float = 0.0
    interruptible: bool = True


@dataclass(frozen=True)
class TemplateMachine:
    name: str
    states: tuple[TemplateMachineState, ...]
    transitions: tuple[TemplateMachineTransition, ...]
    parameters: tuple[tuple[str, str, object], ...] = ()


@dataclass(frozen=True)
class TemplateSet:
    name: str
    semantic_type: str
    slots: tuple[TemplateSetSlot, ...]
    pre_animation_name: str | None = None
    post_animation_name: str | None = None
    default_create: bool = True


@dataclass(frozen=True)
class CharacterTemplate:
    id: str
    version: int
    label: str
    groups: tuple[TemplateGroup, ...] = ()
    sets: tuple[TemplateSet, ...] = ()
    machines: tuple[TemplateMachine, ...] = ()

    def create_state_machines(self, library, character):
        """Create or extend template State Machines. Missing content is skipped, never duplicated."""
        created = []
        # Bind the Character's Animation Set slots first so Set-backed States resolve immediately.
        for animation_set in library.animation_sets_for(character.id):
            library.auto_match_set(animation_set.id)
        for template in self.machines:
            machine = next((row for row in library.state_machines_for(character.id) if row.name == template.name), None)
            new = machine is None
            if new:
                machine = library.add_state_machine(character.id, template.name,
                    parameters=[dict(name=name, type=kind, default=default) for name, kind, default in template.parameters])
            added, skipped = [], []
            for state in template.states:
                if machine.state_by_name(state.name) is not None:
                    continue
                animation_id = set_id = None
                if state.set_name:
                    row = next((item for item in library.animation_sets_for(character.id) if item.name == state.set_name), None)
                    set_id = row.id if row else None
                elif state.animation_name:
                    row = next((resource for resource in library.resources.values()
                        if resource.kind == "ANIMATION" and self.owns(library, character, resource)
                        and normalize_key(resource.name) == normalize_key(state.animation_name)), None)
                    animation_id = row.animation_id if row else None
                if state.set_name and set_id is None or state.animation_name and animation_id is None:
                    skipped.append(state.name)
                    continue
                added.append(machine.add_state(state.name, kind="set" if set_id else "animation",
                    animation_id=animation_id, set_id=set_id, position=state.position))
            for transition in template.transitions:
                source = machine.state_by_name(transition.from_state)
                target = machine.state_by_name(transition.to_state)
                if source is None or target is None:
                    continue
                if any(row.from_state == source.id and row.to_state == target.id for row in machine.transitions):
                    continue
                machine.add_transition(source.id, target.id,
                    conditions=[dict(parameter=name, operator=operator, value=value) for name, operator, value in transition.conditions],
                    priority=transition.priority, exit_time=transition.exit_time, interruptible=transition.interruptible)
            if machine.entry_state is None and machine.states:
                machine.entry_state = machine.states[0].id
            machine.validate()
            created.append((machine, new, added, skipped))
        return created

    def create_animation_sets(self, library, character, only_default=True):
        "Create template Sets once; existing Sets are never duplicated or overwritten."
        created = []
        existing = {row.name.casefold() for row in library.animation_sets_for(character.id)}
        for template_set in self.sets:
            if template_set.name.casefold() in existing:
                continue
            if only_default and not template_set.default_create:
                continue
            slots = [AnimationSlot(slot.display_name, semantic_type=slot.semantic_type or slot.key,
                required=slot.required, repeat_count=slot.repeat_count) for slot in template_set.slots]
            row = library.add_animation_set(character.id, template_set.name, template_set.semantic_type, slots)
            library.auto_match_set(row.id)
            for attribute, name in (("pre_animation", template_set.pre_animation_name),
                                    ("post_animation", template_set.post_animation_name)):
                if not name:
                    continue
                found = next((resource for resource in library.resources.values()
                    if resource.kind == "ANIMATION" and self.owns(library, character, resource)
                    and normalize_key(resource.name) == normalize_key(name)), None)
                setattr(row, attribute, found.animation_id if found else None)
            created.append(row)
        return created

    @staticmethod
    def owns(library, character, resource):
        group = library.groups.get(resource.group_id)
        return group is not None and group.character_id == character.id

    @property
    def top_level(self):
        return tuple(dict.fromkeys(entry.path[0] for entry in self.groups))

    def create_groups(self, library, character):
        """Create the template tree once; later edits are never constrained by the template."""
        created = []
        for entry in self.groups:
            parent_id = None
            for depth, name in enumerate(entry.path):
                existing = next((row for row in library.children(parent_id)
                    if row.name == name and row.character_id == character.id), None)
                if existing is None:
                    existing = library.add_group(name, parent_id, character_id=character.id,
                        semantic_type=entry.semantic_type if depth == len(entry.path) - 1 else "")
                    created.append(existing.id)
                parent_id = existing.id
        return created


BLANK_TEMPLATE = CharacterTemplate(BLANK, 1, "Blank Character")
PLAYER_SETS = (
    TemplateSet("Jump", "jump", (
        TemplateSetSlot("jump_up", "JumpUp", "jump_up"),
        TemplateSetSlot("fall_loop", "FallLoop", "fall_loop", repeat_count=2),
        TemplateSetSlot("land", "Land", "land")), pre_animation_name="Idle"),
    TemplateSet("Combat", "combat", (
        TemplateSetSlot("attack_1", "Attack1", "attack_1"),
        TemplateSetSlot("attack_2", "Attack2", "attack_2"),
        TemplateSetSlot("attack_3", "Attack3", "attack_3")), pre_animation_name="Idle"),
    TemplateSet("Dash", "dash", (
        TemplateSetSlot("ground_dash", "GroundDash", "ground_dash"),
        TemplateSetSlot("air_dash", "AirDash", "air_dash"))),
    TemplateSet("Wall", "wall", (
        TemplateSetSlot("wall_slide", "WallSlide", "wall_slide"),
        TemplateSetSlot("wall_climb", "WallClimb", "wall_climb"),
        TemplateSetSlot("wall_jump", "WallJump", "wall_jump"),
        TemplateSetSlot("mantle", "Mantle", "mantle")), default_create=False),
)


PLAYER_MACHINE = TemplateMachine("Character",
    states=(
        TemplateMachineState("Idle", animation_name="Idle", position=(0.0, 0.0)),
        TemplateMachineState("Run", animation_name="Run", position=(220.0, 0.0)),
        TemplateMachineState("Jump", set_name="Jump", position=(440.0, -120.0)),
        TemplateMachineState("Dash", set_name="Dash", position=(440.0, 120.0)),
        TemplateMachineState("Attack", set_name="Combat", position=(660.0, 0.0)),
        TemplateMachineState("Hurt", animation_name="Hurt", position=(220.0, -220.0)),
        TemplateMachineState("Death", animation_name="Death", position=(440.0, -320.0))),
    transitions=(
        TemplateMachineTransition("Idle", "Run", (("speed", ">", 0),)),
        TemplateMachineTransition("Run", "Idle", (("speed", "<=", 0),)),
        TemplateMachineTransition("Idle", "Jump", (("jump", "==", True),)),
        TemplateMachineTransition("Run", "Jump", (("jump", "==", True),)),
        TemplateMachineTransition("Jump", "Idle", (("is_on_floor", "==", True),)),
        TemplateMachineTransition("Idle", "Dash", (("dash", "==", True),)),
        TemplateMachineTransition("Run", "Dash", (("dash", "==", True),)),
        TemplateMachineTransition("Dash", "Idle", (("speed", "<=", 0),)),
        TemplateMachineTransition("Idle", "Attack", (("attack", "==", True),)),
        TemplateMachineTransition("Run", "Attack", (("attack", "==", True),)),
        TemplateMachineTransition("Attack", "Idle"),
        TemplateMachineTransition("Idle", "Hurt", (("hurt", "==", True),), priority=10),
        TemplateMachineTransition("Run", "Hurt", (("hurt", "==", True),), priority=10),
        TemplateMachineTransition("Jump", "Hurt", (("hurt", "==", True),), priority=10),
        TemplateMachineTransition("Dash", "Hurt", (("hurt", "==", True),), priority=10),
        TemplateMachineTransition("Attack", "Hurt", (("hurt", "==", True),), priority=10),
        TemplateMachineTransition("Hurt", "Idle"),
        TemplateMachineTransition("Idle", "Death", (("death", "==", True),), priority=20),
        TemplateMachineTransition("Run", "Death", (("death", "==", True),), priority=20),
        TemplateMachineTransition("Hurt", "Death", (("death", "==", True),), priority=20)),
    parameters=(("speed", "float", 0), ("is_on_floor", "bool", True), ("jump", "trigger", False),
        ("dash", "trigger", False), ("attack", "trigger", False), ("hurt", "trigger", False), ("death", "trigger", False)))


PLAYER_TEMPLATE = CharacterTemplate(PLAYER, 1, "Metroidvania Player", (
    group("Idle", "idle"),
    group("Movement/Walk", "locomotion"), group("Movement/Run", "locomotion"),
    group("Movement/Sprint", "locomotion"), group("Movement/Turn", "locomotion"),
    group("Jump/JumpUp", "jump"), group("Jump/FallLoop", "jump"),
    group("Jump/Land", "jump"), group("Jump/DoubleJump", "jump"),
    group("Dash/GroundDash", "dash"), group("Dash/AirDash", "dash"),
    group("Wall/WallSlide", "wall"), group("Wall/WallClimb", "wall"),
    group("Wall/WallJump", "wall"), group("Wall/Mantle", "wall"),
    group("Combat/Attack1", "combat"), group("Combat/Attack2", "combat"),
    group("Combat/Attack3", "combat"), group("Combat/UpAttack", "combat"),
    group("Combat/DownAttack", "combat"),
    group("AirCombat/AirAttack", "air_combat"), group("AirCombat/AirAttackUp", "air_combat"),
    group("AirCombat/AirAttackDown", "air_combat"),
    group("Interaction/LookUp", "interaction"), group("Interaction/LookDown", "interaction"),
    group("Interaction/Crouch", "interaction"), group("Interaction/Push", "interaction"),
    group("Interaction/Pull", "interaction"),
    group("Reaction/Hurt", "reaction"), group("Reaction/Knockback", "reaction"),
    group("Reaction/Death", "reaction")), sets=PLAYER_SETS, machines=(PLAYER_MACHINE,))
ENEMY_TEMPLATE = CharacterTemplate(ENEMY, 1, "Enemy", (
    group("Idle", "idle"), group("Walk", "locomotion"), group("Run", "locomotion"),
    group("Attack", "combat"), group("Hurt", "reaction"),
    group("Knockback", "reaction"), group("Death", "reaction")))
BOSS_TEMPLATE = CharacterTemplate(BOSS, 1, "Boss", (
    group("Idle", "idle"), group("Move", "locomotion"),
    group("Phase/Phase1", "phase"), group("Phase/Phase2", "phase"), group("Phase/Phase3", "phase"),
    group("Attack/Attack1", "combat"), group("Attack/Attack2", "combat"), group("Attack/Attack3", "combat"),
    group("Special", "combat"), group("Hurt", "reaction"), group("Stagger", "reaction"),
    group("Death", "reaction"), group("Intro", "reaction")))


class CharacterTemplateRegistry:
    def __init__(self, templates=()):
        self._templates = {}
        for template in templates:
            self.register(template)

    def register(self, template):
        self._templates[template.id] = template
        return template

    def get(self, ident):
        if ident not in self._templates:
            raise ValueError("Unknown Character template")
        return self._templates[ident]

    def ids(self):
        return list(self._templates)

    def templates(self):
        return list(self._templates.values())

    def create_character(self, library, name, template_id, reference=None):
        template = self.get(template_id)
        character = library.add_character(name, template.id, template.version, reference=reference)
        template.create_groups(library, character)
        library.refresh_character_groups()
        if template.sets:
            template.create_animation_sets(library, character)
        return character


def default_registry():
    return CharacterTemplateRegistry((BLANK_TEMPLATE, PLAYER_TEMPLATE, ENEMY_TEMPLATE, BOSS_TEMPLATE))


REGISTRY = default_registry()
