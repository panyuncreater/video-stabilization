"""视频稳像流水线入口（AGENTS.md §6/§7）。

两遍离线架构（§7 架构约定）：
- pass 1：读入全部帧，逐帧估计 M_t（M0 特征/光流临时用 cv2，标 TODO(SELF-IMPL)），
  累积全量轨迹 C_t，并流式计算原视频 ITF；
- pass 2：全量轨迹参数空间居中平滑 → 锚定 → 限幅 → 重建 C^smooth → 逐帧 B_t 补偿
  warp（重读文件）→ 统一裁剪 → 经 warp 采样核缩放回原分辨率 → 写盘；
  最后计算指标、（--vis）出图、写 metrics.json（与输出视频同目录）。

异常降级（§12）：角点 <20 降阈值重检、RANSAC 内点 <6 沿用 M_{t-1}（连续 5 帧退出码 2）、
存活 <30 重新检测；非零退出不产出 metrics.json 并删除部分输出。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time

import cv2
import numpy as np

from src import (crop, features, io_utils, metrics, motion, shots, smoothing,
                 tracking, trajectory, visualize, warp)

logger = logging.getLogger("stabilizer")

MIN_CORNERS = 20       # §12：角点数下限（不足降阈值重检一次，仍不足 M_t = I）
MIN_INLIERS = 6        # §12：RANSAC 内点下限（不足沿用 M_{t-1}）
MAX_FAIL_STREAK = 5    # §12：连续失败上限（达到则以退出码 2 终止）
MIN_TRACKED = 30       # §12：跟踪存活下限（不足下一帧重新检测）


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="视频抖动去除（电子稳像）——两遍离线流水线")
    ap.add_argument("--input", required=True, help="输入视频路径（mp4）")
    ap.add_argument("--output", required=True, help="输出视频路径（mp4）")
    ap.add_argument("--smooth", choices=["ma", "gauss", "median"], default="gauss")
    ap.add_argument("--window", type=int, default=31, help="平滑窗口（默认 31，偶数自动 +1）")
    ap.add_argument("--max-corners", type=int, default=500)
    ap.add_argument("--vis", action="store_true", help="输出轨迹对比图与指标柱状图到 docs/")
    ap.add_argument("--clamp-tx", type=float, default=30.0, help="平移限幅 px（默认 30）")
    ap.add_argument("--clamp-theta", type=float, default=3.0, help="旋转限幅 度（默认 3）")
    ap.add_argument("--clamp-ln-s", type=float, default=0.05, help="对数尺度限幅（默认 0.05）")
    ap.add_argument("--no-clamp", action="store_true", help="关闭漂移限幅")
    return ap.parse_args()


def pass1_estimate(args, reader: io_utils.VideoReader):
    """pass 1：逐帧估计 M_t，累积轨迹，流式计算原视频 ITF。返回轨迹与统计。"""
    traj = trajectory.TrajectoryBuffer()
    deg = {"mt_identity_frames": 0, "ransac_fallback_frames": 0,
           "redetection_frames": 0, "shot_cuts": []}
    itf_orig_vals = []

    prev = reader.read()
    if prev is None:
        raise io_utils.InputError(f"视频为空或首帧读取失败: {args.input}")
    prev_gray = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)
    points = features.detect_corners(prev_gray, args.max_corners)
    m_prev = np.eye(3)
    fail_streak = 0
    last_cut = -10**9   # 上次切换帧（用于最短镜头长度约束）
    n_frames = 1

    while True:
        frame = reader.read()
        if frame is None:
            break
        frame_idx = n_frames          # 当前帧编号（0-based）
        n_frames += 1
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        itf_orig_vals.append(metrics.psnr_gray(prev, frame))

        # §12：角点数 < 20 → 降阈值重检一次；仍不足 → 该帧 M_t = I
        if len(points) < MIN_CORNERS:
            points = features.detect_corners_retry_low(prev_gray, args.max_corners)
            if len(points) < MIN_CORNERS:
                logger.warning("第 %d 帧角点数 < %d（重检后仍不足），该帧 M_t = I", frame_idx, MIN_CORNERS)
                traj.append(np.eye(3))
                m_prev = np.eye(3)
                deg["mt_identity_frames"] += 1
                fail_streak += 1
                if fail_streak >= MAX_FAIL_STREAK:
                    logger.error("连续 %d 帧估计失败，终止（退出码 2）", MAX_FAIL_STREAK)
                    sys.exit(io_utils.EXIT_TRACKING_FAILED)
                prev, prev_gray = frame, gray
                continue

        new_pts, status = tracking.track_points(prev_gray, gray, points)
        alive = int(status.sum())
        if alive >= 2:
            M, inl = motion.estimate_similarity_ransac(points[status], new_pts[status])
            inlier_ratio = float(inl.sum()) / float(alive)
        else:
            M, inl = None, np.zeros(0, dtype=bool)
            inlier_ratio = 0.0

        # 方案①：镜头切换检测（MAD 高 且 运动不一致 且 距上次切换 ≥ 最短镜头长度）
        mad = shots.frame_mad(prev_gray, gray)
        if shots.is_cut(mad, inlier_ratio, frame_idx - last_cut):
            logger.info("检测到镜头切换 @帧 %d（MAD=%.1f，内点率=%.2f），新镜头起算轨迹",
                        frame_idx, mad, inlier_ratio)
            deg["shot_cuts"].append(frame_idx)
            traj.start_new_shot()
            traj.append(np.eye(3))     # 切换帧 M_t = I，新镜头起点 C = I
            m_prev = np.eye(3)
            fail_streak = 0            # 新镜头重新起算，不累计失败
            last_cut = frame_idx
            points = features.detect_corners(gray, args.max_corners)
            prev, prev_gray = frame, gray
            continue

        if M is None or inl.sum() < MIN_INLIERS:
            logger.warning("第 %d 帧 RANSAC 内点数 < %d，沿用 M_{t-1}", n_frames - 1, MIN_INLIERS)
            M = m_prev.copy()
            deg["ransac_fallback_frames"] += 1
            fail_streak += 1
            if fail_streak >= MAX_FAIL_STREAK:
                logger.error("连续 %d 帧估计失败，终止（退出码 2）", MAX_FAIL_STREAK)
                sys.exit(io_utils.EXIT_TRACKING_FAILED)
        else:
            fail_streak = 0

        traj.append(M)
        m_prev = M

        # §12：存活 < 30 → 下一帧重新检测
        if alive < MIN_TRACKED:
            deg["redetection_frames"] += 1
            points = features.detect_corners(gray, args.max_corners)
        else:
            points = new_pts[status]

        prev, prev_gray = frame, gray

    logger.info("pass 1 完成: %d 帧, 镜头切换 %d 处 %s, 角点重检测 %d 次, "
                "M=I 降级 %d 帧, 沿用上一帧 %d 帧",
                n_frames, len(deg["shot_cuts"]), deg["shot_cuts"],
                deg["redetection_frames"], deg["mt_identity_frames"], deg["ransac_fallback_frames"])
    return traj, deg, itf_orig_vals, n_frames


def smooth_trajectory(params_raw: np.ndarray, method: str, window: int) -> np.ndarray:
    """参数空间逐维居中平滑（θ 已解缠）。返回 (4, N) 平滑参数。"""
    out = np.zeros_like(params_raw)
    for d in range(4):
        sm = smoothing.create_smoother(method, window)
        vals = []
        for x in params_raw[d]:
            y = sm.update(float(x))
            if y is not None:
                vals.append(y)
        vals.extend(sm.flush())
        out[d] = vals
    return out


def run(args) -> int:
    t0 = time.perf_counter()

    # ---------- pass 1 ----------
    with io_utils.VideoReader(args.input) as reader:
        fps, width, height = reader.fps, reader.width, reader.height
        traj, deg, itf_orig_vals, n_frames = pass1_estimate(args, reader)
    t1 = time.perf_counter()

    # ---------- 镜头分段（方案①） ----------
    shot_list = shots.collapse_shots(shots.segment_shots(deg["shot_cuts"], n_frames))

    # ---------- 轨迹平滑（参数空间，逐镜头独立） ----------
    params_raw = trajectory.decompose(traj.matrices)
    params_smooth = np.zeros_like(params_raw)
    clamp_events = 0
    for s, e in shot_list:
        params_raw[2, s:e] = np.unwrap(params_raw[2, s:e])      # θ 逐镜头解缠（§7）
        seg = smooth_trajectory(params_raw[:, s:e], args.smooth, args.window)
        # 锚定：减去本镜头平滑首点常数偏移（Δ² 能量不变；小偏差下与矩阵锚定等价，B_0 = I）
        seg = seg - seg[:, [0]]
        if not args.no_clamp:
            seg, ev = trajectory.clamp_drift(
                params_raw[:, s:e], seg,
                args.clamp_tx, np.deg2rad(args.clamp_theta), args.clamp_ln_s)
            clamp_events += ev
        params_smooth[:, s:e] = seg
    if clamp_events:
        logger.info("漂移限幅触发 %d 处（--clamp-tx %.1f px / --clamp-theta %.1f° / --clamp-ln-s %.3f）",
                    clamp_events, args.clamp_tx, args.clamp_theta, args.clamp_ln_s)
    c_smooth = trajectory.rebuild(params_smooth)
    c_raw = traj.matrices
    B_list = [c_smooth[t] @ np.linalg.inv(c_raw[t]) for t in range(len(c_raw))]

    # ---------- 裁剪（解析法） ----------
    rect = crop.compute_crop_rect(B_list, width, height)
    ratio = crop.cropping_ratio(rect, width, height)
    crop_ok = ratio >= 0.85
    if not crop_ok:
        logger.warning("裁剪率 %.4f < 0.85！按 §8.6 先报告数据（rect=%s），"
                       "不擅自放大裁剪或降低标准，请查看后讨论", ratio, rect)

    # ---------- pass 2 ----------
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    itf_warped_vals = []
    with io_utils.VideoReader(args.input) as reader, \
            io_utils.VideoWriterWrap(args.output, fps, width, height) as writer:
        prev_warped = None
        t = 0
        while True:
            frame = reader.read()
            if frame is None:
                break
            warped = warp.warp_frame(frame, B_list[t])  # 完整 warp 帧（供掩膜诊断 ITF）
            if prev_warped is not None:
                itf_warped_vals.append(metrics.psnr_gray(prev_warped, warped, rect))
            # 写出：补偿 warp + 裁剪 + 缩放复合为单次重采样（更快且避免二次插值模糊）
            writer.write(crop.warp_crop_resize(frame, B_list[t], rect, width, height))
            prev_warped = warped
            t += 1
    t2 = time.perf_counter()

    # ---------- 指标 ----------
    itf_orig = float(np.mean(itf_orig_vals))
    itf_stab = metrics.compute_itf(args.output)
    stab = metrics.stability(params_raw, params_smooth, shot_list)  # 逐镜头加权聚合（方案①）
    if stab["degenerate_dims"]:
        logger.warning("稳定度：维度 %s 原始能量过低，按退化记 0", stab["degenerate_dims"])
    if stab["negative"]:
        logger.warning("稳定度 S < 0（平滑后更差），请检查参数与数据")
    dist = metrics.distortion(B_list)

    result = {
        "input": args.input,
        "output": args.output,
        "n_frames": n_frames,
        "fps": fps,
        "width": width,
        "height": height,
        "smoother": {"type": args.smooth, "window": window_eff(args.window),
                     "latency_frames": window_eff(args.window) // 2},
        "clamp": {"enabled": not args.no_clamp, "tx_px": args.clamp_tx,
                  "theta_deg": args.clamp_theta, "ln_s": args.clamp_ln_s,
                  "events": clamp_events},
        "shots": {"n_shots": len(shot_list), "cuts": deg["shot_cuts"],
                  "segments": [[int(s), int(e)] for s, e in shot_list]},
        "metrics": {
            "itf_original_db": itf_orig,
            "itf_stabilized_db": itf_stab,
            "itf_warped_masked_db": float(np.mean(itf_warped_vals)) if itf_warped_vals else None,
            "cropping_ratio": ratio,
            "cropping_ratio_ok": crop_ok,
            "distortion": dist,
            "stability": stab,
        },
        "degradations": deg,
        "runtime_sec": {"pass1": round(t1 - t0, 3), "pass2": round(t2 - t1, 3)},
    }

    metrics_path = os.path.join(os.path.dirname(os.path.abspath(args.output)), "metrics.json")
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    logger.info("metrics.json → %s", metrics_path)

    # ---------- 可视化 ----------
    if args.vis:
        os.makedirs("docs", exist_ok=True)
        stem = os.path.splitext(os.path.basename(args.input))[0]
        p1 = os.path.join("docs", f"trajectory_{stem}.png")
        p2 = os.path.join("docs", f"metrics_bar_{stem}.png")
        visualize.plot_trajectories(params_raw, params_smooth, p1, cuts=deg["shot_cuts"])
        visualize.plot_metrics_bars(result["metrics"], p2)
        logger.info("可视化: %s, %s", p1, p2)

    print(json.dumps({
        "ITF 原视频 dB": round(itf_orig, 3),
        "ITF 稳定后 dB": round(itf_stab, 3),
        "ITF 提升": round(itf_stab - itf_orig, 3),
        "稳定度 S": round(stab["S"], 4),
        "裁剪率": round(ratio, 4),
        "失真值 D": round(dist, 5),
        "降级事件": deg,
        "限幅触发": clamp_events,
        "耗时 s": result["runtime_sec"],
    }, ensure_ascii=False, indent=2))
    return io_utils.EXIT_OK


def window_eff(window: int) -> int:
    return window + 1 if window % 2 == 0 else window


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s", stream=sys.stderr)
    args = parse_args()
    try:
        code = run(args)
    except io_utils.InputError as e:
        logger.error("%s", e)
        code = io_utils.EXIT_INPUT_ERROR
    except io_utils.OutputConsistencyError as e:
        logger.error("%s", e)
        code = io_utils.EXIT_OUTPUT_INCONSISTENT
    except Exception:
        logger.exception("内部错误（退出码 4）")
        code = io_utils.EXIT_INTERNAL
    if code != io_utils.EXIT_OK:
        # §12：非零退出不产出 metrics.json；已部分写盘的输出删除并报告
        out = getattr(args, "output", None)
        if out and os.path.exists(out):
            try:
                os.remove(out)
                logger.error("已删除部分输出: %s", out)
            except OSError:
                logger.error("部分输出删除失败，保留于: %s", out)
    sys.exit(code)


if __name__ == "__main__":
    main()
