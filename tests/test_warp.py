"""warp.py 单元测试（§7 sanity check + §11 数值对照）。

§11 warp 对照：与 cv2.warpAffine 同输入同变换，排除最外 2px 边界环带后 PSNR ≥ 40 dB。
环境注意（2026-09-24 实测）：本环境 OpenCV 5.0.0 的 warpAffine 采用「输入→输出」
正向约定（内部求逆采样），与 OpenCV ≤ 4 的「输出→输入」约定相反——故对照时直接
传 M[:2]，不再取逆。
"""

import sys

import cv2
import numpy as np

sys.path.insert(0, ".")
from src.warp import warp_frame, resample


def _psnr(a: np.ndarray, b: np.ndarray) -> float:
    mse = np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2)
    if mse == 0:
        return float("inf")
    return 10 * np.log10(255.0**2 / mse)


def _texture(h=120, w=160, seed=0):
    """带结构的测试纹理（渐变+棋盘+噪声）。"""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w]
    img = (xx * 1.3 + yy * 0.7) % 256
    img[::8, :] = 255
    img[:, ::8] = 0
    img = img + rng.normal(0, 3, (h, w))
    return np.clip(img, 0, 255).astype(np.uint8)


# ---------- §7 开工 sanity check ----------

def test_identity_is_exact():
    img = _texture()
    out = warp_frame(img, np.eye(3))
    assert np.array_equal(out, img)


def test_pure_translation_moves_content_right_5px():
    img = _texture()
    M = np.array([[1.0, 0, 5], [0, 1.0, 0], [0, 0, 1.0]])
    out = warp_frame(img, M)
    assert np.array_equal(out[:, 5:], img[:, :-5])  # 内容右移 5px
    assert np.all(out[:, :5] == 0)  # 左侧越界填 0


def test_translation_negative_and_vertical():
    img = _texture()
    M = np.array([[1.0, 0, -3], [0, 1.0, 4], [0, 0, 1.0]])
    out = warp_frame(img, M)
    assert np.array_equal(out[4:, :-3], img[:-4, 3:])


def test_oob_filled_zero():
    img = np.full((50, 60), 200, np.uint8)
    M = np.array([[1.0, 0, 50], [0, 1.0, 0], [0, 0, 1.0]])  # 大部分移出画面
    out = warp_frame(img, M)
    assert np.all(out[:, :50] == 0)
    assert np.all(out[:, 50:] == 200)


# ---------- §11 与 cv2.warpAffine 数值对照 ----------

def test_compare_cv2_random_similarity_psnr():
    rng = np.random.default_rng(42)
    img = _texture(200, 300)
    psnrs = []
    for _ in range(20):
        ang = np.deg2rad(rng.uniform(-3, 3))
        s = rng.uniform(0.95, 1.05)
        tx, ty = rng.uniform(-25, 25, 2)
        c, sn = np.cos(ang) * s, np.sin(ang) * s
        M = np.array([[c, -sn, tx], [sn, c, ty], [0, 0, 1.0]])
        mine = warp_frame(img, M)
        ref = cv2.warpAffine(img, M[:2].copy(), (img.shape[1], img.shape[0]))
        # 排除最外 2px 边界环带后比较
        psnrs.append(_psnr(mine[2:-2, 2:-2], ref[2:-2, 2:-2]))
    assert min(psnrs) >= 40.0, f"PSNR 过低: {min(psnrs):.2f} dB"


def test_color_image_support():
    img = np.dstack([_texture(seed=1), _texture(seed=2), _texture(seed=3)])
    ang = np.deg2rad(2.0)
    s = 1.02
    M = np.array([[s * np.cos(ang), -s * np.sin(ang), 7],
                  [s * np.sin(ang), s * np.cos(ang), -4], [0, 0, 1.0]])
    mine = warp_frame(img, M)
    ref = cv2.warpAffine(img, M[:2].copy(), (img.shape[1], img.shape[0]))
    assert _psnr(mine[2:-2, 2:-2], ref[2:-2, 2:-2]) >= 40.0


def test_resample_output_resize_matches_cv2():
    """crop 复用路径：缩放矩阵重采样（对照 cv2.resize 语义的 warp 实现）。"""
    img = _texture(100, 140)
    # 与 cv2.resize 的像素中心对齐约定一致：src = (dst + 0.5) * (in/out) - 0.5
    scx, scy = 140 / 90.0, 100 / 70.0
    Minv = np.array([[scx, 0, 0.5 * scx - 0.5], [0, scy, 0.5 * scy - 0.5], [0, 0, 1.0]])
    mine = resample(img, Minv, 90, 70)
    ref = cv2.resize(img, (90, 70), interpolation=cv2.INTER_LINEAR)
    assert _psnr(mine[2:-2, 2:-2], ref[2:-2, 2:-2]) >= 40.0
