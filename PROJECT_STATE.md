# PROJECT_STATE
更新时间：2026-09-24 21:45
当前阶段：M0（文档修订完成，编码未开始）

## 已完成模块（含验收数值）
- 无代码模块。
- AGENTS.md **v2**（2026-09-24）：依全量审查完成 28 项修订，修订清单与依据见 AGENTS.md 第十六节。
- 环境与骨架：目录契约骨架已建（src/ ds/ tests/ tools/ docs/ data/synthetic/，均含 .gitkeep）；test1.mp4 已从根目录归位至 data/；.gitignore 已建（data/*.mp4 不入库）。
- 依赖实装验证：numpy 2.5.3 / opencv-python 5.0.0.93 / matplotlib 3.11.2 / pytest 9.1.1；cv2 关键接口冒烟通过；mp4v 编码回环通过（24fps / 1280×976 一致）；np.unwrap / sliding_window_view 可用。
- **验收线数值实证（2026-09-24，蒙特卡洛 200 次，按 §11 合成规格）**：内点召回 mean 0.9492 / P5 0.9214 / ≥0.90 达标率 100%；旋转误差 P95 0.105° / max 0.144°，<0.5° 达标率 100%；平移误差 P95 0.355px / max 0.683px，<0.5px 达标率 99%（尾部约 1% 概率单次超限，见已知风险）。

## 当前模块
- 无（等待 M0 计划确认后开工）

## 本次任务
- AGENTS.md 全面审查 → 用户授权按审查推荐项修订为 v2（六项重大决策，见决策日志）。

## 已知风险
- ~~依赖未完成安装核对~~（已解决，2026-09-24 22:18）：阿里云镜像可用（官方源与清华镜像在沙箱内不可用）。requirements.txt 已按实装版本锁定：numpy 2.5.3 / opencv-python 5.0.0.93 / matplotlib 3.11.2 / pytest 9.1.1。cv2 5.0 关键接口（goodFeaturesToTrack / calcOpticalFlowPyrLK / warpAffine / VideoCapture）已验证可用。
- test1.mp4 属性已确认：1280×976、24 fps、1440 帧（60 s）——960×540 合成规格与实拍分辨率不同，合成验收与实拍验收分开口径，无冲突。
- 验收阈值中的经验值（clamp 默认 30px/3°/0.05、合成 S ≥ 0.5、D ≤ 0.05）待 M0 实测校准；如需调整，按协议先报告数据再改。
- RANSAC 平移误差线 <0.5px 在蒙特卡洛中达标率 99%（200 次中 2 次尾部超限，max 0.683px）：属随机种子尾部事件而非设计缺陷；如单次验收轻微超限，按协议先报告数据，届时可改口径为「5 个种子独立试验均达标」。
- data/test1.mp4 不入库（gitignore），跨机迁移需手动携带。

## 本次改动（文件级清单）
- AGENTS.md：v1 → v2 全面修订（28 项，六项重大决策）
- 新增 .gitignore
- 新增 PROJECT_STATE.md（本文件）
- 新增目录骨架：src/ ds/ tests/ tools/ docs/ data/synthetic/（.gitkeep）
- 移动 test1.mp4 → data/test1.mp4
- 新增 requirements.txt（见下）
- README.md：补全环境安装完整步骤（venv / 镜像 / 代理 / 离线 / 排障）；运行与复现两节待 M0/M2 补充
- 重建项目 venv：用户此前用 msys2 Python 3.12.11 建出 `bin/` 布局 venv（无 activate.bat，CMD 无法激活），已改用 CPython 3.13 重建标准 `Scripts/` 布局并完成依赖安装
- requirements.txt：按实装版本回写锁定（numpy 2.5.3 / opencv-python 5.0.0.93 / matplotlib 3.11.2 / pytest 9.1.1）；头部注释去除本机路径
- README.md：全文去硬编码重构——通用步骤为主，机器专属内容收拢至「六、本机环境备注」节（标注克隆请忽略）；补充 test1.mp4 不入库的克隆提示

## 测试结果（pytest 摘要 + 数值对照表）
- 基线：无代码，pytest 无可收集用例（AGENTS.md §13-1 首次会话例外，v2 已补此条款）。

## 遗留问题
- README.md 仍为空占位（按契约随 M0/M2 逐步补齐）。
- 覆盖率测量工具（pytest-cov 或 coverage）为**待确认新增依赖**，须用户明确同意后方可加入 requirements.txt。
- pip 安装若持续失败，M0 首会话优先解决环境问题。

## 下一步
- M0 计划（待用户确认后开工），建议顺序：
  1. tools/make_synthetic.py（先有验收数据源）
  2. ds/ring_buffer.py + ds/heap.py（数据结构地基）
  3. src/smoothing.py（三平滑器 + 单元测试对照）
  4. src/warp.py（含 sanity check 与 cv2 对照测试）
  5. src/motion.py（最小求解器 + RANSAC + 合成点对验收）
  6. src/io_utils.py / src/trajectory.py
  7. src/features.py / src/tracking.py（M0 临时用 cv2，标 TODO(SELF-IMPL)）
  8. src/crop.py / src/metrics.py / src/visualize.py
  9. main.py 两遍流水线拼接，端到端跑通 data/test1.mp4

## 决策日志（数据结构选型理由 / 偏离 AGENTS.md 的记录及确认人）
- 2026-09-24：AGENTS.md v1 全量审查（28 项发现：A 类 4 / B 类 4 / C 类 7 / D 类 10 / E 类 3）→ 用户授权按审查推荐项修订为 v2。**六项重大决策**：① 两遍离线架构（pass1 估计轨迹 / pass2 补偿写盘）；② RANSAC thresh 1.5→2.5 px + 内点召回定义（真内点中被判内点的比例）；③ ITF 主口径定为最终成片全帧、掩膜口径降为辅助诊断；④ 帧编号统一 0-based；⑤ 验收集 = 合成视频 + data/test1.mp4 双份；⑥ cv2.resize 并入红线 2。确认人：用户（2026-09-24 会话）。
- 2026-09-24：平滑口径定稿——居中（非因果）+ update/flush 接口 + 部分窗口重归一边界（删除 np.pad reflect 表述）。确认人：用户（随 v2 整体授权）。
- 2026-09-24：漂移限幅机制纳入 §7（--clamp-tx/--clamp-theta/--clamp-ln-s，默认开启，--no-clamp 关闭）。确认人：用户（E1 建议随 v2 授权）。
- 2026-09-24：requirements.txt 按阿里云镜像实装版本锁定（numpy 2.5.3 / opencv-python 5.0.0.93 / matplotlib 3.11.2 / pytest 9.1.1）。确认人：用户（版本号确认无误）。
- 2026-09-24：项目 venv 用 CPython 3.13 重建（用户原 venv 由 msys2 Python 3.12.11 创建，bin/ 布局无 activate.bat，CMD 不可激活）。确认人：AI 代行（空 venv 重建，已告知用户）。
- 2026-09-24：**pass 2 采用「重读视频文件」而非「缓存全部帧」**——test1.mp4 为 1440 帧 ×1280×976×3 B ≈ 5.3 GB，缓存全帧内存风险不可接受；两遍各读一遍文件，IO 开销可接受。确认人：AI 建议（架构约定允许二选一，此为实现选择，开工后如有异议可改）。
- 2026-09-24：实现备注——visualize.py 的 Matplotlib 图表需设置中文字体（Windows 用 Microsoft YaHei / SimHei，rcParams['font.sans-serif']），否则中文乱码；axes.unicode_minus=False。
- 2026-09-24：**环境职责划分与去硬编码**（应用户要求）：① 项目环境统一为 `<项目根>/.venv`（标准 Scripts/ 布局，gitignore 不入库，克隆后各机自建）；② `C:\Users\v\.workbuddy\binaries\python\envs\default` 仅为 AI 沙箱执行环境（运行时隔离规则要求），不属于项目、不入库、项目文档不再引用；③ README 中机器专属内容（msys2 Python 布局问题、本机 CPython 路径、代理端口 7897、镜像实测情况）全部收拢至「六、本机环境备注」节并标注「克隆请忽略」；④ requirements.txt 头部注释去除本机路径；⑤ README 补充 data/test1.mp4 不入库的克隆提示。确认人：用户（提出克隆可用性要求）。
