"""Create an empty character project without overwriting existing user content."""
from pathlib import Path
import re

from app.models.project import Project

PROJECT_DIRECTORIES = ("source", "sequences", "cache", "exports", "previews", "logs")
TEMPLATES = {"standard": ((512, 512), (512, 512)), "ai_character": ((1536, 1536), (512, 512))}
_INVALID = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\.|$)", re.I)


def sanitize_project_name(name):
    name = _INVALID.sub("_", name).strip().rstrip(" .")[:100].rstrip(" .")
    if _RESERVED.match(name):
        name = "_" + name
    return name


def validate_project_name(name):
    if not name or not name.strip():
        raise ValueError("Project name cannot be empty")
    if name != sanitize_project_name(name) or name in (".", ".."):
        raise ValueError("Project name is not a valid Windows folder name")


def create_project_workspace(parent, name, template="ai_character", output_canvas=None,
                             default_fps=24., source_canvas=None, use_existing_empty=False, project_canvas=None):
    validate_project_name(name)
    if not str(parent).strip():
        raise ValueError("Project save directory does not exist")
    parent = Path(parent).expanduser().resolve()
    if not parent.is_dir():
        raise ValueError("Project save directory does not exist")
    if template not in (*TEMPLATES, "custom"):
        raise ValueError("Invalid project template")
    source, output = TEMPLATES.get(template, ((512, 512), (512, 512)))
    source = tuple(source_canvas or source)
    output = tuple(output_canvas or output)
    project = Project(project_name=name, source_canvas=source, output_canvas=output, default_fps=default_fps)
    project.project_canvas_width, project.project_canvas_height = tuple(project_canvas or source)
    project.canvas_fit_mode = "center_crop_or_pad"
    project.sequence_fps = default_fps
    project.sprite_cell.canvas_mode = "normalize_source"
    project.sprite_cell.target_width, project.sprite_cell.target_height = output
    project.scale = min(output[0] / project.project_canvas_width, output[1] / project.project_canvas_height) if all(v > 0 for v in project.project_canvas) else 1.
    # The actual normalization transform supports ratios outside the legacy scale slider.
    project.scale = min(4., max(.1, project.scale))
    project.validate()
    destination = parent / name
    if destination.exists():
        if destination.is_symlink() or destination.resolve().parent != parent:
            raise ValueError("Existing directory points outside the selected project location")
        if not destination.is_dir() or not use_existing_empty:
            raise ValueError("Target directory already exists")
        if next(destination.iterdir(), None) is not None:
            raise ValueError("Target directory is not empty; its contents will not be overwritten")
    else:
        destination.mkdir()  # Atomic, no exist_ok: concurrent creation is a conflict.
    # Exclusive creation also prevents concurrent project files from being replaced.
    project_file = destination / f"{name}.aivsprite"
    with project_file.open("x", encoding="utf-8"):
        pass
    for directory in PROJECT_DIRECTORIES:
        (destination / directory).mkdir()
    project.save(project_file)
    return project, project_file
