"""Lossless source samples and one explicit, full-range RGBA8 conversion boundary."""
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


@dataclass(frozen=True)
class ImageFormat:
    color_mode: str
    channels: int
    bits_per_channel: int
    has_alpha: bool

    @property
    def bits_per_pixel(self):
        return self.channels * self.bits_per_channel

    def to_dict(self):
        return {**asdict(self), "bits_per_pixel": self.bits_per_pixel}


def sample_max(pixels):
    if pixels.dtype == np.uint8:
        return 255
    if pixels.dtype == np.uint16:
        return 65535
    raise ValueError("Unsupported image sample type; a safe full-range conversion is unavailable")


def to_rgba8(pixels):
    """Round every channel identically. Do not alter hidden RGB or pixel positions."""
    maximum = sample_max(pixels)
    if maximum == 255:
        return pixels
    # 65535 = 255 * 257. uint32 prevents overflow before nearest-value rounding.
    return ((pixels.astype(np.uint32) + 128) // 257).astype(np.uint8)


def read_rgba_with_format(path):
    """Pillow for standard images; OpenCV for native 16-bit RGB(A) samples.

    Pillow's RGB/RGBA mode alone does not describe source bit depth: RGB16 PNG
    also appears as RGB and convert('RGBA') would silently discard precision.
    """
    path = Path(path)
    with Image.open(path) as image:
        if getattr(image, "n_frames", 1) != 1:
            raise ValueError("Use one still image per file; animated or multipage images are not supported")
        width, height = image.size
        if min(width, height) < 1 or width * height > 64_000_000:
            raise ValueError("Invalid sequence image dimensions")
        bits = 8
        associated_alpha = False
        if image.format == "PNG":
            with path.open("rb") as stream:
                bits = stream.read(25)[24]  # IHDR bit depth is PER CHANNEL, not bpp.
        elif image.format == "TIFF":
            samples = image.tag_v2.get(258, (8,))
            samples = (samples,) if isinstance(samples, int) else samples
            if len(set(samples)) != 1 or any(v != 1 for v in image.tag_v2.get(339, (1,))):
                raise ValueError("Unsupported image sample type; a safe full-range conversion is unavailable")
            bits = samples[0]
            associated_alpha = 1 in image.tag_v2.get(338, ())
        elif image.mode.startswith(("I", "F")):
            raise ValueError("Unsupported image sample type; a safe full-range conversion is unavailable")
        mode = image.mode
        channels = len(image.getbands())
        has_alpha = "A" in image.getbands() or "a" in image.getbands() or "transparency" in image.info
        if bits == 16:
            decoded = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
            if decoded is None or decoded.dtype != np.uint16 or decoded.shape[:2] != (height, width):
                raise ValueError("Cannot safely decode this image at its original bit depth")
            if decoded.ndim == 2:
                rgb = np.repeat(decoded[..., None], 3, axis=2)
                rgba = np.concatenate((rgb, np.full((height, width, 1), 65535, np.uint16)), axis=2)
                mode, channels = "L", 1
            elif decoded.shape[2] in (3, 4):
                has_alpha = decoded.shape[2] == 4
                mode, channels = ("RGBA", 4) if has_alpha else ("RGB", 3)
                rgba = cv2.cvtColor(decoded, cv2.COLOR_BGRA2RGBA if has_alpha else cv2.COLOR_BGR2RGBA)
            else:
                raise ValueError("Cannot safely decode this image at its original bit depth")
            if associated_alpha and has_alpha:
                # TIFF may explicitly store associated RGB. Internal RGBA is straight.
                rgb = rgba[..., :3].astype(np.float32) * 65535
                rgb /= np.maximum(rgba[..., 3:4], 1)
                rgba[..., :3] = np.clip(rgb + .5, 0, 65535).astype(np.uint16)
                rgba[rgba[..., 3] == 0, :3] = 0
        elif bits <= 8:
            rgba = np.array(image.convert("RGBA"))
        else:
            raise ValueError("Unsupported image sample type; a safe full-range conversion is unavailable")
    return rgba, ImageFormat(mode, channels, bits, has_alpha)


def read_rgba(path):
    return read_rgba_with_format(path)[0]
