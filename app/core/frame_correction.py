"""Per-frame alignment correction: one translation applied after the Animation Transform."""
import copy
from app.core.alpha_utils import alpha_bbox
from app.core.animation_transform import translate_rgba

FRAME_CORRECTION_OVERFLOW = "Frame correction exceeds project canvas."


def frame_correction(project, index):
    "Zero unless the Animation stores a correction for this output frame."
    return project.frame_correction(index)


def apply_frame_correction(project, pixels, frame, index):
    dx, dy = project.frame_correction(index)
    if not dx and not dy:
        return pixels, frame
    output = translate_rgba(pixels, dx, dy)
    frame = copy.deepcopy(frame)
    bbox = frame.cell_bbox
    h, w = pixels.shape[:2]
    if bbox and (bbox[0] + dx < 0 or bbox[1] + dy < 0 or bbox[2] + dx > w or bbox[3] + dy > h):
        frame.warnings = list(dict.fromkeys([*frame.warnings, FRAME_CORRECTION_OVERFLOW]))
    frame.cell_root = (frame.cell_root[0] + dx, frame.cell_root[1] + dy)
    frame.cell_ground = None if frame.cell_ground is None else frame.cell_ground + dy
    frame.cell_bbox = alpha_bbox(output, 0, 0)
    frame.offset = (frame.offset[0] + dx, frame.offset[1] + dy)
    return output, frame
