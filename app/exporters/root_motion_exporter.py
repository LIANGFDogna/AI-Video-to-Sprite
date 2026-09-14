import json
from pathlib import Path


def root_motion_data(project):
    if project.is_passthrough:
        return {"schema_version": 1, "animation_name": project.export_settings.animation_name, "available": False,
            "fps": project.video.fps, "processing_mode": project.processing_mode, "units": "target_canvas_pixels", "frames": [],
            "usage": "Passthrough input: Root Tracking and motion extraction were skipped."}
    scale = project.layout.normalize_scale
    frames = []
    previous = (0., 0.)
    raw_previous = (0., 0.)
    first_raw = (project.tracking_results[0].raw_root or project.tracking_results[0].root) if project.tracking_results else (0., 0.)
    for f in project.tracking_results:
        cumulative = (f.root_motion[0]*scale[0], f.root_motion[1]*scale[1])
        frames.append({"frame": f.index, "time": f.index/project.video.fps,
                       "delta_x": cumulative[0]-previous[0], "delta_y": cumulative[1]-previous[1],
                       "cumulative_x": cumulative[0], "cumulative_y": cumulative[1],
                       "confidence": f.tracking_confidence, "policy_x": f.effective_policy[0], "policy_y": f.effective_policy[1]})
        previous = cumulative
        raw = f.raw_root or f.root
        raw_cumulative = tuple((raw[a]-first_raw[a])*scale[a] for a in (0, 1))
        frames[-1].update(raw_delta_x=raw_cumulative[0]-raw_previous[0], raw_delta_y=raw_cumulative[1]-raw_previous[1],
                          raw_cumulative_x=raw_cumulative[0], raw_cumulative_y=raw_cumulative[1])
        raw_previous = raw_cumulative
    return {"schema_version": 1, "animation_name": project.export_settings.animation_name,
            "units": "target_canvas_pixels", "fps": project.video.fps,
            "usage": "Optional motion reference. Drive CharacterBody2D from the game state machine; do not animate its position directly.",
            "loop_visual_correction": project.motion_settings.loop_correction, "frames": frames}


def write_root_motion(project, path: Path):
    path.write_text(json.dumps(root_motion_data(project), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
