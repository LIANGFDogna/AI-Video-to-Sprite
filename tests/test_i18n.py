import json
from app.i18n.translator import TranslationManager
from app.models.project import Project
from scripts.check_i18n import required_keys


def test_catalog_coverage_placeholders_and_persisted_language(tmp_path):
    path = tmp_path / "app_settings.json"
    tr = TranslationManager(path)
    assert tr.language == "zh_CN"
    tr.validate()
    assert required_keys() <= tr.catalogs["en_US"].keys()
    assert tr.t("Warnings: {count}", count=2) == "警告帧：2"
    tr.set_language("en_US", persist=True)
    assert TranslationManager(path).language == "en_US"
    assert tr.t("normalize_source") == "Normalize Source Canvas"
    path.write_text("broken", encoding="utf-8")
    assert TranslationManager(path).language == "zh_CN"


def test_old_project_default_compatibility_and_language_independence(tmp_path):
    p = Project()
    path = tmp_path / "legacy.aivsprite"
    p.save(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("motion_settings")
    for key in ("canvas_mode", "target_width", "target_height", "preserve_aspect_ratio"):
        data["sprite_cell"].pop(key)
    path.write_text(json.dumps(data), encoding="utf-8")
    legacy = Project.load(path)
    assert not legacy.motion_settings.enabled
    assert legacy.sprite_cell.canvas_mode == "auto_bounds"
    legacy.save(path)
    before = path.read_bytes()
    tr = TranslationManager(tmp_path / "settings.json")
    for lang in ("en_US", "zh_CN"):
        tr.set_language(lang)
        assert tr.t(legacy.alignment_mode)
        legacy.save(path)
        assert path.read_bytes() == before
    assert json.loads(before)["alignment_mode"] == "ROOT X + GROUND Y"
