"""自研单层 Lucas-Kanade 稀疏光流（§8.2），替代 M0 的 cv2.calcOpticalFlowPyrLK（红线 3）。

实现要点：
- 每个特征点 15×15 窗口，构建结构张量并解 2x2 正规方程（批量向量化，无逐点循环）；
- 迭代至多 20 次或位移增量 < 0.01 px 收敛；
- status 判定：窗口最小特征值 > 1e-4、平均光度残差 < 0.05（[0,1] 灰度尺度，§8.2 参考值）、
  累计位移不超过窗口半径（7 px）、点邻域不出边界；
  （2026-09-25 实验证伪 0.075：test1 ITF 增益 +0.614 vs 0.05 基线 +0.650，无收益反小损——
  放宽残差只引入暗部平坦区低质量存活点，M_t 更噪；用户决策回退 0.05，见 PROJECT_STATE。
  M0 的 ITF 优势归因于金字塔 LK 而非残差阈值，作为已知问题文档化）；
- 亚像素采样使用自研双线性插值。

契约：track_points(prev_gray, curr_gray, pts, win=15) -> (new_pts, status)。

金字塔模式（P4/A，§8.2 可选加分项，`main.py --pyramid`）：
- track_points_pyramid(prev_gray, curr_gray, pts, win=15, levels=3)：2x2 均值池化金字塔 +
  粗到细 LK（同一套 2x2 正规方程，仅初值不同）。
- **默认关闭**：不传 --pyramid 时主流水线仍走单层 track_points，既有标定与指标逐位不变。
- **参数交互（重要）**：镜头切换探针 shots.probe_cut_evidence 内部仍用单层 track_points，
  故其崩溃线 PROBE_SURVIVAL_THRESHOLD=0.25 是按单层标定的。启用 --pyramid 改变了主跟踪的
  存活分布 → **必须重标探针线**（并重跑双份回归），否则切换判据可能与标定不符。
- **已实测能力边界**（tests/test_tracking_pyramid.py，合成平移真值）：
  单轴 6 px 单层正确率 0.10／金字塔 1.00（y 轴单层 0.85 系本测试纹理各向异性所致）；
  单轴 7 px 两者均开始失效；**双轴同时 ≥5 px（如 (5,5)/(6,3)）金字塔仍失败**——粗层
  对该纹理收敛到能量更强的单轴局部极小。故 §8.2 的「位移 ≤5 px」适用区间应按**单轴**理解，
  局限性须写入报告。
"""

from __future__ import annotations

import numpy as np

from src.features import sobel_gradients

MAX_ITERS = 20
CONVERGE_EPS = 0.01     # 位移增量收敛阈值（px）
LAMBDA_MIN = 1e-4       # 结构张量最小特征值阈值
RESIDUAL_MAX = 0.05     # 平均光度残差阈值（[0,1] 尺度；2026-09-25 实验 0.075 证伪后维持 §8.2 参考值）
DET_EPS = 1e-12
PYRAMID_MAX_LEVELS = 4  # 金字塔最大层数（§8.2 可选加分项；2^4 = 16 倍降采样）


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


def _downsample2x(img: np.ndarray) -> np.ndarray:
    """2x2 均值池化降采样（金字塔专用，属尺度约简而非几何重采样）。

    与红线 2 的关系：本函数是**整数倍抽取 + 抗混叠均值**，不涉及旋转/平移等几何映射；
    只有几何重采样（含裁剪后缩放）才必须走 `src.warp.resample`（红线 2）。§8.2 明确
    「自研金字塔降采样（NumPy 向量化 2x2 均值池化）」，故此处按均值池化实现。
    输出尺寸 (h//2, w//2)（奇数行/列丢弃），返回 float32。
    """
    h, w = img.shape[:2]
    h2, w2 = h // 2, w // 2
    a = np.asarray(img, dtype=np.float32)[:2 * h2, :2 * w2]
    return 0.25 * (a[0::2, 0::2] + a[0::2, 1::2] + a[1::2, 0::2] + a[1::2, 1::2])


def _lk_iterate(prev_patch: np.ndarray, ix_patch: np.ndarray, iy_patch: np.ndarray,
                curr: np.ndarray, rows0: np.ndarray, cols0: np.ndarray,
                disp0: np.ndarray, gxx, gxy, gyy, det_g, lam_min):
    """从初值 disp0 做 LK 迭代，返回 (disp, residual, ok)。

    迭代式与单层 track_points 完全一致（同一套 2x2 正规方程），仅初值来源不同：
    单层用 0，金字塔用粗层上采样结果。**若改动 LK 数学，两处必须同步修改。**
    """
    n = prev_patch.shape[0]
    ok = (det_g > DET_EPS) & (lam_min > LAMBDA_MIN)
    disp = np.asarray(disp0, dtype=np.float64).copy()
    residual = np.full(n, np.inf)
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
    return disp, residual, ok


def _lk_level(prev_gray: np.ndarray, curr_gray: np.ndarray, pts: np.ndarray,
              disp0: np.ndarray, win: int):
    """单尺度精化：结构张量取自该尺度 prev_gray；点位越界的点标记为不 ok。"""
    n = len(pts)
    r = win // 2
    prev = np.asarray(prev_gray, dtype=np.float32) / 255.0
    curr = np.asarray(curr_gray, dtype=np.float32) / 255.0
    h, w = prev.shape
    ix, iy = sobel_gradients(prev_gray)
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
    gxx = np.sum(ix_patch * ix_patch, axis=(1, 2))
    gxy = np.sum(ix_patch * iy_patch, axis=(1, 2))
    gyy = np.sum(iy_patch * iy_patch, axis=(1, 2))
    det_g = gxx * gyy - gxy * gxy
    lam_min = 0.5 * ((gxx + gyy) - np.sqrt(np.maximum((gxx - gyy) ** 2 + 4 * gxy * gxy, 0.0)))
    disp, residual, ok = _lk_iterate(prev_patch, ix_patch, iy_patch, curr, rows0, cols0,
                                     disp0, gxx, gxy, gyy, det_g, lam_min)
    return disp, residual, ok & in_bounds


def track_points_pyramid(prev_gray: np.ndarray, curr_gray: np.ndarray,
                         pts: np.ndarray, win: int = 15, levels: int = 3):
    """粗到细金字塔 LK（§8.2 可选加分项）：返回 (new_pts (M,2) float32, status (M,) bool)。

    动机（KNOWN_ISSUES #19）：单层 LK 对大位移超出线性化范围，test1 ITF 增益弱于 M0 的
    `calcOpticalFlowPyrLK`（+1.189 vs +1.299）。金字塔让粗层先捕获大位移，逐层上采样作初值，
    细层再精化——数学仍是同一套 2x2 正规方程，只是初值不同。

    实现要点：
    - 金字塔由 `_downsample2x`（2x2 均值池化）构建；层数上限 `PYRAMID_MAX_LEVELS`，
      且每层须能容纳 win 窗口，不足自动降层；
    - 位移跨层传递：粗层位移 × 2 作为上一层初值（层内像素单位）；
    - status 口径与单层一致：最小特征值 / 残差 < RESIDUAL_MAX / 累计位移 ≤ 窗口半径 /
      点位不出边界，且全部在最细层判定，便于与单层实现逐步对比。
    """
    pts = np.asarray(pts, dtype=np.float64).reshape(-1, 2)
    n = len(pts)
    if n == 0:
        return np.empty((0, 2), dtype=np.float32), np.zeros(0, dtype=bool)

    h, w = prev_gray.shape[:2]
    r = win // 2
    max_by_size = 1
    while max_by_size < PYRAMID_MAX_LEVELS and min(h, w) // (2 ** max_by_size) > win:
        max_by_size += 1
    levels = int(max(1, min(int(levels), max_by_size)))

    prev_pyr = [np.asarray(prev_gray, dtype=np.float32)]
    curr_pyr = [np.asarray(curr_gray, dtype=np.float32)]
    for _ in range(levels - 1):
        prev_pyr.append(_downsample2x(prev_pyr[-1]))
        curr_pyr.append(_downsample2x(curr_pyr[-1]))

    disp = np.zeros((n, 2), dtype=np.float64)
    residual = np.full(n, np.inf)
    ok = np.ones(n, dtype=bool)
    for lvl in range(levels - 1, -1, -1):
        if lvl < levels - 1:
            disp = disp * 2.0          # 粗层位移 → 上一层像素单位
        scale = 0.5 ** lvl
        disp, residual, ok = _lk_level(prev_pyr[lvl], curr_pyr[lvl], pts * scale, disp, win)

    new_pts = pts + disp
    disp_norm = np.linalg.norm(disp, axis=1)
    status = (ok
              & (residual < RESIDUAL_MAX)
              & (disp_norm <= r)
              & (new_pts[:, 0] >= 0) & (new_pts[:, 0] < w)
              & (new_pts[:, 1] >= 0) & (new_pts[:, 1] < h))
    return new_pts.astype(np.float32), status


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
