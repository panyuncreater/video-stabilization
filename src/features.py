"""自研 Harris / Shi-Tomasi 角点检测（§8.1），替代 M0 的 cv2.goodFeaturesToTrack（红线 3）。

实现要点（全部 NumPy 向量化，禁 cv2.Sobel / boxFilter 等一切滤波封装）：
- 梯度：NumPy 移位差分实现 3x3 Sobel 核；
- 结构张量：Ixx / Ixy / Iyy 盒式滤波用滑窗和（积分图向量化）；
- 响应 R = det(H) − k·tr(H)²（k = 0.04）；
- 非极大值抑制：np.lib.stride_tricks.sliding_window_view 取局部最大；
- 阈值取 quality × R_max；
- 取前 N 个点用 np.argpartition（平均 O(N)，与全排序 O(N log N) 对比见 §10）。

契约：detect_corners(gray, max_corners=500) -> (N,2) float32，坐标为 (x, y)。
降级路径（§12「降低 Harris 阈值重检一次」）：detect_corners_retry_low（quality 0.005）。
"""

from __future__ import annotations

import numpy as np

K_HARRIS = 0.04
DEFAULT_QUALITY = 0.01      # 阈值 = quality × R_max
RETRY_QUALITY = 0.005       # §12 降级重检
BOX_SIZE = 3                # 结构张量盒式滤波窗口（奇数）
                            # 选 3 而非 5：实测 k=5 会使响应峰偏向角点内侧约 1 px
                            # （§11 定位误差 ≤ 1 px 难以稳定满足），k=3 峰值正落在角点像素上
NMS_SIZE = 3                # 非极大值抑制邻域


def sobel_gradients(gray: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """3x3 Sobel 梯度（移位差分实现，float32；按 1/8 归一到导数尺度，灰度 [0,1]）。"""
    img = np.asarray(gray, dtype=np.float32) / 255.0
    p = np.pad(img, 1, mode="edge")
    gx = ((p[2:, 2:] + 2 * p[1:-1, 2:] + p[:-2, 2:])
          - (p[2:, :-2] + 2 * p[1:-1, :-2] + p[:-2, :-2])) / 8.0
    gy = ((p[2:, 2:] + 2 * p[2:, 1:-1] + p[2:, :-2])
          - (p[:-2, 2:] + 2 * p[:-2, 1:-1] + p[:-2, :-2])) / 8.0
    return gx, gy


def box_filter(img: np.ndarray, k: int = BOX_SIZE) -> np.ndarray:
    """盒式滤波（滑窗和向量化）：积分图 + 四次差分，输出与输入同尺寸且**中心对齐**。

    积分图约定 I[i,j] = sum img[0:i, 0:j]（由 (1,0) 零填充 + 二次 cumsum 得到）；
    输出 (r,c) = 以 img[r,c] 为中心的 k×k 窗口均值（边界用 reflect 扩展）。
    复杂度 O(HW)（与 k 无关），对比逐窗重算 O(HW·k²)。
    """
    if k % 2 == 0:
        k += 1
    h, w = img.shape
    pad = k // 2 + 1                       # 多垫 1 行/列，供积分图索引起点
    p = np.pad(img, pad, mode="reflect")
    ip = np.pad(p, ((1, 0), (1, 0)), mode="constant").cumsum(0).cumsum(1)
    out = (ip[k + 1:k + 1 + h, k + 1:k + 1 + w]
           - ip[1:1 + h, k + 1:k + 1 + w]
           - ip[k + 1:k + 1 + h, 1:1 + w]
           + ip[1:1 + h, 1:1 + w])
    return out / (k * k)


def harris_response(gray: np.ndarray) -> np.ndarray:
    """Harris 响应 R = det(H) − k·tr(H)²（H 为盒式滤波平滑后的结构张量）。"""
    gx, gy = sobel_gradients(gray)
    ixx = box_filter(gx * gx)
    ixy = box_filter(gx * gy)
    iyy = box_filter(gy * gy)
    det = ixx * iyy - ixy * ixy
    trace = ixx + iyy
    return det - K_HARRIS * trace * trace


def detect_corners(gray: np.ndarray, max_corners: int = 500,
                   quality: float = DEFAULT_QUALITY) -> np.ndarray:
    """自研 Harris 角点检测：返回 (N,2) float32，按响应降序，坐标 (x, y)。"""
    R = harris_response(gray)
    r_max = float(R.max()) if R.size else 0.0
    if r_max <= 0:
        return np.empty((0, 2), dtype=np.float32)

    # 非极大值抑制：3x3 滑窗取局部最大
    win = np.lib.stride_tricks.sliding_window_view(R, (NMS_SIZE, NMS_SIZE))
    local_max = win.max(axis=(-1, -2))
    is_max = np.zeros_like(R, dtype=bool)
    is_max[1:-1, 1:-1] = R[1:-1, 1:-1] >= local_max
    mask = is_max & (R > quality * r_max)

    ys, xs = np.nonzero(mask)
    if ys.size == 0:
        return np.empty((0, 2), dtype=np.float32)
    resp = R[ys, xs]

    # 取 Top-N：np.argpartition 平均 O(N)（对比 np.argsort 的 O(N log N)）
    if resp.size > max_corners:
        idx = np.argpartition(-resp, max_corners - 1)[:max_corners]
        idx = idx[np.argsort(-resp[idx])]   # 仅对 N 个候选排序，保证输出稳定
    else:
        idx = np.argsort(-resp)
    return np.stack([xs[idx], ys[idx]], axis=1).astype(np.float32)


def detect_corners_retry_low(gray: np.ndarray, max_corners: int = 500) -> np.ndarray:
    """§12 降级：降低阈值重检一次（quality 0.01 → 0.005）。"""
    return detect_corners(gray, max_corners, quality=RETRY_QUALITY)
