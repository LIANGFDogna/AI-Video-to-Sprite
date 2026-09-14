from __future__ import annotations

import logging
import os
from pathlib import Path
import shutil
import subprocess
import threading

log = logging.getLogger("aivsprite.ffmpeg")
CREATE_FLAGS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


class Cancelled(Exception):
    """A user-requested cancellation, never a valid completed stage."""


def check_cancel(cancel: threading.Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise Cancelled("Processing cancelled")


def executable(name: str) -> str:
    override = os.environ.get(f"AIVSPRITE_{name.upper()}")
    found = shutil.which(override or name)
    if not found:
        raise RuntimeError(f"{name} was not found. Install FFmpeg (including ffprobe) and add its bin folder to PATH, or set AIVSPRITE_{name.upper()}.")
    return found


def run_capture(args: list[str], cancel: threading.Event | None = None) -> str:
    check_cancel(cancel)
    with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=CREATE_FLAGS) as process:
        try:
            while True:
                check_cancel(cancel)
                try:
                    stdout, stderr = process.communicate(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    continue
        except BaseException:
            process.kill()
            process.communicate()
            raise
    errors = stderr.decode("utf-8", errors="replace")
    if process.returncode:
        log.error("Process failed: %s\n%s", args[0], errors)
        raise RuntimeError(errors[-6000:] or f"{args[0]} failed ({process.returncode})")
    return stdout.decode("utf-8", errors="replace")
