"""定长数组环形缓冲（手写实现，AGENTS.md 红线 7）。

功能：容量固定的先进先出缓冲；写满后自动驱逐最旧元素（滑动窗口语义）。
实现要点：预分配定长列表 + 头指针 + 元素计数；写位置由 (head + count) % capacity
         推出，全程不移动任何已有元素。
复杂度：push / popleft / 按下标随机访问 均 O(1)，空间 O(k)（k = 容量）。
替代方案：collections.deque(maxlen=k)——红线 7 禁止用于主实现（仅允许测试对照）；
         朴素 list.pop(0) 头部删除为 O(k)。
选型理由：平滑器滑窗每帧一入一驱逐，要求 O(1) 更新；环形缓冲是教科书标准结构，
         也是 docs/data_structures.md 的实测对比对象（vs list.pop(0)）。
"""

from __future__ import annotations


class RingBuffer:
    """定长环形缓冲。下标语义：0 = 最旧元素，len-1 = 最新元素。"""

    __slots__ = ("_buf", "_cap", "_head", "_count")

    def __init__(self, capacity: int):
        if capacity <= 0:
            raise ValueError("capacity 必须为正整数")
        self._buf = [None] * capacity  # 定长数组（预分配，不再扩容）
        self._cap = capacity
        self._head = 0   # 最旧元素下标
        self._count = 0  # 当前元素个数

    @property
    def capacity(self) -> int:
        return self._cap

    def __len__(self) -> int:
        return self._count

    def is_full(self) -> bool:
        return self._count == self._cap

    def push(self, x):
        """追加元素。若已满则驱逐最旧元素并返回它，否则返回 None。O(1)。"""
        if self._count == self._cap:
            evicted = self._buf[self._head]
            self._buf[self._head] = x
            self._head = (self._head + 1) % self._cap
            return evicted
        self._buf[(self._head + self._count) % self._cap] = x
        self._count += 1
        return None

    def popleft(self):
        """弹出最旧元素。O(1)。空缓冲抛 IndexError。"""
        if self._count == 0:
            raise IndexError("popleft from empty RingBuffer")
        v = self._buf[self._head]
        self._buf[self._head] = None
        self._head = (self._head + 1) % self._cap
        self._count -= 1
        return v

    def oldest(self):
        if self._count == 0:
            raise IndexError("oldest from empty RingBuffer")
        return self._buf[self._head]

    def newest(self):
        if self._count == 0:
            raise IndexError("newest from empty RingBuffer")
        return self._buf[(self._head + self._count - 1) % self._cap]

    def __getitem__(self, i: int):
        if i < 0:
            i += self._count
        if i < 0 or i >= self._count:
            raise IndexError("RingBuffer index out of range")
        return self._buf[(self._head + i) % self._cap]

    def __iter__(self):
        for i in range(self._count):
            yield self._buf[(self._head + i) % self._cap]

    def to_list(self) -> list:
        return list(iter(self))

    def clear(self) -> None:
        self._buf = [None] * self._cap
        self._head = 0
        self._count = 0
