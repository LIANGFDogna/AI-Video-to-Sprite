from __future__ import annotations

from fractions import Fraction
import json
import logging
from pathlib import Path
import subprocess
import threading
import time

from app.models.project import VideoInfo
from app.utils.ffmpeg import CREATE_FLAGS, check_cancel, executable, run_capture

log = logging.getLogger("aivsprite.decoder")
SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


def probe_video(path: Path, cancel: threading.Event | None = None) -> VideoInfo:
    if not path.is_file():
        raise FileNotFoundError(f"Source video is missing: {path}")
    executable("ffmpeg")
    data = json.loads(run_capture([executable("ffprobe"), "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,avg_frame_rate,r_frame_rate,nb_frames,duration:format=duration", "-of", "json", str(path)], cancel))
    if not data.get("streams"):
        raise ValueError("No video stream was found")
    stream = data["streams"][0]
    rational = stream.get("avg_frame_rate", "0/1")
    if rational in ("0/0", "0/1", "N/A"):
        rational = stream.get("r_frame_rate", "0/1")
    try:
        fps = float(Fraction(rational))
    except (ValueError, ZeroDivisionError):
        fps = 0.0
    if fps <= 0:
        raise ValueError("The video does not report a usable frame rate")
    duration = stream.get("duration") or data.get("format", {}).get("duration", 0)
    duration = float(duration) if duration != "N/A" else 0.0
    count = stream.get("nb_frames", "0")
    return VideoInfo(int(stream["width"]), int(stream["height"]), fps, rational,
                     int(count) if count != "N/A" else 0, duration)


def decode_video(path: Path, output: Path, info: VideoInfo, progress=lambda n, total, message: None,
                 cancel: threading.Event | None = None) -> int:
    """Decode each frame once. No output frame-rate resampling or autorotation."""
    check_cancel(cancel)
    output.mkdir(parents=True, exist_ok=True)
    progress_path = output / "ffmpeg-progress.txt"
    error_path = output / "ffmpeg-errors.txt"
    args = [executable("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-noautorotate", "-i", str(path),
            "-map", "0:v:0", "-an", "-sn", "-dn", "-fps_mode", "passthrough", "-start_number", "0",
            "-pix_fmt", "rgb24", "-progress", str(progress_path), str(output / "frame_%06d.png")]
    with error_path.open("wb") as errors, subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=errors, creationflags=CREATE_FLAGS) as process:
        try:
            while process.poll() is None:
                check_cancel(cancel)
                count = 0
                if progress_path.exists():
                    lines = progress_path.read_text(encoding="utf-8", errors="replace").splitlines()
                    for line in reversed(lines):
                        if line.startswith("frame="):
                            count = int(line.split("=", 1)[1])
                            break
                progress(count, info.frame_count, "Decoding original frames")
                if cancel:
                    cancel.wait(0.15)
                else:
                    time.sleep(0.15)
            check_cancel(cancel)
        except BaseException:
            process.kill()
            process.wait()
            raise
    if process.returncode:
        message = error_path.read_text(encoding="utf-8", errors="replace")
        log.error("FFmpeg decode failure: %s", message)
        raise RuntimeError(message[-6000:])
    count = sum(1 for _ in output.glob("frame_*.png"))
    if count == 0:
        raise ValueError("FFmpeg decoded no frames")
    if info.frame_count and count != info.frame_count:
        log.warning("Metadata frame count %s differs from decoded %s; using actual decoded count", info.frame_count, count)
    progress(count, count, "Decode complete")
    return count
