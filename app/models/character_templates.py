"""Data-driven Character templates; Phase 2C will extend them with Animation Set metadata."""
from __future__ import annotations
from dataclasses import dataclass, field

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
class CharacterTemplate:
    id: str
    version: int
    label: str
    groups: tuple[TemplateGroup, ...] = ()

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
    group("Reaction/Death", "reaction")))
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
        return character


def default_registry():
    return CharacterTemplateRegistry((BLANK_TEMPLATE, PLAYER_TEMPLATE, ENEMY_TEMPLATE, BOSS_TEMPLATE))


REGISTRY = default_registry()
