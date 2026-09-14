from pathlib import Path
import json
import shutil
import subprocess
import threading

import numpy as np
from PIL import Image
import pytest

from app.core.pipeline import Pipeline
from app.core.alpha_utils import alpha_bbox
from app.exporters.image_exporter import export_images
from app.models.project import Project
from app.utils.ffmpeg import Cancelled, CREATE_FLAGS
from app.utils.paths import frame_path


@pytest.fixture
def synthetic_video(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg unavailable")
    rng = np.random.default_rng(12)
    texture = rng.integers(40, 220, (60, 40, 3), dtype=np.uint8)
    texture[..., 1] = 30
    for i in range(10):
        rgb = np.full((128, 160, 3), (0, 230, 0), dtype=np.uint8)
        rgb[30+i:90+i, 50+i*2:90+i*2] = texture
        if i >= 5:
            rgb[45+i:50+i, 90+i*2:120+i*2] = (210, 70, 30)
        Image.fromarray(rgb).save(tmp_path / f"input_{i:03d}.png")
    video = tmp_path / "character 漂移.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-framerate", "24", "-i", str(tmp_path / "input_%03d.png"),
                    "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", str(video)], check=True, creationflags=CREATE_FLAGS)
    return video


def test_full_pipeline_export_and_cache(synthetic_video, tmp_path):
    p = Project(source_video=str(synthetic_video))
    pipe = Pipeline(p, tmp_path / "cache")
    pipe.import_video()
    pipe.ensure_key()
    assert p.video.frame_count == 10
    with Image.open(frame_path(pipe.keyed, 0)) as first:
        assert first.mode == "RGBA" and first.size == (160, 128)
    p.root_keyframes[0] = (70, 60)
    pipe.build()
    assert not p.layout.clipped_frames
    for i, f in enumerate(p.tracking_results):
        assert f.root[0] == pytest.approx(70 + 2*i, abs=0.6)
        bbox = alpha_bbox(pipe.cache.read(frame_path(pipe.aligned, i)))
        assert bbox[3] - 1 == p.layout.ground_baseline
    roots = [f.cell_root[0] for f in p.tracking_results]
    assert max(roots) - min(roots) < 0.001
    raw_time = frame_path(pipe.raw, 0).stat().st_mtime_ns
    key_time = frame_path(pipe.keyed, 0).stat().st_mtime_ns
    align_time = frame_path(pipe.aligned, 0).stat().st_mtime_ns
    p.export_settings.columns = 4
    pipe.build()
    assert frame_path(pipe.raw, 0).stat().st_mtime_ns == raw_time
    assert frame_path(pipe.keyed, 0).stat().st_mtime_ns == key_time
    assert frame_path(pipe.aligned, 0).stat().st_mtime_ns == align_time
    output = export_images(pipe, tmp_path / "export", godot=True)
    data = json.loads((output / "animation.json").read_text())
    assert data["frame_count"] == 10 and len(data["frames"]) == 10 and data["rows"] == 3
    with Image.open(output / "sprite_sheet.png") as sheet:
        assert sheet.size == (p.layout.width * 4, p.layout.height * 3)
    assert len(list((output / "frames").glob("*.png"))) == 10
    p.chroma_key_settings.tolerance += 0.01
    pipe.ensure_key()
    assert frame_path(pipe.raw, 0).stat().st_mtime_ns == raw_time
    assert frame_path(pipe.keyed, 0).stat().st_mtime_ns != key_time


def test_cancel_does_not_validate_partial_cache(synthetic_video, tmp_path):
    p = Project(source_video=str(synthetic_video))
    event = threading.Event()
    pipe = Pipeline(p, tmp_path / "cache", cancel=event)
    pipe.import_video()
    def stop(n, total, message):
        if "Extracting" in message and n == 2:
            event.set()
    pipe.progress = stop
    with pytest.raises(Cancelled):
        pipe.ensure_key()
    assert not (pipe.cache_dir / "key.json").exists()
    event.clear()
    pipe.progress = lambda *args: None
    pipe.ensure_key()
    assert (pipe.cache_dir / "key.json").is_file()
    assert frame_path(pipe.keyed, 9).exists()


def test_clipped_exports_require_explicit_acceptance(synthetic_video, tmp_path):
    p = Project(source_video=str(synthetic_video))
    p.root_keyframes[0] = (70, 60)
    p.sprite_cell.mode = "CUSTOM"
    p.sprite_cell.width, p.sprite_cell.height = 24, 24
    pipe = Pipeline(p, tmp_path / "cache")
    pipe.import_video()
    with pytest.raises(ValueError, match="FRAME CLIPPING DETECTED"):
        export_images(pipe, tmp_path / "refused")
    assert not (tmp_path / "refused").exists()
    output = export_images(pipe, tmp_path / "accepted", kind="frames", allow_clipping=True)
    assert len(list((output / "frames").glob("*.png"))) == 10
