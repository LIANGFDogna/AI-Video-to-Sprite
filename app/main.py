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
    parser.add_argument("--smoke-editor", type=Path, help="Validate the animation editor and three export workflows")
    parser.add_argument("--smoke-character-reference", type=Path, help="Validate locked character axes, whole-animation offsets and final export")
    parser.add_argument("--smoke-path-memory",type=Path,help="Validate file dialogs, persistent purpose paths and UI controls")
    parser.add_argument("--verify-path-memory",action="store_true",help="Second-process verification of saved path history")
    parser.add_argument("--smoke-groups",type=Path,help="Validate Group workspace, imports, exports and task isolation")
    parser.add_argument("--verify-groups",action="store_true",help="Verify saved Groups in a fresh process")
    parser.add_argument("--smoke-characters",type=Path,help="Validate Character templates, per-Character Reference and ownership moves")
    parser.add_argument("--verify-characters",action="store_true",help="Verify saved Characters in a fresh process")
    args = parser.parse_args()
    import os,tempfile,uuid
    if args.smoke_characters:
        os.environ["AIVSPRITE_SETTINGS"]=str(args.smoke_characters.resolve()/"machine-settings.json")
    elif args.smoke_groups:
        os.environ["AIVSPRITE_SETTINGS"]=str(args.smoke_groups.resolve()/"machine-settings.json")
    elif args.smoke_path_memory:
        os.environ['AIVSPRITE_SETTINGS']=str(args.smoke_path_memory.resolve()/'machine-settings.json')
    elif any((args.smoke_test,args.smoke_preview,args.smoke_workspace,args.smoke_keyed_passthrough,args.smoke_project_canvas,args.smoke_editor,args.smoke_character_reference)) and 'AIVSPRITE_SETTINGS' not in os.environ:
        os.environ['AIVSPRITE_SETTINGS']=str(Path(tempfile.gettempdir())/'AI Video to Sprite'/('smoke-settings-'+uuid.uuid4().hex+'.json'))
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
    if args.smoke_characters:
        from app.character_smoke import start_character_smoke
        start_character_smoke(app,window,args.smoke_characters,args.verify_characters)
    elif args.smoke_groups:
        from app.group_smoke import start_group_smoke
        start_group_smoke(app,window,args.smoke_groups,args.verify_groups)
    elif args.smoke_path_memory:
        from app.path_ui_smoke import start_path_smoke
        start_path_smoke(app,window,args.smoke_path_memory,args.verify_path_memory)
    elif args.smoke_character_reference:
        from app.character_reference_smoke import start_reference_smoke
        start_reference_smoke(app, window, args.smoke_character_reference)
    elif args.smoke_editor:
        from app.editor_smoke import start_editor_smoke
        start_editor_smoke(app, window, args.smoke_editor)
    elif args.smoke_project_canvas:
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
