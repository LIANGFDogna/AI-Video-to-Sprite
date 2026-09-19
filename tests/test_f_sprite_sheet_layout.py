"""Slicer layout: Auto Layout reactivity, frame count and out-of-bounds protection."""
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.core.project_workspace import create_project_workspace
from app.core.sprite_sheet_slice import SliceConfig, calculate_cells
from app.i18n import t
from app.ui.main_window import MainWindow
from app.ui.sprite_sheet_slicer_dialog import SpriteSheetSlicerDialog
from app.utils.paths import cache_directory, frame_path
from test_workspace_ui import close_window, events, qt

REAL_SIZE = (1772, 887)


def real_sheet_pixels(empty_cells=(), size=REAL_SIZE):
    width, height = size
    pixels = np.zeros((height, width, 4), np.uint8)
    cell_w, cell_h = width // 4, height // 2
    for index in range(8):
        if index in empty_cells:
            continue
        row, column = divmod(index, 4)
        color = (30 + index * 20, 200 - index * 10, 60 + index * 15, 140 + index * 9)
        offset_x, offset_y = 15 + (index % 3) * 7, 25 + (index // 3) * 11
        pixels[row * (cell_h + 1) + offset_y:row * (cell_h + 1) + offset_y + 60,
               column * cell_w + offset_x:column * cell_w + offset_x + 40] = color
    return pixels


def sheet_window(qt, tmp_path, pixels, name='SkillSlash'):
    w = MainWindow(tmp_path / 'ui.log')
    w._failed = lambda error: setattr(w, 'last_error', error)
    w.project, w.project_file = create_project_workspace(tmp_path, '中文项目', 'standard')
    w._loaded()
    w.show()
    c = w.library_controller
    group = c.new_group(name='Skill')
    path = tmp_path / f'{name}.png'
    Image.fromarray(pixels).save(path)
    c.select_group(group.id)
    resource = c.import_sheet(str(path))
    assert resource is not None
    return w, c, group, resource, path


def dialog_for(w, pixels, config=None):
    return SpriteSheetSlicerDialog(w, 'SkillSlash.png', pixels, config=config or SliceConfig(columns=4, rows=1))


def animation_of(w, group_id):
    rows = w.project.library.in_group(group_id, kinds={'ANIMATION'})
    return rows[0].animation_id if rows else None


def sliced_file(w, animation_id, index):
    project = w.project.select_animation(animation_id)
    return np.array(Image.open(frame_path(Path(project.sequence_folder), index)).convert('RGBA'))


def test_rows_change_recalculates_cell_height(qt, tmp_path):
    w, c, group, resource, path = sheet_window(qt, tmp_path, real_sheet_pixels())
    dialog = dialog_for(w, real_sheet_pixels())
    try:
        assert dialog.auto_layout.isChecked()
        assert dialog.cell_height.value() == 887
        dialog.rows.setValue(2)
        assert dialog.cell_height.value() == 443, dialog.cell_height.value()
        assert dialog.cell_width.value() == 443
        assert dialog.result_layout.frame_count == 8
    finally:
        dialog.reject()
        close_window(qt, w)


def test_columns_change_recalculates_cell_width(qt, tmp_path):
    w, c, group, resource, path = sheet_window(qt, tmp_path, real_sheet_pixels())
    dialog = dialog_for(w, real_sheet_pixels(), SliceConfig(columns=4, rows=2))
    try:
        assert dialog.cell_width.value() == 443
        dialog.columns.setValue(2)
        assert dialog.cell_width.value() == 886, dialog.cell_width.value()
        assert dialog.cell_height.value() == 443
        assert dialog.result_layout.frame_count == 4
    finally:
        dialog.reject()
        close_window(qt, w)


def test_grid_preview_and_frame_count_match(qt, tmp_path):
    "Every frame the preview numbers must exist in the summary and in the layout."
    w, c, group, resource, path = sheet_window(qt, tmp_path, real_sheet_pixels())
    dialog = dialog_for(w, real_sheet_pixels(), SliceConfig(columns=4, rows=2))
    try:
        layout = dialog.result_layout
        numbered = [cell.frame_index for cell in layout.cells
                    if cell.valid and cell.frame_index is not None]
        assert numbered == list(range(8))
        assert layout.frame_count == 8
        expected = t('{frames} frames · Cell {width}×{height} · {fps:g} FPS · {duration:.2f}s',
                     frames=8, width=443, height=443, fps=12, duration=8 / 12)
        assert expected in dialog.summary.text(), dialog.summary.text()
    finally:
        dialog.reject()
        close_window(qt, w)


def test_create_animation_uses_same_cell_layout(qt, tmp_path):
    pixels = real_sheet_pixels()
    w, c, group, resource, path = sheet_window(qt, tmp_path, pixels)
    dialog = dialog_for(w, pixels, SliceConfig(columns=4, rows=2))
    try:
        dialog.accept()
        config = dialog.result_config
        layout = dialog.result_layout
        assert config is not None and layout.frame_count == 8
        assert c.slice_sprite_sheet(resource.id, config) is not None
        animation_id = animation_of(w, group.id)
        assert w.project.select_animation(animation_id).video.frame_count == 8
        for index, cell in enumerate(layout.frames):
            expected = pixels[cell.y:cell.y + cell.height, cell.x:cell.x + cell.width]
            assert np.array_equal(sliced_file(w, animation_id, index), expected), index
    finally:
        close_window(qt, w)


def test_non_divisible_dimension_reports_remainder(qt, tmp_path):
    pixels = np.zeros((1000, 1000, 4), np.uint8)
    pixels[20:200, 20:200] = (10, 20, 30, 255)
    w, c, group, resource, path = sheet_window(qt, tmp_path, pixels)
    dialog = dialog_for(w, pixels, SliceConfig(columns=3, rows=3))
    try:
        layout = dialog.result_layout
        assert layout.config.cell_width == 333 and layout.config.cell_height == 333
        assert layout.remainder == (1, 1), layout.remainder
        assert layout.unused
        assert t('Unused edge: {width} × {height} px', width=1, height=1) in dialog.summary.text()
        assert layout.frame_count == 9
    finally:
        dialog.reject()
        close_window(qt, w)


def test_invalid_cells_not_counted_as_normal(qt, tmp_path):
    pixels = real_sheet_pixels()
    w, c, group, resource, path = sheet_window(qt, tmp_path, pixels)
    config = SliceConfig(columns=4, rows=2, cell_width=443, cell_height=887, auto_layout=False)
    dialog = dialog_for(w, pixels, config)
    try:
        layout = dialog.result_layout
        assert layout.invalid == [4, 5, 6, 7]
        assert layout.frame_count == 4
        assert not dialog.create_button.isEnabled()
        assert t('Cells outside the sheet: {count}', count=4) in dialog.summary.text()
        assert c.slice_sprite_sheet(resource.id, config) is None
        assert t('Cells outside the sheet: {count}', count=4) in w.status.text()
    finally:
        dialog.reject()
        close_window(qt, w)


def test_auto_layout_4x2_real_sheet(qt, tmp_path):
    "The reported case: 1772×887, 4 columns, 2 rows must become 8 frames of 443×443."
    pixels = real_sheet_pixels()
    w, c, group, resource, path = sheet_window(qt, tmp_path, pixels)
    dialog = dialog_for(w, pixels, SliceConfig(columns=4, rows=1))
    try:
        layout = dialog.result_layout
        assert (layout.config.cell_width, layout.config.cell_height) == (443, 887)
        assert layout.frame_count == 4
        dialog.rows.setValue(2)
        layout = dialog.result_layout
        assert (layout.config.cell_width, layout.config.cell_height) == (443, 443)
        assert layout.frame_count == 8
        assert layout.config.spacing_y == 1
        assert layout.remainder == (0, 0)
        dialog.accept()
        assert dialog.result_config is not None
        assert c.slice_sprite_sheet(resource.id, dialog.result_config) is not None
        animation_id = animation_of(w, group.id)
        assert w.project.select_animation(animation_id).video.frame_count == 8
        assert len(w.project.select_animation(animation_id).timeline_edit.timeline_clips) == 8
        for index in range(8):
            row, column = divmod(index, 4)
            expected = pixels[row * 444:row * 444 + 443, column * 443:column * 443 + 443]
            assert np.array_equal(sliced_file(w, animation_id, index), expected), index
    finally:
        close_window(qt, w)


def test_manual_layout_does_not_auto_override(qt, tmp_path):
    pixels = real_sheet_pixels()
    w, c, group, resource, path = sheet_window(qt, tmp_path, pixels)
    config = SliceConfig(columns=4, rows=2, cell_width=443, cell_height=887, auto_layout=False)
    dialog = dialog_for(w, pixels, config)
    try:
        dialog.rows.setValue(2)
        assert dialog.cell_height.value() == 887
        assert dialog.result_layout.config.cell_height == 887
        assert dialog.result_layout.frame_count == 4
        assert dialog.result_layout.invalid == [4, 5, 6, 7]
        dialog.cell_height.setValue(443)
        assert dialog.result_layout.frame_count == 8
        assert dialog.result_layout.config.cell_height == 443
        assert not dialog.result_layout.invalid
    finally:
        dialog.reject()
        close_window(qt, w)


def test_auto_manual_toggle(qt, tmp_path):
    pixels = real_sheet_pixels()
    w, c, group, resource, path = sheet_window(qt, tmp_path, pixels)
    dialog = dialog_for(w, pixels, SliceConfig(columns=4, rows=1))
    try:
        assert dialog.cell_height.isReadOnly()
        dialog.auto_layout.setChecked(False)
        assert not dialog.cell_height.isReadOnly()
        dialog.cell_height.setValue(300)
        assert dialog.result_layout.config.cell_height == 300
        dialog.auto_layout.setChecked(True)
        assert dialog.cell_height.isReadOnly()
        assert dialog.result_layout.config.cell_height == 887
        dialog.rows.setValue(2)
        assert dialog.result_layout.config.cell_height == 443
    finally:
        dialog.reject()
        close_window(qt, w)


def test_summary_updates_immediately(qt, tmp_path):
    pixels = real_sheet_pixels()
    w, c, group, resource, path = sheet_window(qt, tmp_path, pixels)
    dialog = dialog_for(w, pixels, SliceConfig(columns=4, rows=1))
    try:
        def summary(frames, width, height):
            return t('{frames} frames · Cell {width}×{height} · {fps:g} FPS · {duration:.2f}s',
                     frames=frames, width=width, height=height, fps=12, duration=frames / 12)
        assert summary(4, 443, 887) in dialog.summary.text()
        dialog.rows.setValue(2)
        assert summary(8, 443, 443) in dialog.summary.text(), dialog.summary.text()
        dialog.columns.setValue(2)
        assert summary(4, 886, 443) in dialog.summary.text(), dialog.summary.text()
    finally:
        dialog.reject()
        close_window(qt, w)
