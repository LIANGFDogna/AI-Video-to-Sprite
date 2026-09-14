"""Resolution-center crop/pad only. Never examines alpha, roots or subject content."""
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class CanvasFit:
    source: tuple[int, int]
    target: tuple[int, int]

    def __post_init__(self):
        for size in (self.source, self.target):
            if len(size) != 2 or not all(isinstance(v, int) and 1 <= v <= 16384 for v in size) or size[0]*size[1] > 64_000_000:
                raise ValueError("Invalid project canvas dimensions")

    @property
    def padding(self):
        x, y = (max(0, b-a) for a, b in zip(self.source, self.target))
        return x//2, y//2, x-x//2, y-y//2  # left, top, right, bottom

    @property
    def crop(self):
        x, y = (max(0, a-b) for a, b in zip(self.source, self.target))
        return x//2, y//2, x-x//2, y-y//2

    @property
    def offset(self):
        return self.padding[0]-self.crop[0], self.padding[1]-self.crop[1]

    def apply(self, rgba, fill=(0, 0, 0, 0)):
        if rgba.shape != (self.source[1], self.source[0], 4) or rgba.dtype not in (np.uint8, np.uint16):
            raise ValueError("Invalid canvas fit image")
        result = np.empty((self.target[1], self.target[0], 4), dtype=rgba.dtype)
        result[:] = fill
        sx, sy = self.crop[:2]
        dx, dy = self.padding[:2]
        w, h = (min(a, b) for a, b in zip(self.source, self.target))
        result[dy:dy+h, dx:dx+w] = rgba[sy:sy+h, sx:sx+w]
        return result
