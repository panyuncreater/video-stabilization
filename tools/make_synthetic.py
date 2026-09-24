"""合成抖动视频生成器（AGENTS.md §11 规格）。

输出（默认 data/synthetic/）：
- synthetic_shaky.mp4：960×540、200 帧、30 fps 的合成手持抖动视频；
- ground_truth.json：逐帧真值 M_t（第 t-1 帧 → 第 t 帧）与 C_t（累积轨迹）。

规格（§11）：
- 背景为结构化纹理（棋盘 + 几何图形，保证角点密度）；
- 轨迹 = 低频慢漂移（有界正弦）+ 高频抖动（OU 过程，白噪声平滑）；
- 帧间平移 ≤ 5 px、旋转增量 ≤ 0.5°、尺度增量 ≤ 0.005；
- 累积范围：平移 ±40 px、旋转 ±3°、尺度 0.95–1.05；
- 默认种子 42（可复现）。

约定：帧 t = warp_frame(base, C_t)，C_0 = I，与流水线 §7 约定一致。
本文件为数据生成工具，非稳像主实现；几何变换复用自研 src.warp 以保持口径一致。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.warp import warp_frame  # noqa: E402


def make_base_image(w: int, h: int, rng: np.random.Generator) -> np.ndarray:
    """结构化纹理背景（彩色 BGR）：棋盘 + 几何图形，角点丰富。"""
    cell = 36
    yy, xx = np.mgrid[0:h, 0:w]
    board = ((xx // cell + yy // cell) % 2).astype(np.float64)
    base = 60 + 120 * board  # 60 / 180 两灰度
    img = np.dstack([base, base, base]).astype(np.uint8)
    # 几何图形（彩色），提供大量稳定角点
    for _ in range(14):
        cx, cy = int(rng.integers(0, w)), int(rng.integers(0, h))
        r = int(rng.integers(14, 46))
        color = tuple(int(c) for c in rng.integers(40, 255, 3))
        if rng.random() < 0.5:
            cv2.circle(img, (cx, cy), r, color, -1)
        else:
            cv2.rectangle(img, (cx - r, cy - r), (cx + r, cy + r), color, -1)
    for _ in range(10):
        p1 = (int(rng.integers(0, w)), int(rng.integers(0, h)))
        p2 = (int(rng.integers(0, w)), int(rng.integers(0, h)))
        color = tuple(int(c) for c in rng.integers(40, 255, 3))
        cv2.line(img, p1, p2, color, int(rng.integers(2, 5)))
    noise = rng.normal(0, 2.0, (h, w, 1))
    return np.clip(img.astype(np.float64) + noise, 0, 255).astype(np.uint8)


def _bounded_jitter(n: int, inc_max: float, cum_max: float, rng: np.random.Generator,
                    smooth_sigma: float = 4.0) -> np.ndarray:
    """白噪声经高斯核平滑的有界抖动增量过程（§11「平滑随机变换」）。

    构造保证（确定性，非概率）：
    - 增量经高斯核平滑（轨迹平滑）；
    - max|增量| ≤ inc_max（归一化硬限幅）；
    - max|累积| ≤ cum_max（超限则整体同步缩小增量，增量限幅不被破坏）；
    - 累积序列首值为 0（inc[0]=0 → cumsum 自然从 0 起）。

    注：np.convolve 仅用于本数据生成工具；红线 4 约束对象是主实现 src/，此处不适用。
    """
    klen = int(6 * smooth_sigma + 1) | 1
    x = np.arange(klen) - klen // 2
    kern = np.exp(-0.5 * (x / smooth_sigma) ** 2)
    kern /= kern.sum()
    inc = np.convolve(rng.normal(0.0, 1.0, n), kern, mode="same")
    inc[0] = 0.0
    inc = inc / np.abs(inc).max() * inc_max
    cum = np.cumsum(inc)
    m = np.abs(cum).max()
    if m > cum_max:
        inc *= cum_max / m
        cum = np.cumsum(inc)
    return cum


def generate_trajectory(n: int, rng: np.random.Generator):
    """生成累积轨迹参数 (tx, ty, theta, ln_s)，返回 (4, n)，params[:,0] = 0（C_0 = I）。

    轨迹 = 低频慢漂移（正弦，零初相，幅值 A）+ 高斯平滑有界抖动（构造性限幅）。
    预算（§11 约束，留安全边距，check_constraints 复核兜底）：
    - 平移：抖动增量 ≤4.0 px + 漂移导数 ≤0.57 → <5；抖动累积 ≤24 + 漂移 12 → <40。
    - 旋转：抖动增量 ≤0.43° + 漂移导数 ≤0.023 → <0.5°；抖动累积 ≤2.0° + 0.8 → <3°。
    - 尺度：抖动增量 ≤0.0042 + 0.0004 → <0.005；抖动累积 ≤0.036 + 0.010 → s∈[0.955,1.047]。
    """
    t = np.arange(n)
    drift_tx = 12.0 * np.sin(2 * np.pi * t / n * 1.5)
    drift_ty = -10.0 * np.sin(2 * np.pi * t / n * 1.1)
    drift_th = np.deg2rad(0.8) * np.sin(2 * np.pi * t / n * 0.9)
    drift_ls = 0.010 * np.sin(2 * np.pi * t / n * 1.3)
    jit_tx = _bounded_jitter(n, 4.0, 24.0, rng)
    jit_ty = _bounded_jitter(n, 4.0, 24.0, rng)
    jit_th = _bounded_jitter(n, np.deg2rad(0.43), np.deg2rad(2.0), rng)
    jit_ls = _bounded_jitter(n, 0.0042, 0.036, rng)

    tx = drift_tx + jit_tx
    ty = drift_ty + jit_ty
    th = drift_th + jit_th
    ls = drift_ls + jit_ls
    params = np.stack([tx, ty, th, ls], axis=0)
    return params


def params_to_matrix(tx: float, ty: float, theta: float, ln_s: float) -> np.ndarray:
    s = np.exp(ln_s)
    c, sn = s * np.cos(theta), s * np.sin(theta)
    return np.array([[c, -sn, tx], [sn, c, ty], [0.0, 0.0, 1.0]])


def check_constraints(params: np.ndarray) -> dict:
    """校验 §11 幅度约束，返回各约束的实际极值。"""
    d = np.diff(params, axis=1)
    info = {
        "max_frame_translation_px": float(np.max(np.abs(d[0:2]))),
        "max_frame_rotation_deg": float(np.rad2deg(np.max(np.abs(d[2])))),
        "max_frame_scale": float(np.max(np.abs(d[3]))),
        "cum_translation_px": float(np.max(np.abs(params[0:2]))),
        "cum_rotation_deg": float(np.rad2deg(np.max(np.abs(params[2])))),
        "cum_scale_min": float(np.exp(np.min(params[3]))),
        "cum_scale_max": float(np.exp(np.max(params[3]))),
    }
    assert info["max_frame_translation_px"] <= 5.0, info
    assert info["max_frame_rotation_deg"] <= 0.5, info
    assert info["max_frame_scale"] <= 0.005, info
    assert info["cum_translation_px"] <= 40.0, info
    assert info["cum_rotation_deg"] <= 3.0, info
    assert info["cum_scale_min"] >= 0.95 and info["cum_scale_max"] <= 1.05, info
    return info


def main() -> None:
    ap = argparse.ArgumentParser(description="合成抖动视频生成器（§11 规格）")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--frames", type=int, default=200)
    ap.add_argument("--width", type=int, default=960)
    ap.add_argument("--height", type=int, default=540)
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--out-dir", default=os.path.join("data", "synthetic"))
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    rng = np.random.default_rng(args.seed)

    base = make_base_image(args.width, args.height, rng)
    # 轨迹生成：实测归一后仍可能因单次实现超约束，顺序消耗 rng 重试（确定性）
    params, info = None, None
    for _ in range(100):
        candidate = generate_trajectory(args.frames, rng)
        try:
            info = check_constraints(candidate)
            params = candidate
            break
        except AssertionError:
            continue
    if params is None:
        raise RuntimeError("轨迹生成 100 次仍不满足 §11 约束（不应发生，请报告）")

    # 真值矩阵
    c_list = [params_to_matrix(*params[:, t]) for t in range(args.frames)]
    m_list = [np.eye(3)] + [c_list[t] @ np.linalg.inv(c_list[t - 1]) for t in range(1, args.frames)]

    video_path = os.path.join(args.out_dir, "synthetic_shaky.mp4")
    writer = cv2.VideoWriter(video_path, cv2.VideoWriter_fourcc(*"mp4v"), args.fps, (args.width, args.height))
    if not writer.isOpened():
        raise RuntimeError(f"无法创建输出视频: {video_path}")
    for t in range(args.frames):
        writer.write(warp_frame(base, c_list[t]))
    writer.release()

    gt = {
        "seed": args.seed,
        "width": args.width,
        "height": args.height,
        "n_frames": args.frames,
        "fps": args.fps,
        "convention": "frame_t = warp(base, C_t); M_t: frame t-1 -> t; C_0 = I",
        "constraint_check": info,
        "frames": [
            {
                "t": t,
                "params": {"tx": float(params[0, t]), "ty": float(params[1, t]),
                           "theta": float(params[2, t]), "ln_s": float(params[3, t])},
                "M_t": m_list[t].tolist(),
                "C_t": c_list[t].tolist(),
            }
            for t in range(args.frames)
        ],
    }
    gt_path = os.path.join(args.out_dir, "ground_truth.json")
    with open(gt_path, "w", encoding="utf-8") as f:
        json.dump(gt, f, ensure_ascii=False)

    print(f"已生成: {video_path} ({args.frames} 帧, {args.width}x{args.height}, {args.fps} fps)")
    print(f"真值:   {gt_path}")
    print("约束校验:", json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
