from pathlib import Path
import threading

import numpy as np
from PIL import Image
import pytest

from app.core.sprite_sheet import build_sheet
from app.utils.cache import FrameCache
from app.utils.ffmpeg import Cancelled, executable
from app.models.project import Project


def test_missing_ffmpeg_reports_action(monkeypatch):
    monkeypatch.setenv("AIVSPRITE_FFMPEG", "Z:/nonexistent/ffmpeg.exe")
    with pytest.raises(RuntimeError, match="Install FFmpeg"):
        executable("ffmpeg")


def test_lru_obeys_byte_budget(tmp_path):
    for i in range(3):
        Image.new("RGBA", (16, 16), (i, 0, 0, 255)).save(tmp_path / f"{i}.png")
    cache = FrameCache(1500)
    for i in range(3):
        result = cache.read(tmp_path / f"{i}.png")
        assert result[0, 0, 0] == i
        assert not result.flags.writeable
    assert cache._bytes <= 1500 and len(cache._items) == 1
    too_small = FrameCache(100)
    too_small.read(tmp_path / "0.png")
    assert too_small._bytes == 0


def test_cancelled_sheet_does_not_publish_or_replace(tmp_path):
    path = tmp_path / "cell.png"
    Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(path)
    output = tmp_path / "sheet.png"
    original = b"previous completed sheet"
    output.write_bytes(original)
    event = threading.Event()
    def cancel(n, total, message):
        event.set()
    with pytest.raises(Cancelled):
        build_sheet([path, path], output, 8, 8, 2, cancel, event)
    assert output.read_bytes() == original
    assert not output.with_suffix(".tmp").exists()


def test_invalid_project_identifier_cannot_escape_cache():
    project = Project()
    project.project_id = "../../outside"
    with pytest.raises(ValueError, match="identifier"):
        project.validate()
