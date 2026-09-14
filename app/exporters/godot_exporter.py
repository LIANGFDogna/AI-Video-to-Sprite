"""Godot-facing JSON adapter; no dependency on the main window."""
import json
import math
from dataclasses import asdict
from pathlib import Path

from app.models.project import Project


def write_metadata(project: Project, path: Path):
    p, layout = project, project.layout
    if not layout:
        raise ValueError("Build sprites before exporting Godot metadata")
    data = {
        "schema_version": 1,
        "animation_name": p.export_settings.animation_name,
        "input_mode": p.input_mode,
        "processing_mode": p.processing_mode,
        "project_canvas": p.project_canvas,
        "canvas_fit_mode": p.canvas_fit_mode,
        "original_size": p.original_size,
        "passthrough_alignment": p.is_passthrough,
        "root_tracked": not p.is_passthrough,
        "fps": p.video.fps,
        "fps_rational": p.video.fps_rational,
        "frame_count": p.video.frame_count,
        "cell_width": layout.width,
        "cell_height": layout.height,
        "columns": p.export_settings.columns,
        "rows": math.ceil(p.video.frame_count / p.export_settings.columns),
        "root_x": None if p.is_passthrough else layout.target_root[0],
        "root_y": None if p.is_passthrough else layout.target_root[1],
        "ground_baseline": None if p.is_passthrough else layout.ground_baseline,
        "alignment_mode": "passthrough" if p.is_passthrough else p.alignment_mode,
        "scale": layout.normalize_scale[0],
        "canvas_mode": layout.canvas_mode,
        "character_profile": asdict(p.character_profile) if p.character_profile else None,
        "character_profile_applied": bool(p.character_profile) and not p.is_passthrough,
        "canvas_scale": layout.normalize_scale,
        "motion_policy": {"x": "PASSTHROUGH", "y": "PASSTHROUGH"} if p.is_passthrough else {"x": "EXTRACT", "y": "EXTRACT"} if p.character_profile else {"x": p.motion_settings.x_policy, "y": p.motion_settings.y_policy},
        "root_motion_file": "root_motion.json",
        "loop": p.export_settings.loop,
        "texture": "sprite_sheet.png",
        "coordinate_system": "Target pixels; bbox [left,top,right,bottom). root/target_root and ground describe the final cell. raw_root/filtered_root are normalized pre-correction trajectories. No world position animation is authored.",
        "frames": [],
    }
    for f in p.tracking_results:
        data["frames"].append({
            "index": f.index, "source_frame": f.index,
            "source_filename": p.sequence_files[f.index] if p.input_mode == "frame_sequence" else f"frame_{f.index:06d}.png",
            "bbox": f.cell_bbox,
            "root": f.cell_root,
            "ground": f.cell_ground,
            "raw_root": [(f.raw_root or f.root)[a]*layout.normalize_scale[a]+layout.normalize_offset[a] for a in (0, 1)],
            "filtered_root": [(f.filtered_root or f.root)[a]*layout.normalize_scale[a]+layout.normalize_offset[a] for a in (0, 1)],
            "target_root": list(f.cell_root),
            "tracked_root": f.tracked_root,
            "character_correction": f.character_correction,
            "tracking_confidence": f.tracking_confidence,
            "manual_root_keyframe": f.manual,
            "offset": f.offset, "warnings": f.warnings,
            "region": [(f.index % p.export_settings.columns) * layout.width,
                       (f.index // p.export_settings.columns) * layout.height, layout.width, layout.height],
        })
        if p.is_passthrough:
            for key in ("root", "ground", "raw_root", "filtered_root", "target_root", "tracking_confidence"):
                data["frames"][-1][key] = None
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
