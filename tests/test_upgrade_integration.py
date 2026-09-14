import copy
import json
from pathlib import Path
import numpy as np
import pytest
from PIL import Image

from app.core.pipeline import Pipeline
from app.core.final_frame_provider import FinalFrameProvider
from app.core.root_tracker import RootTracker
from app.exporters.image_exporter import export_images
from app.models.project import Project, VideoInfo, TrackingSettings
from app.utils.cache import save_rgba
from app.utils.paths import frame_path


@pytest.fixture
def normalized(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"deterministic decoded source fixture")
    info = VideoInfo(width=1536, height=1536, fps=24, fps_rational="24/1", frame_count=4, duration=4/24)
    texture = np.random.default_rng(8).integers(30, 245, (300, 180, 3), dtype=np.uint8)
    texture[..., 1] = 30
    def decode(path, directory, info, progress, cancel):
        for i in range(4):
            rgba = np.full((1536, 1536, 4), (0, 230, 0, 255), np.uint8)
            rgba[600:900, 650+i*6:830+i*6, :3] = texture
            save_rgba(frame_path(directory, i), rgba)
        return 4
    monkeypatch.setattr("app.core.pipeline.probe_video", lambda *a: copy.deepcopy(info))
    monkeypatch.setattr("app.core.pipeline.decode_video", decode)
    p = Project(source_video=str(source))
    p.root_keyframes[0] = (740, 750)
    p.motion_settings.enabled = True
    p.motion_settings.x_policy = "EXTRACT"
    p.motion_settings.y_policy = "LOCK"
    p.sprite_cell.canvas_mode = "normalize_source"
    p.export_settings.columns = 3
    pipe = Pipeline(p, tmp_path / "cache")
    pipe.import_video()
    pipe.build()
    return pipe


def test_normalize_pipeline_provider_export_same_pixels_and_units(normalized, tmp_path):
    pipe, p = normalized, normalized.project
    provider = FinalFrameProvider(p, pipe.cache_dir)
    assert p.layout.width == p.layout.height == 512
    assert not p.layout.clipped_frames
    assert p.tracking_results[-1].raw_root[0] == pytest.approx(758, abs=.5)
    assert all(f.cell_root == pytest.approx((740/3, 250), abs=.01) for f in p.tracking_results)
    assert provider.get_source_keyed_frame(0).shape == (1536, 1536, 4)
    with Image.open(frame_path(pipe.source_aligned, 0)) as image:
        assert image.size == (1536, 1536)
    exported = export_images(pipe, tmp_path / "output", godot=True)
    metadata = json.loads((exported / "animation.json").read_text())
    assert metadata["cell_width"] == metadata["cell_height"] == 512
    assert metadata["scale"] == pytest.approx(1/3)
    motion = json.loads((exported / "root_motion.json").read_text())
    assert motion["frames"][-1]["cumulative_x"] == pytest.approx(6, abs=.2)
    for i, f in enumerate(p.tracking_results):
        with Image.open(exported / "frames" / f"{i:04d}.png") as image:
            assert np.array_equal(provider.get_final_frame(i), np.array(image))
        assert metadata["frames"][i]["raw_root"] == pytest.approx(np.array(f.raw_root)/3)
        assert metadata["frames"][i]["ground"] == pytest.approx((f.ground+f.correction[1])/3)
    with Image.open(exported / "sprite_sheet.png") as image:
        assert image.size == (1536, 1024)
        assert image.getpixel((600, 600))[3] == 0


def test_target_change_reuses_source_processing_and_invalidates_provider(normalized):
    pipe, p = normalized, normalized.project
    provider = FinalFrameProvider(p, pipe.cache_dir)
    provider.get_final_frame(0)
    paths = [frame_path(d, 0) for d in (pipe.raw, pipe.keyed, pipe.source_aligned)]
    paths += [pipe.cache_dir / "root.json", pipe.cache_dir / "motion.json"]
    times = [path.stat().st_mtime_ns for path in paths]
    p.sprite_cell.target_width = p.sprite_cell.target_height = 256
    pipe.build()
    assert [path.stat().st_mtime_ns for path in paths] == times
    with pytest.raises(RuntimeError, match="changed"):
        provider.get_final_frame(0)
    assert FinalFrameProvider(p, pipe.cache_dir).get_final_frame(0).shape == (256, 256, 4)


def test_character_profile_1536_to_512_exact_axis_and_pixel_export(normalized, tmp_path):
    from app.models.character_profile import CharacterProfile
    pipe, p = normalized, normalized.project
    p.character_profile = CharacterProfile(canonical_root=(256., 300.125), reference_box_half_width=100.)
    pipe.build()
    provider = FinalFrameProvider(p, pipe.cache_dir)
    assert p.layout.target_root == (256., 300.125)
    assert p.layout.normalize_scale == (1/3, 1/3)
    assert all(f.cell_root == p.character_profile.canonical_root for f in p.tracking_results)
    assert provider.get_source_keyed_frame(0).shape == (1536, 1536, 4)
    out = export_images(pipe, tmp_path / "character-export", godot=True)
    metadata = json.loads((out / "animation.json").read_text())
    assert metadata["character_profile"]["canonical_root"] == [256., 300.125]
    assert metadata["motion_policy"] == {"x": "EXTRACT", "y": "EXTRACT"}
    assert all(f["root"] == [256., 300.125] for f in metadata["frames"])
    for i in range(4):
        with Image.open(out / "frames" / f"{i:04d}.png") as image:
            assert image.size == (512, 512)
            assert np.array_equal(np.array(image), provider.get_final_frame(i))


def test_phase_fallback_mask_and_prediction(monkeypatch):
    rng = np.random.default_rng(5)
    texture = rng.integers(30, 220, (50, 40, 3), dtype=np.uint8)
    frames = []
    for offset in (0, 3):
        image = np.zeros((128, 128, 4), np.uint8)
        image[35:85, 40+offset:80+offset, :3] = texture
        image[35:85, 40+offset:80+offset, 3] = 255
        # Strong transparent background noise must not be detected as body features.
        image[image[..., 3] == 0, :3] = rng.integers(0, 255, (np.count_nonzero(image[..., 3] == 0), 3), dtype=np.uint8)
        frames.append(image)
    tracker = RootTracker(TrackingSettings(roi_size=96))
    root, score, features = tracker.step(*frames, (60, 60))
    assert root == pytest.approx((63, 60), abs=.5)
    assert all(frames[1][round(y), round(x), 3] > 0 for x, y in features)
    assert set(tracker.last_metrics) >= {"valid_feature_ratio", "ransac_inlier_ratio", "reprojection_error", "alpha_overlap"}
    monkeypatch.setattr("cv2.goodFeaturesToTrack", lambda *a, **k: None)
    root, score, _ = tracker.step(*frames, (60, 60))
    assert tracker.last_method == "phase_correlation"
    assert root == pytest.approx((63, 60), abs=.7)
    assert score >= tracker.settings.min_confidence
    blank = np.zeros_like(frames[0])
    predicted, score, _ = tracker.step(blank, blank, root)
    assert tracker.last_method == "prediction" and score < tracker.settings.min_confidence
    assert 0 < predicted[0]-root[0] < 3
