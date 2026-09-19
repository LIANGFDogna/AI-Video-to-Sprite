"""Phase 2F.1 acceptance: frame move semantics, in-app drags and paint latency.

Counters in validation.json:
  jump_up_frames / jump_loop_frames / disk_source_files / canonical_pixels_equal
  native_qdrag_used / canvas_visual_diff / timeline_visual_diff / tree_visual_diff
  paint_mousemove_median_ms / paint_mousemove_p95_ms / erase_mousemove_* / restart_verified
"""
import copy
import hashlib
import json
import logging
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QEvent, QPoint, QPointF, QTimer, Qt
from PySide6.QtGui import QDrag, QImage, QMouseEvent, QPainter
from PIL import Image

from app import __build__
from app.core.final_frame_provider import FinalFrameProvider
from app.core.frame_move import canonical_folder
from app.core.project_workspace import create_project_workspace
from app.models.project import Project
from app.utils.cache import save_rgba
from app.utils.paths import cache_directory, frame_path

SIZES = {'move': 41, 'timing': 1}


def _percentile(values, ratio):
    values = sorted(values)
    if not values:
        return 0.
    index = min(len(values) - 1, max(0, int(round(len(values) * ratio)) - 1))
    return round(values[index], 3)


def start_interaction_smoke(app, window, output, verify=False):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger('aivsprite.interaction_smoke')
    state = {'phase': 'verify' if verify else 'setup', 'started': time.monotonic()}
    report = {'status': 'failed', 'build': __build__, 'native_qdrag_used': False}
    window._failed = lambda error: setattr(window, 'last_error', error)
    window._export_notice = lambda result: None
    timer = QTimer(window)
    timer.setInterval(40)

    def advance(phase):
        state.update(phase=phase, ready=time.monotonic())

    def receipt():
        path = output / 'validation.json'
        merged = {}
        if path.is_file():
            try:
                merged = json.loads(path.read_text(encoding='utf-8'))
            except ValueError:
                merged = {}
        merged.update(report)
        path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding='utf-8')

    def finish(code):
        timer.stop()
        if window.worker:
            window.worker.cancel()
            window.worker.wait()
            app.processEvents()
        window.editor.pause_preview()
        window.dirty = False
        receipt()
        window.close()
        app.exit(code)

    # ---------------------------------------------------------------- helpers
    def frames_folder(name, count, size):
        folder = output / name
        folder.mkdir(parents=True, exist_ok=True)
        for index in range(count):
            rgba = np.zeros((size, size, 4), np.uint8)
            band = max(3, size // 8)
            rgba[size // 4:size // 4 + band * 2, size // 8 + index % 5:size // 8 + band + index % 5] = (200, 80, 120, 200)
            save_rgba(folder / f'frame_{index:06d}.png', rgba)
        return folder

    def group(name):
        return next(row for row in window.project.library.groups.values() if row.name == name)

    def animation_of(group_id):
        rows = window.project.library.in_group(group_id, kinds={'ANIMATION'})
        return rows[0].animation_id if rows else None

    def canonical(animation_id, index):
        directory = cache_directory(window.project.project_id, window.project_file, animation_id)
        return np.array(Image.open(frame_path(canonical_folder(directory), index)).convert('RGBA'))

    def canonical_digest(animation_id, indices):
        digest = hashlib.sha256()
        for index in indices:
            digest.update(np.ascontiguousarray(canonical(animation_id, index)).tobytes())
        return digest.hexdigest()

    def grabbed(widget):
        pixmap = widget.grab()
        image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        rows = np.frombuffer(image.constBits(), np.uint8).reshape(image.height(), image.bytesPerLine() // 4, 4)
        return rows[:, :image.width()].copy()

    def mouse(kind, point, button, buttons, global_point=None):
        global_point = global_point if global_point is not None else point
        return QMouseEvent(kind, QPointF(point), QPointF(point), QPointF(global_point), button, buttons,
                           Qt.KeyboardModifier.NoModifier)

    def canvas_drag(canvas, delta):
        centre = QPointF(canvas.viewport().rect().center())
        canvas.mousePressEvent(mouse(QEvent.Type.MouseButtonPress, centre, Qt.MouseButton.LeftButton,
                                     Qt.MouseButton.LeftButton))
        canvas.mouseMoveEvent(mouse(QEvent.Type.MouseMove, centre + delta, Qt.MouseButton.NoButton,
                                    Qt.MouseButton.LeftButton))
        canvas.mouseReleaseEvent(mouse(QEvent.Type.MouseButtonRelease, centre + delta, Qt.MouseButton.LeftButton,
                                       Qt.MouseButton.NoButton))

    def paint_stroke(timings, tool, size, paths):
        editor = window.editor
        editor.set_tool(tool)
        editor.brush_size.setValue(size)
        editor.brush_color = (255, 0, 0, 255) if tool == 'pencil' else (0, 0, 0, 0)
        for path in paths:
            editor.begin_stroke(*path[0])
            for point in path[1:]:
                editor.stroke_point(*point)
            editor.finish_stroke()
            stats = editor.stroke_performance()
            if stats['count']:
                timings.append(stats)

    def verify_saved():
        target = output / 'interaction' / 'interaction.aivsprite'
        project = Project.load(target)
        library = project.library
        window.project = project
        window.project_file = target
        jump_up = next(row for row in library.groups.values() if row.name == 'JumpUp')
        loop = next(row for row in library.groups.values() if row.name == 'JumpLoop')
        reduced = project.select_animation(animation_of_in(library, jump_up.id))
        moved = project.select_animation(animation_of_in(library, loop.id))
        assert reduced.video.frame_count == SIZES['move'] - 4, reduced.video.frame_count
        assert moved.video.frame_count == 4, moved.video.frame_count
        source = Path(reduced.sequence_folder)
        assert source.is_dir()
        report.update(status='passed', restart_verified=True,
                      jump_up_frames=int(reduced.video.frame_count),
                      jump_loop_frames=int(moved.video.frame_count),
                      disk_source_files=len(list((output / 'JumpUp Frames').iterdir())))
        return True

    def animation_of_in(library, group_id):
        rows = library.in_group(group_id, kinds={'ANIMATION'})
        return rows[0].animation_id if rows else None

    # ---------------------------------------------------------------- phases
    def poll():
        try:
            if state['phase'] != 'verify' and window.last_error:
                raise AssertionError(window.last_error)
            if time.monotonic() - state['started'] > 600:
                raise AssertionError('Interaction acceptance timed out: ' + state['phase'])
            if window.worker or time.monotonic() - state.get('ready', 0) < .15:
                return
            phase = state['phase']
            controller = window.library_controller
            if phase == 'verify':
                verify_saved()
                finish(0)
            elif phase == 'setup':
                # Native QDrag must never run during this smoke.
                QDrag.exec = lambda self, *args, **kwargs: (_ for _ in ()).throw(
                    AssertionError('native QDrag used'))
                QDrag.setPixmap = lambda self, *args, **kwargs: (_ for _ in ()).throw(
                    AssertionError('native drag pixmap used'))
                window.project, window.project_file = create_project_workspace(output, 'interaction', 'standard',
                                                                              project_canvas=(96, 96))
                window._loaded()
                state['jump_up'] = controller.new_group(name='JumpUp').id
                state['jump_loop'] = controller.new_group(name='JumpLoop').id
                controller.select_group(state['jump_up'])
                window.import_sequence(frames_folder('JumpUp Frames', SIZES['move'], 96))
                advance('import')
            elif phase == 'import':
                if not window.sequence_dialog:
                    return
                window.sequence_dialog.submit()
                advance('built')
            elif phase == 'built':
                if not window.built:
                    return
                state['source_animation'] = window.project.animation_id
                state['before_digest'] = canonical_digest(state['source_animation'], [1, 2, 3, 4])
                state['source_folder_files'] = len(list((output / 'JumpUp Frames').iterdir()))
                window.steps.setCurrentIndex(2)
                advance('editor')
            elif phase == 'editor':
                if window.editor.provider is None:
                    return
                advance('move')
            elif phase == 'move':
                # Real internal drag: Timeline selection -> Project Library tree.
                timeline = window.editor.timeline
                window.editor.set_tool('move')
                window.editor.select(0)
                frames = timeline.edit.frames()
                timeline.select_ids([frame.id for frame in frames][1:5])
                assert timeline.start_frame_drag()
                tree = window.library_panel.tree
                local = tree.visualItemRect(window.library_panel.items[('GROUP', state['jump_loop'])]).center()
                assert timeline.update_frame_drag(tree.viewport().mapToGlobal(local)) == state['jump_loop']
                assert timeline.finish_frame_drag(commit=True)
                reduced = animation_of(state['jump_up'])
                moved = animation_of(state['jump_loop'])
                state['reduced'], state['moved'] = reduced, moved
                report['jump_up_frames'] = int(window.project.select_animation(reduced).video.frame_count)
                report['jump_loop_frames'] = int(window.project.select_animation(moved).video.frame_count)
                report['disk_source_files'] = len(list((output / 'JumpUp Frames').iterdir()))
                report['canonical_pixels_equal'] = bool(
                    canonical_digest(moved, [0, 1, 2, 3]) == state['before_digest'])
                assert report['jump_up_frames'] == SIZES['move'] - 4
                assert report['jump_loop_frames'] == 4
                assert report['disk_source_files'] == state['source_folder_files'] == SIZES['move']
                assert report['canonical_pixels_equal']
                window.project.save(window.project_file)
                advance('undo')
            elif phase == 'undo':
                window.undo_edit()
                library = window.project.library
                assert library.animation(state['source_animation']) is not None
                assert window.project.select_animation(state['source_animation']).video.frame_count == SIZES['move']
                assert library.in_group(state['jump_loop'], kinds={'ANIMATION'}) == []
                report['undo_restores_source'] = True
                advance('redo')
            elif phase == 'redo':
                window.redo_edit()
                assert window.project.select_animation(animation_of(state['jump_up'])).video.frame_count == \
                    SIZES['move'] - 4
                assert window.project.select_animation(animation_of(state['jump_loop'])).video.frame_count == 4
                report['redo_moves_again'] = True
                window.project.save(window.project_file)
                advance('drags')
            elif phase == 'drags':
                controller.select_group(state['jump_up'])
                window.editor.select(0)
                window.resize(1280, 860)
                advance('drags_ready')
            elif phase == 'drags_ready':
                if window.editor.provider is None or window.editor.worker or window.editor.pending:
                    return
                canvas = window.editor.canvas
                window.editor.set_tool('move')
                window.editor.position_frame.setChecked(True)
                for step in range(200):
                    canvas_drag(canvas, QPointF(60 if step % 2 == 0 else -60, 40 if step % 3 == 0 else 0))
                state['canvas_final'] = window.project.frame_correction(0)
                assert state['canvas_final'] != (0, 0), state['canvas_final']
                advance('canvas_settle')
            elif phase == 'canvas_settle':
                if window.editor.worker or window.editor.pending:
                    return
                state['canvas_dragged'] = grabbed(window.editor.canvas.viewport())
                baseline = copy.deepcopy(window.project)
                baseline.clear_frame_corrections()
                baseline.set_frame_correction(0, *state['canvas_final'])
                window.project = baseline
                window._refresh_editor()
                advance('canvas_diff')
            elif phase == 'canvas_diff':
                if window.editor.provider is None or window.editor.worker or window.editor.pending:
                    return
                fresh = grabbed(window.editor.canvas.viewport())
                dragged = state['canvas_dragged']
                assert dragged.shape == fresh.shape, (dragged.shape, fresh.shape)
                report['canvas_visual_diff'] = int(np.abs(dragged.astype(int) - fresh.astype(int)).max())
                assert report['canvas_visual_diff'] == 0, report['canvas_visual_diff']
                advance('timeline_drags')
            elif phase == 'timeline_drags':
                timeline = window.editor.timeline
                for step in range(100):
                    ids = [frame.id for frame in timeline.edit.frames()][: 2 + step % 6]
                    timeline.select_ids(ids)
                timeline.select_ids([frame.id for frame in timeline.edit.frames()][4:12])
                time.sleep(.05)
                app.processEvents()
                events_drain = grabbed(timeline.viewport())
                timeline.select_ids([frame.id for frame in timeline.edit.frames()][:8])
                timeline.select_ids([frame.id for frame in timeline.edit.frames()][4:12])
                fresh = grabbed(timeline.viewport())
                report['timeline_visual_diff'] = int(np.abs(events_drain.astype(int) - fresh.astype(int)).max())
                assert report['timeline_visual_diff'] == 0, report['timeline_visual_diff']
                advance('frame_drags')
            elif phase == 'frame_drags':
                timeline = window.editor.timeline
                tree = window.library_panel.tree
                frames = timeline.edit.frames()
                for step in range(50):
                    timeline.select_ids([frame.id for frame in frames][step % 4:(step % 4) + 1])
                    assert timeline.start_frame_drag()
                    local = tree.visualItemRect(window.library_panel.items[('GROUP', state['jump_loop'])]).center()
                    timeline.update_frame_drag(tree.viewport().mapToGlobal(local))
                    timeline.finish_frame_drag(commit=False)
                report['timeline_internal_drags'] = 50
                advance('tree_drags')
            elif phase == 'tree_drags':
                parent = controller.new_group(name='TreeParent')
                tree = window.library_panel.tree
                for step in range(50):
                    tree.scrollToItem(window.library_panel.items[('GROUP', state['jump_loop'])])
                    app.processEvents()
                    start = tree.visualItemRect(window.library_panel.items[('GROUP', state['jump_loop'])]).center()
                    tree.mousePressEvent(mouse(QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton,
                                               Qt.MouseButton.LeftButton))
                    # Selecting on press rebuilds the tree; re-read the target row afterwards.
                    app.processEvents()
                    target_item = window.library_panel.items[('GROUP', parent.id)]
                    tree.scrollToItem(target_item)
                    app.processEvents()
                    rect = tree.visualItemRect(target_item)
                    tree.mouseMoveEvent(mouse(QEvent.Type.MouseMove, rect.center(), Qt.MouseButton.NoButton,
                                              Qt.MouseButton.LeftButton))
                    tree.mouseReleaseEvent(mouse(QEvent.Type.MouseButtonRelease, rect.center(),
                                                 Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton))
                # Group selection on press replaces the live Project; read the fresh library.
                assert window.project.library.groups[state['jump_loop']].parent_id == parent.id
                report['tree_internal_drags'] = 50
                # Identical selection, expansion, scroll and focus for both framebuffer grabs.
                controller.selection = ('GROUP', state['jump_loop'])
                controller.refresh()
                tree = window.library_panel.tree
                tree.expandAll()
                tree.verticalScrollBar().setValue(0)
                tree.horizontalScrollBar().setValue(0)
                tree.setFocus()
                app.processEvents()
                state['tree_dragged'] = grabbed(tree.viewport())
                advance('tree_diff')
            elif phase == 'tree_diff':
                library = window.project.library
                library.move_group(state['jump_loop'], None)
                library.move_group(state['jump_loop'], next(row.id for row in library.groups.values()
                                                            if row.name == 'TreeParent'))
                controller.selection = ('GROUP', state['jump_loop'])
                controller.refresh()
                tree = window.library_panel.tree
                tree.expandAll()
                tree.verticalScrollBar().setValue(0)
                tree.horizontalScrollBar().setValue(0)
                tree.setFocus()
                app.processEvents()
                fresh = grabbed(tree.viewport())
                dragged = state['tree_dragged']
                if dragged.shape != fresh.shape:
                    report['tree_visual_diff'] = -1
                else:
                    report['tree_visual_diff'] = int(np.abs(dragged.astype(int) - fresh.astype(int)).max())
                assert report['tree_visual_diff'] == 0, report['tree_visual_diff']
                advance('paint')
            elif phase == 'paint':
                window.editor.set_tool('pencil')
                state['paint'] = []
                state['erase'] = []
                paths = [[(4 + step, 8 + row), (20 + step, 8 + row), (40 + step, 8 + row)]
                         for row, step in enumerate(range(0, 20, 2))]
                paint_stroke(state['paint'], 'pencil', 6, paths[:10])
                paint_stroke(state['erase'], 'eraser', 8,
                             [[(6 + step, 12), (24 + step, 12)] for step in range(0, 20, 2)][:10])
                report['paint_mousemove_median_ms'] = _percentile(
                    [row['median_ms'] for row in state['paint']], .5)
                report['paint_mousemove_p95_ms'] = max((row['p95_ms'] for row in state['paint']), default=0.)
                report['erase_mousemove_median_ms'] = _percentile(
                    [row['median_ms'] for row in state['erase']], .5)
                report['erase_mousemove_p95_ms'] = max((row['p95_ms'] for row in state['erase']), default=0.)
                report['paint_moves'] = int(sum(row['count'] for row in state['paint']))
                report['erase_moves'] = int(sum(row['count'] for row in state['erase']))
                assert report['paint_moves'] >= 10 and report['erase_moves'] >= 10
                report['paint_median_ok'] = bool(report['paint_mousemove_median_ms'] <= 16.)
                report['paint_p95_ok'] = bool(report['paint_mousemove_p95_ms'] <= 50.)
                assert report['paint_median_ok'] and report['paint_p95_ok'], report
                window.project.save(window.project_file)
                report.update(status='passed', native_qdrag_used=False)
                finish(0)
        except AssertionError as error:
            report['failed_phase'] = state['phase']
            report['error'] = str(error)
            log.error('Interaction acceptance failed in %s: %s', state['phase'], error)
            finish(1)
        except Exception as error:  # noqa: BLE001 - the smoke must always write a receipt
            report['failed_phase'] = state['phase']
            report['error'] = f'{type(error).__name__}: {error}'
            log.exception('Interaction acceptance crashed in %s', state['phase'])
            finish(1)

    timer.timeout.connect(poll)
    timer.start()
