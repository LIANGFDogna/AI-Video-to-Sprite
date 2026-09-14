"""Alignment pivots and premultiplied-alpha image translation."""
import cv2
import numpy as np

from app.models.frame_data import FrameData
from app.utils.rgba_image import sample_max


def pivot_for(frame: FrameData, mode: str, source_width: int) -> tuple[float, float]:
    bottom = frame.bbox[3] - 1 if frame.bbox else frame.root[1]
    if mode == "ROOT XY LOCK":
        return tuple(frame.root)
    if mode == "GROUND LOCK":
        return (source_width - 1) / 2, bottom
    if mode == "ROOT X + GROUND Y":
        return frame.root[0], bottom
    raise ValueError(f"Unknown alignment mode: {mode}")


def warp_rgba(rgba: np.ndarray, width: int, height: int, scale: float,
              offset: tuple[float, float]) -> np.ndarray:
    if width * height > 64_000_000:
        raise ValueError("A single cell exceeds the 64 megapixel memory limit. Reduce cell dimensions or scale.")
    if max(width, height, *rgba.shape[:2]) >= 32767:
        raise ValueError("OpenCV requires frame and cell dimensions below 32767 pixels")
    maximum = sample_max(rgba)
    pixels = rgba.astype(np.float32) / maximum
    pixels[..., :3] *= pixels[..., 3:4]
    matrix = np.array([[scale, 0, offset[0]], [0, scale, offset[1]]], np.float32)
    warped = cv2.warpAffine(pixels, matrix, (width, height), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    np.divide(warped[..., :3], np.maximum(warped[..., 3:4], 1 / 65535), out=warped[..., :3])
    result = np.clip(warped * maximum + 0.5, 0, maximum).astype(rgba.dtype)
    result[result[..., 3] == 0, :3] = 0
    return result
