"""手写二叉堆（AGENTS.md 红线 7）：一维数组 + 上浮/下沉。

功能：最小堆 / 最大堆，支持 push / pop / peek / len。
实现要点：完全二叉树存于一维数组，父节点 (i-1)//2，子节点 2i+1 与 2i+2；
         push 末位追加后上浮，pop 摘根后以末元素补位并下沉。
复杂度：push / pop O(log k)，peek O(1)，空间 O(k)。
替代方案：heapq——红线 7 禁止用于主实现（仅允许测试对照）；朴素方案每次全排序
         O(k log k)。
选型理由：滑窗中值滤波的双堆结构要求每帧 O(log k) 更新；手写上浮/下沉是课程
         核心得分点，实测对比见 docs/data_structures.md。
"""

from __future__ import annotations


class BinaryHeap:
    """二叉堆。max_heap=False 为最小堆，True 为最大堆。"""

    __slots__ = ("_a", "_is_max")

    def __init__(self, max_heap: bool = False):
        self._a: list = []
        self._is_max = max_heap

    def _prior(self, x, y) -> bool:
        """x 是否应排在 y 之前（优先级更高）。"""
        return x > y if self._is_max else x < y

    def __len__(self) -> int:
        return len(self._a)

    def peek(self):
        if not self._a:
            raise IndexError("peek from empty BinaryHeap")
        return self._a[0]

    def push(self, x) -> None:
        self._a.append(x)
        self._sift_up(len(self._a) - 1)

    def pop(self):
        if not self._a:
            raise IndexError("pop from empty BinaryHeap")
        root = self._a[0]
        last = self._a.pop()
        if self._a:
            self._a[0] = last
            self._sift_down(0)
        return root

    def _sift_up(self, i: int) -> None:
        a = self._a
        while i > 0:
            p = (i - 1) // 2
            if self._prior(a[i], a[p]):
                a[i], a[p] = a[p], a[i]
                i = p
            else:
                break

    def _sift_down(self, i: int) -> None:
        a = self._a
        n = len(a)
        while True:
            l, r = 2 * i + 1, 2 * i + 2
            best = i
            if l < n and self._prior(a[l], a[best]):
                best = l
            if r < n and self._prior(a[r], a[best]):
                best = r
            if best == i:
                break
            a[i], a[best] = a[best], a[i]
            i = best
