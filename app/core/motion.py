"""POSE + ROOT MOTION + NOISE. Only root curves are filtered; pixels are never blurred."""
import numpy as np

from app.models.project import MotionSettings

PRESETS = {
    "idle": ("LOCK", "GROUND_LOCK"), "walk": ("EXTRACT", "GROUND_LOCK"),
    "run": ("EXTRACT", "GROUND_LOCK"), "jump": ("EXTRACT", "EXTRACT"),
    "fall": ("EXTRACT", "EXTRACT"), "dash": ("EXTRACT", "GROUND_LOCK"),
    "ground_attack": ("EXTRACT", "GROUND_LOCK"), "air_attack": ("EXTRACT", "EXTRACT"),
    "cinematic": ("PRESERVE", "PRESERVE"), "custom": ("LOCK", "GROUND_LOCK"),
}


def filter_trajectory(values, window=7, spike_threshold=8.0, manual_indices=()):
    raw = np.asarray(values, np.float64)
    cleaned = raw.copy()
    spikes = set()
    manual = set(manual_indices)
    for i in range(1, len(raw)-1):
        before, after = raw[i] - raw[i-1], raw[i+1] - raw[i]
        if i not in manual and before * after < 0 and min(abs(before), abs(after)) > spike_threshold:
            neighbors = [j for j in range(max(0, i-2), min(len(raw), i+3)) if j != i]
            # A broad, accelerating parabola can reverse faster than the spike threshold.
            # Fit its surrounding curve without the suspect sample before classifying it.
            prediction = np.polynomial.polynomial.polyfit(np.array(neighbors)-i, raw[neighbors], min(2, len(neighbors)-1))[0]
            if abs(raw[i]-prediction) > spike_threshold:
                cleaned[i] = prediction
                spikes.add(i)
    result = cleaned.copy()
    radius = max(0, window // 2)
    boundaries = sorted({0, len(raw)-1, *manual})
    for i in range(len(raw)):
        if i in manual or radius == 0:
            continue
        left_limit = max((v for v in boundaries if v <= i), default=0)
        right_limit = min((v for v in boundaries if v >= i), default=len(raw)-1)
        # Endpoints are not isolated segments unless they are explicit manual anchors.
        if i == 0: right_limit = next((v for v in boundaries if v > i), len(raw)-1)
        if i == len(raw)-1: left_limit = max((v for v in boundaries if v < i), default=0)
        l, r = max(left_limit, i-radius), min(right_limit+1, i+radius+1)
        if r-l >= 3:
            x = np.arange(l, r, dtype=float) - i
            result[i] = np.polynomial.polynomial.polyfit(x, cleaned[l:r], min(2, r-l-1))[0]
    for i in manual:
        result[i] = raw[i]
    return result, spikes


def effective_policies(settings, index, count):
    x, y = settings.x_policy, settings.y_policy
    airborne_preset = settings.preset in ("jump", "fall", "air_attack")
    phases = settings.takeoff_frame >= 0 and settings.landing_frame >= 0
    in_air = settings.takeoff_frame <= index <= settings.landing_frame if phases else airborne_preset
    if y == "GROUND_LOCK" and in_air:
        y = "EXTRACT"
    return x, y


def process_motion(frames, settings: MotionSettings, fps):
    if not frames:
        return frames
    raw = np.array([f.raw_root if f.raw_root is not None else f.root for f in frames], float)
    manual = [f.index for f in frames if f.manual]
    filtered = raw.copy()
    spikes = set()
    for axis in (0, 1):
        filtered[:, axis], detected = filter_trajectory(raw[:, axis], settings.smoothing_window, settings.spike_threshold, manual)
        spikes.update(detected)
    unwrapped = filtered.copy()
    if settings.loop_correction and len(frames) > 1:
        filtered -= np.linspace(0, 1, len(frames))[:, None] * (filtered[-1] - filtered[0])
    base = filtered[0].copy()
    ground_base = next((f.ground for f in frames if f.ground is not None), base[1])
    velocity = np.diff(unwrapped, axis=0, prepend=unwrapped[:1]) * fps
    for i, f in enumerate(frames):
        f.raw_root = tuple(raw[i])
        f.filtered_root = tuple(filtered[i])
        f.motion_root = tuple(unwrapped[i])
        f.velocity = tuple(velocity[i])
        policies = effective_policies(settings, i, len(frames))
        target = filtered[i].copy()
        motion = np.zeros(2)
        for axis, policy in enumerate(policies):
            if policy in ("LOCK", "EXTRACT"):
                target[axis] = base[axis]
            elif policy == "GROUND_LOCK":
                ground = f.ground if f.ground is not None else raw[i, 1]
                # Align the measured body support while removing tracker noise separately.
                target[axis] = raw[i, axis] + ground_base - ground
            if policy == "EXTRACT" or (axis == 1 and settings.takeoff_frame >= 0 and settings.landing_frame >= 0):
                motion[axis] = unwrapped[i, axis] - unwrapped[0, axis]
        f.target_root = tuple(target)
        f.correction = tuple(target - raw[i])
        f.root_motion = tuple(motion)
        f.effective_policy = policies
        if i in spikes and "Root Spike" not in f.warnings:
            f.warnings.append("Root Spike")
    return frames


def review_warnings(frames, loop=True):
    for i, f in enumerate(frames):
        if f.tracking_confidence < .35 and "Low Confidence" not in f.warnings:
            f.warnings.append("Low Confidence")
        if i and f.cell_bbox and frames[i-1].cell_bbox:
            a, b = f.cell_bbox, frames[i-1].cell_bbox
            area = max(1, (a[2]-a[0])*(a[3]-a[1]))
            old = max(1, (b[2]-b[0])*(b[3]-b[1]))
            if max(area/old, old/area) > 1.5:
                f.warnings.append("Alpha Bounds Change")
            old_dims = np.maximum(1, [b[2]-b[0], b[3]-b[1]])
            dims = np.maximum(1, [a[2]-a[0], a[3]-a[1]])
            if np.max(np.maximum(dims/old_dims, old_dims/dims)) > 1.4:
                f.warnings.append("Size Jump")
        if i and np.linalg.norm(np.array(f.cell_root)-frames[i-1].cell_root) > 8:
            f.warnings.append("Root Jump")
    if loop and len(frames) > 1:
        first, last = frames[0], frames[-1]
        seam = np.linalg.norm(np.array(first.cell_root)-last.cell_root) > 3
        if first.cell_bbox and last.cell_bbox:
            seam |= np.max(np.abs(np.array(first.cell_bbox)-last.cell_bbox)) > 8
        if seam:
            for f in (first, last):
                f.warnings.append("Loop Discontinuity")
    for f in frames:
        f.warnings = list(dict.fromkeys(f.warnings))
