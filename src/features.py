"""特征检测（M0 临时实现，红线 3 M0 豁免仅此函数）。

TODO(SELF-IMPL): M1 替换为自研 Harris / Shi-Tomasi（§8.1：Sobel 移位差分、
结构张量盒式滤波、R = λmin 或 det(H)−k·tr(H)²、NMS、argpartition 取 Top-N）。
契约签名：detect_corners(gray, max_corners=500) -> (N,2) float32。
"""

from __future__ import annotations

import cv2
import numpy as np

_DEFAULT_QUALITY = 0.01   # Shi-Tomasi 质量阈值（M0 临时）
_RETRY_QUALITY = 0.005    # §12 降级：角点数 < 20 时降低阈值重检一次
_MIN_DISTANCE = 10


def _detect_cv2(gray: np.ndarray, max_corners: int, quality: float) -> np.ndarray:
    pts = cv2.goodFeaturesToTrack(gray, max_corners, quality, _MIN_DISTANCE)
    if pts is None:
        return np.empty((0, 2), dtype=np.float32)
    return pts.reshape(-1, 2).astype(np.float32)


def detect_corners(gray: np.ndarray, max_corners: int = 500) -> np.ndarray:
    """M0 临时实现（cv2.goodFeaturesToTrack）。返回 (N,2) float32。"""
    return _detect_cv2(gray, max_corners, _DEFAULT_QUALITY)


def detect_corners_retry_low(gray: np.ndarray, max_corners: int = 500) -> np.ndarray:
    """§12 降级路径：降低阈值重检一次（M0 临时实现）。"""
    return _detect_cv2(gray, max_corners, _RETRY_QUALITY)
