"""Native Qt calibration, symmetric handles, multi-animation project and export acceptance."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import shutil
import sys
import time
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QCoreApplication, QEvent, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QComboBox, QDoubleSpinBox
from app.i18n import manager
from app.i18n.translator import install_qt_translation
from app.ui.main_window import MainWindow
from app.ui.dialogs import MessageBox
from app.utils.logging import configure_logging
from app.utils.paths import frame_path
from app.models.project import Project
from scripts.demo_video import make_demo


def run(output, language, new_project=False):
    output.mkdir(parents=True, exist_ok=True)
    os.environ["AIVSPRITE_SETTINGS"] = str(output / "settings.json")
    manager().set_language(language)
    app = QApplication.instance() or QApplication([])
    install_qt_translation(app)
    failures = []
    original_hook = sys.excepthook
    sys.excepthook = lambda kind, value, traceback: failures.append(str(value))
    original_critical = MessageBox.critical
    MessageBox.critical = lambda *args, **kwargs: failures.append(str(args[2]))
    window = MainWindow(configure_logging(output / "logs"))
    def pump():
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        time.sleep(.008)
        if failures: raise AssertionError(failures)
        if window.last_error: raise AssertionError(window.last_error)
    def wait(predicate, timeout=120):
        deadline = time.monotonic()+timeout
        while not predicate():
            pump()
            if time.monotonic() > deadline: raise AssertionError("Timed out: "+window.status.text())
        pump()
    def drag(view, start, end):
        viewport = view.viewport()
        QTest.mousePress(viewport, Qt.MouseButton.LeftButton, pos=view.mapFromScene(QPointF(*start)))
        QTest.mouseMove(viewport, view.mapFromScene(QPointF(*end)))
        QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=view.mapFromScene(QPointF(*end)))
        pump()
    try:
        idle = output / "Idle.mp4"
        make_demo(idle, count=8, size=320, fps=24)
        window.show()
        if new_project:
            window.new_button.click()
            dialog = window.new_project_dialog
            dialog.name.setText("MainCharacter")
            dialog.directory.setText(str(output.resolve()))
            dialog.create_button.click()
            wait(lambda: window.new_project_dialog is None)
            assert window.project.source_canvas == (1536, 1536)
            assert window.project.character_profile is None and not window.project.root_keyframes
        window.import_video(idle)
        wait(lambda: window.worker is None)
        idle_id = window.project.animation_id
        if new_project:
            assert window.project.project_name == "MainCharacter" and window.project_file.is_file()
        window.steps.setCurrentIndex(2)
        window.open_character_space()
        wait(lambda: window.worker is None and window.character_editor is not None)
        editor = window.character_editor
        assert not editor.isModal() and editor.calibrating
        editor.view.fit_image()
        fixed = (editor.profile.ground_origin, editor.profile.character_scale)
        placement = editor.view.placement
        drag(editor.view, (260, 360), (264, 360))
        assert editor.view.placement[0] > placement[0]
        assert not editor.save_button.isEnabled()
        assert (editor.profile.ground_origin, editor.profile.character_scale) == fixed
        QTest.mouseClick(editor.pick_button, Qt.MouseButton.LeftButton)
        # An off-axis click must still snap to the exact project Y Axis.
        QTest.mouseClick(editor.view.viewport(), Qt.MouseButton.LeftButton,
            pos=editor.view.mapFromScene(QPointF(270, editor.profile.canonical_root[1])))
        pump()
        assert editor.root_set and editor.save_button.isEnabled()
        assert editor.profile.canonical_root[0] == editor.profile.ground_origin[0] == 256.
        canonical = editor.profile.canonical_root
        for edge, delta in ((0, -18), (2, 22)):
            old = asdict(editor.profile)
            box = editor.profile.reference_box
            x, y = box[edge], (box[1]+box[3])/2
            drag(editor.view, (x, y), (x+delta, y))
            assert editor.profile.reference_box_half_width > old["reference_box_half_width"]
            current = asdict(editor.profile)
            old.pop("reference_box_half_width")
            current.pop("reference_box_half_width")
            assert current == old
            l, _, r, _ = editor.profile.reference_box
            assert (l+r)/2 == 256.
        # Exercise translated widgets at native DPI, including all calibration controls.
        for widget in [w for kind in (QPushButton, QComboBox, QDoubleSpinBox, QLabel) for w in editor.findChildren(kind)]:
            if widget.isVisible():
                pos = widget.mapTo(editor, widget.rect().topLeft())
                assert 0 <= pos.x() and pos.x()+widget.width() <= editor.width()+1
        editor.grab().save(str(output / "character-calibration.png"))
        source_root = editor.source_root()
        QTest.mouseClick(editor.save_button, Qt.MouseButton.LeftButton)
        wait(lambda: window.character_editor is None)
        assert window.project.character_profile.canonical_root == canonical
        window.build_sprites()
        wait(lambda: window.worker is None)
        assert window.built and all(f.cell_root == canonical for f in window.project.tracking_results)
        assert not window.project.layout.clipped_frames
        pixels = [frame_path(window.cache_dir / "aligned_frames", i) for i in range(8)]
        before = [(p.read_bytes(), p.stat().st_mtime_ns) for p in pixels]
        window.open_character_space()
        wait(lambda: window.worker is None and window.character_editor is not None)
        editor = window.character_editor
        assert not editor.calibrating and not editor.pick_button.isEnabled()
        editor.width_spin.setValue(50)
        QTest.mouseClick(editor.save_button, Qt.MouseButton.LeftButton)
        wait(lambda: window.character_editor is None)
        assert any("Outside Character Reference Box" in f.warnings for f in window.project.tracking_results)
        assert before == [(p.read_bytes(), p.stat().st_mtime_ns) for p in pixels]
        assert window.built
        window.open_character_space()
        wait(lambda: window.worker is None and window.character_editor is not None)
        editor = window.character_editor
        editor.width_spin.setValue(512)
        QTest.mouseClick(editor.save_button, Qt.MouseButton.LeftButton)
        wait(lambda: window.character_editor is None)
        assert window.project.character_profile.reference_box_half_width == 256
        # A wider box clears horizontal overflow; real pixels below Ground may still warn.
        for f in window.project.tracking_results:
            p = window.project.character_profile
            l, top, r, bottom = f.bbox
            vertical_overflow = top*p.character_scale+f.offset[1] < -1e-6 or (bottom-1)*p.character_scale+f.offset[1] > p.ground_origin[1]+1e-6
            assert ("Outside Character Reference Box" in f.warnings) == vertical_overflow
        assert before == [(p.read_bytes(), p.stat().st_mtime_ns) for p in pixels]
        shared = asdict(window.project.character_profile)
        for name in ("Run", "Ground Attack", "Jump"):
            video = output / (name+".mp4")
            shutil.copy2(idle, video)
            window.import_video(video)
            wait(lambda: window.worker is None)
            assert asdict(window.project.character_profile) == shared
            assert not window.project.root_keyframes
            window.steps.setCurrentIndex(2)
            wait(lambda: window._preview_frame_index == 0 and window.preview_worker is None)
            # A new source detection seed is distinct from the immutable canonical point.
            window._set_root(*source_root)
            window.build_sprites()
            wait(lambda: window.worker is None)
            assert window.built and all(f.cell_root == canonical for f in window.project.tracking_results)
            assert window.project.tracking_results[-1].root_motion[0] > 8
        assert window.animation_selector.count() == 4
        window.animation_selector.setCurrentIndex(window.animation_selector.findData(idle_id))
        wait(lambda: window.worker is None)
        assert Path(window.project.source_video).stem == "Idle"
        assert asdict(window.project.character_profile) == shared
        window.build_sprites()
        wait(lambda: window.worker is None)
        review = window.open_animation_preview()
        wait(lambda: review.worker is None and not review.pending)
        assert review.viewer.character_profile.canonical_root == canonical
        review.grab().save(str(output / "character-preview.png"))
        window.save_project(output / "character.aivsprite")
        wait(lambda: window.worker is None)
        restored = Project.load(output / "character.aivsprite")
        if new_project:
            assert restored.project_name == "MainCharacter" and restored.source_canvas == (1536, 1536)
            assert restored.default_fps == 24 and restored.output_canvas == (512, 512)
        assert len(restored.animations) == 3 and asdict(restored.character_profile) == shared
        assert all(restored.select_animation(key).character_profile.canonical_root == canonical for key in restored.animations)
        window.export_to(output / "export", godot=True)
        wait(lambda: window.worker is None)
        metadata = json.loads((output / "export/animation.json").read_text(encoding="utf-8"))
        assert all(f["root"] == list(canonical) for f in metadata["frames"])
        for i in range(8):
            with Image.open(output / "export/frames" / f"{i:04d}.png") as image:
                assert image.size == (512, 512)
                assert np.array_equal(np.array(image), review.provider.get_final_frame(i))
        report = {"status": "passed", "language": language, "new_project": new_project, "dpi_scale": os.environ.get("QT_SCALE_FACTOR", "system"),
            "canonical_root": canonical, "y_axis_x": 256., "shared_animations": 4, "symmetric_handles": True,
            "reference_edit_preserves_png_bytes_and_mtime": True, "preview_export_pixel_equal": True}
        (output / "validation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report), flush=True)
    finally:
        if window.worker:
            window.worker.cancel()
            window.worker.wait()
            app.processEvents()
        if window.character_editor:
            window.character_editor.close()
        window.dirty = False
        window.close()
        app.processEvents()
        MessageBox.critical = original_critical
        sys.excepthook = original_hook


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--language", default="zh_CN")
    parser.add_argument("--new-project", action="store_true")
    args = parser.parse_args()
    run(args.output.resolve(), args.language, args.new_project)
