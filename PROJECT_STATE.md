# PROJECT_STATE
更新时间：2026-09-25 00:05
当前阶段：**M0 编码完成，待放行评审**（端到端已出片；test1 裁剪率 0.786 < 0.85，按 §8.6 已报告数据，待与用户讨论）

## 已完成模块（含验收数值）
- ds/ring_buffer.py、ds/heap.py：手写环形缓冲/双堆，随机操作对拍 deque/heapq 一致。
- src/warp.py：恒等逐像素一致；与 cv2.warpAffine（OpenCV 5 正向约定）对照，排除 2px 环带 PSNR = inf（≥40 dB 达标）；越界逐点填 0。
- tools/make_synthetic.py：合成数据 960×540×200 帧（种子 42）+ 真值 JSON，§11 全部幅度约束实测通过（帧间 ≤2.21px/0.086°/0.0011，累积 30.9px/2.58°/1.047）。
- src/smoothing.py：MA/高斯/中值三平滑器（居中+flush+部分窗口重归一），与朴素实现逐值一致（1e-9）；双堆中值修复延迟删除脏顶 bug 后对拍一致。
- src/motion.py：自研 RANSAC，§11 验收全过（平移 <0.5px、旋转 <0.5°、召回 ≥90%，多种子稳健）。
- src/io_utils.py / trajectory.py / crop.py / metrics.py / visualize.py：齐备。
- src/features.py / tracking.py：**M0 临时 cv2 实现，标 TODO(SELF-IMPL)**（红线 3 M0 豁免）。
- main.py：两遍离线流水线 + CLI + §12 异常降级与退出码。
- tools/bench_ds.py：§10 计时基准（预热 3、重复 7 取中位、种子 42），结果在 docs/bench_ds.json/.png。
- **端到端指标**：
  - 合成视频：ITF 24.50→28.60 dB（+4.10）✓；S=0.815 ≥0.5 ✓；裁剪率 0.963 ≥0.85 ✓；D=0.0067 ≤0.05 ✓；降级 0 帧。
  - test1.mp4：ITF 30.16→32.38 dB（+2.21）✓；S=0.727 >0 ✓；D=0.0047（实拍仅报告）；**裁剪率 0.786 <0.85 ✗**；降级：沿用上一帧 1 帧、重检测 2 次；限幅触发 43 处；耗时 pass1 27s / pass2 684s。

## 当前模块
- M0 收尾（本文件更新 + commit），随后进入裁剪率问题讨论。

## 本次任务
- M0 全链路实现与端到端验证（合成 + 实拍双份）。

## 已知风险
- **裁剪率 0.786 < 0.85（test1.mp4）**：诊断确认 test1.mp4 为**老电影胶片扫描件**（带齿孔/圆角片框/「测试样片」水印）且**含多个镜头切换**（约 100 帧、870 帧等处轨迹阶跃即切换点）。切换污染全局轨迹模型，切换处平滑滞后使补偿偏差触及限幅（43 处），全帧有效域交集被压缩。按 §8.6 已报告数据，**禁止擅自放大裁剪或降低标准，待讨论**（候选方向：镜头切分处理 / 收紧限幅换裁剪率 / 接受并记已知问题 / 更换测试视频）。
- test1.mp4 的「胶片片门晃动 + 镜头剪辑」与合同预期的「手持抖动」输入分布不同；现有异常规则（内点 <6 沿用、连续 5 帧终止）未覆盖镜头切换语义。
- RANSAC 平移误差线 <0.5px 蒙特卡洛达标率 99%（尾部 ~1%），兜底条款已就位。
- bench 实测：RingBuffer / 双堆在 Python 层常数劣势（小 k 时慢于 list.pop(0)/sorted），渐进优势在 k≥127 才显现；argpartition 稳定 9-11x；MA 增量在 k≥31 后 1.7-2.9x。报告中须如实呈现「Python 常数因子 vs 渐进复杂度」分析。

## 本次改动（文件级清单）
- 新增 src/{warp,smoothing,motion,io_utils,trajectory,features,tracking,crop,metrics,visualize}.py
- 新增 ds/{ring_buffer,heap}.py；新增 tests/{test_ds,test_warp,test_smoothing,test_motion}.py
- 新增 tools/{make_synthetic,bench_ds}.py；新增 main.py
- 生成 data/synthetic/{synthetic_shaky.mp4(不入库),ground_truth.json}
- 生成 output/{synthetic,test1}/{stabilized.mp4(不入库),metrics.json(不入库)}
- 生成 docs/{trajectory,metrics_bar}_{synthetic_shaky,test1}.png、bench_ds.{json,png}
- AGENTS.md §7 对照注释修正（OpenCV 5 正向约定）

## 测试结果（pytest 摘要 + 数值对照表）
- pytest **30 passed**（ds 8 / warp 7 / smoothing 9 / motion 6）。
- warp vs cv2：PSNR = inf（光滑纹理）；identity 逐像素一致；(+5,0) 右移 5px 精确。
- 平滑器 vs 朴素：1e-9 容差全组合通过（含 window>N、偶数窗口、window=1）。
- RANSAC §11 验收 + 多种子稳健性全过。
- 端到端：合成与 test1 双份出片，指标见上。

## 遗留问题
- 裁剪率 0.786 处理方案待用户拍板（见已知风险）。
- 覆盖率工具（pytest-cov / coverage）为待确认新增依赖。
- README「运行方式」节待 M0 放行后补实际命令；「结果复现」待 M2。
- M1（自研 Harris + LK）未开始。

## 下一步
1. 与用户讨论裁剪率问题（候选：① 镜头切分处理——pass1 检测切换、逐镜头独立平滑与裁剪，功能增加需确认；② 收紧限幅/加大窗口换裁剪率——治标；③ 接受现状记已知问题；④ 更换测试视频）。
2. 方案确定后进入 M1：features.py / tracking.py 自研替换。

## 决策日志（数据结构选型理由 / 偏离 AGENTS.md 的记录及确认人）
- 2026-09-24：AGENTS.md v1 全量审查（28 项发现）→ 用户授权按推荐项修订为 v2，六项重大决策（两遍架构 / thresh=2.5+召回定义 / ITF 成片主口径 / 0-based / 双验收集 / resize 入红线）。确认人：用户。
- 2026-09-24：平滑口径定稿（居中 + update/flush + 部分窗口重归一）。确认人：用户（随 v2 授权）。
- 2026-09-24：漂移限幅机制纳入 §7（默认开启）。确认人：用户（随 v2 授权）。
- 2026-09-24：requirements.txt 按阿里云镜像实装锁定（numpy 2.5.3 等四项）。确认人：用户（版本号确认无误）。
- 2026-09-24：项目 venv 用 CPython 3.13 重建（原 msys2 venv 布局异常）。确认人：AI 代行（已告知）。
- 2026-09-24：pass 2 重读文件而非缓存全帧（≈5.3GB 内存风险）。确认人：AI 建议（可改）。
- 2026-09-24：Matplotlib 中文字体配置要求（Microsoft YaHei / SimHei）。实现备注。
- 2026-09-24：OpenCV 5.0.0 warpAffine 已改为「输入→输出」正向约定（实测），AGENTS.md §7 注释同步修正；自研 warp 与其逐像素一致。确认人：AI 实测（事实修正）。
- 2026-09-24：环境职责划分与去硬编码（项目用 .venv；沙箱 envs/default 不入库不引用；README 机器内容收拢第六节）。确认人：用户。
- 2026-09-24/25：crop 有效域取「逐帧内接矩形再求交」保守口径（O(N)，闭式解）；裁剪框向内取整（ceil L/T、floor R/B）保证输出无黑边；**补偿 warp + 裁剪 + 缩放复合为单次重采样**（提速 1.8x 且避免二次插值模糊）；resample 网格缓存 + uint8 走 float32。确认人：AI 实现选择（§8.6 允许课程级实现并已在注释声明保守性）。
- 2026-09-25：**test1.mp4 诊断为胶片扫描多镜头剪辑素材**（抽帧确认齿孔/片框/场景切换），裁剪率 0.786 根因定位；按 §8.6 报告数据待讨论。确认人：AI 诊断（证据：.workbuddy/tmp/step*.png）。
