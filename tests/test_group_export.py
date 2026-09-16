from pathlib import Path
from threading import Event
import json
import numpy as np
import pytest
from PIL import Image
from app.models.project import Project
from app.core.pipeline import Pipeline
from app.core.group_export import plan_group_export, export_group_plan, exportable_resources, group_disk_paths
from app.utils.paths import cache_directory
from app.utils.ffmpeg import Cancelled


def sequence(tmp_path, name):
    folder=tmp_path/name;folder.mkdir()
    pixels=np.zeros((16,16,4),np.uint8);pixels[4:10,7:12]=(80,30,190,140)
    Image.fromarray(pixels).save(folder/'0000.png')
    return folder


def ready_animation(p, tmp_path, group_id, name):
    p.current_group_id=group_id
    p=p.import_frame_sequence(sequence(tmp_path,name))
    pipe=Pipeline(p,cache_directory(p.project_id,tmp_path/'p.aivsprite',p.animation_id));pipe.build()
    p.library.mark_generated(p.animation_id)
    return p


def test_nested_export_same_names_and_same_pixels_without_processing(tmp_path,monkeypatch):
    p=Project(project_name='Game')
    for root in ('MainCharacter','Boss'):
        parent=p.library.add_group(root)
        movement=p.library.add_group('Movement',parent.id)
        run=p.library.add_group('Run',movement.id)
        p=ready_animation(p,tmp_path,run.id,root)
        p.library.animation(p.animation_id).name='idle'
    out=tmp_path/'Export';out.mkdir()
    plan=plan_group_export(p,tmp_path/'p.aivsprite',[g.id for g in p.library.children()])
    original={item.relative_directory:Image.open(item.source_sheet).copy() for item in plan.items}
    def forbidden(*args,**kwargs):raise AssertionError('Export must not process')
    for method in ('build','ensure_key','ensure_final','ensure_aligned','import_input'):
        monkeypatch.setattr(Pipeline,method,forbidden)
    result=export_group_plan(plan,out)
    assert result['resources']==2
    for parent in ('MainCharacter','Boss'):
        path=Path(parent)/'Movement/Run/idle'
        assert np.array_equal(np.array(Image.open(out/path/'sprite_sheet.png')),np.array(original[path]))
        assert json.loads((out/path/'animation.json').read_text())['animation_name']=='idle'
        assert (out/path/'root_motion.json').exists()
    with pytest.raises(FileExistsError):export_group_plan(plan,out)


def test_multiple_animations_and_imported_sheets_coexist(tmp_path):
    p=Project();g=p.library.add_group('Attack')
    p=ready_animation(p,tmp_path,g.id,'Attack01')
    p=ready_animation(p,tmp_path,g.id,'Attack02')
    source=sequence(tmp_path,'old')/'0000.png'
    p.library.add_sheet(g.id,'Attack01.png',str(source))
    plan=plan_group_export(p,tmp_path/'p.aivsprite',[g.id])
    assert len(plan.items)==3 and len({str(i.relative_directory).casefold() for i in plan.items})==3
    out=tmp_path/'Export';out.mkdir();export_group_plan(plan,out)
    imported=next(i for i in plan.items if i.animation is None)
    assert (out/imported.relative_directory/'sprite_sheet.png').read_bytes()==source.read_bytes()
    assert not (out/imported.relative_directory/'root_motion.json').exists()


def test_empty_and_unprocessed_groups_not_exportable_but_may_export_empty(tmp_path):
    p=Project();empty=p.library.add_group('Empty');source=p.library.add_group('Source')
    p.current_group_id=source.id;p=p.import_animation(tmp_path/'pending.mp4')
    assert not exportable_resources(p,tmp_path/'p.aivsprite',empty.id)
    assert not exportable_resources(p,tmp_path/'p.aivsprite',source.id)
    plan=plan_group_export(p,tmp_path/'p.aivsprite',[empty.id,source.id])
    assert len(plan.warnings)==2 and not plan.items
    out=tmp_path/'Export';out.mkdir();export_group_plan(plan,out)
    assert (out/'Empty').is_dir() and (out/'Source').is_dir()


def test_sanitize_collisions_reserved_names_and_unicode_are_safe(tmp_path):
    p=Project()
    groups=[p.library.add_group(name) for name in ('Run:1','Run?1','CON','..','主角 中文')]
    paths=group_disk_paths(p.library)
    assert len({str(path).casefold() for path in paths.values()})==len(groups)
    assert all(len(path.parts)==1 and path.name not in ('..','CON') for path in paths.values())
    assert any(path.name=='主角 中文' for path in paths.values())
    assert p.library.groups[groups[0].id].name=='Run:1'
    plan=plan_group_export(p,None,[g.id for g in groups]);out=tmp_path/'Out';out.mkdir()
    export_group_plan(plan,out)
    assert len(list(out.iterdir()))==len(groups)


def test_flat_export_and_overlapping_parent_selection_deduplicates(tmp_path):
    p=Project();root=p.library.add_group('主角');child=p.library.add_group('Run',root.id)
    p=ready_animation(p,tmp_path,child.id,'run')
    plan=plan_group_export(p,tmp_path/'p.aivsprite',[root.id,child.id],False)
    assert len(plan.items)==1 and plan.items[0].relative_directory.parts==('主角_Run','run')


def test_cancelled_or_failed_export_never_publishes_partial_results(tmp_path,monkeypatch):
    p=Project();g=p.library.add_group('Idle');p=ready_animation(p,tmp_path,g.id,'Idle')
    plan=plan_group_export(p,tmp_path/'p.aivsprite',[g.id]);out=tmp_path/'Out';out.mkdir()
    cancel=Event();cancel.set()
    with pytest.raises(Cancelled):export_group_plan(plan,out,cancel=cancel)
    assert not list(out.iterdir())
    def fail(*args,**kwargs):raise OSError('disk full')
    monkeypatch.setattr('app.core.group_export.copy_file',fail)
    with pytest.raises(OSError):export_group_plan(plan,out)
    assert not list(out.iterdir())


def test_invalid_selection_missing_cache_and_existing_output(tmp_path):
    p=Project();g=p.library.add_group('Idle');p=ready_animation(p,tmp_path,g.id,'Idle')
    with pytest.raises(ValueError):plan_group_export(p,None,[])
    with pytest.raises(ValueError):plan_group_export(p,None,['missing'])
    pipe=Pipeline(p,cache_directory(p.project_id,tmp_path/'p.aivsprite',p.animation_id));pipe.sheet.unlink()
    assert not exportable_resources(p,tmp_path/'p.aivsprite',g.id)
