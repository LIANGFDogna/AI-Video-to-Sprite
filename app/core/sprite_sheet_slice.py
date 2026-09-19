"""Slice an imported Sprite Sheet into canonical frames.

Every frame is a fixed Cell Rect of the sheet: no alpha trim, no re-centering, no resize.
Pixels keep their original RGBA (passthrough), so the sliced frames become the canonical
source frames of a normal frame sequence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math

import numpy as np

FRAME_ORDERS = ("row_major", "row_major_reverse")
DEFAULT_FPS = 12.
MAX_CELLS = 100000


@dataclass
class SliceConfig:
    columns: int = 4
    rows: int = 1
    cell_width: int = 0
    cell_height: int = 0
    margin_left: int = 0
    margin_top: int = 0
    spacing_x: int = 0
    spacing_y: int = 0
    frame_count: int = 0
    frame_order: str = "row_major"
    fps: float = DEFAULT_FPS
    loop: bool = True
    ignore_empty: bool = False

    def validate(self):
        if not 1 <= int(self.columns) <= 4096 or not 1 <= int(self.rows) <= 4096:
            raise ValueError("Invalid Sprite Sheet grid")
        if int(self.columns) * int(self.rows) > MAX_CELLS:
            raise ValueError("Sprite Sheet grid is too large")
        for value in (self.cell_width, self.cell_height, self.margin_left, self.margin_top,
                      self.spacing_x, self.spacing_y, self.frame_count):
            if not isinstance(value, int) or value < 0:
                raise ValueError("Invalid Sprite Sheet slicing value")
        if self.frame_order not in FRAME_ORDERS:
            raise ValueError("Invalid Sprite Sheet frame order")
        if not math.isfinite(float(self.fps)) or not .1 <= float(self.fps) <= 240:
            raise ValueError("Animation FPS must be between 0.1 and 240")
        if self.loop not in (True, False) or self.ignore_empty not in (True, False):
            raise ValueError("Invalid Sprite Sheet slicing option")
        return self

    @classmethod
    def from_dict(cls, data):
        if isinstance(data, cls):
            return data
        data = dict(data or {})
        known = set(cls().__dict__)
        return cls(**{key: value for key, value in data.items() if key in known}).validate()

    def resolved(self, sheet_size):
        """Fill a missing Cell Size from the sheet: the grid must always be explicit."""
        width, height = int(sheet_size[0]), int(sheet_size[1])
        config = SliceConfig(**asdict(self))
        span_x = max(1, width - config.margin_left - max(0, config.columns - 1) * config.spacing_x)
        span_y = max(1, height - config.margin_top - max(0, config.rows - 1) * config.spacing_y)
        if not config.cell_width:
            config.cell_width = max(1, span_x // max(1, config.columns))
        if not config.cell_height:
            config.cell_height = max(1, span_y // max(1, config.rows))
        config.validate()
        return config

    def cells(self, sheet_size):
        """Fixed Cell Rects in frame order; nothing is trimmed or resized."""
        config = self.resolved(sheet_size)
        width, height = int(sheet_size[0]), int(sheet_size[1])
        rects = []
        for row in range(config.rows):
            order = range(config.columns) if config.frame_order == "row_major" else reversed(range(config.columns))
            for column in order:
                x = config.margin_left + column * (config.cell_width + config.spacing_x)
                y = config.margin_top + row * (config.cell_height + config.spacing_y)
                if x < 0 or y < 0 or x + config.cell_width > width or y + config.cell_height > height:
                    continue
                rects.append((x, y, config.cell_width, config.cell_height))
        if config.frame_count:
            rects = rects[:config.frame_count]
        return config, rects


def slice_frames(pixels, config):
    """Return (resolved_config, frames, skipped): RGBA passthrough of every fixed Cell Rect."""
    image = np.asarray(pixels)
    if image.ndim != 3 or image.shape[2] != 4:
        raise ValueError("Sprite Sheet must be RGBA")
    sheet_size = (image.shape[1], image.shape[0])
    resolved, rects = config.cells(sheet_size)
    if not rects:
        raise ValueError("The Sprite Sheet grid selects no frames")
    frames, skipped = [], []
    for index, (x, y, width, height) in enumerate(rects):
        cell = image[y:y + height, x:x + width].copy()
        if resolved.ignore_empty and not cell[..., 3].any():
            skipped.append(index)
            continue
        frames.append(cell)
    if not frames:
        raise ValueError("Every selected Sprite Sheet cell is empty")
    return resolved, frames, skipped


def _runs(values):
    result = []
    start = previous = None
    for value in values:
        if start is None:
            start = previous = value
            continue
        if value == previous + 1:
            previous = value
            continue
        result.append((start, previous))
        start = previous = value
    if start is not None:
        result.append((start, previous))
    return result


def detect_grid(pixels, max_cells=4096):
    """Optional assist: guess a grid from fully transparent separator lines."""
    image = np.asarray(pixels)
    if image.ndim != 3 or image.shape[2] != 4:
        return None
    alpha = image[..., 3] > 0
    if not alpha.any():
        return None
    columns = np.where(alpha.any(axis=0))[0]
    rows = np.where(alpha.any(axis=1))[0]
    left, top = int(columns.min()), int(rows.min())
    width = int(columns.max() - left) + 1
    height = int(rows.max() - top) + 1
    empty_columns = [index for index in range(left, left + width) if not alpha[:, index].any()]
    empty_rows = [index for index in range(top, top + height) if not alpha[index, :].any()]
    if not empty_columns and not empty_rows:
        return None

    def guess(values, span):
        separators = _runs(values)
        if not separators:
            return 1, span
        count = min(max_cells, len(separators) + 1)
        total = sum(end - start + 1 for start, end in separators)
        cell = max(1, (span - total) // max(1, count))
        return count, cell

    column_count, cell_width = guess(empty_columns, width)
    row_count, cell_height = guess(empty_rows, height)
    return SliceConfig(columns=column_count, rows=row_count, cell_width=cell_width, cell_height=cell_height,
                       margin_left=left, margin_top=top).validate()
