from dataclasses import replace
import numpy as np
from PIL import Image
import pytest

from app.core.alpha_utils import alpha_bbox
from app.core.sprite_canvas import calculate_layout, render_cell
from app.core.sprite_sheet import build_sheet, sheet_dimensions
from app.models.frame_data import FrameData
from app.models.project import ALIGNMENT_MODES, SpriteSettings


def subject(x=20, y=10, width=20, height=40):
    image = np.zeros((100, 100, 4), np.uint8)
    image[y:y+height, x:x+width] = (230, 40, 40, 255)
    return image


def test_alpha_bbox_noise_and_empty():
    image = subject()
    image[99, 99] = (255, 0, 0, 255)
    assert alpha_bbox(image) == (20, 10, 40, 50)
    assert alpha_bbox(np.zeros_like(image)) is None
    image[10:50, 20:40, 3] = 16
    assert alpha_bbox(image, threshold=16) is None


@pytest.mark.parametrize("mode", ALIGNMENT_MODES)
def test_alignment_rules(mode):
    frames = [FrameData(0, (20, 10, 40, 50), (30, 30)), FrameData(1, (35, 15, 55, 65), (45, 35))]
    layout = calculate_layout(frames, mode, 100, SpriteSettings(padding=8, bottom_margin=8))
    if mode == "ROOT XY LOCK":
        assert frames[0].cell_root == frames[1].cell_root
        assert frames[0].cell_bbox[3] != frames[1].cell_bbox[3]
    elif mode == "GROUND LOCK":
        assert frames[0].cell_root[0] != frames[1].cell_root[0]
    else:
        assert frames[0].cell_root[0] == frames[1].cell_root[0]
    if mode != "ROOT XY LOCK":
        assert all(f.cell_bbox[3] - 1 == layout.ground_baseline for f in frames)
    assert not layout.clipped_frames


def test_union_padding_rounding_and_clipping():
    frames = [FrameData(0, (10, 10, 30, 40), (20, 25)), FrameData(1, (0, 0, 90, 80), (20, 25))]
    base = SpriteSettings(padding=0, bottom_margin=0)
    tight = calculate_layout(frames, "ROOT XY LOCK", 100, base)
    padded = calculate_layout(frames, "ROOT XY LOCK", 100, replace(base, padding=16))
    assert tight.width == 90 and tight.height == 80
    assert padded.width == tight.width + 32 and padded.height == tight.height + 32
    rounded = calculate_layout(frames, "ROOT XY LOCK", 100, replace(base, round_up=64))
    assert (rounded.width, rounded.height) == (128, 128)
    fixed = calculate_layout(frames, "ROOT XY LOCK", 100, replace(base, mode="CUSTOM", width=32, height=32))
    assert 1 in fixed.clipped_frames and "Clipping" in frames[1].warnings


@pytest.mark.parametrize("scale", [0.5, 1, 1.75, 4])
def test_ground_raster_and_uniform_scale(scale):
    settings = SpriteSettings(padding=8, bottom_margin=8)
    frames = [FrameData(0, (20, 10, 40, 50), (30.2, 30.5)), FrameData(1, (35, 20, 55, 60), (45.2, 40.5))]
    layout = calculate_layout(frames, ALIGNMENT_MODES[2], 100, settings, scale)
    sizes = []
    for frame, image in zip(frames, [subject(), subject(35, 20)]):
        output = render_cell(image, frame, layout, scale, ALIGNMENT_MODES[2], 16, 12)
        bbox = alpha_bbox(output, 16, 1)
        assert bbox[3] - 1 == layout.ground_baseline
        sizes.append((bbox[2] - bbox[0], bbox[3] - bbox[1]))
    assert sizes[0] == sizes[1]
    assert not layout.clipped_frames


def test_sheet_cells_and_transparency(tmp_path):
    paths = []
    for i in range(5):
        path = tmp_path / f"{i}.png"
        Image.new("RGBA", (7, 9), (i * 40, 20, 50, 255)).save(path)
        paths.append(path)
    path = build_sheet(paths, tmp_path / "sheet.png", 7, 9, 3)
    with Image.open(path) as sheet:
        assert sheet.mode == "RGBA" and sheet.size == (21, 18)
        assert sheet.getpixel((8, 10)) == (160, 20, 50, 255)
        assert sheet.getpixel((15, 10))[3] == 0
    assert sheet_dimensions(5, 3, 7, 9) == (21, 18, 2)
