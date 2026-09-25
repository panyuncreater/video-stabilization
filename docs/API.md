# API 参考

> 对应 AGENTS.md §6 接口契约。**签名未经用户确认不得修改**；下表为当前实现（M1 后）。

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
| `detect_corners` | `(gray, max_corners=500, quality=DEFAULT_QUALITY) -> (N,2) float32` | 契约入口；返回按响应降序的角点 |
| `detect_corners_retry_low` | `(gray, max_corners=500)` | §12 降级：quality 0.01→0.005 重检 |
| `sobel_gradients` | `(gray) -> (gx, gy)` | 移位差分 3×3 Sobel，1/8 归一，灰度 [0,1] |
| `box_filter` | `(img, k=BOX_SIZE)` | 积分图滑窗和，中心对齐，同尺寸输出 |
| `harris_response` | `(gray) -> R` | $R=\det(H)-k\operatorname{tr}(H)^2$ |
| 常量 | `K_HARRIS=0.04`、`DEFAULT_QUALITY=0.01`、`RETRY_QUALITY=0.005`、`BOX_SIZE=3`、`NMS_SIZE=3` | BOX_SIZE=3 的原因见 KNOWN_ISSUES #1 |

## src/tracking.py（M1 自研单层 LK）

| 名称 | 签名 | 说明 |
|---|---|---|
| `track_points` | `(prev_gray, curr_gray, pts, win=15) -> (new_pts (M,2) float32, status (M,) bool)` | 批量向量化，无逐点 Python 循环 |
| 常量 | `MAX_ITERS=20`、`CONVERGE_EPS=0.01`、`LAMBDA_MIN=1e-4`、`RESIDUAL_MAX=0.05` | §8.2 允许 ±50% 调整（须记 STATE） |

status 为真的四条件：窗口结构张量 $\lambda_{min} > 10^{-4}$；平均光度残差 < 0.05；累计位移 ≤ 窗口半径（7 px）；点邻域不出界。

## src/motion.py（自研 RANSAC）

| 名称 | 签名 | 说明 |
|---|---|---|
| `estimate_similarity_ransac` | `(src_pts, dst_pts, thresh=2.5, conf=0.99, rng=None) -> (M 3x3, inlier_mask (n,) bool)` | 点数 < 2 时返回 `(None, 全 False)` |
| `solve_similarity_2pts` | `(src, dst) -> (a, t) | None` | 复数法最小解；间距 < 2 px 判退化 |
| `umeyama_similarity` | `(src, dst) -> (a, t)` | 最小二乘闭式解（去反射） |
| `compose_matrix` | `(a, t) -> M 3x3` | — |
| 常量 | `DEGENERATE_DIST=2.0`、`MAX_ITERS=1000` | 自适应迭代 $k=\ln(1-conf)/\ln(1-w^2)$ |

## src/shots.py（镜头切分，v2.1）

| 名称 | 签名 | 说明 |
|---|---|---|
| `is_cut` | `(mad, inlier_ratio, frames_since_last_cut, survival_ratio=1.0) -> bool` | 三条件判据 |
| `frame_mad` | `(prev_gray, curr_gray) -> float` | 帧间灰度平均绝对差 |
| `segment_shots` | `(cut_frames, n_frames) -> [(start, end)]` | end 为开区间 |
| `collapse_shots` | `(shots, min_len=MIN_SHOT_LEN)` | 合并过短镜头 |
| `shot_lengths` / `to_gray` | — | 辅助 |
| 常量 | `MAD_THRESHOLD=25.0`、`INLIER_RATIO_THRESHOLD=0.30`、`SURVIVAL_RATIO_THRESHOLD=0.25`、`MIN_SHOT_LEN=12` | — |

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
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `--smooth` | `gauss` | 平滑器类型 |
| `--window` | `31` | 平滑窗口（偶数自动 +1，建议 15–61） |
| `--max-corners` | `500` | 每帧角点上限 |
| `--vis` | 关 | 输出 docs/trajectory_\<stem\>.png、docs/metrics_bar_\<stem\>.png |
| `--clamp-tx/-theta/-ln-s` | 30 px / 3° / 0.05 | 漂移限幅 |
| `--no-clamp` | 关 | 关闭限幅 |

辅助工具：

```
python tools/make_synthetic.py [--seed 42] [--frames 200] [--width 960] [--height 540] [--fps 30] [--out-dir data/synthetic]
python tools/bench_ds.py
```

## metrics.json 结构

```jsonc
{
  "input": "...", "output": "...", "n_frames": 1440, "fps": 24.0, "width": 1280, "height": 976,
  "smoother": { "type": "gauss", "window": 31, "latency_frames": 15 },
  "clamp": { "enabled": true, "tx_px": 30, "theta_deg": 3.0, "ln_s": 0.05, "events": 0 },
  "shots": { "n_shots": 2, "cuts": [1263], "segments": [[0,1263],[1263,1440]] },
  "metrics": {
    "itf_original_db": 30.163, "itf_stabilized_db": 30.813, "itf_warped_masked_db": 30.65,
    "cropping_ratio": 0.981, "cropping_ratio_ok": true,
    "distortion": 0.00179,
    "stability": { "E_raw": [...], "E_smooth": [...], "S_per_dim": [...], "S": 0.9996,
                   "S_reference_unnormalized": ..., "S_whole_sequence": ...,
                   "degenerate_dims": [], "negative": false,
                   "shots": [...], "n_shots_used": 2, "skipped_short_shots": 0 }
  },
  "degradations": { "mt_identity_frames": 0, "ransac_fallback_frames": 0,
                    "redetection_frames": 3, "shot_cuts": [1263] },
  "runtime_sec": { "pass1": 103.1, "pass2": 680.8 }
}
```
