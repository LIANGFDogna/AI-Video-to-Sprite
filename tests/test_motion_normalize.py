import numpy as np
import pytest
from PIL import Image

from app.core.canvas_normalizer import canvas_transform, normalize_canvas
from app.core.ground_detection import detect_ground
from app.core.motion import filter_trajectory, process_motion
from app.core.sprite_sheet import build_sheet
from app.models.frame_data import FrameData
from app.models.project import MotionSettings


def curve(points):
    return [FrameData(i, root=tuple(p), raw_root=tuple(p), tracking_confidence=1, ground=100.) for i, p in enumerate(points)]


def test_stationary_jitter_locks_output():
    rng = np.random.default_rng(5)
    frames = curve(np.array([50, 70])+rng.uniform(-3, 3, (30, 2)))
    process_motion(frames, MotionSettings(enabled=True, x_policy="LOCK", y_policy="LOCK"), 24)
    roots = np.array([np.array(f.raw_root)+f.correction for f in frames])
    assert np.ptp(roots, axis=0).max() < 1e-8


def test_dash_extract_retains_trend_and_displacement():
    frames = curve([(i*i*.3, 80) for i in range(22)])
    process_motion(frames, MotionSettings(enabled=True, x_policy="EXTRACT", y_policy="LOCK"), 24)
    assert all(frames[i+1].filtered_root[0] > frames[i].filtered_root[0] for i in range(21))
    assert frames[-1].root_motion[0] == pytest.approx(132.3)
    assert np.ptp([f.target_root[0] for f in frames]) < 1e-8


def test_jump_overrides_ground_lock_and_keeps_parabola():
    values = [(50, 100 - 2*i*(20-i)) for i in range(21)]
    frames = curve(values)
    settings = MotionSettings(enabled=True, preset="jump", takeoff_frame=0, apex_frame=10, landing_frame=20)
    process_motion(frames, settings, 24)
    assert frames[10].effective_policy[1] == "EXTRACT"
    assert frames[10].filtered_root[1] == pytest.approx(-100)
    assert frames[10].root_motion[1] == pytest.approx(-200)


def test_single_spike_removed_acceleration_retained():
    values = np.arange(21, dtype=float)**2*.2
    original = values.copy()
    values[10] += 80
    filtered, spikes = filter_trajectory(values)
    assert spikes == {10}
    assert abs(filtered[10]-original[10]) < .2
    assert np.max(np.abs(filtered-original)) < .25


def test_fast_parabola_apex_is_not_a_tracking_spike():
    values = (np.arange(21, dtype=float)-10)**2*20
    filtered, spikes = filter_trajectory(values, spike_threshold=8)
    assert not spikes
    assert filtered == pytest.approx(values)


def test_ground_ignores_sword_below_feet():
    rgba = np.zeros((200, 160, 4), np.uint8)
    rgba[30:130, 50:95] = (255, 40, 40, 255)
    rgba[60:180, 115:120] = (200, 200, 200, 255)
    bottom, roi = detect_ground(rgba, (72, 70))
    assert bottom == 129
    # Even a connected thin tip within a manual ROI cannot override broad foot support.
    rgba[130:180, 72:73] = (200, 200, 200, 255)
    assert detect_ground(rgba, (72, 70), (40, 75, 100, 190))[0] == 129


def test_loop_closes_visual_root_without_deleting_extracted_motion():
    frames = curve([(10+i*.8+np.sin(i*np.pi/5), 40) for i in range(21)])
    process_motion(frames, MotionSettings(enabled=True, loop_correction=True, x_policy="EXTRACT"), 24)
    assert frames[-1].filtered_root == pytest.approx(frames[0].filtered_root)
    assert frames[-1].root_motion[0] > 15


def test_source_canvas_1536_512_no_crop_no_color_bleed(tmp_path):
    image = np.zeros((1536, 1536, 4), np.uint8)
    image[..., :3] = (0, 255, 0)  # transparent RGB contamination must never bleed
    image[151:1001, 301:1202] = (240, 40, 25, 255)
    image[0:6, 0:6] = (240, 40, 25, 255)
    transform = canvas_transform(1536, 1536, 512, 512)
    assert transform.scale_x == transform.scale_y == pytest.approx(1/3)
    assert transform.point((768, 900)) == (256, 300)
    output = normalize_canvas(image, transform)
    assert output.shape == (512, 512, 4)
    assert output[0, 0, 3] == 255  # source-canvas corner preserved
    fractional = (output[..., 3] > 0) & (output[..., 3] < 255)
    assert fractional.any()
    assert np.min(output[fractional, 0]) >= 239
    assert np.max(output[fractional, 1]) <= 41
    paths = []
    for i in range(22):
        path = tmp_path / f"{i}.png"
        Image.fromarray(output).save(path)
        paths.append(path)
    build_sheet(paths, tmp_path / "sheet.png", 512, 512, 10)
    with Image.open(tmp_path / "sheet.png") as sheet:
        assert sheet.size == (5120, 1536)
        assert sheet.getpixel((1024+10, 1024+10))[3] == 0


def test_aspect_preserving_letterbox():
    t = canvas_transform(1536, 768, 512, 512)
    assert t.scale_x == t.scale_y == pytest.approx(1/3)
    assert t.offset_y == 128
