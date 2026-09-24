"""裁剪模块（AGENTS.md §8.6 v2 定稿）：解析法黑边有效域 + 最大内接轴对齐矩形。

解析法（不依赖图像内容，不受夜景/暗场景误判影响）：
- 每帧输出平面的有效域 = 输入图像矩形经 B_t 作用的四边形（相似变换下为旋转矩形）；
- 每帧有效四边形 → 同轴对齐内接矩形（旋转矩形内接轴对齐矩形闭式解，同心）；
- 全片有效域 = 逐帧内接矩形的轴对齐交集（保守：先逐帧内接再求交，复杂度 O(N)；
  与「先求交再内接」的真值相比略保守，差异与复杂度分析写入报告）。

统一裁剪后经 warp 采样核以纯缩放矩阵重采样回原分辨率（红线 2：禁 cv2.resize）。
"""

from __future__ import annotations

import numpy as np

from src.warp import resample


def _inscribed_rect_rotated(a: float, b: float, phi: float) -> tuple[float, float]:
    """旋转矩形（边长 a×b，旋转角 |phi| ∈ [0, π/2]）的最大同心内接轴对齐矩形。

    角点可行约束：w·cosφ + h·sinφ ≤ a，w·sinφ + h·cosφ ≤ b。
    候选解：两约束同时取等的顶点解 + 两个单约束极值解，取面积最大的可行解。
    """
    if phi < 1e-9:
        return a, b
    c, s = np.cos(phi), np.sin(phi)
    cands = []
    det = np.cos(2 * phi)
    if abs(det) > 1e-9:
        w = (a * c - b * s) / det
        h = (b * c - a * s) / det
        if w > 0 and h > 0:
            cands.append((w, h))
    w1, h1 = a / (2 * c), a / (2 * s)
    if w1 * s + h1 * c <= b + 1e-9:
        cands.append((w1, h1))
    w2, h2 = b / (2 * s), b / (2 * c)
    if w2 * c + h2 * s <= a + 1e-9:
        cands.append((w2, h2))
    if not cands:  # 极端角度兜底：保守缩小
        return a * c, b * c
    return max(cands, key=lambda wh: wh[0] * wh[1])


def frame_valid_rect(B: np.ndarray, width: int, height: int) -> tuple[float, float, float, float]:
    """单帧有效矩形：B_t 作用于图像矩形的同心轴对齐内接矩形。

    返回 (cx, cy, w, h)：中心坐标与宽高。相似变换下图像中心映射为 B·center。
    """
    a = B[0, 0] + 1j * B[1, 0]
    s = abs(a)
    theta = np.angle(a)
    phi = abs(theta) % np.pi
    if phi > np.pi / 2:
        phi = np.pi - phi
    # 图像中心经 B 映射（平移含于其中）
    cx0, cy0 = width / 2.0, height / 2.0
    c = B @ np.array([cx0, cy0, 1.0])
    w_in, h_in = _inscribed_rect_rotated(s * width, s * height, phi)
    return float(c[0]), float(c[1]), w_in, h_in


def compute_crop_rect(B_list: list[np.ndarray], width: int, height: int):
    """全片有效域：逐帧内接矩形的轴对齐交集。

    返回 (L, T, R, B) 整数裁剪框（含左/上，不含右/下）。
    交集为空（补偿过大）时抛 ValueError，由调用方按异常规则处理。
    """
    L, T, R, B = 0.0, 0.0, float(width), float(height)
    for Bm in B_list:
        cx, cy, w, h = frame_valid_rect(Bm, width, height)
        L = max(L, cx - w / 2)
        R = min(R, cx + w / 2)
        T = max(T, cy - h / 2)
        B = min(B, cy + h / 2)
    if R - L < 2 or B - T < 2:
        raise ValueError(f"有效区域交集为空: L={L:.1f} R={R:.1f} T={T:.1f} B={B:.1f}")
    # 保守取整（向内收缩 ≤1px），保证裁剪框完全落在有效域内、输出无黑边
    return int(np.ceil(L)), int(np.ceil(T)), int(np.floor(R)), int(np.floor(B))


def cropping_ratio(rect: tuple[int, int, int, int], width: int, height: int) -> float:
    """裁剪率 r = 保留有效面积 / 原画面面积（§9，要求 ≥ 0.85）。"""
    L, T, R, B = rect
    return (R - L) * (B - T) / (width * height)


def warp_crop_resize(frame: np.ndarray, B: np.ndarray, rect: tuple[int, int, int, int],
                     out_w: int, out_h: int) -> np.ndarray:
    """补偿 warp + 裁剪 + 缩放回原分辨率，复合为**单次重采样**（避免二次插值模糊）。

    输出像素 (x,y) → 裁剪框坐标 (u,v)（cv2.resize 中心对齐：u = (x+0.5)·scx − 0.5）
    → warp 帧坐标（加 rect 偏移 L,T）→ 输入坐标（左乘 B^{-1}）。
    复合逆映射 Minv = B^{-1} @ A，A 为「输出全帧 → warp 帧」的缩放+平移矩阵。
    """
    L, T, R, Bb = rect
    cw, ch = R - L, Bb - T
    scx, scy = cw / out_w, ch / out_h
    A = np.array([
        [scx, 0.0, L + 0.5 * scx - 0.5],
        [0.0, scy, T + 0.5 * scy - 0.5],
        [0.0, 0.0, 1.0],
    ])
    Minv = np.linalg.inv(np.asarray(B, dtype=np.float64)) @ A
    return resample(frame, Minv, out_w, out_h)
