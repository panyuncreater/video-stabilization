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

| 指标 | M0（cv2 特征/光流） | M1（自研 Harris + LK） | **v2.3 最终（探针 + LK 0.05）** | 验收线 | 判定 |
|---|---|---|---|---|---|
| ITF 原视频 | 24.503 dB | 24.503 dB | 24.503 dB | — | — |
| ITF 稳定后 | 27.596 dB | 27.601 dB | **27.601 dB** | 高于原视频 | ✅ |
| ITF 提升 | +3.094 dB | +3.098 dB | **+3.098 dB** | >0 | ✅（相对 M0 不退化） |
| 稳定度 S | 0.8150 | 0.8081 | **0.8081** | ≥0.5 | ✅（相对 M0 −0.85%，≤2% 门槛） |
| 裁剪率 | 0.9629 | 0.9629 | **0.9629** | ≥0.85 | ✅ |
| 失真值 D | 0.00670 | 0.00675 | **0.00675** | ≤0.05 | ✅ |
| 降级事件 | 0 | 0 | **0** | — | ✅ |
| 镜头切换 | 0 | 0 | **0**（探针零误触发） | — | ✅ |
| 耗时 | pass1 约 2 s / pass2 39 s | pass1 14.7 s / pass2 37.7 s | **pass1 13.3 s / pass2 36.1 s** | — | — |

### 实拍 test1.mp4（多镜头胶片扫描）

| 指标 | M0（检出 3 处切换） | M1（检出 1 处切换） | **v2.3 最终（探针，4/4 检出）** | 验收线 | 判定 |
|---|---|---|---|---|---|
| ITF 原视频 | 30.163 dB | 30.163 dB | 30.163 dB | — | — |
| ITF 稳定后 | 31.462 dB | 30.813 dB | **30.850 dB** | 高于原视频 | ✅ |
| ITF 提升 | +1.299 dB | +0.650 dB | **+0.687 dB** | >0 | ✅（M0 差距归因金字塔 LK，见 KNOWN_ISSUES #19） |
| 稳定度 S（逐镜头聚合） | 0.978 | 0.9996 | **0.9996**（5 镜头加权） | >0 | ✅ |
| 裁剪率 | 0.8792 | 0.9810 | **0.9718** | ≥0.85 | ✅ |
| 失真值 D | 0.00312 | 0.00179 | **0.00193** | 仅报告 | ✅ |
| 限幅触发 | 7 处 | 0 处 | **0 处** | — | ✅ |
| 降级事件 | 0 | 重检测 3 次 | **重检测 2 次** | — | ✅ |
| 检出切换 | [508, 880, 1263] | [1263] | **[508, 809, 880, 1263]** | — | ✅（KNOWN_ISSUES #11 已解决） |
| 耗时 | pass1 33 s / pass2 700 s | pass1 103 s / pass2 681 s | **pass1 102 s / pass2 634 s** | — | — |

### 单元测试验收（§11）

| 项 | 实测 | 验收线 |
|---|---|---|
| 角点检出率 | 1.000 | ≥0.95 |
| 角点定位误差 | 0.000 px | ≤1 px |
| LK 端点误差 EPE | 0.0004–0.14 px（位移 0.5–3 px） | <0.3 px |
| LK 与 cv2 中位差异 | 0.0009 px | <0.5 px |
| RANSAC 平移误差 / 旋转误差 / 召回 | <0.5 px / <0.5° / ≥0.90（200 次蒙特卡洛达标率 100%/100%/100%） | 同左 |
| warp 与 cv2 对照 | 20 组随机相似变换排除 2 px 环带后 PSNR min = 82.34 dB（2026-09-25 实测）；环带差异像素占比中位 0.0000 / 最大 0.0005（§11 单独报告项） | ≥40 dB |
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
python -m pytest tests/ -q          # 期望 59 passed

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

## 五、§11 验收对照表（M2 收口，2026-09-25）

> 逐项对照 AGENTS.md §11 全部验收基准；「数据来源」可直接复跑复现。

| # | 验收项 | 验收线 | 实测 | 数据来源 | 判定 |
|---|---|---|---|---|---|
| 1 | 合成数据幅度约束（帧间 ≤5 px / ≤0.5° / ≤0.005；累积 ±40 px / ±3° / 0.95–1.05） | 规格内 | 帧间 ≤2.21 px / 0.086° / 0.0011；累积 30.9 px / 2.58° / 1.000–1.047 | §一、`tools/make_synthetic.py`（种子 42） | ✅ |
| 2 | warp 对照（排除 2 px 环带） | PSNR ≥40 dB | 20 组随机相似变换 min = **82.34 dB** | `tests/test_warp.py` | ✅ |
| 3 | warp 边界环带差异占比（单独报告项） | 不设线 | 中位 **0.0000** / 最大 **0.0005** | `tests/test_warp.py`（`-s` 输出） | ✅ 已报告 |
| 4 | RANSAC 平移误差 | <0.5 px | 200 次蒙特卡洛达标率 **100%** | `tests/test_motion.py` | ✅ |
| 5 | RANSAC 旋转误差 | <0.5° | 100% | `tests/test_motion.py` | ✅ |
| 6 | RANSAC 内点召回 | ≥90% | 100% | `tests/test_motion.py` | ✅ |
| 7 | 角点检出率 | ≥95% | **1.000** | `tests/test_features.py` | ✅ |
| 8 | 角点定位误差 | ≤1 px | **0.000 px** | `tests/test_features.py` | ✅ |
| 9 | LK 端点误差 EPE（位移 ≤5 px） | <0.3 px | **0.0004–0.14 px**（位移 0.5–3 px） | `tests/test_tracking.py` | ✅ |
| 10 | LK 与 cv2 中位差异 | <0.5 px | **0.0009 px** | `tests/test_tracking.py` | ✅ |
| 11 | 平滑器 vs 朴素（同边界规则） | 1e-9 逐值一致 | ma / median / gauss 全组合通过 | `tests/test_smoothing.py` | ✅ |
| 12 | 双堆中值 vs sorted | 一致 | 一致（含延迟删除长序列） | `tests/test_smoothing.py` | ✅ |
| 13 | 成片 ITF 高于原视频——合成 | >0 | **+3.098 dB**（24.503→27.601） | `output/synthetic/metrics.json` | ✅ |
| 14 | 成片 ITF 高于原视频——test1 | >0 | **+0.687 dB**（30.163→30.850） | `output/test1/metrics.json` | ✅ |
| 15 | 稳定度 S——合成 | ≥0.5 | **0.8081** | `output/synthetic/metrics.json` | ✅ |
| 16 | 稳定度 S——test1 | >0 | **0.9996**（5 镜头加权） | `output/test1/metrics.json` | ✅ |
| 17 | 裁剪率 | ≥0.85 | 合成 **0.9629** / test1 **0.9718** | 两份 metrics.json | ✅ |
| 18 | 输出分辨率 / 帧率 / 帧数与输入一致 | 一致 | 合成 960×540@30、200 帧；test1 1280×976@24、1440 帧——输入=输出=metrics 记录，**双份 PASS** | 2026-09-25 核对（cv2 逐帧计数） | ✅ |
| 19 | pytest 全绿 | 全绿 | **59 passed** | `python -m pytest tests/ -q` | ✅ |
| 20 | 核心模块覆盖率 | ≥80% | **98%**（heap/tracking 100%，ring_buffer 95%） | `pytest --cov`（命令见 TESTS.md） | ✅ |
| 21 | 硬性红线（§4） | 全部满足 | 自检 grep 无违规（命中均为注释说明文字） | DEVELOPMENT.md 红线自检清单 | ✅ |
| 22 | 合成视频相对 M0 不退化（M1 放行门槛，§5） | 差异 ≤2% | ITF +3.098 vs +3.094；S −0.85% | §二对比表 | ✅ |

**结论：§11 全部 22 项验收基准通过，M2 达成**（§5：红线满足 + 指标验收达标 + 文档与报告素材齐套）。剩余交付仅课程报告成稿（素材已齐，见 data_structures.md / KNOWN_ISSUES / 本文档）。

## 六、结论

- 合成视频：四项指标全部达标，M1 相对 M0 **无退化**（满足 M1 放行门槛）；v2.3 探针落地后复跑结果与 M1 基线完全一致（探针对单镜头素材零影响）。
- 实拍 test1.mp4：四项指标全部达标；v2.3 无状态探针根治切换假阴性（4/4 检出，ITF 增益 +0.650→+0.687）；M1 与 M0 的 ITF 差距归因于金字塔 LK，已文档化（KNOWN_ISSUES #19）；核心模块覆盖率 98%（§11 线 ≥80%）。
- 三项遗留问题（KNOWN_ISSUES #11/#19/#20）已全部收口，无待决事项。
- **M2 达成（2026-09-25）**：§11 全部 22 项验收基准通过（见第五节对照表）；requirements 6 项锁定与环境一致。剩余交付仅课程报告成稿（素材已齐）。
