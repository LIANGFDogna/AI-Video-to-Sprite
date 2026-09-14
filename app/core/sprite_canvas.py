from __future__ import annotations

import math
import numpy as np

from app.core.alignment import pivot_for, warp_rgba
from app.core.alpha_utils import alpha_bbox
from app.models.frame_data import CellLayout, FrameData
from app.models.project import SpriteSettings
from app.utils.rgba_image import to_rgba8


def calculate_layout(frames: list[FrameData], mode: str, source_width: int, settings: SpriteSettings,
                     scale: float = 1.0) -> CellLayout:
    valid = [f for f in frames if f.bbox is not None]
    if not valid:
        raise ValueError("Alpha Empty: no visible subject remains in any frame")
    extents = []
    for f in valid:
        px, py = pivot_for(f, mode, source_width)
        l, t, r, b = f.bbox
        # Conservative coverage for interpolated pixels, including zero padding.
        guard = math.ceil(scale) if scale != 1 or px % 1 or py % 1 else 0
        extents.append((math.floor((l - px) * scale) - guard, math.floor((t - py) * scale) - guard,
                        math.ceil((r - px) * scale) + guard, math.ceil((b - py) * scale) + guard))
    left, top = min(e[0] for e in extents), min(e[1] for e in extents)
    right, bottom = max(e[2] for e in extents), max(e[3] for e in extents)
    required_w = max(1, right - left + settings.padding * 2)
    ground = mode != "ROOT XY LOCK"
    required_h = max(1, bottom - top + settings.padding + (max(settings.padding, settings.bottom_margin) if ground else settings.padding))
    width, height = required_w, required_h
    if settings.mode == "AUTO":
        if settings.round_up:
            width = math.ceil(width / settings.round_up) * settings.round_up
            height = math.ceil(height / settings.round_up) * settings.round_up
    elif settings.mode == "CUSTOM":
        width, height = settings.width, settings.height
    else:
        width, height = (int(n) for n in settings.mode.split("x"))
    target_x = (width - (right - left)) / 2 - left
    if ground:
        # Keep the baseline integral so the lowest effective alpha pixel is exact.
        baseline = height - 1 - max(settings.bottom_margin, settings.padding)
        target_y = float(baseline)
    else:
        target_y = (height - (bottom - top)) / 2 - top
        baseline = height - 1 - settings.bottom_margin
    layout = CellLayout(width, height, (target_x, target_y), baseline, required_w, required_h)
    for f in frames:
        px, py = pivot_for(f, mode, source_width)
        f.offset = (target_x - px * scale, target_y - py * scale)
        f.cell_root = (f.root[0] * scale + f.offset[0], f.root[1] * scale + f.offset[1])
        f.warnings = [w for w in f.warnings if w != "Clipping"]
        if f.bbox:
            l, t, r, b = f.bbox
            f.cell_bbox = (math.floor(l * scale + f.offset[0]), math.floor(t * scale + f.offset[1]),
                           math.ceil((r - 1) * scale + f.offset[0]) + 1, math.ceil((b - 1) * scale + f.offset[1]) + 1)
            a, c, d, e = f.cell_bbox
            if a < 0 or c < 0 or d > width or e > height:
                layout.clipped_frames.append(f.index)
                f.warnings.append("Clipping")
    return layout


def render_cell(rgba: np.ndarray, frame: FrameData, layout: CellLayout, scale: float,
                mode: str, threshold: int, minimum_size: int) -> np.ndarray:
    result = to_rgba8(warp_rgba(rgba, layout.width, layout.height, scale, frame.offset))
    bbox = alpha_bbox(result, threshold, max(1, round(minimum_size * scale * scale)))
    if bbox and mode != "ROOT XY LOCK" and frame.index not in layout.clipped_frames:
        correction = int(layout.ground_baseline - (bbox[3] - 1))
        if correction:
            # Correct the rasterized alpha threshold baseline after subpixel resampling.
            frame.offset = (frame.offset[0], frame.offset[1] + correction)
            frame.cell_root = (frame.cell_root[0], frame.cell_root[1] + correction)
            result = to_rgba8(warp_rgba(rgba, layout.width, layout.height, scale, frame.offset))
            bbox = alpha_bbox(result, threshold, max(1, round(minimum_size * scale * scale)))
    frame.cell_bbox = bbox
    return result
