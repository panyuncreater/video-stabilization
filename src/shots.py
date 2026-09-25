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

无状态探针复核（2026-09-25 新增，KNOWN_ISSUES #11 根治，用户批准）：
  长期跟踪的点集会逐步退化——存活 ≥30 即不重检测，存活者偏向前景消失后仍存在的
  跨场景静态结构（齿孔/片框/暗部平坦区），到切换帧时存活率仅降到 ~0.55（不达 0.25
  崩溃线）、内点率仍 0.8+，两路证据同时失效——这正是 508/809/880 漏判的根因
  （「存活 30/304 = 0.099」是新鲜全集的诊断数字，退化点集永远到不了）。
  修复：MAD > 25 的候选帧上调用 probe_cut_evidence（上一帧现检角点 + 单步跟踪，
  新鲜全集）独立取证，判据改为两路证据取或——任一触发即判切换。
  探针崩溃线 0.25 标定（v2.5 空间均匀化点集、LK 残差 0.05、max_corners=500，
  test1 实测，取间隔中点）：切换帧探针存活率 0.137–0.194，常态帧 0.294–0.975。
  （v2.3 初标 0.45 基于 Plan-A 旧点集：切换 0.099–0.237 vs 常态 0.656–1.000；
  v2.5 均匀化点集含更多弱角点，常态帧存活率整体下移，须按新分布重标。）
  注意：放宽 LK 残差阈值会使切换帧探针存活率抬升（0.05→0.075 时 809 处
  0.146→0.402，暗部平坦区假存活点），两处参数存在交互——重调 LK 阈值后须重标探针线
  （2026-09-25 实验：0.075 使 test1 ITF 增益 +0.650→+0.614，证伪后已回退 0.05）。
"""

from __future__ import annotations

import cv2
import numpy as np

from src.features import detect_corners
from src.motion import estimate_similarity_ransac
from src.tracking import track_points

MAD_THRESHOLD = 25.0           # 帧间灰度平均绝对差阈值
INLIER_RATIO_THRESHOLD = 0.30  # RANSAC 内点率上限（低于此说明运动不一致）
SURVIVAL_RATIO_THRESHOLD = 0.25  # 跟踪存活比例下限（低于此说明跟踪崩溃）
MIN_SHOT_LEN = 12              # 最短镜头长度（帧）
PROBE_SURVIVAL_THRESHOLD = 0.25  # 探针（新鲜全集）存活崩溃线，标定依据见模块 docstring


def frame_mad(prev_gray: np.ndarray, curr_gray: np.ndarray) -> float:
    """帧间灰度平均绝对差（MAD，0–255 量纲）。"""
    diff = curr_gray.astype(np.float32) - prev_gray.astype(np.float32)
    return float(np.abs(diff).mean())


def probe_cut_evidence(prev_gray: np.ndarray, curr_gray: np.ndarray,
                       max_corners: int = 500,
                       rng=None) -> tuple[float | None, float | None]:
    """无状态切换取证：在 prev_gray 现检角点并单步跟踪到 curr_gray（新鲜全集）。

    根治长期跟踪点集退化（见模块 docstring）：新鲜全集在切换帧存活率崩溃
    （实测 0.099–0.237 < 0.45 崩溃线），而退化点集的 ~0.55 无法触发 0.25 线。
    返回 (存活率, 内点率)；角点不足 2 个（极端退化素材）返回 (None, None)，
    调用方回退当前跟踪点集证据。仅在 MAD 候选帧调用，全片代价可忽略。
    """
    pts = detect_corners(prev_gray, max_corners)
    if len(pts) < 2:
        return None, None
    new_pts, status = track_points(prev_gray, curr_gray, pts)
    alive = int(status.sum())
    survival = alive / len(pts)
    if alive >= 2:
        _, inl = estimate_similarity_ransac(pts[status], new_pts[status], rng=rng)
        inlier = float(inl.sum()) / alive
    else:
        inlier = 0.0
    return survival, inlier


def is_cut(mad: float, inlier_ratio: float, frames_since_last_cut: int,
           survival_ratio: float = 1.0, probe_survival: float | None = None,
           probe_inlier: float | None = None) -> bool:
    """是否判定为镜头切换。

    survival_ratio = 跟踪存活点数 / 上一帧特征点数（无跟踪时传 1.0，表示无崩溃证据）。
    probe_survival / probe_inlier = 无状态探针证据（probe_cut_evidence 的返回值，可选）；
    两路证据取或：当前跟踪点集（可能已退化为跨场景静态结构）或探针（新鲜全集）
    任一触发「运动不一致 / 跟踪崩溃」即计入。
    """
    motion_inconsistent = (inlier_ratio < INLIER_RATIO_THRESHOLD
                           or (probe_inlier is not None
                               and probe_inlier < INLIER_RATIO_THRESHOLD))
    tracking_collapsed = (survival_ratio < SURVIVAL_RATIO_THRESHOLD
                           or (probe_survival is not None
                               and probe_survival < PROBE_SURVIVAL_THRESHOLD))
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
