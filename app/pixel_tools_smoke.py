"""Phase 2F acceptance: Group drop zones, safe delete, pixel tools, derived frames, reference, trails."""
import copy
import hashlib
import json
import logging
import time
from pathlib import Path

import numpy as np
from PySide6.QtCore import QEvent, QPoint, QPointF, QTimer, Qt, QMimeData
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent, QImage, QMouseEvent, QPainter
from PIL import Image

from app import __build__
from app.core.final_frame_provider import FinalFrameProvider
from app.core.project_workspace import create_project_workspace
from app.models.character_reference import CharacterReference
from app.models.character_templates import PLAYER
from app.models.project import Project
from app.ui.project_library import MIME
from app.utils.cache import save_rgba
from app.utils.paths import cache_directory


def start_pixel_tools_smoke(app, window, output, verify=False):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger('aivsprite.pixel_smoke')
    state = {'phase': 'verify' if verify else 'setup', 'started': time.monotonic()}
    report = {'status': 'failed', 'build': __build__}
    window._failed = lambda error: setattr(window, 'last_error', error)
    window._export_notice = lambda result: None
    timer = QTimer(window)
    timer.setInterval(40)

    def advance(phase):
        state.update(phase=phase, ready=time.monotonic())

    def finish(code):
        timer.stop()
        if window.worker:
            window.worker.cancel()
            window.worker.wait()
            app.processEvents()
        window.editor.pause_preview()
        window.dirty = False
        receipt = output / 'validation.json'
        merged = {}
        if receipt.is_file():
            try:
                merged = json.loads(receipt.read_text(encoding='utf-8'))
            except ValueError:
                merged = {}
        merged.update(report)
        receipt.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding='utf-8')
        window.close()
        app.exit(code)

    def frames_folder(name, count=12):
        folder = output / name
        folder.mkdir(parents=True, exist_ok=True)
        for index in range(count):
            rgba = np.zeros((96, 96, 4), np.uint8)
            rgba[24:72, 18 + index:42 + index] = (200, 80, 120, 200)
            save_rgba(folder / f'frame_{index:04d}.png', rgba)
        return folder

    def group(name):
        return next(row for row in window.project.library.groups.values() if row.name == name)

    def child_names(parent):
        return [row.name for row in window.project.library.children(parent.id)]

    def digest(pixels):
        return hashlib.sha256(np.ascontiguousarray(pixels).tobytes()).hexdigest()

    def source_pixels(animation_id, index):
        project = window.project.select_animation(animation_id)
        directory = cache_directory(window.project.project_id, window.project_file, animation_id)
        return FinalFrameProvider(project, directory, live_edit=True).get_final_frame(index)

    def drop_group(dragged_id, kind, ident, zone):
        "Real drag events against the tree: Above / On / Below are decided by the tree itself."
        tree = window.library_panel.tree
        item = window.library_panel.items[(kind, ident)]
        tree.scrollToItem(item)
        app.processEvents()
        rect = tree.visualItemRect(item)
        margin = max(3, rect.height() // 4)
        y = rect.top() + 1 if zone == 'above' else rect.bottom() - 1 if zone == 'below' else rect.center().y()
        position = QPointF(rect.left() + 10, y)
        data = QMimeData()
        data.setData(MIME, json.dumps(['GROUP', dragged_id]).encode())
        tree.dragEnterEvent(QDragEnterEvent(position.toPoint(), Qt.DropAction.MoveAction, data,
                                            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        tree.dragMoveEvent(QDragMoveEvent(position.toPoint(), Qt.DropAction.MoveAction, data,
                                          Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
        assert tree.drop_zone == (kind, ident, zone), tree.drop_zone
        drop = QDropEvent(position, Qt.DropAction.MoveAction, data, Qt.MouseButton.LeftButton,
                          Qt.KeyboardModifier.NoModifier)
        tree.dropEvent(drop)
        assert drop.isAccepted()
        return True

    def render_widget(widget):
        target = widget.viewport() if hasattr(widget, 'viewport') else widget
        image = QImage(target.size(), QImage.Format.Format_ARGB32)
        image.fill(0)
        painter = QPainter(image)
        target.render(painter, QPoint(0, 0))
        painter.end()
        rows = np.frombuffer(image.constBits(), np.uint8).reshape(image.height(), image.bytesPerLine() // 4, 4)
        return rows[:, :image.width()].copy()

    def mouse_event(kind, point, button, buttons):
        return QMouseEvent(kind, QPointF(point), QPointF(point), button, buttons, Qt.KeyboardModifier.NoModifier)

    def drag_canvas(canvas, delta):
        centre = QPointF(canvas.viewport().rect().center())
        canvas.mousePressEvent(mouse_event(QEvent.Type.MouseButtonPress, centre, Qt.MouseButton.LeftButton,
                                           Qt.MouseButton.LeftButton))
        canvas.mouseMoveEvent(mouse_event(QEvent.Type.MouseMove, centre + QPointF(*delta), Qt.MouseButton.NoButton,
                                          Qt.MouseButton.LeftButton))
        canvas.mouseReleaseEvent(mouse_event(QEvent.Type.MouseButtonRelease, centre + QPointF(*delta),
                                             Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton))

    def stroke(points, tool='pencil', size=8, color=(255, 0, 0, 255)):
        window.editor.set_tool(tool)
        window.editor.brush_size.setValue(size)
        window.editor.brush_color = color
        window.editor.begin_stroke(*points[0])
        for point in points[1:]:
            window.editor.stroke_point(*point)
        window.editor.finish_stroke()

    def verify_saved_project():
        "Second process: the saved project must reproduce every Phase 2F result."
        target = output / 'pixel-tools' / 'pixel-tools.aivsprite'
        project = Project.load(target)
        library = project.library
        window.project = project
        window.project_file = target
        run_row = next(row for row in library.resources.values()
                       if row.kind == 'ANIMATION' and row.name.startswith('Run'))
        window.cache_dir = cache_directory(project.project_id, target, run_row.animation_id)
        jump = next(row for row in library.groups.values() if row.name == 'Jump')
        raster = project.raster_edit(run_row.animation_id, 5)
        assert raster is not None and raster.revision >= 3, raster
        assert Path(raster.paint_layer).is_file() and Path(raster.erase_mask).is_file()
        reference = library.frame_reference(run_row.animation_id)
        assert reference == {'animation_id': run_row.animation_id, 'frame_index': 0}, reference
        state_row = library.groups[run_row.group_id].animation_states.get(run_row.animation_id)
        assert state_row is not None and state_row.frame_reference_visible is True
        assert abs(state_row.frame_reference_opacity - .15) < 1e-6
        derived = [row for row in library.resources.values() if row.kind == 'ANIMATION'
                   and row.metadata.get('source_animation_id') == run_row.animation_id]
        assert len(derived) == 1, derived
        assert derived[0].metadata['source_frame_indices'] == [4, 5, 6, 9]
        derived_project = project.select_animation(derived[0].animation_id)
        assert derived_project.video.frame_count == 4 and derived_project.is_passthrough
        assert [row.name for row in library.children(jump.id)] == ['Land', 'JumpUp', 'DoubleJump'], \
            [row.name for row in library.children(jump.id)]
        assert library.groups[jump.id].parent_id is None
        painted = np.array(Image.open(raster.paint_layer).convert('RGBA'))
        assert painted[..., 3].max() > 0
        run_directory = cache_directory(project.project_id, target, run_row.animation_id)
        run_project = project.select_animation(run_row.animation_id)
        report['verify_debug'] = {'current_animation': project.animation_id == run_row.animation_id,
                                  'layout': str(run_project.layout),
                                  'animations': sorted(project.animations),
                                  'align_json': (run_directory / 'align.json').is_file(),
                                  'final_json': (run_directory / 'final.json').is_file(),
                                  'frame_count': run_project.video.frame_count}
        source = FinalFrameProvider(run_project, run_directory, live_edit=True)
        assert source.get_final_frame(5).shape[:2] == (96, 96)
        report.update(status='passed', restart_verified=True, raster_revision=int(raster.revision),
                      derived_frames=int(derived_project.video.frame_count), reference_frame=0,
                      jump_children=[row.name for row in library.children(jump.id)])
        return True

    def poll():
        try:
            if state['phase'] != 'verify' and window.last_error:
                raise AssertionError(window.last_error)
            if time.monotonic() - state['started'] > 420:
                raise AssertionError('Pixel tool acceptance timed out: ' + state['phase'])
            if window.worker or time.monotonic() - state.get('ready', 0) < .15:
                return
            phase = state['phase']
            controller = window.library_controller
            if phase == 'verify':
                verify_saved_project()
                finish(0)
            elif phase == 'setup':
                window.project, window.project_file = create_project_workspace(output, 'pixel-tools', 'standard',
                                                                              project_canvas=(96, 96))
                window._loaded()
                player = controller.new_character(name='Player', template_id=PLAYER)
                state['player'] = player.id
                state['idle'], state['run'] = group('Idle').id, group('Run').id
                state['jump'], state['jump_up'] = group('Jump').id, group('JumpUp').id
                state['fall'], state['land'] = group('FallLoop').id, group('Land').id
                state['attack1'] = group('Attack1').id
                controller.select_group(state['idle'])
                window.import_sequence(frames_folder('Idle Frames'))
                advance('idle_import')
            elif phase == 'idle_import':
                if not window.sequence_dialog:
                    return
                window.sequence_dialog.submit()
                advance('idle_built')
            elif phase == 'idle_built':
                if not window.built:
                    return
                state['idle_animation'] = window.project.animation_id
                window._save_character_reference(CharacterReference(window.project.animation_id, 0, 48, 86, 96, 96))
                controller.select_group(state['run'])
                window.import_sequence(frames_folder('Run Frames'))
                advance('run_import')
            elif phase == 'run_import':
                if not window.sequence_dialog:
                    return
                window.sequence_dialog.submit()
                advance('run_built')
            elif phase == 'run_built':
                if not window.built:
                    return
                state['run_animation'] = window.project.animation_id
                window.steps.setCurrentIndex(2)
                advance('editor')
            elif phase == 'editor':
                if window.editor.provider is None:
                    return
                library = window.project.library
                assert child_names(library.groups[state['jump']]) == ['JumpUp', 'FallLoop', 'Land', 'DoubleJump'], \
                    child_names(library.groups[state['jump']])
                advance('tree_ops')
            elif phase == 'tree_ops':
                library = window.project.library
                assert drop_group(state['land'], 'GROUP', state['jump_up'], 'above')
                assert child_names(library.groups[state['jump']]) == ['Land', 'JumpUp', 'FallLoop', 'DoubleJump'], \
                    child_names(library.groups[state['jump']])
                assert drop_group(state['fall'], 'GROUP', state['jump_up'], 'on')
                assert library.groups[state['fall']].parent_id == state['jump_up']
                assert drop_group(state['fall'], 'GROUP', state['jump'], 'on')
                parents = {row.id: row.parent_id for row in library.groups.values()}
                assert parents[state['fall']] == state['jump'] and parents[state['land']] == state['jump'], parents
                assert child_names(library.groups[state['jump']]) == ['Land', 'JumpUp', 'DoubleJump', 'FallLoop'], \
                    child_names(library.groups[state['jump']])
                report['group_reorder_and_nest'] = True
                controller.select_group(state['jump'])
                advance('delete')
            elif phase == 'delete':
                controller.remove_group(state['fall'], confirmed=True)
                library = window.project.library
                assert state['fall'] not in library.groups
                for ident in (state['jump'], state['jump_up'], state['land'], state['player']):
                    assert ident in library.groups or ident in library.characters
                assert child_names(library.groups[state['jump']]) == ['Land', 'JumpUp', 'DoubleJump']
                report['delete_kept_parent_and_siblings'] = True
                controller.select_group(state['run'])
                window.editor.select(5)
                advance('pixel')
            elif phase == 'pixel':
                before = source_pixels(state['run_animation'], 5).copy()
                history = len(window._history().entries)
                stroke([(30, 60), (36, 60), (42, 60)], size=8, color=(255, 0, 0, 255))
                painted = source_pixels(state['run_animation'], 5)
                assert not np.array_equal(painted, before)
                assert tuple(painted[60, 36]) == (255, 0, 0, 255), painted[60, 36]
                assert len(window._history().entries) == history + 1
                window.undo_edit()
                assert np.array_equal(source_pixels(state['run_animation'], 5), before)
                window.redo_edit()
                assert tuple(source_pixels(state['run_animation'], 5)[60, 36]) == (255, 0, 0, 255)
                report['pencil_stroke_one_undo'] = True
                stroke([(36, 60), (36, 66)], tool='eraser', size=8)
                assert source_pixels(state['run_animation'], 5)[66, 36][3] == 0
                window.undo_edit()
                assert source_pixels(state['run_animation'], 5)[66, 36][3] > 0
                window.redo_edit()
                assert source_pixels(state['run_animation'], 5)[66, 36][3] == 0
                report['eraser_stroke_one_undo'] = True
                state['paint_revision'] = window.project.raster_edit(state['run_animation'], 5).revision
                advance('reference')
            elif phase == 'reference':
                window.editor.set_frame_reference_for(0)
                window.editor.select(5)
                advance('reference_ready')
            elif phase == 'reference_ready':
                if window.editor.worker or window.editor.pending:
                    return
                canvas = window.editor.canvas
                assert canvas.ghost_pixels is not None and canvas.reference_pixels is not None
                assert canvas.idle_ghost_item.isVisible() and canvas.frame_reference_item.isVisible()
                state['ghost_digest'] = digest(canvas.ghost_pixels)
                state['reference_digest'] = digest(canvas.reference_pixels)
                stroke([(30, 30), (34, 34)], size=8, color=(0, 255, 0, 255))
                stroke([(30, 30)], tool='eraser', size=8)
                advance('reference_check')
            elif phase == 'reference_check':
                if window.editor.worker or window.editor.pending:
                    return
                canvas = window.editor.canvas
                assert digest(canvas.ghost_pixels) == state['ghost_digest']
                assert digest(canvas.reference_pixels) == state['reference_digest']
                assert window.project.library.frame_reference(state['run_animation']) == \
                    {'animation_id': state['run_animation'], 'frame_index': 0}
                report['overlays_unchanged_by_paint'] = True
                advance('multi')
            elif phase == 'multi':
                before = source_pixels(state['run_animation'], 4).copy()
                assert controller.drop_frames_to_group(state['run_animation'], [4, 5, 6, 9], state['attack1'])
                derived = next(row for row in window.project.library.in_group(state['attack1'], kinds={'ANIMATION'}))
                project = window.project.select_animation(derived.animation_id)
                assert project.video.frame_count == 4 and project.is_passthrough
                written = [np.array(Image.open(path).convert('RGBA'))
                           for path in sorted(Path(project.sequence_folder).glob('*.png'))]
                assert len(written) == 4 and written[0][..., 3].max() == 200
                assert np.array_equal(source_pixels(state['run_animation'], 4), before)
                report['derived_sequence_frames'] = 4
                report['derived_sequence_no_rekey'] = bool(project.is_passthrough)
                window.project.save(window.project_file)
                advance('trail')
            elif phase == 'trail':
                controller.select_group(state['run'])
                window.editor.set_tool('move')
                # Drag the current frame itself, not the whole animation offset.
                window.editor.position_frame.setChecked(True)
                window.editor.select(0)
                advance('trail_ready')
            elif phase == 'trail_ready':
                if window.editor.provider is None or window.editor.worker or window.editor.pending:
                    return
                assert window.editor.index == 0, window.editor.index
                window.resize(1280, 860)
                canvas = window.editor.canvas
                for step in range(100):
                    drag_canvas(canvas, (60 if step % 2 == 0 else -60, 0))
                drag_canvas(canvas, (60, 0))
                advance('trail_render')
            elif phase == 'trail_render':
                if window.editor.worker or window.editor.pending:
                    return
                final = window.project.frame_correction(0)
                report['trail_debug'] = {'corrections': {str(key): list(value) for key, value in
                                                        window.project.frame_corrections.items()},
                                         'editor_index': window.editor.index,
                                         'display_scale': window.editor.canvas.display_scale,
                                         'tool': window.editor.canvas.tool,
                                         'zoom': window.editor.canvas.transform().m11(),
                                         'viewport': [window.editor.canvas.viewport().width(),
                                                      window.editor.canvas.viewport().height()]}
                assert final != (0, 0), report['trail_debug']
                state['canvas_dragged'] = render_widget(window.editor.canvas)
                baseline = copy.deepcopy(window.project)
                baseline.clear_frame_corrections()
                baseline.set_frame_correction(0, *final)
                window.project = baseline
                window._refresh_editor()
                advance('trail_compare')
            elif phase == 'trail_compare':
                if window.editor.provider is None or window.editor.worker or window.editor.pending:
                    return
                fresh = render_widget(window.editor.canvas)
                dragged = state['canvas_dragged']
                assert dragged.shape == fresh.shape
                report['canvas_trail_pixel_difference'] = int(np.abs(dragged.astype(int) - fresh.astype(int)).max())
                assert report['canvas_trail_pixel_difference'] == 0
                advance('tree_trail')
            elif phase == 'tree_trail':
                library = window.project.library
                for step in range(100):
                    library.move_group(state['land'], state['jump_up'] if step % 2 else state['jump'])
                # Back to the accepted order: Land first, then JumpUp and DoubleJump.
                library.move_group(state['land'], state['jump'], 0)
                controller.selection = ('PROJECT', None)
                controller.refresh()
                state['tree_first'] = render_widget(window.library_panel.tree)
                advance('tree_compare')
            elif phase == 'tree_compare':
                controller.selection = ('PROJECT', None)
                controller.refresh()
                second = render_widget(window.library_panel.tree)
                report['tree_fresh_render_equal'] = bool(np.array_equal(state['tree_first'], second))
                assert report['tree_fresh_render_equal']
                timeline = window.editor.timeline
                timeline.select_ids([frame.id for frame in timeline.edit.frames()][:4])
                dragged_frames = [frame.source_index for frame in timeline.edit.selected(timeline.ids(), False)]
                assert dragged_frames == [0, 1, 2, 3], dragged_frames
                report['frame_drag_payload'] = dragged_frames
                report['node_cardinality'] = len(window.editor.canvas.scene().items())
                assert report['node_cardinality'] == 3
                window.dirty = True
                window.project.save(window.project_file)
                report.update(status='passed', pencil_rgb=True, raster_revision=int(state['paint_revision']),
                              ghost_unchanged=True, reference_unchanged=True,
                              saved_project=str(window.project_file))
                finish(0)
        except AssertionError as error:
            report['failed_phase'] = state['phase']
            report['error'] = str(error)
            log.error('Pixel tool acceptance failed in %s: %s', state['phase'], error)
            finish(1)
        except Exception as error:  # noqa: BLE001 - the smoke must always write a receipt
            report['failed_phase'] = state['phase']
            report['error'] = f'{type(error).__name__}: {error}'
            log.exception('Pixel tool acceptance crashed in %s', state['phase'])
            finish(1)

    timer.timeout.connect(poll)
    timer.start()
