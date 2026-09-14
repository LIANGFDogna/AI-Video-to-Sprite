from pathlib import Path
import shutil
import subprocess

import numpy as np
from PIL import Image
import pytest

from app.core.chroma_key import chroma_key, estimate_background
from app.core.video_decoder import decode_video, probe_video
from app.models.project import ChromaSettings
from app.utils.ffmpeg import CREATE_FLAGS


def test_key_opaque_subject_clear_background_and_noise():
    rgb = np.full((80, 100, 3), (0, 230, 15), dtype=np.uint8)
    rgb[20:60, 30:70] = (220, 40, 40)
    rgb[2, 2] = (255, 0, 0)
    settings = ChromaSettings(green_color=estimate_background(rgb), edge_feather=0)
    out = chroma_key(rgb, settings)
    assert out.shape == (80, 100, 4)
    assert out[40, 40, 3] == 255
    assert out[0, 0, 3] == 0 and out[2, 2, 3] == 0
    assert tuple(settings.green_color) == (0, 230, 15)


def test_soft_edges_and_despill():
    rgb = np.full((50, 50, 3), (0, 255, 0), dtype=np.uint8)
    rgb[10:40, 10:40] = (180, 205, 70)
    s = ChromaSettings(tolerance=0.1, softness=0.6, edge_feather=0, noise_removal=0)
    out = chroma_key(rgb, s)
    assert 0 < out[25, 25, 3] < 255
    assert int(out[25, 25, 1]) - int(out[25, 25, 0]) < 25


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg unavailable")
def test_all_original_frames_unicode(tmp_path: Path):
    video = tmp_path / "测试 source.mkv"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=96x64:rate=30000/1001", "-frames:v", "13", "-c:v", "ffv1", str(video)], check=True, creationflags=CREATE_FLAGS)
    info = probe_video(video)
    assert info.width == 96 and info.height == 64
    assert abs(info.fps - 30000 / 1001) < 0.001
    output = tmp_path / "帧"
    assert decode_video(video, output, info) == 13
    assert [p.name for p in sorted(output.glob("*.png"))] == [f"frame_{i:06d}.png" for i in range(13)]
    with Image.open(output / "frame_000012.png") as image:
        assert image.size == (96, 64)
