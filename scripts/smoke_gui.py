"""Exercise actual Qt widgets and workers from import to export; save UI evidence."""
import os
import sys
if sys.platform != "win32":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import time
import json
import faulthandler

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app.ui.dialogs import MessageBox as QMessageBox

from app.ui.main_window import MainWindow
from app.utils.logging import configure_logging
from scripts.demo_video import make_demo


def run(output: Path):
    faulthandler.dump_traceback_later(25, repeat=True)
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    failures = []
    original_hook = sys.excepthook
    sys.excepthook = lambda kind, value, traceback: failures.append(str(value))
    original_critical = QMessageBox.critical
    QMessageBox.critical = lambda *args, **kwargs: failures.append(str(args[2]))
    window = MainWindow(configure_logging(output / "logs"))
    def wait(predicate, timeout=40):
        start = time.monotonic()
        while not predicate():
            app.processEvents()
            # Sleep releases Python's GIL so image work in QThread can make progress.
            time.sleep(0.015)
            if failures:
                raise AssertionError(failures)
            if time.monotonic() - start > timeout:
                raise AssertionError(f"GUI wait timed out: {window.status.text()}")
        app.processEvents()
        if failures:
            raise AssertionError(failures)
    try:
        window.show()
        app.processEvents()
        video = output / "demo_green_screen.mp4"
        roots = make_demo(video)
        window.import_video(video)
        print("GUI: importing", flush=True)
        wait(lambda: window.worker is None)
        print("GUI: imported; waiting preview", flush=True)
        wait(lambda: window._preview_frame_index == 0 and window.preview_worker is None and not window.preview_timer.isActive())
        assert window.project.video.frame_count == 24
        print("GUI: preview ready", flush=True)
        # Real slider signal -> project -> live matte preview.
        field = window.parameter_panels[1].fields["chroma_key_settings.tolerance"]
        field.spin.setValue(0.24)
        wait(lambda: window.preview_worker is None and not window.preview_timer.isActive())
        assert window.project.chroma_key_settings.tolerance == 0.24
        for mode in ("Original", "Transparent", "Alpha Matte", "Checkerboard"):
            window.preview_mode.setCurrentIndex(window.preview_mode.findData(mode))
            wait(lambda: window.preview_worker is None and not window.preview_timer.isActive())
        print("GUI: preview modes checked", flush=True)
        QTest.mouseClick(window.process_button, Qt.MouseButton.LeftButton)
        wait(lambda: window.worker is None)
        print("GUI: keyed", flush=True)
        wait(lambda: window.preview_worker is None and not window.preview_timer.isActive())
        window._arm("root")
        app.processEvents()
        point = window.viewer.mapFromScene(QPointF(*roots[0]) * window.viewer.display_scale)
        QTest.mouseClick(window.viewer.viewport(), Qt.MouseButton.LeftButton, pos=point)
        assert 0 in window.project.root_keyframes
        # A later correction is persisted, deletable, and restarts tracking.
        window.select_frame(12)
        wait(lambda: window._preview_frame_index == 12 and window.preview_worker is None and not window.preview_timer.isActive())
        window._set_root(*roots[12])
        assert 12 in window.project.root_keyframes
        window.delete_root()
        assert 12 not in window.project.root_keyframes
        window._set_root(*roots[12])
        window.build_sprites()
        print("GUI: building", flush=True)
        wait(lambda: window.worker is None)
        assert window.built and not window.project.layout.clipped_frames
        assert len(window.project.tracking_results) == 24
        assert min(f.tracking_confidence for f in window.project.tracking_results) > .35
        app.processEvents()
        window.grab().save(str(output / "gui-sprite-sheet.png"))
        window.steps.setCurrentIndex(2)
        window.overlay_checks["path"].setChecked(True)
        window.select_frame(12)
        wait(lambda: window._preview_frame_index == 12 and window.preview_worker is None and not window.preview_timer.isActive())
        assert window.viewer.frame.root == window.project.tracking_results[12].root
        window.grab().save(str(output / "gui-anchor.png"))
        # Playback must present frames despite debouncing; extraction count stays intact.
        before = window.current_frame
        window.toggle_play()
        playback_start = time.monotonic()
        while time.monotonic() - playback_start < 0.5:
            app.processEvents()
            time.sleep(0.015)
        window.toggle_play()
        assert window.current_frame != before
        assert window.project.video.frame_count == 24
        window.save_project(output / "demo.aivsprite")
        wait(lambda: window.worker is None)
        assert not window.dirty and window.project_file.exists()
        window.open_project(output / "demo.aivsprite")
        wait(lambda: window.worker is None)
        assert set(window.project.root_keyframes) == {0, 12}
        window.build_sprites()
        wait(lambda: window.worker is None)
        window.export_to(output / "godot-export", godot=True)
        wait(lambda: window.worker is None)
        assert window.last_export is not None
        data = json.loads((window.last_export / "animation.json").read_text(encoding="utf-8"))
        assert data["frame_count"] == 24 and data["alignment_mode"] == "ROOT X + GROUND Y"
        window.dirty = False
        print(json.dumps({"status": "passed", "frames": 24, "cell": [window.project.layout.width, window.project.layout.height],
                          "confidence_min": min(f.tracking_confidence for f in window.project.tracking_results),
                          "output": str(output.resolve())}, indent=2))
    finally:
        print("GUI: cleanup", failures, flush=True)
        if window.worker:
            window.worker.cancel()
            window.worker.wait()
            app.processEvents()
        window.dirty = False
        window.close()
        app.processEvents()
        sys.excepthook = original_hook
        QMessageBox.critical = original_critical
        faulthandler.cancel_dump_traceback_later()


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".test-output") / time.strftime("gui-%Y%m%d-%H%M%S")
    run(target)
