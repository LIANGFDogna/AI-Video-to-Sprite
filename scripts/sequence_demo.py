"""Small reproducible, already aligned RGBA sequence; no FFmpeg required."""
from pathlib import Path
import numpy as np
from PIL import Image


def make_sequence(folder, count=22):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        frame = np.zeros((512, 512, 4), np.uint8)
        frame[..., :3] = (12, 240, 31)
        frame[140:360, 140:230] = (194, 57, 93, 255)
        frame[80:140, 155:215] = (233, 179, 143, 255)
        frame[210:225, 230:240+i*3] = (222, 167, 91, 192)
        frame[360:440, 150:180] = (68, 97, 146, 255)
        frame[360:440, 195:225] = (68, 97, 146, 255)
        frame[79, 155:215] = (233, 179, 143, 63)
        frame[0, 0] = (45, 62, 77, 5)
        Image.fromarray(frame).save(folder / f"{i:04d}.png")
    return folder


if __name__ == "__main__":
    from app.models.project import Project
    from app.core.pipeline import Pipeline
    root = Path(__file__).resolve().parents[1]
    folder = make_sequence(root / "examples/sequence_idle")
    p = Project().import_frame_sequence(folder)
    p.export_settings.columns = 10
    Pipeline(p, root / ".test-output/sequence-example-cache").import_sequence()
    p.save(root / "examples/sequence_idle.aivsprite")
