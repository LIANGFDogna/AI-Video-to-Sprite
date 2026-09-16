from dataclasses import asdict
import copy
import json
from pathlib import Path
import pytest
from app.models.project import Project
from app.models.project_library import ProjectLibrary, WorkspaceState, TaskContext
from app.utils.paths import cache_directory


def project_group(name="Idle"):
    project = Project(project_name="中文 Project")
    group = project.library.add_group(name)
    project.current_group_id = group.id
    return project, group.id


def test_empty_project_requires_explicit_group_and_source_cannot_live_at_root():
    p = Project()
    assert not p.library.groups
    with pytest.raises(ValueError):
        p.library.add_source_animation(None, "a"*32, "Idle", "idle.mp4", "SOURCE_VIDEO")
    with pytest.raises(ValueError):
        p.library.add_sheet(None, "Sheet", "sheet.png")


def test_group_multiple_video_sequence_animation_and_sheets_coexist(tmp_path):
    p, group = project_group()
    ids = []
    for name, sequence in (("VideoA", False), ("VideoB", False), ("SequenceA", True), ("SequenceB", True)):
        p = p.import_frame_sequence(tmp_path/name) if sequence else p.import_animation(tmp_path/(name+".mp4"))
        ids.append(p.animation_id)
        p.library.mark_generated(p.animation_id)
    p.library.add_sheet(group, "Old Sheet", str(tmp_path/"old.png"))
    p.library.add_sheet(group, "Other Sheet", str(tmp_path/"other.png"))
    assert len(p.all_animation_snapshots()) == 4
    assert p.library.animation_count(group) == 4
    assert len(p.library.in_group(group, kinds={"SOURCE_VIDEO"})) == 2
    assert len(p.library.in_group(group, kinds={"SOURCE_SEQUENCE"})) == 2
    assert len(p.library.in_group(group, kinds={"GENERATED_SPRITE_SHEET", "SOURCE_SPRITE_SHEET"})) == 6
    for ident in ids:
        assert p.select_animation(ident).current_group_id == group
    p.library.validate()


def test_nested_group_names_uuid_counts_and_cycle_rejection():
    lib = ProjectLibrary()
    a, b = lib.add_group("MainCharacter"), lib.add_group("Boss")
    idle1, idle2 = lib.add_group("Idle", a.id), lib.add_group("Idle", b.id)
    assert idle1.id != idle2.id and idle1.name == idle2.name
    assert lib.add_group("idle", a.id).name == "idle 2"
    lib.add_source_animation(idle1.id, "a"*32, "A", "A.mp4", "SOURCE_VIDEO")
    assert lib.animation_count(a.id) == 1 and lib.animation_count(b.id) == 0
    assert [g.name for g in lib.path(idle1.id)] == ["MainCharacter", "Idle"]
    before = asdict(lib)
    with pytest.raises(ValueError):
        lib.move_group(a.id, idle1.id)
    assert asdict(lib) == before


def test_reorder_rename_and_move_keep_uuid():
    lib = ProjectLibrary()
    a, b, c = [lib.add_group(name) for name in ("A", "B", "C")]
    lib.move_group(c.id, None, 0)
    assert [g.id for g in lib.children()] == [c.id, a.id, b.id]
    lib.rename_group(a.id, "B")
    assert a.name == "B 2"
    lib.move_group(a.id, c.id)
    assert lib.groups[a.id].parent_id == c.id


def test_move_animation_moves_generated_sheet_but_keeps_source_reference(tmp_path):
    p, a = project_group()
    p = p.import_animation(tmp_path/"idle.mp4")
    animation = p.library.animation(p.animation_id)
    source = p.library.resources[animation.source_id]
    sheet = p.library.mark_generated(p.animation_id)
    b = p.library.add_group("Run")
    p.library.groups[a].ui_state.animation_id = p.animation_id
    p.library.move_resource(animation.id, b.id)
    assert animation.group_id == sheet.group_id == b.id and source.group_id == a
    assert p.library.groups[a].ui_state.animation_id is None
    p.library.move_resource(source.id, b.id)
    p.library.validate()
    with pytest.raises(ValueError):
        p.library.move_resource(animation.id, None)


def test_nonempty_delete_only_moves_to_parent_never_deletes_source(tmp_path):
    source = tmp_path/"keep.mp4";source.write_bytes(b"original")
    p, parent = project_group("Parent")
    group = p.library.add_group("Child", parent)
    p.current_group_id = group.id
    p = p.import_animation(source)
    p.library.mark_generated(p.animation_id)
    with pytest.raises(ValueError):
        p.library.remove_group(group.id)
    p.library.remove_group(group.id, move_to_parent=True)
    assert group.id not in p.library.groups
    assert all(r.group_id == parent for r in p.library.resources.values())
    assert source.read_bytes() == b"original"
    with pytest.raises(ValueError):
        p.library.remove_group(parent, move_to_parent=True)


def test_library_roundtrip_preserves_workspace_and_relative_paths(tmp_path):
    p, group = project_group()
    p = p.import_animation(tmp_path/"中文 素材.mp4")
    g = p.library.groups[group]
    g.ui_state = WorkspaceState(p.animation_id, frame=14, timeline_zoom=1400., timeline_scroll_x=120, editor_tab=1, page=2, onion=True)
    g.animation_states[p.animation_id] = copy.deepcopy(g.ui_state)
    p.library.add_sheet(group, "既有 Sheet", str(tmp_path/"旧 图.png"))
    path = tmp_path/"工程.aivsprite"
    p.save(path)
    encoded = json.loads(path.read_text(encoding="utf-8"))
    assert all(not Path(r['path']).is_absolute() for r in encoded['library']['resources'].values() if r['path'])
    restored = Project.load(path)
    assert asdict(restored.library) == asdict(p.library)
    assert restored.current_group_id == group and restored.library.groups[group].ui_state.frame == 14
    assert 'library' not in p.animation_snapshot() and 'library' not in p.project_metadata()


def test_empty_group_selection_keeps_every_animation_and_same_cache(tmp_path):
    p, a = project_group()
    p = p.import_animation(tmp_path/"a.mp4");aid = p.animation_id
    p.root_keyframes[0] = (4., 7.)
    b = p.library.add_group("Empty")
    empty = p.empty_context(b.id)
    assert not empty.source_path and empty.current_group_id == b.id
    restored = empty.select_animation(aid)
    assert restored.root_keyframes == p.root_keyframes
    assert restored.current_group_id == a
    assert cache_directory(p.project_id, tmp_path/"p.aivsprite", aid) == cache_directory(restored.project_id, tmp_path/"p.aivsprite", aid)


def test_background_result_updates_owner_only_and_preserves_new_library(tmp_path):
    p, a = project_group()
    p = p.import_animation(tmp_path/"a.mp4");task = copy.deepcopy(p);aid = p.animation_id
    b = p.library.add_group("B")
    p.current_group_id = b.id
    p = p.import_animation(tmp_path/"b.mp4");bid = p.animation_id
    task.root_keyframes[0] = (9., 8.)
    result = p.merge_animation_result(task)
    assert result.animation_id == bid and result.current_group_id == b.id and not result.root_keyframes
    assert result.select_animation(aid).root_keyframes[0] == (9., 8.)
    assert b.id in result.library.groups
    task.project_id = "a"*32
    with pytest.raises(ValueError):
        result.merge_animation_result(task)


def test_legacy_migration_preserves_all_processing_data_and_ids(tmp_path):
    p = Project(source_video=str(tmp_path/"Idle.mp4"))
    p.root_keyframes[0] = (32., 67.)
    old = asdict(p)
    old.pop('library');old.pop('current_group_id')
    restored = Project.from_dict(old)
    assert len(restored.library.groups) == 1 and restored.animation_id == 'default'
    assert restored.root_keyframes == p.root_keyframes
    before = p.animation_snapshot();after = restored.animation_snapshot()
    assert json.dumps(before, sort_keys=True) == json.dumps(after, sort_keys=True)
    assert not Project.from_dict({}).library.groups


@pytest.mark.parametrize('corruption', ['orphan', 'cycle', 'duplicate_animation', 'bad_selected'])
def test_invalid_library_relationships_rejected(tmp_path, corruption):
    p, group = project_group()
    p = p.import_animation(tmp_path/"a.mp4")
    data = asdict(p.library)
    if corruption == 'orphan':
        next(iter(data['resources'].values()))['group_id'] = 'f'*32
    elif corruption == 'cycle':
        data['groups'][group]['parent_id'] = group
    elif corruption == 'duplicate_animation':
        animation = next(r for r in data['resources'].values() if r['kind'] == 'ANIMATION')
        duplicate = copy.deepcopy(animation);duplicate['id'] = 'e'*32;data['resources'][duplicate['id']] = duplicate
    else:
        data['groups'][group]['ui_state']['animation_id'] = 'missing'
    with pytest.raises(ValueError):
        ProjectLibrary.from_dict(data)


def test_group_status_and_counts_do_not_count_sheets_as_animations(tmp_path):
    p, group = project_group()
    assert p.library.groups[group].status == 'EMPTY'
    p.library.add_sheet(group, 'Sheet', str(tmp_path/'sheet.png'))
    assert p.library.groups[group].status == 'READY' and p.library.animation_count(group) == 0
    p = p.import_animation(tmp_path/'a.mp4')
    p.library.refresh_status([p.animation_id])
    assert p.library.groups[group].status == 'PROCESSING'
    p.library.animation(p.animation_id).warning = 'Cache missing'
    p.library.refresh_status()
    assert p.library.groups[group].status == 'WARNING'
