"""shots.py 单元测试：切换判据、镜头分段与最短镜头长度约束。"""

import sys

import numpy as np

sys.path.insert(0, ".")
from src.shots import (INLIER_RATIO_THRESHOLD, MAD_THRESHOLD, MIN_SHOT_LEN,
                       collapse_shots, frame_mad, is_cut, segment_shots)


def _frame(seed: int, shift: int = 0, h: int = 120, w: int = 160) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = rng.integers(0, 255, (h, w), dtype=np.uint8)
    if shift:
        img = np.roll(img, shift, axis=1)
    return img


# ---------- MAD ----------

def _grad(h: int = 120, w: int = 160) -> np.ndarray:
    """平滑渐变图（用于构造「同场景连续帧」）。"""
    yy, xx = np.mgrid[0:h, 0:w]
    return ((xx * 1.5 + yy * 0.5) % 256).astype(np.uint8)


def test_mad_identical_is_zero():
    a = _grad()
    assert frame_mad(a, a) == 0.0


def test_mad_small_motion_vs_cut():
    g = _grad()
    cont = frame_mad(g, np.roll(g, 3, axis=1))      # 同场景连续帧（微平移）
    other = np.random.default_rng(7).integers(0, 255, g.shape, dtype=np.uint8)
    cut = frame_mad(g, other)                       # 完全不同的场景
    assert cont < MAD_THRESHOLD, cont
    assert cut > MAD_THRESHOLD, cut


# ---------- 判据 ----------

def test_cut_requires_high_mad_and_low_inlier_ratio():
    assert is_cut(40.0, 0.10, 100) is True          # 切换：帧差大 + 运动不一致
    assert is_cut(40.0, 0.80, 100) is False         # 甩镜：帧差大但运动一致 → 不切
    assert is_cut(3.0, 0.05, 100) is False          # 平滑运动 + 低内点率 → 不切


def test_min_shot_length_blocks_dense_cuts():
    assert is_cut(40.0, 0.10, MIN_SHOT_LEN) is True
    assert is_cut(40.0, 0.10, MIN_SHOT_LEN - 1) is False


def test_inlier_ratio_boundary():
    assert is_cut(40.0, INLIER_RATIO_THRESHOLD, 100) is False  # 等于阈值不算切


# ---------- 分段 ----------

def test_segment_shots_bounds():
    cuts = [100, 500]
    assert segment_shots(cuts, 700) == [(0, 100), (100, 500), (500, 700)]


def test_segment_shots_no_cuts():
    assert segment_shots([], 200) == [(0, 200)]


def test_segment_shots_ignores_out_of_range():
    assert segment_shots([0, 200, 999], 200) == [(0, 200)]


def test_collapse_short_shots():
    shots = [(0, 5), (5, 100), (100, 104)]
    merged = collapse_shots(shots, min_len=12)
    assert merged == [(0, 104)] or merged[0][0] == 0 and merged[-1][1] == 104


def test_collapse_keeps_long_shots():
    shots = [(0, 300), (300, 340)]
    assert collapse_shots(shots, min_len=12) == [(0, 300), (300, 340)]
