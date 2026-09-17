"""Pencil / Eraser raster edits above the aligned frame, below the Animation Transform.

Final pixel path per frame:

    Source / Keyed RGBA -> aligned canvas -> PerFrame Raster Edit
        -> Animation Transform -> Frame Correction -> FinalFrameProvider

Every edit is Animation + frame scoped and stores two immutable layers per revision:
a paint layer (RGBA) and an erase mask (L). Erasing only hides the frame's own pixels,
and painting over an erased area brings pixels back, so nothing is destructively deleted.
"""
from __future__ import annotations

from collections import OrderedDict
import math
from pathlib import Path

import numpy as np
from PIL import Image

from app.models.timeline_edit import FrameOverride

LAYER_BUDGET = 64 * 1024 * 1024
_LAYER_CACHE = OrderedDict()
_LAYER_BYTES = 0


def _cache_read(path: Path, loader):
    global _LAYER_BYTES
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    if key in _LAYER_CACHE:
        _LAYER_CACHE.move_to_end(key)
        return _LAYER_CACHE[key]
    result = loader(path)
    if result.nbytes <= LAYER_BUDGET:
        while _LAYER_CACHE and _LAYER_BYTES + result.nbytes > LAYER_BUDGET:
            _, old = _LAYER_CACHE.popitem(last=False)
            _LAYER_BYTES -= old.nbytes
        _LAYER_CACHE[key] = result
        _LAYER_BYTES += result.nbytes
    return result


def clear_layer_cache():
    _LAYER_CACHE.clear()
    global _LAYER_BYTES
    _LAYER_BYTES = 0


def empty_paint(shape):
    return np.zeros((int(shape[0]), int(shape[1]), 4), np.uint8)


def empty_erase(shape):
    return np.zeros((int(shape[0]), int(shape[1])), np.uint8)


def save_layer(path, array):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    Image.fromarray(array).save(temp, format="PNG")
    temp.replace(path)


def load_paint(path, shape=None):
    array = np.array(_cache_read(Path(path), lambda p: np.array(Image.open(p).convert("RGBA"))))
    if shape is not None and array.shape[:2] != (int(shape[0]), int(shape[1])):
        raise ValueError("Raster edit paint layer does not match the frame")
    return array


def load_erase(path, shape=None):
    array = np.array(_cache_read(Path(path), lambda p: np.array(Image.open(p).convert("L"))))
    if shape is not None and array.shape[:2] != (int(shape[0]), int(shape[1])):
        raise ValueError("Raster edit erase layer does not match the frame")
    return array


def composite_edit(source, paint=None, erase=None):
    """Straight-alpha composite: erase hides the frame's own pixels, then paint is drawn."""
    erasing = erase is not None and bool(np.any(erase))
    painting = paint is not None and bool(np.any(paint[..., 3]))
    if not erasing and not painting:
        return source
    base = source.astype(np.float32) / 255.
    if erasing:
        base[..., 3] *= 1. - erase.astype(np.float32) / 255.
    if not painting:
        return np.clip(base * 255. + .5, 0, 255).astype(np.uint8)
    top = paint.astype(np.float32) / 255.
    top_alpha = top[..., 3:4]
    out_alpha = top_alpha + base[..., 3:4] * (1. - top_alpha)
    denom = np.maximum(out_alpha, 1e-8)
    out = np.empty_like(base)
    out[..., 3:4] = out_alpha
    out[..., :3] = (top[..., :3] * top_alpha + base[..., :3] * base[..., 3:4] * (1. - top_alpha)) / denom
    return np.clip(out * 255. + .5, 0, 255).astype(np.uint8)


def brush_points(x, y, size):
    "Hard circular brush in frame-local pixels; size is the diameter including the center."
    radius = max(.5, float(size) / 2.)
    reach = int(math.ceil(radius))
    xs, ys = np.meshgrid(np.arange(-reach, reach + 1), np.arange(-reach, reach + 1))
    inside = (xs * xs + ys * ys) <= radius * radius
    return [(int(x) + int(dx), int(y) + int(dy)) for dy, dx in zip(ys[inside], xs[inside])]


def stroke_points(x0, y0, x1, y1, size):
    "Every point between two drag samples so a fast stroke stays continuous."
    span = max(abs(int(x1) - int(x0)), abs(int(y1) - int(y0)))
    step = max(1, int(size) // 4)
    count = max(1, int(math.ceil(span / step)))
    return [(round(x0 + (x1 - x0) * i / count), round(y0 + (y1 - y0) * i / count)) for i in range(count + 1)]


def _clip_brush(points, width, height):
    return [(x, y) for x, y in points if 0 <= x < width and 0 <= y < height]


def stamp_pencil(paint, x, y, size, color):
    """Source-over one brush dot of an 8-bit RGBA colour into the paint layer."""
    height, width = paint.shape[:2]
    points = _clip_brush(brush_points(x, y, size), width, height)
    if not points:
        return
    src = np.array(color, np.float32) / 255.
    alpha = src[3]
    if alpha <= 0:
        return
    columns = np.array([p[0] for p in points])
    rows = np.array([p[1] for p in points])
    dst = paint[rows, columns].astype(np.float32) / 255.
    out_alpha = alpha + dst[:, 3] * (1. - alpha)
    denom = np.maximum(out_alpha, 1e-8)
    out_rgb = (src[:3] * alpha + dst[:, :3] * dst[:, 3:4] * (1. - alpha)) / denom[:, None]
    result = np.empty((len(points), 4), np.float32)
    result[:, :3] = out_rgb
    result[:, 3] = out_alpha
    paint[rows, columns] = np.clip(result * 255. + .5, 0, 255).astype(np.uint8)


def stamp_eraser(paint, erase, x, y, size):
    """Hide the frame's own pixels and drop anything painted at the same spot."""
    height, width = paint.shape[:2]
    points = _clip_brush(brush_points(x, y, size), width, height)
    if not points:
        return
    columns = np.array([p[0] for p in points])
    rows = np.array([p[1] for p in points])
    erase[rows, columns] = 255
    paint[rows, columns] = 0


def shift_layer(array, dx, dy):
    "Integer translation that keeps the layer size; mirrors translate_rgba semantics."
    dx, dy = int(round(dx)), int(round(dy))
    if not dx and not dy:
        return array
    out = np.zeros_like(array)
    height, width = array.shape[:2]
    sx, sy, tx, ty = max(0, -dx), max(0, -dy), max(0, dx), max(0, dy)
    cw, ch = min(width - sx, width - tx), min(height - sy, height - ty)
    if cw > 0 and ch > 0:
        out[ty:ty + ch, tx:tx + cw] = array[sy:sy + ch, sx:sx + cw]
    return out


def scale_layer(array, size):
    height, width = int(size[0]), int(size[1])
    method = Image.Resampling.BICUBIC if array.ndim == 3 else Image.Resampling.NEAREST
    return np.array(Image.fromarray(array).resize((width, height), method))


def canvas_layers(paint, erase, mapping, shape):
    """Move the pending stroke layers into canvas space for live feedback."""
    scale, dx, dy = mapping
    result = []
    for array in (paint, erase):
        if array is None:
            result.append(None)
            continue
        layer = array
        if scale != 1:
            layer = scale_layer(layer, (shape[0], shape[1]))
        layer = shift_layer(layer, dx, dy)
        result.append(layer)
    return result[0], result[1]


def frame_chain(project, index, source_index):
    """base -> canvas mapping (scale, dx, dy) of one output frame's primary layer."""
    layout = project.layout
    value = FrameOverride()
    if project.timeline_edit.enabled:
        timing = project.final_timing[index] if index < len(project.final_timing) else None
        clip_id = timing["layers"][0] if timing and timing["layers"] else f"source:{source_index}"
        value = project.timeline_edit.frame_overrides.get(clip_id, FrameOverride())
    scale = value.scale
    dx = value.offset_x + (1 - scale) * layout.width / 2
    dy = value.offset_y + (1 - scale) * layout.height / 2
    if project.animation_transform.active:
        sx, sy = layout.normalize_scale
        if project.is_passthrough:
            dx += project.animation_transform.offset_x
            dy += project.animation_transform.offset_y
        else:
            dx += project.animation_transform.offset_x * sx
            dy += project.animation_transform.offset_y * sy
    cx, cy = project.frame_correction(index)
    return scale, dx + cx, dy + cy


def canvas_to_frame(mapping, x, y):
    scale, dx, dy = mapping
    scale = scale or 1.
    return ((x - dx) / scale, (y - dy) / scale)


def frame_to_canvas(mapping, x, y):
    scale, dx, dy = mapping
    return (x * scale + dx, y * scale + dy)


class RasterStroke:
    """One press -> moves -> release becomes one revision and one undo command."""

    def __init__(self, animation_id, frame_index, shape, paint=None, erase=None):
        self.animation_id = animation_id
        self.frame_index = int(frame_index)
        self.shape = (int(shape[0]), int(shape[1]))
        self.paint = empty_paint(shape) if paint is None else paint
        self.erase = empty_erase(shape) if erase is None else erase
        self.bounds = None
        self.points = 0

    def _touch(self, x, y, size):
        left, top = int(math.floor(x - size / 2)), int(math.floor(y - size / 2))
        right, bottom = int(math.ceil(x + size / 2)) + 1, int(math.ceil(y + size / 2)) + 1
        box = (max(0, left), max(0, top), min(self.shape[1], right), min(self.shape[0], bottom))
        if box[2] <= box[0] or box[3] <= box[1]:
            return
        self.bounds = box if self.bounds is None else (min(self.bounds[0], box[0]), min(self.bounds[1], box[1]),
                                                       max(self.bounds[2], box[2]), max(self.bounds[3], box[3]))

    def dot(self, x, y, tool, size, color=None):
        x, y = int(round(x)), int(round(y))
        if tool == "eraser":
            stamp_eraser(self.paint, self.erase, x, y, size)
        else:
            stamp_pencil(self.paint, x, y, size, color or (255, 255, 255, 255))
        self._touch(x, y, size)
        self.points += 1

    def segment(self, x0, y0, x1, y1, tool, size, color=None):
        for x, y in stroke_points(x0, y0, x1, y1, size):
            self.dot(x, y, tool, size, color)

    @property
    def changed(self):
        return self.bounds is not None


def revision_paths(directory, animation_id, frame_index, revision):
    directory = Path(directory) / str(animation_id)
    stem = f"frame_{int(frame_index):06d}.r{int(revision):04d}"
    return directory / f"{stem}.paint.png", directory / f"{stem}.erase.png"


def write_revision(directory, animation_id, frame_index, revision, paint, erase):
    paint_path, erase_path = revision_paths(directory, animation_id, frame_index, revision)
    save_layer(paint_path, paint)
    save_layer(erase_path, erase)
    return paint_path, erase_path


def prune_revisions(directory, keep):
    "Drop superseded revisions that no history entry references any more."
    directory = Path(directory)
    if not directory.is_dir():
        return 0
    keep = {str(Path(path).resolve()) for path in keep if path}
    removed = 0
    for path in directory.rglob("frame_*.png"):
        if str(path.resolve()) in keep:
            continue
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def referenced_layers(*states):
    "Every layer path mentioned by the given project snapshots; used to prune safely."
    result = set()
    for state in states:
        rows = (state or {}).get("pixel_edits") if isinstance(state, dict) else getattr(state, "pixel_edits", None)
        for frames in (rows or {}).values():
            for row in (frames or {}).values():
                data = row if isinstance(row, dict) else row.__dict__
                result.update(path for path in (data.get("paint_layer"), data.get("erase_mask")) if path)
    return result
