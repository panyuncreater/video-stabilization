# HANDOVER —— 交接总入口（跨会话 / 跨机器 / 跨 agent 迁移）

> 本文回答一个问题：**一个没有任何上下文的新 agent，拿到这个仓库后，怎么在最短时间内
> 确认「它能跑、它没被改坏、现在该做什么」，并且有据可查。**
>
> 本文不替代 AGENTS.md（规范与红线）、PROJECT_STATE.md（进度与决策日志）与 docs/（技术细节），
> 而是它们的**入口 + 落地核查清单**。

---

## 一、五分钟接手路径

| 顺序 | 动作 | 目的 |
|---|---|---|
| 1 | 读本文「二、三、四」 | 知道环境怎么起、当前干到哪、下一步做什么 |
| 2 | 读 `AGENTS.md` 第四、五、六、九节 | 红线（§4）、阶段（§5）、接口契约（§6）、指标定义（§9） |
| 3 | 读 `PROJECT_STATE.md` | 已完成的实测数值、本次改动、决策日志 |
| 4 | `python tools/verify_env.py --cov` | **一次性确认环境 + 红线 + 60 项测试 + 覆盖率** |
| 5 | 按需读 `docs/`（顺序见 `docs/README.md`） | 架构 / API / 测试 / 指标 / 已知问题 |

> 接手者**不得**先改代码再验证：本工程的历史教训是「既有验收全绿仍可能掩盖感知回归」
> （见 PROJECT_STATE.md 的 v2.5 与 KNOWN_ISSUES #21），所以先跑 §四 的核查，再动代码。

---

## 二、环境先决条件（迁移最强约束）

### 2.1 版本锁定

| 项 | 要求 | 来源 |
|---|---|---|
| Python | ≥ 3.10（开发机实测 3.13.14） | README 第一节 |
| numpy | `2.5.3` | `requirements.txt` |
| opencv-python | `5.0.0.93`（**必需**，缺它无法跑流水线与 27 项测试） | 同上 |
| matplotlib | `3.11.2` | 同上 |
| pytest | `9.1.1` | 同上 |
| pytest-cov / coverage | `7.1.0` / `7.16.1` | 同上 |

依赖**按实际环境精确锁定**（AGENTS.md §3）：升级或新增任何依赖**必须先问用户**。

### 2.2 不入库的文件（迁移必查）

| 路径 | 状态 | 迁移动作 |
|---|---|---|
| `.venv/` | gitignore，**不迁移** | 每台机器各自建（§2.3） |
| `data/test1.mp4` | **已入库**（2026-09-26 起，11.3 MB） | 克隆即得，无迁移动作；实拍档验收直接可用 |
| `data/synthetic/synthetic_shaky.mp4` | gitignore，**可由代码重建** | `python tools/make_synthetic.py`（种子 42） |
| `output/` | gitignore | 由运行产生；改动前后对比需要各自留存（§四） |
| `.workbuddy/` | gitignore，AI 工作目录 | 存放本地证据（环境快照、对比产物） |

### 2.3 建环境（标准路径）

```powershell
# 1) 用已知可用的 CPython 建 venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2) 装锁定依赖（国内走镜像；阿里云实测可用）
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 3) 一次性核查
python tools\verify_env.py --cov --json .workbuddy\env-probe\verify_env.json
```

也可以直接跑一键脚本（等价，但会同时落盘报告）：

```powershell
powershell -ExecutionPolicy Bypass -File tools\transfer_check.ps1 -Full
```

### 2.4 已知环境陷阱（踩过，记录以免重踩）

1. **`pip` 依赖可写的临时目录**：某些受限沙箱/容器禁止向 `tempfile.mkdtemp()` 新建的子目录
   写入，表现为 `pip` 报 `PermissionError: ...pip-unpack-.../xxx.whl.metadata`。
   这不是工程问题——换一台正常机器或用带写权限的容器即可；也可用 `pip download` + 手动
   解包绕开（不推荐，易破坏版本锁定）。
2. **msys2 的 Python 建 venv 不可用**：会生成 `bin/` 布局且没有 `activate.bat`（README 第六节）。
   请用标准 CPython 安装版。
3. **`ensurepip` 失败时 venv 无 pip**：可用基解释器安装 `pip --python .venv\Scripts\python.exe`，
   （`--python` 必须写在子命令前）。
4. **控制台中文乱码**：PowerShell 回显中文可能乱码，属**显示**问题。需要留证据时用
   `$env:PYTHONIOENCODING='utf-8'` 并把输出 `Out-File -Encoding UTF8`，再以 UTF-8 读回。
5. **BOM**：手工/其它脚本中转过的 JSON 可能带 BOM；`tools/verify_invariance.py` 已显式容忍。
6. **`tools/*.ps1` 必须带 UTF-8 BOM**：Windows PowerShell 5.1 会按 ANSI 解析无 BOM 的 `.ps1`，
   中文注释将导致语法错误。用 VS Code「UTF-8 with BOM」或 `Set-Content -Encoding UTF8`（PS 5.1 自带 BOM）保存。
7. **失败实验可能留下不可删的临时目录**：受限环境下 pip 失败会在仓库根目录留下
   `pip-unpack-*` / `pip-build-tracker-*` 等目录（无写权限，连 `rmdir /s /q` 也删不掉）。
   它们未被跟踪、也不被 `.gitignore` 覆盖，但**不在暂存区**，只是让 `git status` 报 warning；
   在正常权限的终端里手工删除即可，不影响仓库内容。

---

## 三、验收档位（按手上有什么素材决定）

跑 `tools/verify_env.py` 的结论会落到以下三档之一：

| 档位 | 前提 | 可执行的验收 | 不能做的 |
|---|---|---|---|
| **A. 全档** | 依赖齐 + `data/test1.mp4` 在位 | 60 项 pytest + 覆盖率 + 合成档 + 实拍档 | — |
| **B. 合成档** | 依赖齐，无 test1 | 60 项 pytest + 覆盖率 + 合成档全部指标 | test1 的 ITF/S/裁剪率/切换检出 |
| **C. 只读档** | 缺 cv2 或缺其它依赖 | 红线静态自检 + 不依赖 cv2 的部分测试 | 流水线、任何端到端指标、等价性视频比较 |

> 档位 C **不能**用来声称「指标通过」。历史上本仓就在受限沙箱里只能跑 33/60 项测试
> （`shots/tracking/warp` 因模块级 `import cv2` 无法收集），此时只做文档与脚本工作。

---

## 四、核心验收命令（照抄可用）

```powershell
# 0) 环境 + 红线 + 测试 + 覆盖率
python tools\verify_env.py --cov

# 1) 重建合成素材（缺 synthetic_shaky.mp4 时）
python tools\make_synthetic.py

# 2) 合成档端到端（与 docs/RESULTS.md 的基准数值对照）
python main.py --input data/synthetic/synthetic_shaky.mp4 `
               --output output/synthetic/stabilized.mp4 --smooth gauss --window 31 --vis

# 3) 实拍档端到端（需 data/test1.mp4；单遍 pass2 约 18 分钟）
python main.py --input data/test1.mp4 `
               --output output/test1/stabilized.mp4 --smooth gauss --window 31 --vis

# 4) 改动前后等价性（性能类改动必做；否则不得声称「零数学改动」）
python tools\verify_invariance.py `
  --baseline  output/_baseline/synthetic/metrics.json `
  --candidate output/synthetic/metrics.json `
  --baseline-video  output/_baseline/synthetic/stabilized.mp4 `
  --candidate-video output/synthetic/stabilized.mp4 `
  --psnr-min 50 --json .workbuddy\baseline-local\invariance_synthetic.json

# 5) 数据结构计时基准（§10 报告素材）
python tools\bench_ds.py

# 6) pass 2 诊断开销剖析（P2/C：诊断 warp 占两次重采样的比例）
python tools\profile_pipeline.py --json docs\profile_pass2.json

# 7) 三平滑器 × 窗口 对比实验（P3/B；结果落 docs/smoother_sweep.json 并可追加进 RESULTS.md）
python tools\profile_smoothers.py --no-diagnostic --md docs\RESULTS.md
python tools\profile_smoothers.py --stage test1 --no-diagnostic --md docs\RESULTS.md   # 需 test1.mp4，≈2.9 h

# 8) 跳过纯诊断重采样（P2/C 提速；不传则与历史版本逐位一致）
python main.py --input data/test1.mp4 --output output/test1/stabilized.mp4 `
               --smooth gauss --window 31 --no-diagnostic
```

**基线留存约定**：任何性能/等价性改动，先跑一遍并另存为 `output/_baseline/<档位>/`，
再改代码跑第二遍对比；不要覆盖旧 metrics.json。`.workbuddy/baseline-local/` 用于放对照结论。

---

## 五、当前进度与五阶段路线（2026-09-25 之后）

**已完成**：M0 / M1 / v2.1 镜头切分 / v2.2 文档体系 / v2.3 探针 / v2.4 M2 验收收口 /
v2.5 角点空间均匀化（根治「修复后比原视频更抖」）。**M2 验收达成，交付就绪**；
§11 全部 22 项通过；pytest 60 passed（P2 新增 `tests/test_invariance.py` 4 项 → 期望 64 passed）；核心模块覆盖率 98%。

**剩余交付**：课程报告成稿。已批准的三项优化按序推进：**P2(C) 已落地待验收** → P3(B) → P4(A)。

| 阶段 | 内容 | 数学逻辑 | 验收方式 | 状态 |
|---|---|---|---|---|
| **P1** | 迁移与验证骨架：`HANDOVER.md`、`CHANGELOG.md`、`tools/verify_env.py`、`tools/transfer_check.ps1`、`tools/verify_invariance.py` | 不触碰数学 | 脚本可用 + 文档自洽 | ✅ 已完成（用户验收中） |
| **P2** | C. pass2 提速：**已落地** `main.py --no-diagnostic`（跳过纯诊断的中间 warp 与掩膜 ITF）。原记候选「合并诊断 warp 与写出」经核对不可行（复合重采样 vs 未裁剪 warp 的插值不同，合并必改成片像素），故改为**跳过**而非合并 | 严格等价（默认口径与 v2.5 逐位一致） | 编排级等价性 4 项（`tests/test_invariance.py`，无 cv2 可跑）+ 改前后 metrics 逐字段一致 + 成片逐帧 PSNR ≥ 50 dB + 64 passed + pass2 计时；流程见 `.workbuddy/baseline-local/README.md` | 🔶 **代码已落地，待用户验收** |
| **P3** | B. 三平滑器对比：`ma`/`median`/`gauss` × `--window` {15,31,61} × {合成, test1} | 零算法改动（只扫既有参数） | runner/表格/判定线已就位（`tools/profile_smoothers.py` + RESULTS.md §七）；**9+9 配置结果待实测** | 🔶 **runner 已就位，待跑实验** |
| **P4** | A. 金字塔 LK：**已落地**，`main.py --pyramid`（默认**关闭**，保证既有标定/指标逐位不变）；2x2 均值池化金字塔 + 粗到细（同一套 LK 方程，仅初值不同） | 复用既有 LK 数学（扩展非替换） | >=2 阶段实测：单轴 6 px 单层崩溃（0.10）而金字塔 1.00；**双轴 >=5 px 仍失败（能力边界，KNOWN_ISSUES #23）**；test1 收益待验证且**须先重标探针崩溃线** | 🔶 **实现已落地（默认关闭），待验证** |
| **P5** | 课程报告成稿 | 汇总 | 交付物清单（§15）核对 | 待做 |

**执行顺序固定为 C → B → A**：C 落地后缩短 test1 回归周期（现 pass2 ≈ 1055 s），
B 需要多遍 test1 回归，A 是最大改动、压轴。

**参数交互警告**：`src/shots.py` 的探针崩溃线（现 **0.25**）与 `src/tracking.py` 的
`RESIDUAL_MAX`（现 **0.05**）存在交互——重调 LK 阈值**必须重标探针线**并重跑双份回归。

---

## 六、迁移规则（新 agent / 新会话必须遵守）

1. **先核查再动手**：`tools/verify_env.py --cov` 全绿之前不写代码。
2. **每次会话开始**：读 `PROJECT_STATE.md`，用 ≤5 行复述「已完成 / 当前 / 本次任务 / 风险」
   （AGENTS.md §13.1）。
3. **动手前先报计划与验收方式**，等用户确认（AGENTS.md §13.2）。
4. **DoD 四条缺一不算完成**：代码 + pytest + 数值对照 + `PROJECT_STATE.md` 已更新（§13.3）。
5. **偏离文档必先问**：改接口、换算法、加依赖、动红线（§13.4）。
6. **改动可追溯**：每阶段独立 commit；`PROJECT_STATE.md` 的「本次改动（文件级清单）」逐文件列出
   新增/修改；性能类改动附 `tools/verify_invariance.py` 的 JSON 报告路径。
7. **收尾**：更新 `PROJECT_STATE.md`（改动 / 测试结果 / 遗留问题 / 下一步 / 决策日志），
   输出变更摘要并提醒用户 `git commit`（§13.5）。
8. **不得夸大执行范围**：没跑过的验证写「未执行」，并在档位表里标清属于哪一档（§三）。

---

## 七、已知缺口（迁移视角）

| 缺口 | 影响 | 处理 |
|---|---|---|
| ~~实拍素材 `data/test1.mp4` 不入库~~ **已于 2026-09-26 关闭** | 克隆即可跑实拍档，不再受「只能做合成档」限制 | `data/test1.mp4` 已入库；`verify_env.py` 不再报缺素材 |
| 原机 `.venv` 不可迁移 | 新机器需重建 | §2.3 命令；版本以 `requirements.txt` 为准 |
| 无 CI 配置 | 回归靠手工执行 | 用 `tools/transfer_check.ps1` 一键跑，报告落 `.workbuddy/` |
| pass2 耗时偏长（test1 ≈ 1055 s） | 多遍回归代价高 | P2 解决（目标 −20~30%） |
| 控制台中文乱码 | 证据留存易踩坑 | §2.4 第 4 条 |

---

## 八、本次（P1）改动清单

| 文件 | 类型 | 说明 |
|---|---|---|
| `HANDOVER.md` | 新增 | 本文：交接总入口 |
| `tools/verify_env.py` | 新增 | 环境 / 数据 / 红线 / 测试 / 覆盖率 自检，返回 0/1/2 |
| `tools/verify_invariance.py` | 新增 | 改前改后 metrics.json 逐字段对比 + 成片逐帧 PSNR |
| `tools/transfer_check.ps1` | 新增 | 一键跑核查 + 端到端并落盘报告 |
| `AGENTS.md` | 修改 | §17 文档体系登记上述入口 |
| `README.md` | 修改 | 文档中心新增 HANDOVER 入口与一键脚本 |
| `docs/DEVELOPMENT.md` | 修改 | 新增「迁移与核查」小节 |
| `PROJECT_STATE.md` | 修改 | P1 改动 / 测试结果 / 下一步 |
| `.workbuddy/env-probe/*` | 本地证据 | 沙箱环境实测记录、`verify_env` 输出与 JSON（不入库） |
