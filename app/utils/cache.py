from collections import OrderedDict
from pathlib import Path

import numpy as np
import cv2
from PIL import Image
from app.utils.rgba_image import read_rgba, sample_max


class FrameCache:
    """Read-only array LRU bounded by bytes, including a single oversized frame."""

    def __init__(self, max_bytes: int = 128 * 1024 * 1024):
        self.max_bytes = max_bytes
        self._items = OrderedDict()
        self._bytes = 0

    def clear(self):
        self._items.clear()
        self._bytes = 0

    def read(self, path: Path) -> np.ndarray:
        stat = path.stat()
        key = (str(path), stat.st_mtime_ns, stat.st_size)
        if key in self._items:
            self._items.move_to_end(key)
            return self._items[key]
        result = read_rgba(path)
        result.flags.writeable = False
        if result.nbytes <= self.max_bytes:
            while self._items and self._bytes + result.nbytes > self.max_bytes:
                _, old = self._items.popitem(last=False)
                self._bytes -= old.nbytes
            self._items[key] = result
            self._bytes += result.nbytes
        return result


def save_rgba(path: Path, pixels: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    if sample_max(pixels) == 65535:
        ok, encoded = cv2.imencode(".png", cv2.cvtColor(pixels, cv2.COLOR_RGBA2BGRA))
        if not ok:
            raise ValueError("Cannot safely encode this image at its original bit depth")
        temp.write_bytes(encoded.tobytes())
    else:
        Image.fromarray(pixels).save(temp, format="PNG")
    temp.replace(path)
