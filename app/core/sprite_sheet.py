"""Sprite packing with a disk-backed raw raster and streaming PNG encoder."""
from __future__ import annotations

import math
from pathlib import Path
import struct
import tempfile
import zlib

import numpy as np
from PIL import Image

from app.utils.ffmpeg import check_cancel


def sheet_dimensions(frame_count: int, columns: int, cell_width: int, cell_height: int) -> tuple[int, int, int]:
    if frame_count < 1 or columns < 1 or cell_width < 1 or cell_height < 1:
        raise ValueError("A sprite sheet needs frames, positive columns and cell dimensions")
    rows = math.ceil(frame_count / columns)
    return columns * cell_width, rows * cell_height, rows


def _chunk(file, kind: bytes, data: bytes) -> None:
    file.write(struct.pack(">I", len(data)))
    file.write(kind)
    file.write(data)
    file.write(struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))


def build_sheet(paths: list[Path], output: Path, cell_width: int, cell_height: int, columns: int,
                progress=lambda n, total, message: None, cancel=None) -> Path:
    width, height, _ = sheet_dimensions(len(paths), columns, cell_width, cell_height)
    if width >= 2**31 or height >= 2**31 or width * 4 > 64 * 1024 * 1024:
        raise ValueError("Sheet dimensions exceed PNG or scanline memory limits")
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_png = output.with_suffix(".tmp")
    # One frame + one scanline in memory. Sparse file holes represent transparent cells.
    try:
        with tempfile.TemporaryFile(dir=output.parent) as raster:
            raster.truncate(width * height * 4)
            for i, path in enumerate(paths):
                check_cancel(cancel)
                with Image.open(path) as source:
                    if source.size != (cell_width, cell_height):
                        raise ValueError(f"Mismatched cell dimensions: {path.name}")
                    pixels = np.array(source.convert("RGBA"))
                x, y = (i % columns) * cell_width, (i // columns) * cell_height
                for line in range(cell_height):
                    raster.seek(((y + line) * width + x) * 4)
                    raster.write(pixels[line].tobytes())
                progress(i + 1, len(paths), "Packing sprite cells")
            raster.seek(0)
            with temp_png.open("wb") as file:
                file.write(b"\x89PNG\r\n\x1a\n")
                _chunk(file, b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
                encoder = zlib.compressobj(6)
                for y in range(height):
                    check_cancel(cancel)
                    data = encoder.compress(b"\x00" + raster.read(width * 4))
                    if data:
                        _chunk(file, b"IDAT", data)
                    if y % 32 == 0:
                        progress(y, height, "Encoding transparent PNG")
                _chunk(file, b"IDAT", encoder.flush())
                _chunk(file, b"IEND", b"")
        check_cancel(cancel)
        temp_png.replace(output)
    finally:
        temp_png.unlink(missing_ok=True)
    return output


def sheet_preview(paths: list[Path], cell_width: int, cell_height: int, columns: int, max_side: int = 2048,
                  cancel=None) -> tuple[np.ndarray, float]:
    width, height, _ = sheet_dimensions(len(paths), columns, cell_width, cell_height)
    scale = min(1.0, max_side / max(width, height))
    preview = Image.new("RGBA", (max(1, round(width * scale)), max(1, round(height * scale))))
    for i, path in enumerate(paths):
        check_cancel(cancel)
        x0, y0 = round(i % columns * cell_width * scale), round(i // columns * cell_height * scale)
        x1, y1 = round((i % columns + 1) * cell_width * scale), round((i // columns + 1) * cell_height * scale)
        if x1 <= x0 or y1 <= y0:
            continue
        with Image.open(path) as cell:
            thumb = cell.convert("RGBA").resize((x1 - x0, y1 - y0), Image.Resampling.LANCZOS)
            preview.paste(thumb, (x0, y0))
    return np.array(preview), scale
