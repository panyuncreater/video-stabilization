"""量化指标（AGENTS.md §9 v2 定稿）。

- ITF 主口径：最终成片与原视频同口径全帧计算（无掩膜），PSNR 在灰度图上；
  辅助诊断口径：未裁剪 warp 中间序列 + 有效掩膜（掩膜 = 解析有效域）。
- 裁剪率：r = S_valid / S_frame。
- 失真值：D = mean(|ln s_t| + |θ_t|)，(θ, s) 从 B_t 线性部分分解。
- 稳定度：逐维二阶差分能量归一 S = mean_d(1 − E_smooth,d/E_raw,d)；
  E_raw,d < 1e-9 的维度记 0 并告警；S < 0 触发告警。
"""

from __future__ import annotations

import cv2
import numpy as np

from src.io_utils import VideoReader

EPS_ENERGY = 1e-9


def psnr_gray(a: np.ndarray, b: np.ndarray, rect: tuple[int, int, int, int] | None = None) -> float:
    """灰度 PSNR；rect=(L,T,R,B) 时仅在该矩形区域（掩膜）内计算。"""
    if a.ndim == 3:
        a = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY)
    if b.ndim == 3:
        b = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY)
    if rect is not None:
        L, T, R, B = rect
        a, b = a[T:B, L:R], b[T:B, L:R]
    mse = float(np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2))
    if mse <= 1e-12:
        return float("inf")
    return 10.0 * np.log10(255.0**2 / mse)


def compute_itf(path: str, rect: tuple[int, int, int, int] | None = None,
                max_frames: int | None = None) -> float:
    """ITF（§9）：帧间 PSNR 均值，流式读取（不缓存全帧）。

    rect 为 None 时全帧计算（成片主口径）；否则在掩膜矩形内计算（辅助诊断口径）。
    """
    vals = []
    with VideoReader(path) as reader:
        prev = reader.read()
        n = 1
        while prev is not None:
            if max_frames is not None and n >= max_frames:
                break
            curr = reader.read()
            if curr is None:
                break
            vals.append(psnr_gray(prev, curr, rect))
            prev = curr
            n += 1
    if not vals:
        raise ValueError(f"视频帧数不足，无法计算 ITF: {path}")
    return float(np.mean(vals))


def distortion(B_list: list[np.ndarray]) -> float:
    """失真值 D（§9）：D = (1/N)·Σ(|ln s_t| + |θ_t|)，B_0 = I 贡献 0。"""
    vals = []
    for B in B_list:
        a = B[0, 0] + 1j * B[1, 0]
        vals.append(abs(np.log(abs(a))) + abs(np.angle(a)))
    return float(np.mean(vals)) if vals else 0.0


def _stability_single(params_raw: np.ndarray, params_smooth: np.ndarray) -> dict:
    """单段序列的稳定度（内部函数）。"""

    def energy(p: np.ndarray) -> np.ndarray:
        d2 = p[:, 2:] - 2 * p[:, 1:-1] + p[:, :-2]  # 二阶差分
        return np.sum(d2 * d2, axis=1)

    e_raw = energy(params_raw)
    e_smooth = energy(params_smooth)
    s_per_dim = np.zeros(4)
    degenerate = []
    for d in range(4):
        if e_raw[d] < EPS_ENERGY:
            degenerate.append(d)  # 无抖动维度：记 0 并告警
            s_per_dim[d] = 0.0
        else:
            s_per_dim[d] = 1.0 - e_smooth[d] / e_raw[d]
    s_total = float(np.mean(s_per_dim))
    ref = 1.0 - e_smooth.sum() / e_raw.sum() if e_raw.sum() >= EPS_ENERGY else 0.0
    return {
        "E_raw": e_raw.tolist(),
        "E_smooth": e_smooth.tolist(),
        "S_per_dim": s_per_dim.tolist(),
        "S": s_total,
        "S_reference_unnormalized": float(ref),
        "degenerate_dims": degenerate,
        "negative": bool(s_total < 0),
    }


def stability(params_raw: np.ndarray, params_smooth: np.ndarray,
              shots: list[tuple[int, int]] | None = None) -> dict:
    """稳定度（§9 v2 逐维归一）；多镜头时**逐镜头加权聚合**（方案①，用户确认）。

    跨镜头切换处的二阶差分不具物理意义（同一序列里是两个不同场景），故按镜头
    分段计算后以帧数加权聚合；同时给出整段（不分段）结果作为参考值。
    输入 (4, N) 参数序列（t_x, t_y, θ, ln s；θ 应为解缠域）。
    """
    n = params_raw.shape[1]
    if shots is None:
        shots = [(0, n)]
    per_shot = []
    for s, e in shots:
        if e - s < 3:   # 二阶差分至少需要 3 帧
            continue
        r = _stability_single(params_raw[:, s:e], params_smooth[:, s:e])
        r["start"], r["end"], r["n_frames"] = int(s), int(e), int(e - s)
        per_shot.append(r)
    if not per_shot:
        return _stability_single(params_raw, params_smooth) | {
            "shots": [], "n_shots_used": 0, "skipped_short_shots": len(shots)}

    w = np.array([r["n_frames"] for r in per_shot], dtype=np.float64)
    wsum = w.sum()
    s_per_dim = (np.array([r["S_per_dim"] for r in per_shot]) * w[:, None]).sum(0) / wsum
    e_raw = (np.array([r["E_raw"] for r in per_shot]) * w[:, None]).sum(0) / wsum
    e_smooth = (np.array([r["E_smooth"] for r in per_shot]) * w[:, None]).sum(0) / wsum
    whole = _stability_single(params_raw, params_smooth)
    return {
        "E_raw": e_raw.tolist(),
        "E_smooth": e_smooth.tolist(),
        "S_per_dim": s_per_dim.tolist(),
        "S": float(np.mean(s_per_dim)),
        "S_reference_unnormalized": whole["S_reference_unnormalized"],
        "S_whole_sequence": whole["S"],
        "degenerate_dims": sorted({d for r in per_shot for d in r["degenerate_dims"]}),
        "negative": any(r["negative"] for r in per_shot) or float(np.mean(s_per_dim)) < 0,
        "shots": per_shot,
        "n_shots_used": len(per_shot),
        "skipped_short_shots": len(shots) - len(per_shot),
    }
