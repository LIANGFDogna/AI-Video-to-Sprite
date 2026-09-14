"""Soft chroma-distance matte with edge reconstruction and spill suppression."""
import cv2
import numpy as np

from app.core.alpha_utils import component_mask
from app.models.project import ChromaSettings


def estimate_background(rgb: np.ndarray) -> tuple[int, int, int]:
    h, w = rgb.shape[:2]
    size = max(1, min(h, w) // 10)
    samples = np.concatenate([rgb[:size, :size, :3].reshape(-1, 3), rgb[:size, -size:, :3].reshape(-1, 3),
                              rgb[-size:, :size, :3].reshape(-1, 3), rgb[-size:, -size:, :3].reshape(-1, 3)])
    # Robust modal color bin excludes corners occupied by a small foreground area.
    bins = samples.astype(np.int32) // 24
    codes = bins[:, 0] * 121 + bins[:, 1] * 11 + bins[:, 2]
    mode = np.bincount(codes).argmax()
    return tuple(int(v) for v in np.median(samples[codes == mode], axis=0))


def chroma_key(rgb: np.ndarray, settings: ChromaSettings) -> np.ndarray:
    rgb = np.ascontiguousarray(rgb[..., :3])
    color = rgb.astype(np.float32) / 255.0
    key = np.array(settings.green_color, dtype=np.float32) / 255.0
    # Normalize chromaticity to remain tolerant to background illumination changes.
    chroma = color / np.maximum(color.sum(axis=2, keepdims=True), 0.08)
    key_chroma = key / max(float(key.sum()), 0.08)
    distance = np.linalg.norm(chroma - key_chroma, axis=2)
    hsv = cv2.cvtColor(color, cv2.COLOR_RGB2HSV)
    key_hsv = cv2.cvtColor(key.reshape(1, 1, 3), cv2.COLOR_RGB2HSV)[0, 0]
    hue_delta = np.abs(hsv[..., 0] - key_hsv[0])
    hue_delta = np.minimum(hue_delta, 360.0 - hue_delta) / 180.0
    # Unsaturated subjects remain distinct from a saturated green background.
    distance = 0.8 * distance + 0.2 * (hue_delta + np.abs(hsv[..., 1] - key_hsv[1]))
    matte = np.clip((distance - settings.tolerance) / max(settings.softness, 0.001), 0, 1)
    matte = matte * matte * (3.0 - 2.0 * matte)
    if settings.morphology:
        size = 2 * settings.morphology + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
        matte = cv2.morphologyEx(matte, cv2.MORPH_OPEN, kernel)
        matte = cv2.morphologyEx(matte, cv2.MORPH_CLOSE, kernel)
    if settings.noise_removal > 1:
        valid = component_mask((matte * 255).astype(np.uint8), 0, settings.noise_removal)
        matte *= valid
    if settings.edge_feather > 0:
        matte = cv2.GaussianBlur(matte, (0, 0), settings.edge_feather)
    matte[matte * 255 < settings.minimum_alpha] = 0
    if settings.spill_suppression:
        # Undo some background mixing at fractional-alpha edges, then cap excess green.
        a = np.maximum(matte[..., None], 0.15)
        reconstructed = np.clip((color - (1 - matte[..., None]) * key) / a, 0, 1)
        edge_weight = (1 - matte)[..., None] * settings.despill_strength
        color = color * (1 - edge_weight) + reconstructed * edge_weight
        excess = np.maximum(color[..., 1] - np.maximum(color[..., 0], color[..., 2]), 0)
        removal = excess * settings.despill_strength
        color[..., 1] -= removal
        # Redistribute luminance instead of leaving a dark fringe.
        color[..., 0] += removal * 0.25
        color[..., 2] += removal * 0.25
    result = np.empty((*rgb.shape[:2], 4), dtype=np.uint8)
    result[..., :3] = np.clip(color * 255 + 0.5, 0, 255).astype(np.uint8)
    result[..., 3] = np.clip(matte * 255 + 0.5, 0, 255).astype(np.uint8)
    result[result[..., 3] == 0, :3] = 0
    return result


def has_green_spill(rgba: np.ndarray) -> bool:
    rgb = rgba[..., :3].astype(np.int16)
    edges = (rgba[..., 3] > 16) & (rgba[..., 3] < 245)
    green = rgb[..., 1] - np.maximum(rgb[..., 0], rgb[..., 2]) > 35
    return bool(np.count_nonzero(edges & green) > max(10, np.count_nonzero(edges) * 0.1))
