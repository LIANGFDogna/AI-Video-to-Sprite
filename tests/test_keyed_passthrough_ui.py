import numpy as np
import pytest
import shutil
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from app.i18n import t
from app.core.pipeline import Pipeline
from app.core.final_frame_provider import FinalFrameProvider
from app.ui.main_window import MainWindow
from app.utils.paths import frame_path, cache_directory
from test_keyed_passthrough import keyed_video
from test_workspace_ui import qt, events, close_window


def test_video_key_choice_preview_and_anchor_resume(qt, keyed_video, tmp_path, monkeypatch):
    pipe, _ = keyed_video
    window = MainWindow(tmp_path / 'app.log')
    window.project, window.cache_dir = pipe.project, pipe.cache_dir
    window._loaded()
    window.show()
    try:
        window.steps.setCurrentIndex(1)
        events(qt)
        scroll = window.panels.widget(1).verticalScrollBar()
        scroll.setValue(scroll.maximum())
        window.process_key()
        events(qt, lambda: window.worker is None)
        events(qt, lambda: all(b.visibleRegion().contains(b.rect()) for b in (window.keyed_passthrough_button, window.keyed_continue_button)))
        assert window.steps.currentIndex() == 1
        assert window.keyed_passthrough_button.isVisible() and window.keyed_continue_button.isVisible()
        keyed_times = [frame_path(pipe.keyed, i).stat().st_mtime_ns for i in range(56)]
        def forbidden(*a, **k):
            raise AssertionError('Tracking or keying started during passthrough/resume preview')
        monkeypatch.setattr(Pipeline, 'ensure_roots', forbidden)
        monkeypatch.setattr('app.core.pipeline.chroma_key', forbidden)
        monkeypatch.setattr('app.ui.main_window.chroma_key', forbidden)
        window.keyed_passthrough_button.click()
        events(qt, lambda: window.worker is None and window.built)
        assert window.project.is_keyed_passthrough and window.steps.currentIndex() == 3
        assert window.project.layout.width == 96 and not window.project.root_keyframes
        assert window.steps.count() == 5 and window.keyed_passthrough_note.isVisible()
        assert all(window.steps.isTabEnabled(i) for i in (2, 3, 4))
        assert not window.parameter_panels[3].fields['motion_settings.enabled'].isEnabled()
        assert window.keyed_passthrough_note.isVisible()
        review = window.open_animation_preview()
        events(qt, lambda: review.worker is None and review.last_pixels is not None)
        assert np.array_equal(review.last_pixels, pipe.cache.read(frame_path(pipe.keyed, 0)))
        assert not review.viewer.root_visible and not review.overlay_controls['ground'].isEnabled()
        review.toggle_play()
        events(qt, lambda: review.index >= 3)
        review.toggle_play()
        review.fps.setCurrentIndex(review.fps.findData(12))
        assert review.timer.interval() == 83 and window.project.video.fps == 30
        review.select(27)
        events(qt, lambda: not review.worker and not review.pending)
        QTest.keyClick(review, Qt.Key.Key_Right)
        events(qt, lambda: not review.worker and not review.pending)
        assert review.index == 28
        for effect in (review.onion, review.ghost):
            effect.setChecked(True)
            events(qt, lambda: not review.worker and not review.pending)
            assert not np.array_equal(review.last_pixels, review.provider.get_final_frame(28))
            effect.setChecked(False)
            events(qt, lambda: not review.worker and not review.pending)
        review.close()
        events(qt, lambda: not window.review_windows)
        window.steps.setCurrentIndex(2)
        window.editor.alignment()
        assert window.viewer.interaction is None and window.anchor_resume_button.isVisible()
        window.anchor_resume_button.click()
        events(qt, lambda: window.preview_worker is None)
        assert not window.project.is_passthrough and window.steps.currentIndex() == 2
        assert all(window.steps.isTabEnabled(i) for i in range(5))
        assert window.keyed_ready and keyed_times == [frame_path(pipe.keyed, i).stat().st_mtime_ns for i in range(56)]
        assert window.last_error is None
    finally:
        close_window(qt, window)


def test_passthrough_presets_and_reopen_reuses_rgba(qt, keyed_video, tmp_path, monkeypatch):
    pipe, _ = keyed_video
    window = MainWindow(tmp_path / 'app.log')
    window.project, window.cache_dir = pipe.project, pipe.cache_dir
    window.project_file = tmp_path / 'workspace' / 'initial.aivsprite'
    window.cache_dir = cache_directory(pipe.project.project_id, window.project_file)
    shutil.copytree(pipe.cache_dir, window.cache_dir, dirs_exist_ok=True)
    window._loaded()
    window.show()
    try:
        window.start_keyed_passthrough()
        events(qt, lambda: window.built and window.worker is None)
        preset = window.passthrough_resolution
        assert [preset.itemData(i) for i in range(preset.count())] == ['native', 1536, 1024, 768, 512, 'custom']
        preset.setCurrentIndex(preset.findData(512))
        assert window.project.sprite_cell.canvas_mode == 'normalize_source'
        assert window.project.sprite_cell.target_width == window.project.sprite_cell.target_height == 512
        preset.setCurrentIndex(preset.findData('custom'))
        assert preset.currentData() == 'custom'
        window.parameter_panels[5].fields['sprite_cell.target_width'].setValue(128)
        window.parameter_panels[5].fields['sprite_cell.target_height'].setValue(96)
        window.build_sprites()
        events(qt, lambda: window.built and window.worker is None)
        provider = FinalFrameProvider(window.project, window.cache_dir)
        assert provider.get_final_frame(0).shape == (96, 128, 4)
        window.save_project(tmp_path / 'video.aivsprite')
        events(qt, lambda: window.worker is None)
        old = frame_path(window.cache_dir / 'keyed_frames', 0).stat().st_mtime_ns
        monkeypatch.setattr('app.core.pipeline.chroma_key', lambda *a: (_ for _ in ()).throw(AssertionError('Unexpected key')))
        window.open_project(tmp_path / 'video.aivsprite')
        events(qt, lambda: window.worker is None and window.built)
        assert window.project.processing_mode == 'keyed_passthrough' and window.steps.currentIndex() == 3
        assert frame_path(window.cache_dir / 'keyed_frames', 0).stat().st_mtime_ns == old
        assert np.array_equal(FinalFrameProvider(window.project, window.cache_dir).get_final_frame(0), provider.get_final_frame(0))
    finally:
        close_window(qt, window)


@pytest.mark.parametrize("canvas", [None, (128, 112)])
def test_sprite_build_without_root_offers_direct_route(qt, keyed_video, tmp_path, monkeypatch, canvas):
    from app.exporters.image_exporter import export_images
    from app.utils.rgba_image import read_rgba

    pipe, _ = keyed_video
    if canvas:
        pipe.project.project_canvas_width, pipe.project.project_canvas_height = canvas
        pipe.project.canvas_fit_mode = "center_crop_or_pad"
        pipe.ensure_key()
    window = MainWindow(tmp_path / "app.log")
    window.project, window.cache_dir = pipe.project, pipe.cache_dir
    window._loaded()
    window.show()
    try:
        window.steps.setCurrentIndex(3)
        events(qt)
        # Users may click the generic build control, without knowing about the
        # dedicated choice on the key page. This must not force root tracking.
        window.build_button.click()
        events(qt)
        assert window.steps.currentIndex() == 3
        assert window.sprite_direct_button.isVisible()
        assert not window.project.is_passthrough and not window.worker
        assert not window.project.root_keyframes
        window.sprite_continue_button.click()
        assert window.steps.currentIndex() == 2 and window.viewer.interaction == "root"
        window.build_button.click()
        events(qt)
        assert window.steps.currentIndex() == 3
        times = [frame_path(pipe.keyed, i).stat().st_mtime_ns for i in range(56)]
        def forbidden(*a, **k):
            raise AssertionError("Direct sprite build must reuse keyed pixels without root processing")
        for method in ("ensure_roots", "ensure_motion", "ensure_source_aligned"):
            monkeypatch.setattr(Pipeline, method, forbidden)
        monkeypatch.setattr("app.core.pipeline.chroma_key", forbidden)
        monkeypatch.setattr("app.ui.main_window.chroma_key", forbidden)
        window.sprite_direct_button.click()
        events(qt, lambda: window.worker is None and window.built)
        assert window.steps.currentIndex() == 3 and window.project.is_keyed_passthrough
        assert not window.sprite_direct_button.isVisible()
        assert (window.project.layout.width, window.project.layout.height) == (canvas or (96, 96))
        provider = FinalFrameProvider(window.project, window.cache_dir)
        export_images(Pipeline(window.project, window.cache_dir), tmp_path / "out", godot=True)
        for index in range(56):
            keyed = read_rgba(frame_path(pipe.keyed, index))
            assert np.array_equal(provider.get_final_frame(index), keyed)
            assert np.array_equal(read_rgba(tmp_path / "out/frames" / f"{index:04d}.png"), keyed)
        assert times == [frame_path(pipe.keyed, i).stat().st_mtime_ns for i in range(56)]
        assert window.last_error is None
    finally:
        close_window(qt, window)
