"""Real 22-frame, 1536px, 24FPS import → final preview → PNG export acceptance."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
from dataclasses import asdict
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt, QPointF
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QCheckBox, QComboBox
from app.i18n import manager
from app.i18n.translator import install_qt_translation
from app.ui.main_window import MainWindow
from app.ui.dialogs import MessageBox
from app.utils.logging import configure_logging
from scripts.demo_video import make_demo


def run(output, language="zh_CN", project_path=None):
    output.mkdir(parents=True, exist_ok=True)
    os.environ["AIVSPRITE_SETTINGS"] = str(output / "app_settings.json")
    manager().set_language(language)
    app = QApplication.instance() or QApplication([])
    install_qt_translation(app)
    failures = []
    original_hook = sys.excepthook
    sys.excepthook = lambda kind, value, traceback: failures.append(str(value))
    original_critical = MessageBox.critical
    MessageBox.critical = lambda *args, **kwargs: failures.append(str(args[2]))
    window = MainWindow(configure_logging(output / "logs"))
    def wait(predicate, timeout=120):
        start = time.monotonic()
        while not predicate():
            app.processEvents()
            time.sleep(.008)
            if failures: raise AssertionError(failures)
            if window.last_error: raise AssertionError(window.last_error)
            if time.monotonic()-start > timeout: raise AssertionError("Timed out: "+window.status.text())
        app.processEvents()
        if failures: raise AssertionError(failures)
    def ready(review):
        wait(lambda: review.worker is None and not review.pending)
        assert review.last_pixels is not None and not review.stale
    try:
        window.show()
        app.processEvents()
        if project_path:
            window.open_project(project_path)
        else:
            video = output / "22帧_1536_24fps.mp4"
            roots = make_demo(video, count=22, size=1536, fps=24)
            window.import_video(video)
        wait(lambda: window.worker is None)
        assert window.project.video.frame_count == 22
        assert window.project.video.width == window.project.video.height == 1536
        assert window.project.video.fps == 24
        assert window.project.sprite_cell.canvas_mode == "normalize_source"
        if not project_path:
            window.process_key()
            wait(lambda: window.worker is None)
            wait(lambda: window._preview_frame_index == 0 and window.preview_worker is None)
            window._arm("root")
            point = window.viewer.mapFromScene(QPointF(*roots[0])*window.viewer.display_scale)
            QTest.mouseClick(window.viewer.viewport(), Qt.MouseButton.LeftButton, pos=point)
            assert 0 in window.project.root_keyframes
            preset = window.parameter_panels[3].fields["motion_settings.preset"]
            preset.setCurrentIndex(preset.findData("dash"))
            columns = window.parameter_panels[5].fields["export_settings.columns"]
            columns.setValue(10)
        window.build_sprites()
        print("Building 22 source-resolution frames", flush=True)
        wait(lambda: window.worker is None)
        assert window.built and not window.project.layout.clipped_frames
        assert window.project.layout.width == window.project.layout.height == 512
        window.grab().save(str(output / "sprite.png"))
        window.steps.setCurrentIndex(3)
        app.processEvents()
        window.motion_editor.fit_image()
        window.grab().save(str(output / "motion.png"))
        window.steps.setCurrentIndex(5)
        review = window.open_animation_preview()
        assert review is not None and not review.isModal()
        ready(review)
        assert review.fps.currentData() == "Source" and review.timer.interval() == 42
        export_calls = []
        real_export = window.choose_export
        window.choose_export = lambda *args: export_calls.append(args)
        QTest.mouseClick(review.export_button, Qt.MouseButton.LeftButton)
        window.choose_export = real_export
        assert export_calls == [("all", True)]
        assert np.array_equal(review.last_pixels, review.provider.get_final_frame(0))
        for key in ("root", "ground", "bounds", "canvas", "path"):
            review.overlay_controls[key].setChecked(True)
        review.zoom(1)
        assert review.viewer.transform().m11() == 1
        review.zoom(2)
        assert review.viewer.transform().m11() == 2
        review.zoom(None)
        review.toggle_play()
        started = time.monotonic()
        indices = set()
        while time.monotonic()-started < 1.25:
            app.processEvents()
            indices.add(review.index)
            time.sleep(.004)
        review.toggle_play()
        ready(review)
        assert len(indices) >= 18, f"Playback progressed through only {len(indices)} frames"
        assert len(review.provider) == 22
        review.step(1)
        ready(review)
        frame = review.index
        QTest.keyClick(review, Qt.Key.Key_Left)
        ready(review)
        assert review.index == max(0, frame-1)
        QTest.keyClick(review, Qt.Key.Key_End)
        ready(review)
        assert review.index == 21
        QTest.keyClick(review, Qt.Key.Key_Home)
        ready(review)
        assert review.index == 0
        review.fps.setCurrentIndex(review.fps.findData(12))
        assert review.timer.interval() == 83 and window.project.video.fps == 24
        review.fps.setCurrentIndex(review.fps.findData("Source"))
        review.seam.setChecked(True)
        ready(review)
        assert review.sequence() == [19, 20, 21, 0, 1, 2]
        review.seam.setChecked(False)
        for control in (review.onion, review.ghost):
            control.setChecked(True)
            review.select(10)
            ready(review)
            assert not np.array_equal(review.last_pixels, review.provider.get_final_frame(10))
            control.setChecked(False)
            ready(review)
        review.comparison.setCurrentIndex(1)
        ready(review)
        assert review.last_pixels.shape == (1536, 1536, 4)
        review.comparison.setCurrentIndex(0)
        ready(review)
        assert review.last_pixels.shape == (512, 512, 4)
        # Backgrounds, debug drawings and speed have no effect on provider/export pixels.
        review.background.setCurrentIndex(review.background.findData("White"))
        review.background.setCurrentIndex(review.background.findData("Checkerboard"))
        review.grab().save(str(output / "animation-preview.png"))
        if not project_path:
            window.save_project(output / "acceptance.aivsprite")
            wait(lambda: window.worker is None)
        destination = output / "export"
        window.export_to(destination, godot=True)
        wait(lambda: window.worker is None)
        assert window.export_notices and review.folder_button.isVisible()
        metadata = json.loads((destination / "animation.json").read_text(encoding="utf-8"))
        motion = json.loads((destination / "root_motion.json").read_text(encoding="utf-8"))
        assert metadata["cell_width"] == metadata["cell_height"] == 512
        assert metadata["columns"] == 10 and metadata["rows"] == 3
        assert motion["frames"][-1]["cumulative_x"] > 60
        for i in range(22):
            with Image.open(destination / "frames" / f"{i:04d}.png") as image:
                assert image.size == (512, 512)
                assert np.array_equal(review.provider.get_final_frame(i), np.array(image))
        with Image.open(destination / "sprite_sheet.png") as image:
            assert image.size == (5120, 1536) and image.getpixel((2000, 1200))[3] == 0
        ready(review)
        assert np.array_equal(review.last_pixels, review.provider.get_final_frame(review.index))
        # All controls remain inside their dialog at native Windows DPI scaling.
        for widget in [w for kind in (QPushButton, QCheckBox, QComboBox, QLabel) for w in review.findChildren(kind)]:
            if widget.isVisible():
                pos = widget.mapTo(review, widget.rect().topLeft())
                assert pos.x() >= 0 and pos.x()+widget.width() <= review.width()+1
        # Language is application state, never project data.
        before = json.dumps(asdict(window.project), sort_keys=True)
        old_information = MessageBox.information
        MessageBox.information = lambda *args: MessageBox.StandardButton.Ok
        window.language.setCurrentIndex(1 if language == "zh_CN" else 0)
        MessageBox.information = old_information
        assert json.dumps(asdict(window.project), sort_keys=True) == before
        assert json.loads((output / "app_settings.json").read_text())["language"] != language
        window._setting_changed("sprite_cell.target_width", 256)
        assert review.stale and not review.export_button.isEnabled()
        report = {"status": "passed", "language": language, "dpi_scale": os.environ.get("QT_SCALE_FACTOR", "system"),
            "frames": 22, "source_size": [1536, 1536], "cell": [512, 512], "sheet": [5120, 1536],
            "fps": 24, "distinct_frames_played_in_1_25s": len(indices), "preview_export_pixel_equal": True,
            "minimum_confidence": min(f.tracking_confidence for f in window.project.tracking_results)}
        (output / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report), flush=True)
    finally:
        if window.worker:
            window.worker.cancel()
            window.worker.wait()
            app.processEvents()
        window.dirty = False
        window.close()
        app.processEvents()
        MessageBox.critical = original_critical
        sys.excepthook = original_hook


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--language", default="zh_CN")
    parser.add_argument("--project", type=Path)
    args = parser.parse_args()
    run(args.output, args.language, args.project)
