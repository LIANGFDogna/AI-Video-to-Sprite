"""Plan Group paths and export existing results without running any processing."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import json
import shutil
import tempfile
from app.core.project_workspace import sanitize_project_name
from app.models.project_library import unique_name
from app.utils.paths import cache_directory
from app.utils.ffmpeg import check_cancel
from app.utils.publish import publish_folder
from app.exporters.image_exporter import copy_file
from app.exporters.godot_exporter import write_metadata
from app.exporters.root_motion_exporter import write_root_motion


@dataclass
class GroupExportItem:
    resource_id: str
    group_id: str
    relative_directory: Path
    source_sheet: Path
    animation: object = None
    metadata: dict = field(default_factory=dict)


@dataclass
class GroupExportPlan:
    items: list[GroupExportItem]
    directories: list[Path]
    warnings: list[str]
    selected_groups: list[str]


def sheet_path(project, project_file, resource):
    if resource.kind == "SOURCE_SPRITE_SHEET":
        return Path(resource.path)
    return cache_directory(project.project_id, project_file, resource.animation_id) / "sprite_sheet.png"


def exportable_resources(project, project_file, group_id, recursive=True):
    library = project.library
    result = []
    for resource in library.in_group(group_id, recursive):
        if resource.kind == "SOURCE_SPRITE_SHEET" and Path(resource.path).is_file():
            result.append(resource)
        elif resource.kind == "ANIMATION" and resource.ready:
            animation = project if project.animation_id == resource.animation_id and project.source_path else project.select_animation(resource.animation_id)
            generated = next((r for r in library.resources.values() if r.kind == "GENERATED_SPRITE_SHEET" and r.animation_id == resource.animation_id and r.ready), None)
            if animation.layout and generated and sheet_path(project, project_file, generated).is_file():
                result.append(resource)
    return result


def safe_component(value, fallback="Group"):
    return sanitize_project_name(value) or fallback


def character_prefix(library, group):
    "Character nodes are part of the export path; loose Groups stay at the top level."
    if group.character_id is None:
        return None
    character = library.characters.get(group.character_id)
    if character is None:
        return None
    return safe_component(character.name, "Character")


def group_disk_paths(library, preserve_tree=True):
    paths = {}

    def visit(groups, root):
        names = []
        for group in groups:
            component = unique_name(safe_component(group.name), names, "_")
            names.append(component)
            paths[group.id] = root / component
            visit(library.children(group.id), root / component)

    prefixes = []
    for character in library.characters.values():
        prefix = unique_name(safe_component(character.name, "Character"), prefixes, "_")
        prefixes.append(prefix)
        visit(library.character_roots(character.id), Path(prefix))
    visit(library.loose_roots(), Path())
    if not preserve_tree:
        used = []
        for ident, path in paths.items():
            name = unique_name(safe_component("_".join(path.parts)), used, "_")
            used.append(name)
            paths[ident] = Path(name)
    return paths


def plan_group_export(project, project_file, group_ids, preserve_tree=True):
    library = project.library
    library.validate()
    selected = list(dict.fromkeys(group_ids))
    if not selected or any(g not in library.groups for g in selected):
        raise ValueError("Select at least one valid Group")
    included = set()
    for group_id in selected:
        included.update(library.descendants(group_id))
    paths = group_disk_paths(library, preserve_tree)
    items, warnings = [], []
    directories = [paths[g] for g in paths if g in included]
    for group_id in paths:
        if group_id not in included:
            continue
        resources = exportable_resources(project, project_file, group_id, recursive=False)
        names = [paths[g.id].name for g in library.children(group_id)] if preserve_tree else []
        for resource in resources:
            slug = unique_name(safe_component(Path(resource.name).stem if resource.kind == "SOURCE_SPRITE_SHEET" else resource.name, "Animation"), names, "_")
            names.append(slug)
            animation = project.select_animation(resource.animation_id) if resource.kind == "ANIMATION" else None
            if animation:
                # UI names are independent of cache signatures; exported metadata matches the resource.
                animation.export_settings.animation_name = resource.name
            items.append(GroupExportItem(resource.id, group_id, paths[group_id]/slug,
                sheet_path(project, project_file, resource), animation, dict(resource.metadata)))
        if not resources and not any(exportable_resources(project, project_file, g) for g in (group_id,)):
            warnings.append(" / ".join(g.name for g in library.path(group_id)))
    return GroupExportPlan(items, directories, warnings, selected)


def export_group_plan(plan, destination, progress=lambda n, total, message: None, cancel=None,
                      include_sheet=True, include_animation_json=True, include_root_motion=True):
    """All files stage first. Existing top-level Group folders are never merged/overwritten."""
    if not any((include_sheet, include_animation_json, include_root_motion)):
        raise ValueError("Select at least one export format")
    destination = Path(destination).expanduser().resolve()
    if not destination.is_dir():
        raise ValueError("Export directory does not exist")
    top_names = sorted({p.parts[0] for p in plan.directories})
    if not top_names:
        raise ValueError("Select at least one valid Group")
    for name in top_names:
        if (destination/name).exists():
            raise FileExistsError("Group export folders already exist. Choose another export directory.")
    staging = Path(tempfile.mkdtemp(prefix=".aivsprite-groups-", dir=destination))
    published = []
    try:
        for relative in plan.directories:
            target = (staging/relative).resolve()
            if not target.is_relative_to(staging.resolve()):
                raise ValueError("Invalid export path")
            target.mkdir(parents=True, exist_ok=True)
        for index, item in enumerate(plan.items):
            check_cancel(cancel)
            target = (staging/item.relative_directory).resolve()
            if not target.is_relative_to(staging.resolve()):
                raise ValueError("Invalid export path")
            target.mkdir(parents=True, exist_ok=True)
            if include_sheet:
                suffix = ".png" if item.animation else item.source_sheet.suffix.lower()
                copy_file(item.source_sheet, target/("sprite_sheet"+suffix), cancel)
            if item.animation:
                if include_animation_json:
                    write_metadata(item.animation, target/"animation.json")
                if include_root_motion:
                    write_root_motion(item.animation, target/"root_motion.json")
            elif include_animation_json:
                (target/"sprite_sheet.json").write_text(json.dumps({"resource_id":item.resource_id,
                    "group_id":item.group_id,"type":"SOURCE_SPRITE_SHEET","metadata":item.metadata,
                    "animation_grid":None}, ensure_ascii=False, indent=2), encoding="utf-8")
            progress(index+1, len(plan.items), "Exporting Group resources")
        check_cancel(cancel)
        for name in top_names:
            check_cancel(cancel)
            target = destination/name
            # rename on Windows refuses an existing directory; never replace user content.
            publish_folder(staging/name, target)
            published.append(target)
        return dict(destination=str(destination), resources=len(plan.items), groups=plan.selected_groups, warnings=plan.warnings)
    except Exception:
        for target in published:
            if target.resolve().parent == destination:
                shutil.rmtree(target)
        raise
    finally:
        if staging.exists() and staging.resolve().parent == destination:
            shutil.rmtree(staging)
