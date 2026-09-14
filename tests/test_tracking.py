import cv2
import numpy as np

from app.core.root_tracker import RootTracker
from app.models.project import TrackingSettings


def textured_frame():
    image = np.zeros((160, 200, 4), np.uint8)
    rng = np.random.default_rng(42)
    image[40:120, 50:140, :3] = rng.integers(40, 230, (80, 90, 3), dtype=np.uint8)
    image[40:120, 50:140, 3] = 255
    return image


def test_tracks_translation_with_confidence():
    first = textured_frame()
    images = [cv2.warpAffine(first, np.float32([[1, 0, i * 3], [0, 1, i * 2]]), (200, 160)) for i in range(6)]
    result = RootTracker(TrackingSettings(roi_size=96)).track(6, lambda i: images[i], {0: (90, 80)})
    for i, frame in enumerate(result):
        assert np.allclose(frame.root, (90 + i * 3, 80 + i * 2), atol=0.3)
        assert frame.tracking_confidence > 0.7
        assert "Tracking Lost" not in frame.warnings


def test_no_features_freezes_and_manual_keyframe_restarts():
    image = np.full((100, 100, 4), 255, np.uint8)
    tracker = RootTracker(TrackingSettings())
    frames = tracker.track(4, lambda i: image, {0: (40, 40), 2: (60, 60)})
    assert frames[1].root == (40, 40) and frames[1].tracking_confidence == 0
    assert "Tracking Lost" in frames[1].warnings
    assert frames[2].manual and frames[2].root == (60, 60)
    assert frames[3].root == (60, 60)
