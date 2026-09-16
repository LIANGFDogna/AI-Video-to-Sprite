"""Phase 2E: character State Machine model, transition runtime, protection, export and UI."""
from dataclasses import asdict
import json
import numpy as np
from PIL import Image
import pytest
from app.core.pipeline import Pipeline
from app.core.state_machine import MachineRuntime, state_provider
from app.core.state_machine_export import export_state_machine, state_machine_metadata
from app.core.set_preview import SetPreviewProvider
from app.core.final_frame_provider import FinalFrameProvider
from app.models.character_templates import PLAYER, REGISTRY
from app.models.project import Project
from app.models.state_machine import Condition, StateMachine, StateParameter
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


def ready_animation(project, tmp_path, group_id, name, project_file):
    project.current_group_id = group_id
    project = project.import_frame_sequence(sequence(tmp_path, name))
    Pipeline(project, cache_directory(project.project_id, project_file, project.animation_id)).build()
    project.library.mark_generated(project.animation_id)
    return project


def player_project(tmp_path, with_animations=("Idle", "Run", "Hurt", "Death", "JumpUp", "FallLoop", "Land")):
    project = Project(project_name="Game")
    character = REGISTRY.create_character(project.library, "Player", PLAYER)
    project_file = tmp_path / "game.aivsprite"
    groups = {row.name: row for row in project.library.character_roots(character.id)}
    jump = groups["Jump"]
    targets = {"Idle": groups["Idle"], "Run": next(row for row in project.library.children(groups["Movement"].id) if row.name == "Run"),
               "Hurt": next(row for row in project.library.children(groups["Reaction"].id) if row.name == "Hurt"),
               "Death": next(row for row in project.library.children(groups["Reaction"].id) if row.name == "Death"),
               "JumpUp": next(row for row in project.library.children(jump.id) if row.name == "JumpUp"),
               "FallLoop": next(row for row in project.library.children(jump.id) if row.name == "FallLoop"),
               "Land": next(row for row in project.library.children(jump.id) if row.name == "Land")}
    for name in with_animations:
        project = ready_animation(project, tmp_path, targets[name].id, name, project_file)
    for row in project.library.animation_sets_for(character.id):
        project.library.auto_match_set(row.id)
    return project, character, project_file


def template_machine(project, character):
    result = REGISTRY.get(PLAYER).create_state_machines(project.library, character)
    assert result, "template machine must be created on explicit request"
    return result[0][0]


def machine_with_states(tmp_path, names=("Idle", "Run")):
    project, character, project_file = player_project(tmp_path, with_animations=names)
    machine = project.library.add_state_machine(character.id, "Test", parameters=[dict(name="speed", type="float", default=0)])
    animations = {row.name: row for row in project.library.resources.values() if row.kind == "ANIMATION"}
    states = {name: machine.add_state(name, animation_id=animations[name].animation_id) for name in names}
    return project, character, project_file, machine, states


def test_create_state_machine_uuid_and_entry(tmp_path):
    project, character, project_file, machine, states = machine_with_states(tmp_path)
    assert len(machine.id) == 32 and machine.character_id == character.id
    assert machine.entry_state == states["Idle"].id
    project.library.validate()
    assert project.library.state_machine(machine.id).id == machine.id


def test_state_machine_character_ownership_and_cross_character_rejected(tmp_path):
    project, character, project_file, machine, states = machine_with_states(tmp_path)
    machine = project.library.state_machine(machine.id)
    other = REGISTRY.create_character(project.library, "Boss", "blank")
    boss_group = project.library.add_group("BossIdle", None, character_id=other.id)
    project = ready_animation(project, tmp_path, boss_group.id, "BossIdle", project_file)
    foreign = project.animation_id
    machine = project.library.state_machine(machine.id)
    machine.add_state("Foreign", animation_id=foreign)
    with pytest.raises(ValueError):
        project.library.validate()
    machine.remove_state(machine.state_by_name("Foreign").id)
    project.library.validate()


def test_animation_and_set_bindings_with_protection(tmp_path):
    project, character, project_file = player_project(tmp_path)
    machine = template_machine(project, character)
    by_name = {row.name: row for row in machine.states}
    assert by_name["Jump"].kind == "set" and by_name["Attack"].kind == "set" and by_name["Dash"].kind == "set"
    assert by_name["Idle"].kind == "animation" and by_name["Run"].kind == "animation"
    assert project.library.animation_sets[by_name["Jump"].set_id].name == "Jump"
    jump_set_id = by_name["Jump"].set_id
    with pytest.raises(ValueError):
        project.library.remove_animation_set(jump_set_id)
    idle_animation = by_name["Idle"].animation_id
    with pytest.raises(ValueError):
        project.library.remove_animation(project.library.animation(idle_animation).id)
    project.library.remove_animation_set(jump_set_id, clear_machines=True)
    assert machine.state_by_name("Jump") is None
    project.library.remove_animation(project.library.animation(idle_animation).id, clear_machines=True)
    assert machine.state_by_name("Idle") is None
    project.library.validate()


def test_cross_character_move_clears_machine_references(tmp_path):
    project, character, project_file = player_project(tmp_path)
    machine = template_machine(project, character)
    machine = project.library.state_machine(machine.id)
    boss = REGISTRY.create_character(project.library, "Boss", "blank")
    idle_group = next(row for row in project.library.character_roots(character.id) if row.name == "Idle")
    with pytest.raises(ValueError):
        project.library.set_group_character(idle_group.id, boss.id)
    assert machine.state_by_name("Idle") is not None
    project.library.set_group_character(idle_group.id, boss.id, clear_machines=True)
    assert machine.state_by_name("Idle") is None, "moving content out of the Character drops its States"
    project.library.validate()


def test_transition_runtime_priority_exit_time_and_interruptible(tmp_path):
    project, character, project_file, machine, states = machine_with_states(tmp_path)
    machine.parameters.append(StateParameter("jump", "trigger", False))
    machine.parameters.append(StateParameter("locked", "bool", False))
    machine.add_transition(states["Idle"].id, states["Run"].id, [Condition("speed", ">", 0)], exit_time=0.5)
    machine.add_transition(states["Run"].id, states["Idle"].id, [Condition("speed", "<=", 0)])
    machine.add_transition(states["Idle"].id, states["Run"].id, [Condition("jump", "==", True)], priority=5)
    machine.add_transition(states["Run"].id, states["Idle"].id, [Condition("locked", "==", True)], priority=9, interruptible=False)
    machine.validate()
    runtime = MachineRuntime(machine)
    runtime.set_parameter("speed", 1)
    assert runtime.tick(0.2) is None, "exit_time blocks the first tick"
    event = runtime.tick(0.4)
    assert event is not None and event.to_state == states["Run"].id
    runtime.set_parameter("locked", True)
    assert runtime.tick(1.0) is None, "non-interruptible transitions never fire from a plain tick"
    event = runtime.tick(0.0, force=True)
    assert event is not None and event.to_state == states["Idle"].id, "only an explicit force fires the edge"
    runtime.force_state(states["Run"].id)
    runtime.set_parameter("locked", False); runtime.set_parameter("speed", 0)
    assert runtime.tick().to_state == states["Idle"].id
    runtime.toggle("jump")
    event = runtime.tick()
    assert event.to_state == states["Run"].id and event.priority == 5
    assert runtime.values["jump"] is False, "triggers are consumed by the transition"
    assert [row.reason for row in runtime.history][-1].startswith("jump == True")


def test_conditions_are_structured_data_only(tmp_path):
    project, character, project_file, machine, states = machine_with_states(tmp_path)
    with pytest.raises(ValueError):
        Condition("speed", ">", 0).validate({})
    with pytest.raises(ValueError):
        Condition("speed", "__import__", 0).validate({"speed": None})
    expression = "__import__('os').system('echo hi')"
    condition = Condition("speed", "==", expression)
    condition.validate({"speed": None})
    assert condition.matches({"speed": expression}) is True
    assert condition.matches({"speed": 0}) is False
    assert condition.matches({}) is False


def test_template_machine_states_and_upgrade(tmp_path):
    project, character, project_file = player_project(tmp_path)
    result = REGISTRY.get(PLAYER).create_state_machines(project.library, character)
    machine, new, added, skipped = result[0]
    assert new is True and not skipped
    assert [row.name for row in machine.states] == ["Idle", "Run", "Jump", "Dash", "Attack", "Hurt", "Death"]
    by_name = {row.name: row for row in machine.states}
    assert project.library.animation_sets[by_name["Jump"].set_id].name == "Jump"
    assert project.library.animation_sets[by_name["Attack"].set_id].name == "Combat"
    assert project.library.animation_sets[by_name["Dash"].set_id].name == "Dash"
    assert machine.entry_state == by_name["Idle"].id
    assert len(machine.transitions) >= 15
    assert any(row.priority == 20 for row in machine.transitions), "Death outranks the regular transitions"
    again = REGISTRY.get(PLAYER).create_state_machines(project.library, character)
    machine2, new2, added2, skipped2 = again[0]
    assert new2 is False and added2 == [] and len(machine2.states) == 7, "no duplicates on the second click"
    assert len(machine2.transitions) == len(machine.transitions)


def test_template_machine_partial_then_completed(tmp_path):
    project = Project(project_name="Game")
    character = REGISTRY.create_character(project.library, "Player", PLAYER)
    first = REGISTRY.get(PLAYER).create_state_machines(project.library, character)[0]
    machine, new, added, skipped = first
    assert new is True and skipped == ["Idle", "Run", "Hurt", "Death"]
    assert [row.name for row in machine.states] == ["Jump", "Dash", "Attack"], "set-backed States resolve immediately"
    project_file = tmp_path / "game.aivsprite"
    groups = {row.name: row for row in project.library.character_roots(character.id)}
    targets = {"Idle": groups["Idle"], "Run": next(row for row in project.library.children(groups["Movement"].id) if row.name == "Run"),
               "Hurt": next(row for row in project.library.children(groups["Reaction"].id) if row.name == "Hurt"),
               "Death": next(row for row in project.library.children(groups["Reaction"].id) if row.name == "Death")}
    for name in ("Idle", "Run", "Hurt", "Death"):
        project = ready_animation(project, tmp_path, targets[name].id, name, project_file)
    second = REGISTRY.get(PLAYER).create_state_machines(project.library, character)[0]
    machine, new, added, skipped = second
    assert new is False and skipped == []
    assert [row.name for row in machine.states] == ["Jump", "Dash", "Attack", "Idle", "Run", "Hurt", "Death"]
    assert machine.state_by_name("Run") is not None and machine.transitions, "transitions appear once both ends exist"


def test_state_provider_uses_final_frame_provider_and_set_preview(tmp_path):
    project, character, project_file = player_project(tmp_path)
    machine = template_machine(project, character)
    machine = project.library.state_machine(machine.id)
    idle = machine.state_by_name("Idle")
    provider = state_provider(project, project_file, machine, idle.id)
    reference = FinalFrameProvider(project.select_animation(idle.animation_id),
        cache_directory(project.project_id, project_file, idle.animation_id), live_edit=True)
    assert isinstance(provider, FinalFrameProvider) and len(provider) == len(reference)
    project = project.select_animation(idle.animation_id)
    project.animation_transform = type(project.animation_transform)(4, -3)
    project.set_frame_correction(1, 2, 5)
    provider = state_provider(project, project_file, machine, idle.id)
    reference = FinalFrameProvider(project.select_animation(idle.animation_id),
        cache_directory(project.project_id, project_file, idle.animation_id), live_edit=True)
    assert np.array_equal(provider.get_final_frame(1), reference.get_final_frame(1)), "offset + correction apply inside a State"
    jump = machine.state_by_name("Jump")
    set_provider = state_provider(project, project_file, machine, jump.id)
    assert isinstance(set_provider, SetPreviewProvider) and len(set_provider) > 0


def test_save_reopen_and_legacy_without_machines(tmp_path):
    project, character, project_file = player_project(tmp_path)
    machine = template_machine(project, character)
    machine.state_by_name("Idle").position = (321.0, 123.0)
    project.save(project_file)
    restored = Project.load(project_file)
    machines = restored.library.state_machines_for(character.id)
    assert len(machines) == 1
    row = machines[0]
    assert row.id == machine.id and row.entry_state == machine.entry_state
    assert [state.name for state in row.states] == [state.name for state in machine.states]
    assert row.state_by_name("Idle").position == (321.0, 123.0), "node positions survive"
    assert len(row.transitions) == len(machine.transitions)
    assert [parameter.name for parameter in row.parameters] == [parameter.name for parameter in machine.parameters]
    legacy = asdict(Project(source_video=str(tmp_path / "legacy.mp4")))
    legacy.pop("state_machines", None)
    restored_legacy = Project.from_dict(legacy)
    assert restored_legacy.library.state_machines == {}, "legacy projects never grow State Machines"


def test_export_state_machine_structure_and_metadata(tmp_path):
    project, character, project_file = player_project(tmp_path)
    machine = template_machine(project, character)
    metadata = state_machine_metadata(project, machine)
    assert metadata["name"] == "Character" and metadata["entry"] == "Idle"
    assert [state["name"] for state in metadata["states"]][:3] == ["Idle", "Run", "Jump"]
    assert any(state["kind"] == "set" and state["content"] == "Jump" for state in metadata["states"])
    assert any(row["next"] == "Hurt" for row in metadata["godot"])
    destination = tmp_path / "Export"
    destination.mkdir()
    result = export_state_machine(project, project_file, machine, destination)
    root = destination / "Character"
    assert root.is_dir() and (root / "state_machine.json").is_file()
    assert (root / "animations" / "Idle" / "sprite_sheet.png").is_file()
    assert (root / "sets" / "Jump" / "animation_set.json").is_file(), "set States keep their own metadata"
    assert "Dash" in result["warnings"] and "Attack" in result["warnings"], "Sets without ready content are reported, never processed"
    payload = json.loads((root / "state_machine.json").read_text(encoding="utf-8"))
    assert payload["entry"] == "Idle" and len(payload["transitions"]) == len(machine.transitions)
    assert result["animations"] >= 2 and result["sets"] >= 1
    for item in ("animations", "sets"):
        for sheet in (root / item).rglob("sprite_sheet.png"):
            source = sheet.read_bytes()
            assert source, "exported sheets come from the provider cache"
    with pytest.raises(FileExistsError):
        export_state_machine(project, project_file, machine, destination)


def test_dialog_graph_positions_simulator_and_transitions(qt, tmp_path):
    from test_group_workspace_ui import window
    w = window(qt, tmp_path)
    try:
        project, character, project_file = player_project(tmp_path)
        w.project, w.project_file = project, project_file
        w._loaded()
        w.library_controller.select_character(character.id)
        machine = template_machine(w.project, character)
        dialog = w.open_state_machine(machine.id)
        assert dialog is not None and dialog.machine is not None
        node_count = len(dialog.nodes) if hasattr(dialog, "nodes") else None
        assert len(dialog.view.scene().items()) > 0
        node = dialog.nodes[machine.state_by_name("Idle").id]
        node.setPos(410.0, 260.0)
        dialog.positions_changed()
        assert w.project.library.state_machine(machine.id).state_by_name("Idle").position == (410.0, 260.0)
        entry = dialog.machine.state_by_name("Death")
        dialog.from_box.setCurrentIndex(dialog.from_box.findData(entry.id))
        dialog.to_box.setCurrentIndex(dialog.to_box.findData(dialog.machine.state_by_name("Hurt").id))
        dialog.add_transition()
        assert any(row.from_state == entry.id and row.to_state == dialog.machine.state_by_name("Hurt").id for row in dialog.machine.transitions)
        dialog.transition_list.setCurrentRow(dialog.transition_list.count() - 1)
        dialog.condition_parameter.setCurrentIndex(dialog.condition_parameter.findData("speed"))
        dialog.condition_value.setText("2")
        dialog.add_condition()
        assert any(condition.parameter == "speed" for row in dialog.machine.transitions for condition in row.conditions)
        dialog.parameter_box.setCurrentIndex(dialog.parameter_box.findData("speed"))
        dialog.parameter_value.setText("3")
        dialog.set_parameter()
        dialog.tick()
        assert dialog.runtime.current_state.name == "Run", "speed > 0 switches Idle → Run"
        dialog.parameter_box.setCurrentIndex(dialog.parameter_box.findData("hurt"))
        dialog.toggle_parameter()
        dialog.tick()
        assert dialog.runtime.current_state.name == "Hurt", "the hurt trigger wins by priority"
        from app.i18n import t as translate
        assert translate("Current State: {name}", name="Hurt") in dialog.current_state.text()
        assert dialog.log_view.toPlainText()
        dialog.close()
    finally:
        close_window(qt, w)
