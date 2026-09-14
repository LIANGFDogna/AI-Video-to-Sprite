"""One source-canvas transform shared by the entire animation; never bbox crop."""
from dataclasses import dataclass

import cv2
import numpy as np
from app.utils.rgba_image import sample_max


@dataclass(frozen=True)
class CanvasTransform:
    source_width: int
    source_height: int
    target_width: int
    target_height: int
    resized_width: int
    resized_height: int
    offset_x: int
    offset_y: int
    uniform_scale: float | None = None

    @property
    def scale_x(self):
        return self.uniform_scale if self.uniform_scale is not None else self.resized_width / self.source_width

    @property
    def scale_y(self):
        return self.uniform_scale if self.uniform_scale is not None else self.resized_height / self.source_height

    def point(self, point):
        return point[0] * self.scale_x + self.offset_x, point[1] * self.scale_y + self.offset_y

    def bbox(self, bbox):
        if bbox is None:
            return None
        return (*self.point(bbox[:2]), *self.point(bbox[2:]))


def canvas_transform(width, height, target_width, target_height, preserve_aspect=True):
    if min(width, height, target_width, target_height) < 1 or target_width * target_height > 64_000_000:
        raise ValueError("Invalid normalization dimensions")
    if preserve_aspect:
        scale = min(target_width / width, target_height / height)
        rw, rh = max(1, round(width * scale)), max(1, round(height * scale))
    else:
        rw, rh = target_width, target_height
    return CanvasTransform(width, height, target_width, target_height, rw, rh,
                           (target_width - rw) // 2, (target_height - rh) // 2)


def premultiplied_resize(rgba, width, height, uniform_scale=None):
    # Source/cache may be RGBA16; only quantize after the float32 resampling.
    pixels = rgba.astype(np.float32) / sample_max(rgba)
    pixels[..., :3] *= pixels[..., 3:4]
    interpolation = cv2.INTER_AREA if width <= rgba.shape[1] and height <= rgba.shape[0] else cv2.INTER_CUBIC
    resized = cv2.resize(pixels, (width, height), interpolation=interpolation) if uniform_scale is None else cv2.resize(pixels, None, fx=uniform_scale, fy=uniform_scale, interpolation=interpolation)
    resized = np.clip(resized, 0, 1)
    np.divide(resized[..., :3], np.maximum(resized[..., 3:4], 1e-8), out=resized[..., :3])
    result = np.clip(resized * 255 + .5, 0, 255).astype(np.uint8)
    result[result[..., 3] == 0, :3] = 0
    return result


def normalize_canvas(rgba, transform: CanvasTransform):
    if rgba.shape[:2] != (transform.source_height, transform.source_width):
        raise ValueError("Source canvas size differs between frames")
    resized = premultiplied_resize(rgba, transform.resized_width, transform.resized_height, transform.uniform_scale)
    output = np.zeros((transform.target_height, transform.target_width, 4), np.uint8)
    x, y = transform.offset_x, transform.offset_y
    height, width = min(resized.shape[0], output.shape[0]-y), min(resized.shape[1], output.shape[1]-x)
    output[y:y+height, x:x+width] = resized[:height, :width]
    return output
