import cv2
import numpy as np

from app.models.frame_data import BBox
from app.utils.rgba_image import sample_max


def component_mask(alpha: np.ndarray, threshold: int = 16, minimum_size: int = 12) -> np.ndarray:
    mask = (alpha > threshold * (sample_max(alpha) / 255)).astype(np.uint8)
    if minimum_size <= 1 or not mask.any():
        return mask
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    keep = np.zeros(count, dtype=np.uint8)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= minimum_size
    return keep[labels]


def alpha_bbox(rgba: np.ndarray, threshold: int = 16, minimum_size: int = 12) -> BBox | None:
    mask = component_mask(rgba[..., 3], threshold, minimum_size)
    points = cv2.findNonZero(mask)
    if points is None:
        return None
    x, y, w, h = cv2.boundingRect(points)
    return x, y, x + w, y + h


def root_inside(rgba: np.ndarray, root: tuple[float, float], threshold: int = 16) -> bool:
    x, y = (int(round(v)) for v in root)
    return 0 <= y < rgba.shape[0] and 0 <= x < rgba.shape[1] and rgba[y, x, 3] > threshold * (sample_max(rgba) / 255)
