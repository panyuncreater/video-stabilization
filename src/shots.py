"""镜头切分（方案①，2026-09-25 用户确认）：切换检测 + 镜头分段。

背景：test1.mp4 为多镜头剪辑素材（胶片扫描件）；若按单镜头假设累积全局轨迹，
切换处会污染轨迹 → 平滑滞后 → 补偿偏差触及限幅 → 全片有效域交集被压缩
（实测裁剪率 0.786 < 0.85）。本模块在 pass 1 中识别切换，使轨迹按镜头分段。

判据（三条件，阈值由 test1.mp4 实测分布确定，见 PROJECT_STATE 决策日志）：
  切换 ⟺ 帧间 MAD > 25.0，且「运动不一致」或「跟踪存活崩溃」，且距上次切换 ≥ 12 帧。
  - MAD 单条件会把「快速甩镜/平移」误判为切换；
  - 内点率一致性：真切换无法被单个相似变换解释（内点率崩塌），甩镜虽然帧差大但
    运动一致（内点率高），不应切分；
  - **跟踪存活比例（v2.1 修订）**：胶片扫描类素材存在跨场景恒定的静态结构
    （齿孔/片框），切换时这些点仍被稳定跟踪，导致内点率居高（实测切换帧内点率
    0.80 而存活率仅 0.099），故补入存活率崩溃条件才能覆盖；
  - 最短镜头长度抑制抖动式连续触发。

实测依据：MAD 中位 2.25 / P99 13.2，切换帧（508/809/880/1263）MAD 34–42，
与次高值 13.6 之间有 2.5 倍空档；切换帧存活率 0.10 vs 常态 0.95 以上。
"""

from __future__ import annotations

import cv2
import numpy as np

MAD_THRESHOLD = 25.0           # 帧间灰度平均绝对差阈值
INLIER_RATIO_THRESHOLD = 0.30  # RANSAC 内点率上限（低于此说明运动不一致）
SURVIVAL_RATIO_THRESHOLD = 0.25  # 跟踪存活比例下限（低于此说明跟踪崩溃）
MIN_SHOT_LEN = 12              # 最短镜头长度（帧）


def frame_mad(prev_gray: np.ndarray, curr_gray: np.ndarray) -> float:
    """帧间灰度平均绝对差（MAD，0–255 量纲）。"""
    diff = curr_gray.astype(np.float32) - prev_gray.astype(np.float32)
    return float(np.abs(diff).mean())


def is_cut(mad: float, inlier_ratio: float, frames_since_last_cut: int,
           survival_ratio: float = 1.0) -> bool:
    """是否判定为镜头切换。

    survival_ratio = 跟踪存活点数 / 上一帧特征点数（无跟踪时传 1.0，表示无崩溃证据）。
    """
    motion_inconsistent = inlier_ratio < INLIER_RATIO_THRESHOLD
    tracking_collapsed = survival_ratio < SURVIVAL_RATIO_THRESHOLD
    return (mad > MAD_THRESHOLD
            and (motion_inconsistent or tracking_collapsed)
            and frames_since_last_cut >= MIN_SHOT_LEN)


def segment_shots(cut_frames: list[int], n_frames: int) -> list[tuple[int, int]]:
    """由切换帧列表得到镜头区间列表 [(start, end)]（end 为开区间）。"""
    bounds = [0] + [int(t) for t in cut_frames if 0 < t < n_frames] + [n_frames]
    return [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]


def shot_lengths(shots: list[tuple[int, int]]) -> list[int]:
    return [e - s for s, e in shots]


def collapse_shots(shots: list[tuple[int, int]], min_len: int = MIN_SHOT_LEN) -> list[tuple[int, int]]:
    """合并过短镜头到相邻镜头（平滑/指标需要 ≥3 帧，过短无意义）。"""
    if not shots:
        return []
    merged = [shots[0]]
    for s, e in shots[1:]:
        ps, pe = merged[-1]
        if pe - ps < min_len or e - s < min_len:
            merged[-1] = (ps, e)
        else:
            merged.append((s, e))
    if len(merged) > 1 and merged[-1][1] - merged[-1][0] < min_len:
        ps, _ = merged[-2]
        merged[-2] = (ps, merged[-1][1])
        merged.pop()
    return merged


def to_gray(frame: np.ndarray) -> np.ndarray:
    """BGR → 灰度（视频色彩转换，红线 5 允许）。"""
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
