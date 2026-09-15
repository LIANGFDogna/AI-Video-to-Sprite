"""UI regression tests must never alter the user's language or remembered paths."""
import pytest

@pytest.fixture(autouse=True)
def isolated_app_settings(tmp_path,monkeypatch):
    import app.i18n.translator as translation
    import app.utils.path_memory as paths
    setting=tmp_path/'machine-settings.json'
    monkeypatch.setenv('AIVSPRITE_SETTINGS',str(setting))
    monkeypatch.setattr(translation,'_manager',translation.TranslationManager(setting))
    monkeypatch.setattr(paths,'WORK_CANDIDATES',(tmp_path/'work',))
