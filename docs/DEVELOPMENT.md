# 开发环境与协作约定

> 对应 AGENTS.md §3（技术栈）与 §13（会话协议）。快速上手见 [../README.md](../README.md)。

## 一、环境要求

| 项 | 值 |
|---|---|
| Python | 3.10+（本项目实测 3.13.14） |
| 依赖（锁定） | numpy 2.5.3、opencv-python 5.0.0.93、matplotlib 3.11.2、pytest 9.1.1、pytest-cov 7.1.0（传递依赖 coverage 7.16.1，2026-09-25 经用户批准新增） |
| 操作系统 | Windows 10/11（Linux/macOS 亦可，激活脚本路径不同） |

## 二、环境搭建

```powershell
python tools\verify_env.py          # 环境 + 数据 + 红线（含禁用 API 与遗留 TODO 扫描）
source .venv/Scripts/activate        # Git Bash
# CMD:      .venv\Scripts\activate
# PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

| 终端 | 激活命令 | 注意 |
|---|---|---|
| Git Bash | `source .venv/Scripts/activate` | `source` 是 bash 内置命令 |
| CMD | `.venv\Scripts\activate` | 不要用 `source`（会报「不是内部或外部命令」） |
| PowerShell | `.venv\Scripts\Activate.ps1` | 若被禁止：`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |

网络不通时的三种方案：

```bash
# 1) 镜像（本机实测阿里云可用，清华/官方源不可用）
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
# 2) 代理（本机端口 7897）
pip install -r requirements.txt --proxy http://127.0.0.1:7897
# 3) 离线：有网机器下载轮子后拷贝
pip download -r requirements.txt -d wheels/
pip install --no-index --find-links=wheels -r requirements.txt
```

**坑**：本机 CMD 中 `python` 可能解析到 msys2 的 Python 3.12.11，其 `venv` 生成 `bin/` 布局且**无 activate.bat**。若 `.venv/Scripts/` 不存在，请用 CPython 完整路径重建（README 第六节有本机备注）。

## 三、常用命令

| 目的 | 命令 |
|---|---|
| 单元测试 | `python -m pytest tests/ -q`（期望 60 passed） |
| 覆盖率测量 | `python -m pytest tests/ --cov=ds --cov=src.smoothing --cov=src.motion --cov=src.warp --cov=src.features --cov=src.tracking`（核心模块总体 98%，§11 验收线 ≥80%） |
| 合成数据 | `python tools/make_synthetic.py`（种子 42） |
| 稳像运行 | `python main.py --input <mp4> --output <mp4> --smooth gauss --window 31 --vis` |
| 计时基准 | `python tools/bench_ds.py` |
| 单文件测试 | `python -m pytest tests/test_motion.py -q -s`（`-s` 显示诊断输出） |
| 环境/红线自检 | `python tools/verify_env.py`（加 `--cov` 追覆盖率；退出码 0 就绪 / 1 阻断 / 2 缺实拍素材） |
| 改动等价性 | `python tools/verify_invariance.py --baseline <旧 metrics.json> --candidate <新 metrics.json> [--baseline-video A --candidate-video B]` |
| 一键迁移核查 | `powershell -ExecutionPolicy Bypass -File tools/transfer_check.ps1 -Full`（报告落 `.workbuddy/baseline-local/reports/<时间戳>/`） |

## 四、目录结构

```
src/        自研算法模块（11 个）
ds/         手写数据结构（2 个）
tools/      合成数据生成器、计时基准
tests/      pytest（7 个文件）
docs/       文档中心（本目录）
data/       测试素材（实拍 test1.mp4 已入库；合成 *.mp4 不入库）与合成数据
output/     运行产物（不入库）
main.py     流水线入口
HANDOVER.md 交接总入口（环境先决条件 / 验收档位 / 迁移规则）
CHANGELOG.md 文件级变更记录
```

## 五、迁移与核查（跨机器 / 跨 agent 接手必做）

接手或换机器后，**先核查再写代码**（历史教训：既有验收全绿仍可能掩盖感知回归，见 KNOWN_ISSUES #21）。

| 核查项 | 命令 | 判定 |
|---|---|---|
| 环境 + 数据 + 红线 + 测试 | `python tools/verify_env.py --cov` | 退出码 0 就绪；1 阻断；2 缺 `data/test1.mp4` |
| 一键全档核查 | `powershell -ExecutionPolicy Bypass -File tools/transfer_check.ps1 -Full` | 报告落 `.workbuddy/baseline-local/reports/<时间戳>/` |
| 改动前后等价性 | `python tools/verify_invariance.py --baseline A --candidate B`（可加 `--baseline-video/--candidate-video`） | metrics 逐字段一致 + 成片逐帧 PSNR ≥ 50 dB |

**验收档位**（由手上素材决定，详见 `HANDOVER.md` 第三节）：

- **A 全档**：依赖齐 + `data/test1.mp4` 在位 → 单元测试 + 合成档 + 实拍档；
- **B 合成档**：依赖齐、无 test1 → 单元测试 + 合成档；
- **C 只读档**：缺 cv2 等依赖 → 只能做红线自检与不依赖 cv2 的部分测试，**不得声称指标通过**。

**环境陷阱**（实测记录，详见 `HANDOVER.md` §2.4）：

- pip 需要可写的临时目录；受限沙箱会报 `PermissionError: ...pip-unpack-...`（非工程问题）；
- msys2 的 Python 建 venv 不可用（无 `activate.bat`），请用标准 CPython；
- Windows PowerShell 5.1 读**无 BOM 的 `.ps1`** 会按 ANSI 解析 → 本仓 `.ps1` 统一带 UTF-8 BOM；
- 中文控制台乱码时，留证据请用 `$env:PYTHONIOENCODING='utf-8'` + `Out-File -Encoding UTF8`。
## 六、编码约定

- 注释与文档字符串一律**简体中文**；模块 docstring 需写明：职责、实现要点、复杂度、对应 AGENTS.md 章节。
- 数据结构相关实现需在注释中给出**五要素**：功能、实现要点、时间/空间复杂度、替代方案、选型理由（§10）。
- 常量用模块级大写（如 `MAD_THRESHOLD`）；阈值调整须记入 PROJECT_STATE.md 决策日志。
- 数值计算用 NumPy 向量化，**禁止逐像素/逐点 Python 循环**（红线 2/4）。
- 日志用 `logging`（stderr），warning 用于降级，info 用于阶段完成与限幅统计。
- 接口签名未经用户确认不得修改（§6）；新增可选参数需保证既有调用行为不变。

## 七、红线自检清单（提交前逐条确认）

1. 运动估计：未使用 `estimateAffinePartial2D / estimateAffine2D / findHomography / estimateRigidTransform`；RANSAC 自研（可用 `np.linalg.lstsq / svd`）。
2. 图像补偿：未使用 `warpAffine / warpPerspective / remap / resize`；所有重采样走 `src.warp`。
3. 特征与跟踪：`src/features.py`、`src/tracking.py` 无 cv2 调用、无 `TODO(SELF-IMPL)`；`cornerHarris / cornerSubPix` 全程禁用。
4. 滤波与梯度：主实现未使用 `scipy.ndimage / filter2D / GaussianBlur / Sobel / boxFilter`；`np.convolve` 仅出现在 tools/（数据生成）。
5. 编解码：只用 `cv2.VideoCapture / VideoWriter`。
6. 线性代数：SVD/伪逆/矩阵乘使用 NumPy。
7. 数据结构：环形缓冲、双堆为手写实现；`collections.deque / heapq` 仅出现在 tests/。

自检命令（提交前建议执行）：

```bash
grep -rn "cv2\.\(warpAffine\|remap\|resize\|goodFeaturesToTrack\|calcOpticalFlowPyrLK\|Sobel\|GaussianBlur\|boxFilter\|filter2D\|cornerHarris\|cornerSubPix\|estimate\)" src/ ds/
grep -rn "from collections import deque\|import heapq" src/ ds/
grep -rn "TODO(SELF-IMPL)" src/ ds/
```

期望：全部无输出（`src/`、`ds/` 内）。

## 八、Git 约定

- 提交信息前缀：`docs:`（文档）、`feat:`（功能）、`fix:`（修复）、`refactor:`（重构）、`test:`（测试）、`chore:`（杂项）。
- 中文正文，首行不超过 72 字，正文用 `-` 列表说明改动与原因。
- 提交前：跑 `python -m pytest tests/ -q`；更新 PROJECT_STATE.md。
- 不入库：`output/`、`data/synthetic/*.mp4`、`.venv/`、`.workbuddy/`（见 `.gitignore`）。
  **例外**：实拍素材 `data/test1.mp4` 自 2026-09-26 起入库（保证克隆即可跑实拍档）。

## 九、会话协议摘要（§13）

1. 会话开始：读 `PROJECT_STATE.md` + `HANDOVER.md` + `docs/README.md`，跑 `python tools/verify_env.py` 确认基线与档位，用 ≤5 行复述「已完成 / 当前 / 本次任务 / 已知风险」。
2. 列出计划与验收方式，**等用户确认后再动手**。
3. DoD（缺一不算完成）：代码完成 + pytest 通过 + 数值对照达标 + `PROJECT_STATE.md` 已更新。
4. 任何偏离契约的决策（改接口、换算法、加依赖、动红线）必须先停下来问用户。
5. 会话结束：更新 STATE、输出变更摘要、提醒 git commit；指标不达标时先报告数据再讨论，禁止擅自降低标准。

## 十、新增依赖流程

依 §3：任何新增依赖（含 `pytest-cov` 等工具类）必须**先征求用户同意**，确认后再写入 `requirements.txt` 并锁定版本；随后更新本文件与 README 的依赖列表。
