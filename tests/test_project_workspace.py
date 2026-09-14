from dataclasses import asdict
import json
from pathlib import Path
import pytest

from app.core.project_workspace import create_project_workspace, sanitize_project_name, PROJECT_DIRECTORIES
from app.models.project import Project
from app.models.character_profile import CharacterProfile


def test_create_ai_template_project_and_reopen(tmp_path):
    p, path = create_project_workspace(tmp_path, 'MainCharacter')
    assert path == tmp_path / 'MainCharacter' / 'MainCharacter.aivsprite'
    assert all((path.parent / folder).is_dir() for folder in PROJECT_DIRECTORIES)
    assert p.source_canvas == (1536, 1536) and p.output_canvas == (512, 512)
    assert p.scale == 1 / 3 and p.default_fps == p.sequence_fps == 24
    assert p.sprite_cell.canvas_mode == 'normalize_source'
    assert p.character_profile is None and not p.root_keyframes
    saved = json.loads(path.read_text(encoding='utf-8'))
    assert saved['project_version'] == '0.4' and saved['project_type'] == 'character_animation'
    assert saved['animations'] == {} and saved['character_profile'] is None
    assert json.loads(json.dumps(asdict(Project.load(path)))) == json.loads(json.dumps(asdict(p)))


def test_custom_project_and_clips_keep_project_metadata_and_profile(tmp_path):
    p, path = create_project_workspace(tmp_path, 'Hero', template='custom', source_canvas=(1200, 900), output_canvas=(800, 600), default_fps=12.5)
    p.character_profile = CharacterProfile()
    p = p.import_animation(tmp_path / 'idle.mp4')
    p.motion_settings.spike_threshold = 5
    run = p.import_animation(tmp_path / 'run.mp4')
    assert run.project_metadata() == p.project_metadata()
    assert (run.sprite_cell.target_width, run.sprite_cell.target_height) == p.character_profile.canvas_size
    seq = run.import_frame_sequence(tmp_path / 'jump')
    assert seq.sequence_fps == 12.5 and seq.is_passthrough
    assert seq.sprite_cell.canvas_mode == 'source_canvas'  # project template never moves passthrough frames
    seq.save(path)
    restored = Project.load(path)
    assert restored.project_metadata() == p.project_metadata()
    assert restored.character_profile == p.character_profile
    idle = restored.select_animation(p.animation_id)
    assert idle.motion_settings.spike_threshold == 5
    assert idle.character_profile == p.character_profile and idle.project_metadata() == p.project_metadata()


@pytest.mark.parametrize('name', ['', ' ', '../escape', 'bad/name', 'bad:name', 'CON', 'LPT1.txt', 'trailing.', 'nul', 'x' * 101])
def test_invalid_windows_names_cannot_create(tmp_path, name):
    with pytest.raises(ValueError, match='name'):
        create_project_workspace(tmp_path, name)
    assert not list(tmp_path.iterdir())


def test_sanitize_names_and_never_overwrite_existing_content(tmp_path):
    assert sanitize_project_name('  My:Hero?  ') == 'My_Hero_'
    assert sanitize_project_name('CON') == '_CON'
    target = tmp_path / 'Hero'
    target.mkdir()
    with pytest.raises(ValueError, match='already exists'):
        create_project_workspace(tmp_path, 'Hero')
    sentinel = target / 'data.txt'
    sentinel.write_text('keep')
    with pytest.raises(ValueError, match='not empty'):
        create_project_workspace(tmp_path, 'Hero', use_existing_empty=True)
    assert sentinel.read_text() == 'keep' and list(target.iterdir()) == [sentinel]


def test_explicit_empty_directory_reuse(tmp_path):
    (tmp_path / 'Hero').mkdir()
    _, path = create_project_workspace(tmp_path, 'Hero', template='standard', use_existing_empty=True)
    assert Project.load(path).source_canvas == (512, 512)


def test_legacy_projects_default_metadata_and_empty_animation_array():
    p = Project.load(Path('examples/demo.aivsprite'))
    assert p.default_fps == 24 and p.project_type == 'character_animation'
    assert p.project_name == '' and p.source_video.endswith('demo_green_screen.mp4')
    assert Project.from_dict({'animations': []}).animations == {}
