# CHANGELOG —— 文件级变更记录（增 / 改 / 删）

> 目的：让**任何 agent 或人**在几秒内看清「每一轮改了什么文件、为什么改、怎么验证的」。
> 与 `PROJECT_STATE.md` 的分工：
> - 本文件 = **文件级清单 + 证据**（可追溯「哪一轮动了哪些文件」）；
> - `PROJECT_STATE.md` = **进度与决策**（已完成模块、实测数值、下一步、决策日志）。
>
> 约定（AGENTS.md §13）：每阶段独立 commit；只记实际发生的改动，**未执行的验证必须标注「未执行」**。

图例：`+` 新增文件 ｜ `~` 修改文件 ｜ `-` 删除文件

---

## [验收] 独立机器复跑 + 实拍素材入库 —— 2026-09-26

**目标**：在一台独立机器上复跑验收、把结果随仓库发布；并把实拍素材放回约定路径后正式入库。
**数学逻辑**：**零算法 / 零口径改动**——只新增报告、移动素材、同步文档表述。

### 新增
| 文件 | 说明 |
|---|---|
| `+ docs/TEST_RUN_2026-09-26.md` | 独立机器验收复跑报告：环境差异（numpy 2.2.6 / matplotlib 3.10.9 低于锁定）、可复现命令、双档实测数值、辅助工具、未执行项、遗留与提示 |
| `+ data/test1.mp4` | 实拍验收素材**正式入库**（11.3 MB，blob `e204829f`）。来源为远程网页上传的 `data/synthetic/test1.mp4`（内容完全相同，git 识别为重命名），错放副本已删除 |

### 修改
| 文件 | 说明 |
|---|---|
| `~ .gitignore` | `data/*.mp4` 之后新增 `!data/test1.mp4` 例外，并在注释说明入库决定 |
| `~ AGENTS.md` | §6 目录树 `data/` 行：「gitignore 不入库」→「2026-09-26 起入库」 |
| `~ README.md` | 「数据说明」：改为「已入库，克隆即可跑实拍档」 |
| `~ HANDOVER.md` | §2.2 不入库文件表 + §七 已知缺口行：test1.mp4 行改为「已入库 / 缺口关闭」 |
| `~ docs/RESULTS.md` | §一 素材表：test1.mp4 标注「已入库」 |
| `~ docs/DEVELOPMENT.md` | 目录树与「不入库」清单补例外说明 |
| `~ docs/KNOWN_ISSUES.md` | #18：区分「output/ 与合成视频仍不入库」与「实拍素材已入库」 |
| `~ PROJECT_STATE.md` | 本次机上复跑、报告发布与素材入库的记录 |

### 验证证据
| 验证项 | 结果 | 证据路径 |
|---|---|---|
| 全量测试 / 覆盖率 | **74 passed / 98%** | `docs/TEST_RUN_2026-09-26.md` §4.1 |
| 合成档四项指标 | ITF +3.098 dB / S 0.8091 / 裁剪率 0.9629 / D 0.00677 | `output/synthetic/metrics.json`（本地，不入库） |
| 实拍档四项指标 + 切换检出 | ITF +1.175 dB / S 0.9971 / 裁剪率 0.9690 / D 0.00187 / 切换 **4/4** `[508, 809, 880, 1263]` | `output/test1/metrics.json`（本地，不入库） |
| 素材入库完整性 | 与本地原文件字节一致（blob `e204829f582e4a754c1345f1ff6777fba7eedbc5`） | `git hash-object data/test1.mp4` |
| **未执行** | `--vis` 直写 `docs/`；`profile_smoothers.py` 实拍档 9 配置 | 见报告 §六 |

---

## [P4] A. 金字塔 LK（默认关闭，能力边界已实测并文档化） —— 2026-09-25

**目标**：按 §8.2 补齐粗到细金字塔 LK，缩小与 M0（`calcOpticalFlowPyrLK`）的 ITF 差距（KNOWN_ISSUES #19：+1.189 vs +1.299）。
**数学逻辑**：**扩展而非替换**——金字塔复用同一套 2x2 正规方程，只改变迭代初值（粗层估计 x2 上采样）。**默认关闭**，故既有标定、探针线与全部指标逐位不变。

### 新增
| 文件 | 说明 |
|---|---|
| `+ tests/test_tracking_pyramid.py` | 10 项行为测试（纯 numpy，无 cv2 可跑）：2x2 均值池化语义、§8.2 规格区间（<=5 px 单轴）满分级、单轴 6 px 严格优于单层、**双轴局限固定为回归保护**、(4,3) 双轴小位移满分、小图自动降层、空点集、自跟踪 |

### 修改
| 文件 | 说明 |
|---|---|
| `~ src/tracking.py` | 新增 `_downsample2x`（2x2 均值池化）、`_lk_iterate` / `_lk_level`（与单层同式，仅初值不同）、`track_points_pyramid`（`levels=3`，上限 `PYRAMID_MAX_LEVELS=4`，按尺寸自动降层）。**`track_points` 单层实现一行未动** |
| `~ main.py` | 新增 `--pyramid`（默认关）+ `PYRAMID_LEVELS=3`；pass 1 跟踪调用点按开关分派；docstring 记录参数交互 |
| `~ docs/KNOWN_ISSUES.md` | 新增 **#23**：双轴同时位移的能力边界（实测数据 + 根因 + 报告须如实说明 + 探针重标要求） |
| `~ docs/API.md` | CLI 增 `--pyramid`；tracking 接口表补 `track_points_pyramid` / `_downsample2x` |
| `~ PROJECT_STATE.md` | P4 状态与验收流程 |

### 验证证据
| 验证项 | 结果 | 证据路径 |
|---|---|---|
| 金字塔在 §8.2 规格区间（单轴 <=5 px） | **存活 100% + 正确率 100%** | `tests/test_tracking_pyramid.py`（10 passed） |
| 单轴 6 px（单层已崩溃） | 单层正确率 0.10（x）/ 0.85（y，纹理各向异性）；**金字塔均 1.00** | `.workbuddy/env-probe/diag_pyramid7.txt` |
| 单轴 7 px / 双轴 >=5 px | 两者均失效（双轴为**能力边界**，已固定为回归测试） | `.workbuddy/env-probe/diag_pyramid10.txt` |
| 边界伪影排除 | 用整数循环平移复测，结论不变 | `diag_pyramid10.txt` |
| 层数选择 | 实测 4 层在小位移反而劣化（4/48），故默认 3 层 | `diag_pyramid6.txt` |
| 沙箱可跑全量测试 | **47 passed**（原 33 + 等价性 4 + 金字塔 10） | `.workbuddy/env-probe/pytest_pyramid4.txt` |
| **test1 上 `--pyramid` 的 ITF 增益** | **未执行** —— 需 cv2 + test1.mp4；启用前**必须重标探针崩溃线** | 见 PROJECT_STATE「下一步」 |

### 本阶段暴露的真问题
1. **测试桩件把「位移」误当「绝对位置」**（真值应为 `pts + shift`），曾导致全盘假失败 → 修正后才看到真实能力。
2. **能力边界是任务固有的**：粗层对合成纹理收敛到能量更强的单轴局部极小；单轴 6 px 可解、双轴 6 px 不可解（阈值效应），与 §8.2「<=5 px」的规格边界一致。
3. **main.py 行法替换踩坑**：锚点定位失败导致 3 行被插入文件头、`--pyramid` 漏插 → 改为「子串定位 + 改后必 `py_compile`」。

---

## [P3] B. 三平滑器 × 窗口 对比实验（runner 就绪，结果待实测） —— 2026-09-25

**目标**：为 AGENTS.md §8.4 的「高斯 + 窗口 31」选型提供**端到端实测依据**（报告核心素材）。
**数学逻辑**：**零算法改动**，只扫既有 `--smooth` / `--window` 两个参数。

### 新增
| 文件 | 说明 |
|---|---|
| `+ tools/profile_smoothers.py` | 实验 runner：`ma/median/gauss` × 窗口 `{15,31,61}` × 数据集 `{synth,test1}`；每配置隔离输出到 `output/sweep/<dataset>/<smoother>_<w>/`；默认幂等（已有 metrics 跳过，`--force` 重跑）；单配置失败不中断并汇总；输出 `docs/smoother_sweep.json` + 对比表 + **规则化小结**（每个平滑器的窗口趋势、达标配置、S/ITF 最优配置）；`--md` 可把表追加进 RESULTS.md |

### 修改
| 文件 | 说明 |
|---|---|
| `~ docs/RESULTS.md` | 新增「七、三平滑器 × 窗口 端到端对比（B / P3）」：运行命令、**基准参考行（gauss/w31 的 v2.5 实测值）**、判定线、报告结论维度；其余 8 格**明确标注未实测**，禁止填推测值。§11 第 19 项 pytest 计数更新为「60 → 期望 64」 |
| `~ HANDOVER.md` | 五阶段表 P3 行更新；命令节补平滑器扫描 |
| `~ docs/API.md` | 辅助工具列表补 `profile_smoothers.py` |
| `~ PROJECT_STATE.md` | P3 状态与验收流程 |

### 验证证据
| 验证项 | 结果 | 证据路径 |
|---|---|---|
| `profile_smoothers.py` 语法 | `py_compile` 通过 | — |
| 汇总 / 表格 / 小结函数（9 组假数据） | 9 行表格 + 每个平滑器窗口趋势 + S/ITF 最优配置，输出正确 | `.workbuddy/env-probe/smoke_smoothers.txt` |
| 素材缺失守卫 | 缺合成视频时明确报错并 exit 1，不空跑 | `.workbuddy/env-probe/sweep_dryrun.txt` |
| 子进程失败处理 | 素材在位但 main.py 失败（本沙箱缺 cv2）→ 记录 `returncode=1` + stderr 尾部 + 失败清单，exit 1，不中断 | `.workbuddy/env-probe/sweep_dryrun2.txt` |
| **9 配置真实实验** | **未执行** —— 需 opencv + `data/synthetic/synthetic_shaky.mp4`（test1 档另需 test1.mp4） | 运行 `python tools/profile_smoothers.py --no-diagnostic --md docs/RESULTS.md` |

---
## [P2] C. pass2 提速：跳过纯诊断重采样 —— 2026-09-25

**目标**：缩短 pass2 耗时（test1 v2.5 实测 ≈ 1055 s），为 P3（三平滑器对比需多遍 test1 回归）降低实验成本。
**数学逻辑**：**严格等价，零数学改动**。默认口径（不传新开关）与 v2.5 代码路径**逐位一致**；
新增的可选开关只跳过「不参与任何验收判据」的辅助诊断量。

### 设计决策：为什么不做「合并诊断 warp 与写出」

工程原先记录的候选优化是「合并诊断 warp 与写出」。经代码核对：`crop.warp_crop_resize` 是
「补偿 + 裁剪 + 缩放」的**复合单次重采样**（逆映射 `B^{-1} @ A`），而诊断用的是**未裁剪的
`warp_frame(frame, B_t)`** —— 两者采样点、插值权重、有效域都不同，**合并必然改变成片像素**，
与「零数学改动」冲突（也会破坏 `warp_crop_resize` 的「避免二次插值模糊」设计）。
故改为**跳过**而非合并：`--no-diagnostic`。

### 新增
| 文件 | 说明 |
|---|---|
| `+ tests/test_invariance.py` | 编排级等价性测试（4 项，仅依赖 numpy + cv2 桩件）：关闭诊断后 `warp_frame` 调用数归零、成片路径逐帧入参一致、写出帧逐帧一致、默认参数保留诊断 |
| `+ tools/profile_pipeline.py` | pass 2 代价剖析：量化诊断 warp 在两次重采样中的占比（预热 3 轮 / 取 5 次中位 / 固定种子），输出终端表 + `docs/profile_pass2.json`，可 `--md` 追加到 RESULTS.md |

### 修改
| 文件 | 说明 |
|---|---|
| `~ main.py` | 新增 `--no-diagnostic`（跳过诊断 warp + 掩膜 PSNR）；pass 2 循环加 `if diag:` 分支；metrics.json 新增 `diagnostic.masked_itf`；模块 docstring 补诊断口径说明。**默认行为不变** |
| `~ tools/verify_invariance.py` | 识别「诊断开关变化」：此时把 `diagnostic` 与 `metrics.itf_warped_masked_db` 排除出比较，并**显式打印**该按设计缺失项（不静默忽略）；忽略集在任意层级生效 |
| `~ docs/KNOWN_ISSUES.md` | #17 更新：P2 已落地可选优化、实测占比口径、**明确不采用合并**及其数学原因 |
| `~ docs/API.md` | CLI 增 `--no-diagnostic`；辅助工具列表补三个核查/剖析工具；metrics.json 增 `diagnostic` 块 |
| `~ README.md` | 运行方式补 `--no-diagnostic` 说明 |
| `~ PROJECT_STATE.md` | P2 改动 / 测试结果 / 下一步 |

### 新增（本地，不入库）
| 文件 | 说明 |
|---|---|
| `+ .workbuddy/baseline-local/PROJECT_STATE_v2.5_before_P2.md` | **优化前基线备份**（v2.5 已验收状态），供对比与回滚 |
| `+ .workbuddy/baseline-local/README.md` | P2 验收流程（5 步命令 + 判定标准表） |
| `+ .workbuddy/baseline-local/p2_base_metrics_example.json` | P2 等价比对场景示例 |

### 验证证据
| 验证项 | 结果 | 证据路径 |
|---|---|---|
| `tests/test_invariance.py`（编排级，无 cv2 可跑） | **4 passed** —— 关闭诊断后 `warp_frame` 调用 5→0，成片路径入参逐帧一致，写出帧一致 | `.workbuddy/env-probe/pytest_invariance2.txt` |
| `verify_invariance.py` 场景矩阵 | A 仅计时→exit 0；B 指标漂移→exit 1；C 配置不可比→exit 1；**P2 关诊断→exit 0** | `.workbuddy/tests-p1/final_*.txt` |
| `profile_pipeline.py` 冒烟 | 320×180×6 帧：诊断 warp 8.78 ms/帧，占两次重采样 **58.9%** | `.workbuddy/env-probe/profile_small.txt` |
| `main.py` 语法 | `py_compile` 通过 | — |
| 全量 64 项 pytest / 端到端双档 / 成片 PSNR 等价性 / test1 pass2 提速实测 | **未执行** —— 本沙箱缺 cv2 与 `data/test1.mp4` | 须按 `.workbuddy/baseline-local/README.md` 在你的机器执行 |

### 本阶段暴露并修掉的真问题
1. **按行号批量替换导致 pass 2 的 `with`/初始化行被误删**（`git diff` 才暴露）→ 改为「先 diff 复核 + 用唯一锚点文本替换 + 每次改后 `py_compile`」。
2. **here-string 吞掉前导缩进**（PowerShell `@'...'@` 对首行缩进的处理）→ 改用显式数组逐行构造替换块。
3. **`verify_invariance.py` 忽略集只在顶层生效**，导致嵌套的 `metrics.itf_warped_masked_db` 仍被判差异 → 忽略集改为任意层级生效。

---

## [P1] 迁移与验证骨架 —— 2026-09-25

**目标**：把「换机器 / 换 agent 能否接手」从口头约定变成可执行核查；为 P2 的性能优化准备等价性判据。
**数学逻辑**：不触碰任何算法与数值口径（本阶段零算法改动）。

### 新增
| 文件 | 说明 |
|---|---|
| `+ HANDOVER.md` | 交接总入口：环境先决条件、不入库文件、验收档位 A/B/C、核心命令、五阶段路线、迁移规则、已知缺口 |
| `+ CHANGELOG.md` | 本文件：文件级变更记录 |
| `+ tools/verify_env.py` | 上机环境 / 数据 / 红线 / 测试 / 覆盖率自检；退出码 0 就绪、1 阻断、2 缺实拍素材 |
| `+ tools/verify_invariance.py` | 改前改后等价性验证：`metrics.json` 递归 deep-diff（忽略 `runtime_sec`，校验配置类字段严格相等）+ 成片逐帧 PSNR |
| `+ tools/transfer_check.ps1` | 一键核查：环境 → 测试 → 合成档端到端（可选实拍档），报告落 `.workbuddy/baseline-local/reports/<时间戳>/` |

### 修改
| 文件 | 说明 |
|---|---|
| `~ AGENTS.md` | §17 文档体系登记 `HANDOVER.md` / `CHANGELOG.md` 与两个核查工具 |
| `~ README.md` | 文档中心新增 HANDOVER 入口；补充一键核查脚本用法 |
| `~ docs/DEVELOPMENT.md` | 新增「迁移与核查」小节（命令、档位、坑位） |
| `~ PROJECT_STATE.md` | 记录 P1 改动 / 测试结果 / 下一步 |

### 新增（本地证据，不入库）
| 文件 | 说明 |
|---|---|
| `+ .workbuddy/env-probe/SANDBOX_ENV_*.md` | 受限沙箱环境实测记录（pip 阻断根因、可用解释器清单） |
| `+ .workbuddy/env-probe/*.json/.txt` | `verify_env` / `verify_invariance` / pytest 的实测输出 |
| `+ .workbuddy/baseline-local/reports/<时间戳>/` | `transfer_check.ps1` 的运行报告 |

### 验证证据
| 验证项 | 结果 | 证据路径 |
|---|---|---|
| `verify_env.py` 阻断路径（缺 cv2） | exit 1，正确列出 6 项依赖缺失 | `.workbuddy/env-probe/ve_anaconda.txt` |
| `verify_env.py` 红线自检 | 扫描 18 个主实现文件，**无违规** | 同上 |
| `verify_invariance.py` 三路径 | A=exit 0（仅计时差异）；B=exit 1（指标漂移 1e-3）；C=exit 1（配置不可比） | `.workbuddy/tests-p1/out_*.txt` |
| `verify_invariance.py` BOM 容忍 | 带 BOM 的 JSON 可正常解析（修复前崩溃） | 同上 |
| `transfer_check.ps1` 守卫 | 缺依赖时 exit 1，**不进入 end-to-end**；报告落盘 | `.workbuddy/env-probe/tc_run7.txt` |
| pytest（本沙箱可收集部分） | 33 passed（`shots/tracking/warp` 因缺 cv2 无法收集） | `.workbuddy/env-probe/pytest_recheck.txt` |
| pytest 全量 60 项 / 端到端 / 等价性视频比较 | **未执行** —— 本沙箱缺 cv2 与 `data/test1.mp4`，须在有 cv2 的机器上执行 | — |

### 本阶段暴露并修掉的真问题（记录以免重踩）
1. **`ProcessStartInfo.ArgumentList` 在 Windows PowerShell 5.1 不存在**（.NET Framework）→ 改用手工拼接 `Arguments`。
2. **子进程 stdout 重定向死锁**：设 `RedirectStandardOutput=$true` 却 `ReadToEnd()` 会挂起 → 改为 `BaseStream.CopyTo` 落文件再读回，并加超时保护。
3. **`verify_env.py` 退出码语义错**：缺依赖时返回 2（"数据不全"）会让上层误判为可继续 → 依赖缺失一律返回 1（阻断）。
4. **`.ps1` 中文需 UTF-8 BOM**：Windows PowerShell 5.1 按 ANSI 读无 BOM 的 `.ps1`，中文注释会导致解析错误。
5. **`verify_invariance.py` 不认 BOM**：`json.load` 对带 BOM 文件报错 → 改用 `encoding="utf-8-sig"`。

---

## 模板（后续阶段照此填写）

```markdown
## [阶段号] 标题 —— YYYY-MM-DD

**目标**：
**数学逻辑**：（是否偏离既有数学约定；若偏离，附用户确认记录）

### 新增 / 修改 / 删除
| 文件 | 说明 |

### 验证证据
| 验证项 | 结果 | 证据路径 |

### 遗留 / 未执行
```
