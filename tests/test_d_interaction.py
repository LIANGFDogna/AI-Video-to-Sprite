"""Phase 2F.1 C/D: paint performance, internal drags, selection overlay and framebuffer checks."""
import copy
import time

import numpy as np
import pytest
from PIL import Image
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QDrag, QImage, QMouseEvent, QPainter
from PySide6.QtWidgets import QWidget

from app.core.final_frame_provider import FinalFrameProvider
from app.ui.frame_editor import FrameEditor
from test_b_pixel_tools import editor_window, paint, render_viewport
from test_group_workspace_ui import window
from test_workspace_ui import close_window, events, qt


def stroke_points(w, points, tool='pencil', size=6, color=(255, 0, 0, 255)):
    w.editor.set_tool(tool)
    w.editor.brush_size.setValue(size)
    w.editor.brush_color = color
    w.editor.begin_stroke(*points[0])
    for point in points[1:]:
        w.editor.stroke_point(*point)
    return w.editor


def prepare_tree(w):
    "Same expansion and scroll for both trees; only the drag history differs."
    tree = w.library_panel.tree
    tree.expandAll()
    tree.verticalScrollBar().setValue(0)
    tree.horizontalScrollBar().setValue(0)


def grabbed(widget):
    "Real framebuffer of a shown widget, not a scene render."
    pixmap = widget.grab()
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    rows = np.frombuffer(image.constBits(), np.uint8).reshape(image.height(), image.bytesPerLine() // 4, 4)
    return rows[:, :image.width()].copy()


def test_pencil_mousemove_no_disk_io(qt, tmp_path, monkeypatch):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        import app.core.pixel_edit as pixel_edit
        written = []
        monkeypatch.setattr(pixel_edit, 'save_layer', lambda *args, **kwargs: written.append(args[0]))
        stroke_points(w, [(4, 5)] + [(x, 5) for x in range(6, 30)])
        assert written == []
        assert w.project.raster_edit(animation_id, 0) is None
        w.editor.finish_stroke()
        assert len(written) == 2, written
    finally:
        close_window(qt, w)


def test_eraser_mousemove_no_disk_io(qt, tmp_path, monkeypatch):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        import app.core.pixel_edit as pixel_edit
        written = []
        monkeypatch.setattr(pixel_edit, 'save_layer', lambda *args, **kwargs: written.append(args[0]))
        stroke_points(w, [(10, 10), (14, 12)], tool='eraser', size=6)
        assert written == []
        w.editor.finish_stroke()
        assert len(written) == 2
    finally:
        close_window(qt, w)


def test_pencil_mousemove_no_worker(qt, tmp_path, monkeypatch):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        started = []
        monkeypatch.setattr(FrameEditor, '_start_preview', lambda self, *args: started.append(1))
        stroke_points(w, [(4, 5)] + [(x, 5) for x in range(6, 30)])
        assert started == []
        w.editor.finish_stroke()
        assert w.editor.pending is True
        assert w.editor.stroke is None
    finally:
        close_window(qt, w)


def test_eraser_mousemove_no_worker(qt, tmp_path, monkeypatch):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        started = []
        monkeypatch.setattr(FrameEditor, '_start_preview', lambda self, *args: started.append(1))
        stroke_points(w, [(10, 10), (16, 10)], tool='eraser', size=8)
        assert started == []
        w.editor.finish_stroke()
        assert w.editor.pending is True
    finally:
        close_window(qt, w)


def test_pencil_working_buffer_live(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        stroke_points(w, [(10, 10), (14, 10)], size=6, color=(255, 0, 0, 255))
        canvas = w.editor.canvas
        assert canvas.stroke_item.isVisible()
        image = canvas.stroke_item.image()
        assert image.pixelColor(12, 10).red() == 255
        assert image.pixelColor(12, 10).alpha() == 255
        assert w.project.raster_edit(animation_id, 0) is None
        w.editor.finish_stroke()
        assert not canvas.stroke_item.isVisible()
    finally:
        close_window(qt, w)


def test_eraser_working_buffer_live(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        stroke_points(w, [(11, 12), (11, 12)], tool='eraser', size=8)
        canvas = w.editor.canvas
        assert canvas.stroke_item.isVisible()
        assert canvas.stroke_item.image().pixelColor(11, 12).alpha() == 0
        w.editor.finish_stroke()
    finally:
        close_window(qt, w)


def test_pencil_interpolates_fast_stroke(qt, tmp_path):
    "A single far mouse move must still paint a continuous line."
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        stroke_points(w, [(6, 12), (26, 12)], size=6)
        w.editor.finish_stroke()
        row = w.project.raster_edit(animation_id, 0)
        layer = np.array(Image.open(row.paint_layer).convert('RGBA'))
        for x in range(6, 27):
            assert layer[12, x, 3] > 0, x
    finally:
        close_window(qt, w)


def test_one_stroke_one_commit(qt, tmp_path, monkeypatch):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        import app.core.pixel_edit as pixel_edit
        written = []
        monkeypatch.setattr(pixel_edit, 'save_layer', lambda *args, **kwargs: written.append(args[0]))
        c.entries = []
        c.index = 0
        entries = len(w._history().entries)
        stroke_points(w, [(6, 6)] + [(x, 6) for x in range(8, 24)])
        assert len(written) == 0
        w.editor.finish_stroke()
        assert len(written) == 2
        assert len(w._history().entries) == entries + 1
        assert w.project.raster_edit(animation_id, 0).revision == 1
    finally:
        close_window(qt, w)


def test_paint_mousemove_performance(qt, tmp_path):
    "mouseMove UI updates must stay well inside the frame budget (disk commit excluded)."
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        w.editor.set_tool('pencil')
        w.editor.brush_size.setValue(6)
        w.editor.brush_color = (255, 0, 0, 255)
        w.editor.begin_stroke(2, 2)
        for step in range(200):
            w.editor.stroke_point(2 + step % 28, 2 + (step // 28))
        stats = w.editor.stroke_performance()
        assert stats['count'] >= 200
        assert stats['median_ms'] <= 16., stats
        assert stats['p95_ms'] <= 50., stats
        w.editor.finish_stroke()
    finally:
        close_window(qt, w)


def test_timeline_frame_drag_uses_no_qdrag(qt, tmp_path, monkeypatch):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        def forbidden(*args, **kwargs):
            raise AssertionError('native QDrag must never be used')
        monkeypatch.setattr(QDrag, 'exec', forbidden)
        monkeypatch.setattr(QDrag, 'setPixmap', forbidden)
        target = c.new_group(name='JumpLoop')
        c.select_group(group.id)
        timeline = w.editor.timeline
        ids = [frame.id for frame in timeline.edit.frames()][:3]
        timeline.select_ids(ids)
        assert timeline.start_frame_drag()
        local = w.library_panel.tree.visualItemRect(w.library_panel.items[('GROUP', target.id)]).center()
        assert timeline.update_frame_drag(w.library_panel.tree.viewport().mapToGlobal(local)) == target.id
        assert timeline.finish_frame_drag(commit=True) is True
        assert w.project.library.in_group(group.id, kinds={'ANIMATION'})[0].animation_id != animation_id
        assert w.project.select_animation(w.project.library.in_group(target.id, kinds={'ANIMATION'})[0].animation_id).video.frame_count == 3
    finally:
        close_window(qt, w)


def test_timeline_frame_drag_no_native_pixmap(qt, tmp_path, monkeypatch):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        grabs = []
        pixmaps = []
        monkeypatch.setattr(QWidget, 'grab', lambda self, *args, **kwargs: grabs.append(self) or None)
        monkeypatch.setattr(QDrag, 'setPixmap', lambda self, pixmap: pixmaps.append(pixmap))
        monkeypatch.setattr(QDrag, 'exec', lambda self, *args, **kwargs: Qt.DropAction.IgnoreAction)
        target = c.new_group(name='JumpLoop')
        c.select_group(group.id)
        timeline = w.editor.timeline
        timeline.select_ids([frame.id for frame in timeline.edit.frames()][:2])
        assert timeline.start_frame_drag()
        local = w.library_panel.tree.visualItemRect(w.library_panel.items[('GROUP', target.id)]).center()
        timeline.update_frame_drag(w.library_panel.tree.viewport().mapToGlobal(local))
        assert timeline.finish_frame_drag(commit=False) is False
        assert grabs == [] and pixmaps == []
    finally:
        close_window(qt, w)


def test_timeline_frame_internal_drop(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path, count=8)
    try:
        target = c.new_group(name='JumpLoop')
        c.select_group(group.id)
        timeline = w.editor.timeline
        frames = timeline.edit.frames()
        timeline.select_ids([frame.id for frame in frames][2:5])
        assert timeline.start_frame_drag()
        tree = w.library_panel.tree
        local = tree.visualItemRect(w.library_panel.items[('GROUP', target.id)]).center()
        timeline.update_frame_drag(tree.viewport().mapToGlobal(local))
        assert timeline.frame_drop_target == target.id
        assert timeline.finish_frame_drag(commit=True)
        reduced = w.project.library.in_group(group.id, kinds={'ANIMATION'})[0]
        moved = w.project.library.in_group(target.id, kinds={'ANIMATION'})[0]
        assert w.project.select_animation(reduced.animation_id).video.frame_count == 5
        assert w.project.select_animation(moved.animation_id).video.frame_count == 3
    finally:
        close_window(qt, w)


def test_tree_group_drag_internal(qt, tmp_path):
    "Group reorder works through the internal controller; no QDrag is started."
    w, c, group, animation_id = editor_window(qt, tmp_path)
    try:
        first = c.new_group(name='Alpha')
        second = c.new_group(name='Beta')
        c.select_group(group.id)
        tree = w.library_panel.tree
        source = tree.visualItemRect(w.library_panel.items[('GROUP', second.id)]).center()
        target_rect = tree.visualItemRect(w.library_panel.items[('GROUP', first.id)])
        tree.mousePressEvent(QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(source), QPointF(source),
                                         Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                                         Qt.KeyboardModifier.NoModifier))
        above = QPointF(target_rect.left() + 5, target_rect.top() + 1)
        tree.mouseMoveEvent(QMouseEvent(QEvent.Type.MouseMove, above, above, Qt.MouseButton.NoButton,
                                        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        assert tree.drop_zone == ('GROUP', first.id, 'above')
        tree.mouseReleaseEvent(QMouseEvent(QEvent.Type.MouseButtonRelease, above, above,
                                           Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                                           Qt.KeyboardModifier.NoModifier))
        names = [row.name for row in w.project.library.ordered_children(None, None)]
        assert names.index('Beta') < names.index('Alpha')
        assert tree.drop_zone is None
    finally:
        close_window(qt, w)


def test_selection_overlay_above_cells(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path, count=12)
    try:
        timeline = w.editor.timeline
        empty_y = timeline.ruler_height + timeline.row_layout_height() - timeline.row_height / 2
        start = QPointF(timeline.label_width + 900, empty_y)
        end = QPointF(timeline.label_width + 12, timeline.ruler_height + 12)
        timeline.mousePressEvent(QMouseEvent(QEvent.Type.MouseButtonPress, start, start,
                                             Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                                             Qt.KeyboardModifier.NoModifier))
        timeline.mouseMoveEvent(QMouseEvent(QEvent.Type.MouseMove, end, end, Qt.MouseButton.NoButton,
                                            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        assert timeline.rubber is not None
        assert all(item.zValue() < 50 for item in timeline.scene().items()), 'no overlay scene item'
        image = render_viewport(timeline)
        scale = timeline.transform().m11()
        edge_y = int(timeline.ruler_height * scale) + 2
        row = image[max(0, edge_y)]
        assert row[:, 2].max() > 120, row[:, :4]
        timeline.mouseReleaseEvent(QMouseEvent(QEvent.Type.MouseButtonRelease, end, end,
                                               Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                                               Qt.KeyboardModifier.NoModifier))
        assert timeline.rubber is None
        assert timeline.ids()
    finally:
        close_window(qt, w)


def test_selection_survives_horizontal_scroll(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path, count=20)
    try:
        timeline = w.editor.timeline
        ids = [frame.id for frame in timeline.edit.frames()][4:20]
        timeline.select_ids(ids)
        selected = set(timeline.ids())
        assert selected == set(ids)
        bar = timeline.horizontalScrollBar()
        for value in (bar.maximum(), 0, bar.maximum(), 0):
            bar.setValue(value)
            events(qt, lambda: True)
            assert set(timeline.ids()) == selected
            assert timeline.rubber is None
        image = render_viewport(timeline)
        assert image.shape[0] > timeline.ruler_height
    finally:
        close_window(qt, w)


def test_rubber_band_removed_after_release(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path, count=12)
    try:
        timeline = w.editor.timeline
        start = QPointF(timeline.label_width + 900, timeline.ruler_height + timeline.row_layout_height() - 20)
        end = QPointF(timeline.label_width + 500, timeline.ruler_height + 12)
        timeline.mousePressEvent(QMouseEvent(QEvent.Type.MouseButtonPress, start, start,
                                             Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                                             Qt.KeyboardModifier.NoModifier))
        timeline.mouseMoveEvent(QMouseEvent(QEvent.Type.MouseMove, end, end, Qt.MouseButton.NoButton,
                                            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        timeline.mouseReleaseEvent(QMouseEvent(QEvent.Type.MouseButtonRelease, end, end,
                                               Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                                               Qt.KeyboardModifier.NoModifier))
        assert timeline.rubber is None and timeline.selecting is None
    finally:
        close_window(qt, w)


def test_scroll_visual_no_trail(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path, count=20)
    try:
        timeline = w.editor.timeline
        timeline.select_ids([frame.id for frame in timeline.edit.frames()][4:20])
        bar = timeline.horizontalScrollBar()
        for value in (bar.maximum(), 0, bar.maximum()):
            bar.setValue(value)
            events(qt, lambda: True)
        bar.setValue(bar.maximum() // 2)
        events(qt, lambda: True)
        dragged = grabbed(timeline.viewport())
        bar.setValue(0)
        events(qt, lambda: True)
        bar.setValue(bar.maximum() // 2)
        events(qt, lambda: True)
        fresh = grabbed(timeline.viewport())
        assert np.array_equal(dragged, fresh), int(np.abs(dragged.astype(int) - fresh.astype(int)).max())
    finally:
        close_window(qt, w)


def test_timeline_real_viewport_drag_no_trail(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path, count=20)
    try:
        timeline = w.editor.timeline
        for step in range(100):
            ids = [frame.id for frame in timeline.edit.frames()][: 2 + step % 6]
            timeline.select_ids(ids)
        timeline.select_ids([frame.id for frame in timeline.edit.frames()][4:12])
        events(qt, lambda: True)
        dragged = grabbed(timeline.viewport())
        timeline.select_ids([frame.id for frame in timeline.edit.frames()][:8])
        events(qt, lambda: True)
        timeline.select_ids([frame.id for frame in timeline.edit.frames()][4:12])
        events(qt, lambda: True)
        fresh = grabbed(timeline.viewport())
        difference = int(np.abs(dragged.astype(int) - fresh.astype(int)).max())
        assert np.array_equal(dragged, fresh), difference
    finally:
        close_window(qt, w)


def test_tree_real_viewport_drag_no_trail(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    fresh_folder = tmp_path / 'fresh-tree-view'
    fresh_folder.mkdir()
    try:
        library = w.project.library
        parent = c.new_group(name='Parent')
        for step in range(100):
            library.move_group(group.id, parent.id if step % 2 else None)
        library.move_group(group.id, None)
        c.selection = ('PROJECT', None)
        c.refresh()
        prepare_tree(w)
        events(qt, lambda: True)
        dragged = grabbed(w.library_panel.tree.viewport())
        w2 = window(qt, fresh_folder)
        try:
            w2.project = copy.deepcopy(w.project)
            w2.project_file = w.project_file
            w2.library_controller.selection = ('PROJECT', None)
            w2.resize(w.size())
            w2.library_controller.refresh()
            prepare_tree(w2)
            events(qt, lambda: True)
            fresh = grabbed(w2.library_panel.tree.viewport())
        finally:
            close_window(qt, w2)
        assert dragged.shape == fresh.shape
        difference = int(np.abs(dragged.astype(int) - fresh.astype(int)).max())
        assert np.array_equal(dragged, fresh), difference
    finally:
        close_window(qt, w)


def test_canvas_real_viewport_drag_no_trail(qt, tmp_path):
    w, c, group, animation_id = editor_window(qt, tmp_path)
    fresh_folder = tmp_path / 'fresh-canvas-view'
    fresh_folder.mkdir()
    try:
        w.resize(1200, 820)
        events(qt, lambda: True)
        canvas = w.editor.canvas
        centre = QPointF(canvas.viewport().rect().center())
        for step in range(200):
            delta = QPointF(60 if step % 2 == 0 else -60, 40 if step % 3 == 0 else 0)
            canvas.mousePressEvent(QMouseEvent(QEvent.Type.MouseButtonPress, centre, centre,
                                               Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                                               Qt.KeyboardModifier.NoModifier))
            canvas.mouseMoveEvent(QMouseEvent(QEvent.Type.MouseMove, centre + delta, centre + delta,
                                              Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
                                              Qt.KeyboardModifier.NoModifier))
            canvas.mouseReleaseEvent(QMouseEvent(QEvent.Type.MouseButtonRelease, centre + delta, centre + delta,
                                                 Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
                                                 Qt.KeyboardModifier.NoModifier))
        events(qt, lambda: not w.editor.worker and not w.editor.pending)
        final = w.project.frame_correction(0)
        dragged = grabbed(canvas.viewport())
        w2 = window(qt, fresh_folder)
        try:
            w2.project = copy.deepcopy(w.project)
            w2.project_file = w.project_file
            w2.cache_dir = w.cache_dir
            w2.built = True
            w2.resize(1200, 820)
            w2._loaded()
            w2.steps.setCurrentIndex(2)
            events(qt, lambda: not w2.worker)
            w2.library_controller.select_group(group.id)
            events(qt, lambda: w2.editor.provider is not None and not w2.editor.worker)
            w2.project.clear_frame_corrections()
            w2.project.set_frame_correction(0, *final)
            w2.editor.bind()
            events(qt, lambda: not w2.editor.worker and not w2.editor.pending)
            fresh = grabbed(w2.editor.canvas.viewport())
        finally:
            close_window(qt, w2)
        assert dragged.shape == fresh.shape
        difference = int(np.abs(dragged.astype(int) - fresh.astype(int)).max())
        assert np.array_equal(dragged, fresh), difference
    finally:
        close_window(qt, w)
