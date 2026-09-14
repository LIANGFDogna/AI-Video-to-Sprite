from dataclasses import asdict, replace
import json
import numpy as np
import pytest
from PIL import Image

from app.models.character_profile import CharacterProfile
from app.models.project import Project, VideoInfo, MotionSettings
from app.models.frame_data import FrameData
from app.core.character_space import apply_character_motion, review_reference_bounds, prepare_character_calibration
from app.core.motion import process_motion
from app.core.pipeline import Pipeline
from app.core.final_frame_provider import FinalFrameProvider
from app.exporters.root_motion_exporter import root_motion_data
from app.utils.paths import frame_path
from app.utils.cache import save_rgba


def test_handles_only_change_half_width_and_remain_symmetric():
    original = CharacterProfile()
    for x in (200, 100, 350, 480, -200, 256):
        changed = original.with_edge(x)
        l, top, r, bottom = changed.reference_box
        assert l == changed.ground_origin[0]-changed.reference_box_half_width
        assert r == changed.ground_origin[0]+changed.reference_box_half_width
        assert (l+r)/2 == original.ground_origin[0]
        assert bottom == original.ground_origin[1]
        a, b = asdict(original), asdict(changed)
        a.pop("reference_box_half_width")
        b.pop("reference_box_half_width")
        assert a == b


def test_first_canonical_x_is_forced_to_axis_and_bad_profile_rejected():
    p = CharacterProfile().with_canonical_root(427.75, 250.125)
    assert p.canonical_root == (256., 250.125)
    assert p.canonical_root_offset == (0, -229.875)
    with pytest.raises(ValueError, match="Y Axis"):
        CharacterProfile(canonical_root=(257., 250.))


def test_all_animations_inherit_one_profile_and_survive_save_switch(tmp_path):
    p = Project(source_video=str(tmp_path / "idle.mp4"), character_profile=CharacterProfile())
    p.root_keyframes[0] = (750, 900)
    for name in ("run", "ground_attack", "jump"):
        new = p.import_animation(tmp_path / f"{name}.mp4")
        assert new.character_profile is p.character_profile
        assert new.character_profile.canonical_root == (256., 256.)
        assert not new.root_keyframes
        p = new
    path = tmp_path / "hero.aivsprite"
    p.save(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data["animations"]) == 3
    assert all("character_profile" not in item for item in data["animations"].values())
    assert "reference_box_half_width" in data["character_profile"]
    assert "left" not in data["character_profile"] and "right" not in data["character_profile"]
    p = Project.load(path)
    p.character_profile = p.character_profile.with_edge(500)
    switched = p.select_animation("default")
    assert switched.character_profile.reference_box_half_width == 244
    assert switched.character_profile.canonical_root == (256., 256.)
    assert switched.root_keyframes[0] == (750, 900)
    assert switched.source_video == str(tmp_path / "idle.mp4")


@pytest.mark.parametrize("preset", ["idle", "run", "ground_attack", "jump"])
def test_in_place_all_roots_use_canonical_never_alpha_center(preset):
    profile = CharacterProfile()
    frames = [FrameData(i, bbox=(10, 20, 1200+i*12, 1500), root=(500+i*20, 800-i*15), raw_root=(500+i*20, 800-i*15), ground=1400.) for i in range(10)]
    process_motion(frames, MotionSettings(enabled=True, preset=preset), 24)
    apply_character_motion(frames, profile)
    for f in frames:
        assert np.array(f.tracked_root)+f.character_correction == pytest.approx(profile.canonical_root)
        assert np.array(f.raw_root)+f.correction == pytest.approx(np.array(profile.canonical_root)/profile.character_scale)
    assert frames[-1].root_motion == pytest.approx((180, -135))


def test_calibration_proposes_ground_only_once():
    rgba = np.zeros((300, 300, 4), np.uint8)
    rgba[70:220, 120:190] = (220, 40, 70, 255)
    profile, placement, pixels = prepare_character_calibration(rgba, (300, 300))
    assert profile.character_scale == 1
    assert 219+placement[1] == profile.ground_origin[1]
    assert profile.canonical_root[0] == profile.ground_origin[0] == 150


def test_reference_overflow_warns_without_resizing_or_rebuilding_pixels(tmp_path, monkeypatch):
    source = tmp_path / "fixture.mp4"
    source.write_bytes(b"decoded fixture")
    info = VideoInfo(300, 300, 24, "24/1", 3, 3/24)
    def decode(path, directory, info, progress, cancel):
        for i in range(3):
            rgba = np.full((300, 300, 4), (0, 255, 0, 255), np.uint8)
            rgba[80:230, 100+i*10:170+i*10] = (220, 40, 60, 255)
            if i:
                rgba[100:110, 160+i*10:260] = (200, 60, 60, 255)  # attack changes bounds radically
            save_rgba(frame_path(directory, i), rgba)
        return 3
    monkeypatch.setattr("app.core.pipeline.probe_video", lambda *a: info)
    monkeypatch.setattr("app.core.pipeline.decode_video", decode)
    profile = CharacterProfile((300, 300), 1., (150., 280.), (150., 190.), 40.)
    p = Project(source_video=str(source), character_profile=profile)
    p.root_keyframes = {i: (135+i*10, 150) for i in range(3)}
    pipe = Pipeline(p, tmp_path / "cache")
    pipe.import_video()
    pipe.build()
    assert all(f.cell_root == profile.canonical_root for f in p.tracking_results)
    assert "Outside Character Reference Box" in p.tracking_results[1].warnings
    assert not p.layout.clipped_frames
    paths = [frame_path(pipe.aligned, i) for i in range(3)]
    before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths]
    p.character_profile = profile.with_edge(300)
    pipe.build()
    assert before == [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths]
    assert all("Outside Character Reference Box" not in f.warnings for f in p.tracking_results)
    assert all(f.cell_root == profile.canonical_root for f in p.tracking_results)
    assert p.scale == 1 and p.character_profile.character_scale == 1
    assert p.character_profile.ground_origin == profile.ground_origin
    assert FinalFrameProvider(p, pipe.cache_dir).get_final_frame(1).shape == (300, 300, 4)
    motion = root_motion_data(p)
    assert motion["frames"][-1]["raw_cumulative_x"] == 20
    assert motion["frames"][-1]["cumulative_x"] == pytest.approx(20)
