"""自研图像几何变换（AGENTS.md 红线 2）：逆向映射 + 双线性插值，NumPy 向量化。

warp 方向约定（§7，关键易错点）：
- `warp_frame(img, M)` 中 M 为「输入图像坐标 → 输出图像坐标」的正向 3x3 齐次变换；
  内部对 M 求逆后做逆向映射采样，即 out(x) = img(M^{-1} x)。
- cv2.warpAffine 的 M 是「输出 → 输入」约定；单元测试对照时应调用
  cv2.warpAffine(img, np.linalg.inv(M), ...) 与本模块比较。

越界策略：逐采样点四邻各自判定，越界邻点贡献为 0（与 cv2.BORDER_CONSTANT 一致），
黑边交由 crop 模块处理（§8.6）。
"""

from __future__ import annotations

import numpy as np

# 输出网格缓存：网格仅取决于输出尺寸，逐帧复用（流水线中每帧尺寸相同）
_GRID_CACHE: dict[tuple[int, int], np.ndarray] = {}


def _output_grid(out_w: int, out_h: int) -> np.ndarray:
    key = (out_h, out_w)
    grid = _GRID_CACHE.get(key)
    if grid is None:
        ys, xs = np.mgrid[0:out_h, 0:out_w].astype(np.float32)
        grid = np.stack([xs.ravel(), ys.ravel(), np.ones(xs.size, dtype=np.float32)], axis=0)
        _GRID_CACHE[key] = grid
    return grid


def resample(img: np.ndarray, Minv: np.ndarray, out_w: int, out_h: int) -> np.ndarray:
    """双线性重采样核：out(x) = img(Minv x)，输出尺寸 (out_h, out_w)。

    Minv 为「输出坐标 → 输入坐标」的 3x3 齐次矩阵。供 warp_frame 与 crop 复用；
    crop 的「缩放回原分辨率」即以纯缩放矩阵调用本函数（红线 2：禁 cv2.resize）。
    uint8 输入按 float32 计算（精度对 8bit 输出足够，速度约快一倍）。
    """
    h, w = img.shape[:2]
    cdtype = np.float32 if img.dtype == np.uint8 else np.float64
    grid = _output_grid(out_w, out_h)  # (3, N)
    src = Minv.astype(cdtype) @ grid
    z = src[2]
    z[z == 0.0] = 1.0  # 数值保护；相似变换下 z 恒为 1
    sx = (src[0] / z).reshape(out_h, out_w)
    sy = (src[1] / z).reshape(out_h, out_w)

    x0 = np.floor(sx)
    y0 = np.floor(sy)
    wx = sx - x0
    wy = sy - y0

    x0i = x0.astype(np.int64)
    y0i = y0.astype(np.int64)
    x1i = x0i + 1
    y1i = y0i + 1

    # 四个邻点各自的越界掩膜（广播计算权重）
    m00 = (x0i >= 0) & (x0i < w) & (y0i >= 0) & (y0i < h)
    m10 = (x1i >= 0) & (x1i < w) & (y0i >= 0) & (y0i < h)
    m01 = (x0i >= 0) & (x0i < w) & (y1i >= 0) & (y1i < h)
    m11 = (x1i >= 0) & (x1i < w) & (y1i >= 0) & (y1i < h)

    x0c = np.clip(x0i, 0, w - 1)
    x1c = np.clip(x1i, 0, w - 1)
    y0c = np.clip(y0i, 0, h - 1)
    y1c = np.clip(y1i, 0, h - 1)

    imgf = img.astype(cdtype)
    w00 = ((1 - wx) * (1 - wy)) * m00
    w10 = (wx * (1 - wy)) * m10
    w01 = ((1 - wx) * wy) * m01
    w11 = (wx * wy) * m11
    if img.ndim == 2:
        out = (imgf[y0c, x0c] * w00 + imgf[y0c, x1c] * w10
               + imgf[y1c, x0c] * w01 + imgf[y1c, x1c] * w11)
    else:
        out = (imgf[y0c, x0c] * w00[..., None] + imgf[y0c, x1c] * w10[..., None]
               + imgf[y1c, x0c] * w01[..., None] + imgf[y1c, x1c] * w11[..., None])

    if img.dtype == np.uint8:
        return np.clip(np.rint(out), 0, 255).astype(np.uint8)
    return out.astype(img.dtype, copy=False)


def warp_frame(img: np.ndarray, M: np.ndarray) -> np.ndarray:
    """按正向变换 M（输入→输出）对 img 做补偿，输出与输入同尺寸。"""
    M = np.asarray(M, dtype=np.float64)
    Minv = np.linalg.inv(M)
    h, w = img.shape[:2]
    return resample(img, Minv, w, h)
