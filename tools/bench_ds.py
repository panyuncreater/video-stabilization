"""数据结构计时基准（AGENTS.md §10 实测耗时对比口径）。

统一口径：time.perf_counter 计时、每配置预热 3 轮、重复 ≥5 取中位、固定随机种子。
结果输出 docs/bench_ds.json 与 docs/bench_ds.png（计时曲线），为课程报告核心素材。

对比项（§10 表格）：
1. 环形缓冲滑窗驱逐 vs 朴素 list.pop(0)（O(1) vs O(k)）
2. 移动平均增量更新 vs 每次重算窗口和（O(1) vs O(k)）
3. 双堆滑窗中值 vs 每次排序取中值（O(log k) vs O(k log k)）
4. np.argpartition 取 Top-N vs 全排序（平均 O(N) vs O(N log N)）
"""

from __future__ import annotations

import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ds.heap import BinaryHeap  # noqa: E402
from ds.ring_buffer import RingBuffer  # noqa: E402
from src.smoothing import MedianSmoother, MovingAverageSmoother  # noqa: E402

WARMUP = 3
REPEAT = 7
SEED = 42


def bench(fn, *args) -> float:
    """预热 + 重复取中位，返回单次耗时（秒）。"""
    for _ in range(WARMUP):
        fn(*args)
    ts = []
    for _ in range(REPEAT):
        t0 = time.perf_counter()
        fn(*args)
        ts.append(time.perf_counter() - t0)
    return float(np.median(ts))


# ---------- 1. 环形缓冲 vs list.pop(0) ----------

def slide_ring(seq, k):
    rb = RingBuffer(k)
    s = 0.0
    for x in seq:
        v = rb.push(x)
        if v is not None:
            s -= v
        s += x
    return s


def slide_list_pop0(seq, k):
    buf = []
    s = 0.0
    for x in seq:
        buf.append(x)
        if len(buf) > k:
            s -= buf.pop(0)
        s += x
    return s


# ---------- 2. 移动平均增量 vs 重算 ----------

def ma_incremental(seq, k):
    sm = MovingAverageSmoother(k)
    out = [y for x in seq if (y := sm.update(x)) is not None]
    out.extend(sm.flush())
    return out


def ma_recompute(seq, k):
    if k % 2 == 0:
        k += 1
    r = k // 2
    n = len(seq)
    out = []
    for i in range(n):
        lo, hi = max(0, i - r), min(n - 1, i + r)
        out.append(sum(seq[lo:hi + 1]) / (hi - lo + 1))
    return out


# ---------- 3. 双堆中值 vs 排序 ----------

def median_dual_heap(seq, k):
    sm = MedianSmoother(k)
    out = [y for x in seq if (y := sm.update(x)) is not None]
    out.extend(sm.flush())
    return out


def median_sorted(seq, k):
    if k % 2 == 0:
        k += 1
    r = k // 2
    n = len(seq)
    out = []
    for i in range(n):
        lo, hi = max(0, i - r), min(n - 1, i + r)
        s = sorted(seq[lo:hi + 1])
        m = len(s)
        out.append(s[m // 2] if m % 2 else (s[m // 2 - 1] + s[m // 2]) / 2)
    return out


# ---------- 4. argpartition vs 全排序 ----------

def topn_argpartition(resp, n_keep):
    idx = np.argpartition(resp, -n_keep)[-n_keep:]
    return idx[np.argsort(resp[idx])[::-1]]


def topn_full_sort(resp, n_keep):
    return np.argsort(resp)[::-1][:n_keep]


def main() -> None:
    rng = np.random.default_rng(SEED)
    results = {}

    print("== 1. 滑窗驱逐：RingBuffer vs list.pop(0) ==")
    r1 = []
    for k in [15, 31, 63, 127, 255]:
        seq = rng.normal(0, 1, 20000).tolist()
        t_rb = bench(slide_ring, seq, k)
        t_lp = bench(slide_list_pop0, seq, k)
        r1.append({"k": k, "ring_buffer_s": t_rb, "list_pop0_s": t_lp, "speedup": t_lp / t_rb})
        print(f"  k={k:4d}: ring={t_rb*1e3:7.2f}ms  pop0={t_lp*1e3:7.2f}ms  加速比 {t_lp/t_rb:5.2f}x")
    results["ring_buffer_vs_pop0"] = r1

    print("== 2. 移动平均：增量更新 vs 每次重算 ==")
    r2 = []
    for k in [15, 31, 63, 127]:
        seq = rng.normal(0, 1, 20000).tolist()
        t_inc = bench(ma_incremental, seq, k)
        t_rec = bench(ma_recompute, seq, k)
        r2.append({"k": k, "incremental_s": t_inc, "recompute_s": t_rec, "speedup": t_rec / t_inc})
        print(f"  k={k:4d}: incr={t_inc*1e3:7.2f}ms  recomp={t_rec*1e3:7.2f}ms  加速比 {t_rec/t_inc:5.2f}x")
    results["moving_average"] = r2

    print("== 3. 滑窗中值：双堆 vs 每次排序 ==")
    r3 = []
    for k in [15, 31, 63, 127]:
        seq = rng.normal(0, 1, 5000).tolist()
        t_dh = bench(median_dual_heap, seq, k)
        t_st = bench(median_sorted, seq, k)
        r3.append({"k": k, "dual_heap_s": t_dh, "sorted_s": t_st, "speedup": t_st / t_dh})
        print(f"  k={k:4d}: heap={t_dh*1e3:7.2f}ms  sorted={t_st*1e3:7.2f}ms  加速比 {t_st/t_dh:5.2f}x")
    results["sliding_median"] = r3

    print("== 4. Top-N：argpartition vs 全排序 ==")
    r4 = []
    for n in [100_000, 500_000, 1_000_000]:
        resp = rng.normal(0, 1, n)
        t_ap = bench(topn_argpartition, resp, 500)
        t_fs = bench(topn_full_sort, resp, 500)
        r4.append({"n": n, "argpartition_s": t_ap, "full_sort_s": t_fs, "speedup": t_fs / t_ap})
        print(f"  N={n:8d}: argpart={t_ap*1e3:7.2f}ms  sort={t_fs*1e3:7.2f}ms  加速比 {t_fs/t_ap:5.2f}x")
    results["topn_selection"] = r4

    os.makedirs("docs", exist_ok=True)
    out = os.path.join("docs", "bench_ds.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"口径": "perf_counter，预热3轮，重复7取中位，种子42", "results": results},
                  f, ensure_ascii=False, indent=2)
    print(f"\n结果已写入 {out}")

    # 计时曲线（报告素材）
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))
    ks = [r["k"] for r in r1]
    axes[0].plot(ks, [r["ring_buffer_s"] * 1e3 for r in r1], "o-", label="RingBuffer O(1)")
    axes[0].plot(ks, [r["list_pop0_s"] * 1e3 for r in r1], "s-", label="list.pop(0) O(k)")
    axes[0].set_title("滑窗驱逐"); axes[0].set_xlabel("窗口 k"); axes[0].set_ylabel("耗时 ms")
    ks2 = [r["k"] for r in r2]
    axes[1].plot(ks2, [r["incremental_s"] * 1e3 for r in r2], "o-", label="增量更新 O(1)")
    axes[1].plot(ks2, [r["recompute_s"] * 1e3 for r in r2], "s-", label="每次重算 O(k)")
    axes[1].set_title("移动平均"); axes[1].set_xlabel("窗口 k")
    ks3 = [r["k"] for r in r3]
    axes[2].plot(ks3, [r["dual_heap_s"] * 1e3 for r in r3], "o-", label="双堆 O(log k)")
    axes[2].plot(ks3, [r["sorted_s"] * 1e3 for r in r3], "s-", label="每次排序 O(k log k)")
    axes[2].set_title("滑窗中值"); axes[2].set_xlabel("窗口 k")
    for ax in axes:
        ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout()
    fig_path = os.path.join("docs", "bench_ds.png")
    fig.savefig(fig_path, dpi=130)
    print(f"计时曲线已写入 {fig_path}")


if __name__ == "__main__":
    main()
