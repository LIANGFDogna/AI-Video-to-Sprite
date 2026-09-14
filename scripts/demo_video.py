"""Generate a reproducible green-screen animation for validation and a first-run demo."""
from pathlib import Path
import subprocess
import tempfile

import cv2
import numpy as np
from PIL import Image

from app.utils.ffmpeg import CREATE_FLAGS, executable


def make_demo(destination: Path, count=24, size=320, fps=12) -> dict[int, tuple[float, float]]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    roots = {}
    rng = np.random.default_rng(7)
    texture = rng.integers(80, 220, (65, 40, 3), dtype=np.uint8)
    texture[..., 1] = 35
    with tempfile.TemporaryDirectory(prefix="aivsprite-demo-") as folder:
        for index in range(count):
            rgb = np.full((320, 320, 3), (8, 224, 24), np.uint8)
            dx, dy = index * 2 - 20, round(4 * np.sin(index / 4))
            base = np.zeros((320, 320, 4), np.uint8)
            cv2.circle(base, (150, 91), 27, (233, 172, 127, 255), -1)
            cv2.rectangle(base, (128, 70), (173, 84), (80, 95, 142, 255), -1)
            cv2.circle(base, (141, 92), 3, (28, 31, 39, 255), -1)
            cv2.circle(base, (159, 92), 3, (28, 31, 39, 255), -1)
            cv2.rectangle(base, (130, 120), (169, 184), (190, 40, 61, 255), -1)
            base[120:185, 130:170, :3] = texture
            cv2.line(base, (128, 126), (109, 177), (205, 55, 75, 255), 17)
            reach = round(40 * np.sin(index / 23 * np.pi))
            cv2.line(base, (171, 128), (195+reach, 141), (205, 55, 75, 255), 17)
            cv2.line(base, (195+reach, 141), (216+reach, 89), (210, 221, 244, 255), 7)
            cv2.line(base, (192+reach, 126), (211+reach, 135), (225, 172, 69, 255), 5)
            cv2.rectangle(base, (132, 185), (148, 239), (76, 89, 135, 255), -1)
            cv2.rectangle(base, (153, 185), (169, 239), (76, 89, 135, 255), -1)
            cv2.rectangle(base, (125, 236), (148, 247), (53, 56, 76, 255), -1)
            cv2.rectangle(base, (153, 236), (177, 247), (53, 56, 76, 255), -1)
            shifted = cv2.warpAffine(base, np.float32([[1, 0, dx], [0, 1, dy]]), (320, 320))
            mask = shifted[..., 3] > 0
            rgb[mask] = shifted[mask, :3]
            if size != 320:
                rgb = cv2.resize(rgb, (size, size), interpolation=cv2.INTER_NEAREST)
            Image.fromarray(rgb).save(Path(folder) / f"frame_{index:04d}.png")
            roots[index] = ((150.0 + dx)*size/320, (153.0 + dy)*size/320)
        subprocess.run([executable("ffmpeg"), "-v", "error", "-y", "-framerate", str(fps), "-i", str(Path(folder) / "frame_%04d.png"),
            "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", str(destination)], check=True, creationflags=CREATE_FLAGS)
    return roots


if __name__ == "__main__":
    make_demo(Path("examples/demo_green_screen.mp4"))
