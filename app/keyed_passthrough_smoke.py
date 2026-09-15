"""Exercise the real video UI and frozen release, including returning to full processing."""
import json
import logging
from pathlib import Path
import tempfile
import time

import numpy as np
from PIL import Image
from PySide6.QtCore import QTimer

from app.core import pipeline as pipeline_module
from app.core.final_frame_provider import FinalFrameProvider
from app.models.project import Project
from app.ui import main_window as ui_module
from app.utils.paths import frame_path


def start_keyed_smoke(app, window, project_path, output=None):
    log = logging.getLogger("aivsprite.release")
    output = Path(output or tempfile.mkdtemp(prefix="aivsprite-keyed-review-")).resolve()
    output.mkdir(parents=True, exist_ok=True)
    state = {"phase": "open", "start": time.monotonic(), "review": None}
    original_key, original_preview_key = pipeline_module.chroma_key, ui_module.chroma_key
    timer = QTimer(window)
    timer.setInterval(35)
    window._failed = lambda message: setattr(window, "last_error", message)

    def finish(code):
        timer.stop()
        if window.worker:
            window.worker.cancel()
            window.worker.wait()
            app.processEvents()
        window.dirty = False
        window.close()
        pipeline_module.chroma_key, ui_module.chroma_key = original_key, original_preview_key
        app.exit(code)

    def forbid_key(*a, **kw):
        raise AssertionError("Keyed cache was unnecessarily reprocessed")

    def poll():
        try:
            if window.last_error:
                raise AssertionError(window.last_error)
            if time.monotonic() - state["start"] > 85:
                raise AssertionError("Keyed video UI smoke timed out")
            if window.worker:
                state.pop("ready_since", None)
                return
            # Let queued Qt layout / paint updates settle before visual assertions.
            ready = state.setdefault("ready_since", (state["phase"], time.monotonic()))
            if ready[0] != state["phase"]:
                state["ready_since"] = (state["phase"], time.monotonic())
                return
            if time.monotonic() - ready[1] < .2:
                return
            p = window.project
            phase = state["phase"]
            if phase == "open":
                state["roots"] = dict(p.root_keyframes)
                assert state["roots"]
                p.root_keyframes.clear()
                window.process_key()
                state["phase"] = "keyed"
            elif phase == "keyed":
                if window.preview_worker or window.preview_pending:
                    return
                assert window.keyed_ready and window.steps.currentIndex() == 1
                assert window.keyed_passthrough_button.isVisible() and window.keyed_continue_button.isVisible()
                assert all(b.visibleRegion().contains(b.rect()) for b in (window.keyed_passthrough_button, window.keyed_continue_button))
                window.grab().save(str(output / "keyed-choice.png"))
                state["keyed_times"] = [frame_path(window.cache_dir / "keyed_frames", i).stat().st_mtime_ns for i in range(p.video.frame_count)]
                pipeline_module.chroma_key = ui_module.chroma_key = forbid_key
                window.build_button.click()
                assert not p.is_passthrough and window.steps.currentIndex() == 3
                state["phase"] = "choose"
            elif phase == "choose":
                assert all(b.visibleRegion().contains(b.rect()) for b in (window.sprite_direct_button, window.sprite_continue_button))
                window.grab().save(str(output / "sprite-keyed-choice.png"))
                window.sprite_direct_button.click()
                state["phase"] = "native"
            elif phase == "native":
                assert window.built and p.is_keyed_passthrough and not p.root_keyframes
                provider = FinalFrameProvider(p, window.cache_dir)
                for i in range(len(provider)):
                    assert np.array_equal(provider.get_final_frame(i), provider.get_source_keyed_frame(i))
                assert all(f.correction == (0, 0) for f in p.tracking_results)
                window.grab().save(str(output / "keyed-native-sprite.png"))
                window.passthrough_resolution.setCurrentIndex(window.passthrough_resolution.findData(512))
                window.build_sprites()
                state["phase"] = "resized"
            elif phase == "resized":
                assert window.built and p.layout.width == p.layout.height == 512
                assert p.layout.normalize_scale[0] == p.layout.normalize_scale[1]
                window.grab().save(str(output / "keyed-resized-sprite.png"))
                state.update(review=window.open_animation_preview(), phase="preview")
            elif phase == "preview":
                review = state["review"]
                if review.worker or review.last_pixels is None:
                    return
                assert np.array_equal(review.last_pixels, review.provider.get_final_frame(0))
                assert not review.viewer.root_visible and review.viewer.character_profile is None
                review.grab().save(str(output / "keyed-animation-preview.png"))
                review.fps.setCurrentIndex(review.fps.findData(12))
                assert review.timer.interval() == 83 and p.video.fps == 24
                review.toggle_play()
                state["phase"] = "playing"
            elif phase == "playing":
                review = state["review"]
                if review.index < 3:
                    return
                review.toggle_play()
                window.export_to(output / "export", godot=True)
                state["phase"] = "exported"
            elif phase == "exported":
                assert window.last_export
                provider = state["review"].provider
                for i in range(len(provider)):
                    with Image.open(output / "export" / "frames" / f"{i:04d}.png") as frame:
                        assert np.array_equal(np.array(frame), provider.get_final_frame(i))
                with Image.open(output / "export" / "sprite_sheet.png") as sheet:
                    state["sheet_size"] = sheet.size
                    assert sheet.size == (8 * 512, ((len(provider)+7)//8) * 512)
                state["review"].close()
                window.save_project(output / "review.aivsprite")
                state["phase"] = "saved"
            elif phase == "saved":
                restored = Project.load(output / "review.aivsprite")
                assert restored.is_keyed_passthrough
                window.open_project(output / "review.aivsprite")
                state["phase"] = "reopened"
            elif phase == "reopened":
                if not window.built:
                    return
                assert p.is_keyed_passthrough and window.steps.currentIndex() == 3
                # Save-as copies files; capture timestamps at the new cache location.
                state["keyed_times"] = [frame_path(window.cache_dir / "keyed_frames", i).stat().st_mtime_ns for i in range(p.video.frame_count)]
                window.steps.setCurrentIndex(2)
                window.editor.alignment()
                assert window.anchor_resume_button.isVisible() and window.viewer.interaction is None
                window.anchor_resume_button.click()
                p.root_keyframes = state["roots"]
                window.build_sprites()
                state["phase"] = "full"
            elif phase == "full":
                assert window.built and not p.is_passthrough
                assert all(f.tracking_method != "passthrough" for f in p.tracking_results)
                assert state["keyed_times"] == [frame_path(window.cache_dir / "keyed_frames", i).stat().st_mtime_ns for i in range(p.video.frame_count)]
                report = dict(status="passed", frames=p.video.frame_count, fps=p.video.fps, sheet_size=state["sheet_size"],
                    sprite_entry_without_root=True, native_keyed_pixel_equal=True, preview_export_equal=True, full_processing_resumed_without_key=True,
                    project_mode_restored=True, dpr=window.devicePixelRatioF())
                (output / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
                log.info("Keyed passthrough smoke passed: %s output=%s", report, output)
                finish(0)
        except Exception:
            log.exception("Keyed passthrough smoke failed")
            finish(1)

    window.open_project(project_path)
    timer.timeout.connect(poll)
    timer.start()
    window._release_smoke_timer = timer
