"""Sprite Sheet Slicer: fixed-cell slicing into an editable animation."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.core.final_frame_provider import FinalFrameProvider
from app.core.project_workspace import create_project_workspace
from app.core.sprite_sheet_slice import SliceConfig, detect_grid, slice_frames
from app.models.project import Project
from app.ui.main_window import MainWindow
from app.utils.paths import cache_directory, frame_path
from test_workspace_ui import close_window, events, qt

SHEET = 512
COLUMNS, ROWS = 4, 2
CELL_W, CELL_H = SHEET // COLUMNS, SHEET // ROWS


def sheet_pixels(empty_cells=(), columns=COLUMNS, rows=ROWS, size=SHEET):
    cell_w, cell_h = size // columns, size // rows
    pixels = np.zeros((size, size, 4), np.uint8)
    for row in range(rows):
        for column in range(columns):
            index = row * columns + column
            if index in empty_cells:
                continue
            color = (30 + index * 20, 200 - index * 10, 60 + index * 15, 128 + index * 8)
            offset_x, offset_y = 10 + (index % 3) * 6, 20 + (index // 3) * 10
            pixels[row * cell_h + offset_y:row * cell_h + offset_y + 40,
                   column * cell_w + offset_x:column * cell_w + offset_x + 30] = color
    return pixels


def sheet_window(qt, tmp_path, pixels=None, name='SkillSlash', canvas=None):
    "canvas='none' clears the project canvas so the cells stay at their own resolution."
    w = MainWindow(tmp_path / 'ui.log')
    w._failed = lambda error: setattr(w, 'last_error', error)
    w.project, w.project_file = create_project_workspace(tmp_path, '中文项目', 'standard')
    if canvas == 'none':
        w.project.canvas_fit_mode = 'none'
        w.project.project_canvas_width = w.project.project_canvas_height = 0
    w._loaded()
    w.show()
    c = w.library_controller
    group = c.new_group(name='Skill')
    pixels = sheet_pixels() if pixels is None else pixels
    path = tmp_path / f'{name}.png'
    Image.fromarray(pixels).save(path)
    c.select_group(group.id)
    resource = c.import_sheet(str(path))
    assert resource is not None
    return w, c, group, resource, path, pixels


def slice_sheet(c, resource, ignore_empty=False, fps=12., **overrides):
    config = SliceConfig(columns=COLUMNS, rows=ROWS, cell_width=CELL_W, cell_height=CELL_H,
                         fps=fps, loop=True, ignore_empty=ignore_empty, **overrides)
    return c.slice_sprite_sheet(resource.id, config)


def animation_of(w, group_id):
    rows = w.project.library.in_group(group_id, kinds={'ANIMATION'})
    return rows[0].animation_id if rows else None


def canonical(w, animation_id, index):
    directory = cache_directory(w.project.project_id, w.project_file, animation_id)
    return np.array(Image.open(frame_path(directory / 'aligned_frames', index)).convert('RGBA'))


def cell_of(pixels, index):
    "The exact fixed Cell Rect of frame index in the source sheet."
    row, column = divmod(index, COLUMNS)
    return pixels[row * CELL_H:(row + 1) * CELL_H, column * CELL_W:(column + 1) * CELL_W]


def sliced_file(w, animation_id, index):
    project = w.project.select_animation(animation_id)
    return np.array(Image.open(frame_path(Path(project.sequence_folder), index)).convert('RGBA'))


def placed_cell(w, cell):
    "The project canvas rule: source resolution, centered, never alpha based."
    project = w.project
    canvas = project.project_canvas
    if canvas is None:
        return cell
    width, height = canvas
    result = np.zeros((height, width, 4), np.uint8)
    left, top = (width - cell.shape[1]) // 2, (height - cell.shape[0]) // 2
    result[top:top + cell.shape[0], left:left + cell.shape[1]] = cell
    return result


def rendered(w, animation_id, index):
    project = w.project.select_animation(animation_id)
    directory = cache_directory(w.project.project_id, w.project_file, animation_id)
    return FinalFrameProvider(project, directory, live_edit=True).get_final_frame(index)


def editor_window(qt, tmp_path, ignore_empty=False):
    w, c, group, resource, path, pixels = sheet_window(qt, tmp_path)
    assert slice_sheet(c, resource, ignore_empty=ignore_empty) is not None
    w.steps.setCurrentIndex(2)
    events(qt, lambda: not w.worker)
    events(qt, lambda: w.editor.provider is not None and not w.editor.worker)
    return w, c, group, resource, path, pixels


def test_sprite_sheet_slice_4x2(qt, tmp_path):
    w, c, group, resource, path, pixels = sheet_window(qt, tmp_path)
    try:
        assert slice_sheet(c, resource) is not None
        animation_id = animation_of(w, group.id)
        assert w.project.select_animation(animation_id).video.frame_count == 8
        assert sliced_file(w, animation_id, 0).shape[:2] == (CELL_H, CELL_W)
        assert canonical(w, animation_id, 0).shape[:2] == (SHEET, SHEET)
        assert w.last_error is None
    finally:
        close_window(qt, w)


def test_sprite_sheet_frame_count_8(qt, tmp_path):
    w, c, group, resource, path, pixels = sheet_window(qt, tmp_path)
    try:
        assert slice_sheet(c, resource) is not None
        assert len(list(Path(w.project.sequence_folder).glob('*.png'))) == 8
        assert w.project.select_animation(animation_of(w, group.id)).video.frame_count == 8
    finally:
        close_window(qt, w)


def test_sprite_sheet_row_major_order(qt, tmp_path):
    w, c, group, resource, path, pixels = sheet_window(qt, tmp_path)
    try:
        assert slice_sheet(c, resource) is not None
        animation_id = animation_of(w, group.id)
        for index in range(8):
            assert np.array_equal(sliced_file(w, animation_id, index), cell_of(pixels, index)), index
            assert np.array_equal(canonical(w, animation_id, index), placed_cell(w, cell_of(pixels, index))), index
    finally:
        close_window(qt, w)


def test_sprite_sheet_fixed_cell_size(qt, tmp_path):
    w, c, group, resource, path, pixels = sheet_window(qt, tmp_path)
    try:
        assert slice_sheet(c, resource) is not None
        animation_id = animation_of(w, group.id)
        sizes = {sliced_file(w, animation_id, index).shape[:2] for index in range(8)}
        assert sizes == {(CELL_H, CELL_W)}
        assert all(sliced_file(w, animation_id, index).shape[:2] == (CELL_H, CELL_W) for index in range(8))
    finally:
        close_window(qt, w)


def test_sprite_sheet_preserves_alpha(qt, tmp_path):
    w, c, group, resource, path, pixels = sheet_window(qt, tmp_path)
    try:
        assert slice_sheet(c, resource) is not None
        animation_id = animation_of(w, group.id)
        frame = sliced_file(w, animation_id, 3)
        source = cell_of(pixels, 3)
        assert np.array_equal(frame, source)
        assert frame[..., 3].max() == 128 + 3 * 8
        assert frame[..., 3].min() == 0
        assert np.array_equal(canonical(w, animation_id, 3), placed_cell(w, source))
    finally:
        close_window(qt, w)


def test_sprite_sheet_no_alpha_trim(qt, tmp_path):
    "Content stays at its cell-relative position; nothing is re-centered."
    w, c, group, resource, path, pixels = sheet_window(qt, tmp_path)
    try:
        assert slice_sheet(c, resource) is not None
        animation_id = animation_of(w, group.id)
        for index in (0, 4, 7):
            source = cell_of(pixels, index)
            assert np.array_equal(sliced_file(w, animation_id, index), source), index
            placed = canonical(w, animation_id, index)
            rows = np.where(placed[..., 3] > 0)[0]
            expected = placed_cell(w, source)
            assert np.array_equal(placed, expected), index
            assert rows.min() == np.where(expected[..., 3] > 0)[0].min()
    finally:
        close_window(qt, w)


def test_sprite_sheet_does_not_modify_original(qt, tmp_path):
    w, c, group, resource, path, pixels = sheet_window(qt, tmp_path)
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert slice_sheet(c, resource) is not None
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
        assert w.project.library.resources[resource.id].path == str(path)
        assert np.array_equal(np.array(Image.open(path).convert('RGBA')), pixels)
    finally:
        close_window(qt, w)


def test_sprite_sheet_no_second_normalize(qt, tmp_path):
    "The canonical frame is the cell itself: no fit, no resample, no keying."
    w, c, group, resource, path, pixels = sheet_window(qt, tmp_path)
    try:
        assert slice_sheet(c, resource) is not None
        animation_id = animation_of(w, group.id)
        project = w.project.select_animation(animation_id)
        assert project.is_passthrough and project.processing_mode == 'full'
        assert (project.video.width, project.video.height) == (SHEET, SHEET)
        # One fit only: the cell is centered at scale 1 and keeps its pixels byte for byte.
        assert np.array_equal(canonical(w, animation_id, 5), placed_cell(w, cell_of(pixels, 5)))
    finally:
        close_window(qt, w)


def test_sprite_sheet_create_sequence(qt, tmp_path):
    w, c, group, resource, path, pixels = sheet_window(qt, tmp_path)
    try:
        assert slice_sheet(c, resource) is not None
        rows = w.project.library.in_group(group.id)
        sequences = [row for row in rows if row.kind == 'SOURCE_SEQUENCE']
        assert len(sequences) == 1
        assert sequences[0].name.endswith('_Source')
        assert len(list(Path(sequences[0].path).glob('*.png'))) == 8
        assert w.project.library.resources[resource.id].kind == 'SOURCE_SPRITE_SHEET'
    finally:
        close_window(qt, w)


def test_sprite_sheet_create_animation(qt, tmp_path):
    w, c, group, resource, path, pixels = sheet_window(qt, tmp_path)
    try:
        animation_row = slice_sheet(c, resource)
        assert animation_row is not None
        row = w.project.library.resources[animation_row]
        assert row.kind == 'ANIMATION' and row.metadata['slice_source'] == resource.id
        sheet_row = w.project.library.resources[resource.id]
        assert sheet_row.metadata['sliced_animation'] == row.animation_id
        assert sheet_row.metadata['slice_config']['columns'] == COLUMNS
        assert not row.ready
    finally:
        close_window(qt, w)


def test_sprite_sheet_fps(qt, tmp_path):
    w, c, group, resource, path, pixels = sheet_window(qt, tmp_path)
    try:
        assert slice_sheet(c, resource, fps=12.) is not None
        project = w.project.select_animation(animation_of(w, group.id))
        assert abs(project.video.fps - 12.) < 1e-9
        assert project.timeline_edit.enabled and len(project.timeline_edit.timeline_clips) == 8
        clip = project.timeline_edit.timeline_clips[0]
        assert abs(clip.duration - 1 / 12.) < 1e-9
        assert project.export_settings.loop is True
    finally:
        close_window(qt, w)


def test_sprite_sheet_playback(qt, tmp_path):
    w, c, group, resource, path, pixels = editor_window(qt, tmp_path)
    try:
        animation_id = animation_of(w, group.id)
        provider = FinalFrameProvider(w.project, w.cache_dir, live_edit=True)
        assert len(provider) == 8
        first = provider.get_final_frame(0).copy()
        w.editor.select(3)
        events(qt, lambda: not w.editor.worker and not w.editor.pending)
        assert w.editor.index == 3
        assert not np.array_equal(rendered(w, animation_id, 3), first)
        w.editor.step(1)
        events(qt, lambda: not w.editor.worker and not w.editor.pending)
        assert w.editor.index == 4
    finally:
        close_window(qt, w)


def test_sprite_sheet_timeline_editable(qt, tmp_path):
    w, c, group, resource, path, pixels = editor_window(qt, tmp_path)
    try:
        assert len(w.editor.timeline.items_by_id) == 8
        ids = [frame.id for frame in w.editor.timeline.edit.frames()]
        w.editor.timeline.select_ids(ids[2:5])
        assert set(w.editor.timeline.ids()) == set(ids[2:5])
        w.editor.action('reverse')
        events(qt, lambda: not w.editor.worker)
        assert len(w.project.timeline_edit.timeline_clips) == 8
    finally:
        close_window(qt, w)


def test_sprite_sheet_pencil_editable(qt, tmp_path):
    w, c, group, resource, path, pixels = editor_window(qt, tmp_path)
    try:
        animation_id = animation_of(w, group.id)
        w.editor.select(3)
        events(qt, lambda: not w.editor.worker and not w.editor.pending)
        before = rendered(w, animation_id, 3).copy()
        rows = np.where(before[..., 3] > 0)[0]
        row = int(rows[len(rows) // 2])
        columns = np.where(before[row, :, 3] > 0)[0]
        column = int(columns[len(columns) // 2])
        w.editor.set_tool('pencil')
        w.editor.brush_size.setValue(8)
        w.editor.brush_color = (255, 0, 0, 255)
        w.editor.begin_stroke(column, row)
        w.editor.stroke_point(column + 6, row)
        w.editor.finish_stroke()
        events(qt, lambda: not w.editor.worker and not w.editor.pending)
        assert w.project.raster_edit(animation_id, 3) is not None
        assert tuple(rendered(w, animation_id, 3)[row, column]) == (255, 0, 0, 255)
        assert not np.array_equal(rendered(w, animation_id, 3), before)
    finally:
        close_window(qt, w)


def test_sprite_sheet_eraser_editable(qt, tmp_path):
    w, c, group, resource, path, pixels = editor_window(qt, tmp_path)
    try:
        animation_id = animation_of(w, group.id)
        w.editor.select(4)
        events(qt, lambda: not w.editor.worker and not w.editor.pending)
        target = rendered(w, animation_id, 4)
        rows = np.where(target[..., 3] > 0)[0]
        row = int(rows[len(rows) // 2])
        columns = np.where(target[row, :, 3] > 0)[0]
        column = int(columns[len(columns) // 2])
        w.editor.set_tool('eraser')
        w.editor.brush_size.setValue(10)
        w.editor.begin_stroke(column, row)
        w.editor.stroke_point(column, row)
        w.editor.finish_stroke()
        events(qt, lambda: not w.editor.worker and not w.editor.pending)
        assert rendered(w, animation_id, 4)[row, column][3] == 0
    finally:
        close_window(qt, w)


def test_sprite_sheet_frame_correction(qt, tmp_path):
    w, c, group, resource, path, pixels = editor_window(qt, tmp_path)
    try:
        animation_id = animation_of(w, group.id)
        w.editor.select(5)
        events(qt, lambda: not w.editor.worker and not w.editor.pending)
        before = rendered(w, animation_id, 5).copy()
        w.add_frame_correction([5], 6, -4)
        events(qt, lambda: not w.editor.worker and not w.editor.pending)
        after = rendered(w, animation_id, 5)
        assert w.project.select_animation(animation_id).frame_correction(5) == (6, -4)
        assert not np.array_equal(after, before)
    finally:
        close_window(qt, w)


def test_sprite_sheet_save_reopen(qt, tmp_path):
    w, c, group, resource, path, pixels = editor_window(qt, tmp_path)
    try:
        target = w.project_file
        w.project.save(target)
        data = json.loads(target.read_text(encoding='utf-8'))
        stored = data['library']['resources'][resource.id]['metadata']
        assert stored['slice_config']['rows'] == ROWS and stored['slice_config']['fps'] == 12.
        reopened = Project.load(target)
        rows = [row for row in reopened.library.resources.values() if row.kind == 'ANIMATION']
        assert len(rows) == 1
        animation = reopened.select_animation(rows[0].animation_id)
        assert animation.video.frame_count == 8
        assert abs(animation.video.fps - 12.) < 1e-9
        assert len(animation.timeline_edit.timeline_clips) == 8
        assert reopened.library.resources[resource.id].metadata['sliced_animation'] == rows[0].animation_id
    finally:
        close_window(qt, w)


def test_sprite_sheet_ui_refresh_immediate(qt, tmp_path):
    w, c, group, resource, path, pixels = sheet_window(qt, tmp_path)
    try:
        animation_row = slice_sheet(c, resource)
        assert animation_row is not None
        assert ('RESOURCE', animation_row) in w.library_panel.items
        assert w.project.animation_id == w.project.library.resources[animation_row].animation_id
        assert len(w.editor.timeline.items_by_id) == 8
        assert w.editor.provider is not None
        assert w.library_panel.items[('GROUP', group.id)].text(1) == '1'
    finally:
        close_window(qt, w)


def test_transparent_cells_preserved_by_default(qt, tmp_path):
    w, c, group, resource, path, pixels = sheet_window(qt, tmp_path, sheet_pixels(empty_cells=(2, 5)))
    try:
        assert slice_sheet(c, resource) is not None
        animation_id = animation_of(w, group.id)
        assert w.project.select_animation(animation_id).video.frame_count == 8
        assert trimmed_cell(w, animation_id, 2)[..., 3].max() == 0
        assert sliced_file(w, animation_id, 2)[..., 3].max() == 0
    finally:
        close_window(qt, w)


def test_ignore_empty_cells_optional(qt, tmp_path):
    w, c, group, resource, path, pixels = sheet_window(qt, tmp_path, sheet_pixels(empty_cells=(1, 6)))
    try:
        assert slice_sheet(c, resource, ignore_empty=True) is not None
        animation_id = animation_of(w, group.id)
        assert w.project.select_animation(animation_id).video.frame_count == 6
        row = w.project.library.resources[animation_row_id(w, group.id)]
        assert row.metadata['skipped_empty'] == [1, 6]
        assert row.metadata['slice_config']['ignore_empty'] is True
    finally:
        close_window(qt, w)


def trimmed_cell(w, animation_id, index):
    "The canonical frame cropped back to the cell size, for alpha checks."
    placed = canonical(w, animation_id, index)
    canvas = w.project.project_canvas or (placed.shape[1], placed.shape[0])
    left, top = (canvas[0] - CELL_W) // 2, (canvas[1] - CELL_H) // 2
    return placed[top:top + CELL_H, left:left + CELL_W]


def animation_row_id(w, group_id):
    return w.project.library.in_group(group_id, kinds={'ANIMATION'})[0].id


def test_sprite_sheet_no_second_normalize_without_project_canvas(qt, tmp_path):
    "With no project canvas the sliced cell is the canonical frame, byte for byte."
    w, c, group, resource, path, pixels = sheet_window(qt, tmp_path, canvas='none')
    try:
        assert slice_sheet(c, resource) is not None
        animation_id = animation_of(w, group.id)
        project = w.project.select_animation(animation_id)
        assert (project.video.width, project.video.height) == (CELL_W, CELL_H)
        for index in (0, 5, 7):
            assert np.array_equal(canonical(w, animation_id, index), cell_of(pixels, index)), index
    finally:
        close_window(qt, w)


def test_slice_config_and_detection_helpers():
    "Grid math and the optional separator detection, without any UI."
    pixels = sheet_pixels()
    config = SliceConfig(columns=4, rows=2, cell_width=CELL_W, cell_height=CELL_H)
    resolved, frames, skipped = slice_frames(pixels, config)
    assert (resolved.cell_width, resolved.cell_height) == (CELL_W, CELL_H)
    assert len(frames) == 8 and not skipped
    guessed = detect_grid(np.asarray(pixels))
    assert guessed is None or guessed.columns >= 1
    separated = np.zeros((64, 128, 4), np.uint8)
    separated[8:56, 4:60] = (10, 20, 30, 255)
    separated[8:56, 68:124] = (10, 20, 30, 255)
    guess = detect_grid(separated)
    assert guess is not None and guess.columns == 2
