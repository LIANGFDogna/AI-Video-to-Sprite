"""Phase 2F.1 A: moving canonical frames between Animations and Groups."""
import numpy as np
import pytest
from PIL import Image

from app.core.final_frame_provider import FinalFrameProvider
from app.utils.paths import cache_directory, frame_path
from test_group_workspace_ui import cached_clip, window
from test_workspace_ui import close_window, events, qt


def move_window(qt, tmp_path, name='JumpUp', count=12):
    w = window(qt, tmp_path)
    c = w.library_controller
    group = c.new_group(name=name)
    animation_id = cached_clip(w, group.id, name, count=count)
    c.select_group(group.id)
    w.steps.setCurrentIndex(2)
    events(qt, lambda: not w.worker)
    c.select_group(group.id)
    events(qt, lambda: w.editor.provider is not None and not w.editor.worker)
    return w, c, group, animation_id


def canonical_pixels(w, animation_id, index):
    directory = cache_directory(w.project.project_id, w.project_file, animation_id)
    return np.array(Image.open(frame_path(directory / 'aligned_frames', index)).convert('RGBA'))


def animation_of(w, group_id):
    rows = w.project.library.in_group(group_id, kinds={'ANIMATION'})
    return rows[0].animation_id if rows else None


def render(w, animation_id, index):
    project = w.project.select_animation(animation_id)
    directory = cache_directory(w.project.project_id, w.project_file, animation_id)
    return FinalFrameProvider(project, directory, live_edit=True).get_final_frame(index)


def paint(w, points, size=6, color=(255, 0, 0, 255)):
    w.editor.set_tool('pencil')
    w.editor.brush_size.setValue(size)
    w.editor.brush_color = color
    w.editor.begin_stroke(*points[0])
    for point in points[1:]:
        w.editor.stroke_point(*point)
    w.editor.finish_stroke()


def test_move_selected_frames_removes_from_source(qt, tmp_path):
    w, c, group, animation_id = move_window(qt, tmp_path)
    try:
        target = c.new_group(name='JumpLoop')
        assert c.move_selected_frames(animation_id, [1, 2, 3, 4], target.id) is not None
        reduced = animation_of(w, group.id)
        assert reduced is not None and reduced != animation_id
        assert w.project.select_animation(reduced).video.frame_count == 8
        assert w.project.select_animation(animation_of(w, target.id)).video.frame_count == 4
        assert w.last_error is None
    finally:
        close_window(qt, w)


def test_move_selected_frames_target_only_selected(qt, tmp_path):
    "The target must never inherit the whole source Animation."
    w, c, group, animation_id = move_window(qt, tmp_path, count=41)
    try:
        target = c.new_group(name='JumpLoop')
        assert c.move_selected_frames(animation_id, [1, 2, 3, 4], target.id) is not None
        assert w.project.select_animation(animation_of(w, group.id)).video.frame_count == 37
        assert w.project.select_animation(animation_of(w, target.id)).video.frame_count == 4
        source_row = w.project.library.animation(animation_of(w, group.id))
        assert source_row.metadata.get('moved_frames_out') == 4
        target_row = w.project.library.animation(animation_of(w, target.id))
        assert target_row.metadata['source_frame_indices'] == [1, 2, 3, 4]
    finally:
        close_window(qt, w)


def test_move_selected_frames_preserves_order(qt, tmp_path):
    w, c, group, animation_id = move_window(qt, tmp_path)
    try:
        target = c.new_group(name='JumpLoop')
        before = {index: canonical_pixels(w, animation_id, index) for index in (5, 2, 7)}
        assert c.move_selected_frames(animation_id, [5, 2, 7], target.id) is not None
        moved = animation_of(w, target.id)
        for position, index in enumerate([5, 2, 7]):
            assert np.array_equal(canonical_pixels(w, moved, position), before[index]), position
    finally:
        close_window(qt, w)


def test_move_selected_frames_preserves_canonical_pixels(qt, tmp_path):
    "Canonical pixels and alpha bounds must be byte-identical after the move."
    w, c, group, animation_id = move_window(qt, tmp_path)
    try:
        target = c.new_group(name='JumpLoop')
        before = canonical_pixels(w, animation_id, 1).copy()
        assert c.move_selected_frames(animation_id, [1, 2, 3, 4], target.id) is not None
        after = canonical_pixels(w, animation_of(w, target.id), 0)
        assert after.shape == before.shape
        assert np.array_equal(after, before)
        assert np.array_equal(after[..., 3] > 0, before[..., 3] > 0)
    finally:
        close_window(qt, w)


def test_move_selected_frames_does_not_delete_disk_source(qt, tmp_path):
    w, c, group, animation_id = move_window(qt, tmp_path, count=6)
    try:
        original = w.project.select_animation(animation_id)
        folder = __import__('pathlib').Path(original.sequence_folder)
        before = sorted(path.name for path in folder.iterdir())
        assert len(before) == 6
        target = c.new_group(name='JumpLoop')
        assert c.move_selected_frames(animation_id, [2, 3], target.id) is not None
        assert sorted(path.name for path in folder.iterdir()) == before
        assert len(before) == 6
        reduced = w.project.library.animation(w.project.library.in_group(group.id, kinds={'ANIMATION'})[0].animation_id)
        repacked = __import__('pathlib').Path(w.project.library.resources[reduced.source_id].path)
        assert repacked != folder and len(sorted(path.name for path in repacked.iterdir())) == 4
    finally:
        close_window(qt, w)


def test_move_selected_frames_no_final_provider_bake(qt, tmp_path):
    "Corrections, raster edits and the Animation Transform must not be baked into the move."
    w, c, group, animation_id = move_window(qt, tmp_path)
    try:
        target = c.new_group(name='JumpLoop')
        canonical_before = canonical_pixels(w, animation_id, 2).copy()
        rendered_before = render(w, animation_id, 2).copy()
        c.select_group(group.id)
        w.add_frame_correction([2], 3, -2)
        w.editor.select(2)
        events(qt, lambda: not w.editor.worker and not w.editor.pending)
        paint(w, [(10, 10)], size=8, color=(255, 0, 0, 255))
        events(qt, lambda: not w.editor.worker and not w.editor.pending)
        edited = render(w, animation_id, 2).copy()
        assert not np.array_equal(edited, rendered_before)
        assert c.move_selected_frames(animation_id, [1, 2, 3, 4], target.id) is not None
        moved = animation_of(w, target.id)
        assert np.array_equal(canonical_pixels(w, moved, 1), canonical_before)
        assert w.project.select_animation(moved).animation_transform.offset_x == 0
        assert w.project.select_animation(moved).animation_transform.offset_y == 0
        assert np.array_equal(render(w, moved, 1), edited)
    finally:
        close_window(qt, w)


def test_move_selected_frames_no_second_normalize(qt, tmp_path):
    "A moved canonical frame is copied, never fitted to another canvas again."
    w, c, group, animation_id = move_window(qt, tmp_path)
    try:
        target = c.new_group(name='JumpLoop')
        source_canvas = w.project.select_animation(animation_id).video
        before = canonical_pixels(w, animation_id, 3).copy()
        assert c.move_selected_frames(animation_id, [3], target.id) is not None
        moved_project = w.project.select_animation(animation_of(w, target.id))
        after = canonical_pixels(w, animation_of(w, target.id), 0)
        assert (moved_project.video.width, moved_project.video.height) == (before.shape[1], before.shape[0])
        assert np.array_equal(after, before)
        assert (before.shape[1], before.shape[0]) == (source_canvas.width, source_canvas.height)
        def bounds(image):
            columns = np.where(image[..., 3] > 0)[1]
            return int(columns.min()), int(columns.max())
        assert bounds(after) == bounds(before)
    finally:
        close_window(qt, w)


def test_move_selected_frames_moves_frame_correction(qt, tmp_path):
    w, c, group, animation_id = move_window(qt, tmp_path)
    try:
        target = c.new_group(name='JumpLoop')
        c.select_group(group.id)
        w.add_frame_correction([2], 4, -3)
        assert c.move_selected_frames(animation_id, [1, 2, 3, 4], target.id) is not None
        moved = animation_of(w, target.id)
        assert w.project.select_animation(moved).frame_correction(1) == (4, -3)
        reduced = animation_of(w, group.id)
        assert w.project.select_animation(reduced).frame_corrections == {}
    finally:
        close_window(qt, w)


def test_move_selected_frames_moves_raster_edit(qt, tmp_path):
    w, c, group, animation_id = move_window(qt, tmp_path)
    try:
        target = c.new_group(name='JumpLoop')
        c.select_group(group.id)
        w.editor.select(2)
        events(qt, lambda: not w.editor.worker and not w.editor.pending)
        paint(w, [(10, 10), (14, 10)], size=8, color=(0, 255, 0, 255))
        events(qt, lambda: not w.editor.worker and not w.editor.pending)
        rendered = render(w, animation_id, 2).copy()
        assert c.move_selected_frames(animation_id, [1, 2, 3, 4], target.id) is not None
        moved = animation_of(w, target.id)
        row = w.project.select_animation(moved).raster_edit(moved, 1)
        assert row is not None and row.revision == 1
        assert np.array_equal(render(w, moved, 1), rendered)
    finally:
        close_window(qt, w)


def test_move_selected_frames_undo(qt, tmp_path):
    w, c, group, animation_id = move_window(qt, tmp_path)
    try:
        target = c.new_group(name='JumpLoop')
        before = {index: canonical_pixels(w, animation_id, index) for index in (1, 2, 3, 4)}
        assert c.move_selected_frames(animation_id, [1, 2, 3, 4], target.id) is not None
        assert c.entries[-1][0] == 'frames'
        w.undo_edit()
        assert w.project.library.animation(animation_id) is not None
        assert w.project.select_animation(animation_id).video.frame_count == 12
        assert w.project.library.in_group(target.id, kinds={'ANIMATION'}) == []
        for index in (1, 2, 3, 4):
            assert np.array_equal(canonical_pixels(w, animation_id, index), before[index])
    finally:
        close_window(qt, w)


def test_move_selected_frames_redo(qt, tmp_path):
    w, c, group, animation_id = move_window(qt, tmp_path)
    try:
        target = c.new_group(name='JumpLoop')
        assert c.move_selected_frames(animation_id, [1, 2, 3, 4], target.id) is not None
        w.undo_edit()
        w.redo_edit()
        reduced = animation_of(w, group.id)
        moved = animation_of(w, target.id)
        assert w.project.select_animation(reduced).video.frame_count == 8
        assert w.project.select_animation(moved).video.frame_count == 4
        assert w.last_error is None
    finally:
        close_window(qt, w)


def test_drop_refreshes_tree_immediately(qt, tmp_path):
    w, c, group, animation_id = move_window(qt, tmp_path)
    try:
        target = c.new_group(name='JumpLoop')
        assert c.move_selected_frames(animation_id, [1, 2, 3, 4], target.id) is not None
        counts = {name: len(w.project.library.in_group(ident, kinds={'ANIMATION'}))
                  for name, ident in (('source', group.id), ('target', target.id))}
        assert counts == {'source': 1, 'target': 1}
        assert w.library_panel.items[('GROUP', target.id)].text(1) == '1'
        assert w.library_panel.items[('GROUP', group.id)].text(1) == '1'
        frames = {name: w.project.select_animation(animation_of(w, ident)).video.frame_count
                  for name, ident in (('source', group.id), ('target', target.id))}
        assert frames == {'source': 8, 'target': 4}
    finally:
        close_window(qt, w)


def test_drop_refreshes_timeline_immediately(qt, tmp_path):
    w, c, group, animation_id = move_window(qt, tmp_path)
    try:
        target = c.new_group(name='JumpLoop')
        c.select_group(group.id)
        assert c.move_selected_frames(animation_id, [1, 2, 3, 4], target.id) is not None
        assert w.project.animation_id == animation_of(w, group.id)
        assert len(w.editor.timeline.items_by_id) == 8
        rows = w.project.library.in_group(target.id, kinds={'ANIMATION'})
        c.select_animation(rows[0].animation_id)
        events(qt, lambda: not w.worker)
        assert len(w.editor.timeline.items_by_id) == 4
    finally:
        close_window(qt, w)


def test_drop_marks_sheet_stale(qt, tmp_path):
    w, c, group, animation_id = move_window(qt, tmp_path)
    try:
        assert w.project.library.animation(animation_id).ready
        target = c.new_group(name='JumpLoop')
        assert c.move_selected_frames(animation_id, [1, 2, 3, 4], target.id) is not None
        reduced = w.project.library.animation(animation_of(w, group.id))
        moved = w.project.library.animation(animation_of(w, target.id))
        assert not reduced.ready and not moved.ready
        assert all(not sheet.ready for sheet in w.project.library.generated_sheets(reduced.animation_id))
        assert w.project.library.groups[group.id].status != 'READY'
    finally:
        close_window(qt, w)
