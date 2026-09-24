"""tracking.py 单元测试（§11）：合成位移场 EPE < 0.3 px；可选与 cv2 对照中位差异 < 0.5 px。"""

import sys

import cv2
import numpy as np

sys.path.insert(0, ".")
from src.tracking import track_points
from src.warp import warp_frame


def make_texture(h: int = 220, w: int = 260, seed: int = 0) -> np.ndarray:
    """平滑低频纹理（正弦叠加）：保证亚像素插值精度，适合考查 LK 收敛。"""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    img = 128.0
    for _ in range(6):
        fx = rng.uniform(0.01, 0.05)
        fy = rng.uniform(0.01, 0.05)
        ph = rng.uniform(0, 2 * np.pi)
        img += 30.0 * np.sin(2 * np.pi * (fx * xx + fy * yy) + ph)
    return np.clip(img, 0, 255).astype(np.uint8)


def grid_points(h: int, w: int, margin: int = 20, step: int = 25) -> np.ndarray:
    ys = np.arange(margin, h - margin, step)
    xs = np.arange(margin, w - margin, step)
    gy, gx = np.meshgrid(ys, xs, indexing="ij")
    return np.stack([gx.ravel(), gy.ravel()], axis=1).astype(np.float32)


def shift_image(img: np.ndarray, dx: float, dy: float) -> np.ndarray:
    """用自研 warp 施加纯平移：内容位移 (dx, dy)。"""
    M = np.array([[1.0, 0.0, dx], [0.0, 1.0, dy], [0.0, 0.0, 1.0]])
    return warp_frame(img, M)


def epe(new_pts: np.ndarray, status: np.ndarray, pts: np.ndarray,
        dx: float, dy: float) -> tuple[float, float]:
    """返回 (EPE, 跟踪成功比例)。"""
    gt = pts.astype(np.float64) + np.array([dx, dy])
    err = np.linalg.norm(new_pts[status].astype(np.float64) - gt[status], axis=1)
    return float(np.mean(err)), float(status.mean())


def test_tracking_epe_small_displacement():
    img = make_texture(seed=0)
    dx, dy = 1.7, -2.3
    img2 = shift_image(img, dx, dy)
    pts = grid_points(*img.shape[:2])
    new, st = track_points(img, img2, pts, win=15)
    err, ratio = epe(new, st, pts, dx, dy)
    print(f"\nEPE={err:.4f} px | 跟踪成功比例={ratio:.3f}")
    assert ratio >= 0.95, f"跟踪成功率 {ratio:.3f} 过低"
    assert err < 0.3, f"EPE {err:.4f} ≥ 0.3 px"


def test_tracking_epe_multiple_displacements():
    img = make_texture(seed=1)
    pts = grid_points(*img.shape[:2])
    for dx, dy in [(0.5, 0.5), (2.0, 1.0), (-1.5, 2.5), (3.0, -3.0)]:
        img2 = shift_image(img, dx, dy)
        new, st = track_points(img, img2, pts, win=15)
        err, ratio = epe(new, st, pts, dx, dy)
        print(f"  位移({dx},{dy}): EPE={err:.4f}, 成功率={ratio:.3f}")
        assert ratio >= 0.95, f"位移({dx},{dy}) 成功率 {ratio:.3f}"
        assert err < 0.3, f"位移({dx},{dy}) EPE {err:.4f} ≥ 0.3"


def test_tracking_vs_cv2_median_diff():
    """可选对照（§11）：与 cv2.calcOpticalFlowPyrLK 的中位差异 < 0.5 px。"""
    img = make_texture(seed=2)
    dx, dy = 1.7, -2.3
    img2 = shift_image(img, dx, dy)
    pts = grid_points(*img.shape[:2])
    mine, st = track_points(img, img2, pts, win=15)
    ref, r_st, _ = cv2.calcOpticalFlowPyrLK(img, img2, pts.reshape(-1, 1, 2),
                                            None, winSize=(15, 15))
    ref = ref.reshape(-1, 2)
    both = st & r_st.reshape(-1).astype(bool)
    diff = np.linalg.norm(mine[both].astype(np.float64) - ref[both], axis=1)
    med = float(np.median(diff))
    print(f"\n与 cv2 中位差异={med:.4f} px（对照样本 {both.sum()}）")
    assert med < 0.5, f"与 cv2 中位差异 {med:.4f} ≥ 0.5 px"


def test_empty_points():
    img = make_texture()
    new, st = track_points(img, img, np.empty((0, 2), np.float32))
    assert len(new) == 0 and len(st) == 0
