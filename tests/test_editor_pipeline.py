import json
from pathlib import Path
import numpy as np
import pytest
from dataclasses import asdict
from app.models.project import Project
from app.models.timeline_edit import FrameOverride
from app.core.pipeline import Pipeline
from app.core.final_frame_provider import FinalFrameProvider
from app.core.timeline_renderer import compile_timeline
from app.exporters.image_exporter import export_images
from app.utils.cache import save_rgba
from app.utils.rgba_image import read_rgba
from app.utils.paths import frame_path


@pytest.fixture
def editor_pipe(tmp_path):
    folder = tmp_path / 'attack'
    folder.mkdir()
    for i in range(39):
        rgba = np.zeros((32, 32, 4), np.uint8)
        rgba[12:18, 10:16] = (10+i*5, 30, 180, 255)
        rgba[0, 0] = (77, 33, 12, 0)
        save_rgba(folder / f'{i}.png', rgba)
    p = Project().import_frame_sequence(folder)
    pipe = Pipeline(p, tmp_path / 'cache')
    pipe.build()
    p.timeline_edit.initialize(39, 24)
    return pipe


def test_39_to_20_remap_preview_export_and_roundtrip(editor_pipe, tmp_path):
    pipe = editor_pipe
    p = pipe.project
    e = p.timeline_edit
    chosen = e.retime_count([f.id for f in e.frames()], 20, 24, 'ease_in_out')
    pipe.build()
    provider = FinalFrameProvider(p, pipe.cache_dir)
    assert len(provider) == 20 and p.video.frame_count == len(p.tracking_results) == 39
    assert provider.source_index(0) == 0 and provider.source_index(19) == 38
    export_images(pipe, tmp_path / 'out', godot=True)
    for i in range(20):
        assert np.array_equal(provider.get_final_frame(i), read_rgba(tmp_path / 'out/frames' / f'{i:04d}.png'))
        assert np.array_equal(provider.get_source_keyed_frame(i), read_rgba(frame_path(pipe.keyed, provider.source_index(i))))
    metadata = json.loads((tmp_path / 'out/animation.json').read_text())
    assert metadata['frame_count'] == 20 and metadata['source_frame_count'] == 39 and metadata['rows'] == 3
    assert sum(f['duration'] for f in metadata['frames']) == pytest.approx(20/24)
    p.save(tmp_path / 'attack.aivsprite')
    restored = Project.load(tmp_path / 'attack.aivsprite')
    assert asdict(restored.timeline_edit) == asdict(e)
    assert [f.id for f in restored.timeline_edit.frames()] == chosen
    assert restored.select_animation(restored.animation_id).timeline_edit.enabled


def test_identity_exact_rgba_and_manual_offset(editor_pipe, tmp_path):
    pipe = editor_pipe
    p = pipe.project
    pipe.build()
    first = FinalFrameProvider(p, pipe.cache_dir)
    assert np.array_equal(first.get_final_frame(0), read_rgba(frame_path(pipe.aligned, 0)))
    p.timeline_edit.offset([p.timeline_edit.frames()[12].id], 3, -4)
    pipe.build()
    provider = FinalFrameProvider(p, pipe.cache_dir)
    expected = np.zeros((32, 32, 4), np.uint8)
    expected[8:14, 13:19] = (70, 30, 180, 255)
    assert np.array_equal(provider.get_final_frame(12), expected)
    assert provider.frame_data(12).cell_bbox == (13, 8, 19, 14)
    with pytest.raises(RuntimeError): first.validate()
    assert read_rgba(Path(p.sequence_folder) / '12.png')[12,10,0] == 70


def test_multi_track_alpha_order_visibility_and_reference_exclusion(editor_pipe):
    p = editor_pipe.project
    e = p.timeline_edit
    clip = e.copy([e.frames()[38].id])
    overlay = e.paste(clip, 0, 'effects')[0]
    e.frame_overrides[overlay].opacity = .5
    e.paste(e.copy([e.frames()[1].id]), 0, 'reference')
    editor_pipe.build()
    provider = FinalFrameProvider(p, editor_pipe.cache_dir)
    assert tuple(provider.get_final_frame(0)[13,11]) == (105,30,180,255)
    next(t for t in e.track_layout if t.id == 'effects').visible = False
    editor_pipe.build()
    assert tuple(FinalFrameProvider(p, editor_pipe.cache_dir).get_final_frame(0)[13,11]) == (10,30,180,255)


def test_duration_retime_and_reverse_preserve_source(editor_pipe):
    p = editor_pipe.project
    e = p.timeline_edit
    source = [f.source_index for f in e.frames()]
    ids = [f.id for f in e.frames()]
    e.reverse(ids[-5:])
    assert [f.source_index for f in e.frames()][-5:] == list(reversed(source[-5:]))
    e.retime_duration(ids[:20], .4, 'ease_in_out')
    editor_pipe.build()
    provider = FinalFrameProvider(p, editor_pipe.cache_dir)
    durations = [provider.duration(i) for i in range(len(provider))]
    assert len(provider) == 39 and sum(durations[:20]) == pytest.approx(.4)
    assert max(durations[:20]) > min(durations[:20])*2
    assert sum(durations) == pytest.approx(.4+19/24)


def test_hidden_or_deleted_timeline_never_exports_stale_frames(editor_pipe):
    p = editor_pipe.project
    p.timeline_edit.delete([f.id for f in p.timeline_edit.frames()])
    assert compile_timeline(p.timeline_edit) == []
    with pytest.raises(ValueError, match='no visible frames'):
        editor_pipe.build()


def test_edit_is_animation_local_and_legacy_defaults(editor_pipe):
    p = editor_pipe.project
    p.timeline_edit.delete([p.timeline_edit.frames()[2].id])
    other = p.import_frame_sequence(Path(p.sequence_folder))
    assert not other.timeline_edit.enabled
    assert other.select_animation(p.animation_id).timeline_edit.enabled
    assert not Project.load(Path('examples/demo.aivsprite')).timeline_edit.enabled


def test_live_provider_matches_cached_output_for_copies_layers_and_timing(editor_pipe):
    p=editor_pipe.project;e=p.timeline_edit
    ids=[f.id for f in e.frames()]
    e.offset(ids[5:8],3,2)
    pasted=e.paste(e.copy(ids[:4]),.1,'effects',False)
    for ident in pasted:e.frame_overrides[ident]=FrameOverride(-2,4,.8,.4)
    e.retime_duration(ids[10:20],.3,'ease_in_out')
    live=FinalFrameProvider(p,editor_pipe.cache_dir,live_edit=True)
    expected=[live.get_final_frame(i).copy() for i in range(len(live))]
    editor_pipe.build()
    final=FinalFrameProvider(p,editor_pipe.cache_dir)
    assert len(final)==len(live)
    for i,pixels in enumerate(expected):
        assert np.array_equal(pixels,final.get_final_frame(i))
        assert final.duration(i)==live.duration(i)
    assert all('Low Confidence' not in f.warnings for f in p.final_frames)
