"""Phase 2D: export an Animation Set as separate Animation folders plus animation_set.json."""
from __future__ import annotations
from pathlib import Path
import json
import shutil
import tempfile

from app.core.group_export import exportable_resources, safe_component, sheet_path
from app.exporters.image_exporter import copy_file
from app.exporters.godot_exporter import write_metadata
from app.exporters.root_motion_exporter import write_root_motion
from app.models.project_library import unique_name
from app.utils.ffmpeg import check_cancel


def set_sequence_names(project, animation_set):
    names = []
    for slot, animation_id, _, _ in animation_set.preview_timeline():
        row = project.library.animation(animation_id)
        names.append((slot, animation_id, row.name if row else animation_id))
    return names


def animation_set_metadata(project, animation_set):
    rows = set_sequence_names(project, animation_set)
    sequence = [name for _, _, name in rows]
    godot = []
    for index, (slot, animation_id, name) in enumerate(rows):
        nxt = rows[index + 1][2] if index + 1 < len(rows) else None
        godot.append(dict(state=name, suggested_state_name=name, loop=slot.repeat_count > 1,
                          next=nxt, transition=animation_set.transition_type))
    return dict(id=animation_set.id, name=animation_set.name, semantic_type=animation_set.semantic_type,
        character_id=animation_set.character_id, transition=animation_set.transition_type,
        sequence=sequence, slots=[dict(slot=s.display_name, semantic_type=s.semantic_type, required=s.required,
            repeat_count=s.repeat_count, animation=name) for (s, _, name) in rows],
        godot=godot)


def plan_animation_set(project, project_file, animation_set):
    "Resolve every bound slot to its exported Animation folder; missing results are reported, never processed."
    library = project.library
    plan, warnings = [], []
    names = []
    for slot, animation_id, _ in set_sequence_names(project, animation_set):
        resource = library.animation(animation_id)
        if resource is None or not resource.ready or resource not in exportable_resources(project, project_file, resource.group_id):
            warnings.append(slot.display_name)
            continue
        folder = unique_name(safe_component(resource.name, "Animation"), names, "_")
        names.append(folder)
        plan.append(dict(slot=slot, resource=resource, folder=folder,
            source_sheet=sheet_path(project, project_file, resource)))
    return plan, warnings


def export_animation_set(project, project_file, animation_set, destination, progress=lambda n, total, message: None, cancel=None):
    "Stage everything first; an existing Set folder is never merged or overwritten."
    destination = Path(destination).expanduser().resolve()
    if not destination.is_dir():
        raise ValueError("Export directory does not exist")
    set_folder = safe_component(animation_set.name, "Animation Set")
    target_root = destination / set_folder
    if target_root.exists():
        raise FileExistsError("Animation Set export folder already exists. Choose another export directory.")
    plan, warnings = plan_animation_set(project, project_file, animation_set)
    if not plan:
        raise ValueError("Animation Set has no ready Animations to export")
    staging = Path(tempfile.mkdtemp(prefix=".aivsprite-set-", dir=destination))
    try:
        for index, item in enumerate(plan):
            check_cancel(cancel)
            resource = item["resource"]
            folder = staging / item["folder"]
            folder.mkdir(parents=True, exist_ok=True)
            animation = project.select_animation(resource.animation_id)
            animation.export_settings.animation_name = resource.name
            copy_file(item["source_sheet"], folder / "sprite_sheet.png", cancel)
            write_metadata(animation, folder / "animation.json")
            write_root_motion(animation, folder / "root_motion.json")
            progress(index + 1, len(plan), "Exporting Animation Set")
        check_cancel(cancel)
        (staging / "animation_set.json").write_text(json.dumps(animation_set_metadata(project, animation_set),
            ensure_ascii=False, indent=2), encoding="utf-8")
        check_cancel(cancel)
        staging.rename(target_root)
        return dict(destination=str(target_root), resources=len(plan), warnings=warnings, metadata=str(target_root / "animation_set.json"))
    finally:
        if staging.exists():
            shutil.rmtree(staging)
