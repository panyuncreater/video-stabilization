# 视频抖动去除（电子稳像）—— 数据结构课程大作业

输入一段手持抖动视频（mp4），估计帧间 **2D 相似变换**（平移 + 旋转 + 等比缩放，4 自由度），在参数空间平滑相机轨迹后做逆向映射补偿，输出：稳定后视频 + 量化指标（metrics.json）+ 可视化图表。

核心算法（RANSAC、Harris 角点、LK 光流、图像 warp、环形缓冲、双堆中值等）全部自研，禁止调用 OpenCV 高层封装——完整约束、接口契约与验收基准见 [AGENTS.md](AGENTS.md)。

**当前状态**：M1 已完成（自研 Harris + 单层 LK 替换 cv2 临时实现），pytest 54 passed，合成与实拍双份四项指标全部达标。下一步 M2（验收收口与报告素材定稿）。

## 文档中心（`docs/`）

新接手请先读 [docs/README.md](docs/README.md)（含阅读顺序）：

| 文档 | 内容 |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 两遍离线架构、模块依赖、数学约定、异常降级 |
| [docs/API.md](docs/API.md) | 模块接口签名、CLI、metrics.json 结构、退出码 |
| [docs/data_structures.md](docs/data_structures.md) | 数据结构选型、复杂度、实测耗时（课程报告素材） |
| [docs/TESTS.md](docs/TESTS.md) | 测试清单与验收映射 |
| [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md) | 已知问题、根因、解决方案与待决策项 |
| [docs/RESULTS.md](docs/RESULTS.md) | 端到端指标、产物路径、复现步骤 |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | 环境搭建、命令、Git/编码约定、红线自检 |
| [PROJECT_STATE.md](PROJECT_STATE.md) | 交接状态（每次会话必读必更新） |

## 一、环境要求

| 项目 | 要求 |
|---|---|
| 操作系统 | Windows 10/11（Linux / macOS 亦适用） |
| Python | 3.10+（3.12 / 3.13 均可） |
| 第三方依赖 | 仅 4 个：numpy、opencv-python、matplotlib、pytest（版本锁定见 requirements.txt） |

> 未安装 Python 时，从 https://www.python.org/downloads/ 下载安装并勾选 **Add python.exe to PATH**。

## 二、完整安装步骤

以下命令默认在**项目根目录**下执行。

### 第 1 步：确认 Python 版本

```bash
python --version          # 期望 ≥ 3.10
# Windows 也可用 py 启动器确认：py -3 --version
```

### 第 2 步：创建项目虚拟环境

```bash
python -m venv .venv
```

> `.venv/` 已在 .gitignore 中，不会提交。虚拟环境不可移植，每台机器克隆后各自创建。

### 第 3 步：激活虚拟环境

| 终端 | 命令 |
|---|---|
| Git Bash | `source .venv/Scripts/activate` |
| CMD | `.venv\Scripts\activate` |
| PowerShell | `.venv\Scripts\Activate.ps1` |

> ⚠️ `source` 是 **Git Bash 专用**命令；CMD 直接运行 `.venv\Scripts\activate`（自动匹配 activate.bat），**不要加 `source`**，否则报「'source' 不是内部或外部命令」。
> PowerShell 若报「禁止运行脚本」：先执行 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` 再激活。

### 第 4 步：安装依赖

```bash
pip install -r requirements.txt
```

国内网络较慢 / 失败时，指定镜像源（任选其一）：

```bash
# 阿里云
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/
# 清华
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
# 腾讯
pip install -r requirements.txt -i https://mirrors.cloud.tencent.com/pypi/simple
```

需要走代理（端口按本机实际修改）：

```bash
pip install -r requirements.txt --proxy http://127.0.0.1:7890
```

完全无网络时（离线安装）：

```bash
# 在任意一台有网的机器上：只下载不安装（注意下载机需与目标机同为 Windows x64）
pip download -r requirements.txt -d wheels/
# 把 wheels/ 整个文件夹拷贝到本项目根目录后：
pip install --no-index --find-links=wheels -r requirements.txt
```

### 第 5 步：验证安装

```bash
python -c "import numpy, cv2, matplotlib, pytest; print(numpy.__version__, cv2.__version__, matplotlib.__version__, pytest.__version__)"
```

四个版本号正常打印即安装成功。

### 第 6 步：版本回写（项目约定）

AGENTS.md 约定依赖按实际环境精确锁定。安装成功后核对实际版本，若与 requirements.txt 不一致（Git Bash）：

```bash
pip freeze | grep -iE "^(numpy|opencv-python|matplotlib|pytest)=="
```

把实际版本回写 requirements.txt，并在 PROJECT_STATE.md 记录一次。

## 三、运行方式（M0 已可用）

```bash
python main.py --input data/test1.mp4 --output output/test1/stabilized.mp4 --smooth gauss --window 31 --max-corners 500 --vis
```

- `--smooth {ma|gauss|median}` 平滑器；`--window` 平滑窗口（默认 31，偶数自动 +1）；`--max-corners` 角点数（默认 500）；`--vis` 输出轨迹对比图与指标柱状图到 docs/。
- `--clamp-tx / --clamp-theta / --clamp-ln-s` 漂移限幅（默认 30 px / 3° / 0.05），`--no-clamp` 关闭。
- 产物：稳定视频 + 同目录 `metrics.json`（§15 字段），`--vis` 图在 docs/。
- 退出码（§12）：0 成功；1 输入错误；2 连续 5 帧估计失败；3 输出封装不一致；4 内部错误。

合成数据（验收用）：

```bash
python tools/make_synthetic.py          # 种子 42，输出到 data/synthetic/
```

数据结构计时基准（§10 报告素材）：

```bash
python tools/bench_ds.py                # 输出到 docs/bench_ds.json 与 docs/bench_ds.png
```

> **数据说明**：`data/test1.mp4`（11 MB）不入库。克隆仓库后如需实拍验收，请手动获取该文件放入 `data/`；无该文件时可仅用合成视频验收（`tools/make_synthetic.py` 生成）。

## 四、结果复现

完整指标、产物路径与复现步骤见 [docs/RESULTS.md](docs/RESULTS.md)。要点：

```bash
python -m pytest tests/ -q                       # 期望 54 passed
python main.py --input data/synthetic/synthetic_shaky.mp4 \
               --output output/synthetic/stabilized.mp4 --smooth gauss --window 31 --vis
python main.py --input data/test1.mp4 \
               --output output/test1/stabilized.mp4 --smooth gauss --window 31 --vis
```

| 指标（最新 M1） | 合成视频 | test1.mp4 | 验收线 |
|---|---|---|---|
| ITF 提升 | +3.10 dB | +0.65 dB | 高于原视频 |
| 稳定度 S | 0.8081 | 0.9996 | 合成 ≥0.5 / 实拍 >0 |
| 裁剪率 | 0.963 | 0.981 | ≥0.85 |
| 失真值 D | 0.00675 | 0.00179 | 合成 ≤0.05 |

已知问题与待决策项见 [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md)。

## 五、常见问题排查

| 现象 | 处理 |
|---|---|
| `Could not find a version ... (from versions: none)` | 当前索引不可达：换第 4 步中的镜像源，或加 `--proxy` 走代理 |
| 安装长时间无响应 / 超时 | 追加 `--timeout 20 --retries 3`，或换镜像 |
| SSL 证书报错 | 追加 `--trusted-host <镜像域名>`（如 `--trusted-host mirrors.aliyun.com`） |
| `import cv2` 报 DLL 加载失败 | 安装 Microsoft Visual C++ 运行库：https://aka.ms/vs/17/release/vc_redist.x64.exe |
| PowerShell 激活脚本被禁止 | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| 磁盘空间 | opencv-python 轮子约 60 MB，全量依赖约 300 MB，建议预留 1 GB |

## 六、本机环境备注（仅适用于最初开发机；克隆到其他机器请忽略本节）

- 开发机 CMD / PowerShell 中 `python` 解析到 msys2 的 Python 3.12.11，用它执行 `python -m venv` 会生成 `bin/` 布局且**没有 activate.bat**（CMD 无法激活）。该机上建 venv 需使用完整路径：`C:/Users/v/.workbuddy/binaries/python/versions/3.13.12/python.exe -m venv .venv`（CPython 3.13，标准 Scripts/ 布局）。
- 开发机代理端口为 7897；该机网络实测：阿里云镜像可用，清华镜像与官方源不可用。
- 开发机已实装验证：numpy 2.5.3 / opencv-python 5.0.0.93 / matplotlib 3.11.2 / pytest 9.1.1（2026-09-24，阿里云镜像）。
