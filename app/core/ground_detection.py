"""Body-only, ROI-constrained robust foot support; detached weapons/FX are ignored."""
import cv2
import numpy as np

from app.core.alpha_utils import alpha_bbox, component_mask


def detect_ground(rgba, root, roi=None, threshold=16, minimum_size=12):
    bbox = alpha_bbox(rgba, threshold, minimum_size)
    if bbox is None:
        return None, None
    h, w = rgba.shape[:2]
    if roi is None:
        l, t, r, b = bbox
        half_width = max(8, (r-l) * .22)
        roi = (root[0]-half_width, max(root[1], t+(b-t)*.4), root[0]+half_width, b)
    l, t, r, b = [int(round(v)) for v in roi]
    l, r, t, b = max(0, l), min(w, r), max(0, t), min(h, b)
    if l >= r or t >= b:
        return None, None
    mask = component_mask(rgba[t:b, l:r, 3], threshold, minimum_size)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    if count <= 1:
        return None, (l, t, r, b)
    areas = stats[1:, cv2.CC_STAT_AREA]
    # Keep comparable leg components, reject small isolated particles/weapons.
    keep = np.zeros(count, np.uint8)
    keep[1:] = areas >= max(minimum_size, int(areas.max() * .3))
    body = keep[labels]
    support = body.sum(axis=1)
    rows = np.flatnonzero(support >= max(2, float(support.max()) * .25))
    if not len(rows):
        return None, (l, t, r, b)
    # A sparse tip extending below the main horizontal support cannot set the baseline.
    return float(t + rows[-1]), (l, t, r, b)
