# 测试说明

> 对应 AGENTS.md §11（测试与数值验收基准）。运行：`python -m pytest tests/ -q`。

## 一、概览

| 文件 | 用例数 | 覆盖模块 |
|---|---|---|
| `tests/test_ds.py` | 8 | `ds/ring_buffer.py`、`ds/heap.py` |
| `tests/test_warp.py` | 7 | `src/warp.py` |
| `tests/test_smoothing.py` | 9 | `src/smoothing.py` |
| `tests/test_motion.py` | 6 | `src/motion.py` |
| `tests/test_shots.py` | 11 | `src/shots.py` |
| `tests/test_features.py` | 9 | `src/features.py` |
| `tests/test_tracking.py` | 4 | `src/tracking.py` |
| **合计** | **54** | — |

最近结果：**54 passed**（2026-09-25，M1 后）。

## 二、各文件要点

### test_ds.py（手写数据结构）

- 环形缓冲：容量校验、FIFO 与驱逐语义、`popleft` / 随机访问 / 空缓冲异常；**2000 次随机操作与 `collections.deque(maxlen)` 逐值一致**（对照基准）。
- 二叉堆：最小/最大堆弹出序列等于 `sorted` / 逆序；**3000 次随机 push/pop 与 `heapq` 对照一致**；空堆 `peek/pop` 抛 `IndexError`。

### test_warp.py（图像补偿）

- §7 sanity check：`warp_frame(img, I)` 与原图**逐像素一致**；纯平移 (+5,0) 内容右移 5 px（切面精确相等）；负向/纵向平移同理；越界填 0 校验。
- §11 对照：20 组随机相似变换与 `cv2.warpAffine(img, M[:2])` 比较，**排除最外 2 px 环带后 PSNR ≥ 40 dB**（光滑纹理实测 PSNR = inf）。
- 彩色图像路径；`resample` 缩放与 `cv2.resize` 对照（半像素中心对齐一致）。

### test_smoothing.py（轨迹平滑）

- 输出总数 = N；延迟语义（前 r 次 `update` 返回 None）。
- **与朴素遍历实现逐值一致**（相对容差 1e-9），覆盖：window=1/5/31、window > 序列长度、偶数窗口自动 +1、显式 sigma。
- 中值模块：与「排序取中值」朴素实现一致；双堆延迟删除正确性（长序列、重复值）。

### test_motion.py（RANSAC）

- §11 验收：合成点对（200 组、400×400 分布、σ=1 px 噪声、30% 外点）下**平移 <0.5 px、旋转 <0.5°、召回 ≥90%**。
- 多种子稳健性：10 组种子下旋转与召回每次达标、平移取中位达标（尾部风险见 KNOWN_ISSUES）。
- 无噪精确恢复；退化样本（间距 <2 px）拒绝；去反射（det>0）；点数不足返回 `(None, 全 False)`。

### test_shots.py（镜头切分）

- MAD：同帧为 0；连续帧（渐变图微移）低于阈值、切换帧（异场景）高于阈值。
- 判据：高 MAD + 低内点率 → 切；高 MAD + 高内点率 → 不切（甩镜）；**高 MAD + 高内点率 + 存活率崩溃 → 切**（胶片静态结构补丁）；最短镜头长度生效；阈值边界。
- 分段：边界正确、无切换、越界切换帧忽略；过短镜头合并。

### test_features.py（自研 Harris）

- §11 验收：合成角点图（白底黑方块网格，真值为方块四角像素）**检出率 ≥95%、定位误差 ≤1 px**（实测 1.000 / 0.000）。
- 组件：Sobel 平坦区为 0；盒式滤波保常数、冲激均值正确、**中心对齐**（5×5 响应块边界检查）；全平坦图响应为 0 且检测为空。
- 接口：返回 `float32`、(N,2)、`max_corners` 截断；降级重检（quality 0.005）点数不少于常规。

### test_tracking.py（自研单层 LK）

- §11 验收：合成位移场（自研 warp 施加纯平移）下 **EPE < 0.3 px**；4 组位移（0.5–3 px）均达标且跟踪成功率 ≥95%。
- 与 `cv2.calcOpticalFlowPyrLK` 对照：中位差异 <0.5 px（实测 0.0009 px）。
- 空输入返回空数组。

## 三、对照基准的豁免说明

`collections.deque`、`heapq`、`sorted`、`cv2`（warpAffine / calcOpticalFlowPyrLK / goodFeaturesToTrack / calcHist 等）**仅出现在 tests/ 与 tools/bench_ds.py 中**，用作数值对照或数据生成；主实现 `src/`、`ds/` 严格遵守红线（详见 DEVELOPMENT.md 红线自检清单）。

## 四、新增测试约定

- 每个自研模块对应一个 `tests/test_<模块>.py`。
- 与第三方实现对照时，必须在文件 docstring 注明「对照基准仅用于测试」。
- 涉及验收线的断言需写出实测数值到失败信息中（便于定位）。
- 新增阈值/常量调整须同步更新本文档与 PROJECT_STATE.md 决策日志。
