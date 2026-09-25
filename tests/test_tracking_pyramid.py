"""P4（A. 金字塔 LK）行为测试：粗到细把可靠跟踪范围从约 4 px 扩到约 6-7 px。

依据 §8.2 与 KNOWN_ISSUES #19：单层 LK 受线性化范围限制，位移接近窗口半径时失效；
金字塔用粗层捕获位移、逐层上采样作初值，故在中等位移上显著更稳。
本测试用合成平移给出真值（不需 cv2），把该结论变成可回归的断言。

实测标定（200x260 高纹理图、win=15、48 个均匀点、整数平移；证据
.workbuddy/env-probe/diag_pyramid6.txt）：

| 帧间位移 | 单层存活 | 金字塔(3层)存活 |
|---|---|---|
| 5 px | 44/48 | 48/48 |
| 6 px | 5/48 | 48/48 |
| 7 px | 0/48 | 5/48 |
| 8 px | 0/48 | 0/48 |

另实测 4 层在位移较小（5-6 px）时反而劣化（4/48、0/48）——粗层位移过小且均值池化损失细节，
故默认 levels=3。单层在 >=6 px 基本崩溃，与 §8.2「合成验收位移幅度约 <=5 px」的区间一致。

注意：单层会把「收敛到错误局部极值但残差恰好达标」的点也标为存活，故本测试用
真值容差内的正确率判定，而不是只看 status。
"""

from __future__ import annotations

import numpy as np
import pytest

from src.tracking import _downsample2x, track_points, track_points_pyramid

H, W = 200, 260
WIN = 15

def _texture(seed: int = 7) -> np.ndarray:
    """高纹理灰度图（正弦 + 棋盘 + 噪点）。"""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:H, 0:W].astype(np.float64)
    img = 120.0
    img += 60.0 * np.sin(2 * np.pi * x / 11.0) * np.cos(2 * np.pi * y / 13.0)
    img += 40.0 * (((x // 9) + (y // 9)) % 2)
    img += rng.normal(0, 6.0, (H, W))
    return np.clip(img, 0, 255).astype(np.uint8)

def _translate(img: np.ndarray, dx: int, dy: int) -> np.ndarray:
    """整数平移（同尺寸，越界填 0）——已知真值的帧间运动。"""
    out = np.zeros_like(img)
    h, w = img.shape
    out[max(0, dy):min(h, h + dy), max(0, dx):min(w, w + dx)] = \
        img[max(0, -dy):min(h, h - dy), max(0, -dx):min(w, w - dx)]
    return out

def _pts_in(nx: int = 8, ny: int = 6) -> np.ndarray:
    xs = np.linspace(70, W - 70, nx)
    ys = np.linspace(70, H - 70, ny)
    gx, gy = np.meshgrid(xs, ys)
    return np.stack([gx.ravel(), gy.ravel()], axis=1).astype(np.float32)

def _survival(est: np.ndarray, status: np.ndarray, pts: np.ndarray,
              shift: tuple, tol: float = 0.5) -> tuple:
    """返回 (存活率, 真值容差内比例)。

    末者比「存活」更严格：单层会把已收敛到错误局部极值、但残差恰好达标的点也标为存活
    （实测 5 px 时 44/48 存活，却只有少数点正确），故用真值容差判定真实正确率。
    """
    truth = pts.astype(np.float64) + np.asarray(shift, dtype=np.float64)
    correct = status & (np.linalg.norm(est.astype(np.float64) - truth, axis=1) <= tol)
    return float(status.mean()), float(correct.mean())

def test_downsample2x_mean_pooling():
    """2x2 均值池化：尺寸减半，值等于手工四格均值。"""
    img = np.arange(4 * 6, dtype=np.float32).reshape(4, 6)
    out = _downsample2x(img)
    assert out.shape == (2, 3)
    assert out[0, 0] == pytest.approx((img[0, 0] + img[0, 1] + img[1, 0] + img[1, 1]) / 4)
    assert out[1, 2] == pytest.approx((img[2, 4] + img[2, 5] + img[3, 4] + img[3, 5]) / 4)

def test_downsample2x_odd_size_drops_last():
    assert _downsample2x(np.zeros((5, 7), dtype=np.float32)).shape == (2, 3)

def test_pyramid_accurate_and_stable_on_motion_within_spec():
    """§8.2 规格区间（位移 <=5 px）：金字塔须全部点正确（存活 100%、正确 100%）。"""
    img = _texture()
    pts = _pts_in()
    for shift in [(2, 0), (0, 2), (5, 0), (0, 5), (3, 4)]:
        shifted = _translate(img, *shift)
        est, st = track_points_pyramid(img, shifted, pts, win=WIN, levels=3)
        rate, correct = _survival(est, st, pts, shift)
        assert rate == 1.0, f"位移 {shift}: 金字塔存活率应 100%，实测 {rate:.2f}"
        assert correct == 1.0, f"位移 {shift}: 金字塔正确率应 100%，实测 {correct:.2f}"

def test_pyramid_beats_single_level_for_single_axis_beyond_linear_range():
    """单轴 6 px（单层已崩溃）：金字塔必须接近满分。

    实测（diag_pyramid7.txt）：单层 x 轴 6 px 正确率 0.104、y 轴 6 px 0.854；
    金字塔两者均 1.000。y 轴单层未崩溃源于本测试纹理的各向异性（x 向 sin 周期 11 px
    强于 y 向 13 px），故此处只断言「金字塔满分级 + 严格优于单层」。
    """
    img = _texture()
    pts = _pts_in()
    for shift in [(6, 0), (0, 6)]:
        shifted = _translate(img, *shift)
        _, c1 = _survival(*track_points(img, shifted, pts, win=WIN)[:2], pts, shift)
        _, c2 = _survival(*track_points_pyramid(img, shifted, pts, win=WIN,
                                                levels=3)[:2], pts, shift)
        assert c2 >= 0.95, f"位移 {shift}: 金字塔正确率应 ≥0.95，实测 {c2:.2f}"
        assert c2 > c1, f"位移 {shift}: 金字塔 {c2:.2f} 应优于单层 {c1:.2f}"


def test_diagonal_motion_limitation_is_recorded():
    """已知局限（须文档化）：双轴同时大位移（≥5 px/轴）时金字塔仍会失败。

    实测（diag_pyramid10.txt，循环平移排除边界伪影）：(5,5)/(6,6)/(6,3) 正确率均为 0.000，
    而 (4,3) 为 1.000、(3,3) 为 1.000——呈阈值效应。本测试**固定该行为**，一旦未来改进
    （如增大粗层窗口或改 LK 阻尼）使其通过，此测试会失败并提醒更新文档与结论。
    """
    img = _texture()
    pts = _pts_in()
    for shift in [(5, 5), (6, 3)]:
        shifted = _translate(img, *shift)
        _, c = _survival(*track_points_pyramid(img, shifted, pts, win=WIN,
                                               levels=3)[:2], pts, shift)
        assert c <= 0.2, (f"位移 {shift}: 预期仍失败（局限已知）；若已改善为 {c:.2f}，"
                          f"请更新 KNOWN_ISSUES/RESULTS 与 AGENTS §8.2 结论后放宽本断言")


def test_pyramid_handles_diagonal_within_small_budget():
    """双轴合计仍在单层能力内（4,3）：金字塔应满分。"""
    img = _texture()
    pts = _pts_in()
    shifted = _translate(img, 4, 3)
    _, c2 = _survival(*track_points_pyramid(img, shifted, pts, win=WIN,
                                            levels=3)[:2], pts, (4, 3))
    assert c2 >= 0.95, f"金字塔对 (4,3) 应接近满分，实测 {c2:.2f}"

def test_both_reject_motion_beyond_window_radius():
    """位移超出窗口半径（8/10 px）时不得大面积误报为正确（判定线应拒绝）。"""
    img = _texture()
    pts = _pts_in()
    for shift in [(8, 0), (0, 10)]:
        shifted = _translate(img, *shift)
        est, st = track_points_pyramid(img, shifted, pts, win=WIN, levels=3)
        _, correct = _survival(est, st, pts, shift)
        assert correct <= 0.2, f"位移 {shift}: 不应有大量点被判正确，实测 {correct:.2f}"

def test_pyramid_levels_auto_reduced_for_small_images():
    """小图自动降层：不得因层数过大而报错或产出非有限值。"""
    small = _texture()[:40, :40]
    shifted = _translate(small, 1, 1)
    pts = np.array([[20.0, 20.0], [25.0, 18.0]], dtype=np.float32)
    new_pts, status = track_points_pyramid(small, shifted, pts, win=WIN, levels=4)
    assert new_pts.shape == (2, 2)
    assert status.dtype == bool
    assert np.all(np.isfinite(new_pts))

def test_pyramid_empty_points():
    img = _texture()
    new_pts, status = track_points_pyramid(img, img, np.empty((0, 2), np.float32))
    assert new_pts.shape == (0, 2) and status.shape == (0,)
    assert status.dtype == bool

def test_pyramid_identity_returns_input_points():
    """同一帧自跟踪：位移近 0 且点数保留（与单层同口径）。"""
    img = _texture()
    pts = _pts_in()
    new_pts, status = track_points_pyramid(img, img, pts, win=WIN, levels=3)
    assert status.sum() >= int(0.8 * len(pts))
    disp = np.linalg.norm(new_pts[status] - pts[status], axis=1)
    assert float(disp.max()) < 0.05
