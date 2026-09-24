"""稀疏光流（M0 临时实现，红线 3 M0 豁免仅此函数）。

TODO(SELF-IMPL): M1 替换为自研单层 Lucas-Kanade（§8.2：15×15 窗口、结构张量
2x2 正规方程批量向量化、迭代 ≤20 次或增量 <0.01 px、四条件 status 判定）。
契约签名：track_points(prev_gray, curr_gray, pts, win=15) -> (new_pts, status)。
"""

from __future__ import annotations

import cv2
import numpy as np


def track_points(prev_gray: np.ndarray, curr_gray: np.ndarray,
                 pts: np.ndarray, win: int = 15):
    """M0 临时实现（cv2.calcOpticalFlowPyrLK）。

    返回 (new_pts (M,2) float32, status (M,) bool)。
    """
    pts = np.asarray(pts, dtype=np.float32).reshape(-1, 2)
    if len(pts) == 0:
        return np.empty((0, 2), dtype=np.float32), np.zeros(0, dtype=bool)
    p1, st, _err = cv2.calcOpticalFlowPyrLK(
        prev_gray, curr_gray, pts.reshape(-1, 1, 2), None, winSize=(win, win))
    new_pts = p1.reshape(-1, 2).astype(np.float32)
    status = st.reshape(-1).astype(bool)
    return new_pts, status
