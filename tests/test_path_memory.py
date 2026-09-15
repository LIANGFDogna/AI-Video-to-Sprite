import json
from pathlib import Path
import pytest
from app.utils.path_memory import PathMemoryService,WORK_ROOT,PATH_KEYS
from app.utils.app_settings import AppSettings
from app.i18n.translator import TranslationManager


def memory(tmp_path):
    return PathMemoryService(tmp_path/'settings.json',work_candidates=[tmp_path/'work'],home=tmp_path)


def test_product_root_and_auto_creation(tmp_path):
    assert str(WORK_ROOT)==str(Path('E:/AI Video to Sprite/work'))
    service=memory(tmp_path)
    assert not (tmp_path/'work').exists()
    assert service.initial('project_create')==tmp_path/'work'
    assert (tmp_path/'work').is_dir()
    assert not (tmp_path/'settings.json').exists()


@pytest.mark.parametrize('blocked_count',[0,1,2,3])
def test_work_root_e_d_c_then_home(tmp_path,monkeypatch,blocked_count):
    roots=[tmp_path/f'{drive}_drive/work' for drive in 'EDC']
    original=Path.mkdir
    def mkdir(path,*a,**kw):
        if any(path==root for root in roots[:blocked_count]):raise PermissionError('unavailable drive')
        return original(path,*a,**kw)
    monkeypatch.setattr(Path,'mkdir',mkdir)
    assert PathMemoryService(tmp_path/'settings.json',roots,tmp_path).work_root==(roots[blocked_count] if blocked_count<3 else tmp_path)


@pytest.mark.parametrize('key',['video_import','image_import','image_sequence_import','folder_import','sprite_sheet_export','png_export','frame_export','project_open','project_save','project_export'])
def test_purpose_history_independent_and_reloaded(tmp_path,key):
    service=memory(tmp_path);a=tmp_path/'中文 素材 A';a.mkdir();b=tmp_path/'Exports B';b.mkdir()
    assert service.remember(key,a)
    other='generic_open';assert service.remember(other,b)
    again=memory(tmp_path)
    assert again.initial(key)==a and again.initial(other)==b
    assert again.state['last_location']==str(b)
    assert 'path_state' not in __import__('dataclasses').asdict(__import__('app.models.project',fromlist=['Project']).Project())


def test_new_project_remembers_success_parent_only_and_ignores_imports(tmp_path):
    service=memory(tmp_path);a=tmp_path/'Project Parent';a.mkdir();b=tmp_path/'Video';b.mkdir()
    service.remember('video_import',b)
    assert service.initial('project_create')==tmp_path/'work'
    service.remember('project_create',a);service.remember('video_import',b)
    assert memory(tmp_path).initial('project_create')==a
    a.rmdir()
    assert memory(tmp_path).initial('project_create')==tmp_path/'work'


def test_missing_directory_ancestor_and_unavailable_drive_fallback(tmp_path):
    service=memory(tmp_path);project=tmp_path/'Project';project.mkdir()
    service.settings.update({'path_state':{'recent_paths':{'video_import':str(tmp_path/'missing/deep')},'last_location':''}})
    assert service.initial('video_import',project)==tmp_path
    service.settings.update({'path_state':{'recent_paths':{'video_import':'Z:/definitely_missing_xyz/deep'},'last_location':'Z:/missing'}})
    assert service.initial('video_import',project)==project
    assert service.initial('image_import')==tmp_path/'work'


def test_cwd_dist_never_default_and_malformed_state_safe(tmp_path,monkeypatch):
    dist=tmp_path/'dist/AI Video to Sprite';dist.mkdir(parents=True);monkeypatch.chdir(dist)
    service=memory(tmp_path)
    assert service.initial('video_import')==tmp_path/'work'
    service.settings.update({'path_state':{'recent_paths':{'video_import':{'bad':True}},'last_location':123}})
    assert service.initial('video_import',dist)==tmp_path/'work'


def test_settings_language_and_history_merge_without_data_loss(tmp_path):
    service=memory(tmp_path);service.remember('image_import',tmp_path)
    TranslationManager(tmp_path/'settings.json').save_language('en_US')
    assert service.initial('image_import')==tmp_path
    service.remember('png_export',tmp_path)
    assert AppSettings(tmp_path/'settings.json').read()['language']=='en_US'


def test_reject_invalid_path_no_write_and_io_error_nonfatal(tmp_path,monkeypatch):
    service=memory(tmp_path)
    assert not service.remember('video_import',tmp_path/'missing.mp4',file=True)
    assert not service.settings.path.exists()
    monkeypatch.setattr(service.settings,'update',lambda value:(_ for _ in ()).throw(PermissionError('readonly')))
    assert not service.remember('video_import',tmp_path) and service.last_error


def test_dynamic_shortcuts_current_project_and_last_location(tmp_path):
    service=memory(tmp_path);a=tmp_path/'A';b=tmp_path/'B';a.mkdir();b.mkdir()
    service.remember('video_import',a)
    assert dict(service.shortcuts(b))['Current Project']==b
    assert dict(service.shortcuts(b))['Last Location']==a
    assert 'Current Project' not in dict(service.shortcuts())
    service.remember('png_export',b)
    assert dict(service.shortcuts(a))['Last Location']==b
