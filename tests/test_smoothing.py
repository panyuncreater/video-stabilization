"""smoothing.py 单元测试（§11：与朴素遍历实现逐值一致，同一部分窗口边界规则）。"""

import sys

import numpy as np

sys.path.insert(0, ".")
from src.smoothing import (GaussianSmoother, MedianSmoother, MovingAverageSmoother,
                           create_smoother)


def naive_centered(seq, window, kind, sigma=None):
    """朴素参照实现：整序列离线、同一居中口径与部分窗口边界规则。"""
    if window % 2 == 0:
        window += 1
    r = window // 2
    n = len(seq)
    out = []
    for i in range(n):
        lo, hi = max(0, i - r), min(n - 1, i + r)
        seg = np.asarray(seq[lo:hi + 1], dtype=np.float64)
        if kind == "ma":
            out.append(seg.sum() / len(seg))
        elif kind == "median":
            s = sorted(seg.tolist())
            m = len(s)
            out.append(s[m // 2] if m % 2 else (s[m // 2 - 1] + s[m // 2]) / 2)
        elif kind == "gauss":
            x = np.arange(window) - r
            k = np.exp(-0.5 * (x / sigma) ** 2)
            taps = k[lo - (i - r): lo - (i - r) + len(seg)]
            w = taps / taps.sum()
            out.append(float(seg @ w))
    return out


def run_smoother(smoother, seq):
    out = []
    for x in seq:
        y = smoother.update(x)
        if y is not None:
            out.append(y)
    out.extend(smoother.flush())
    return out


SEQS = {
    "random100": np.random.default_rng(42).normal(10, 5, 100).tolist(),
    "short5": [3.0, 1.0, 4.0, 1.0, 5.0],
    "spikes": [0.0] * 20 + [100.0] + [0.0] * 18 + [50.0, -50.0] + [0.0] * 9,
}


def assert_close(a, b, rtol=1e-9):
    a, b = np.asarray(a), np.asarray(b)
    assert a.shape == b.shape, f"长度不一致: {a.shape} vs {b.shape}"
    assert np.allclose(a, b, rtol=rtol, atol=1e-12), np.abs(a - b).max()


# ---------- 输出个数与延迟语义 ----------

def test_output_count_equals_n_and_latency():
    seq = SEQS["random100"]
    for cls in (MovingAverageSmoother, GaussianSmoother, MedianSmoother):
        out = run_smoother(cls(31), seq)
        assert len(out) == len(seq), cls.__name__


def test_update_returns_none_during_latency():
    sm = MovingAverageSmoother(5)  # r = 2
    assert sm.update(1.0) is None
    assert sm.update(2.0) is None
    assert sm.update(3.0) is not None  # 第 3 次（t=2）起有输出


# ---------- 与朴素实现逐值一致 ----------

def test_moving_average_matches_naive():
    for name, seq in SEQS.items():
        for w in (1, 5, 31):
            assert_close(run_smoother(MovingAverageSmoother(w), seq),
                         naive_centered(seq, w, "ma"))


def test_median_matches_naive_and_sorted():
    for name, seq in SEQS.items():
        for w in (1, 5, 31):
            assert_close(run_smoother(MedianSmoother(w), seq),
                         naive_centered(seq, w, "median"))


def test_gaussian_matches_naive():
    for name, seq in SEQS.items():
        for w in (5, 31):
            sigma = w / 6.0
            assert_close(run_smoother(GaussianSmoother(w), seq),
                         naive_centered(seq, w, "gauss", sigma))


def test_gaussian_explicit_sigma():
    seq = SEQS["random100"]
    assert_close(run_smoother(GaussianSmoother(15, sigma=3.0), seq),
                 naive_centered(seq, 15, "gauss", 3.0))


def test_window_longer_than_sequence():
    """window=31 作用于 5 点序列：全序列皆为部分窗口。"""
    seq = SEQS["short5"]
    for cls, kind in ((MovingAverageSmoother, "ma"), (MedianSmoother, "median")):
        assert_close(run_smoother(cls(31), seq), naive_centered(seq, 31, kind))


# ---------- 偶数窗口自动 +1 ----------

def test_even_window_auto_increment():
    seq = SEQS["random100"]
    # window=10 应按 11 计算
    assert_close(run_smoother(MovingAverageSmoother(10), seq),
                 naive_centered(seq, 11, "ma"))
    assert MovingAverageSmoother(10).window == 11


def test_create_smoother_factory():
    assert isinstance(create_smoother("ma", 5), MovingAverageSmoother)
    assert isinstance(create_smoother("gauss", 5), GaussianSmoother)
    assert isinstance(create_smoother("median", 5), MedianSmoother)
    try:
        create_smoother("bad", 5)
        assert False, "应抛 ValueError"
    except ValueError:
        pass
