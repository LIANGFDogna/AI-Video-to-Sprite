"""Native Qt: folder selection → 22 original cells → preview → PNG export, plus folder drop."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
import time
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QCoreApplication, QEvent, QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app.i18n import manager
from app.i18n.translator import install_qt_translation
from app.ui.dialogs import MessageBox, FileDialog
from app.ui.main_window import MainWindow
from app.models.character_profile import CharacterProfile
from app.models.project import Project
from app.utils.paths import frame_path
from app.utils.logging import configure_logging
from scripts.sequence_demo import make_sequence


def run(output, language):
    output.mkdir(parents=True, exist_ok=True)
    os.environ["AIVSPRITE_SETTINGS"] = str(output / "settings.json")
    manager().set_language(language)
    app = QApplication.instance() or QApplication([])
    install_qt_translation(app)
    failures = []
    original_hook, original_critical = sys.excepthook, MessageBox.critical
    original_directory = FileDialog.getExistingDirectory
    sys.excepthook = lambda kind, value, traceback: failures.append(str(value))
    MessageBox.critical = lambda *args, **kwargs: failures.append(str(args[2]))
    window = MainWindow(configure_logging(output / "logs"))
    def pump():
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        time.sleep(.008)
        if failures or window.last_error: raise AssertionError(failures or window.last_error)
    def wait(predicate, timeout=90):
        deadline = time.monotonic()+timeout
        while not predicate():
            pump()
            if time.monotonic()>deadline: raise AssertionError("Timed out: "+window.status.text())
        pump()
    def ready(review):
        wait(lambda: review.worker is None and not review.pending and review.last_pixels is not None)
        assert not review.stale
    try:
        folder = make_sequence(output / "idle")
        window.project.character_profile = CharacterProfile()  # Must be bypassed by passthrough.
        window.show()
        FileDialog.getExistingDirectory = lambda *a, **k: str(folder)
        QTest.mouseClick(window.import_sequence_button, Qt.MouseButton.LeftButton)
        wait(lambda: window.sequence_dialog is not None and window.worker is None)
        dialog = window.sequence_dialog
        assert dialog.aligned.isChecked() and dialog.fps.value() == 24
        assert len(dialog.scan.names) == 22 and dialog.scan.alpha == "RGBA"
        dialog.grab().save(str(output / "sequence-import.png"))
        QTest.mouseClick(dialog.import_button, Qt.MouseButton.LeftButton)
        wait(lambda: window.built and window.worker is None and window.sequence_dialog is None)
        p = window.project
        assert p.is_passthrough and not p.root_keyframes
        assert p.export_settings.animation_name == "idle"
        assert window.steps.currentIndex() == 5 and all(not window.steps.isTabEnabled(i) for i in range(1, 5))
        assert p.layout.normalize_scale == (1., 1.) and p.layout.width == p.layout.height == 512
        assert window.timeline.model.data(window.timeline.model.index(0, 1)) == manager().t("Skipped")
        window.parameter_panels[5].fields["export_settings.columns"].setValue(10)
        assert not window.built
        QTest.mouseClick(window.review_button, Qt.MouseButton.LeftButton)  # Builds automatically, no Root prompt.
        wait(lambda: window.worker is None and len(window.review_windows) == 1)
        review = window.review_windows[0]
        ready(review)
        assert review.viewer.character_profile is None and not review.viewer.root_visible
        assert not review.overlay_controls["root"].isEnabled()
        assert not review.folder_button.isVisible()
        with Image.open(folder / "0000.png") as im:
            assert np.array_equal(review.last_pixels, np.array(im))
        indices = set()
        review.toggle_play()
        start = time.monotonic()
        while time.monotonic()-start < 1.3:
            pump()
            indices.add(review.index)
        review.toggle_play()
        ready(review)
        assert len(indices) >= 18
        QTest.keyClick(review, Qt.Key.Key_End)
        ready(review)
        assert review.index == 21
        review.fps.setCurrentIndex(review.fps.findData(12))
        assert review.timer.interval() == 83 and window.project.sequence_fps == 24
        review.seam.setChecked(True)
        assert review.sequence() == [19, 20, 21, 0, 1, 2]
        review.seam.setChecked(False)
        for control in (review.onion, review.ghost):
            review.select(10)
            ready(review)
            control.setChecked(True)
            ready(review)
            assert not np.array_equal(review.last_pixels, review.provider.get_final_frame(10))
            control.setChecked(False)
            ready(review)
        review.comparison.setCurrentIndex(1)
        ready(review)
        assert np.array_equal(review.last_pixels, review.provider.get_final_frame(review.index))
        review.comparison.setCurrentIndex(0)
        ready(review)
        review.grab().save(str(output / "sequence-preview.png"))
        window.grab().save(str(output / "sequence-sprite.png"))
        paths = [frame_path(window.cache_dir / directory, i) for directory in ("raw_frames", "aligned_frames") for i in range(22)]
        times = [p.stat().st_mtime_ns for p in paths]
        window.parameter_panels[0].fields["sequence_fps"].setValue(18.5)
        assert review.stale and window.project.video.fps == 18.5
        review.close()
        wait(lambda: not window.review_windows)
        window.open_animation_preview()
        wait(lambda: window.worker is None and len(window.review_windows) == 1)
        review = window.review_windows[0]
        ready(review)
        assert [p.stat().st_mtime_ns for p in paths] == times
        window.save_project(output / "idle.aivsprite")
        wait(lambda: window.worker is None)
        loaded = Project.load(output / "idle.aivsprite")
        assert loaded.sequence_folder == str(folder) and loaded.sequence_fps == 18.5 and loaded.is_passthrough
        window.export_to(output / "export", godot=True)
        wait(lambda: window.worker is None)
        for i in range(22):
            with Image.open(output / "export/frames" / f"{i:04d}.png") as exported, Image.open(folder / f"{i:04d}.png") as source:
                assert np.array_equal(np.array(exported), np.array(source))
                assert np.array_equal(np.array(exported), review.provider.get_final_frame(i))
        with Image.open(output / "export/sprite_sheet.png") as sheet:
            assert sheet.size == (5120, 1536) and sheet.getpixel((5119, 1535))[3] == 0
        meta = json.loads((output / "export/animation.json").read_text())
        assert meta["fps"] == 18.5 and meta["root_tracked"] is False
        mixed = output / "mixed"
        mixed.mkdir()
        Image.fromarray(np.zeros((512, 512, 4), np.uint8)).save(mixed / "0.png")
        Image.fromarray(np.zeros((512, 600, 4), np.uint8)).save(mixed / "1.png")
        before = asdict(window.project)
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(mixed))])
        drag = QDragEnterEvent(QPoint(20, 20), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        app.sendEvent(window, drag)
        assert drag.isAccepted()
        drop = QDropEvent(QPointF(20, 20), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        app.sendEvent(window, drop)
        wait(lambda: window.sequence_dialog is not None and window.worker is None)
        dialog = window.sequence_dialog
        assert dialog.scan.mixed_sizes and not dialog.import_button.isEnabled()
        dialog.grab().save(str(output / "sequence-mixed-warning.png"))
        dialog.close()
        wait(lambda: window.sequence_dialog is None)
        assert asdict(window.project) == before
        window.import_sequence(mixed)
        wait(lambda: window.sequence_dialog is not None and window.worker is None)
        dialog = window.sequence_dialog
        dialog.size_policy.setCurrentIndex(1)
        assert dialog.import_button.isEnabled()
        QTest.mouseClick(dialog.import_button, Qt.MouseButton.LeftButton)
        wait(lambda: window.worker is None and window.built and window.project.video.frame_count == 2)
        assert window.project.layout.width == 600 and window.project.layout.height == 512
        report = {"status": "passed", "language": language, "dpi_scale": os.environ.get("QT_SCALE_FACTOR", "system"),
            "input_frames": 22, "cell": [512, 512], "sheet": [5120, 1536], "input_preview_export_pixel_equal": True,
            "character_profile_bypassed": True, "tracking_skipped": True, "fps_edits_keep_pixel_cache": True,
            "frames_played": len(indices), "folder_drop_and_mixed_size_choice": True}
        (output / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report), flush=True)
    finally:
        if window.worker:
            window.worker.cancel()
            window.worker.wait()
            app.processEvents()
        if window.sequence_dialog:
            window.sequence_dialog.close()
        window.dirty = False
        window.close()
        app.processEvents()
        FileDialog.getExistingDirectory = original_directory
        MessageBox.critical, sys.excepthook = original_critical, original_hook


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--language", default="zh_CN")
    args = parser.parse_args()
    run(args.output.resolve(), args.language)
