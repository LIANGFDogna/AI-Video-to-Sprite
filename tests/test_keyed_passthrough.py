import copy
from dataclasses import asdict
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.core.pipeline import Pipeline
from app.core.alpha_utils import alpha_bbox
from app.core.final_frame_provider import FinalFrameProvider
from app.core.canvas_normalizer import normalize_canvas, canvas_transform
from app.exporters.image_exporter import export_images
from app.models.project import Project, VideoInfo
from app.models.character_profile import CharacterProfile
from app.utils.cache import save_rgba, FrameCache
from app.utils.paths import frame_path


@pytest.fixture
def keyed_video(tmp_path, monkeypatch):
    source = tmp_path / 'jump_dash.mp4'
    source.write_bytes(b'synthetic decoded fixture')
    info = VideoInfo(96, 96, 30., '30/1', 56, 56/30)
    positions = [(8 + i, int(round(65 - 45 * np.sin(np.pi * i / 55)))) for i in range(56)]
    def decode(path, directory, video, progress, cancel):
        for i, (x, y) in enumerate(positions):
            rgba = np.full((96, 96, 4), (0, 255, 0, 255), np.uint8)
            rgba[y:y+16, x:x+10] = (210, 30, 70, 255)
            save_rgba(frame_path(directory, i), rgba)
        return 56
    monkeypatch.setattr('app.core.pipeline.probe_video', lambda *a: copy.deepcopy(info))
    monkeypatch.setattr('app.core.pipeline.decode_video', decode)
    project = Project(source_video=str(source))
    project.motion_settings.enabled = True
    project.chroma_key_settings.edge_feather = 0
    project.chroma_key_settings.noise_removal = 0
    project.chroma_key_settings.minimum_alpha = 0
    pipe = Pipeline(project, tmp_path / 'cache')
    pipe.ensure_key()
    return pipe, positions


def test_keyed_passthrough_preserves_every_pixel_jump_dash_and_skips_all_motion(keyed_video, monkeypatch):
    pipe, positions = keyed_video
    p = pipe.project
    p.character_profile = CharacterProfile()
    p.root_keyframes[0] = (90., 90.)
    p.motion_settings.x_policy = p.motion_settings.y_policy = 'LOCK'
    p.sprite_cell.canvas_mode = 'normalize_source'
    profile = asdict(p.character_profile)
    p.set_processing_mode('keyed_passthrough')
    assert p.sprite_cell.canvas_mode == 'source_canvas'
    def forbidden(*a, **k):
        raise AssertionError('No root, motion, alignment, alpha centering or re-keying')
    for method in ('ensure_roots', 'ensure_motion', 'ensure_source_aligned'):
        monkeypatch.setattr(pipe, method, forbidden)
    for method in ('chroma_key', 'warp_rgba', 'apply_character_motion', 'calculate_layout', 'motion_auto_layout'):
        monkeypatch.setattr('app.core.pipeline.' + method, forbidden)
    pipe.build()
    provider = FinalFrameProvider(p, pipe.cache_dir)
    assert p.video.frame_count == 56 and (p.layout.width, p.layout.height) == (96, 96)
    for i, (x, y) in enumerate(positions):
        expected = pipe.cache.read(frame_path(pipe.keyed, i))
        final = provider.get_final_frame(i)
        assert np.array_equal(expected, final)
        assert alpha_bbox(final, 0, 0) == (x, y, x+10, y+16)
        assert p.tracking_results[i].correction == p.tracking_results[i].offset == (0., 0.)
    assert p.tracking_results[27].cell_bbox[1] < p.tracking_results[0].cell_bbox[1] - 40
    assert p.tracking_results[-1].cell_bbox[0] > p.tracking_results[0].cell_bbox[0] + 50
    assert asdict(p.character_profile) == profile
    assert all(f.tracking_method == 'passthrough' and not f.warnings for f in p.tracking_results)


@pytest.mark.parametrize('target', [1536, 1024, 768, 512, 137])
def test_resize_uses_one_shared_transform(keyed_video, target, monkeypatch):
    pipe, _ = keyed_video
    p = pipe.project
    # Two existing decoded frames are enough to verify transform identity at all presets.
    p.video.frame_count = 2
    monkeypatch.setattr(pipe, 'ensure_key', lambda: None)
    p.set_processing_mode('keyed_passthrough')
    p.sprite_cell.canvas_mode = 'normalize_source'
    p.sprite_cell.target_width = target
    p.sprite_cell.target_height = target // 2
    original = normalize_canvas
    transforms = []
    def record(rgba, transform):
        transforms.append(transform)
        return original(rgba, transform)
    monkeypatch.setattr('app.core.pipeline.normalize_canvas', record)
    pipe.ensure_aligned()
    provider = FinalFrameProvider(p, pipe.cache_dir)
    expected = canvas_transform(96, 96, target, target // 2, True)
    assert len(transforms) == 2 and transforms[0] is transforms[1] and transforms[0] == expected
    assert expected.scale_x == expected.scale_y
    for i in range(2):
        final = provider.get_final_frame(i)
        assert final.shape[:2] == (target // 2, target)
        assert np.array_equal(final, original(pipe.cache.read(frame_path(pipe.keyed, i)), expected))


def test_passthrough_export_metadata_and_preview_are_identical(keyed_video, tmp_path):
    pipe, _ = keyed_video
    p = pipe.project
    p.character_profile = CharacterProfile()
    p.set_processing_mode('keyed_passthrough')
    output = export_images(pipe, tmp_path / 'export', godot=True)
    provider = FinalFrameProvider(p, pipe.cache_dir)
    with Image.open(output / 'sprite_sheet.png') as sheet:
        assert sheet.size == (96 * 8, 96 * 7)
        for i in range(56):
            x, y = i % 8 * 96, i // 8 * 96
            assert np.array_equal(np.array(sheet.crop((x, y, x+96, y+96))), provider.get_final_frame(i))
            with Image.open(output / 'frames' / f'{i:04d}.png') as frame:
                assert np.array_equal(np.array(frame), provider.get_final_frame(i))
    metadata = json.loads((output / 'animation.json').read_text())
    assert metadata['processing_mode'] == 'keyed_passthrough' and metadata['alignment_mode'] == 'passthrough'
    assert not metadata['character_profile_applied'] and not metadata['root_tracked']
    assert all(f['root'] is None and f['tracking_confidence'] is None for f in metadata['frames'])
    motion = json.loads((output / 'root_motion.json').read_text())
    assert motion['fps'] == 30 and not motion['available'] and motion['frames'] == []


def test_resume_full_processing_reuses_keyed_cache_and_keeps_settings(keyed_video, monkeypatch):
    pipe, _ = keyed_video
    p = pipe.project
    p.root_keyframes = {i: (13+i, 72.) for i in range(56)}
    p.motion_settings.smoothing_window = 11
    old = (dict(p.root_keyframes), asdict(p.motion_settings), p.alignment_mode, p.sprite_cell.canvas_mode)
    times = [frame_path(pipe.keyed, i).stat().st_mtime_ns for i in range(56)]
    p.set_processing_mode('keyed_passthrough')
    pipe.build()
    stale = FinalFrameProvider(p, pipe.cache_dir)
    p.set_processing_mode('full')
    monkeypatch.setattr('app.core.pipeline.chroma_key', lambda *a: pytest.fail('Re-keyed unchanged source'))
    pipe.build()
    assert times == [frame_path(pipe.keyed, i).stat().st_mtime_ns for i in range(56)]
    assert (p.root_keyframes, asdict(p.motion_settings), p.alignment_mode, p.sprite_cell.canvas_mode) == old
    assert all(f.tracking_method == 'manual' for f in p.tracking_results)
    with pytest.raises(RuntimeError, match='changed'):
        stale.get_final_frame(0)


def test_key_parameter_changes_invalidate_passthrough_cells(keyed_video):
    pipe, _ = keyed_video
    p = pipe.project
    p.set_processing_mode('keyed_passthrough')
    pipe.build()
    before = FinalFrameProvider(p, pipe.cache_dir).get_final_frame(0).copy()
    sig = pipe.align_signature()
    p.chroma_key_settings.green_color = (210, 30, 70)
    assert sig != pipe.align_signature() and not pipe.key_cache_ready()
    pipe.build()
    after = FinalFrameProvider(p, pipe.cache_dir).get_final_frame(0)
    assert not np.array_equal(before, after)
    assert np.array_equal(after, pipe.cache.read(frame_path(pipe.keyed, 0)))


def test_mode_save_reload_and_legacy_defaults(keyed_video, tmp_path):
    pipe, _ = keyed_video
    p = pipe.project
    p.set_processing_mode('keyed_passthrough')
    p.save(tmp_path / 'video.aivsprite')
    restored = Project.load(tmp_path / 'video.aivsprite')
    assert restored.processing_mode == 'keyed_passthrough' and restored.is_passthrough
    assert restored.input_mode == 'video' and not restored.passthrough_alignment
    Pipeline(restored, pipe.cache_dir).build()
    data = json.loads((tmp_path / 'video.aivsprite').read_text())
    data.pop('processing_mode')
    data.pop('full_processing_canvas_mode')
    legacy = Project.from_dict(data)
    assert legacy.processing_mode == 'full' and not legacy.is_passthrough
    assert Project.load(Path('examples/demo.aivsprite')).processing_mode == 'full'
    clip = p.import_animation(tmp_path / 'run.mp4')
    assert not clip.is_passthrough and clip.select_animation(p.animation_id).is_keyed_passthrough


def test_1536_to_512_keeps_both_moving_frames_on_shared_source_canvas(tmp_path, monkeypatch):
    source = tmp_path / 'large.mp4'
    source.write_bytes(b'large keyed source fixture')
    p = Project(source_video=str(source), video=VideoInfo(1536, 1536, 24, '24/1', 2, 2/24))
    p.set_processing_mode('keyed_passthrough')
    p.sprite_cell.canvas_mode = 'normalize_source'
    pipe = Pipeline(p, tmp_path / 'cache')
    monkeypatch.setattr(pipe, 'ensure_key', lambda: None)
    for i, (x, y) in enumerate(((0, 0), (1200, 1302))):
        rgba = np.zeros((1536, 1536, 4), np.uint8)
        rgba[..., :3] = (0, 255, 0)
        rgba[y:y+90, x:x+60] = (220, 40, 70, 255)
        save_rgba(frame_path(pipe.keyed, i), rgba)
    pipe.ensure_aligned()
    assert p.layout.normalize_scale == (1/3, 1/3) and p.layout.normalize_offset == (0, 0)
    provider = FinalFrameProvider(p, pipe.cache_dir)
    for i, bbox in enumerate(((0, 0, 20, 30), (400, 434, 420, 464))):
        frame = provider.get_final_frame(i)
        assert frame.shape == (512, 512, 4) and alpha_bbox(frame, 0, 0) == bbox
        assert np.all(frame[frame[..., 3] > 0, :3] == (220, 40, 70))
