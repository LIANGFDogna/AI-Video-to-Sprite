from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from app.ui.dialogs import MessageBox as QMessageBox
from app.i18n import t, translate_error
from app.i18n.translator import install_qt_translation

from app.ui.main_window import MainWindow
from app.utils.logging import configure_logging


def main() -> int:
    parser = argparse.ArgumentParser(description="AI Video to Sprite desktop application")
    parser.add_argument("file", nargs="?", help="Video, frame folder or .aivsprite project to open")
    parser.add_argument("--smoke-test", action="store_true", help="Launch Qt, initialize the window, then quit")
    parser.add_argument("--smoke-preview", type=Path, help="Validate a project build and final animation preview, then quit")
    parser.add_argument("--smoke-workspace", type=Path, help="Validate project creation, folder picker and RGBA16 export in the given test directory")
    parser.add_argument("--smoke-keyed-passthrough", type=Path, help="Validate a video's key, passthrough, preview, export and full-mode resume")
    parser.add_argument("--smoke-output", type=Path, help="Output folder for keyed passthrough validation")
    parser.add_argument("--smoke-project-canvas", type=Path, help="Validate project canvas creation, mixed inputs, preview and export")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("AI Video to Sprite")
    app.setOrganizationName("AI Video to Sprite")
    install_qt_translation(app)
    try:
        log_path = configure_logging(Path.cwd() / "logs")
    except OSError:
        log_path = configure_logging()
    def exception_hook(kind, value, traceback):
        logging.getLogger("aivsprite").error("Unhandled UI exception", exc_info=(kind, value, traceback))
        QMessageBox.critical(None, "AI Video to Sprite", translate_error(str(value))+"\n\n"+t("Log: {path}", path=log_path))
    sys.excepthook = exception_hook
    window = MainWindow(log_path)
    window.show()
    if args.smoke_project_canvas:
        from app.project_canvas_smoke import start_canvas_smoke
        start_canvas_smoke(app, window, args.smoke_project_canvas)
    elif args.smoke_keyed_passthrough:
        from app.keyed_passthrough_smoke import start_keyed_smoke
        start_keyed_smoke(app, window, args.smoke_keyed_passthrough, args.smoke_output)
    elif args.smoke_workspace:
        from app.workspace_smoke import start_workspace_smoke
        start_workspace_smoke(app, window, args.smoke_workspace)
    elif args.smoke_preview:
        from app.preview_smoke import start_preview_smoke
        start_preview_smoke(app, window, args.smoke_preview)
    elif args.smoke_test:
        QTimer.singleShot(1200, window.close)
    elif args.file:
        path = Path(args.file)
        QTimer.singleShot(0, lambda: window.import_sequence(path) if path.is_dir() else window.open_project(path) if path.suffix.lower() == ".aivsprite" else window.import_video(path))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
