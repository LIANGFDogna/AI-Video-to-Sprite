from pathlib import Path
import tempfile


def cache_directory(project_id: str, project_file: Path | None = None, animation_id="default") -> Path:
    base = project_file.parent / "cache" if project_file else Path(tempfile.gettempdir()) / "AI Video to Sprite" / "cache"
    result = base / project_id
    if animation_id != "default":
        result = result / "animations" / animation_id
    result.mkdir(parents=True, exist_ok=True)
    return result


def frame_path(directory: Path, index: int) -> Path:
    return directory / f"frame_{index:06d}.png"


def project_cache_root(project_id: str, project_file: Path | None = None) -> Path:
    base = project_file.parent / "cache" if project_file else Path(tempfile.gettempdir()) / "AI Video to Sprite" / "cache"
    result = base / project_id
    result.mkdir(parents=True, exist_ok=True)
    return result


def pixel_edit_directory(project_id: str, project_file: Path | None = None, animation_id: str = "default") -> Path:
    """Pencil / Eraser layers live beside the Animation cache, never inside the project JSON."""
    result = project_cache_root(project_id, project_file) / "pixel_edits" / str(animation_id)
    result.mkdir(parents=True, exist_ok=True)
    return result
