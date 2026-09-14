"""Fixed project-level geometry. Alpha may warn, but may never move the reference."""
import math
import cv2
import numpy as np
from app.models.character_profile import CharacterProfile
from app.core.canvas_normalizer import CanvasTransform, premultiplied_resize
from app.core.ground_detection import detect_ground
from app.core.alpha_utils import component_mask

REFERENCE_WARNING = "Outside Character Reference Box"


def character_transform(profile):
    width, height = profile.canvas_size
    scale = profile.character_scale
    sw, sh = math.ceil(width/scale), math.ceil(height/scale)
    return CanvasTransform(sw, sh, width, height, round(sw*scale), round(sh*scale), 0, 0, scale)


def apply_character_motion(frames, profile):
    if not frames:
        return
    scale = profile.character_scale
    initial_motion = frames[0].motion_root or frames[0].root
    for f in frames:
        raw = f.raw_root or f.root
        f.tracked_root = tuple(v*scale for v in raw)
        f.character_correction = tuple(profile.canonical_root[a]-f.tracked_root[a] for a in (0, 1))
        f.correction = tuple(v/scale for v in f.character_correction)
        f.target_root = tuple(v/scale for v in profile.canonical_root)
        motion = f.motion_root or raw
        f.root_motion = tuple(motion[a]-initial_motion[a] for a in (0, 1))
        f.effective_policy = ("EXTRACT", "EXTRACT")


def review_reference_bounds(project):
    profile = project.character_profile
    for f in project.tracking_results:
        f.warnings = [w for w in f.warnings if w != REFERENCE_WARNING]
        if not profile or not f.bbox:
            continue
        l, top, r, bottom = f.bbox
        scale, (dx, dy) = profile.character_scale, f.offset
        bl, bt, br, bb = profile.reference_box
        # BBox is exclusive; compare the outermost pixel centers to reference lines.
        if l*scale+dx < bl-1e-6 or (r-1)*scale+dx > br+1e-6 or top*scale+dy < bt-1e-6 or (bottom-1)*scale+dy > bb+1e-6:
            f.warnings.append(REFERENCE_WARNING)


def prepare_character_calibration(rgba, canvas_size=(512, 512)):
    """Only first-time Idle calibration may use body detection to propose placement."""
    mask = component_mask(rgba[..., 3], 128, 0)
    count, labels, stats, centers = cv2.connectedComponentsWithStats(mask, 8)
    if count < 2:
        raise ValueError("Alpha Empty: no visible subject remains in any frame")
    main = 1+int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    l, top, width, height, area = stats[main]
    body_root = (float(centers[main, 0]), float(top+height*.5))
    body = rgba.copy()
    body[labels != main, 3] = 0
    ground, _ = detect_ground(body, body_root)
    if ground is None:
        raise ValueError("Ground Detection Failed")
    scale = min(canvas_size[0]/rgba.shape[1], canvas_size[1]/rgba.shape[0])
    origin = (canvas_size[0]/2, canvas_size[1]-max(1, canvas_size[1]/16))
    placement = (origin[0]-body_root[0]*scale, origin[1]-ground*scale)
    canonical = (origin[0], max(0., body_root[1]*scale+placement[1]))
    profile = CharacterProfile(tuple(canvas_size), scale, origin, canonical, max(.5, float(width)*scale*.65))
    scaled = premultiplied_resize(rgba, round(rgba.shape[1]*scale), round(rgba.shape[0]*scale), scale)
    return profile, placement, scaled
