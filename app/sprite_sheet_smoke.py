"""Sprite Sheet Slicer acceptance: fixed-cell slicing into a fully editable animation."""
import hashlib
import json
import logging
import time
from pathlib import Path

import numpy as np
from PIL import Image
from PySide6.QtCore import QTimer

from app import __build__
from app.core.final_frame_provider import FinalFrameProvider
from app.core.project_workspace import create_project_workspace
from app.core.sprite_sheet_slice import SliceConfig
from app.models.project import Project
from app.utils.cache import save_rgba
from app.utils.paths import cache_directory, frame_path

SHEET_SIZE = 512
COLUMNS, ROWS = 4, 2
CELL_W, CELL_H = SHEET_SIZE // COLUMNS, SHEET_SIZE // ROWS
FPS = 12.


def start_sprite_sheet_smoke(app, window, output, verify=False):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger('aivsprite.sheet_smoke')
    state = {'phase': 'verify' if verify else 'setup', 'started': time.monotonic()}
    report = {'status': 'failed', 'build': __build__}
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

    def sheet_pixels():
        pixels = np.zeros((SHEET_SIZE, SHEET_SIZE, 4), np.uint8)
        for row in range(ROWS):
            for column in range(COLUMNS):
                index = row * COLUMNS + column
                color = (20 + index * 25, 210 - index * 12, 70 + index * 18, 150 + index * 10)
                offset_x, offset_y = 12 + (index % 3) * 5, 18 + (index // 3) * 9
                pixels[row * CELL_H + offset_y:row * CELL_H + offset_y + 48,
                       column * CELL_W + offset_x:column * CELL_W + offset_x + 36] = color
        return pixels

    def cell_of(pixels, index):
        row, column = divmod(index, COLUMNS)
        return pixels[row * CELL_H:(row + 1) * CELL_H, column * CELL_W:(column + 1) * CELL_W]

    def group(name):
        return next(row for row in window.project.library.groups.values() if row.name == name)

    def animation_of(group_id):
        rows = window.project.library.in_group(group_id, kinds={'ANIMATION'})
        return rows[0].animation_id if rows else None

    def sliced_file(animation_id, index):
        project = window.project.select_animation(animation_id)
        return np.array(Image.open(frame_path(Path(project.sequence_folder), index)).convert('RGBA'))

    def rendered(animation_id, index):
        project = window.project.select_animation(animation_id)
        directory = cache_directory(window.project.project_id, window.project_file, animation_id)
        return FinalFrameProvider(project, directory, live_edit=True).get_final_frame(index)

    def content_pixel(image):
        rows = np.where(image[..., 3] > 0)[0]
        row = int(rows[len(rows) // 2])
        columns = np.where(image[row, :, 3] > 0)[0]
        return int(columns[len(columns) // 2]), row

    def verify_saved():
        target = output / 'sheet' / 'sheet.aivsprite'
        project = Project.load(target)
        library = project.library
        window.project = project
        window.project_file = target
        sheet_row = next(row for row in library.resources.values() if row.kind == 'SOURCE_SPRITE_SHEET')
        animation_row = next(row for row in library.resources.values() if row.kind == 'ANIMATION')
        window.cache_dir = cache_directory(project.project_id, target, animation_row.animation_id)
        animation = project.select_animation(animation_row.animation_id)
        assert animation.video.frame_count == 8, animation.video.frame_count
        assert abs(animation.video.fps - FPS) < 1e-9, animation.video.fps
        assert len(animation.timeline_edit.timeline_clips) == 8
        assert sheet_row.metadata['sliced_animation'] == animation_row.animation_id
        assert sheet_row.metadata['slice_config']['columns'] == COLUMNS
        assert Path(sheet_row.path).is_file()
        painted = animation.raster_edit(animation_row.animation_id, 3)
        assert painted is not None and Path(painted.paint_layer).is_file(), painted
        assert animation.frame_correction(5) == (6, -4), animation.frame_correction(5)
        directory = cache_directory(project.project_id, target, animation_row.animation_id)
        pixels = FinalFrameProvider(animation, directory, live_edit=True).get_final_frame(3)
        assert pixels[..., 0].max() == 255
        report.update(status='passed', restart_verified=True, reopened_frames=int(animation.video.frame_count),
                      reopened_fps=float(animation.video.fps),
                      reopened_timeline_clips=len(animation.timeline_edit.timeline_clips),
                      reopened_raster_edit=True, reopened_frame_correction=[6, -4])
        return True

    def poll():
        try:
            if state['phase'] != 'verify' and window.last_error:
                raise AssertionError(window.last_error)
            if time.monotonic() - state['started'] > 600:
                raise AssertionError('Sprite Sheet acceptance timed out: ' + state['phase'])
            if window.worker or time.monotonic() - state.get('ready', 0) < .15:
                return
            phase = state['phase']
            controller = window.library_controller
            if phase == 'verify':
                verify_saved()
                finish(0)
            elif phase == 'setup':
                window.project, window.project_file = create_project_workspace(output, 'sheet', 'standard')
                window._loaded()
                state['group'] = controller.new_group(name='Skill').id
                state['pixels'] = sheet_pixels()
                state['sheet_path'] = output / 'SkillSlash.png'
                Image.fromarray(state['pixels']).save(state['sheet_path'])
                state['sheet_digest'] = hashlib.sha256(state['sheet_path'].read_bytes()).hexdigest()
                controller.select_group(state['group'])
                resource = controller.import_sheet(str(state['sheet_path']))
                assert resource is not None
                state['sheet_resource'] = resource.id
                report['sheet_imported'] = True
                advance('slice')
            elif phase == 'slice':
                config = SliceConfig(columns=COLUMNS, rows=ROWS, cell_width=CELL_W, cell_height=CELL_H,
                                     fps=FPS, loop=True)
                assert controller.slice_sprite_sheet(state['sheet_resource'], config) is not None
                animation_id = animation_of(state['group'])
                state['animation'] = animation_id
                animation = window.project.select_animation(animation_id)
                report['frames'] = int(animation.video.frame_count)
                report['fps'] = float(animation.video.fps)
                report['cell_size'] = [CELL_W, CELL_H]
                report['timeline_clips'] = len(animation.timeline_edit.timeline_clips)
                report['row_major_order'] = all(
                    np.array_equal(sliced_file(animation_id, index), cell_of(state['pixels'], index))
                    for index in range(8))
                report['original_sheet_unchanged'] = bool(
                    hashlib.sha256(state['sheet_path'].read_bytes()).hexdigest() == state['sheet_digest'])
                sheet_row = window.project.library.resources[state['sheet_resource']]
                report['sheet_keeps_resource'] = sheet_row.kind == 'SOURCE_SPRITE_SHEET'
                report['slice_config_saved'] = bool(sheet_row.metadata.get('slice_config'))
                assert report['frames'] == 8
                assert abs(report['fps'] - FPS) < 1e-9
                assert report['timeline_clips'] == 8
                assert report['row_major_order']
                assert report['original_sheet_unchanged'] and report['sheet_keeps_resource']
                assert report['slice_config_saved']
                window.steps.setCurrentIndex(2)
                advance('editor')
            elif phase == 'editor':
                if window.editor.provider is None:
                    return
                report['editor_bound'] = True
                window.editor.select(0)
                advance('play')
            elif phase == 'play':
                if window.editor.worker or window.editor.pending:
                    return
                state['play_from'] = window.editor.index
                window.editor.toggle_play()
                advance('playing')
            elif phase == 'playing':
                if time.monotonic() - state['ready'] < 1.0:
                    return
                window.editor.stop()
                report['playback_advanced'] = window.editor.index != state['play_from']
                assert report['playback_advanced'], window.editor.index
                advance('edit_pencil')
            elif phase == 'edit_pencil':
                window.editor.select(3)
                advance('pencil_ready')
            elif phase == 'pencil_ready':
                if window.editor.worker or window.editor.pending:
                    return
                before = rendered(state['animation'], 3).copy()
                column, row = content_pixel(before)
                window.editor.set_tool('pencil')
                window.editor.brush_size.setValue(8)
                window.editor.brush_color = (255, 0, 0, 255)
                window.editor.begin_stroke(column, row)
                window.editor.stroke_point(column + 6, row)
                window.editor.finish_stroke()
                state['pencil_pixel'] = (column, row)
                advance('pencil_done')
            elif phase == 'pencil_done':
                if window.editor.worker or window.editor.pending:
                    return
                assert window.project.raster_edit(state['animation'], 3) is not None
                column, row = state['pencil_pixel']
                assert tuple(rendered(state['animation'], 3)[row, column]) == (255, 0, 0, 255)
                report['pencil_editable'] = True
                window.editor.select(4)
                advance('erase_ready')
            elif phase == 'erase_ready':
                if window.editor.worker or window.editor.pending:
                    return
                image = rendered(state['animation'], 4).copy()
                column, row = content_pixel(image)
                window.editor.set_tool('eraser')
                window.editor.brush_size.setValue(10)
                window.editor.begin_stroke(column, row)
                window.editor.stroke_point(column, row)
                window.editor.finish_stroke()
                state['erase_pixel'] = (column, row)
                advance('erase_done')
            elif phase == 'erase_done':
                if window.editor.worker or window.editor.pending:
                    return
                column, row = state['erase_pixel']
                assert rendered(state['animation'], 4)[row, column][3] == 0
                report['eraser_editable'] = True
                window.editor.select(5)
                advance('correction_ready')
            elif phase == 'correction_ready':
                if window.editor.worker or window.editor.pending:
                    return
                before = rendered(state['animation'], 5).copy()
                window.add_frame_correction([5], 6, -4)
                advance('correction_done')
            elif phase == 'correction_done':
                if window.editor.worker or window.editor.pending:
                    return
                assert window.project.select_animation(state['animation']).frame_correction(5) == (6, -4)
                report['frame_correction_editable'] = True
                window.project.save(window.project_file)
                report.update(status='passed', saved_project=str(window.project_file))
                finish(0)
        except AssertionError as error:
            report['failed_phase'] = state['phase']
            report['error'] = str(error)
            log.error('Sprite Sheet acceptance failed in %s: %s', state['phase'], error)
            finish(1)
        except Exception as error:  # noqa: BLE001 - the smoke must always write a receipt
            report['failed_phase'] = state['phase']
            report['error'] = f'{type(error).__name__}: {error}'
            log.exception('Sprite Sheet acceptance crashed in %s', state['phase'])
            finish(1)

    timer.timeout.connect(poll)
    timer.start()
