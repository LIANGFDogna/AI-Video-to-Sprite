import numpy as np
from PIL import Image

from app.core.project_workspace import create_project_workspace
from app.core.final_frame_provider import FinalFrameProvider
from app.models.project import Project
from app.ui.main_window import MainWindow
from app.ui.new_project_dialog import NewProjectDialog
from app.i18n import t
from test_workspace_ui import qt, events, close_window


def test_create_rectangular_canvas_and_custom_dimensions(qt, tmp_path):
    dialog = NewProjectDialog(initial_directory=str(tmp_path))
    results = []
    dialog.project_created.connect(lambda p, path: results.append((p, path)))
    dialog.show()
    try:
        dialog.name.setText('Rectangular')
        assert dialog.source_width.isEnabled() and dialog.source_height.isEnabled()
        dialog.canvas_preset.setCurrentIndex(dialog.canvas_preset.findData('1024x1536'))
        assert (dialog.source_width.value(), dialog.source_height.value()) == (1024, 1536)
        dialog.canvas_preset.setCurrentIndex(3)
        dialog.source_width.setValue(960)
        dialog.source_height.setValue(1280)
        assert dialog.canvas_preset.currentData() == 'custom'
        dialog.create_button.click()
        events(qt, lambda: bool(results))
        project, path = results[0]
        assert project.project_canvas == (960, 1280)
        assert Project.load(path).project_canvas == (960, 1280)
        assert not project.character_profile
    finally:
        if not results:
            dialog.close()
        events(qt)


def test_mixed_sequence_preview_reports_each_source_and_exports_same_cells(qt, tmp_path):
    window = MainWindow(tmp_path / 'app.log')
    window.project, window.project_file = create_project_workspace(tmp_path, 'Hero', project_canvas=(96, 64))
    window._loaded()
    window.show()
    try:
        folder = tmp_path / 'idle'
        folder.mkdir()
        for i, (w, h) in enumerate(((64, 64), (128, 32))):
            rgba = np.zeros((h, w, 4), np.uint8)
            rgba[8:16, 20:28] = (230, 40, 90, 180)
            Image.fromarray(rgba).save(folder / f'{i}.png')
        window.library_controller.new_group(name="Idle")
        window.import_sequence(folder)
        events(qt, lambda: window.sequence_dialog is not None and window.worker is None)
        dialog = window.sequence_dialog
        assert dialog.project_canvas == (96, 64) and dialog.import_button.isEnabled()
        assert '64 × 64' in dialog.canvas_info.text() and '128 × 32' in dialog.canvas_info.text()
        assert t('Project canvas fit runs first. Passthrough preserves the fitted positions and skips Root / Motion / Align.') in '\n'.join(w.text() for w in dialog.findChildren(type(dialog.canvas_info)))
        dialog.submit()
        events(qt, lambda: window.worker is None and window.built and window.sequence_dialog is None)
        assert window.project.layout.width == 96 and window.project.layout.height == 64
        expected = np.zeros((64, 96, 4), np.uint8)
        expected[8:16, 36:44] = (230, 40, 90, 180)
        review = window.open_animation_preview()
        events(qt, lambda: review.worker is None and review.last_pixels is not None)
        assert np.array_equal(review.last_pixels, expected)
        window.select_frame(1)
        assert '128 × 32' in window.source_info.text()
        assert '16 / 0 / 16 / 0' in window.project_canvas_info.text()
        assert '0 / 16 / 0 / 16' in window.project_canvas_info.text()
        window.export_to(tmp_path / 'export', godot=True)
        events(qt, lambda: window.worker is None and window.last_export is not None)
        assert np.array_equal(np.array(Image.open(tmp_path / 'export/frames/0000.png')), expected)
        provider = FinalFrameProvider(window.project, window.cache_dir)
        assert np.array_equal(np.array(Image.open(tmp_path / 'export/frames/0001.png')), provider.get_final_frame(1))
        review.close()
    finally:
        close_window(qt, window)
