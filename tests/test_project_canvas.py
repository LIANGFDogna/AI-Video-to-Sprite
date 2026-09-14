from dataclasses import asdict
import json
from pathlib import Path

import numpy as np
import pytest

from app.core.canvas_fit import CanvasFit
from app.core.pipeline import Pipeline
from app.core.final_frame_provider import FinalFrameProvider
from app.core.project_workspace import create_project_workspace
from app.exporters.image_exporter import export_images
from app.models.project import Project, VideoInfo
from app.models.character_profile import CharacterProfile
from app.utils.cache import save_rgba
from app.utils.rgba_image import read_rgba
from app.utils.paths import frame_path


@pytest.mark.parametrize('source,pad,crop', [
    ((1024, 1536), (256, 0, 256, 0), (0, 0, 0, 0)),
    ((1920, 1536), (0, 0, 0, 0), (192, 0, 192, 0)),
    ((1536, 1024), (0, 256, 0, 256), (0, 0, 0, 0)),
    ((1536, 1920), (0, 0, 0, 0), (0, 192, 0, 192)),
    ((1920, 1080), (0, 228, 0, 228), (192, 0, 192, 0)),
])
def test_center_crop_pad_examples(source, pad, crop):
    fit = CanvasFit(source, (1536, 1536))
    assert fit.padding == pad and fit.crop == crop
    image = np.full((source[1], source[0], 4), (27, 180, 93, 201), np.uint8)
    image[source[1]//2, source[0]//2] = (255, 12, 38, 255)
    result = fit.apply(image)
    assert result.shape == (1536, 1536, 4)
    assert tuple(result[768, 768]) == (255, 12, 38, 255)
    x, y = pad[:2]
    w, h = min(source[0], 1536), min(source[1], 1536)
    assert np.array_equal(result[y:y+h, x:x+w], image[crop[1]:crop[1]+h, crop[0]:crop[0]+w])
    exterior = np.ones((1536, 1536), bool)
    exterior[y:y+h, x:x+w] = False
    assert np.all(result[exterior] == 0)


def test_odd_difference_never_interpolates_and_keeps_uint16():
    image = np.arange(7*9*4, dtype=np.uint16).reshape(7, 9, 4)*257
    fit = CanvasFit((9, 7), (6, 10))
    assert fit.crop == (1, 0, 2, 0) and fit.padding == (0, 1, 0, 2)
    output = fit.apply(image)
    assert output.dtype == np.uint16
    assert np.array_equal(output[1:8], image[:, 1:7])
    assert not output[0].any() and not output[8:].any()


def test_project_fields_template_custom_legacy_and_animation_inheritance(tmp_path):
    p, path = create_project_workspace(tmp_path, 'Hero', project_canvas=(1024, 1536))
    assert p.project_canvas == (1024, 1536) and p.canvas_fit_mode == 'center_crop_or_pad'
    assert not p.character_profile and not p.root_keyframes
    saved = json.loads(path.read_text(encoding='utf-8'))
    assert saved['project_canvas_width'] == 1024 and saved['project_canvas_height'] == 1536
    p = p.import_animation(tmp_path / 'idle.mp4')
    p.original_size = (1920, 1080)
    q = p.import_frame_sequence(tmp_path / 'jump')
    assert q.project_canvas == p.project_canvas and 'project_canvas_width' not in q.animations[p.animation_id]
    q.save(path)
    restored = Project.load(path).select_animation(p.animation_id)
    assert restored.project_canvas == (1024, 1536) and restored.original_size == (1920, 1080)
    assert Project.from_dict({}).project_canvas is None
    assert Project.load(Path('examples/demo.aivsprite')).canvas_fit_mode == 'none'


def test_mixed_sequence_fits_each_original_center_not_alpha_or_max_canvas(tmp_path, monkeypatch):
    folder = tmp_path / 'run'
    folder.mkdir()
    sources = []
    for i, (w, h) in enumerate(((20, 32), (40, 16))):
        frame = np.zeros((h, w, 4), np.uint16)
        frame[2:8, 5:9] = (50000, 12345, 60000, 37000)
        save_rgba(folder / f'{i}.png', frame)
        sources.append(frame)
    p, _ = create_project_workspace(tmp_path, 'Hero', project_canvas=(32, 32))
    p.character_profile = CharacterProfile()
    p = p.import_frame_sequence(folder)
    pipe = Pipeline(p, tmp_path / 'cache')
    for name in ('ensure_motion', 'ensure_roots', 'ensure_source_aligned'):
        monkeypatch.setattr(pipe, name, lambda: pytest.fail('Content alignment called'))
    pipe.build()
    assert (p.video.width, p.video.height) == (32, 32)
    assert p.sequence_sizes == [(20, 32), (40, 16)]
    first = read_rgba(frame_path(pipe.raw, 0))
    second = read_rgba(frame_path(pipe.raw, 1))
    assert first.dtype == second.dtype == np.uint16
    assert np.array_equal(first[:, 6:26], sources[0])
    assert np.array_equal(second[8:24], sources[1][:, 4:36])
    assert not first[:, :6].any() and not second[:8].any()
    provider = FinalFrameProvider(p, pipe.cache_dir)
    expected = np.zeros((32, 32, 4), np.uint8)
    expected[2:8, 11:15] = (195, 48, 233, 144)
    assert np.array_equal(provider.get_final_frame(0), expected)
    p.export_settings.columns = 2
    export_images(pipe, tmp_path / 'export', godot=True)
    assert np.array_equal(read_rgba(tmp_path / 'export/frames/0000.png'), expected)
    metadata = json.loads((tmp_path / 'export/animation.json').read_text())
    assert metadata['project_canvas'] == [32, 32]
    assert metadata['frames'][0]['bbox'] == [11, 2, 15, 8]
    assert metadata['frames'][1]['bbox'] == [1, 10, 5, 16]
    old = pipe.raw_signature()
    p.project_canvas_width = 34
    assert old != pipe.raw_signature()
    pipe.build()
    assert p.layout.width == 34


def test_video_green_pad_before_key_and_roots_use_fitted_coordinates(tmp_path, monkeypatch):
    path = tmp_path / 'dash.mp4'
    path.write_bytes(b'fixture')
    original = np.full((48, 64, 4), (8, 224, 24, 255), np.uint8)
    original[12:28, 20:30] = (220, 20, 60, 255)
    calls = []
    def decode(path, directory, info, progress, cancel):
        calls.append('decode')
        save_rgba(frame_path(directory, 0), original)
        return 1
    monkeypatch.setattr('app.core.pipeline.probe_video', lambda *a: VideoInfo(64, 48, 24, '24/1', 1, 1/24))
    monkeypatch.setattr('app.core.pipeline.decode_video', decode)
    p = Project(source_video=str(path), project_canvas_width=48, project_canvas_height=64, canvas_fit_mode='center_crop_or_pad')
    p.chroma_key_settings.edge_feather = 0
    p.chroma_key_settings.noise_removal = 0
    pipe = Pipeline(p, tmp_path / 'cache')
    pipe.import_video()
    assert p.original_size == (64, 48) and (p.video.width, p.video.height) == (48, 64)
    raw = read_rgba(frame_path(pipe.raw, 0))
    assert np.all(raw[:8] == (8, 224, 24, 255))
    assert np.array_equal(raw[8:56], original[:, 8:56])
    pipe.ensure_key()
    keyed = read_rgba(frame_path(pipe.keyed, 0))
    assert not keyed[:8, :, 3].any() and keyed[20, 12, 3] == 255
    p.root_keyframes[0] = (16, 25)
    pipe.ensure_roots()
    assert p.tracking_results[0].root == (16, 25)
    assert p.tracking_results[0].bbox == (12, 20, 22, 36)
    p.character_profile = CharacterProfile(canvas_size=(48, 64), character_scale=1., ground_origin=(24., 60.), canonical_root=(24., 30.))
    pipe.build()
    assert p.tracking_results[0].cell_root == (24., 30.)
    assert p.tracking_results[0].tracked_root == (16., 25.)
    p.set_processing_mode('keyed_passthrough')
    pipe.build()
    provider = FinalFrameProvider(p, pipe.cache_dir)
    assert np.array_equal(provider.get_final_frame(0), keyed)
    export_images(pipe, tmp_path / 'out', godot=True)
    assert np.array_equal(read_rgba(tmp_path / 'out/frames/0000.png'), keyed)
    p.project_canvas_height = 66
    pipe.build()
    assert calls == ['decode']  # canvas edits reuse original decoded pixels
    assert p.video.height == 66
