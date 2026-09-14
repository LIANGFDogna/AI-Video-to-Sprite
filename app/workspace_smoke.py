"""Frozen-app acceptance: create project, custom picker, RGBA16, preview, export."""
import logging
from pathlib import Path
import time

import numpy as np
from PIL import Image
from PySide6.QtCore import QTimer

from app.models.project import Project
from app.ui.folder_picker import FolderPickerDialog
from app.utils.cache import save_rgba


def start_workspace_smoke(app, window, output):
    log = logging.getLogger("aivsprite.release")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    state = {"phase": "new", "start": time.monotonic(), "source": None, "review": None, "picker": None}
    timer = QTimer(window)
    timer.setInterval(35)
    window._failed = lambda message: setattr(window, "last_error", message)

    def finish(code):
        timer.stop()
        if window.worker:
            window.worker.cancel()
            window.worker.wait()
            app.processEvents()
        if state["picker"]:
            state["picker"].reject()
        window.dirty = False
        window.close()
        app.exit(code)

    def poll():
        try:
            if window.last_error:
                raise AssertionError(window.last_error)
            if time.monotonic() - state["start"] > 85:
                raise AssertionError("Packaged workspace smoke timed out")
            if window.worker:
                return
            if state["phase"] == "new":
                window.new_button.click()
                dialog = window.new_project_dialog
                assert dialog is not None and not dialog.isModal()
                dialog.name.setText("MainCharacter")
                dialog.directory.setText(str(output))
                dialog.canvas_preset.setCurrentIndex(dialog.canvas_preset.findData("512x512"))
                dialog.create_button.click()
                state["phase"] = "created"
            elif state["phase"] == "created":
                if window.new_project_dialog:
                    return
                p = Project.load(window.project_file)
                assert p.project_name == "MainCharacter" and p.project_canvas == (512, 512)
                assert p.character_profile is None and not p.root_keyframes
                assert window.views.currentWidget() is window.start_page
                folder = window.project_file.parent / "sequences" / "RGBA16"
                folder.mkdir()
                source = np.zeros((512, 512, 4), np.uint16)
                source[..., :3] = (12345, 40000, 65000)
                source[75:440, 130:285] = (50000, 12000, 20000, 37000)
                source[0, 0] = (257, 32768, 65535, 128)
                for i in range(22):
                    save_rgba(folder / f"{i:04d}.png", source)
                state.update(source=source, folder=folder)
                picker = FolderPickerDialog(window, path=str(folder), sequence=True)
                picker.show()
                state.update(picker=picker, phase="picker")
            elif state["phase"] == "picker":
                picker = state["picker"]
                if picker.worker or picker.hint_pending:
                    return
                assert "16-bit/channel" in picker.hint.text()
                picker.select_button.click()
                assert picker.selected_folder == str(state["folder"])
                window.import_sequence(state["folder"])
                state["phase"] = "sequence"
            elif state["phase"] == "sequence":
                dialog = window.sequence_dialog
                if dialog is None:
                    return
                assert "16-bit/channel" in dialog.format_info.text() and "8-bit/channel" in dialog.format_info.text()
                dialog.submit()
                state["phase"] = "build"
            elif state["phase"] == "build":
                if not window.built or window.sequence_dialog:
                    return
                assert window.project.project_name == "MainCharacter" and window.project.is_passthrough
                assert window.project.sequence_formats[0]["bits_per_pixel"] == 64
                window.project.export_settings.columns = 10
                window.build_sprites()
                state["phase"] = "preview_open"
            elif state["phase"] == "preview_open":
                review = window.open_animation_preview()
                state.update(review=review, phase="preview")
            elif state["phase"] == "preview":
                review = state["review"]
                if review.worker or review.last_pixels is None:
                    return
                expected = np.floor(state["source"].astype(np.float64) / 257 + .5).astype(np.uint8)
                assert np.array_equal(review.last_pixels, expected)
                state["expected"] = expected
                review.toggle_play()
                state["phase"] = "play"
            elif state["phase"] == "play":
                if state["review"].index < 3:
                    return
                state["review"].toggle_play()
                window.export_to(window.project_file.parent / "exports" / "reviewed", godot=True)
                state["phase"] = "export"
            elif state["phase"] == "export":
                assert window.last_export
                for index in range(22):
                    with Image.open(window.last_export / "frames" / f"{index:04d}.png") as frame:
                        assert np.array_equal(np.array(frame), state["expected"])
                with Image.open(window.last_export / "sprite_sheet.png") as sheet:
                    assert sheet.size == (5120, 1536)
                window.save_project()
                state["phase"] = "saved"
            elif state["phase"] == "saved":
                restored = Project.load(window.project_file)
                assert restored.project_name == "MainCharacter" and restored.sequence_formats[0]["bits_per_channel"] == 16
                assert not restored.character_profile and restored.is_passthrough
                log.info("Packaged workspace smoke passed: new_project=True folder_picker=True frames=22 source=RGBA16 final=RGBA8 preview_export_equal=True sheet=5120x1536 saved=True")
                finish(0)
        except Exception:
            log.exception("Packaged workspace smoke failed")
            finish(1)

    timer.timeout.connect(poll)
    timer.start()
    window._release_smoke_timer = timer
