from __future__ import annotations

import logging
import math

import cv2
import numpy as np

from app.core.alpha_utils import alpha_bbox, root_inside
from app.core.chroma_key import has_green_spill
from app.models.frame_data import FrameData
from app.models.project import TrackingSettings
from app.utils.ffmpeg import check_cancel

log = logging.getLogger("aivsprite.tracking")


class RootTracker:
    def __init__(self, settings: TrackingSettings):
        self.settings = settings
        self.last_metrics = {}
        self.last_method = "optical_flow"
        self.reference_root = None
        self.velocity = np.zeros(2)
        self.lost_count = 0

    def step(self, previous: np.ndarray, current: np.ndarray, root: tuple[float, float]) -> tuple[tuple[float, float], float, list]:
        self.last_metrics = {}
        candidate, confidence, features = self._flow(previous, current, root)
        self.last_method = "optical_flow"
        if confidence < self.settings.min_confidence and self.settings.fallback:
            fallback, score = self._phase(previous, current, root)
            if score >= self.settings.min_confidence:
                candidate, confidence, self.last_method = fallback, score, "phase_correlation"
        if confidence < self.settings.min_confidence:
            self.lost_count += 1
            decay = max(0, 1-self.lost_count/3)
            candidate = tuple(np.clip(np.array(root)+self.velocity*decay, [0, 0], [current.shape[1]-1, current.shape[0]-1]))
            self.last_method = "prediction"
        else:
            self.velocity = np.array(candidate)-root
            self.lost_count = 0
        return tuple(float(v) for v in candidate), confidence, features

    def _phase(self, previous, current, root):
        size = self.settings.roi_size or max(64, min(512, int(min(previous.shape[:2])*.35)))
        x0, y0 = max(0, int(root[0]-size/2)), max(0, int(root[1]-size/2))
        x1, y1 = min(previous.shape[1], x0+size), min(previous.shape[0], y0+size)
        if self.settings.body_roi:
            reference = self.reference_root or root
            dx, dy = root[0]-reference[0], root[1]-reference[1]
            l, top, r, bottom = self.settings.body_roi
            x0, x1 = max(0, round(l+dx)), min(previous.shape[1], round(r+dx))
            y0, y1 = max(0, round(top+dy)), min(previous.shape[0], round(bottom+dy))
        if x1-x0 < 8 or y1-y0 < 8:
            return root, 0.0
        signals = []
        for image in (previous, current):
            crop = image[y0:y1, x0:x1]
            mask = crop[..., 3] > 128
            gray = cv2.cvtColor(crop[..., :3], cv2.COLOR_RGB2GRAY).astype(np.float32)
            if np.count_nonzero(mask) < 20 or float(gray[mask].std()) < 2:
                return root, 0.0
            signals.append((gray - float(gray[mask].mean())) * mask)
        if min(signals[0].shape) < 8:
            return root, 0.0
        window = cv2.createHanningWindow((x1-x0, y1-y0), cv2.CV_32F)
        shift, response = cv2.phaseCorrelate(signals[0], signals[1], window)
        if not np.isfinite(shift).all() or np.linalg.norm(shift) > size*.4:
            return root, 0.0
        score = float(np.clip(response, 0, 1)) * .8
        self.last_metrics["phase_response"] = float(response)
        return (root[0]+shift[0], root[1]+shift[1]), score

    def _flow(self, previous: np.ndarray, current: np.ndarray, root):
        height, width = previous.shape[:2]
        size = self.settings.roi_size or min(256, max(64, int(min(height, width) * 0.2)))
        x, y = root
        mask = np.zeros((height, width), np.uint8)
        x0, x1 = max(0, int(x - size / 2)), min(width, int(x + size / 2))
        y0, y1 = max(0, int(y - size / 2)), min(height, int(y + size / 2))
        if self.settings.body_roi:
            reference = self.reference_root or root
            dx, dy = x-reference[0], y-reference[1]
            l, t, r, b = self.settings.body_roi
            x0, x1, y0, y1 = max(0, round(l+dx)), min(width, round(r+dx)), max(0, round(t+dy)), min(height, round(b+dy))
        if x1 <= x0 or y1 <= y0:
            return root, 0.0, []
        mask[y0:y1, x0:x1] = (previous[y0:y1, x0:x1, 3] > 128).astype(np.uint8) * 255
        mask = cv2.erode(mask, np.ones((3, 3), np.uint8))
        gray0 = cv2.cvtColor(previous[..., :3], cv2.COLOR_RGB2GRAY)
        gray1 = cv2.cvtColor(current[..., :3], cv2.COLOR_RGB2GRAY)
        points = cv2.goodFeaturesToTrack(gray0, maxCorners=self.settings.max_features, qualityLevel=0.01,
                                         minDistance=4, mask=mask, blockSize=5)
        if points is None or len(points) < 3:
            return root, 0.0, []
        next_points, status, _ = cv2.calcOpticalFlowPyrLK(gray0, gray1, points, None, winSize=(21, 21), maxLevel=3,
                        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01))
        if next_points is None:
            return root, 0.0, []
        back, back_status, _ = cv2.calcOpticalFlowPyrLK(gray1, gray0, next_points, None, winSize=(21, 21), maxLevel=3)
        if back is None:
            return root, 0.0, []
        forward = next_points.reshape(-1, 2)
        original = points.reshape(-1, 2)
        fb_error = np.linalg.norm(back.reshape(-1, 2) - original, axis=1)
        valid = status.ravel().astype(bool) & back_status.ravel().astype(bool) & (fb_error < 1.5)
        valid &= np.isfinite(forward).all(axis=1)
        coords = np.nan_to_num(forward).round().astype(np.int32)
        valid &= (coords[:, 0] >= 0) & (coords[:, 0] < width) & (coords[:, 1] >= 0) & (coords[:, 1] < height)
        safe = np.clip(coords, [0, 0], [width - 1, height - 1])
        valid &= current[safe[:, 1], safe[:, 0], 3] > 64
        if np.count_nonzero(valid) < 3:
            return root, 0.0, []
        matrix, inliers = cv2.estimateAffinePartial2D(original[valid], forward[valid], method=cv2.RANSAC,
                           ransacReprojThreshold=2.0, maxIters=2000, confidence=0.99, refineIters=10)
        if matrix is None or inliers is None or not np.isfinite(matrix).all():
            return root, 0.0, []
        keep = inliers.ravel().astype(bool)
        if self.settings.estimation == "translation":
            shift = np.median(forward[valid][keep]-original[valid][keep], axis=0) if keep.any() else np.zeros(2)
            matrix = np.array([[1, 0, shift[0]], [0, 1, shift[1]]], dtype=float)
        count = int(keep.sum())
        valid_ratio = np.count_nonzero(valid) / len(points)
        inlier_ratio = count / max(1, np.count_nonzero(valid))
        residual = np.linalg.norm(cv2.transform(original[valid].reshape(-1, 1, 2), matrix).reshape(-1, 2)-forward[valid], axis=1)
        error = float(np.median(residual[keep])) if count else 100.0
        region = np.zeros_like(mask)
        region[y0:y1, x0:x1] = 1
        moved = cv2.warpAffine((previous[..., 3] > 128).astype(np.uint8)*region, matrix, (width, height)) > 0
        moved_roi = cv2.warpAffine(region, matrix, (width, height)) > 0
        observed = (current[..., 3] > 128) & moved_roi
        overlap = np.count_nonzero(moved & observed) / max(1, np.count_nonzero(moved | observed))
        self.last_metrics = {"valid_feature_ratio": float(valid_ratio), "ransac_inlier_ratio": float(inlier_ratio),
                             "reprojection_error": error, "alpha_overlap": float(overlap)}
        confidence = valid_ratio * inlier_ratio * min(1, count/8) * math.exp(-error/2) * math.sqrt(overlap)
        candidate = matrix @ np.array([root[0], root[1], 1.0])
        local_scale = float(np.linalg.norm(matrix[0, :2]))
        plausible = 0.8 <= local_scale <= 1.25 and np.linalg.norm(candidate - root) < size * 0.6
        plausible &= 0 <= candidate[0] < width and 0 <= candidate[1] < height
        if not plausible:
            confidence = 0.0
        features = [tuple(float(v) for v in point) for point in forward[valid][keep]]
        return tuple(float(v) for v in candidate), float(confidence), features

    def track(self, count: int, read_frame, keyframes: dict[int, tuple[float, float]], threshold=16,
              minimum_size=12, progress=lambda n, total, message: None, cancel=None) -> list[FrameData]:
        if 0 not in keyframes:
            raise ValueError("Select a Root on frame 0 in the Anchor editor before building sprites")
        frames = []
        previous = None
        root = keyframes[0]
        self.reference_root = root
        for index in range(count):
            check_cancel(cancel)
            current = read_frame(index)
            manual = index in keyframes
            if manual:
                root, confidence, features = tuple(keyframes[index]), 1.0, []
                self.velocity = np.zeros(2)
                self.lost_count = 0
                self.last_method, self.last_metrics = "manual", {}
            else:
                root, confidence, features = self.step(previous, current, root)
            bbox = alpha_bbox(current, threshold, minimum_size)
            warnings = []
            if bbox is None:
                warnings.append("Alpha Empty")
            if not root_inside(current, root, threshold):
                warnings.append("Root Outside Subject")
            if confidence < self.settings.min_confidence:
                warnings.append("Tracking Lost")
                log.warning("Tracking loss at frame %06d (confidence %.3f); fallback root %s", index, confidence, root)
            if has_green_spill(current):
                warnings.append("Green Spill")
            if self.last_method == "prediction":
                warnings.append("Motion Prediction")
            frames.append(FrameData(index, bbox, root, confidence, warnings, features, manual,
                                    raw_root=root, tracking_method=self.last_method, tracking_metrics=dict(self.last_metrics)))
            previous = current
            progress(index + 1, count, "Tracking root / alpha bounds")
        return frames
