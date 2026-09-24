"""轨迹平滑器（AGENTS.md §6 口径定稿 + §8.4）。

全文唯一平滑口径：**居中（非因果）**，输出延迟 r = window//2 帧。
- `update(x_t)`：输入第 t 个值（0-based），返回 y_{t-r}；t < r 时返回 None（延迟期）。
- `flush()`：序列结束后调用一次，返回尾部 r 个值。update + flush 输出总数恰为 N。
- 边界规则 = 部分窗口重归一：头/尾部分窗口内，移动平均与高斯核权重在可得元素上
  重新归一；中值在可得元素上取，元素为偶数个时取两中位数的均值（仅出现于部分窗口，
  完整窗口恒为奇数）。
- 窗口为偶数时自动 +1 并记录日志。

数据结构（§10，红线 7 手写实现）：
- 移动平均：ds.RingBuffer 环形缓冲 + 增量维护窗口和，单帧更新 O(1)。
- 高斯平滑：手写高斯核（σ = window/6 或显式参数），滑窗点积，每帧 O(k)。
- 中值滤波：ds.BinaryHeap 双堆（最大堆 + 最小堆）+ 哈希表延迟删除，更新 O(log k)。
"""

from __future__ import annotations

import logging

import numpy as np

from ds.heap import BinaryHeap
from ds.ring_buffer import RingBuffer

logger = logging.getLogger(__name__)


class _BaseSmoother:
    """居中滑窗平滑器基类：缓冲管理 + update/flush 时序，子类实现具体核计算。"""

    def __init__(self, window: int):
        if window <= 0:
            raise ValueError("window 必须为正整数")
        if window % 2 == 0:
            window += 1
            logger.info("平滑窗口为偶数，自动 +1 → %d", window)
        self.window = window
        self.r = window // 2
        self._buf = RingBuffer(window)
        self._start = 0   # buffer 最旧元素的绝对下标
        self._t = -1      # 最后输入值的绝对下标
        self._emitted = 0  # 已输出位置数

    # ---- 子类钩子 ----
    def _on_push(self, x: float, evicted) -> None:
        pass

    def _on_evict(self, v: float) -> None:
        pass

    def _value(self, i: int) -> float:
        """用当前 buffer（已对齐到位置 i 的窗口）计算 y_i。"""
        raise NotImplementedError

    # ---- 统一时序 ----
    def update(self, x: float):
        self._t += 1
        evicted = self._buf.push(x)
        if evicted is not None:
            self._start += 1
        self._on_push(x, evicted)
        if self._t < self.r:
            return None
        self._emitted += 1
        return self._value(self._t - self.r)

    def flush(self) -> list[float]:
        n = self._t + 1
        out = []
        for i in range(self._emitted, n):
            # 位置 i 的窗口左端为 max(0, i-r)，驱逐绝对下标小于它的元素
            while self._start < i - self.r:
                v = self._buf.popleft()
                self._start += 1
                self._on_evict(v)
            out.append(self._value(i))
        self._emitted = n
        return out


class MovingAverageSmoother(_BaseSmoother):
    """移动平均：环形缓冲 + 增量窗口和，单帧 O(1)（vs 朴素每次重算 O(k)）。"""

    def __init__(self, window: int):
        super().__init__(window)
        self._sum = 0.0

    def _on_push(self, x: float, evicted) -> None:
        self._sum += x - (evicted if evicted is not None else 0.0)

    def _on_evict(self, v: float) -> None:
        self._sum -= v

    def _value(self, i: int) -> float:
        return self._sum / len(self._buf)


class GaussianSmoother(_BaseSmoother):
    """高斯平滑：手写高斯核（σ = window/6 或显式参数），滑窗点积，每帧 O(k)。"""

    def __init__(self, window: int, sigma: float | None = None):
        super().__init__(window)
        self.sigma = sigma if sigma is not None else self.window / 6.0
        x = np.arange(self.window, dtype=np.float64) - self.r
        k = np.exp(-0.5 * (x / self.sigma) ** 2)
        self._kernel = k / k.sum()

    def _value(self, i: int) -> float:
        vals = np.asarray(self._buf.to_list(), dtype=np.float64)
        # buffer 最旧元素的核下标 = 其绝对下标 - 窗口左端（部分窗口时 > 0）
        offset = self._start - (i - self.r)
        w = self._kernel[offset:offset + len(vals)]
        w = w / w.sum()  # 部分窗口重归一
        return float(vals @ w)


class MedianSmoother(_BaseSmoother):
    """中值滤波：手写双堆（最大堆 lo + 最小堆 hi）+ 哈希表延迟删除。

    不变量：sz_lo == sz_hi（总数偶，取两堆顶均值）或 sz_lo == sz_hi + 1（总数奇，
    取 lo 堆顶）。被驱逐元素记入 _deleted 延迟删除，升至堆顶时才物理移除。
    """

    def __init__(self, window: int):
        super().__init__(window)
        self._lo = BinaryHeap(max_heap=True)
        self._hi = BinaryHeap(max_heap=False)
        self._sz_lo = 0
        self._sz_hi = 0
        self._deleted: dict[float, int] = {}

    # ---- 双堆维护 ----
    def _prune(self, heap: BinaryHeap) -> None:
        while len(heap) > 0:
            top = heap.peek()
            c = self._deleted.get(top, 0)
            if c == 0:
                break
            heap.pop()
            if c == 1:
                del self._deleted[top]
            else:
                self._deleted[top] = c - 1

    def _rebalance(self) -> None:
        if self._sz_lo > self._sz_hi + 1:
            self._prune(self._lo)
            v = self._lo.pop()
            self._hi.push(v)
            self._sz_lo -= 1
            self._sz_hi += 1
        elif self._sz_hi > self._sz_lo:
            self._prune(self._hi)
            v = self._hi.pop()
            self._lo.push(v)
            self._sz_hi -= 1
            self._sz_lo += 1

    def _insert(self, x: float) -> None:
        if self._sz_lo > 0 and x > self._lo.peek():
            self._hi.push(x)
            self._sz_hi += 1
        else:
            self._lo.push(x)
            self._sz_lo += 1
        self._rebalance()

    def _delete(self, x: float) -> None:
        # 顺序关键（延迟删除的正确性全在这里）：
        # 1) 先清理两堆脏顶——此时 x 尚未被标记，不会被误删；
        # 2) 再标记 x 删除并按「干净堆顶」分类（若 x 就在堆顶，x <= x 恒成立，必分对）；
        # 3) 若 x 正在堆顶则当即 prune；否则留待其升至堆顶时再物理移除。
        self._prune(self._lo)
        self._prune(self._hi)
        self._deleted[x] = self._deleted.get(x, 0) + 1
        if self._sz_lo > 0 and len(self._lo) > 0 and x <= self._lo.peek():
            self._sz_lo -= 1
            if x == self._lo.peek():
                self._prune(self._lo)
        else:
            self._sz_hi -= 1
            if self._sz_hi > 0 and len(self._hi) > 0 and x == self._hi.peek():
                self._prune(self._hi)
        self._rebalance()

    # ---- 钩子 ----
    def _on_push(self, x: float, evicted) -> None:
        self._insert(x)
        if evicted is not None:
            self._delete(evicted)

    def _on_evict(self, v: float) -> None:
        self._delete(v)

    def _value(self, i: int) -> float:
        # 防御性清理：任何路径到达这里时两堆顶都应是干净的
        self._prune(self._lo)
        self._prune(self._hi)
        if self._sz_lo > self._sz_hi:
            return self._lo.peek()
        return (self._lo.peek() + self._hi.peek()) / 2.0


SMOOTHERS = {
    "ma": MovingAverageSmoother,
    "gauss": GaussianSmoother,
    "median": MedianSmoother,
}


def create_smoother(name: str, window: int) -> _BaseSmoother:
    if name not in SMOOTHERS:
        raise ValueError(f"未知平滑器: {name}（可选 {list(SMOOTHERS)}）")
    return SMOOTHERS[name](window)
