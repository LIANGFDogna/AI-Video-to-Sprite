from __future__ import annotations

from pathlib import Path
import shutil
import tempfile

from app.core.pipeline import Pipeline
from app.core.final_frame_provider import FinalFrameProvider
from app.utils.ffmpeg import check_cancel
from app.utils.paths import frame_path


def copy_file(source: Path, destination: Path, cancel=None):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as src, destination.open("wb") as dst:
        while chunk := src.read(1024 * 1024):
            check_cancel(cancel)
            dst.write(chunk)
    check_cancel(cancel)


def export_images(pipeline: Pipeline, destination: Path, kind="all", godot=False, allow_clipping=False) -> Path:
    """Publish a completed bundle atomically to a new directory, never merge old frames."""
    if kind not in ("all", "sheet", "frames", "rgba"):
        raise ValueError(f"Unknown export type: {kind}")
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError("Choose a new output folder to avoid mixing or overwriting existing frames")
    if kind == "rgba":
        pipeline.ensure_key()
    else:
        pipeline.build()
        provider = FinalFrameProvider(pipeline.project, pipeline.cache_dir, pipeline.final_signature())
        if pipeline.project.layout.clipped_frames and not allow_clipping:
            indices = ", ".join(str(i) for i in pipeline.project.layout.clipped_frames)
            raise ValueError(f"FRAME CLIPPING DETECTED: {indices}. Use AUTO / a larger cell or explicitly accept clipping.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".aivsprite-export-", dir=destination.parent))
    try:
        if kind in ("all", "sheet"):
            copy_file(pipeline.sheet, staging / "sprite_sheet.png", pipeline.cancel)
        count = pipeline.project.video.frame_count if kind == "rgba" else len(provider)
        if kind in ("all", "frames", "rgba"):
            directory = staging / ("frames_rgba" if kind == "rgba" else "frames")
            directory.mkdir()
            for index in range(count):
                check_cancel(pipeline.cancel)
                source = frame_path(pipeline.keyed, index) if kind == "rgba" else provider.final_path(index)
                name = f"frame_{index:06d}.png" if kind == "rgba" else f"{index:04d}.png"
                copy_file(source, directory / name, pipeline.cancel)
                pipeline.progress(index + 1, count, "Exporting transparent PNG frames")
        if godot:
            if kind not in ("all", "sheet"):
                raise ValueError("Godot metadata requires a sprite sheet export")
            from app.exporters.godot_exporter import write_metadata
            write_metadata(pipeline.project, staging / "animation.json")
            from app.exporters.root_motion_exporter import write_root_motion
            write_root_motion(pipeline.project, staging / "root_motion.json")
        check_cancel(pipeline.cancel)
        staging.rename(destination)
    finally:
        if staging.exists():
            # staging is an exclusively owned mkdtemp under the requested output parent.
            shutil.rmtree(staging)
    return destination
