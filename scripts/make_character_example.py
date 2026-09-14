"""Create a 1536px / 22-frame Character Profile example from the shipped demo."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.pipeline import Pipeline
from app.core.character_space import prepare_character_calibration
from app.models.project import Project
from app.utils.paths import frame_path


def main():
    root = Path(__file__).resolve().parents[1]
    p = Project(source_video=str(root / "examples/normalized_512.mp4"))
    p.motion_settings.enabled = True
    p.export_settings.animation_name = "character_idle"
    p.export_settings.columns = 10
    p.sprite_cell.canvas_mode = "normalize_source"
    pipe = Pipeline(p, root / ".test-output/character-example")
    pipe.import_video()
    pipe.ensure_key()
    profile, placement, _ = prepare_character_calibration(pipe.cache.read(frame_path(pipe.keyed, 0)))
    p.character_profile = profile
    p.root_keyframes[0] = tuple((profile.canonical_root[a]-placement[a])/profile.character_scale for a in (0, 1))
    p.save(root / "examples/character_profile.aivsprite")
    print("Character example saved:", profile)


if __name__ == "__main__":
    main()
