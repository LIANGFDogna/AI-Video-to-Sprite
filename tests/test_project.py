import pytest
from app.models.project import Project
from app.models.frame_data import FrameData


def test_project_round_trip(tmp_path):
    project = Project(source_video=str(tmp_path / "素材.mp4"))
    project.video.frame_count = 20
    project.root_keyframes = {0: (12.5, 21.0), 10: (18.0, 25.0)}
    project.tracking_results = [FrameData(0, root=(12.5, 21), tracking_confidence=1)]
    path = tmp_path / "动画.aivsprite"
    project.save(path)
    loaded = Project.load(path)
    assert loaded.source_video == project.source_video
    assert loaded.root_keyframes == project.root_keyframes
    assert loaded.tracking_results[0].tracking_confidence == 1


def test_invalid_project_rejected():
    p = Project()
    p.scale = 8
    with pytest.raises(ValueError, match="Scale"):
        p.validate()
