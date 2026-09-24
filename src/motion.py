"""运动估计（AGENTS.md 红线 1）：自研 RANSAC + 相似变换求解器。

- 最小求解器：2 组点对应（复数法 z' = a·z + b，|a| 为尺度、arg(a) 为旋转）；
  样本退化检验：两点间距 < 2 px 判退化，弃样重采（§8.3）。
- RANSAC 自适应迭代次数：k = ln(1-conf) / ln(1-w^n)，w 为当前内点率、n = 2；
  w^n ≥ 1 时取 k = 1，分母为 0 时设上限 1000。
- 内点判据：二维欧氏距离 ||p̂ - p|| < thresh（默认 2.5 px，§8.3 定稿）。
- 全部内点上用最小二乘重新拟合（复数闭式解，等效 Umeyama 去反射：
  解空间为 a ∈ ℂ，天然不含反射分量）。
- 返回 (3x3 齐次矩阵, 内点掩码)；掩码按「重拟合后的最终模型」判定。
模型求解允许使用 NumPy 基础线性代数（§6 红线 6）。
"""

from __future__ import annotations

import math

import numpy as np

DEGENERATE_DIST = 2.0  # 最小样本两点间距下限（px）
MAX_ITERS = 1000


def _to_complex(pts: np.ndarray) -> np.ndarray:
    return pts[:, 0] + 1j * pts[:, 1]


def _forward(a: complex, t: complex, pts: np.ndarray) -> np.ndarray:
    w = a * _to_complex(pts) + t
    return np.stack([w.real, w.imag], axis=1)


def solve_similarity_2pts(src: np.ndarray, dst: np.ndarray):
    """2 点对应求相似变换（复数法）。退化（间距 < 2 px）返回 None。"""
    z = _to_complex(np.asarray(src, dtype=np.float64))
    w = _to_complex(np.asarray(dst, dtype=np.float64))
    dz = z[1] - z[0]
    if abs(dz) < DEGENERATE_DIST:
        return None
    a = (w[1] - w[0]) / dz
    t = w[0] - a * z[0]
    return a, t


def umeyama_similarity(src: np.ndarray, dst: np.ndarray):
    """相似变换最小二乘闭式解（去反射）。返回 (a, t)，p̂ = a·p + t。"""
    z = _to_complex(np.asarray(src, dtype=np.float64))
    w = _to_complex(np.asarray(dst, dtype=np.float64))
    zc = z - z.mean()
    wc = w - w.mean()
    denom = np.sum(np.abs(zc) ** 2)
    if denom < 1e-12:  # 源点全部重合：退化为纯平移
        return 1.0 + 0.0j, complex(w.mean() - z.mean())
    a = np.sum(wc * np.conj(zc)) / denom
    t = w.mean() - a * z.mean()
    return complex(a), complex(t)


def compose_matrix(a: complex, t: complex) -> np.ndarray:
    """(a, t) → 3x3 齐次相似变换矩阵。"""
    return np.array([
        [a.real, -a.imag, t.real],
        [a.imag, a.real, t.imag],
        [0.0, 0.0, 1.0],
    ])


def estimate_similarity_ransac(src_pts, dst_pts, thresh: float = 2.5,
                               conf: float = 0.99, rng: np.random.Generator | None = None):
    """RANSAC 估计相似变换。返回 (M 3x3, inlier_mask)；n < 2 时返回 (None, 全 False)。"""
    src = np.asarray(src_pts, dtype=np.float64)
    dst = np.asarray(dst_pts, dtype=np.float64)
    n = len(src)
    if n < 2:
        return None, np.zeros(n, dtype=bool)
    if rng is None:
        rng = np.random.default_rng()

    best_mask = np.zeros(n, dtype=bool)
    best_model = (1.0 + 0.0j, 0.0 + 0.0j)
    it = 0
    max_it = MAX_ITERS
    while it < max_it:
        it += 1
        i, j = rng.choice(n, 2, replace=False)
        sol = solve_similarity_2pts(src[[i, j]], dst[[i, j]])
        if sol is None:
            continue  # 退化样本，弃样重采
        a, t = sol
        inl = np.linalg.norm(_forward(a, t, src) - dst, axis=1) < thresh
        if inl.sum() > best_mask.sum():
            best_mask = inl
            best_model = (a, t)
            w = inl.mean()
            if w * w >= 1.0:
                max_it = it  # k = 1，本轮后即可停
            else:
                k = math.log(1.0 - conf) / math.log(1.0 - w * w)
                max_it = min(MAX_ITERS, max(it, int(math.ceil(k))))

    # 全部内点上最小二乘重拟合（去反射）
    if best_mask.sum() >= 2:
        a, t = umeyama_similarity(src[best_mask], dst[best_mask])
    else:
        a, t = best_model
    # 按最终模型重判内点（验收口径：召回以最终判定为准）
    final_mask = np.linalg.norm(_forward(a, t, src) - dst, axis=1) < thresh
    return compose_matrix(a, t), final_mask
