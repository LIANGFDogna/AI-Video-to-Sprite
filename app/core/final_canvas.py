"""Apply motion in source pixels, then normalize the entire source canvas."""
import math
import numpy as np

from app.core.alignment import pivot_for, warp_rgba
from app.core.alpha_utils import alpha_bbox
from app.core.canvas_normalizer import canvas_transform, normalize_canvas
from app.core.sprite_canvas import calculate_layout
from app.models.frame_data import CellLayout, FrameData
from app.core.character_space import character_transform


def source_corrections(project):
    frames = project.tracking_results
    if not frames:
        raise ValueError("No frames to align")
    if not project.motion_settings.enabled and not project.character_profile:
        anchor = pivot_for(frames[0], project.alignment_mode, project.video.width)
        for f in frames:
            pivot = pivot_for(f, project.alignment_mode, project.video.width)
            f.correction = (anchor[0]-pivot[0], anchor[1]-pivot[1])
            f.target_root = (f.root[0]+f.correction[0], f.root[1]+f.correction[1])
    for f in frames:
        f.warnings = [w for w in f.warnings if w != "Clipping"]
        if f.bbox:
            l, t, r, b = f.bbox
            dx, dy = f.correction
            profile = project.character_profile
            max_width, max_height = (tuple(v/profile.character_scale for v in profile.canvas_size) if profile else (project.video.width, project.video.height))
            if l+dx < 0 or t+dy < 0 or r+dx > max_width or b+dy > max_height:
                f.warnings.append("Clipping")


def normalized_layout(project):
    p, s = project, project.sprite_cell
    if p.character_profile:
        profile = p.character_profile
        transform = character_transform(profile)
        width, height = profile.canvas_size
        layout = CellLayout(width, height, profile.canonical_root, profile.ground_origin[1], width, height,
            [f.index for f in p.tracking_results if "Clipping" in f.warnings], "character_profile",
            (profile.character_scale, profile.character_scale), (0, 0), p.video.width, p.video.height)
        return layout, transform
    transform = canvas_transform(p.video.width, p.video.height, s.target_width, s.target_height, s.preserve_aspect_ratio)
    first = p.tracking_results[0]
    first_ground = first.ground if first.ground is not None else first.root[1]
    baseline = (first_ground+first.correction[1])*transform.scale_y + transform.offset_y
    layout = CellLayout(s.target_width, s.target_height, transform.point(first.target_root), baseline,
                        s.target_width, s.target_height, [f.index for f in p.tracking_results if "Clipping" in f.warnings],
                        "normalize_source", (transform.scale_x, transform.scale_y),
                        (transform.offset_x, transform.offset_y), p.video.width, p.video.height)
    return layout, transform


def normalize_frame(aligned_rgba, frame, transform, settings):
    result = normalize_canvas(aligned_rgba, transform)
    frame.cell_root = transform.point(frame.target_root)
    frame.offset = (frame.correction[0]*transform.scale_x+transform.offset_x,
                    frame.correction[1]*transform.scale_y+transform.offset_y)
    frame.cell_bbox = alpha_bbox(result, settings.alpha_threshold, max(1, round(settings.min_component_size*transform.scale_x*transform.scale_y)))
    frame.cell_ground = (frame.ground+frame.correction[1])*transform.scale_y+transform.offset_y if frame.ground is not None else None
    return result


def motion_auto_layout(project):
    p = project
    translated = []
    for f in p.tracking_results:
        box = None
        if f.bbox:
            l, t, r, b = f.bbox
            dx, dy = f.correction
            box = (math.floor(l+dx), math.floor(t+dy), math.ceil(r+dx), math.ceil(b+dy))
        translated.append(FrameData(f.index, bbox=box, root=(0., 0.)))
    layout = calculate_layout(translated, "ROOT XY LOCK", p.video.width, p.sprite_cell, p.scale)
    shift = layout.target_root
    layout.normalize_scale = (p.scale, p.scale)
    layout.normalize_offset = shift
    for f, temp in zip(p.tracking_results, translated):
        f.offset = (shift[0]+f.correction[0]*p.scale, shift[1]+f.correction[1]*p.scale)
        f.cell_root = (f.target_root[0]*p.scale+shift[0], f.target_root[1]*p.scale+shift[1])
        f.cell_ground = (f.ground+f.correction[1])*p.scale+shift[1] if f.ground is not None else None
        f.warnings = [w for w in f.warnings if w != "Clipping"]
        if f.index in layout.clipped_frames:
            f.warnings.append("Clipping")
    layout.target_root = p.tracking_results[0].cell_root
    layout.ground_baseline = next((f.cell_ground for f in p.tracking_results if f.cell_ground is not None), layout.ground_baseline)
    return layout
