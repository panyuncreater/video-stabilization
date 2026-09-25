# PROJECT_STATE
更新时间：2026-09-25（P4：金字塔 LK 落地，默认关闭，能力边界已实测）
当前阶段：**M2 验收达成（交付就绪）**；§11 全部 22 项基准通过；v2.5 已治愈感知回归（KNOWN_ISSUES #21）；**P1 骨架 / P2 提速 / P3 对比 runner / P4 金字塔 LK 均已落地**，其中 P2、P3、P4 的端到端与实拍验证待用户在有 cv2 的机器上执行；剩余交付为课程报告成稿

## 已完成模块（含验收数值）
- ds/ring_buffer.py、ds/heap.py：手写环形缓冲 / 双堆；与 deque、heapq 随机操作对拍一致。
- src/warp.py：恒等逐像素一致；与 cv2.warpAffine（OpenCV 5 正向约定）对照排除 2 px 环带后 20 组随机变换 min PSNR = 82.34 dB（≥40 dB），环带差异占比中位 0.0000/最大 0.0005；越界逐点填 0；uint8 走 float32 + 网格缓存。
- src/smoothing.py：三平滑器（居中 + flush + 部分窗口重归一），与朴素实现逐值一致（1e-9）；双堆延迟删除正确。
- src/motion.py：自研 RANSAC（复数法最小解 + 退化检验 + Umeyama 重拟合）；§11 验收平移 <0.5 px / 旋转 <0.5° / 召回 ≥90%（200 次蒙特卡洛达标率 100%/100%/100%）。
- src/features.py（M1 自研 Harris；**v2.5 角点空间均匀化**）：§11 验收检出率 1.000、定位误差 0.000 px；Top-N 改为网格分桶（桶数 ≥ N、桶内取响应最大者），质量阈值 0.001（重检 0.0002），根治全局 Top-N 条带化导致的估计噪声注入（KNOWN_ISSUES #21）。
- src/tracking.py（M1 自研单层 LK）：§11 验收 EPE 0.0004–0.14 px、跟踪成功率 1.000、与 cv2 中位差异 0.0009 px；RESIDUAL_MAX 维持 0.05（0.075 实验证伪，见决策日志）。
- src/shots.py（v2.1 方案① + **v2.3 无状态探针** + **v2.5 探针线重标**）：镜头切分（MAD + 内点率/存活率/探针存活率三线，两路证据取或）；test1 切换 **4/4 检出 [508, 809, 880, 1263]**；v2.5 均匀化点集下探针崩溃线 0.45→**0.25**（切换帧 0.137–0.194 vs 常态 0.294–0.975）；单测 16 项。
- src/io_utils.py / trajectory.py（镜头重置）/ crop.py（解析法 + 复合重采样）/ metrics.py（S 逐镜头聚合）/ visualize.py（切换标注 + 中文字体）。
- tools/make_synthetic.py（§11 规格 + 真值 JSON）、tools/bench_ds.py（§10 计时基准）。
- tools/verify_env.py（P1 新增：环境/数据/红线/测试/覆盖率自检，退出码 0/1/2）、tools/verify_invariance.py（P1 新增：改前改后 metrics 逐字段 + 成片逐帧 PSNR 等价性判定）、tools/transfer_check.ps1（P1 新增：一键迁移核查 + 报告落盘）。
- HANDOVER.md（P1 新增：交接总入口——环境先决条件 / 验收档位 A/B/C / 核心命令 / 迁移规则 / 已知缺口）、CHANGELOG.md（P1 新增：文件级变更记录 + 验证证据）。
- main.py：两遍离线流水线 + CLI + §12 降级规则与退出码 0–4；MAD 候选帧探针接入。
- 文档体系（v2.2）+ v2.3 修订：AGENTS.md §12/§16、docs/ 全量同步（README、ARCHITECTURE、API、TESTS、KNOWN_ISSUES、RESULTS）。

## 端到端指标（最新，v2.5 角点空间均匀化回归）
| 指标 | 合成视频 | test1.mp4 | 验收线 |
|---|---|---|---|
| ITF | 24.503 → 27.601（+3.098） | 30.163 → 31.352（+1.189） | 高于原视频 ✅ |
| 稳定度 S | 0.8090 | 0.9967（5 镜头加权） | 合成 ≥0.5 / 实拍 >0 ✅ |
| 裁剪率 | 0.9629 | 0.9685 | ≥0.85 ✅ |
| 失真值 D | 0.00677 | 0.00187 | 合成 ≤0.05 ✅ |
| 限幅触发 | 0 | 0 | — |
| 降级 | 0 | 重检测 47 次（§12 存活 <30 规则；均匀化点集弱角点更多，非缺陷） | — |
| 切换检出 | 0（单镜头，探针零误触发） | [508, 809, 880, 1263]（4/4） | — |
| 耗时 | pass1 14.0 s / pass2 36.5 s | pass1 98 s / pass2 1055 s（重检测增至 47 次所致） | — |

> 对比 v2.3：test1 ITF 增益 +0.687→+1.189（逼近 M0 的 +1.299）；裁剪率 0.9718→0.9685；S 0.9996→0.9967。决定性外测（`output/_residual_measure.py`，同法重跟踪 + 切换帧掩膜）：切断帧掩膜后垂直方向二阶差分 RMS 原 2.651 → v2.4 2.870（**更抖 +8.3%**）→ v2.5 1.467（**−44.7%**），坐实用户感知并验证修复。

## 当前模块
- P4（A. 金字塔 LK）已实现并完成本沙箱可做的全部验证（10 项行为测试 + 能力边界标定）；**默认关闭**，故既有指标与探针标定不变。三阶段的端到端/实拍验证均待用户执行。无进行中代码模块。

## 本次任务
**P2 干净计时（2026-09-25，顺序执行无争用，seed=42，test1 1440 帧 1280x976）**

| 口径 | pass1 | pass2 | 合计 |
|---|---|---|---|
| 默认（诊断开） | 83.1 s | **560.1 s** | 643.2 s |
| `--no-diagnostic` | 83.5 s | **271.7 s** | 355.2 s |
| 提升 | — | **−51.5%**（省 288.4 s） | **端到端 −44.8%** |

- 同时复验等价性：**1440/1440 帧逐像素完全相同**、指标逐字段一致（PASS）。
- pass1 两次 83.1 / 83.5 s（差 0.5%，噪声）——诊断只作用于 pass2，符合预期。
- 合成档（960x540，200 帧）早前测得 pass2 31.86→14.91 s（−53%），与实拍档 −51.5% 互相印证。
- 注：此前的 646→370 s（−42.7%）是并行运行受争用污染的数据，已由本表取代。

**根因定位与修复（2026-09-25，用户要求「直接定位根因」）**

- **根因（代码级、已复现）**：`src/motion.py::estimate_similarity_ransac` 的 `rng` 参数默认为 `None`，
  此时**每次调用都新建 `np.random.default_rng()`（无种子）** → 每次采样不同 → 内点集不同 →
  **`M_t` 每次运行都不同**。`main.py` 与 `src/shots.py` 的调用点**都没有传 `rng`**，
  而 `tests/test_motion.py` 传了 `default_rng(seed)`——**单测因此长期掩盖了该缺陷**。
- **同进程内实证**：对同一对帧、同一点集连续调用 5 次，`M[0,2]` 得到 0.4989 / 0.5169 / 0.5324 /
  0.5390 / 0.5210（各不相同）；而 `cvtColor` / `detect_corners` / `track_points` 5 次均完全一致
  → 不确定性**唯一来源就是 RANSAC 随机采样**。
- **为何合成档「看起来」确定**：合成视频纹理干净、外点极少，RANSAC 首轮即收敛且内点率稳定，
  采样差异不改变最终重拟合结果；test1 为胶片扫描（颗粒/暗部/齿孔），外点多且内点率波动，
  采样差异直接改变内点集 → 轨迹分岔 → 成片完全不同。
- **修复**：`main.py` 新增 `--seed`（默认 **42**），`run()` 内建**单一带种子 RNG 贯穿全链路**
  （pass1 的 RANSAC + 镜头探针共用）；`src/shots.py::probe_cut_evidence` 增加可选 `rng` 透传；
  `metrics.json` 记录 `seed` 便于复现判定。未传 `seed` 的既有调用行为不变（默认参数）。
- **修复验证（决定性）**：200 帧短片，**同种子 42 跑两次 → 200/200 帧逐像素相同、指标逐字段一致（PASS）**；
  **换种子 42→43 → 34 处指标差异、0/200 帧相同（min PSNR 24.4 dB）**——既证明可复现已达成，
  也证明 `--seed` 确实在控制随机性。全量 `pytest` **74 passed**（测试桩件已同步 `seed`/`rng` 签名）。
- **重要推论**：test1 的估计对 RANSAC 采样**极度敏感**（换种子即成片全变）。这说明**此前所有 test1
  的「逐帧等价」判定都不可信**，P2 的实拍档等价性**必须在固定种子下重跑**才能定论。

**实拍档验证（2026-09-25 用户提供 test1.mp4 后执行，环境打通）**

环境：pip 被沙箱临时目录限制阻断 → 改为**手动下载 6 个锁定 wheel + 解包**到 `.workbuddy/pylibs`
（sha256 全部校验 PASS，Anaconda 基础环境零污染）；`pytest` **74 passed**、覆盖率 **98%**。

结果：
- **P2 合成档 PASS**：成片 **200/200 帧逐像素相同**、指标逐字段一致、pass2 **31.86→14.91 s（−53%）**、
  诊断 warp 实测占两次重采样 **49.9%**（`tools/profile_pipeline.py`）。
- **P2 实拍档无法判定**：test1 上默认 vs `--no-diagnostic` 出现 87 处指标差异、0/1440 帧相同；
  决定性对照证明**这是 test1 自身的不可复现性**，与开关无关（见下）。
- **P3 合成档完成（9/9，0 失败）**：`median` 三窗口 **S < 0（−1.15 ~ −1.50）不达标**；
  `gauss` w61 S 最高 0.9673；`ma` w61 ITF 增益最高 +7.658 dB；已写入 `docs/RESULTS.md` §七。
- **P4 未获收益**：test1 上 `--pyramid` ITF 增益 **+1.172** vs 单层 **+1.186**，S 0.9963 vs 0.9969，
  重检测 47→63、pass1 82→168 s；三口径切换均 **4/4 检出** `[508,809,880,1263]`。
  → **结论：不启用为默认**（保持现状），代码与 10 项测试留作可选能力与报告素材。

**关键发现：test1 端到端结果不可复现（非 `--no-diagnostic` 引入）**

| 实验 | 条件 | 结果 |
|---|---|---|
| 合成档重复运行 | 同命令两次 | **200/200 帧逐像素相同**（确定性） |
| test1 重复运行 | 同命令两次（并行） | **0/1440 帧相同**，87 处指标差异 |
| test1 重复运行（**单线程 BLAS**） | `OMP/OPENBLAS/MKL/NUMEXPR_NUM_THREADS=1`，同命令两次 | **仍 0/1440 帧相同**，87 处差异 → **排除线程归约** |
| test1 前 200 帧短片 | 同命令两次 | **仍 0/200 帧相同**，33 处差异 → **排除长序列累计** |

→ 不确定性**只与 test1 素材内容相关**（胶片扫描的颗粒/暗部/齿孔结构使 LK 残差贴近 0.05 阈值，
边界点翻转后轨迹分岔）。**影响**：任何「改前/改后逐帧等价」判定在 test1 上方法不成立；
但 AGENTS §11 的**验收量本身稳定**（三次运行：切换均 4/4、裁剪率 0.962~0.967、S 0.996~0.997、ITF 增益 +1.17~+1.20 均达标）。
**待办**：定位不确定性来源（应先查 pass1 中 LK 阈值边界、`np.argpartition` 并列、RANSAC 随机种子与集合迭代序）
或在流水线内固定归约顺序；在此之前，实拍档的等价性判定改用「同参数重复运行的可复现性区间」作口径。

**P4（A. 金字塔 LK）—— 默认关闭，能力边界已实测**
- 目标：按 §8.2 补齐粗到细金字塔，缩小与 M0 的 ITF 差距（KNOWN_ISSUES #19：+1.189 vs +1.299）。
- 实现：src/tracking.py 新增 `_downsample2x`（2x2 均值池化）、`_lk_iterate` / `_lk_level`（与单层同一套正规方程，仅初值不同）、`track_points_pyramid`（levels=3）。**单层 `track_points` 一行未动**。
- 接入：main.py `--pyramid`（默认关）+ `PYRAMID_LEVELS=3`。**默认关闭是刻意选择**：保证既有标定、探针线（0.25）与全部指标逐位不变。
- 实测能力（合成平移真值，tests/test_tracking_pyramid.py 10 项）：单轴 ≤5 px 存活与正确率均 100%；单轴 6 px 单层崩溃（正确率 0.10）而金字塔 1.00；**双轴同时 ≥5 px（(5,5)/(6,3)）金字塔仍失败**——记为能力边界（KNOWN_ISSUES #23）并固定为回归测试。
- **未执行**：test1 上 `--pyramid` 的 ITF 增益（需 cv2 + 素材）；**启用前必须重标探针崩溃线**（探针内部仍用单层 LK）。

**P3（B. 三平滑器 × 窗口 对比实验）—— runner 就位，待实测**
- 目标：为 §8.4「高斯 + 窗口 31」的选型提供**端到端实测依据**（报告「选型理由」核心素材）；零算法改动，只扫既有 `--smooth` / `--window`。
- 新增 `tools/profile_smoothers.py`：3 平滑器 × 3 窗口 × 2 数据集；每配置隔离输出 `output/sweep/<dataset>/<smoother>_<w>/`（避免 metrics/成片互相覆盖）；默认幂等（已有 metrics 跳过，`--force` 重跑）；单配置失败不中断并汇总；输出 `docs/smoother_sweep.json` + 对比表 + **规则化小结**（窗口趋势 / 达标配置 / S 与 ITF 最优配置）。
- 新增 `docs/RESULTS.md` §七：运行命令、基准参考行（gauss/w31 的 v2.5 实测值）、判定线（沿用 §11 不放松）、报告结论维度；**其余 8 格明确标注未实测，禁止填推测值**。
- **未执行**：9 配置（合成）+ 9 配置（test1）真实实验 —— 须有 cv2 与素材。运行：`python tools/profile_smoothers.py --no-diagnostic --md docs/RESULTS.md`。

**P2（C. pass2 提速）—— 本轮主任务，数学零改动**
- 目标：缩短 pass2（test1 v2.5 实测 ≈ 1055 s），为 P3 的多遍 test1 回归降低成本。
- **设计决策**：工程原记候选是「合并诊断 warp 与写出」，经核对不可行——成片走 `crop.warp_crop_resize`（补偿+裁剪+缩放复合单次重采样，逆映射 B^{-1}@A），诊断走未裁剪 `warp_frame`，两者采样点/插值/有效域不同，合并必改成片像素，与「零数学改动」冲突。故改为**跳过**：新增 `main.py --no-diagnostic`，关掉纯诊断的中间 warp 与掩膜 ITF（§9 辅助口径，不参与任何验收判据）。
- **默认口径完全不变**（不传开关 = 与 v2.5 代码路径逐位一致），另新增 `metrics.json.diagnostic.masked_itf` 标记本次是否计算了诊断。
- 新增 `tests/test_invariance.py`（4 项编排级等价性，无 cv2 可跑）：关闭诊断后 `warp_frame` 调用 5→0、成片路径逐帧入参一致、写出帧一致、默认仍保留诊断。
- 新增 `tools/profile_pipeline.py`：实测诊断 warp 占两次重采样比例（冒烟 320×180 为 58.9%）。
- **未执行（须有 cv2 的机器）**：全量 64 项 pytest、端到端双档回归、成片逐帧 PSNR 等价性、test1 pass2 提速实测。按 `.workbuddy/baseline-local/README.md` 五步执行。

**P1（迁移与验证骨架）—— 上一步，已完成待验收**
- 新增 `HANDOVER.md`（交接总入口）、`CHANGELOG.md`（文件级变更记录 + 验证证据）、三个核查工具（`verify_env.py` / `verify_invariance.py` / `transfer_check.ps1`）；文档同步 AGENTS §17、README、docs/README、docs/DEVELOPMENT。
- 本沙箱只能执行部分验证（缺 cv2 + pip 被沙箱阻断），详见「测试结果」。
## 已知风险
- **P4 金字塔 LK 的收益未在真实素材上验证**，且其**双轴同时位移**能力有限（KNOWN_ISSUES #23）：单轴 6 px 可解、双轴 ≥5 px 不可解。故 `--pyramid` 保持默认关闭；若最终决定启用，**必须重标探针崩溃线并重跑双份回归**（探针内部仍用单层 LK 标定）。
- **P3 的实验结果尚未产生**：runner 与判定线就位，但 9+9 配置的真实数值须在装有 cv2 的机器上跑出（合成档 ≈8 min；test1 档 ≈2.9 h）。在结果落 `docs/RESULTS.md` 前，报告不得引用任何非实测的平滑器/窗口对比数值。
-
- **本沙箱无法执行端到端与全量测试**（缺 cv2；pip 因受限沙箱不能创建可写临时目录，属环境而非工程问题）→ P1 的等价性/指标类结论**尚未在本机验证**，须由用户在装有锁定依赖的机器上按 `HANDOVER.md` §四 执行后确认。
- 探针崩溃线（v2.5 重标为 0.25）与 LK 残差阈值（RESIDUAL_MAX 0.05）存在**参数交互**（放宽残差会使切换帧探针存活 0.146→0.402，判别间隔收窄）——后续若重调 LK 阈值必须重标探针线（shots.py docstring 已注明）。P4 金字塔 LK 亦受此约束。
- v2.5 均匀化使点集含更多弱角点，§12「存活 <30 重检测」触发次数由 2 升至 47，pass2 耗时 634→1055 s（指标不受影响，是 P2 优化要处理的对象）。
- 水平方向残余运动（KNOWN_ISSUES #22）：重跟踪 dx 二阶差分 RMS 原 1.154 → v2.5 1.583（v2.4 为 2.162），略高于原视频——属估计噪声底，绝对量级小，非缺陷，报告如实说明。
- Python 常数因子使 RingBuffer / 双堆在小 k 慢于 C 实现对照——非缺陷，报告须如实呈现（见 data_structures.md）。
- M0 与 v2.5 的 ITF 差距（+1.299 vs +1.189）仍有残余，归因金字塔 LK，留作课程加分项（P4），报告局限性章节如实说明。

## 本次改动（文件级清单）

**本会话（P4：A. 金字塔 LK，零默认行为改动）**——详见 CHANGELOG.md [P4]：
- src/tracking.py（改）：新增 `_downsample2x` / `_lk_iterate` / `_lk_level` / `track_points_pyramid` + `PYRAMID_MAX_LEVELS`；模块 docstring 补金字塔说明与**探针参数交互**警告。单层实现未动。
- main.py（改）：`--pyramid`（默认关）+ `PYRAMID_LEVELS=3`；跟踪调用点按开关分派；docstring 补跟踪器选择说明。
- tests/test_tracking_pyramid.py（新增）：10 项行为测试，含双轴局限的回归保护测试。
- docs/KNOWN_ISSUES.md（改）：新增 #23（双轴能力边界 + 根因 + 报告须如实说明 + 探针重标要求）。
- docs/API.md（改）：CLI 增 `--pyramid`；tracking 接口表补金字塔接口与降采样函数。
- PROJECT_STATE.md（改）：本记录。

**本会话（P3：B. 三平滑器对比，零算法改动）**——详见 CHANGELOG.md [P3]：
- tools/profile_smoothers.py（新增）：实验 runner（3 平滑器 × 3 窗口 × 2 数据集；隔离输出、幂等、失败不中断、规则化小结）。
- docs/RESULTS.md（改）：新增 §七「三平滑器 × 窗口 端到端对比」——运行命令 + 基准参考行 + 判定线 + 报告维度；其余 8 格标注未实测。
- HANDOVER.md（改）：五阶段表 P3 行、命令节补平滑器扫描。
- docs/API.md（改）：辅助工具列表补 verify_env / verify_invariance / transfer_check / profile_pipeline / profile_smoothers 五项。
- PROJECT_STATE.md（改）：本记录。

**本会话（P2：C. pass2 提速，数学零改动）**——详见 CHANGELOG.md [P2]：
- main.py（改）：新增 `--no-diagnostic`（跳过诊断 warp + 掩膜 PSNR）；pass 2 加 `if diag:` 分支；metrics.json 新增 `diagnostic.masked_itf`；docstring 补诊断口径。**默认行为逐位不变**。
- tests/test_invariance.py（新增）：编排级等价性测试 4 项（关闭诊断后 `warp_frame` 5→0、成片路径逐帧入参一致、写出帧一致、默认保留诊断），含 cv2 桩件，无 cv2 亦可运行。
- tools/profile_pipeline.py（新增）：pass 2 代价剖析（诊断 warp 占比），预热 3/取 5 中位/固定种子，输出 JSON 并可追加 markdown 表。
- tools/verify_invariance.py（改）：识别诊断开关变化，把 `diagnostic` 与 `metrics.itf_warped_masked_db` 排除比较并**显式打印**；忽略集改为任意层级生效。
- docs/KNOWN_ISSUES.md（改）：#17 更新为「P2 已落地 + 不采用合并的数学理由 + 实测占比口径」。
- docs/API.md（改）：CLI 增 `--no-diagnostic`；辅助工具补 3 项；metrics.json 增 `diagnostic` 块。
- README.md（改）：运行方式补 `--no-diagnostic` 说明。
- PROJECT_STATE.md（改）：本记录。
- 本地基线（.workbuddy/baseline-local/，不入库）：`PROJECT_STATE_v2.5_before_P2.md`（优化前备份）、`README.md`（P2 验收 5 步流程）、`p2_base_metrics_example.json`。

**本会话（P1 迁移与验证骨架，零算法改动）**——详见 CHANGELOG.md [P1]：
- HANDOVER.md（新增）：交接总入口。
- CHANGELOG.md（新增）：文件级变更记录 + 验证证据。
- tools/verify_env.py（新增）：环境/数据/红线/测试/覆盖率自检；退出码 0 就绪 / 1 阻断 / 2 缺实拍素材。
- tools/verify_invariance.py（新增）：metrics.json 逐字段 deep-diff（忽略 runtime_sec，配置类字段严格相等）+ 成片逐帧 PSNR。
- tools/transfer_check.ps1（新增）：一键核查 + 报告落盘（`.workbuddy/baseline-local/reports/<时间戳>/`）。
- AGENTS.md（改）：§17 文档体系登记 HANDOVER / CHANGELOG 与三个核查工具。
- README.md（改）：文档中心新增 HANDOVER / CHANGELOG 行；复现小节新增核查命令。
- docs/README.md（改）：阅读顺序插入 HANDOVER(0) 与 CHANGELOG(8)；契约表补两行。
- docs/DEVELOPMENT.md（改）：新增「五、迁移与核查」并把原五~九节顺延为六~十；常用命令表加三行（自检/等价性/一键核查）；红线自检改用 verify_env.py；会话协议第 1 条补 HANDOVER。
- PROJECT_STATE.md（改）：本记录。


**本会话（v2.5 角点空间均匀化，根治感知回归）**：
- src/features.py：`detect_corners` 的 Top-N 选取由全局 argpartition 改为**近方形网格分桶**（桶数 ≥ max_corners，桶内取响应最大者，桶内排序 O(M log M)）；`DEFAULT_QUALITY` 0.01→0.001、`RETRY_QUALITY` 0.005→0.0002；模块/函数 docstring 补 v2.5 根因说明。
- src/shots.py：`PROBE_SURVIVAL_THRESHOLD` 0.45→0.25（按均匀化点集分布重标）；docstring 更新标定数据（切换帧 0.137–0.194 vs 常态 0.294–0.975）。
- tests/test_features.py：新增空间均匀性单测（候选远超 max_corners 时下带仍分到可观份额），9→10 项。
- tests/test_shots.py：探针阈值相关断言同步至 0.25。
- AGENTS.md：§16 增 v2.5 修订记录（根因、修复、重标、决定性验证数据，确认人：用户选定方案 2）。
- docs/KNOWN_ISSUES.md：新增 #21（已解决：帧间估计误差注入 / 角点空间均匀化）、#22（非缺陷：水平方向残余运动）；#11 注记同步探针线重标。
- docs/API.md、ARCHITECTURE.md、TESTS.md、RESULTS.md、README.md：同步 v2.5（features 常量、探针线 0.25、60 passed、覆盖率明细、test1 指标列、结论）。
- PROJECT_STATE.md：本会话记录。

**上次会话（M2 验收收口）**：
- tests/test_warp.py：`test_compare_cv2_random_similarity_psnr` 补 §11 要求的「边界环带差异像素占比」报告输出（20 组变换环带内 mine≠ref 占比，中位/最大打印；不断言、不设线）。
- docs/RESULTS.md：新增「五、§11 验收对照表（M2 收口）」22 项全绿；单元测试验收表 warp 行修正为实测 82.34 dB + 环带占比；结论补 M2 达成判定。
- docs/TESTS.md：test_warp 说明同步实测值与环带报告项。
- PROJECT_STATE.md / README.md / docs/README.md：阶段推进至 M2 达成。
- AGENTS.md：§16 增 v2.4 修订记录（M2 验收收口）。

**前次会话（文档全面审查，纯文档/注释，无算法与接口变更）**：
- docs/ARCHITECTURE.md：模块依赖表 `shots.py` 补探针依赖（features/tracking/motion，无循环依赖）；mermaid 架构图 B4 节点标注「MAD>25 候选帧触发无状态探针取证」。
- docs/DEVELOPMENT.md：依赖表补 pytest-cov 7.1.0 / coverage 7.16.1；常用命令 54→59 passed，新增覆盖率测量命令行。
- README.md：KNOWN_ISSUES 描述与结尾改为「当前无待决项」；第 5 步安装验证含 pytest_cov、第 6 步 pip freeze 正则补 pytest-cov/coverage；「三、运行方式（M0 已可用）」→「（M1 + v2.3 已可用）」；结果复现表 test1 列由「见 RESULTS」改为实测值（+0.69 / 0.9996 / 0.972 / 0.00193）并新增切换检出行（4/4）。
- docs/API.md：metrics.json 示例整体更新为 v2.3 实测输出（5 镜头 / 4 切换 / itf 30.850 / crop 0.9718 / S_whole_sequence 0.282 / redetection 2 / runtime 102.5+633.5），补双口径与合成单镜头说明；实现状态行 M1→M1+v2.3。
- docs/README.md：KNOWN_ISSUES 阅读项「当前无待决项」；「关键约定速查」新增探针崩溃线 × LK 残差阈值参数交互警示（重调须重标 + 重跑双份回归）。
- main.py：模块 docstring 补镜头切换探针机制说明（纯注释，无代码逻辑改动）。
- PROJECT_STATE.md：本会话记录。

**上一会话（v2.3 遗留收口）**：
- src/shots.py：新增 `probe_cut_evidence`；`is_cut` 增加可选探针证据参数（两路取或）；`PROBE_SURVIVAL_THRESHOLD=0.45`；模块 docstring 补根因与标定数据。
- src/tracking.py：RESIDUAL_MAX 0.05→0.075→0.05（实验过程与证伪数据记入注释）。
- main.py：pass 1 在 MAD>25 候选帧调用探针取证并传入 is_cut；切换日志增探针存活率。
- tests/test_shots.py：新增探针测试 5 项（切换崩溃 / 常态存活 / 无角点 None / 退化点集救援回归 / 甩镜不误触发），11→16 项。
- requirements.txt：新增 pytest-cov==7.1.0、coverage==7.16.1（用户批准）。
- AGENTS.md：§12 补无状态探针机制；§16 增 v2.3 修订记录。
- docs/API.md、ARCHITECTURE.md、TESTS.md、KNOWN_ISSUES.md、RESULTS.md、docs/README.md、README.md：同步至 v2.3。
- 中间实验产物已清理（output/*/stabilized_lk075.mp4、基线备份 json）。

## 测试结果（pytest 摘要 + 数值对照表）
- 本会话（P4）验证（本沙箱可执行部分）：tests/test_tracking_pyramid.py **10 passed**（2x2 均值池化语义；单轴 ≤5 px 存活/正确率 100%；单轴 6 px 严格优于单层；双轴 ≥5 px 局限固定；(4,3) 满分；小图自动降层；空点集；自跟踪）；沙箱可跑全量 **47 passed**；main.py / src/tracking.py py_compile 通过；红线自检 20 个主实现文件无违规。
- 本会话 **未执行**：test1 上 `--pyramid` 端到端 ITF 对比（需 cv2 + 素材）、探针线重标（启用 `--pyramid` 的前置条件）。
- 本会话（P3）验证（本沙箱可执行部分）：`profile_smoothers.py` py_compile 通过；汇总/表格/小结函数用 9 组假数据验证正确（输出 9 行表 + 每平滑器窗口趋势 + S/ITF 最优配置）；素材缺失守卫正确报错 exit 1；子进程失败路径正确记录 returncode 与 stderr 尾部且不中断（exit 1）。**9+9 配置真实实验未执行**（需 cv2 + 素材）。

- 本会话（P2）验证（本沙箱可执行部分）：新增 tests/test_invariance.py **4 passed**（关闭诊断 warp_frame 调用 5 变 0、成片路径入参逐帧一致、写出帧一致、默认保留诊断）；verify_invariance.py 场景矩阵 A/B/C/P2 = exit **0/1/1/0** 全部符合预期（P2 场景：仅诊断按设计缺失，判 PASS 并显式打印）；profile_pipeline.py 冒烟 320x180x6 帧 → 诊断 warp 8.78 ms/帧、占两次重采样 **58.9%**；main.py py_compile 通过。
- 本会话 **未执行**：全量 64 项 pytest、端到端双档回归、成片逐帧 PSNR 等价性、test1 pass2 提速实测 —— 须在有 cv2 的机器按 .workbuddy/baseline-local/README.md 执行。**不得据此宣称提速或等价已达验收线**。
- 本会话（P1）验证：**本沙箱只能执行部分验证** —— (1) `tools/verify_env.py` 阻断路径正确（缺 6 项依赖 → exit 1，且明确提示勿继续）；(2) 红线静态自检扫描 **18 个主实现文件无违规**；(3) `tools/verify_invariance.py` 三条判定路径全部正确（仅计时差异→PASS；指标漂移 1e-3→FAIL；配置不可比→FAIL）；(4) `tools/transfer_check.ps1` 依赖守卫正确（缺依赖 exit 1 且不进入 end-to-end，报告落盘）；(5) pytest 可收集部分 **33 passed**（shots/tracking/warp 因模块级 `import cv2` 无法收集）。
- 本会话 **未执行**：全量 60 项 pytest、覆盖率复测、合成/实拍端到端回归、等价性成片 PSNR 比较 —— 均需有 cv2 的机器，按 HANDOVER.md §四 执行。**不得据此宣称指标仍达标**。

- 本会话（v2.5）验证：pytest **60 passed**（features 9→10 项）；覆盖率总体 **98%**（heap/tracking 100%、smoothing/warp 98%、features 97%、motion/ring_buffer 95%）；合成回归不退化（ITF +3.098 持平、S 0.8090、crop 0.9629、D 0.00677、切换 0）；test1 回归 ITF +1.189 / crop 0.9685 / S 0.9967 / D 0.00187 / 切换 4/4 / 重检测 47；决定性外测（`output/_residual_measure.py`）dy d2_rms 原 2.651 → v2.4 2.870（更抖 +8.3%）→ v2.5 1.467（−44.7%）；§11 全部 22 项仍通过。
- 上次会话（M2 收口）验证：pytest **59 passed**；§11 对照表 22 项全绿（docs/RESULTS.md 第五节）；warp 环带差异占比实测中位 0.0000 / 最大 0.0005（20 组变换）；输出一致性双份 PASS（合成 960×540@30×200、test1 1280×976@24×1440，输入=输出=metrics 记录）；pip freeze 与 requirements.txt 六项完全一致。
- 前次会话（文档审查）验证：红线自检 grep（src/、ds/ 禁用 API / deque / heapq / TODO）命中全部为注释性说明文字，无实际调用；全库过期引用复扫归零。
- 历史存档（v2.3/M2 期数据，已被上方 v2.5 结果取代，仅供对照）：pytest 59 passed（features 9 项）；覆盖率 motion 97%、features 96%；探针旧点集标定（LK 0.05）切换帧 0.099/0.146/0.237/0.147 vs 常态 0.656–1.000；#19 LK 0.075 实验证伪回退 0.05（test1 ITF +0.614 vs 基线 +0.650）；v2.3 双份回归（合成 +3.098 / 0.8081 / 0.9629 / 0.00675 / 切换 0）。

## 遗留问题
- 无待决事项。报告素材提示：v2.5 的「用户主观感知发现问题 → 定位为估计误差注入 → 找到决定性量化指标（同法重跟踪 + 切换帧掩膜二阶差分）→ 坐实并修复」是极佳的报告案例，与 M2 报告素材（点集退化机制、两参数交互、0.075 证伪过程）一并写入。

## 下一步

| 阶段 | 内容 | 状态 |
|---|---|---|
| P1 | 迁移与验证骨架（HANDOVER / CHANGELOG / 核查工具） | ✅ 已完成（用户验收中） |
| P2 | **C. pass2 提速**：`--no-diagnostic` 跳过纯诊断重采样（数学零改动） | 🔶 **代码已落地，待用户验收**（见下） |
| P3 | **B. 三平滑器对比**：ma / median / gauss × `--window` {15,31,61} × {合成, test1} | 🔶 **runner/表格/判定线已就位，9+9 配置结果待实测** |
| P4 | **A. 金字塔 LK**（粗到细；2x2 均值池化降采样） | 🔶 **实现已落地（默认关闭），能力边界已实测；真实素材收益待验证** |
| P5 | 课程报告成稿（用户主导） | 待做 |

**P2 待用户验收（须在有 cv2、且 preferably 有 data/test1.mp4 的机器上）**：

1. `python -m pytest tests/ -q` → 期望 **64 passed**（原 60 + 新增 `tests/test_invariance.py` 4 项）；
2. 默认口径改动前后等价：按 `.workbuddy/baseline-local/README.md` 第 1–3 步跑双档并用 `tools/verify_invariance.py` 判定 → 期望 **PASS**（指标逐字段一致 + 成片逐帧 PSNR ≥ 50 dB）；
3. `python tools/profile_pipeline.py` → 得到诊断 warp 占两次重采样的**实测占比**（本沙箱 320×180 冒烟为 58.9%）；
4. `--no-diagnostic` 端到端提速：同素材同参数各跑一遍，比较 `metrics.json.runtime_sec.pass2` → 期望明显下降（诊断 warp + 掩膜 PSNR 全部省掉）；
5. 若第 2 步或第 4 步不达标，**先报告数据再讨论**，不得放松判定（§11/§13.5）。

**P3 待用户执行的实验（runner 已就位）**：

```powershell
python tools\profile_smoothers.py --no-diagnostic --md docs\RESULTS.md            # 合成档 9 配置 ≈8 min
python tools\profile_smoothers.py --stage test1 --no-diagnostic --md docs\RESULTS.md  # 实拍档 ≈2.9 h（需 test1.mp4）
```

判定线：合成 S ≥ 0.5 / 裁剪率 ≥ 0.85 / D ≤ 0.05；test1 S > 0 / 裁剪率 ≥ 0.85。
结果自动写入 `docs/smoother_sweep.json` 并把对比表追加进 `docs/RESULTS.md` §七；
小结会给出每个平滑器的窗口趋势与 S / ITF 最优配置——据此在报告里论证 §8.4 的选型。

**P4 待用户验证（需 cv2 + 素材；且启用前须重标探针崩溃线）**：

```powershell
# 1) 行为测试（无 cv2 也能跑）：期望 10 passed
python -m pytest tests/test_tracking_pyramid.py -q

# 2) 默认口径不受影响：不传 --pyramid 时指标应与 v2.5 完全一致（逐字段）
python main.py --input data/test1.mp4 --output output/test1/metrics_check/stabilized.mp4 --smooth gauss --window 31
python tools\verify_invariance.py --baseline .workbuddy/baseline-local/test1_baseline_metrics.json --candidate output/test1/metrics_check/metrics.json

# 3) 金字塔口径（本阶段目标：test1 ITF 增益应逼近 M0 的 +1.299，当前单层为 +1.189）
python main.py --input data/test1.mp4 --output output/test1_pyramid/stabilized.mp4 --smooth gauss --window 31 --pyramid

# 4) 若第 3 步收益成立且要启用为默认：必须先重标探针崩溃线（探针内部仍用单层 LK）
#    标定方法见 src/shots.py 模块 docstring；随后重跑双份回归与切换 4/4 检出
```

**判定**：第 2 步必须 PASS（证明默认行为零改动）；第 3 步报告 ITF 增益与切换检出，
**不预设必须达标**——若双轴局限（KNOWN_ISSUES #23）导致实拍收益不足，按「先报告数据再讨论」处理。

**课程报告成稿素材**：数据结构五要素与实测耗时（docs/data_structures.md）、选型理由与架构（ARCHITECTURE.md）、
实验数据（RESULTS.md + §11 验收对照表）、局限性讨论与已知问题（KNOWN_ISSUES，含 #17 的 P2 取舍）、
「先报告数据再决策」案例（点集退化根治、0.075 证伪实验、P2 的「合并 vs 跳过」数学论证）；P3 完成后再增补三平滑器对比。

## 决策日志（数据结构选型理由 / 偏离 AGENTS.md 的记录及确认人）
- 2026-09-24：AGENTS.md v1 全量审查（28 项发现）→ 用户授权按推荐项修订为 v2，六项重大决策（两遍架构 / thresh=2.5+召回定义 / ITF 成片主口径 / 0-based / 双验收集 / resize 入红线）。确认人：用户。
- 2026-09-24：平滑口径定稿（居中 + update/flush + 部分窗口重归一）。确认人：用户（随 v2 授权）。
- 2026-09-24：漂移限幅机制纳入 §7（默认开启）。确认人：用户（随 v2 授权）。
- 2026-09-24：requirements.txt 按阿里云镜像实装锁定（numpy 2.5.3 等四项）。确认人：用户（版本号确认无误）。
- 2026-09-24：项目 venv 用 CPython 3.13 重建（原 msys2 venv 布局异常）。确认人：AI 代行（已告知）。
- 2026-09-24：pass 2 重读文件而非缓存全帧（≈5.3 GB 内存风险）。确认人：AI 建议（可改）。
- 2026-09-24：Matplotlib 中文字体配置要求。实现备注。
- 2026-09-24：OpenCV 5.0.0 warpAffine 改为「输入→输出」正向约定（实测），§7 注释同步修正。确认人：AI 实测（事实修正）。
- 2026-09-24：环境职责划分与去硬编码（项目用 .venv；沙箱 envs/default 不入库不引用；README 机器内容收拢第六节）。确认人：用户。
- 2026-09-24/25：crop 有效域取「逐帧内接矩形再求交」保守口径；裁剪框向内取整；补偿 warp + 裁剪 + 缩放复合为单次重采样；resample 网格缓存 + float32。确认人：AI 实现选择（§8.6 允许课程级实现，注释已声明保守性）。
- 2026-09-25：test1.mp4 诊断为胶片扫描多镜头剪辑素材，裁剪率 0.786 根因定位。确认人：AI 诊断（证据 .workbuddy/tmp/step*.png）。
- 2026-09-25：**方案①镜头切分落地（v2.1）**：新增 src/shots.py，判据阈值由实测分布确定；轨迹逐镜头重置、平滑/锚定/限幅逐镜头独立、S 逐镜头加权聚合。效果：test1 裁剪率 0.786→0.8792，S 0.727→0.978，限幅 43→7，降级归零。确认人：用户（三确认）。
- 2026-09-25：**M1（v2.2）自研特征/光流落地**，cv2 临时实现与 TODO 全部移除；盒式滤波 k=5→3（响应峰定位修正）。确认人：AI 实现（含实测依据，已记 KNOWN_ISSUES #1）。
- 2026-09-25：**切换判据补丁**：MAD>25 且（内点率<0.30 或 存活率<0.25）。确认人：AI 实测修订（判据细化，不动验收线）。
- 2026-09-25：**文档体系建立（v2.2）**：8 份文档 + README/AGENTS 同步，确保新会话可零提问接手。确认人：用户（本次任务指令）。
- 2026-09-25：**v2.3 #11 无状态探针**（用户批准方案）：MAD>25 候选帧 `probe_cut_evidence` 新鲜全集取证，崩溃线 0.45（切换帧 0.099–0.237 vs 常态 0.656–1.000 取中点）；`is_cut` 两路证据取或；test1 切换 4/4 检出、ITF +0.687、裁剪率 0.9718。AGENTS §12/§16 同步。确认人：用户。
- 2026-09-25：**v2.3 #19 LK 残差实验**：0.05→0.075（用户批准实验）→ test1 ITF +0.614 vs 基线 +0.650 证伪 → **回退 0.05 + 差距文档化**（用户二次决策）；归因 M0 金字塔 LK，记 KNOWN_ISSUES #19 非缺陷。注意与探针线的参数交互。确认人：用户（两次）。
- 2026-09-25：**v2.3 #20 覆盖率工具**：新增 pytest-cov 7.1.0 + coverage 7.16.1 依赖（用户批准）；核心模块覆盖率 98%（≥80% 达标）。确认人：用户。
- 2026-09-25：**文档系统全面审查**（用户指令）：全量文档同步至 v2.3，修复 7 处过期内容（依赖表/指标示例/阶段标注等），新接手 AI 零提问可接手。确认人：用户（本次任务指令）。
- 2026-09-25：**M2 验收收口达成（v2.4）**：§11 全部 22 项基准通过（对照表固化于 docs/RESULTS.md 第五节）；补齐 warp 环带差异占比报告（中位 0.0000/最大 0.0005）与输出一致性双份核对（PASS）；修正 warp 对照历史记录（inf → 82.34 dB，旧值系早期纹理版本所测）。确认人：用户（「继续推进」指令授权 M2 收口）。
- 2026-09-25：**后续优化方向选定**：用户选定 A（金字塔 LK）+ B（三平滑器对比）+ C（pass2 提速）三项，明确**暂不执行**、写入下一步规划；建议执行序 C→B→A（提速先行缩短 B 的多遍回归周期）。git 已推送至 origin/main（6eab298 及规划更新）。确认人：用户。
- 2026-09-25：**v2.5 角点空间均匀化（用户感知回归根治）**：用户反馈「修复后视频比原视频抖动更明显」→ 根因定位为帧间估计误差注入（全局 Top-N 角点条带化 → RANSAC 逐帧平移误差经 B_t 进入输出，ITF/S 不敏感）；用户选定**方案 2：角点均匀化**。实现：`detect_corners` Top-N 改网格分桶 + 质量阈值 0.001；探针线 0.45→0.25 重标（两参数交互，若重调 LK 阈值须重标）。决定性验证：同法重跟踪 + 切换帧掩膜二阶差分 RMS，dy 原 2.651 → v2.4 2.870（更抖 +8.3%，坐实感知）→ v2.5 1.467（−44.7%）；test1 ITF +0.687→+1.189。确认人：用户（选定方案 2 并授权继续）。
- 2026-09-25：**P1 迁移与验证骨架**（用户指令「安排下一轮、分阶段执行、保留增改记录、保证跨 agent 迁移能力」）。决策：① 先做 C（P2）而非 B/A，因其数学零改动、可用等价性严格证明，且为 B 的多遍 test1 回归提速；② 迁移能力以「文档 + 一键核查脚本」落地，不引入 CI/新依赖；③ 核查工具一律**不修改数学口径**，只读不写工程数据。附带处置 5 个实测暴露的缺陷（PS 5.1 无 ArgumentList、stdout 重定向死锁、退出码语义、.ps1 需 BOM、JSON BOM 容忍）。确认人：用户（本轮任务指令；P1 验收待用户在有 cv2 的机器上执行）。
- 2026-09-25：**P2（C. pass2 提速）落地**。决策：① **不采用**工程原记的「合并诊断 warp 与写出」——经核对，成片用 `warp_crop_resize`（补偿+裁剪+缩放复合单次重采样，逆映射 B^{-1}@A），诊断用未裁剪 `warp_frame`，两者采样点/插值/有效域不同，合并必改成片像素，与「零数学改动」冲突；② 改为**跳过**：`--no-diagnostic` 关掉纯诊断的中间 warp 与掩膜 ITF（§9 辅助口径，不参与任何验收判据）；③ **默认口径不变**，保证改动前代码路径逐位不变，等价性可用 `verify_invariance.py` 严格判定；④ 新增编排级测试 `tests/test_invariance.py`（无 cv2 可跑，验证调用次序与数值传递），弥补本沙箱无法端到端验证的缺口。确认人：AI 依 AGENTS.md §13.4 记录设计偏离（原「合并」方案被数学理由否决）；验收待用户执行。
- 2026-09-25：**P3（B. 三平滑器对比）runner 落地**。决策：① 用独立 runner 而非手工重复跑 main.py——保证配置隔离（每配置独立输出目录）、幂等、失败不中断、结果可复算；② 只扫既有 `--smooth`/`--window`，**不动任何算法与口径**；③ 实验用 `--no-diagnostic`（P2 产出）缩短周期——诊断量与本实验结论无关；④ **不预填任何未实测数值**进 RESULTS.md，只给基准参考行（gauss/w31 的 v2.5 实测）与判定线，避免「推测值混入报告」。确认人：AI 依 §13.4（参数实验不改契约）；实验结果待用户执行后填入。

- 2026-09-25：**P4（A. 金字塔 LK）落地，默认关闭**。决策：① 采用「新增函数 + 开关」而非替换单层实现——探针（shots.py）内部用单层 track_points 且崩溃线 0.25 按单层分布标定，若把金字塔设为默认，必须同步重标探针线，成本与风险都高；故保持默认口径逐位不变，金字塔作为可选加分项（`--pyramid`）。② 降采样用 2x2 均值池化（§8.2 明文），并明确「尺度约简 ≠ 几何重采样」，不触红线 2。③ 实测发现**双轴同时 ≥5 px 位移仍失败**（粗层收敛到能量更强的单轴局部极小），经整数循环平移复测排除边界伪影后**确认为能力边界而非实现缺陷**，写入 KNOWN_ISSUES #23，并用回归测试固定该行为（若未来修复，测试会失败并提醒更新文档）。确认人：AI 依 §13.4 记录（新增可选功能 + 能力边界如实上报）；是否启用为默认待用户决策。
- 2026-09-25：**实拍档验证与不确定性发现**。① 环境改用「手动 wheel 解包」打通（pip 受限，非工程问题）；② P2 合成档严格的逐像素等价 + 53% 提速达标；③ P3 合成档完成，`median` S<0 为选型提供实测依据；④ P4 金字塔**未获收益**（ITF +1.172 vs +1.186）→ 建议不启用，保持默认关闭；⑤ **发现 test1 端到端结果不可复现**，经「合成档对照 + 单线程 BLAS + 200 帧短片」三重实验排除线程归约、长序列累计与 `--no-diagnostic` 三个假设，定位为**素材内容相关**（阈值边界翻转）。确认人：AI 执行 + 如实上报（未据此宣称任何验收结论）；下一步待用户决定是否投入定位根因。
- 2026-09-25：**RANSAC 可复现性缺陷定位并修复**（用户指令「直接定位根因」）。根因：`estimate_similarity_ransac` 在 `rng=None` 时每次新建无种子生成器，而 `main.py`/`shots.py` 均未传 rng（单测传了种子故未暴露）。修复：新增 `--seed`（默认 42），单一 RNG 贯穿 pass1 与镜头探针，metrics.json 记录 seed。验证：同种子两次 **200/200 帧逐位相同**；换种子 **0/200 帧相同**。**推论**：test1 对 RANSAC 采样极敏感，此前实拍档「逐帧等价」判定均不可信，P2 实拍档等价性须在固定种子下重跑。确认人：AI 定位并修复（属缺陷修复，不改数学口径；接口为新增可选 `--seed`，默认 42 保证后续可复现）。