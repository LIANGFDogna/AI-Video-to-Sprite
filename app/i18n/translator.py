"""JSON translation catalog with stable English message keys and named placeholders."""
import json
import logging
import os
from pathlib import Path
from string import Formatter

log = logging.getLogger("aivsprite.i18n")
LANGUAGES = {"zh_CN": "简体中文", "en_US": "English"}


class TranslationManager:
    def __init__(self, settings_path=None):
        self.settings_path = Path(settings_path) if settings_path else Path(os.environ.get("AIVSPRITE_SETTINGS", str(Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "AI Video to Sprite" / "app_settings.json")))
        base = Path(__file__).parent
        self.catalogs = {code: json.loads((base / f"{code}.json").read_text(encoding="utf-8")) for code in LANGUAGES}
        self.language = "zh_CN"
        self.reload()

    def reload(self):
        try:
            code = json.loads(self.settings_path.read_text(encoding="utf-8")).get("language", "zh_CN")
            self.language = code if code in LANGUAGES else "zh_CN"
        except (OSError, ValueError):
            self.language = "zh_CN"

    def save_language(self, language):
        if language not in LANGUAGES:
            raise ValueError("Unsupported language")
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.settings_path.with_suffix(".tmp")
        temp.write_text(json.dumps({"language": language}, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.settings_path)

    def set_language(self, language, persist=False):
        if language not in LANGUAGES:
            raise ValueError("Unsupported language")
        if persist:
            self.save_language(language)
        self.language = language

    def t(self, key, **values):
        if not isinstance(key, str):
            return str(key)
        message = self.catalogs[self.language].get(key)
        if message is None:
            # Technical numeric values and already translated UI strings are allowed.
            message = key
            if key and any(c.isalpha() for c in key) and key.isascii():
                log.debug("Uncatalogued translation key: %s", key)
        return message.format(**values) if values else message

    def validate(self):
        a, b = self.catalogs["zh_CN"], self.catalogs["en_US"]
        if a.keys() != b.keys():
            raise ValueError("Language catalog keys differ")
        for key in a:
            fields = lambda text: {field for _, field, _, _ in Formatter().parse(text) if field is not None}
            if fields(a[key]) != fields(b[key]):
                raise ValueError(f"Translation placeholders differ: {key}")


_manager = None


def manager():
    global _manager
    if _manager is None:
        _manager = TranslationManager()
    return _manager


def t(key, **values):
    return manager().t(key, **values)


def install_qt_translation(app):
    from PySide6.QtCore import QTranslator, QLibraryInfo
    translator = QTranslator(app)
    if manager().language == "zh_CN" and translator.load("qtbase_zh_CN", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)
    app._ui_translator = translator


def translate_error(message):
    message = str(message)
    if message in manager().catalogs["en_US"]:
        return t(message)
    if "was not found. Install FFmpeg" in message:
        return t("FFmpeg or ffprobe is missing. Install FFmpeg and add its bin folder to PATH, then retry.")
    if message.startswith("FRAME CLIPPING DETECTED"):
        return t("Content exceeds the sprite cell. Use AUTO or a larger canvas, or explicitly accept clipping.")
    if "Source video is missing" in message:
        return t("The source video is missing. Open the project and locate its source file.")
    return t("Processing failed. Check Diagnostics for technical details.")
