# 文档索引（新接手先读这里）

> 本目录是项目文档中心。**首次接手请按「阅读顺序」依次阅读**，无需额外询问即可开展后续开发。

## 项目一句话

对一段手持抖动视频（mp4）做电子稳像：估计帧间 **2D 相似变换**（平移 + 旋转 + 等比缩放，4 自由度），在参数空间平滑相机轨迹后做逆向映射补偿，输出稳定视频 + 量化指标（metrics.json）+ 可视化图表。核心算法全部自研，禁止调用 OpenCV 高层封装。

## 当前状态（2026-09-25）

| 项目 | 值 |
|---|---|
| 阶段 | **M2 验收达成（交付就绪）**——§11 全部 22 项基准通过（对照表见 RESULTS.md 第五节），剩余交付仅课程报告成稿；v2.5 已根治「修复后比原视频更抖」（KNOWN_ISSUES #21） |
| 下一步 | 课程报告成稿（素材已齐：data_structures / RESULTS / KNOWN_ISSUES / ARCHITECTURE）；已批准优化 C→B→A 暂不执行 |
| 测试 | pytest **60 passed**；核心模块覆盖率 **98%**（§11 验收线 ≥80%） |
| 代码规模 | src/ 11 模块、ds/ 2 模块、tools/ 2 工具、tests/ 7 文件 |
| 依赖 | numpy 2.5.3 / opencv-python 5.0.0 / matplotlib 3.11.2 / pytest 9.1.1 / pytest-cov 7.1.0（Python 3.13） |

## 阅读顺序

0. [../HANDOVER.md](../HANDOVER.md) —— **交接总入口**：环境先决条件、验收档位、核心命令、迁移规则（**新接手第一份**）
1. [ARCHITECTURE.md](ARCHITECTURE.md) —— 架构、数据流、数学约定、异常降级（**必读**）
2. [API.md](API.md) —— 各模块接口签名、CLI、metrics.json 结构、退出码
3. [data_structures.md](data_structures.md) —— 课程核心：数据结构选型、复杂度、实测耗时
4. [TESTS.md](TESTS.md) —— 测试清单与验收映射
5. [KNOWN_ISSUES.md](KNOWN_ISSUES.md) —— 已知问题、根因与解决方案（当前无待决项）
6. [RESULTS.md](RESULTS.md) —— 端到端指标、产物路径、复现步骤
7. [DEVELOPMENT.md](DEVELOPMENT.md) —— 环境搭建、命令、Git 与编码约定、红线自检、迁移核查
8. [../CHANGELOG.md](../CHANGELOG.md) —— 文件级变更记录（增/改/删 + 验证证据）

## 文档与契约的关系

| 文档 | 对应 AGENTS.md 章节 | 说明 |
|---|---|---|
| ARCHITECTURE.md | §6 / §7 / §8 | 架构约定与自研方案实现说明 |
| API.md | §6 接口契约 | 签名不得擅自修改（需用户确认） |
| data_structures.md | §10 | 数据结构得分点与报告素材 |
| TESTS.md | §11 | 测试与数值验收基准 |
| KNOWN_ISSUES.md | §12 / §8.6 | 异常降级与「先报告数据再讨论」条款 |
| RESULTS.md | §9 / §15 | 指标口径与交付物 |
| DEVELOPMENT.md | §3 / §13 | 技术栈与会话协议 |
| HANDOVER.md | §13 | 交接与迁移：环境先决条件、验收档位、核查工具 |
| CHANGELOG.md | §13.3 | 文件级变更记录与验证证据 |

## 关键约定速查（易错点）

- `warp_frame(img, M)` 的 **M 是「输入→输出」正向映射**，内部求逆采样；本环境 OpenCV 5 的 `cv2.warpAffine` 同样是正向约定，对照传 `M[:2]`。
- 平滑为**居中（非因果）**，`update()` 返回 $y_{t-r}$（前 r 次返回 None），尾部必须 `flush()`。
- 帧编号 **0-based**；$C_0 = I$；$B_0 = I$。
- 所有几何重采样（含裁剪后缩放）走自研 `warp.resample`，**禁 cv2.resize**。
- 切换判据的探针崩溃线（`shots.PROBE_SURVIVAL_THRESHOLD=0.25`）与 LK 残差阈值
  （`tracking.RESIDUAL_MAX=0.05`）存在**参数交互**：放宽残差会使切换帧探针存活率抬升
  （0.146→0.402 @帧809），重调任一参数须重标另一处并重跑双份回归。v2.5 角点空间均匀化后
  点集含更多弱角点、常态帧存活率整体下移，探针线已由 0.45 重标为 0.25（见 KNOWN_ISSUES #21）。
- 红线自检清单见 [DEVELOPMENT.md](DEVELOPMENT.md#红线自检清单)。
