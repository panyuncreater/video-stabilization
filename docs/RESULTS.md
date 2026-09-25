# 实验结果与复现

> 对应 AGENTS.md §9（指标口径）与 §15（交付物）。
> 数值来源：各次运行产出的 `metrics.json`（合成：`output/synthetic/metrics.json`，实拍：`output/test1/metrics.json`）。

## 一、测试素材

| 素材 | 分辨率 | 帧数 | 帧率 | 说明 |
|---|---|---|---|---|
| `data/synthetic/synthetic_shaky.mp4` | 960×540 | 200 | 30 | 生成器输出（种子 42），带真值 `ground_truth.json` |
| `data/test1.mp4` | 1280×976 | 1440 | 24 | 实拍验收素材：老电影胶片扫描件，含多镜头剪辑（不入库，需手动携带） |

合成数据幅度约束实测（§11）：帧间 ≤2.21 px / 0.086° / 0.0011；累积 30.9 px / 2.58° / 尺度 1.000–1.047。

## 二、端到端指标

### 合成视频（单镜头，回归基准）

| 指标 | M0（cv2 特征/光流） | **M1（自研 Harris + LK）** | 验收线 | 判定 |
|---|---|---|---|---|
| ITF 原视频 | 24.503 dB | 24.503 dB | — | — |
| ITF 稳定后 | 27.596 dB | **27.601 dB** | 高于原视频 | ✅ |
| ITF 提升 | +3.094 dB | **+3.098 dB** | >0 | ✅（不退化） |
| 稳定度 S | 0.8150 | **0.8081** | ≥0.5 | ✅（相对 M0 −0.85%，≤2% 门槛） |
| 裁剪率 | 0.9629 | **0.9629** | ≥0.85 | ✅ |
| 失真值 D | 0.00670 | **0.00675** | ≤0.05 | ✅ |
| 降级事件 | 0 | **0** | — | ✅ |
| 镜头切换 | 0 | **0**（单镜头正确不误报） | — | ✅ |
| 耗时 | pass1 约 2 s / pass2 39 s | **pass1 14.7 s / pass2 37.7 s** | — | — |

### 实拍 test1.mp4（多镜头胶片扫描）

| 指标 | M0（检出 3 处切换） | **M1（检出 1 处切换）** | 验收线 | 判定 |
|---|---|---|---|---|
| ITF 原视频 | 30.163 dB | 30.163 dB | — | — |
| ITF 稳定后 | 31.462 dB | **30.813 dB** | 高于原视频 | ✅ |
| ITF 提升 | +1.299 dB | **+0.650 dB** | >0 | ✅（弱于 M0，见 KNOWN_ISSUES #19） |
| 稳定度 S（逐镜头聚合） | 0.978 | **0.9996** | >0 | ✅ |
| 裁剪率 | 0.8792 | **0.9810** | ≥0.85 | ✅ |
| 失真值 D | 0.00312 | **0.00179** | 仅报告 | ✅ |
| 限幅触发 | 7 处 | **0 处** | — | ✅ |
| 降级事件 | 0 | **重检测 3 次** | — | ✅ |
| 检出切换 | [508, 880, 1263] | **[1263]** | — | 见 KNOWN_ISSUES #11 |
| 耗时 | pass1 33 s / pass2 700 s | **pass1 103 s / pass2 681 s** | — | — |

### 单元测试验收（§11）

| 项 | 实测 | 验收线 |
|---|---|---|
| 角点检出率 | 1.000 | ≥0.95 |
| 角点定位误差 | 0.000 px | ≤1 px |
| LK 端点误差 EPE | 0.0004–0.14 px（位移 0.5–3 px） | <0.3 px |
| LK 与 cv2 中位差异 | 0.0009 px | <0.5 px |
| RANSAC 平移误差 / 旋转误差 / 召回 | <0.5 px / <0.5° / ≥0.90（200 次蒙特卡洛达标率 100%/100%/100%） | 同左 |
| warp 与 cv2 对照 | PSNR = inf（光滑纹理，排除 2 px 环带） | ≥40 dB |
| 平滑器与朴素实现 | 1e-9 容差全组合一致 | 逐值一致 |

## 三、产物清单

| 路径 | 内容 |
|---|---|
| `output/synthetic/stabilized.mp4`、`output/test1/stabilized.mp4` | 稳定后视频（不入库） |
| `output/synthetic/metrics.json`、`output/test1/metrics.json` | 指标（不入库） |
| `docs/trajectory_synthetic_shaky.png`、`docs/trajectory_test1.png` | 轨迹对比图（2×2，含切换竖虚线） |
| `docs/metrics_bar_synthetic_shaky.png`、`docs/metrics_bar_test1.png` | 指标柱状图 |
| `docs/bench_ds.json`、`docs/bench_ds.png` | 数据结构计时基准 |
| `data/synthetic/ground_truth.json` | 合成真值（逐帧 M_t / C_t） |

## 四、复现步骤

```bash
# 1) 环境（详见 docs/DEVELOPMENT.md）
python -m venv .venv && source .venv/Scripts/activate     # Git Bash；CMD 用 .venv\Scripts\activate
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 2) 单元测试
python -m pytest tests/ -q          # 期望 54 passed

# 3) 生成合成数据（可跳过，仓库已含 ground_truth.json）
python tools/make_synthetic.py      # 种子 42

# 4) 合成视频端到端
python main.py --input data/synthetic/synthetic_shaky.mp4 \
               --output output/synthetic/stabilized.mp4 --smooth gauss --window 31 --vis

# 5) 实拍端到端（test1.mp4 需自备；约 13 分钟）
python main.py --input data/test1.mp4 \
               --output output/test1/stabilized.mp4 --smooth gauss --window 31 --vis

# 6) 数据结构计时基准
python tools/bench_ds.py
```

预期：合成 ITF 提升约 +3.1 dB、S≈0.81、裁剪率≈0.963、D≈0.0068、切换 0 处；实拍四项均达标（数值见上表，随素材与随机性小幅波动）。

## 五、结论

- 合成视频：四项指标全部达标，且 M1 相对 M0 **无退化**（满足 M1 放行门槛）。
- 实拍 test1.mp4：四项指标全部达标；因素材为多镜头胶片扫描件，切换检测存在假阴性、M1 的 ITF 提升弱于 M0，均已在 KNOWN_ISSUES 中记录并给出候选方案。
