"""Create the small, re-openable example project shipped beside the source."""
from pathlib import Path

from app.models.project import Project
from app.core.pipeline import Pipeline
from app.utils.paths import cache_directory
from scripts.demo_video import make_demo


def main():
    directory = Path("examples").resolve()
    video = directory / "demo_green_screen.mp4"
    roots = make_demo(video)
    project_file = directory / "demo.aivsprite"
    project = Project(source_video=str(video))
    project.export_settings.animation_name = "demo_attack"
    project.root_keyframes = {0: roots[0], 12: roots[12]}
    pipe = Pipeline(project, cache_directory(project.project_id, project_file))
    pipe.import_video()
    pipe.build()
    project.save(project_file)
    print(project_file)


if __name__ == "__main__":
    main()
