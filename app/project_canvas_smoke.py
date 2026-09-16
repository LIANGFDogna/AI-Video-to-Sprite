"""Actual Qt and frozen EXE acceptance for project canvas creation and mixed sources."""
import json
import logging
from pathlib import Path
import time

import numpy as np
from PIL import Image
from PySide6.QtCore import QTimer

from app.core.final_frame_provider import FinalFrameProvider
from app.models.project import Project
from app.utils.cache import save_rgba
from app.utils.rgba_image import read_rgba


def start_canvas_smoke(app, window, output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    state = dict(phase="new", start=time.monotonic(), review=None)
    log = logging.getLogger("aivsprite.release")
    timer = QTimer(window)
    timer.setInterval(40)
    window._failed = lambda message: setattr(window, "last_error", message)

    def expected(index):
        pixels = np.zeros((1536, 1536, 4), np.uint8)
        x, y = 468 + 10*index, 568 + 4*index
        pixels[y:y+100, x:x+80] = (230, 50, 80, 200)
        return pixels

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
                raise AssertionError("Project canvas smoke timed out")
            if window.worker:
                state.pop("ready", None)
                return
            ready = state.setdefault("ready", (state["phase"], time.monotonic()))
            if ready[0] != state["phase"]:
                state["ready"] = (state["phase"], time.monotonic())
                return
            if time.monotonic()-ready[1] < .25:
                return
            phase = state["phase"]
            if phase == "new":
                window.new_button.click()
                dialog = window.new_project_dialog
                dialog.name.setText("CanvasCharacter")
                dialog.directory.setText(str(output))
                dialog.canvas_preset.setCurrentIndex(dialog.canvas_preset.findData("1024x1536"))
                state["phase"] = "create"
            elif phase == "create":
                dialog = window.new_project_dialog
                assert (dialog.source_width.value(), dialog.source_height.value()) == (1024, 1536)
                assert dialog.create_button.visibleRegion().contains(dialog.create_button.rect())
                dialog.grab().save(str(output / "new-project-canvas.png"))
                dialog.canvas_preset.setCurrentIndex(dialog.canvas_preset.findData("1536x1536"))
                dialog.create_button.click()
                state["phase"] = "created"
            elif phase == "created":
                assert window.project.project_canvas == (1536, 1536)
                assert not window.project.character_profile and not window.project.root_keyframes
                folder = output / "mixed_sequence"
                folder.mkdir(exist_ok=True)
                for i, (w, h) in enumerate(((1024, 1536), (1920, 1536), (1536, 1024), (1536, 1920), (1920, 1080))):
                    pixels = np.zeros((h, w, 4), np.uint8)
                    x, y = w//2-300+10*i, h//2-200+4*i
                    pixels[y:y+100, x:x+80] = (230, 50, 80, 200)
                    save_rgba(folder / f'{i}.png', pixels)
                window.library_controller.new_group(name="Mixed")
                window.import_sequence(folder)
                state["phase"] = "import"
            elif phase == "import":
                dialog = window.sequence_dialog
                assert dialog is not None and dialog.import_button.isEnabled()
                assert dialog.import_button.visibleRegion().contains(dialog.import_button.rect())
                dialog.grab().save(str(output / "sequence-canvas-fit.png"))
                dialog.submit()
                state["phase"] = "built"
            elif phase == "built":
                if not window.built or window.sequence_dialog:
                    return
                p = window.project
                assert (p.video.width, p.video.height) == (1536, 1536)
                provider = FinalFrameProvider(p, window.cache_dir)
                for i in range(5):
                    assert np.array_equal(provider.get_final_frame(i), expected(i))
                window.steps.setCurrentIndex(0)
                window.select_frame(4)
                state["phase"] = "source_preview"
            elif phase == "source_preview":
                if window.preview_worker or window.preview_pending:
                    return
                assert "1920 × 1080" in window.project_canvas_info.text()
                window.grab().save(str(output / "import-canvas-preview.png"))
                state.update(review=window.open_animation_preview(), phase="preview")
                state["review"].select(4)
            elif phase == "preview":
                review = state["review"]
                if review.worker or review.last_pixels is None:
                    return
                assert np.array_equal(review.last_pixels, expected(4))
                review.grab().save(str(output / "final-canvas-preview.png"))
                window.export_to(output / "export", godot=True)
                state["phase"] = "export"
            elif phase == "export":
                assert window.last_export
                for i in range(5):
                    assert np.array_equal(read_rgba(output / 'export/frames' / f'{i:04d}.png'), expected(i))
                with Image.open(output / 'export/sprite_sheet.png') as sheet:
                    assert sheet.size == (12288, 1536)
                state["review"].close()
                window.save_project()
                state["phase"] = "saved"
            elif phase == "saved":
                path = window.project_file
                assert Project.load(path).project_canvas == (1536, 1536)
                window.open_project(path)
                state["phase"] = "reopened"
            elif phase == "reopened":
                if not window.built:
                    return
                assert np.array_equal(FinalFrameProvider(window.project, window.cache_dir).get_final_frame(4), expected(4))
                report = dict(status="passed", canvas=[1536, 1536], frames=5, mixed_dimensions=True,
                    preview_export_equal=True, reopened=True, dpr=window.devicePixelRatioF())
                (output / 'validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
                log.info("Project canvas smoke passed: %s output=%s", report, output)
                finish(0)
        except Exception:
            log.exception("Project canvas smoke failed")
            finish(1)

    timer.timeout.connect(poll)
    timer.start()
    window._release_smoke_timer = timer
