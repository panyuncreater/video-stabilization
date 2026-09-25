# API 参考

> 对应 AGENTS.md §6 接口契约。**签名未经用户确认不得修改**；下表为当前实现（M1 + v2.5：自研特征/光流 + 无状态探针 + 角点空间均匀化）。

## 约定

- 坐标一律为 **(x, y)**；点集形状 `(N, 2)`，浮点为 `float32`（内部计算用 float64）。
- 图像为 BGR `uint8`（与 cv2 一致）；指标计算内部转灰度。
- 矩阵为 3×3 齐次相似变换；`M[:2]` 为 cv2 接受的形式。
- 帧编号 **0-based**。

## src/io_utils.py

| 名称 | 签名 / 属性 | 说明 |
|---|---|---|
| `VideoReader` | `VideoReader(path)` | 打开失败抛 `InputError`；属性 `fps`（缺失兜底 30）、`width`、`height`、`frame_count` |
| `.read()` | `-> np.ndarray | None` | 返回 BGR 帧；结束返回 None；尺寸不符抛 `InputError` |
| `.release()` / 上下文管理 | — | 支持 `with` |
| `VideoWriterWrap` | `VideoWriterWrap(path, fps, width, height)` | mp4v 编码；尺寸须为偶数，否则 `OutputConsistencyError` |
| `.write(frame)` | — | 尺寸不符抛异常；灰度自动转 BGR |
| 异常 | `InputError` / `OutputConsistencyError` | 分别对应退出码 1 / 3 |
| 常量 | `EXIT_OK=0`、`EXIT_INPUT_ERROR=1`、`EXIT_TRACKING_FAILED=2`、`EXIT_OUTPUT_INCONSISTENT=3`、`EXIT_INTERNAL=4` | 见 AGENTS §12 |

## src/features.py（M1 自研 Harris）

| 名称 | 签名 | 说明 |
|---|---|---|
| `detect_corners` | `(gray, max_corners=500, quality=DEFAULT_QUALITY) -> (N,2) float32` | 契约入口；返回按响应降序的角点（v2.5 空间均匀化：网格分桶 Top-N） |
| `detect_corners_retry_low` | `(gray, max_corners=500)` | §12 降级：quality 0.001→0.0002 重检 |
| `sobel_gradients` | `(gray) -> (gx, gy)` | 移位差分 3×3 Sobel，1/8 归一，灰度 [0,1] |
| `box_filter` | `(img, k=BOX_SIZE)` | 积分图滑窗和，中心对齐，同尺寸输出 |
| `harris_response` | `(gray) -> R` | $R=\det(H)-k\operatorname{tr}(H)^2$ |
| 常量 | `K_HARRIS=0.04`、`DEFAULT_QUALITY=0.001`、`RETRY_QUALITY=0.0002`、`BOX_SIZE=3`、`NMS_SIZE=3` | v2.5 阈值放宽（0.01→0.001）配合空间均匀化；BOXSIZE=3 原因见 KNOWN_ISSUES #1 |

## src/tracking.py（M1 自研单层 LK）

| 名称 | 签名 | 说明 |
|---|---|---|
| `track_points` | `(prev_gray, curr_gray, pts, win=15) -> (new_pts (M,2) float32, status (M,) bool)` | 批量向量化，无逐点 Python 循环 |
| `track_points_pyramid`（P4/A） | `(prev_gray, curr_gray, pts, win=15, levels=3) -> (new_pts, status)` | 粗到细金字塔 LK；2x2 均值池化降采样（`_downsample2x`），`levels` 上限 `PYRAMID_MAX_LEVELS=4` 且按尺寸自动降层。**默认不由主流水线调用**（需 `--pyramid`） |
| `_downsample2x`（P4/A） | `(img) -> float32` | 2x2 均值池化（尺寸 (h//2, w//2)）。属尺度约简，不触红线 2（几何重采样才须走 `warp.resample`） |
| 常量 | `MAX_ITERS=20`、`CONVERGE_EPS=0.01`、`LAMBDA_MIN=1e-4`、`RESIDUAL_MAX=0.05` | §8.2 参考值；2026-09-25 实验 0.075 证伪（ITF +0.614 vs +0.650）后维持 0.05 |

status 为真的四条件：窗口结构张量 $\lambda_{min} > 10^{-4}$；平均光度残差 < 0.05；累计位移 ≤ 窗口半径（7 px）；点邻域不出界。

## src/motion.py（自研 RANSAC）

| 名称 | 签名 | 说明 |
|---|---|---|
| `estimate_similarity_ransac` | `(src_pts, dst_pts, thresh=2.5, conf=0.99, rng=None) -> (M 3x3, inlier_mask (n,) bool)` | 点数 < 2 时返回 `(None, 全 False)` |
| `solve_similarity_2pts` | `(src, dst) -> (a, t) | None` | 复数法最小解；间距 < 2 px 判退化 |
| `umeyama_similarity` | `(src, dst) -> (a, t)` | 最小二乘闭式解（去反射） |
| `compose_matrix` | `(a, t) -> M 3x3` | — |
| 常量 | `DEGENERATE_DIST=2.0`、`MAX_ITERS=1000` | 自适应迭代 $k=\ln(1-conf)/\ln(1-w^2)$ |

## src/shots.py（镜头切分，v2.1；v2.3 增无状态探针）

| 名称 | 签名 | 说明 |
|---|---|---|
| `is_cut` | `(mad, inlier_ratio, frames_since_last_cut, survival_ratio=1.0, probe_survival=None, probe_inlier=None) -> bool` | 三条件判据；两路证据（当前点集 / 探针新鲜全集）取或 |
| `probe_cut_evidence` | `(prev_gray, curr_gray, max_corners=500) -> (survival, inlier)`，角点 <2 时 `(None, None)` | 无状态切换取证（KNOWN_ISSUES #11 根治）：现检角点 + 单步跟踪，仅 MAD 候选帧调用 |
| `frame_mad` | `(prev_gray, curr_gray) -> float` | 帧间灰度平均绝对差 |
| `segment_shots` | `(cut_frames, n_frames) -> [(start, end)]` | end 为开区间 |
| `collapse_shots` | `(shots, min_len=MIN_SHOT_LEN)` | 合并过短镜头 |
| `shot_lengths` / `to_gray` | — | 辅助 |
| 常量 | `MAD_THRESHOLD=25.0`、`INLIER_RATIO_THRESHOLD=0.30`、`SURVIVAL_RATIO_THRESHOLD=0.25`、`MIN_SHOT_LEN=12`、`PROBE_SURVIVAL_THRESHOLD=0.25` | 探针崩溃线标定（LK 残差 0.05）：v2.5 均匀化点集下切换帧探针存活 0.137–0.194 vs 常态 0.294–0.975，取间隔中点（v2.3 旧点集为 0.45） |

## src/trajectory.py

| 名称 | 签名 | 说明 |
|---|---|---|
| `TrajectoryBuffer` | `TrajectoryBuffer()` | 全量轨迹用可增长数组；`C_0 = I` |
| `.append(M_t)` | `-> C_t` | 累积 $C_t = M_t C_{t-1}$；若已标记新镜头则 $C=I$ |
| `.start_new_shot()` | — | 下一帧作为新镜头起点 |
| `.matrices` / `__len__` | — | — |
| `decompose` | `(matrices) -> (4, N)` | 顺序 $(t_x, t_y, \theta, \ln s)$ |
| `rebuild` | `(params) -> [M...]` | cos/sin 重建 |
| `clamp_drift` | `(params_raw, params_smooth, tx_lim, theta_lim, ln_s_lim) -> (params, events)` | 逐维截断 $\delta$，返回截断处数 |

## src/smoothing.py

统一接口：`__init__(window: int)`、`update(x) -> float | None`、`flush() -> list[float]`。

| 类 | 说明 |
|---|---|
| `MovingAverageSmoother` | 环形缓冲 + 增量窗口和，$O(1)$ |
| `GaussianSmoother(window, sigma=None)` | 手写高斯核，默认 $\sigma=$ window/6，滑窗点积 $O(k)$ |
| `MedianSmoother` | 双堆 + 哈希表延迟删除，$O(\log k)$ |
| `create_smoother(name, window)` | name ∈ {`ma`, `gauss`, `median`} |

时序：`update(x_t)` 返回 $y_{t-r}$（$r=$ window//2），$t<r$ 返回 `None`；序列结束后 `flush()` 返回尾部 $r$ 个值；两者输出总数 $=N$。部分窗口（头/尾）内权重重归一，中值元素为偶数取两中位均值。

## src/warp.py

| 名称 | 签名 | 说明 |
|---|---|---|
| `warp_frame` | `(img, M) -> out` | M 为**输入→输出**正向；内部求逆采样；输出同尺寸；越界填 0 |
| `resample` | `(img, Minv, out_w, out_h) -> out` | 采样核；`Minv` 为输出→输入；供 crop 复用 |

## src/crop.py

| 名称 | 签名 | 说明 |
|---|---|---|
| `frame_valid_rect` | `(B, width, height) -> (cx, cy, w, h)` | 单帧旋转矩形的同心内接轴对齐矩形（闭式） |
| `compute_crop_rect` | `(B_list, width, height) -> (L, T, R, B)` | 全片交集；空交集抛 `ValueError` |
| `cropping_ratio` | `(rect, width, height) -> float` | §9 裁剪率 |
| `warp_crop_resize` | `(frame, B, rect, out_w, out_h) -> frame` | 补偿+裁剪+缩放复合为单次重采样 |

## src/metrics.py

| 名称 | 签名 | 说明 |
|---|---|---|
| `psnr_gray` | `(a, b, rect=None) -> float` | 灰度 PSNR；`rect` 为掩膜诊断口径 |
| `compute_itf` | `(path, rect=None, max_frames=None) -> float` | 流式读取，不缓存全帧 |
| `distortion` | `(B_list) -> float` | $D=\frac1N\sum(|\ln s_t|+|\theta_t|)$ |
| `stability` | `(params_raw, params_smooth, shots=None) -> dict` | 逐维归一；`shots` 给定时逐镜头加权聚合 |

`stability` 返回键：`E_raw`、`E_smooth`、`S_per_dim`、`S`、`S_reference_unnormalized`、`S_whole_sequence`、`degenerate_dims`、`negative`、`shots`（分镜头明细）、`n_shots_used`、`skipped_short_shots`。

## src/visualize.py

| 名称 | 签名 | 说明 |
|---|---|---|
| `plot_trajectories` | `(params_raw, params_smooth, out_path, cuts=None)` | 2×2 子图；`cuts` 画切换竖虚线 |
| `plot_metrics_bars` | `(m, out_path)` | ITF 对比 / S / 裁剪率（含 0.85 验收线）/ D |

中文字体：`Microsoft YaHei` → `SimHei` → `DejaVu Sans` 回退，`axes.unicode_minus=False`。

## 命令行（main.py）

```
python main.py --input <mp4> --output <mp4> [--smooth ma|gauss|median] [--window 31]
               [--max-corners 500] [--vis]
               [--clamp-tx 30] [--clamp-theta 3.0] [--clamp-ln-s 0.05] [--no-clamp]
               [--no-diagnostic] [--pyramid] [--seed 42]
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--smooth` | `gauss` | 平滑器类型 |
| `--window` | `31` | 平滑窗口（偶数自动 +1，建议 15–61） |
| `--max-corners` | `500` | 每帧角点上限 |
| `--vis` | 关 | 输出 docs/trajectory_\<stem\>.png、docs/metrics_bar_\<stem\>.png |
| `--clamp-tx/-theta/-ln-s` | 30 px / 3° / 0.05 | 漂移限幅 |
| `--no-clamp` | 关 | 关闭限幅 |
| `--no-diagnostic` | 关（保留诊断） | P2/C：跳过纯诊断的中间 warp 与掩膜 ITF（§9 辅助口径，不参与任何验收判据）。**不传 = 与历史版本逐位一致**；传则 pass2 更快，`itf_warped_masked_db` 记 null、`diagnostic.masked_itf=false` |
| `--pyramid` | 关（单层 LK） | P4/A：启用粗到细金字塔 LK（§8.2 加分项）。**默认关闭以保证既有标定与指标逐位不变**；启用后须重标探针崩溃线并重跑双份回归（参数交互见 KNOWN_ISSUES #23） |
| `--seed` | `42` | RANSAC / 镜头探针的随机种子。**同一输入 + 同一种子 → 逐位可复现**；不传则用默认 42（可复现）。修复前 rng 无种子导致 test1 成片每次不同（KNOWN_ISSUES #24） |

辅助工具：

```
python tools/make_synthetic.py [--seed 42] [--frames 200] [--width 960] [--height 540] [--fps 30] [--out-dir data/synthetic]
python tools/bench_ds.py
python tools/verify_env.py [--run-tests] [--cov] [--json out.json]
python tools/verify_invariance.py --baseline A.json --candidate B.json [--baseline-video A.mp4 --candidate-video B.mp4]
python tools/transfer_check.ps1 [-Full] [-RunTest1] [-Cov] [-SkipTests]
python tools/profile_pipeline.py [--width 960] [--height 540] [--frames 64] [--json docs/profile_pass2.json] [--md docs/RESULTS.md]
python tools/profile_smoothers.py [--stage synth|test1|both] [--force] [--no-diagnostic] [--max-configs N] [--json docs/smoother_sweep.json] [--md docs/RESULTS.md]
```

## metrics.json 结构

```jsonc
{
  "input": "...", "output": "...", "n_frames": 1440, "fps": 24.0, "width": 1280, "height": 976,
  "smoother": { "type": "gauss", "window": 31, "latency_frames": 15 },
  "seed": 42,                              // RANSAC/探针随机种子（可复现性）
  "diagnostic": { "masked_itf": true },   // P2 新增：false = 本次运行跳过了掩膜 ITF 诊断
  "clamp": { "enabled": true, "tx_px": 30, "theta_deg": 3.0, "ln_s": 0.05, "events": 0 },
  "shots": { "n_shots": 5, "cuts": [508, 809, 880, 1263],
             "segments": [[0,508],[508,809],[809,880],[880,1263],[1263,1440]] },
  "metrics": {
    "itf_original_db": 30.163, "itf_stabilized_db": 31.352, "itf_warped_masked_db": 31.190,
    "cropping_ratio": 0.9685, "cropping_ratio_ok": true,
    "distortion": 0.00187,
    "stability": { "E_raw": [...], "E_smooth": [...], "S_per_dim": [...], "S": 0.9967,
                   "S_reference_unnormalized": 0.0131, "S_whole_sequence": 0.0960,
                   "degenerate_dims": [], "negative": false,
                   "shots": [ { ...每镜头明细：E_raw/E_smooth/S_per_dim/S/S_reference_unnormalized/degenerate_dims/negative/start/end/n_frames... } ],
                   "n_shots_used": 5, "skipped_short_shots": 0 }
  },
  "degradations": { "mt_identity_frames": 0, "ransac_fallback_frames": 0,
                    "redetection_frames": 47, "shot_cuts": [508, 809, 880, 1263] },
  "runtime_sec": { "pass1": 98.2, "pass2": 1055.3 }
}
```

> 数值为 v2.5 最终回归（test1.mp4，探针 4/4 检出 + 角点空间均匀化）的实测输出；合成视频为单镜头（`cuts: []`、`n_shots: 1`）。`S_whole_sequence` 为整段参考口径（§9 v2.1 说明两种口径不可直接比较）。v2.5 均匀化点集含更多弱角点，`redetection_frames` 由 2 升至 47（§12 存活 <30 重检测规则触发，非缺陷）。
