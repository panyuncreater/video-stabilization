"""features.py 单元测试（§11）：合成角点图（真值已知）检出率 ≥ 95%、定位误差 ≤ 1 px。"""

import sys

import numpy as np

sys.path.insert(0, ".")
from src.features import (box_filter, detect_corners, detect_corners_retry_low,
                          harris_response, sobel_gradients)


def make_corner_image(h: int = 240, w: int = 240, square: int = 40, step: int = 70):
    """白底黑方块网格：真值角点取黑方块的四个**角点像素**。

    黑方块覆盖像素 [y, y+square) × [x, x+square)，故其四角像素为
    (x, y)、(x+square-1, y)、(x, y+square-1)、(x+square-1, y+square-1)。
    """
    img = np.full((h, w), 255, dtype=np.uint8)
    gt = []
    for y in range(20, h - square, step):
        for x in range(20, w - square, step):
            img[y:y + square, x:x + square] = 0
            x1, y1 = x + square - 1, y + square - 1
            gt.extend([(x, y), (x1, y), (x, y1), (x1, y1)])
    return img, np.array(gt, dtype=np.float64)


def match_stats(pts: np.ndarray, gt: np.ndarray, tol: float = 1.0):
    """返回 (命中率, 最大定位误差)：每个真值角点找最近检测点。"""
    if len(pts) == 0:
        return 0.0, np.inf
    d = np.linalg.norm(pts[None, :, :] - gt[:, None, :], axis=2)  # (M_gt, N)
    nearest = d.min(axis=1)
    hits = nearest <= tol
    return float(hits.mean()), float(nearest.max())


# ---------- 组件 ----------

def test_sobel_shape_and_zero_on_flat():
    flat = np.full((40, 50), 100, np.uint8)
    gx, gy = sobel_gradients(flat)
    assert gx.shape == flat.shape and gy.shape == flat.shape
    assert np.allclose(gx[1:-1, 1:-1], 0, atol=1e-7)
    assert np.allclose(gy[1:-1, 1:-1], 0, atol=1e-7)


def test_box_filter_preserves_constant():
    img = np.full((30, 40), 0.5)
    assert np.allclose(box_filter(img, 5), 0.5, atol=1e-6)


def test_box_filter_mean_of_impulse():
    img = np.zeros((31, 31))
    img[15, 15] = 1.0
    out = box_filter(img, 5)
    assert abs(out[15, 15] - 1.0 / 25) < 1e-9


def test_box_filter_is_center_aligned():
    """冲激响应应是以 (15,15) 为中心的 5×5 块：行 13..17 非零，12 与 18 为零。"""
    img = np.zeros((31, 31))
    img[15, 15] = 1.0
    out = box_filter(img, 5)
    assert abs(out[13, 15] - 1.0 / 25) < 1e-9   # 窗口上边界
    assert abs(out[17, 15] - 1.0 / 25) < 1e-9   # 窗口下边界
    assert out[12, 15] == 0.0                   # 窗口外
    assert out[18, 15] == 0.0                   # 窗口外
    assert abs(out[15, 13] - 1.0 / 25) < 1e-9
    assert out[15, 12] == 0.0 and out[15, 18] == 0.0


def test_response_flat_image_is_zero():
    R = harris_response(np.full((40, 40), 128, np.uint8))
    assert np.allclose(R[1:-1, 1:-1], 0, atol=1e-8)


# ---------- §11 验收 ----------

def test_corner_detection_rate_and_localization():
    img, gt = make_corner_image()
    pts = detect_corners(img, max_corners=500)
    rate, max_err = match_stats(pts, gt, tol=1.0)
    print(f"\n检出 {len(pts)} 点 / 真值 {len(gt)} 角点 | 命中率 {rate:.3f} | 最大定位误差 {max_err:.3f} px")
    assert rate >= 0.95, f"检出率 {rate:.3f} < 0.95"
    assert max_err <= 1.0, f"定位误差 {max_err:.3f} > 1 px"


def test_flat_image_returns_empty():
    assert len(detect_corners(np.full((60, 60), 128, np.uint8))) == 0


def test_max_corners_cap_and_dtype():
    img, _ = make_corner_image()
    pts = detect_corners(img, max_corners=7)
    assert len(pts) <= 7
    assert pts.dtype == np.float32 and pts.shape[1] == 2


def test_retry_low_threshold_yields_at_least_as_many():
    img, _ = make_corner_image()
    normal = detect_corners(img, max_corners=500)
    retry = detect_corners_retry_low(img, max_corners=500)
    assert len(retry) >= len(normal)


# ---------- v2.5 空间均匀化（KNOWN_ISSUES #21 根治） ----------

def test_grid_bucketing_spreads_points_spatially():
    """上带密集强纹理 + 下带稀疏纹理：全局 Top-N 会把点全部集中到上带，
    网格分桶应让下带也分到可观份额——保证 y 方向几何基线。"""
    img = np.full((160, 200), 255, dtype=np.uint8)
    # 上带：8px 棋盘（角点密集、响应强）
    band = ((np.add.outer(np.arange(80) // 8, np.arange(200) // 8) % 2) * 200 + 20)
    img[:80, :] = band.astype(np.uint8)
    # 下带：稀疏黑方块（角点少）
    for y0 in (95, 125):
        for x0 in (20, 90, 140):
            img[y0:y0 + 30, x0:x0 + 30] = 0
    pts = detect_corners(img, max_corners=60)     # 候选 240 >> 60，触发分桶
    lower = pts[pts[:, 1] > 80]
    print(f"\n总点数 {len(pts)}，下带点数 {len(lower)}（占比 {len(lower)/len(pts):.0%}）")
    assert len(pts) >= 30, f"总点数 {len(pts)} 过少"
    assert len(lower) / len(pts) >= 0.15, f"下带占比 {len(lower)/len(pts):.0%} —— 点集仍条带化"
