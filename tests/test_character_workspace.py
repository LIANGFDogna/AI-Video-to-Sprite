"""Phase 2B: Character hierarchy, templates, ownership and Reference isolation."""
from dataclasses import asdict
from pathlib import Path
import numpy as np
from PIL import Image
import pytest
from PySide6.QtCore import Qt
from app.models.character_reference import AnimationTransform, CharacterReference
from app.models.character_templates import BLANK, BOSS, ENEMY, PLAYER, REGISTRY
from app.models.project import Project
from app.models.project_library import TaskContext
from app.core.group_export import group_disk_paths, plan_group_export, export_group_plan
from app.core.pipeline import Pipeline
from app.utils.paths import cache_directory
from app.i18n import t
from app.ui.dialogs import MessageBox
from test_group_workspace_ui import cached_clip, window
from test_workspace_ui import close_window, events, qt


def animation_folder(tmp_path, name, count=3):
    folder = tmp_path / name
    folder.mkdir()
    for index in range(count):
        rgba = np.zeros((24, 24, 4), np.uint8)
        rgba[6 + index:14 + index, 6:14] = (200, 90, 40, 190)
        Image.fromarray(rgba).save(folder / f"{index:04d}.png")
    return folder


def add_animation(project, group_id, tmp_path, name="Idle", project_file=None):
    project.current_group_id = group_id
    project = project.import_frame_sequence(animation_folder(tmp_path, name))
    target = project_file or (tmp_path / "p.aivsprite")
    Pipeline(project, cache_directory(project.project_id, target, project.animation_id)).build()
    project.library.mark_generated(project.animation_id)
    return project


def reference(animation_id, x=48, y=86, width=96, height=96):
    return CharacterReference(animation_id, 0, x, y, width, height)


def test_empty_character_has_no_groups_and_stable_unique_ids():
    project = Project()
    character = REGISTRY.create_character(project.library, "NPC_A", BLANK)
    assert character.template_id == "blank" and character.template_version == 1
    assert project.library.character_members(character.id) == []
    assert project.library.character_animation_count(character.id) == 0
    assert project.library.character_roots(character.id) == []
    assert len(character.id) == 32 and character.created_at and character.modified_at
    twin = REGISTRY.create_character(project.library, "NPC_A", BLANK)
    assert twin.id != character.id and twin.name == "NPC_A 2"


@pytest.mark.parametrize("template_id,expected", [(PLAYER, 39), (ENEMY, 7), (BOSS, 15)])
def test_templates_create_complete_group_trees(template_id, expected):
    project = Project()
    character = REGISTRY.create_character(project.library, "Hero", template_id)
    members = project.library.character_members(character.id)
    assert len(members) == expected
    assert all(row.character_id == character.id for row in members)
    template = REGISTRY.get(template_id)
    for entry in template.groups:
        parent = None
        for depth, name in enumerate(entry.path):
            parent = next(row for row in project.library.children(parent.id if parent else None) if row.name == name)
            if depth == len(entry.path) - 1 and entry.semantic_type:
                assert parent.semantic_type == entry.semantic_type
    assert project.library.characters[character.id].group_ids == sorted(row.id for row in members)
    project.library.validate()


def test_player_template_top_level_matches_specification():
    project = Project()
    character = REGISTRY.create_character(project.library, "Hero", PLAYER)
    assert [row.name for row in project.library.character_roots(character.id)] == [
        "Idle", "Movement", "Jump", "Dash", "Wall", "Combat", "AirCombat", "Interaction", "Reaction"]
    movement = next(row for row in project.library.character_roots(character.id) if row.name == "Movement")
    assert [row.name for row in project.library.children(movement.id)] == ["Walk", "Run", "Sprint", "Turn"]
    jump = next(row for row in project.library.character_roots(character.id) if row.name == "Jump")
    assert [row.name for row in project.library.children(jump.id)] == ["JumpUp", "FallLoop", "Land", "DoubleJump"]
    enemy = REGISTRY.create_character(project.library, "Foe", ENEMY)
    assert [row.name for row in project.library.character_roots(enemy.id)] == [
        "Idle", "Walk", "Run", "Attack", "Hurt", "Knockback", "Death"]
    boss = REGISTRY.create_character(project.library, "Big", BOSS)
    assert [row.name for row in project.library.character_roots(boss.id)] == [
        "Idle", "Move", "Phase", "Attack", "Special", "Hurt", "Stagger", "Death", "Intro"]


def test_loose_group_has_no_character_and_joins_one_explicitly(tmp_path):
    project = Project()
    loose = project.library.add_group("Loose")
    assert loose.character_id is None and project.library.loose_roots()[0].id == loose.id
    character = REGISTRY.create_character(project.library, "Boss", BLANK)
    project.library.set_group_character(loose.id, character.id)
    assert project.library.groups[loose.id].character_id == character.id
    assert not project.library.loose_roots()
    project.library.validate()


def test_nested_group_inherits_character_and_cannot_mix(tmp_path):
    project = Project()
    hero = REGISTRY.create_character(project.library, "Hero", PLAYER)
    child = project.library.add_group("Extra", parent_id=project.library.character_roots(hero.id)[0].id)
    assert child.character_id == hero.id
    loose = project.library.add_group("Loose")
    original = project.library.groups[child.id].character_id
    project.library.groups[child.id].character_id = None
    with pytest.raises(ValueError):
        project.library.validate()
    project.library.groups[child.id].character_id = original
    project.library.validate()
    other = REGISTRY.create_character(project.library, "Other", BLANK)
    project.library.set_group_character(child.id, other.id)
    assert project.library.groups[child.id].character_id == other.id


def test_cross_character_move_keeps_offsets_and_marks_review(tmp_path):
    project = Project()
    hero = REGISTRY.create_character(project.library, "Hero", BLANK)
    boss = REGISTRY.create_character(project.library, "Boss", BLANK)
    group = project.library.add_group("Run", None, character_id=hero.id)
    project = add_animation(project, group.id, tmp_path, "Run")
    animation_id = project.animation_id
    project.animation_transform = AnimationTransform(-12, 4)
    project.library.set_group_character(group.id, boss.id)
    moved = project.select_animation(animation_id)
    assert moved.animation_transform == AnimationTransform(-12, 4)
    assert moved.library.groups[group.id].alignment_review_required is True
    assert moved.library.groups[group.id].character_id == boss.id
    assert not moved.library.characters[hero.id].group_ids


def test_character_references_are_independent_and_persisted(tmp_path):
    project = Project(project_name="Game")
    player = REGISTRY.create_character(project.library, "Player", BLANK)
    boss = REGISTRY.create_character(project.library, "Boss", BLANK)
    player_group = project.library.add_group("Idle", None, character_id=player.id)
    boss_group = project.library.add_group("BossIdle", None, character_id=boss.id)
    project = add_animation(project, player_group.id, tmp_path, "PlayerIdle")
    player_animation = project.animation_id
    project = add_animation(project, boss_group.id, tmp_path, "BossIdle")
    boss_animation = project.animation_id
    project.library.characters[player.id].character_reference = reference(player_animation, x=48)
    project.library.characters[boss.id].character_reference = reference(boss_animation, x=80)
    project.library.validate()
    path = tmp_path / "Game.aivsprite"
    project.current_character_id = player.id
    project.sync_character_reference()
    project.save(path)
    restored = Project.load(path)
    assert restored.library.characters[player.id].character_reference.origin_x == 48
    assert restored.library.characters[boss.id].character_reference.origin_x == 80
    assert restored.library.characters[player.id].template_id == "blank"
    assert restored.library.characters[player.id].template_version == 1
    restored.current_group_id = boss_group.id
    restored.current_character_id = boss.id
    restored.sync_character_reference()
    assert restored.character_reference.origin_x == 80
    restored.current_group_id = player_group.id
    restored.current_character_id = player.id
    restored.sync_character_reference()
    assert restored.character_reference.origin_x == 48


def test_reference_must_belong_to_the_same_character(tmp_path):
    project = Project()
    player = REGISTRY.create_character(project.library, "Player", BLANK)
    boss = REGISTRY.create_character(project.library, "Boss", BLANK)
    boss_group = project.library.add_group("BossIdle", None, character_id=boss.id)
    player_group = project.library.add_group("Idle", None, character_id=player.id)
    project = add_animation(project, boss_group.id, tmp_path, "BossIdle")
    foreign = project.animation_id
    project = add_animation(project, player_group.id, tmp_path, "Idle")
    project.library.characters[player.id].character_reference = reference(project.animation_id)
    project.library.validate()
    project.library.characters[player.id].character_reference = reference(foreign)
    with pytest.raises(ValueError):
        project.library.validate()


def test_moving_the_reference_group_requires_clearing_the_reference(tmp_path):
    project = Project()
    player = REGISTRY.create_character(project.library, "Player", BLANK)
    boss = REGISTRY.create_character(project.library, "Boss", BLANK)
    group = project.library.add_group("Idle", None, character_id=player.id)
    project = add_animation(project, group.id, tmp_path, "Idle")
    project.library.characters[player.id].character_reference = reference(project.animation_id)
    with pytest.raises(ValueError):
        project.library.set_group_character(group.id, boss.id)
    assert project.library.characters[player.id].character_reference is not None
    project.library.set_group_character(group.id, boss.id, clear_references=True)
    assert project.library.characters[player.id].character_reference is None
    assert project.library.groups[group.id].character_id == boss.id
    project.library.validate()


def test_delete_character_moves_groups_to_loose_and_rename_keeps_ids(tmp_path):
    project = Project()
    boss = REGISTRY.create_character(project.library, "Boss", BOSS)
    group = project.library.character_roots(boss.id)[0]
    project = add_animation(project, group.id, tmp_path, "BossIdle")
    reference_animation = project.animation_id
    project.library.characters[boss.id].character_reference = reference(reference_animation)
    group_ids = sorted(row.id for row in project.library.character_members(boss.id))
    root_ids = sorted(row.id for row in project.library.character_roots(boss.id))
    project.library.rename_character(boss.id, "首领")
    assert project.library.characters[boss.id].name == "首领"
    assert sorted(row.id for row in project.library.character_members(boss.id)) == group_ids
    assert project.library.characters[boss.id].character_reference is not None
    project.library.remove_character(boss.id, move_to_loose=True)
    assert boss.id not in project.library.characters
    assert all(project.library.groups[ident].character_id is None for ident in group_ids)
    assert sorted(row.id for row in project.library.loose_roots()) == root_ids
    assert all(project.library.groups[ident].character_id is None for ident in group_ids)
    project.library.validate()


def test_delete_character_refuses_without_move_flag(tmp_path):
    project = Project()
    hero = REGISTRY.create_character(project.library, "Hero", ENEMY)
    with pytest.raises(ValueError):
        project.library.remove_character(hero.id, move_to_loose=False)
    assert hero.id in project.library.characters


def test_legacy_reference_migrates_to_default_character(tmp_path):
    project = Project(source_video=str(tmp_path / "Idle.mp4"))
    project.character_reference = reference(project.animation_id, x=64)
    legacy = asdict(project)
    legacy.pop("library")
    legacy.pop("current_character_id")
    restored = Project.from_dict(legacy)
    assert len(restored.library.characters) == 1
    character = next(iter(restored.library.characters.values()))
    assert character.name == "Default Character"
    assert character.character_reference == project.character_reference
    assert restored.current_character_id == character.id
    assert all(row.character_id == character.id for row in restored.library.groups.values())
    restored.library.validate()


def test_legacy_project_without_reference_keeps_loose_groups(tmp_path):
    project = Project(source_video=str(tmp_path / "Idle.mp4"))
    assert project.character_reference is None
    legacy = asdict(project)
    legacy.pop("library")
    legacy.pop("current_character_id")
    restored = Project.from_dict(legacy)
    assert not restored.library.characters
    assert restored.library.groups
    assert all(row.character_id is None for row in restored.library.groups.values())
    assert restored.current_group_id in restored.library.groups


def test_task_context_carries_character_id():
    context = TaskContext("project", "group", "animation", "key", "character")
    assert (context.project_id, context.character_id, context.group_id, context.animation_id) == (
        "project", "character", "group", "animation")
    assert TaskContext("project", "group", "animation", "key").character_id is None


def test_export_tree_path_includes_character(tmp_path):
    project = Project()
    player = REGISTRY.create_character(project.library, "Player", BLANK)
    boss = REGISTRY.create_character(project.library, "Boss", BLANK)
    movement = project.library.add_group("Movement", None, character_id=player.id)
    run = project.library.add_group("Run", movement.id)
    boss_idle = project.library.add_group("Idle", None, character_id=boss.id)
    loose = project.library.add_group("Loose")
    paths = group_disk_paths(project.library)
    assert paths[run.id] == Path("Player") / "Movement" / "Run"
    assert paths[boss_idle.id] == Path("Boss") / "Idle"
    assert paths[loose.id] == Path("Loose")
    project = add_animation(project, run.id, tmp_path, "Run", tmp_path / "p.aivsprite")
    plan = plan_group_export(project, tmp_path / "p.aivsprite", [movement.id, boss_idle.id, loose.id])
    assert plan.items[0].relative_directory == Path("Player") / "Movement" / "Run" / "Run"
    destination = tmp_path / "Export"
    destination.mkdir()
    export_group_plan(plan, destination)
    assert (destination / "Player" / "Movement" / "Run" / "Run" / "sprite_sheet.png").is_file()
    assert (destination / "Boss" / "Idle").is_dir()


def test_character_tree_search_selection_counts_and_dialog(qt, tmp_path):
    w = window(qt, tmp_path)
    try:
        c = w.library_controller
        hero = c.new_character(name="主角玩家", template_id=PLAYER)
        boss = c.new_character(name="Boss", template_id=BOSS)
        panel = w.library_panel
        assert panel.items[("CHARACTER", hero.id)].text(0) == "主角玩家"
        assert panel.items[("CHARACTER", hero.id)].text(1) == "0"
        assert panel.items[("CHARACTER", hero.id)].icon(0).isNull() is False
        idle = next(row for row in w.project.library.character_roots(hero.id) if row.name == "Idle")
        c.select_group(idle.id)
        cached_clip(w, idle.id, "Idle")
        assert w.project.library.character_animation_count(hero.id) == 1
        panel.refresh()
        assert panel.items[("CHARACTER", hero.id)].text(1) == "1"
        panel.search.setText("Boss")
        assert not panel.items[("CHARACTER", boss.id)].isHidden()
        assert panel.items[("CHARACTER", hero.id)].isHidden()
        panel.search.clear()
        c.select_character(hero.id)
        assert w.views.currentWidget() is w.character_page
        assert "主角玩家" in w.character_page.title.text()
        assert not w.worker and w.last_error is None
        c.select_character(boss.id)
        assert w.views.currentWidget() is w.character_page
        assert "Boss" in w.character_page.title.text()
    finally:
        close_window(qt, w)


def test_controller_move_delete_and_reference_prompt(qt, tmp_path, monkeypatch):
    w = window(qt, tmp_path)
    try:
        c = w.library_controller
        hero = c.new_character(name="Hero", template_id=BLANK)
        boss = c.new_character(name="Boss", template_id=BLANK)
        group = w.project.library.add_group("Loose", None)
        c.select_group(group.id)
        cached_clip(w, group.id, "Idle")
        animation_id = w.project.animation_id
        c.move_to_character(group.id, boss.id)
        assert w.project.library.groups[group.id].character_id == boss.id
        assert w.project.library.groups[group.id].alignment_review_required is True
        assert w.project.select_animation(animation_id).animation_transform == AnimationTransform(0, 0)
        w.project.library.characters[boss.id].character_reference = reference(animation_id)
        w.project.sync_character_reference()
        monkeypatch.setattr(MessageBox, "question", staticmethod(lambda *args, **kwargs: MessageBox.StandardButton.Cancel))
        c.move_to_character(group.id, hero.id)
        assert w.project.library.groups[group.id].character_id == boss.id
        monkeypatch.setattr(MessageBox, "question", staticmethod(lambda *args, **kwargs: MessageBox.StandardButton.Yes))
        c.move_to_character(group.id, hero.id)
        assert w.project.library.groups[group.id].character_id == hero.id
        assert w.project.library.characters[boss.id].character_reference is None
        c.rename("CHARACTER", hero.id, "英雄")
        assert w.project.library.characters[hero.id].name == "英雄"
        c.remove_character(boss.id, confirmed=True)
        assert boss.id not in w.project.library.characters
        assert not w.project.library.characters[boss.id].group_ids if boss.id in w.project.library.characters else True
    finally:
        close_window(qt, w)


def test_character_dialog_preview_lists_template_groups(qt, tmp_path):
    w = window(qt, tmp_path)
    try:
        dialog = CharacterDialogForTest(w)
        dialog.template.setCurrentIndex(dialog.template.findData(PLAYER))
        text = dialog.preview.toPlainText()
        assert "Idle" in text and "Movement" in text and "Reaction" in text
        dialog.name.setText("主角玩家")
        assert dialog.create.isEnabled()
        dialog.template.setCurrentIndex(dialog.template.findData(BLANK))
        assert dialog.preview.toPlainText() == t("This Character starts empty. Create Groups yourself.")
        dialog.reject()
    finally:
        close_window(qt, w)


def CharacterDialogForTest(host):
    from app.ui.character_dialogs import CharacterDialog
    return CharacterDialog(host, REGISTRY)
