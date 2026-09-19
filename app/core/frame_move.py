"""Move canonical frames between Animations.

The canonical layer is the aligned / normalized cell: it already contains Decode, Key and
Canvas Normalize, but it is still *before* the Animation Transform and Frame Correction.
Frame moves copy those files byte for byte, so nothing is rendered, re-normalized or baked
into final pixels, and the user's own media is never touched.
"""
from __future__ import annotations

import copy
import shutil
from pathlib import Path

from app.models.frame_data import FrameData
from app.models.pixel_edit import PerFrameRasterEdit
from app.models.timeline_edit import FrameOverride, TimelineEdit
from app.utils.paths import frame_path


def canonical_folder(cache_dir) -> Path:
    "Canonical cells of one Animation, before Animation Transform and Frame Correction."
    return Path(cache_dir) / "aligned_frames"


def canonical_files(folder, indices):
    result = []
    for index in indices:
        path = frame_path(Path(folder), int(index))
        if not path.is_file():
            raise ValueError(f"Canonical frame {int(index)} is missing")
        result.append(path)
    return result


def copy_canonical_frames(folder, indices, target) -> list[Path]:
    "Byte copies renumbered in Timeline order; the original frames stay where they are."
    files = canonical_files(folder, indices)
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    written = []
    for new_index, source in enumerate(files):
        destination = frame_path(target, new_index)
        if source.resolve() != destination.resolve():
            shutil.copyfile(source, destination)
        written.append(destination)
    return written


def apply_frame_state(target, source, mapping, fps) -> None:
    """Frame-owned state follows the frame; the Animation Transform never does.

    mapping: {target_index: source_index}
    """
    corrections = {}
    for target_index, source_index in mapping.items():
        value = source.frame_corrections.get(int(source_index))
        if value and (int(value[0]) or int(value[1])):
            corrections[int(target_index)] = (int(value[0]), int(value[1]))
    target.frame_corrections = corrections

    rows = {int(row.index): row for row in source.tracking_results}
    results = []
    for target_index, source_index in mapping.items():
        row = rows.get(int(source_index))
        if row is None:
            results.append(FrameData(int(target_index)))
            continue
        moved = copy.deepcopy(row)
        moved.index = int(target_index)
        results.append(moved)
    target.tracking_results = results

    edit = TimelineEdit()
    edit.initialize(len(mapping), fps or 24.)
    clips = ({int(clip.source_index): clip for clip in source.timeline_edit.timeline_clips}
             if source.timeline_edit.enabled else {})
    for new_index, clip in enumerate(edit.timeline_clips):
        old = clips.get(int(mapping[new_index]))
        if old is None:
            continue
        clip.duration = old.duration
        clip.keyframe = old.keyframe
        override = source.timeline_edit.frame_overrides.get(old.id)
        edit.frame_overrides[clip.id] = copy.deepcopy(override) if override is not None else FrameOverride()
    target.timeline_edit = edit


def copy_raster_edits(target, source, mapping, source_root, target_root) -> None:
    "Pencil / Eraser layers belong to the frame and are copied into the target Animation."
    rows = source.pixel_edits.get(source.animation_id) or {}
    directory = Path(target_root) / str(target.animation_id)
    for target_index, source_index in mapping.items():
        row = rows.get(int(source_index))
        if row is None or not row.active:
            continue
        directory.mkdir(parents=True, exist_ok=True)
        stem = f"frame_{int(target_index):06d}.r{int(row.revision):04d}"
        paint = directory / f"{stem}.paint.png"
        erase = directory / f"{stem}.erase.png"
        shutil.copyfile(row.paint_layer, paint)
        shutil.copyfile(row.erase_mask, erase)
        target.set_raster_edit(target.animation_id, int(target_index), str(paint), str(erase), int(row.revision))


def frame_edit_rows(project, animation_id):
    return project.pixel_edits.get(animation_id) or {}


def mark_generated_stale(project, animation_id) -> bool:
    """After its frames changed an Animation is no longer READY and its Sheet is stale."""
    library = getattr(project, "library", project)
    owner = library.animation(animation_id)
    if owner is None:
        return False
    changed = bool(owner.ready)
    owner.ready = False
    for sheet in library.generated_sheets(animation_id):
        changed = changed or bool(sheet.ready)
        sheet.ready = False
    return changed


def invalidate_sheet_manifest(cache_dir) -> None:
    "Drop the Sheet signature so the next build really rebuilds the cached sheet."
    for name in ("sheet.json", "final.json"):
        (Path(cache_dir) / name).unlink(missing_ok=True)
