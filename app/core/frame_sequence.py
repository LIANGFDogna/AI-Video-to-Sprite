"""File-per-frame image sequences. No chroma, motion or alignment dependencies."""
from dataclasses import dataclass
from pathlib import Path
import re
import numpy as np
from app.utils.rgba_image import ImageFormat, read_rgba, read_rgba_with_format
from app.utils.ffmpeg import check_cancel

IMAGE_EXTENSIONS = {".png", ".webp", ".tif", ".tiff", ".bmp", ".jpg", ".jpeg"}


def natural_key(name):
    parts = tuple(int(p) if p.isdigit() else p.casefold() for p in re.split(r"(\d+)", name))
    return parts, name.casefold(), name


def sequence_paths(folder):
    folder = Path(folder)
    if not folder.is_dir():
        raise ValueError("Sequence folder is missing")
    paths = sorted((p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS), key=lambda p: natural_key(p.name))
    if not paths:
        raise ValueError("No supported images in this folder. Select a single animation folder; PNG is recommended.")
    return paths


@dataclass(frozen=True)
class SequenceScan:
    folder: str
    names: tuple[str, ...]
    sizes: tuple[tuple[int, int], ...]
    alpha: str
    formats: tuple[ImageFormat, ...] = ()

    @property
    def canvas_size(self):
        return max(s[0] for s in self.sizes), max(s[1] for s in self.sizes)

    @property
    def mixed_sizes(self):
        return len(set(self.sizes)) != 1


def scan_sequence(folder, progress=lambda *a: None, cancel=None):
    paths = sequence_paths(folder)
    sizes, alpha_modes, formats = [], set(), []
    for i, path in enumerate(paths):
        check_cancel(cancel)
        try:
            rgba, info = read_rgba_with_format(path)
            alpha_modes.add(info.has_alpha)
            sizes.append((rgba.shape[1], rgba.shape[0]))
            formats.append(info)
        except Exception:
            import logging
            logging.getLogger("aivsprite.sequence").exception("Cannot import sequence image: %s", path)
            raise
        progress(i+1, len(paths), "Scanning sequence frames")
    result = SequenceScan(str(Path(folder).resolve()), tuple(p.name for p in paths), tuple(sizes),
        "RGBA" if alpha_modes == {True} else "RGB" if alpha_modes == {False} else "Mixed RGB / RGBA", tuple(formats))
    if result.canvas_size[0]*result.canvas_size[1] > 64_000_000:
        raise ValueError("Invalid sequence image dimensions")
    return result


def read_sequence_frame(path, canvas_size):
    rgba = read_rgba(path)
    width, height = canvas_size
    if rgba.shape[:2] == (height, width):
        return rgba
    if rgba.shape[0] > height or rgba.shape[1] > width:
        raise ValueError("Sequence images changed during import. Scan the folder again.")
    canvas = np.zeros((height, width, 4), rgba.dtype)
    canvas[:rgba.shape[0], :rgba.shape[1]] = rgba
    return canvas
