# PROJECT_STATE
更新时间：2026-09-25 00:35
当前阶段：**M0 完成并达放行标准**（方案①镜头切分落地后，合成与实拍四项指标全部达标）

## 已完成模块（含验收数值）
- ds/ring_buffer.py、ds/heap.py：手写环形缓冲/双堆，随机操作对拍 deque/heapq 一致。
- src/warp.py：恒等逐像素一致；与 cv2.warpAffine（OpenCV 5 正向约定）对照 PSNR = inf；越界逐点填 0。
- tools/make_synthetic.py：合成数据 960×540×200 帧（种子 42）+ 真值 JSON，§11 幅度约束实测通过。
- src/smoothing.py：三平滑器（居中+flush+部分窗口重归一），与朴素实现逐值一致（1e-9）。
- src/motion.py：自研 RANSAC，§11 验收全过（平移 <0.5px、旋转 <0.5°、召回 ≥90%）。
- **src/shots.py（v2.1 方案①）**：镜头切分——MAD + 内点率双条件 + 最短镜头长度；逐镜头分段/平滑/锚定/限幅；S 逐镜头加权聚合。单测 10 项。
- src/io_utils.py / trajectory.py（镜头重置）/ crop.py / metrics.py（S 分段聚合）/ visualize.py（切换虚线标注）。
- src/features.py / tracking.py：**M0 临时 cv2 实现，标 TODO(SELF-IMPL)**（M1 替换）。
- main.py：两遍离线流水线 + 镜头切分 + §12 降级与退出码；tools/bench_ds.py §10 计时基准。
- **端到端指标（v2.1 后）**：
  - 合成视频（单镜头回归）：检出切换 0 处 ✓；ITF 24.50→27.60（+3.09）✓；S=0.815 ✓；裁剪率 0.963 ✓；D=0.0067 ✓。
  - test1.mp4（多镜头）：检出切换 3 处 [508, 880, 1263]；ITF +1.30 dB ✓；**S=0.978**（逐镜头聚合）✓；**裁剪率 0.8792 ≥0.85** ✓；D=0.0031；降级全零；限幅触发 7 处；耗时 pass1 33s / pass2 700s。

## 当前模块
- M0 放行评审；下一步 M1（自研 Harris + LK）。

## 本次任务
- 方案①镜头切分实现（用户确认：新增 src/shots.py、S 逐镜头加权聚合）+ 双份回归验证。

## 已知风险
- **切换检测存在假阴性**：帧 809 实测为真切换（MAD 36.6，抽帧确认桌边双人 → 西装男子）但内点率 ≥0.30 被双条件否决——该处跨切换污染残留于 809–880 段（71 帧，限幅兜住，裁剪率仍达标）。候选缓解：内点率阈值 0.30→0.5（有误判甩镜风险）。**待用户决定是否继续调优**；当前验收已全部达标。
- RANSAC 平移误差线 <0.5px 蒙特卡洛达标率 99%（尾部 ~1%），兜底条款已就位。
- bench 实测：RingBuffer / 双堆在 Python 层常数劣势（小 k 时慢于 list.pop(0)/sorted），渐进优势在 k≥127 才显现；argpartition 稳定 9-11x；MA 增量在 k≥31 后 1.7-2.9x。报告中须如实呈现「Python 常数因子 vs 渐进复杂度」分析。

## 本次改动（文件级清单）
- 新增 src/{warp,smoothing,motion,io_utils,trajectory,features,tracking,crop,metrics,visualize,shots}.py
- 新增 ds/{ring_buffer,heap}.py；新增 tests/{test_ds,test_warp,test_smoothing,test_motion,test_shots}.py
- 新增 tools/{make_synthetic,bench_ds}.py；新增 main.py
- 生成 data/synthetic/{synthetic_shaky.mp4(不入库),ground_truth.json}
- 生成 output/{synthetic,test1}/{stabilized.mp4(不入库),metrics.json(不入库)}
- 生成 docs/{trajectory,metrics_bar}_{synthetic_shaky,test1}.png、bench_ds.{json,png}
- AGENTS.md：§7 对照注释修正（OpenCV 5 正向约定）；v2.1 新增镜头切分（§6 目录 / §9 稳定度分段聚合 / §12 切换规则 / §16 修订记录）
- trajectory.py 增 start_new_shot()；metrics.py 增逐镜头加权聚合；visualize.py 增切换虚线标注

## 测试结果（pytest 摘要 + 数值对照表）
- pytest **40 passed**（ds 8 / warp 7 / smoothing 9 / motion 6 / shots 10）。
- warp vs cv2：PSNR = inf（光滑纹理）；identity 逐像素一致；(+5,0) 右移 5px 精确。
- 平滑器 vs 朴素：1e-9 容差全组合通过（含 window>N、偶数窗口、window=1）。
- RANSAC §11 验收 + 多种子稳健性全过；镜头切分：判据/分段/最短镜头长度 10 项单测全过。
- 端到端：合成（0 切换，指标不变）与 test1（3 切换，四项全达标）双份出片，指标见上。

## 遗留问题
- 切换检测假阴性（帧 809）是否继续调优，待用户决定（当前验收已达标）。
- 覆盖率工具（pytest-cov / coverage）为待确认新增依赖。
- README「运行方式」节待 M0 放行后补实际命令；「结果复现」待 M2。
- M1（自研 Harris + LK）未开始。

## 下一步
1. M0 放行确认 → M1：自研 Harris 角点（§8.1）替换 goodFeaturesToTrack，自研单层 LK（§8.2）替换 calcOpticalFlowPyrLK（放行门槛：单元测试达标 + 合成视频端到端 ITF/稳定度相对 M0 不退化 ≤2% + 全链路无 TODO）。
2. 假阴性（帧 809）调优与否由用户决定；若调优，改内点率阈值并重跑双份回归。
3. README「结果复现」节待 M2；覆盖率工具待确认依赖。

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
- 2026-09-25：**方案①镜头切分落地（v2.1）**：新增 src/shots.py；判据 MAD>25.0 且 内点率<0.30 且 最短镜头 12 帧（阈值由 test1 实测分布确定：切换帧 MAD 34–42 vs 常态 P99 13.2，有 2.5 倍空档）；轨迹逐镜头重置、平滑/锚定/限幅逐镜头独立、S 逐镜头加权聚合；trajectory.py 增 start_new_shot()；visualize.py 增切换虚线标注。AGENTS.md v2.1 同步（§6/§9/§12/§16）。效果：test1 裁剪率 0.786→**0.8792（达标）**，S 0.727→0.978，限幅 43→7，降级归零；合成回归 0 切换、指标不变。确认人：用户（三确认：新增模块/S 口径/开工）。
