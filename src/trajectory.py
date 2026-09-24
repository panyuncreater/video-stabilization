"""轨迹管理（AGENTS.md §6/§7）：全量累积轨迹 + 参数空间分解/重建 + 漂移限幅。

存储约定（v2 定稿）：全量轨迹用可增长数组（list）存储，供平滑/指标/可视化使用；
定长滑窗需求一律复用 ds/ring_buffer（环形缓冲不承载全量历史）。

数学约定（§7，0-based）：M_t（t=1..N-1）把第 t-1 帧坐标映射到第 t 帧；
C_t = M_t·C_{t-1}，C_0 = I；参数空间为 (t_x, t_y, θ, ln s)；
B_t = C_t^smooth·C_t^{-1}，B_0 = I。
"""

from __future__ import annotations

import numpy as np


class TrajectoryBuffer:
    """全量累积轨迹缓冲（可增长数组）。C_0 = I 自动占位。"""

    def __init__(self):
        self._mats: list[np.ndarray] = [np.eye(3)]

    def append(self, M_t: np.ndarray) -> np.ndarray:
        """追加帧间变换 M_t，累积 C_t = M_t·C_{t-1}，返回 C_t。"""
        c = np.asarray(M_t, dtype=np.float64) @ self._mats[-1]
        self._mats.append(c)
        return c

    @property
    def matrices(self) -> list[np.ndarray]:
        return self._mats

    def __len__(self) -> int:
        return len(self._mats)


def decompose(matrices: list[np.ndarray]) -> np.ndarray:
    """3x3 相似矩阵序列 → 参数空间 (t_x, t_y, θ, ln s)，返回 (4, N)。

    相似矩阵线性部分唯一确定 s 与 θ（sR 的极分解无歧义）。
    """
    n = len(matrices)
    out = np.zeros((4, n))
    for i, M in enumerate(matrices):
        a = M[0, 0] + 1j * M[1, 0]
        out[0, i] = M[0, 2]
        out[1, i] = M[1, 2]
        out[2, i] = np.angle(a)
        out[3, i] = np.log(abs(a))
    return out


def rebuild(params: np.ndarray) -> list[np.ndarray]:
    """参数空间 (4, N) → 3x3 相似矩阵序列（cos/sin 天然处理 θ 的主值回绕）。"""
    n = params.shape[1]
    out = []
    for i in range(n):
        tx, ty, th, ls = params[:, i]
        s = np.exp(ls)
        c, sn = s * np.cos(th), s * np.sin(th)
        out.append(np.array([[c, -sn, tx], [sn, c, ty], [0.0, 0.0, 1.0]]))
    return out


def clamp_drift(params_raw: np.ndarray, params_smooth: np.ndarray,
                tx_lim: float, theta_lim: float, ln_s_lim: float):
    """漂移限幅（§7）：δ = p_smooth − p_raw 逐维截断到 ±lim（θ 在解缠域比较）。

    返回 (限幅后参数 (4,N), 截断事件数)。
    """
    lims = np.array([tx_lim, tx_lim, theta_lim, ln_s_lim])[:, None]
    delta = params_smooth - params_raw
    clamped_delta = np.clip(delta, -lims, lims)
    events = int(np.count_nonzero(clamped_delta != delta))
    return params_raw + clamped_delta, events
