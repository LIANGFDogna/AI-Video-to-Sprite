"""Phase 2F B-E: Pencil / Eraser raster edits, Frame Reference, derived sequences and trails."""
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt, QMimeData
from PySide6.QtGui import (QDrag, QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent, QDropEvent, QImage,
                           QMouseEvent, QPainter)
from PySide6.QtWidgets import QApplication, QWidget

from app.core.final_frame_provider import FinalFrameProvider
from app.core.pipeline import Pipeline
from app.models.character_reference import CharacterReference
from app.models.character_templates import PLAYER
from app.models.project import Project
from app.ui.editor_timeline import FRAME_MIME
from app.ui.project_library import MIME
from app.utils.paths import cache_directory
from test_group_workspace_ui import cached_clip, window
from test_workspace_ui import close_window, events, qt


def editor_window(qt, tmp_path, name='Run', count=6):
    w = window(qt, tmp_path)
    c = w.library_controller
    group = c.new_group(name='Run')
    animation_id = cached_clip(w, group.id, name, count=count)
    c.select_group(group.id)
    w.steps.setCurrentIndex(2)
    events(qt, lambda: not w.worker)
    c.select_group(group.id)
    events(qt, lambda: w.editor.provider is not None and not w.editor.worker)
    w.editor.select(0)
    events(qt, lambda: not w.editor.worker and not w.editor.pending)
    return w, c, group, animation_id


def character_window(qt, tmp_path):
    "Player with an Idle Character Reference plus a Run animation for painting."
    w = window(qt, tmp_path)
    c = w.library_controller
    player = c.new_character(template_id=PLAYER, name='Player')
    roots = {group.name: group for group in w.project.library.character_roots(player.id)}
    idle_animation = cached_clip(w, roots['Idle'].id, 'Idle Frames', count=4)
    movement = roots['Movement']
    run_group = next(group for group in w.project.library.children(movement.id) if group.name == 'Run')
    run_animation = cached_clip(w, run_group.id, 'Run Frames', count=6)
    c.select_animation(idle_animation)
    w._save_character_reference(CharacterReference(idle_animation, 0, 16, 28, 32, 32))
    c.select_animation(run_animation)
    w.steps.setCurrentIndex(2)
    events(qt, lambda: not w.worker)
    c.select_animation(run_animation)
    events(qt, lambda: w.editor.provider is not None and not w.editor.worker)
    w.editor.select(0)
    events(qt, lambda: not w.editor.worker and not w.editor.pending)
    return w, c, player, run_group, run_animation


def paint(w, points, tool='pencil', size=4, color=(255, 0, 0, 255)):
    "One press - moves - release through the editor's real stroke API."
    w.editor.set_tool(tool)
    w.editor.brush_size.setValue(size)
    w.editor.brush_color = color
    w.editor.begin_stroke(*points[0])
    for point in points[1:]:
        w.editor.stroke_point(*point)
    w.editor.finish_stroke()


def final_pixels(w, index=0, project=None):
    provider = FinalFrameProvider(project or w.project, w.cache_dir, live_edit=True)
    return provider.get_final_frame(index)


def source_pixels(w, animation_id, index):
    "Final pixels of another Animation of the same project, from its own cache."
    project = w.project.select_animation(animation_id)
    directory = cache_directory(w.project.project_id, w.project_file, animation_id)
    return FinalFrameProvider(project, directory, live_edit=True).get_final_frame(index)


def render_viewport(widget):
    "Paint the widget (a viewport) into an image; QGraphicsView itself has no such overload."
    target = widget.viewport() if hasattr(widget, 'viewport') else widget
    image = QImage(target.size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    target.render(painter, QPoint(0, 0))
    painter.end()
    rows = np.frombuffer(image.constBits(), np.uint8).reshape(image.height(), image.bytesPerLine() // 4, 4)
    return rows[:, :image.width()].copy()


def mouse(widget, kind, point, button, buttons):
    return QMouseEvent(kind, QPointF(point), QPointF(point), button, buttons, Qt.KeyboardModifier.NoModifier)


def drag_canvas(canvas, delta):
    centre = QPointF(canvas.viewport().rect().center())
    canvas.mousePressEvent(mouse(canvas, QEvent.Type.MouseButtonPress, centre, Qt.MouseButton.LeftButton,
                                 Qt.MouseButton.LeftButton))
    canvas.mouseMoveEvent(mouse(canvas, QEvent.Type.MouseMove, centre + QPointF(delta[0], delta[1]),
                                Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton))
    canvas.mouseReleaseEvent(mouse(canvas, QEvent.Type.MouseButtonRelease, centre + QPointF(delta[0], delta[1]),
                                   Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton))


def frame_payload(animation_id, frames, label='4 Frames'):
    "Keep the QMimeData alive: QDropEvent only stores a pointer to it."
    data = QMimeData()
    data.setData(FRAME_MIME, json.dumps({'animation_id': animation_id, 'frames': list(frames), 'label': label}).encode())
    return data


def derived_row(w, group_id):
    rows = [row for row in w.project.library.in_group(group_id, kinds={'ANIMATION'})]
    return rows[0] if rows else None


def test_pencil_draw_current_frame(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        before = final_pixels(w).copy()
        source_folder = Path(w.project.sequence_folder)
        source_before = sorted((path.name, path.stat().st_size) for path in source_folder.iterdir())
        paint(w, [(10, 10)], size=4, color=(255, 0, 0, 255))
        row = w.project.raster_edit(animation_id, 0)
        assert row is not None and row.frame_index == 0 and row.revision == 1
        after = final_pixels(w)
        assert tuple(after[10, 10]) == (255, 0, 0, 255), after[10, 10]
        assert np.array_equal(after[0:6, 0:6], before[0:6, 0:6])
        assert sorted((path.name, path.stat().st_size) for path in source_folder.iterdir()) == source_before
        assert w.last_error is None
    finally:
        close_window(qt, w)


def test_pencil_rgba(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        paint(w, [(25, 25)], size=4, color=(0, 0, 255, 128))
        after = final_pixels(w)
        assert tuple(after[25, 25]) == (0, 0, 255, 128), after[25, 25]
        stored = Image.open(w.project.raster_edit(animation_id, 0).paint_layer)
        assert stored.mode == 'RGBA' and stored.getpixel((25, 25)) == (0, 0, 255, 128)
    finally:
        close_window(qt, w)


def test_eraser_current_frame(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        before = final_pixels(w).copy()
        assert before[10, 10][3] > 0
        paint(w, [(10, 10)], tool='eraser', size=8)
        after = final_pixels(w)
        assert after[10, 10][3] == 0, after[10, 10]
        assert before[0, 0][3] == after[0, 0][3]
        row = w.project.raster_edit(animation_id, 0)
        assert row is not None and Image.open(row.erase_mask).mode == 'L'
    finally:
        close_window(qt, w)


def test_eraser_makes_transparent(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        paint(w, [(10, 10)], tool='eraser', size=6)
        after = final_pixels(w)
        assert np.all(after[8:13, 8:13, 3] == 0), after[8:13, 8:13, 3]
        assert after[25, 25][3] == 0 and after[2, 2][3] == 0
    finally:
        close_window(qt, w)


def test_pencil_after_erase_restores_pixel(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        paint(w, [(10, 10)], tool='eraser', size=6)
        assert final_pixels(w)[10, 10][3] == 0
        paint(w, [(10, 10)], size=4, color=(0, 255, 0, 255))
        after = final_pixels(w)
        assert tuple(after[10, 10]) == (0, 255, 0, 255), after[10, 10]
        assert w.project.raster_edit(animation_id, 0).revision == 2
    finally:
        close_window(qt, w)


def test_pencil_does_not_modify_character_ghost(qt, tmp_path):
    w, c, player, run_group, animation_id = character_window(qt, tmp_path)
    try:
        ghost = w.editor.canvas.ghost_pixels
        assert ghost is not None and ghost.size
        digest = hashlib.sha256(np.ascontiguousarray(ghost).tobytes()).hexdigest()
        paint(w, [(10, 10)], size=4, color=(255, 255, 0, 255))
        events(qt, lambda: not w.editor.worker and not w.editor.pending)
        assert w.last_error is None
        assert hashlib.sha256(np.ascontiguousarray(w.editor.canvas.ghost_pixels).tobytes()).hexdigest() == digest
        assert w.project.library.characters[player.id].character_reference is not None
    finally:
        close_window(qt, w)


def test_eraser_does_not_modify_character_ghost(qt, tmp_path):
    w, c, player, run_group, animation_id = character_window(qt, tmp_path)
    try:
        ghost = w.editor.canvas.ghost_pixels
        assert ghost is not None and ghost.size
        digest = hashlib.sha256(np.ascontiguousarray(ghost).tobytes()).hexdigest()
        paint(w, [(10, 10)], tool='eraser', size=8)
        events(qt, lambda: not w.editor.worker and not w.editor.pending)
        assert hashlib.sha256(np.ascontiguousarray(w.editor.canvas.ghost_pixels).tobytes()).hexdigest() == digest
        assert w.editor.canvas.idle_ghost_item.isVisible()
    finally:
        close_window(qt, w)


def test_pencil_does_not_modify_frame_reference(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        w.editor.set_frame_reference_for(2)
        events(qt, lambda: not w.editor.worker and not w.editor.pending)
        reference = w.editor.canvas.reference_pixels
        assert reference is not None and reference.size
        digest = hashlib.sha256(np.ascontiguousarray(reference).tobytes()).hexdigest()
        paint(w, [(10, 10)], size=4, color=(255, 255, 0, 255))
        events(qt, lambda: not w.editor.worker and not w.editor.pending)
        assert hashlib.sha256(np.ascontiguousarray(w.editor.canvas.reference_pixels).tobytes()).hexdigest() == digest
        assert w.editor.canvas.frame_reference_item.isVisible()
        assert w.editor.frame_reference_state()['frame_index'] == 2
    finally:
        close_window(qt, w)


def test_eraser_does_not_modify_frame_reference(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        w.editor.set_frame_reference_for(2)
        events(qt, lambda: not w.editor.worker and not w.editor.pending)
        reference = w.editor.canvas.reference_pixels.copy()
        paint(w, [(10, 10)], tool='eraser', size=8)
        events(qt, lambda: not w.editor.worker and not w.editor.pending)
        assert np.array_equal(w.editor.canvas.reference_pixels, reference)
        assert w.editor.frame_reference_state() == {'animation_id': animation_id, 'frame_index': 2}
    finally:
        close_window(qt, w)


def test_one_pencil_stroke_one_undo(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        c.entries = []
        c.index = 0
        before = final_pixels(w).copy()
        entries = len(w._history().entries)
        paint(w, [(8, 8), (10, 10), (12, 12), (14, 14), (16, 16)], size=4, color=(255, 0, 0, 255))
        assert len(w._history().entries) == entries + 1
        assert not np.array_equal(final_pixels(w), before)
        w.undo_edit()
        assert np.array_equal(final_pixels(w), before)
        assert w.project.raster_edit(animation_id, 0) is None
        w.redo_edit()
        assert tuple(final_pixels(w)[16, 16]) == (255, 0, 0, 255)
    finally:
        close_window(qt, w)


def test_one_eraser_stroke_one_undo(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        c.entries = []
        c.index = 0
        before = final_pixels(w).copy()
        entries = len(w._history().entries)
        paint(w, [(6, 12), (10, 12), (14, 12), (18, 12)], tool='eraser', size=6)
        assert len(w._history().entries) == entries + 1
        assert final_pixels(w)[12, 10][3] == 0
        w.undo_edit()
        assert np.array_equal(final_pixels(w), before)
        w.redo_edit()
        assert final_pixels(w)[12, 10][3] == 0
    finally:
        close_window(qt, w)


def test_raster_edit_save_reopen(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        paint(w, [(10, 10)], size=6, color=(12, 34, 56, 200))
        expected = final_pixels(w).copy()
        target = w.project_file
        w.project.save(target)
        data = json.loads(target.read_text(encoding='utf-8'))
        stored = data['pixel_edits'][animation_id]['0']
        assert not Path(stored['paint_layer']).is_absolute() and not Path(stored['erase_mask']).is_absolute()
        reopened = Project.load(target)
        row = reopened.raster_edit(animation_id, 0)
        assert row is not None and row.revision == 1
        assert tuple(row.paint_layer) and Path(row.paint_layer).is_absolute()
        assert np.array_equal(final_pixels(w, project=reopened), expected)
        assert reopened.has_final_edits
    finally:
        close_window(qt, w)


def test_raster_edit_exported(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        paint(w, [(10, 10)], size=6, color=(255, 0, 255, 255))
        expected = final_pixels(w).copy()
        Pipeline(w.project, w.cache_dir).build()
        with Image.open(w.cache_dir / 'sprite_sheet.png') as sheet:
            pixels = np.array(sheet.convert('RGBA'))
        cell = w.project.layout
        assert tuple(pixels[10, 10]) == (255, 0, 255, 255), pixels[10, 10]
        assert np.array_equal(pixels[:cell.height, :cell.width], expected)
    finally:
        close_window(qt, w)


def test_canvas_drag_item_count_stable(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        w.resize(1200, 820)
        events(qt, lambda: True)
        canvas = w.editor.canvas
        before = len(canvas.scene().items())
        for step in range(100):
            drag_canvas(canvas, (2 if step % 2 == 0 else -2, 0))
        events(qt, lambda: not w.editor.worker and not w.editor.pending)
        assert len(canvas.scene().items()) == before
        assert canvas.pixmap_item.pos().isNull()
    finally:
        close_window(qt, w)


def test_canvas_drag_100_visual_no_trail(qt, tmp_path):
    "100 drags must leave exactly the pixels a fresh editor shows at the same coordinates."
    w, c, group, animation_id = editor_window(qt, tmp_path)
    fresh_folder = tmp_path / 'fresh-editor'
    fresh_folder.mkdir()
    try:
        w.resize(1200, 820)
        events(qt, lambda: True)
        canvas = w.editor.canvas
        for step in range(100):
            drag_canvas(canvas, (60 if step % 2 == 0 else -60, 0))
        drag_canvas(canvas, (60, 0))
        events(qt, lambda: not w.editor.worker and not w.editor.pending)
        final = w.project.frame_correction(0)
        assert final != (0, 0), final
        dragged = render_viewport(canvas)
        w2 = window(qt, fresh_folder)
        try:
            w2.project = copy.deepcopy(w.project)
            w2.project_file = w.project_file
            w2.cache_dir = w.cache_dir
            w2.built = True
            # Same final coordinates, reached without any dragging.
            w2.project.clear_frame_corrections()
            w2.project.set_frame_correction(0, *final)
            w2.resize(1200, 820)
            w2._loaded()
            w2.steps.setCurrentIndex(2)
            events(qt, lambda: not w2.worker)
            w2.library_controller.select_group(group.id)
            events(qt, lambda: w2.editor.provider is not None and not w2.editor.worker)
            w2.editor.select(0)
            events(qt, lambda: not w2.editor.worker and not w2.editor.pending)
            fresh = render_viewport(w2.editor.canvas)
        finally:
            close_window(qt, w2)
        assert dragged.shape == fresh.shape
        difference = int(np.abs(dragged.astype(int) - fresh.astype(int)).max())
        assert np.array_equal(dragged, fresh), difference
    finally:
        close_window(qt, w)


def test_timeline_drag_visual_no_snapshot(qt, tmp_path, monkeypatch):
    "Frame drags show a light text label; the Timeline is never grabbed into a pixmap."
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        timeline = w.editor.timeline
        grabbed = []
        pixmaps = []
        monkeypatch.setattr(QWidget, 'grab', lambda self, *args, **kwargs: grabbed.append(self))
        monkeypatch.setattr(QDrag, 'setPixmap', lambda self, pixmap: pixmaps.append(pixmap))
        monkeypatch.setattr(QDrag, 'exec', lambda self, *args, **kwargs: Qt.DropAction.IgnoreAction)
        timeline.select_ids([frame.id for frame in timeline.edit.frames()][:4])
        assert timeline._begin_frame_drag()
        assert not grabbed
        assert pixmaps and pixmaps[0].height() <= 32 and pixmaps[0].width() < 160
        assert len([frame.id for frame in timeline.edit.frames()][:4]) == 4
    finally:
        close_window(qt, w)


def test_interaction_cancel_after_paint(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        w.editor.set_tool('pencil')
        w.editor.begin_stroke(10, 10)
        w.editor.stroke_point(12, 12)
        assert w.editor.stroke is not None
        w.editor.cancel_active_interaction()
        assert w.editor.stroke is None
        assert w.project.raster_edit(animation_id, 0) is None
        assert w.editor.canvas.pixmap_item.pos().isNull()
    finally:
        close_window(qt, w)


def test_interaction_cancel_after_tree_drag(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        other = c.new_group(name='AttackPrep')
        tree = w.library_panel.tree
        item = w.library_panel.items[('GROUP', other.id)]
        tree.scrollToItem(item)
        events(qt, lambda: True)
        position = QPointF(tree.visualItemRect(item).center())
        data = QMimeData()
        data.setData(MIME, json.dumps(['GROUP', group.id]).encode())
        tree.dragEnterEvent(QDragEnterEvent(position.toPoint(), Qt.DropAction.MoveAction, data,
                                            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        tree.dragMoveEvent(QDragMoveEvent(position.toPoint(), Qt.DropAction.MoveAction, data,
                                          Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        assert tree.drop_zone is not None
        tree.dragLeaveEvent(QDragLeaveEvent())
        assert tree.drop_zone is None and tree.frame_drop_target is None
        assert w.project.library.groups[other.id].parent_id is None
        assert w.project.library.groups[group.id].parent_id is None
    finally:
        close_window(qt, w)


def test_interaction_cancel_after_frame_drag(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        timeline = w.editor.timeline
        ids = [frame.id for frame in timeline.edit.frames()][:2]
        timeline.select_ids(ids)
        timeline.drag = (QPointF(0, 0), 0., timeline.edit.track_layout[0].id, True)
        for ident in ids:
            timeline.items_by_id[ident].setPos(40, 0)
        timeline.cancel_active_interaction()
        assert all(item.pos().isNull() for item in timeline.items_by_id.values())
        assert derived_row(w, group.id) is not None and len(w.project.library.in_group(group.id, kinds={'ANIMATION'})) == 1
    finally:
        close_window(qt, w)


def test_multi_frame_drag_to_group(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        target = c.new_group(name='AttackPrep')
        tree = w.library_panel.tree
        item = w.library_panel.items[('GROUP', target.id)]
        tree.scrollToItem(item)
        events(qt, lambda: True)
        payload = frame_payload(animation_id, [1, 2, 3, 5])
        drop = QDropEvent(QPointF(tree.visualItemRect(item).center()), Qt.DropAction.CopyAction, payload,
                          Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        tree.dropEvent(drop)
        assert drop.isAccepted()
        events(qt, lambda: derived_row(w, target.id) is not None)
        row = derived_row(w, target.id)
        assert row is not None
        assert row.metadata['source_animation_id'] == animation_id
        assert row.metadata['source_frame_indices'] == [1, 2, 3, 5]
        derived = w.project.select_animation(row.animation_id)
        assert derived.video.frame_count == 4
        assert w.last_error is None
    finally:
        close_window(qt, w)


def test_multi_frame_order_preserved(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        target = c.new_group(name='AttackPrep')
        assert c.drop_frames_to_group(animation_id, [3, 1, 2], target.id) is not None
        row = derived_row(w, target.id)
        derived = w.project.select_animation(row.animation_id)
        folder = Path(derived.sequence_folder)
        written = [np.array(Image.open(path).convert('RGBA')) for path in sorted(folder.glob('*.png'))]
        for position, index in enumerate([3, 1, 2]):
            assert np.array_equal(written[position], source_pixels(w, animation_id, index)), position
        assert row.metadata['source_frame_indices'] == [3, 1, 2]
    finally:
        close_window(qt, w)


def test_multi_frame_drag_does_not_remove_source_frames(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        before = final_pixels(w).copy()
        target = c.new_group(name='AttackPrep')
        assert c.drop_frames_to_group(animation_id, [1, 2, 3, 5], target.id) is not None
        assert w.project.library.animation(animation_id) is not None
        assert w.project.select_animation(animation_id).video.frame_count == 6
        assert np.array_equal(source_pixels(w, animation_id, 0), before)
    finally:
        close_window(qt, w)


def test_derived_sequence_uses_final_frame_provider(qt, tmp_path):
    "Corrections and raster edits must be part of the snapshot."
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        w.add_frame_correction([2], 3, -2)
        w.editor.select(2)
        events(qt, lambda: not w.editor.worker and not w.editor.pending)
        paint(w, [(10, 10)], size=6, color=(255, 128, 0, 255))
        events(qt, lambda: not w.editor.worker and not w.editor.pending)
        expected = final_pixels(w, 2).copy()
        target = c.new_group(name='AttackPrep')
        assert c.drop_frames_to_group(animation_id, [2], target.id) is not None
        row = derived_row(w, target.id)
        derived = w.project.select_animation(row.animation_id)
        written = np.array(Image.open(sorted(Path(derived.sequence_folder).glob('*.png'))[0]).convert('RGBA'))
        assert np.array_equal(written, expected)
        assert written[10, 10][0] == 255
    finally:
        close_window(qt, w)


def test_derived_sequence_is_snapshot(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        target = c.new_group(name='AttackPrep')
        assert c.drop_frames_to_group(animation_id, [1, 2], target.id) is not None
        row = derived_row(w, target.id)
        derived = w.project.select_animation(row.animation_id)
        folder = Path(derived.sequence_folder)
        before = [np.array(Image.open(path).convert('RGBA')) for path in sorted(folder.glob('*.png'))]
        w.project.set_frame_correction(1, 5, 5)
        w.project.set_frame_correction(2, -4, 0)
        after = [np.array(Image.open(path).convert('RGBA')) for path in sorted(folder.glob('*.png'))]
        for position in range(2):
            assert np.array_equal(before[position], after[position]), position
        assert row.metadata['created_at']
    finally:
        close_window(qt, w)


def test_derived_sequence_no_rekey(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        target = c.new_group(name='AttackPrep')
        assert c.drop_frames_to_group(animation_id, [1, 2], target.id) is not None
        row = derived_row(w, target.id)
        derived = w.project.select_animation(row.animation_id)
        assert derived.input_mode == 'frame_sequence' and derived.is_passthrough
        assert derived.processing_mode == 'full'
        raw = np.array(Image.open(sorted(Path(derived.sequence_folder).glob('*.png'))[0]).convert('RGBA'))
        assert raw[..., 3].min() == 0 and raw[..., 3].max() == 180
    finally:
        close_window(qt, w)


def test_derived_sequence_undo(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        target = c.new_group(name='AttackPrep')
        assert c.drop_frames_to_group(animation_id, [1, 2, 3], target.id) is not None
        row = derived_row(w, target.id)
        assert row is not None
        assert c.entries[-1][-1] == 'Derived Frame Sequence' and c.index == len(c.entries)
        w.undo_edit()
        assert derived_row(w, target.id) is None
        assert w.project.library.animation(row.animation_id) is None
        assert w.last_error is None
    finally:
        close_window(qt, w)


def test_frame_context_menu_set_reference(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        timeline = w.editor.timeline
        seen = []
        timeline.frame_menu_requested.connect(lambda index, position: seen.append(index))
        first = timeline.edit.frames()[0]
        point = QPoint(round(timeline.label_width + (first.start + first.duration / 2) * timeline.pixels_per_second),
                       timeline.ruler_height + 10)
        timeline._context_menu(point)
        assert seen == [first.source_index]
        w.editor.set_frame_reference_for(seen[0])
        assert w.editor.frame_reference_state() == {'animation_id': animation_id, 'frame_index': first.source_index}
        assert timeline.reference_index == first.source_index
        w.editor.clear_frame_reference()
        assert w.editor.frame_reference_state() is None and timeline.reference_index is None
    finally:
        close_window(qt, w)


def test_frame_reference_toggle(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        w.editor.set_frame_reference_for(2)
        events(qt, lambda: not w.editor.worker and not w.editor.pending)
        assert w.editor.canvas.frame_reference_item.isVisible()
        w.editor.show_frame_reference.setChecked(False)
        events(qt, lambda: not w.editor.worker and not w.editor.pending)
        assert not w.editor.canvas.frame_reference_item.isVisible()
        w.editor.show_frame_reference.setChecked(True)
        events(qt, lambda: not w.editor.worker and not w.editor.pending)
        assert w.editor.canvas.frame_reference_item.isVisible()
    finally:
        close_window(qt, w)


def test_frame_reference_opacity(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        assert abs(w.editor.frame_reference_opacity.value() - .15) < 1e-9
        w.editor.set_frame_reference_for(2)
        w.editor.frame_reference_opacity.setValue(.5)
        events(qt, lambda: not w.editor.worker and not w.editor.pending)
        assert abs(w.editor.canvas.frame_reference_item.opacity() - .5) < 1e-9
        from app.models.project_library import WorkspaceState
        with pytest.raises(ValueError):
            WorkspaceState.from_dict({'frame_reference': {'animation_id': animation_id, 'frame_index': 2},
                                      'frame_reference_opacity': .9})
    finally:
        close_window(qt, w)


def test_frame_reference_save_reopen(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        w.editor.set_frame_reference_for(3)
        w.editor.frame_reference_opacity.setValue(.4)
        w.editor.show_frame_reference.setChecked(False)
        events(qt, lambda: not w.editor.worker and not w.editor.pending)
        c.capture()
        target = w.project_file
        w.project.save(target)
        reopened = Project.load(target)
        state = reopened.library.groups[group.id].animation_states[animation_id]
        assert state.frame_reference == {'animation_id': animation_id, 'frame_index': 3}
        assert abs(state.frame_reference_opacity - .4) < 1e-9
        assert state.frame_reference_visible is False
    finally:
        close_window(qt, w)


def test_frame_reference_not_exported(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        w.editor.set_frame_reference_for(2)
        events(qt, lambda: not w.editor.worker and not w.editor.pending)
        expected = final_pixels(w).copy()
        Pipeline(w.project, w.cache_dir).build()
        with Image.open(w.cache_dir / 'sprite_sheet.png') as sheet:
            pixels = np.array(sheet.convert('RGBA'))
        cell = w.project.layout
        assert np.array_equal(pixels[:cell.height, :cell.width], expected)
        assert w.editor.canvas.frame_reference_item.isVisible()
        assert w.editor.canvas.frame_reference_item.zValue() < w.editor.canvas.pixmap_item.zValue()
    finally:
        close_window(qt, w)


def test_character_ghost_and_frame_reference_coexist(qt, tmp_path):
    w, c, player, run_group, animation_id = character_window(qt, tmp_path)
    try:
        w.editor.set_frame_reference_for(2)
        w.editor.reference_opacity.setValue(.5)
        w.editor.frame_reference_opacity.setValue(.3)
        events(qt, lambda: not w.editor.worker and not w.editor.pending)
        canvas = w.editor.canvas
        assert canvas.ghost_pixels is not None and canvas.reference_pixels is not None
        assert canvas.idle_ghost_item.isVisible() and canvas.frame_reference_item.isVisible()
        assert abs(canvas.idle_ghost_item.opacity() - .5) < 1e-9
        assert abs(canvas.frame_reference_item.opacity() - .3) < 1e-9
        order = [canvas.idle_ghost_item.zValue(), canvas.frame_reference_item.zValue(), canvas.pixmap_item.zValue()]
        assert order == sorted(order) and order[0] < order[1] < order[2]
    finally:
        close_window(qt, w)
