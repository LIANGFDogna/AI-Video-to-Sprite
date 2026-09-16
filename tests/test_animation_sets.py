"""Phase 2D: Animation Set model, ownership, auto-match, preview scheduling and export."""
from dataclasses import asdict
import json
import numpy as np
from PIL import Image
import pytest
from app.core.pipeline import Pipeline
from app.core.set_export import animation_set_metadata, export_animation_set, plan_animation_set
from app.core.set_preview import SetPreviewProvider, set_segments
from app.models.animation_set import AnimationSet, AnimationSlot
from app.models.character_templates import BOSS, PLAYER, REGISTRY
from app.models.project import Project
from app.utils.paths import cache_directory
from test_workspace_ui import close_window, events, qt


def sequence(tmp_path, name, count=4):
    folder = tmp_path / name
    folder.mkdir(exist_ok=True)
    for index in range(count):
        pixels = np.zeros((16, 16, 4), np.uint8)
        pixels[4:10, 4 + index:9 + index] = (80, 30, 190, 140)
        Image.fromarray(pixels).save(folder / f"{index:04d}.png")
    return folder


def player(tmp_path, name="Player"):
    project = Project(project_name="Game")
    character = REGISTRY.create_character(project.library, name, PLAYER)
    return project, character


def ready_animation(project, tmp_path, group_id, name, project_file):
    project.current_group_id = group_id
    project = project.import_frame_sequence(sequence(tmp_path, name))
    Pipeline(project, cache_directory(project.project_id, project_file, project.animation_id)).build()
    project.library.mark_generated(project.animation_id)
    return project


def group_named(project, character, name):
    return next(row for row in project.library.character_roots(character.id) if row.name == name)


def jump_animations(project, tmp_path, character, project_file):
    for name in ("JumpUp", "FallLoop", "Land"):
        group = group_named(project, character, "Jump")
        child = next(row for row in project.library.children(group.id) if row.name == name)
        project = ready_animation(project, tmp_path, child.id, name, project_file)
    return project


def test_create_animation_set_and_uuid_stable(tmp_path):
    project, character = player(tmp_path)
    row = project.library.add_animation_set(character.id, "Custom", "custom",
        [AnimationSlot("A"), AnimationSlot("B", required=False)])
    assert row.id in project.library.animation_sets and len(row.id) == 32
    assert row.status == "EMPTY" and row.completion == (0, 1)
    assert [slot.display_name for slot in row.required_slots] == ["A"]
    assert [slot.display_name for slot in row.optional_slots] == ["B"]
    project.library.validate()
    assert project.library.animation_sets[row.id].id == row.id


def test_set_belongs_to_character_and_cross_character_binding_rejected(tmp_path):
    project, player_character = player(tmp_path)
    boss = REGISTRY.create_character(project.library, "Boss", BOSS)
    row = project.library.animation_sets_for(player_character.id)[0]
    assert row.character_id == player_character.id
    boss_group = next(group for group in project.library.character_roots(boss.id) if group.name == "Idle")
    project = ready_animation(project, tmp_path, boss_group.id, "BossIdle", tmp_path / "p.aivsprite")
    with pytest.raises(ValueError):
        project.library.bind_slot(row.id, row.slots[0].id, project.animation_id)
    project.library.validate()


def test_completion_states_and_bind_unbind(tmp_path):
    project, character = player(tmp_path)
    project_file = tmp_path / "p.aivsprite"
    project = jump_animations(project, tmp_path, character, project_file)
    row = next(item for item in project.library.animation_sets_for(character.id) if item.name == "Jump")
    assert row.status == "EMPTY" and row.completion == (0, 3)
    animations = [resource.animation_id for resource in project.library.resources.values() if resource.kind == "ANIMATION"]
    assert len(animations) == 3
    project.library.bind_slot(row.id, row.slots[0].id, animations[0])
    assert row.status == "INCOMPLETE" and row.completion == (1, 3)
    assert [slot.display_name for slot in row.missing_required] == ["FallLoop", "Land"]
    for slot, animation_id in zip(row.slots[1:], animations[1:]):
        project.library.bind_slot(row.id, slot.id, animation_id)
    assert row.status == "READY" and row.completion == (3, 3) and not row.missing_required
    project.library.bind_slot(row.id, row.slots[0].id, None)
    assert row.status == "INCOMPLETE" and row.slot_bindings.get(row.slots[0].id) is None
    project.library.validate()


def test_auto_match_by_semantic_type_then_name_fallback(tmp_path):
    project, character = player(tmp_path)
    project_file = tmp_path / "p.aivsprite"
    jump = group_named(project, character, "Jump")
    semantic_group = next(row for row in project.library.children(jump.id) if row.name == "FallLoop")
    semantic_group.semantic_type = "fall_loop"
    project = ready_animation(project, tmp_path, semantic_group.id, "Renamed Fall", project_file)
    renamed = next(row for row in project.library.children(jump.id) if row.name == "JumpUp")
    renamed.name = "JumpUp"
    project = ready_animation(project, tmp_path, renamed.id, "JumpUp", project_file)
    row = next(item for item in project.library.animation_sets_for(character.id) if item.name == "Jump")
    matched = project.library.auto_match_set(row.id)
    assert matched == 2, "semantic_type match plus name fallback"
    bound = {slot.display_name: project.library.animation(slot.animation_id).name for slot in row.slots if slot.animation_id}
    assert bound["FallLoop"] == "Renamed Fall", "semantic_type wins over the Animation name"
    assert bound["JumpUp"] == "JumpUp", "name fallback binds by id and stays stored"
    stored = project.library.animation_sets[row.id].slot_bindings
    assert stored == {slot.id: slot.animation_id for slot in row.slots if slot.animation_id}


def test_player_template_presets_jump_combat_dash(tmp_path):
    project, character = player(tmp_path)
    sets = {row.name: row for row in project.library.animation_sets_for(character.id)}
    assert set(sets) == {"Jump", "Combat", "Dash"}, "Wall stays opt-in and Enemy/Boss preset none"
    assert [slot.display_name for slot in sets["Jump"].slots] == ["JumpUp", "FallLoop", "Land"]
    assert [slot.display_name for slot in sets["Combat"].slots] == ["Attack1", "Attack2", "Attack3"]
    assert [slot.display_name for slot in sets["Dash"].slots] == ["GroundDash", "AirDash"]
    assert sets["Jump"].slots[1].repeat_count == 2 and sets["Jump"].semantic_type == "jump"
    project.library.validate()


def test_template_upgrade_creates_sets_without_duplicates(tmp_path):
    project = Project(project_name="Legacy")
    character = project.library.add_character("Player", PLAYER, 1)
    registry = REGISTRY.get(PLAYER)
    registry.create_groups(project.library, character)
    assert not project.library.animation_sets_for(character.id), "legacy characters start without Sets"
    created = registry.create_animation_sets(project.library, character)
    assert [row.name for row in created] == ["Jump", "Combat", "Dash"]
    again = registry.create_animation_sets(project.library, character)
    assert again == [] and len(project.library.animation_sets_for(character.id)) == 3


def test_rename_animation_keeps_binding_and_delete_requires_clear(tmp_path):
    project, character = player(tmp_path)
    project_file = tmp_path / "p.aivsprite"
    project = jump_animations(project, tmp_path, character, project_file)
    row = next(item for item in project.library.animation_sets_for(character.id) if item.name == "Jump")
    assert project.library.auto_match_set(row.id) == 3
    animation = project.library.animation(row.slots[0].animation_id)
    animation.name = "Jump Up Renamed"
    assert project.library.animation_sets[row.id].slots[0].animation_id == animation.animation_id
    with pytest.raises(ValueError):
        project.library.remove_animation(animation.id)
    assert project.library.animation(animation.animation_id) is not None
    project.library.remove_animation(animation.id, clear_sets=True)
    assert project.library.animation(animation.animation_id) is None
    assert project.library.animation_sets[row.id].slots[0].animation_id is None
    assert project.library.animation_sets[row.id].status == "INCOMPLETE"
    project.library.validate()


def test_cross_character_move_requires_clearing_set_bindings(tmp_path):
    project, player_character = player(tmp_path)
    project_file = tmp_path / "p.aivsprite"
    project = jump_animations(project, tmp_path, player_character, project_file)
    row = next(item for item in project.library.animation_sets_for(player_character.id) if item.name == "Jump")
    project.library.auto_match_set(row.id)
    boss = REGISTRY.create_character(project.library, "Boss", BOSS)
    jump = group_named(project, player_character, "Jump")
    with pytest.raises(ValueError):
        project.library.set_group_character(jump.id, boss.id)
    assert project.library.groups[jump.id].character_id == player_character.id
    assert project.library.animation_sets[row.id].slots[0].animation_id is not None
    project.library.set_group_character(jump.id, boss.id, clear_sets=True)
    assert project.library.groups[jump.id].character_id == boss.id
    assert project.library.animation_sets[row.id].slot_bindings == {}
    assert project.library.animation_sets[row.id].status == "EMPTY"
    project.library.validate()


def test_preview_sequence_repeat_and_context(tmp_path):
    project, character = player(tmp_path)
    project_file = tmp_path / "p.aivsprite"
    idle_group = group_named(project, character, "Idle")
    project = ready_animation(project, tmp_path, idle_group.id, "Idle", project_file)
    idle_animation = project.animation_id
    project = jump_animations(project, tmp_path, character, project_file)
    row = next(item for item in project.library.animation_sets_for(character.id) if item.name == "Jump")
    assert project.library.auto_match_set(row.id) == 3
    project.library.animation_sets[row.id].pre_animation = idle_animation
    project.library.animation_sets[row.id].post_animation = idle_animation
    row = project.library.animation_sets[row.id]
    ids = [segment.animation_id for segment in set_segments(row)]
    assert ids[0] == idle_animation and ids[-1] == idle_animation, "Idle is preview context, not a required slot"
    assert [slot.display_name for slot, _, _, _ in row.preview_timeline()] == ["JumpUp", "FallLoop", "Land"]
    assert [repeat for _, _, repeat, _ in row.preview_timeline()] == [1, 2, 1]
    assert [segment.transition for segment in set_segments(row, include_context=False)] == ["cut", "cut", "cut"]
    provider = SetPreviewProvider(project, project_file, row)
    labels = [provider.label(index) for index in range(len(provider))]
    assert labels[0].startswith("Idle (pre)")
    assert labels[-1].startswith("Idle (post)")
    assert any("FallLoop x2" in label for label in labels), "repeat_count repeats the segment without touching the source"


def test_set_preview_uses_final_frame_provider_with_offsets_and_corrections(tmp_path):
    project, character = player(tmp_path)
    project_file = tmp_path / "p.aivsprite"
    project = jump_animations(project, tmp_path, character, project_file)
    row = next(item for item in project.library.animation_sets_for(character.id) if item.name == "Jump")
    project.library.auto_match_set(row.id)
    row = project.library.animation_sets[row.id]
    target = row.slots[0].animation_id
    project = project.select_animation(target)
    project.animation_transform = type(project.animation_transform)(7, -5)
    project.set_frame_correction(1, 3, -4)
    provider = SetPreviewProvider(project, project_file, row)
    direct = Pipeline(project, cache_directory(project.project_id, project_file, target)) if False else None
    from app.core.final_frame_provider import FinalFrameProvider
    reference = FinalFrameProvider(project.select_animation(target), cache_directory(project.project_id, project_file, target), live_edit=True)
    assert len(provider) >= len(reference)
    assert np.array_equal(provider.get_final_frame(1), reference.get_final_frame(1)), "Animation Offset + Frame Correction apply inside the Set preview"
    assert not np.array_equal(provider.get_final_frame(0), provider.get_final_frame(1))


def test_set_export_structure_metadata_and_no_ghost(tmp_path):
    project, character = player(tmp_path)
    project_file = tmp_path / "p.aivsprite"
    project = jump_animations(project, tmp_path, character, project_file)
    row = next(item for item in project.library.animation_sets_for(character.id) if item.name == "Jump")
    project.library.auto_match_set(row.id)
    row = project.library.animation_sets[row.id]
    plan, warnings = plan_animation_set(project, project_file, row)
    assert len(plan) == 3 and not warnings
    destination = tmp_path / "Export"
    destination.mkdir()
    result = export_animation_set(project, project_file, row, destination)
    root = destination / "Jump"
    for name in ("JumpUp", "FallLoop", "Land"):
        folder = root / name
        assert folder.is_dir() and (folder / "sprite_sheet.png").is_file()
        assert (folder / "animation.json").is_file() and (folder / "root_motion.json").is_file()
    metadata_path = root / "animation_set.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["name"] == "Jump" and metadata["semantic_type"] == "jump"
    assert metadata["sequence"] == ["JumpUp", "FallLoop", "Land"]
    assert [state["next"] for state in metadata["godot"]] == ["FallLoop", "Land", None]
    assert metadata["godot"][1]["loop"] is True
    assert result["resources"] == 3
    with pytest.raises(FileExistsError):
        export_animation_set(project, project_file, row, destination)
    for item in plan:
        expected = (cache_directory(project.project_id, project_file, item["resource"].animation_id) / "sprite_sheet.png").read_bytes()
        assert (root / item["folder"] / "sprite_sheet.png").read_bytes() == expected, "export copies FinalFrameProvider results only; no editor overlay"


def test_save_reopen_sets_and_legacy_without_sets(tmp_path):
    project, character = player(tmp_path)
    project_file = tmp_path / "p.aivsprite"
    project = jump_animations(project, tmp_path, character, project_file)
    row = next(item for item in project.library.animation_sets_for(character.id) if item.name == "Jump")
    project.library.auto_match_set(row.id)
    project.library.animation_sets[row.id].slots[1].repeat_count = 3
    project.save(project_file)
    restored = Project.load(project_file)
    sets = {item.name: item for item in restored.library.animation_sets_for(character.id)}
    assert set(sets) == {"Jump", "Combat", "Dash"}
    assert sets["Jump"].id == row.id and sets["Jump"].character_id == character.id
    assert [slot.display_name for slot in sets["Jump"].slots] == ["JumpUp", "FallLoop", "Land"]
    assert sets["Jump"].slots[1].repeat_count == 3
    assert sets["Jump"].status == "READY"
    assert sets["Jump"].slot_bindings == row.slot_bindings, "bindings survive by animation_id"
    legacy = asdict(Project(source_video=str(tmp_path / "legacy.mp4")))
    legacy.pop("animation_sets", None)
    restored_legacy = Project.from_dict(legacy)
    assert restored_legacy.library.animation_sets == {}, "legacy projects never grow Sets on their own"
    assert not restored_legacy.library.animation_sets_for(next(iter(restored_legacy.library.characters.values())).id) if restored_legacy.library.characters else True

def test_panel_lists_sets_and_shows_slots(qt, tmp_path):
    from app.ui.dialogs import MessageBox
    from test_group_workspace_ui import window
    from test_workspace_ui import close_window
    w = window(qt, tmp_path)
    try:
        controller = w.library_controller
        character = controller.new_character(name='Player', template_id=PLAYER)
        controller.select_character(character.id)
        panel = w.character_page
        assert panel.sets_list.count() == 3
        labels = [panel.sets_list.item(index).text() for index in range(panel.sets_list.count())]
        assert any('Jump' in label and '0/3' in label for label in labels)
        assert any('Combat' in label for label in labels) and any('Dash' in label for label in labels)
        text = panel.set_slots.toPlainText()
        assert 'JumpUp' in text and 'FallLoop' in text and 'Land' in text
        assert '3' in text.split()[0] or '0/3' in text
        selected = panel.selected_set()
        assert selected in w.project.library.animation_sets
    finally:
        close_window(qt, w)


def test_template_upgrade_button_creates_missing_sets(qt, tmp_path):
    from test_group_workspace_ui import window
    from test_workspace_ui import close_window
    w = window(qt, tmp_path)
    try:
        library = w.project.library
        character = library.add_character('Legacy Player', PLAYER, 1)
        REGISTRY.get(PLAYER).create_groups(library, character)
        controller = w.library_controller
        controller.select_character(character.id)
        panel = w.character_page
        assert panel.sets_list.count() == 0
        created = controller.template_animation_sets()
        assert [row.name for row in created] == ['Jump', 'Combat', 'Dash']
        assert panel.sets_list.count() == 3, 'panel refreshes after the upgrade'
        assert controller.template_animation_sets() == [], 'no duplicates on a second click'
        assert panel.sets_list.count() == 3
    finally:
        close_window(qt, w)


def test_controller_binding_and_delete_protection_prompt(qt, tmp_path):
    from app.ui.dialogs import MessageBox
    from test_group_workspace_ui import window
    from test_workspace_ui import close_window
    w = window(qt, tmp_path)
    try:
        project_file = tmp_path / 'game.aivsprite'
        project, character = player(tmp_path)
        w.project, w.project_file = project, project_file
        w._loaded()
        controller = w.library_controller
        project = jump_animations(w.project, tmp_path, character, project_file)
        w.project = project
        controller.select_character(character.id)
        row = next(item for item in w.project.library.animation_sets_for(character.id) if item.name == 'Jump')
        assert w.project.library.auto_match_set(row.id) == 3
        row = w.project.library.animation_sets[row.id]
        animation = w.project.library.animation(row.slots[0].animation_id)
        assert animation is not None, 'auto-match bound the template slots'
        prompts = []
        original = MessageBox.question
        try:
            MessageBox.question = staticmethod(lambda *args, **kwargs: (prompts.append(args[2]), MessageBox.StandardButton.Cancel)[1])
            assert controller.remove_resource(animation.id) is None
            assert w.project.library.animation(animation.animation_id) is not None
            assert prompts, 'delete must warn that an Animation Set uses this Animation'
            MessageBox.question = staticmethod(lambda *args, **kwargs: MessageBox.StandardButton.Yes)
            assert controller.remove_resource(animation.id) is not None
        finally:
            MessageBox.question = original
        assert w.project.library.animation(animation.animation_id) is None
        assert w.project.library.animation_sets[row.id].slots[0].animation_id is None
        assert w.project.library.animation_sets[row.id].status == 'INCOMPLETE'
        w.project.library.validate()
    finally:
        close_window(qt, w)
