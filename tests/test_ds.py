"""ds/ 手写数据结构单元测试。

红线 7：collections.deque / heapq / sorted 仅允许在本测试文件中作对照基准。
"""

import collections
import heapq
import random
import sys

import pytest

sys.path.insert(0, ".")
from ds.ring_buffer import RingBuffer
from ds.heap import BinaryHeap


# ---------------- RingBuffer ----------------

def test_ring_buffer_capacity_must_be_positive():
    with pytest.raises(ValueError):
        RingBuffer(0)


def test_ring_buffer_fifo_and_eviction():
    rb = RingBuffer(3)
    assert rb.push(1) is None
    assert rb.push(2) is None
    assert rb.push(3) is None
    assert rb.is_full()
    # 写满后 push 驱逐最旧
    assert rb.push(4) == 1
    assert rb.push(5) == 2
    assert rb.to_list() == [3, 4, 5]
    assert rb.oldest() == 3
    assert rb.newest() == 5
    assert len(rb) == 3


def test_ring_buffer_popleft_and_getitem():
    rb = RingBuffer(4)
    for v in [10, 20, 30]:
        rb.push(v)
    assert rb.popleft() == 10
    assert rb[0] == 20
    assert rb[-1] == 30
    with pytest.raises(IndexError):
        _ = rb[2]
    rb.clear()
    assert len(rb) == 0
    with pytest.raises(IndexError):
        rb.popleft()


def test_ring_buffer_random_ops_match_deque():
    """随机操作序列下与 collections.deque(maxlen) 逐值一致（对照基准）。"""
    rng = random.Random(42)
    cap = 7
    rb = RingBuffer(cap)
    dq = collections.deque(maxlen=cap)
    for _ in range(2000):
        if rng.random() < 0.6:
            v = rng.randint(-100, 100)
            rb.push(v)
            dq.append(v)
        elif len(dq) > 0:
            assert rb.popleft() == dq.popleft()
        assert rb.to_list() == list(dq)


# ---------------- BinaryHeap ----------------

def test_heap_empty_errors():
    h = BinaryHeap()
    with pytest.raises(IndexError):
        h.peek()
    with pytest.raises(IndexError):
        h.pop()


def test_min_heap_pop_order_is_sorted():
    rng = random.Random(0)
    data = [rng.randint(-1000, 1000) for _ in range(500)]
    h = BinaryHeap()
    for v in data:
        h.push(v)
    out = [h.pop() for _ in range(len(data))]
    assert out == sorted(data)


def test_max_heap_pop_order_is_reverse_sorted():
    rng = random.Random(1)
    data = [rng.uniform(-10, 10) for _ in range(300)]
    h = BinaryHeap(max_heap=True)
    for v in data:
        h.push(v)
    out = [h.pop() for _ in range(len(data))]
    assert out == sorted(data, reverse=True)


def test_heap_random_ops_match_heapq():
    """随机 push/pop 与 heapq 对照一致。"""
    rng = random.Random(7)
    mine = BinaryHeap()
    ref = []
    for _ in range(3000):
        if rng.random() < 0.55 or len(ref) == 0:
            v = rng.randint(-500, 500)
            mine.push(v)
            heapq.heappush(ref, v)
        else:
            assert mine.pop() == heapq.heappop(ref)
        assert mine.peek() == ref[0]
        assert len(mine) == len(ref)
