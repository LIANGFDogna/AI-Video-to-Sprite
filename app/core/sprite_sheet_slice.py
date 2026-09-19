"""Slice an imported Sprite Sheet into canonical frames.

Every frame is a fixed Cell Rect of the sheet: no alpha trim, no re-centering, no resize.
Pixels keep their original RGBA (passthrough), so the sliced frames become the canonical
source frames of a normal frame sequence.

One function, calculate_cells(), is the single source of truth for the Cell Size, the grid
preview, the effective frame count and the frames the slicer writes.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
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
    auto_layout: bool = True

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
        if self.auto_layout not in (True, False):
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
        """Cell Size actually used, after the Auto or Manual layout rule."""
        return calculate_cells(self, sheet_size).config

    def cells(self, sheet_size):
        """Candidate Cell Rects in frame order: valid cells only, before the empty filter."""
        layout = calculate_cells(self, sheet_size)
        return layout.config, [(cell.x, cell.y, cell.width, cell.height) for cell in layout.candidates]


@dataclass
class LayoutCell:
    index: int
    x: int
    y: int
    width: int
    height: int
    valid: bool
    empty: bool = False
    frame_index: int | None = None
    skipped: bool = False


@dataclass
class LayoutResult:
    config: SliceConfig
    sheet_size: tuple[int, int]
    cells: list[LayoutCell] = field(default_factory=list)
    candidates: list[LayoutCell] = field(default_factory=list)
    frames: list[LayoutCell] = field(default_factory=list)
    invalid: list[int] = field(default_factory=list)
    skipped: list[int] = field(default_factory=list)
    remainder: tuple[int, int] = (0, 0)

    @property
    def frame_count(self):
        return len(self.frames)

    @property
    def unused(self):
        return self.remainder[0] > 0 or self.remainder[1] > 0


def calculate_cells(config, image):
    """The one calculation used by the preview, the summary and the slicer.

    image is either the RGBA pixels or a (width, height) pair; without pixels the empty
    check is skipped, so the layout stays identical either way.
    """
    if isinstance(image, (tuple, list)):
        width, height = int(image[0]), int(image[1])
        alpha = None
    else:
        pixels = np.asarray(image)
        if pixels.ndim != 3 or pixels.shape[2] != 4:
            raise ValueError("Sprite Sheet must be RGBA")
        height, width = int(pixels.shape[0]), int(pixels.shape[1])
        alpha = pixels[..., 3]
    config = SliceConfig(**asdict(config)).validate()
    available_x = max(1, width - config.margin_left)
    available_y = max(1, height - config.margin_top)
    if config.auto_layout:
        # Auto Layout: Columns and Rows always drive the Cell Size.
        span_x = max(1, available_x - max(0, config.columns - 1) * config.spacing_x)
        span_y = max(1, available_y - max(0, config.rows - 1) * config.spacing_y)
        config.cell_width = max(1, span_x // max(1, config.columns))
        config.cell_height = max(1, span_y // max(1, config.rows))
        # A remainder that divides evenly between the gaps becomes Spacing, never a stale Cell.
        used_x = config.cell_width * config.columns + config.spacing_x * max(0, config.columns - 1)
        used_y = config.cell_height * config.rows + config.spacing_y * max(0, config.rows - 1)
        rest_x, rest_y = available_x - used_x, available_y - used_y
        if config.columns > 1 and rest_x > 0 and rest_x % (config.columns - 1) == 0:
            config.spacing_x += rest_x // (config.columns - 1)
        if config.rows > 1 and rest_y > 0 and rest_y % (config.rows - 1) == 0:
            config.spacing_y += rest_y // (config.rows - 1)
    else:
        # Manual Layout: Rows and Columns only decide how many cells are tried.
        if not config.cell_width:
            config.cell_width = max(1, available_x // max(1, config.columns))
        if not config.cell_height:
            config.cell_height = max(1, available_y // max(1, config.rows))
    layout = LayoutResult(config, (width, height))
    for row in range(config.rows):
        order = range(config.columns) if config.frame_order == "row_major" else reversed(range(config.columns))
        for column in order:
            x = config.margin_left + column * (config.cell_width + config.spacing_x)
            y = config.margin_top + row * (config.cell_height + config.spacing_y)
            valid = x >= 0 and y >= 0 and x + config.cell_width <= width and y + config.cell_height <= height
            empty = False
            if valid and alpha is not None:
                empty = not alpha[y:y + config.cell_height, x:x + config.cell_width].any()
            cell = LayoutCell(len(layout.cells), x, y, config.cell_width, config.cell_height, valid, empty)
            layout.cells.append(cell)
            if valid:
                layout.candidates.append(cell)
            else:
                layout.invalid.append(cell.index)
    candidates = layout.candidates
    if config.frame_count:
        candidates = candidates[:config.frame_count]
    layout.candidates = candidates
    for cell in candidates:
        if config.ignore_empty and cell.empty:
            cell.skipped = True
            layout.skipped.append(cell.index)
            continue
        cell.frame_index = len(layout.frames)
        layout.frames.append(cell)
    used_x = config.cell_width * config.columns + config.spacing_x * max(0, config.columns - 1)
    used_y = config.cell_height * config.rows + config.spacing_y * max(0, config.rows - 1)
    layout.remainder = (max(0, width - config.margin_left - used_x), max(0, height - config.margin_top - used_y))
    return layout


def slice_frames(pixels, config):
    """Return (resolved config, frames, skipped): RGBA passthrough of the calculated layout."""
    image = np.asarray(pixels)
    layout = calculate_cells(config, image)
    if not layout.candidates:
        raise ValueError("The Sprite Sheet grid selects no frames")
    if not layout.frames:
        raise ValueError("Every selected Sprite Sheet cell is empty")
    frames = [image[cell.y:cell.y + cell.height, cell.x:cell.x + cell.width].copy() for cell in layout.frames]
    return layout.config, frames, list(layout.skipped)


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
    empty_rows = [index for index in range(left, top + height) if not alpha[index, :].any()]
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
