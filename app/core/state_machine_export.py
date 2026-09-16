"""Phase 2E: export a State Machine as content folders plus state_machine.json (metadata only)."""
from __future__ import annotations
from pathlib import Path
import json
import shutil
import tempfile

from app.core.group_export import exportable_resources, safe_component, sheet_path
from app.core.set_export import animation_set_metadata, plan_animation_set
from app.exporters.image_exporter import copy_file
from app.exporters.godot_exporter import write_metadata
from app.exporters.root_motion_exporter import write_root_motion
from app.models.project_library import unique_name
from app.utils.ffmpeg import check_cancel
from app.utils.publish import publish_folder


def state_machine_metadata(project, machine):
    library = project.library
    states, godot = [], []
    for state in machine.states:
        if state.kind == "set":
            row = library.animation_sets.get(state.set_id)
            label = row.name if row else None
            kind_name = "set"
        else:
            row = library.animation(state.animation_id)
            label = row.name if row else None
            kind_name = "animation"
        states.append(dict(id=state.id, name=state.name, kind=kind_name, content=label, loop=state.loop,
            position=[state.position[0], state.position[1]]))
    for transition in machine.transitions:
        source = machine.state(transition.from_state)
        target = machine.state(transition.to_state)
        transitions = [dict(parameter=condition.parameter, operator=condition.operator, value=condition.value)
            for condition in transition.conditions]
        godot.append(dict(state=source.name if source else transition.from_state,
            next=target.name if target else transition.to_state,
            conditions=transitions, priority=transition.priority,
            exit_time=transition.exit_time, interruptible=transition.interruptible))
    entry = machine.state(machine.entry_state)
    return dict(id=machine.id, name=machine.name, character_id=machine.character_id,
        entry=entry.name if entry else None,
        parameters=[dict(name=row.name, type=row.type, default=row.default) for row in machine.parameters],
        states=states,
        transitions=[dict(id=row.id, source=next((s.name for s in machine.states if s.id == row.from_state), row.from_state),
            target=next((s.name for s in machine.states if s.id == row.to_state), row.to_state),
            conditions=[dict(parameter=c.parameter, operator=c.operator, value=c.value) for c in row.conditions],
            priority=row.priority, exit_time=row.exit_time, interruptible=row.interruptible,
            description=row.describe()) for row in machine.transitions],
        godot=godot)


def export_state_machine(project, project_file, machine, destination, progress=lambda n, total, message: None, cancel=None):
    "Stage content for every State, then publish; an existing Machine folder is never merged."
    destination = Path(destination).expanduser().resolve()
    if not destination.is_dir():
        raise ValueError("Export directory does not exist")
    machine_folder = safe_component(machine.name, "State Machine")
    target_root = destination / machine_folder
    if target_root.exists():
        raise FileExistsError("State Machine export folder already exists. Choose another export directory.")
    library = project.library
    animations, sets, warnings = [], [], []
    for state in machine.states:
        if state.kind == "set":
            row = library.animation_sets.get(state.set_id)
            if row is None or not plan_animation_set(project, project_file, row)[0]:
                warnings.append(state.name)
                continue
            if row.id not in {item.id for item in sets}:
                sets.append(row)
        else:
            resource = library.animation(state.animation_id)
            if resource is None or not resource.ready or resource not in exportable_resources(project, project_file, resource.group_id):
                warnings.append(state.name)
                continue
            if resource.animation_id not in {item.animation_id for item in animations}:
                animations.append(resource)
    if not animations and not sets:
        raise ValueError("State Machine has no ready content to export")
    staging = Path(tempfile.mkdtemp(prefix=".aivsprite-machine-", dir=destination))
    try:
        total = len(animations) + len(sets)
        done = 0
        used_animation_names, used_set_names = [], []
        for resource in animations:
            check_cancel(cancel)
            folder = staging / "animations" / unique_name(safe_component(resource.name, "Animation"), used_animation_names, "_")
            folder.mkdir(parents=True, exist_ok=True)
            animation = project.select_animation(resource.animation_id)
            animation.export_settings.animation_name = resource.name
            copy_file(sheet_path(project, project_file, resource), folder / "sprite_sheet.png", cancel)
            write_metadata(animation, folder / "animation.json")
            write_root_motion(animation, folder / "root_motion.json")
            done += 1
            progress(done, total, "Exporting State Machine")
        for row in sets:
            check_cancel(cancel)
            folder = staging / "sets" / unique_name(safe_component(row.name, "Animation Set"), used_set_names, "_")
            folder.mkdir(parents=True, exist_ok=True)
            for item in plan_animation_set(project, project_file, row)[0]:
                check_cancel(cancel)
                resource = item["resource"]
                animation = project.select_animation(resource.animation_id)
                animation.export_settings.animation_name = resource.name
                child = folder / item["folder"]
                child.mkdir(parents=True, exist_ok=True)
                copy_file(item["source_sheet"], child / "sprite_sheet.png", cancel)
                write_metadata(animation, child / "animation.json")
                write_root_motion(animation, child / "root_motion.json")
            (folder / "animation_set.json").write_text(json.dumps(animation_set_metadata(project, row),
                ensure_ascii=False, indent=2), encoding="utf-8")
            done += 1
            progress(done, total, "Exporting State Machine")
        check_cancel(cancel)
        (staging / "state_machine.json").write_text(json.dumps(state_machine_metadata(project, machine),
            ensure_ascii=False, indent=2), encoding="utf-8")
        check_cancel(cancel)
        publish_folder(staging, target_root)
        return dict(destination=str(target_root), animations=len(animations), sets=len(sets), warnings=warnings,
            metadata=str(target_root / "state_machine.json"))
    finally:
        if staging.exists():
            shutil.rmtree(staging)
