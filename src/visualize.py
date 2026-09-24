"""可视化（AGENTS.md §9 v2 可视化定义）。

- 轨迹对比图：2×2 子图（t_x, t_y, θ, ln s），raw 轨迹 vs 平滑轨迹双曲线对比；
- 指标柱状图：原视频 vs 稳定视频的 ITF 与 S，另示裁剪率与失真值 D。
中文字体配置（Windows：Microsoft YaHei / SimHei），避免中文乱码。
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")  # 无显示环境
import matplotlib.pyplot as plt
import numpy as np

# 中文字体与负号显示（决策日志 2026-09-24）
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

_PARAM_NAMES = ["t_x (px)", "t_y (px)", "θ (rad)", "ln s"]
_PARAM_KEYS = ["tx", "ty", "theta", "ln_s"]


def plot_trajectories(params_raw: np.ndarray, params_smooth: np.ndarray, out_path: str) -> None:
    """轨迹对比图（2×2）：raw vs smooth。"""
    fig, axes = plt.subplots(2, 2, figsize=(12, 7))
    n = params_raw.shape[1]
    t = np.arange(n)
    for d, ax in enumerate(axes.flat):
        ax.plot(t, params_raw[d], color="#d62728", lw=1.0, label="原始轨迹")
        ax.plot(t, params_smooth[d], color="#1f77b4", lw=1.4, label="平滑轨迹")
        ax.set_title(_PARAM_NAMES[d])
        ax.set_xlabel("帧")
        ax.grid(alpha=0.3)
        ax.legend(loc="best", fontsize=8)
    fig.suptitle("相机轨迹对比（原始 vs 平滑）")
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)


def plot_metrics_bars(m: dict, out_path: str) -> None:
    """指标柱状图：ITF 对比、稳定度、裁剪率、失真值。"""
    fig, axes = plt.subplots(1, 4, figsize=(14, 3.6))

    axes[0].bar(["原视频", "稳定后"], [m["itf_original_db"], m["itf_stabilized_db"]],
                color=["#d62728", "#1f77b4"])
    axes[0].set_title("ITF (dB) ↑")

    s_val = m["stability"]["S"]
    axes[1].bar(["稳定度 S"], [s_val], color="#1f77b4")
    axes[1].set_title("稳定度 S ↑")
    axes[1].set_ylim(min(0, s_val - 0.1), 1.0)

    axes[2].bar(["裁剪率"], [m["cropping_ratio"]], color="#2ca02c")
    axes[2].axhline(0.85, color="#d62728", ls="--", lw=1, label="验收线 0.85")
    axes[2].set_title("裁剪率 ≥ 0.85")
    axes[2].set_ylim(0, 1.05)
    axes[2].legend(fontsize=8)

    axes[3].bar(["失真值 D"], [m["distortion"]], color="#9467bd")
    axes[3].set_title("失真值 D ↓")

    for ax in axes:
        ax.grid(alpha=0.3, axis="y")
    fig.suptitle("稳像量化指标")
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
