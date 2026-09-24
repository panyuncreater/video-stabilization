"""自研单层 Lucas-Kanade 稀疏光流（§8.2），替代 M0 的 cv2.calcOpticalFlowPyrLK（红线 3）。

实现要点：
- 每个特征点 15×15 窗口，构建结构张量并解 2x2 正规方程（批量向量化，无逐点循环）；
- 迭代至多 20 次或位移增量 < 0.01 px 收敛；
- status 判定：窗口最小特征值 > 1e-4、平均光度残差 < 0.05（[0,1] 灰度尺度）、
  累计位移不超过窗口半径（7 px）、点邻域不出边界；
- 亚像素采样使用自研双线性插值。

契约：track_points(prev_gray, curr_gray, pts, win=15) -> (new_pts, status)。
"""

from __future__ import annotations

import numpy as np

from src.features import sobel_gradients

MAX_ITERS = 20
CONVERGE_EPS = 0.01     # 位移增量收敛阈值（px）
LAMBDA_MIN = 1e-4       # 结构张量最小特征值阈值
RESIDUAL_MAX = 0.05     # 平均光度残差阈值（[0,1] 尺度）
DET_EPS = 1e-12


def _sample_bilinear(img: np.ndarray, rows: np.ndarray, cols: np.ndarray) -> np.ndarray:
    """双线性采样 img[rows, cols]（rows/cols 为同形状浮点坐标数组，向量化）。"""
    h, w = img.shape
    r0 = np.floor(rows).astype(np.int64)
    c0 = np.floor(cols).astype(np.int64)
    wr = rows - r0
    wc = cols - c0
    r0c = np.clip(r0, 0, h - 1)
    c0c = np.clip(c0, 0, w - 1)
    r1c = np.clip(r0 + 1, 0, h - 1)
    c1c = np.clip(c0 + 1, 0, w - 1)
    return (img[r0c, c0c] * (1 - wr) * (1 - wc)
            + img[r0c, c1c] * (1 - wr) * wc
            + img[r1c, c0c] * wr * (1 - wc)
            + img[r1c, c1c] * wr * wc)


def track_points(prev_gray: np.ndarray, curr_gray: np.ndarray,
                 pts: np.ndarray, win: int = 15):
    """单层 LK 光流：返回 (new_pts (M,2) float32, status (M,) bool)。"""
    pts = np.asarray(pts, dtype=np.float64).reshape(-1, 2)
    n = len(pts)
    if n == 0:
        return np.empty((0, 2), dtype=np.float32), np.zeros(0, dtype=bool)

    prev = np.asarray(prev_gray, dtype=np.float32) / 255.0
    curr = np.asarray(curr_gray, dtype=np.float32) / 255.0
    h, w = prev.shape
    r = win // 2

    ix, iy = sobel_gradients(prev_gray)   # 导数尺度，灰度 [0,1]

    # 整数锚点与窗口网格（n, win, win）
    cy = np.rint(pts[:, 1]).astype(np.int64)
    cx = np.rint(pts[:, 0]).astype(np.int64)
    dy = np.arange(-r, r + 1, dtype=np.float64)
    dx = np.arange(-r, r + 1, dtype=np.float64)
    rows0 = np.broadcast_to(cy[:, None, None] + dy[None, :, None], (n, win, win))
    cols0 = np.broadcast_to(cx[:, None, None] + dx[None, None, :], (n, win, win))

    in_bounds = (cy - r >= 0) & (cy + r < h) & (cx - r >= 0) & (cx + r < w)

    prev_patch = _sample_bilinear(prev, rows0, cols0)
    ix_patch = _sample_bilinear(ix, rows0, cols0)
    iy_patch = _sample_bilinear(iy, rows0, cols0)

    # 结构张量（窗口求和）
    gxx = np.sum(ix_patch * ix_patch, axis=(1, 2))
    gxy = np.sum(ix_patch * iy_patch, axis=(1, 2))
    gyy = np.sum(iy_patch * iy_patch, axis=(1, 2))
    det_g = gxx * gyy - gxy * gxy
    # 2x2 对称矩阵最小特征值（闭式解）
    lam_min = 0.5 * ((gxx + gyy) - np.sqrt(np.maximum((gxx - gyy) ** 2 + 4 * gxy * gxy, 0.0)))

    disp = np.zeros((n, 2), dtype=np.float64)
    residual = np.full(n, np.inf)
    ok = (det_g > DET_EPS) & (lam_min > LAMBDA_MIN) & in_bounds

    # 迭代解 2x2 正规方程 G·d = -b（批量向量化，无逐点循环）
    for _ in range(MAX_ITERS):
        cur_patch = _sample_bilinear(curr, rows0 + disp[:, 1:2, None],
                                     cols0 + disp[:, 0:1, None])
        it = cur_patch - prev_patch
        bx = np.sum(ix_patch * it, axis=(1, 2))
        by = np.sum(iy_patch * it, axis=(1, 2))
        safe = np.where(det_g > DET_EPS, det_g, 1.0)
        dx_v = -(gyy * bx - gxy * by) / safe
        dy_v = -(gxx * by - gxy * bx) / safe
        step = np.where(ok[:, None], np.stack([dx_v, dy_v], axis=1), 0.0)
        disp = disp + step
        residual = np.abs(it).mean(axis=(1, 2))
        if float(np.max(np.linalg.norm(step, axis=1))) < CONVERGE_EPS:
            break

    disp_norm = np.linalg.norm(disp, axis=1)
    status = (ok
              & (residual < RESIDUAL_MAX)
              & (disp_norm <= r)
              & in_bounds
              & (pts[:, 0] + disp[:, 0] >= 0) & (pts[:, 0] + disp[:, 0] < w)
              & (pts[:, 1] + disp[:, 1] >= 0) & (pts[:, 1] + disp[:, 1] < h))

    return (pts + disp).astype(np.float32), status
