"""CLI-only validation for the frozen Windows distribution, including Qt workers."""
import logging
import time
import numpy as np
from PySide6.QtCore import QTimer
from app.i18n import manager


def start_preview_smoke(app, window, project_path):
    log = logging.getLogger("aivsprite.release")
    state = {"phase": "open", "start": time.monotonic(), "review": None}
    timer = QTimer(window)
    timer.setInterval(30)
    # Automated failures must not block on interactive message boxes.
    window._failed = lambda message: setattr(window, "last_error", message)

    def finish(code):
        timer.stop()
        if window.worker:
            window.worker.cancel()
            window.worker.wait()
            app.processEvents()
        window.dirty = False
        window.close()
        app.exit(code)

    def poll():
        try:
            if window.last_error:
                raise AssertionError(window.last_error)
            if time.monotonic()-state["start"] > 85:
                raise AssertionError("Packaged preview timed out")
            if window.worker:
                return
            if state["phase"] == "open":
                if not window.built:
                    window.build_sprites()
                state["phase"] = "build"
            elif state["phase"] == "build":
                assert window.built
                if window.project.character_profile and not window.project.is_passthrough:
                    profile = window.project.character_profile
                    assert profile.canonical_root[0] == profile.ground_origin[0]
                    assert all(f.cell_root == profile.canonical_root for f in window.project.tracking_results)
                review = window.open_animation_preview()
                assert review is not None and not review.isModal()
                state.update(phase="preview", review=review)
            elif state["phase"] == "preview":
                review = state["review"]
                if review.worker or review.last_pixels is None:
                    return
                assert not review.stale
                assert np.array_equal(review.last_pixels, review.provider.get_final_frame(0))
                if window.project.is_keyed_passthrough:
                    p = window.project
                    if p.sprite_cell.canvas_mode == "source_canvas":
                        for i in range(len(review.provider)):
                            assert np.array_equal(review.provider.get_source_keyed_frame(i), review.provider.get_final_frame(i))
                    assert not review.viewer.root_visible and review.viewer.character_profile is None
                    log.info("Packaged keyed passthrough passed: frames=%s keyed_final_equal=True tracking_skipped=True", p.video.frame_count)
                elif window.project.is_passthrough:
                    from app.core.frame_sequence import read_sequence_frame
                    from app.utils.rgba_image import to_rgba8
                    from pathlib import Path
                    p = window.project
                    assert all(f.tracking_method == "passthrough" for f in p.tracking_results)
                    if p.sprite_cell.canvas_mode == "source_canvas":
                        for i, name in enumerate(p.sequence_files):
                            source = read_sequence_frame(Path(p.sequence_folder) / name, (p.video.width, p.video.height))
                            assert np.array_equal(to_rgba8(source), review.provider.get_final_frame(i))
                    assert not review.viewer.root_visible and review.viewer.character_profile is None
                    log.info("Packaged sequence smoke passed: frames=%s input_final_pixel_equal=True tracking_skipped=True", len(p.sequence_files))
                assert manager().language == "zh_CN" and window.import_button.text() == "导入视频"
                review.toggle_play()
                state["phase"] = "playing"
            elif state["phase"] == "playing":
                review = state["review"]
                if review.index < 3 or review.worker:
                    return
                log.info("Packaged preview smoke passed: language=%s frames=%s cell=%sx%s fps=%s pixel_match=True",
                    manager().language, len(review.provider), window.project.layout.width, window.project.layout.height, window.project.video.fps)
                if window.project.character_profile and not window.project.is_passthrough:
                    review.toggle_play()
                    window.open_character_space()
                    state["phase"] = "reference"
                else:
                    finish(0)
            elif state["phase"] == "reference":
                editor = window.character_editor
                if editor is None:
                    return
                from dataclasses import replace
                original = editor.profile
                editor.width_spin.setValue(original.reference_box_half_width*2+16)
                assert np.isclose(editor.profile.reference_box_half_width-original.reference_box_half_width, 8, atol=.005)
                assert editor.profile == replace(original, reference_box_half_width=editor.width_spin.value()/2)
                assert not editor.calibrating
                editor.close()
                log.info("Packaged Character Space smoke passed: canonical_root=%s y_axis=%s width_only=True",
                    original.canonical_root, original.ground_origin[0])
                finish(0)
        except Exception:
            log.exception("Packaged preview smoke failed")
            finish(1)

    window.open_project(project_path)
    timer.timeout.connect(poll)
    timer.start()
    window._release_smoke_timer = timer
