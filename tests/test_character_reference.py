from dataclasses import asdict, replace, FrozenInstanceError
from pathlib import Path
import json
import numpy as np
import pytest
from app.models.project import Project
from app.models.character_reference import CharacterReference, AnimationTransform
from app.core.pipeline import Pipeline
from app.core.final_frame_provider import FinalFrameProvider
from app.core.character_reference import ReferenceSource
from app.core.animation_transform import ANIMATION_OVERFLOW
from app.core.project_workspace import create_project_workspace
from app.exporters.image_exporter import export_images
from app.utils.cache import save_rgba
from app.utils.paths import cache_directory, frame_path
from app.utils.rgba_image import read_rgba


@pytest.fixture
def reference_pipe(tmp_path):
    folder=tmp_path/'Idle';folder.mkdir()
    for i in range(4):
        rgba=np.zeros((96,80,4),np.uint8)
        rgba[30:42,20+i:32+i]=(220,70,130,191)
        save_rgba(folder/f'{i}.png',rgba)
    p,path=create_project_workspace(tmp_path,'Hero','standard',project_canvas=(96,96))
    p=p.import_frame_sequence(folder)
    pipe=Pipeline(p,cache_directory(p.project_id,path,p.animation_id));pipe.build()
    pipe.project_path=path
    return pipe


def reference(p):
    return CharacterReference(p.animation_id,0,48.,86.,p.video.width,p.video.height)


def test_reference_draft_axis_constraints_and_saved_lock():
    r=CharacterReference('default',0,764.,1218.,1536,1536)
    assert r.moved('ground',70,-3).origin==(764.,1215.)
    assert r.moved('y_axis',-4,80).origin==(760.,1218.)
    assert r.moved('origin',-4,3).origin==(760.,1221.)
    assert r.locked and r.canvas_size==(1536,1536)
    with pytest.raises(FrozenInstanceError):r.origin_x=1
    with pytest.raises(ValueError,match='locked'):replace(r,locked=False)


def test_reference_is_global_offset_is_animation_local_roundtrip(reference_pipe,tmp_path):
    p=reference_pipe.project;p.character_reference=reference(p)
    idle=p.animation_id;original=p.character_reference
    p=p.import_frame_sequence(Path(p.sequence_folder));run=p.animation_id
    assert p.character_reference==original and not p.animation_transform.active
    p.animation_transform=AnimationTransform(-12,4)
    p=p.import_animation(tmp_path/'Jump.mp4')
    assert p.is_keyed_passthrough and not p.animation_transform.active
    p.save(tmp_path/'Hero.aivsprite')
    loaded=Project.load(tmp_path/'Hero.aivsprite')
    assert loaded.character_reference==original
    assert loaded.select_animation(run).animation_transform==AnimationTransform(-12,4)
    assert loaded.select_animation(idle).animation_transform==AnimationTransform()
    assert all('character_reference' not in entry for entry in loaded.animations.values())
    assert 'character_reference' in json.loads((tmp_path/'Hero.aivsprite').read_text())


def test_missing_fields_legacy_and_reference_is_not_canonical_root():
    old=Project.load(Path('examples/character_profile.aivsprite'))
    assert old.character_reference is None and old.animation_transform==AnimationTransform()
    before=asdict(old.character_profile)
    old.character_reference=CharacterReference(old.animation_id,0,764,1218,1536,1536)
    assert asdict(old.character_profile)==before
    assert Project.from_dict({}).character_reference is None


def test_reference_edits_do_not_invalidate_canvas_key_alignment_or_pixels(reference_pipe):
    pipe=reference_pipe;p=pipe.project
    signatures=(pipe.raw_signature(),pipe.key_signature(),pipe.align_signature(),pipe.final_signature())
    paths=[frame_path(pipe.raw,i) for i in range(4)]+[frame_path(pipe.aligned,i) for i in range(4)]
    before=[(path.read_bytes(),path.stat().st_mtime_ns) for path in paths]
    p.character_reference=reference(p).moved('origin',6,-8)
    pipe.build()
    assert signatures==(pipe.raw_signature(),pipe.key_signature(),pipe.align_signature(),pipe.final_signature())
    assert before==[(path.read_bytes(),path.stat().st_mtime_ns) for path in paths]
    assert p.project_canvas==(96,96)
    assert np.array_equal(read_rgba(frame_path(pipe.raw,0))[:,8:88],read_rgba(Path(p.sequence_folder)/'0.png'))


def test_whole_animation_offset_no_source_changes_and_live_export_equality(reference_pipe,tmp_path,monkeypatch):
    pipe=reference_pipe;p=pipe.project;p.character_reference=reference(p)
    sources=sorted(Path(p.sequence_folder).glob('*.png'))
    base=[frame_path(pipe.aligned,i) for i in range(4)]
    before=[(f.read_bytes(),f.stat().st_mtime_ns) for f in sources+base]
    p.animation_transform=AnimationTransform(-12,4)
    # Offset also works without entering/initializing a timeline.
    assert not p.timeline_edit.enabled and not p.timeline_edit.frame_overrides
    live=FinalFrameProvider(p,pipe.cache_dir,live_edit=True)
    for name in ('ensure_roots','ensure_motion','ensure_source_aligned'):
        monkeypatch.setattr(pipe,name,lambda:pytest.fail('Automatic alignment must not run'))
    pipe.build();export_images(pipe,tmp_path/'out',godot=True)
    final=FinalFrameProvider(p,pipe.cache_dir)
    for i in range(4):
        expected=np.zeros((96,96,4),np.uint8);expected[34:46,16+i:28+i]=(220,70,130,191)
        assert np.array_equal(live.get_final_frame(i),expected)
        assert np.array_equal(final.get_final_frame(i),expected)
        assert np.array_equal(read_rgba(tmp_path/'out/frames'/f'{i:04d}.png'),expected)
    assert before==[(f.read_bytes(),f.stat().st_mtime_ns) for f in sources+base]
    data=json.loads((tmp_path/'out/animation.json').read_text())
    assert data['animation_transform']=={'offset_x':-12,'offset_y':4}
    assert data['character_reference']['origin_x']==48
    assert not data['root_tracked'] and all(f['root'] is None for f in data['frames'])


def test_offset_project_pixels_before_1536_to_512(reference_pipe,tmp_path):
    folder=tmp_path/'large';folder.mkdir()
    pixels=np.zeros((1536,1536,4),np.uint16);pixels[606:636,708:738]=(65535,0,32768,65535)
    save_rgba(folder/'0.png',pixels)
    p=Project(project_canvas_width=1536,project_canvas_height=1536,canvas_fit_mode='center_crop_or_pad').import_frame_sequence(folder)
    p.sprite_cell.canvas_mode='normalize_source';p.sprite_cell.target_width=p.sprite_cell.target_height=512
    pipe=Pipeline(p,tmp_path/'large-cache');pipe.build()
    p.character_reference=CharacterReference(p.animation_id,0,764,1218,1536,1536)
    p.animation_transform=AnimationTransform(-12,6)
    live=FinalFrameProvider(p,pipe.cache_dir,live_edit=True);pipe.build()
    expected=np.zeros((512,512,4),np.uint8);expected[204:214,232:242]=(255,0,128,255)
    assert np.array_equal(live.get_final_frame(0),expected)
    assert np.array_equal(FinalFrameProvider(p,pipe.cache_dir).get_final_frame(0),expected)
    assert p.project_canvas==(1536,1536) and (p.layout.width,p.layout.height)==(512,512)


def test_offset_overflow_warns_without_recenter_resize_or_export_block(reference_pipe,tmp_path):
    pipe=reference_pipe;p=pipe.project;p.character_reference=reference(p)
    p.animation_transform=AnimationTransform(-35,0)
    pipe.build()
    assert all(ANIMATION_OVERFLOW in f.warnings for f in p.output_frames)
    assert p.layout.width==p.layout.height==96 and not p.layout.clipped_frames
    result=FinalFrameProvider(p,pipe.cache_dir).get_final_frame(0)
    assert tuple(result[30,0])==(220,70,130,191) and not result[:,5:,3].any()
    export_images(pipe,tmp_path/'clipped')


def test_idle_ghost_ignores_current_and_reference_offsets_and_reuses_cache(reference_pipe,monkeypatch):
    pipe=reference_pipe;p=pipe.project;p.character_reference=reference(p)
    p.animation_transform=AnimationTransform(20,4)
    run=p.import_frame_sequence(Path(p.sequence_folder));run.animation_transform=AnimationTransform(-12,8)
    runpipe=Pipeline(run,cache_directory(run.project_id,pipe.project_path,run.animation_id));runpipe.build()
    ghost=ReferenceSource(run,run.character_reference,runpipe.cache_dir,pipe.project_path)
    raw=read_rgba(frame_path(pipe.keyed,0))
    assert np.array_equal(ghost.get(),raw)
    monkeypatch.setattr(ghost.pipe,'ensure_key',lambda:pytest.fail('Ghost decoded/keyed again'))
    assert ghost.get() is ghost.get()
    assert np.array_equal(ghost.output(run.layout),raw)
    assert ghost.output(run.layout) is ghost.output(run.layout)


@pytest.mark.parametrize('size',[(1024,1536),(1920,1536),(1920,1080)])
def test_reference_does_not_change_resolution_center_fit(size,tmp_path):
    w,h=size;folder=tmp_path/'Idle';folder.mkdir()
    source=np.zeros((h,w,4),np.uint8);source[h//2-9:h//2+9,w//2-12:w//2+12]=(71,190,230,203)
    save_rgba(folder/'0.png',source)
    p=Project(project_canvas_width=1536,project_canvas_height=1536,canvas_fit_mode='center_crop_or_pad').import_frame_sequence(folder)
    pipe=Pipeline(p,tmp_path/'cache');pipe.build()
    expected=np.zeros((1536,1536,4),np.uint8);expected[759:777,756:780]=(71,190,230,203)
    p.character_reference=CharacterReference(p.animation_id,0,764,1218,1536,1536).moved('origin',100,-100)
    pipe.build()
    assert np.array_equal(FinalFrameProvider(p,pipe.cache_dir).get_final_frame(0),expected)
    assert p.project_canvas==(1536,1536) and p.original_size==size


def test_keyed_video_reference_offset_export_never_rekeys_or_redecodes(tmp_path,monkeypatch):
    from app.models.project import VideoInfo
    source=tmp_path/'Idle.mp4';source.write_bytes(b'decoder fixture')
    original=np.full((48,64,4),(0,255,0,255),np.uint8);original[18:32,24:36]=(230,40,90,255)
    def decode(path,directory,info,progress,cancel):
        for i in range(3):save_rgba(frame_path(directory,i),original)
        return 3
    monkeypatch.setattr('app.core.pipeline.probe_video',lambda *a:VideoInfo(64,48,24,'24/1',3,3/24))
    monkeypatch.setattr('app.core.pipeline.decode_video',decode)
    p=Project(source_video=str(source),project_canvas_width=48,project_canvas_height=64,canvas_fit_mode='center_crop_or_pad')
    pipe=Pipeline(p,tmp_path/'cache');pipe.import_video();pipe.ensure_key()
    p.set_processing_mode('keyed_passthrough');pipe.build()
    keyed=read_rgba(frame_path(pipe.keyed,0));stamp=frame_path(pipe.keyed,0).stat().st_mtime_ns
    monkeypatch.setattr('app.core.pipeline.decode_video',lambda *a:pytest.fail('Unexpected decode'))
    monkeypatch.setattr('app.core.pipeline.chroma_key',lambda *a:pytest.fail('Unexpected Chroma Key'))
    monkeypatch.setattr(pipe,'ensure_roots',lambda:pytest.fail('Unexpected Root Tracking'))
    p.character_reference=CharacterReference(p.animation_id,0,24,50,48,64)
    p.animation_transform=AnimationTransform(-5,2)
    live=FinalFrameProvider(p,pipe.cache_dir,live_edit=True)
    expected=np.zeros_like(keyed);expected[2:,:-5]=keyed[:-2,5:]
    export_images(pipe,tmp_path/'video-out',godot=True)
    for i in range(3):
        assert np.array_equal(live.get_final_frame(i),expected)
        assert np.array_equal(read_rgba(tmp_path/'video-out/frames'/f'{i:04d}.png'),expected)
    assert frame_path(pipe.keyed,0).stat().st_mtime_ns==stamp
    assert not p.root_keyframes
