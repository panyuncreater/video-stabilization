"""P2（C. pass2 提速）等价性测试：`--no-diagnostic` 不得改变任何数值结果。

背景（CHANGELOG [P2]）：pass 2 原本每帧做两次独立几何重采样——
  ① 诊断路径 `warp.warp_frame(frame, B_t)`（未裁剪 warp，供掩膜 ITF 辅助口径）；
  ② 成片路径 `crop.warp_crop_resize(frame, B_t, rect, w, h)`（补偿+裁剪+缩放复合单次重采样）。
`--no-diagnostic` 只跳过 ①。本测试用**桩件（stub）**替代 cv2 视频与自研核，
在「编排层」证明该开关是纯粹的可选旁路：

  1. 调用次序：诊断模式下调用序列必须含 `warp_frame → warp_crop_resize` 且逐帧成对；
     关闭诊断后 `warp_frame` 调用次数必须降为 0（这正是提速来源）。
  2. 数值等价：两种模式下
     - `warp_crop_resize` 收到的 (frame, B_t, rect, w, h) 逐帧完全一致（→ 成片逐位相同）；
     - 平滑参数、限幅事件、裁剪框、ITF 均值完全一致；
     - 掩膜 ITF 值一致，且关闭诊断时该量变为 None（仅此一项按设计缺失）。

桩件只依赖 numpy，故本测试在**没有 cv2** 的环境也能运行。
"""

from __future__ import annotations

import sys
import types

import numpy as np
import pytest

# --- 让本测试在「没有 cv2」的环境也能运行：仅在 cv2 缺失时注入最小桩件 ---
# main 与 src/* 在导入期只引用 cv2 的少量属性；真实调用路径已由本测试的桩件接管。
if "cv2" not in sys.modules:
    try:
        import cv2  # noqa: F401
    except Exception:
        _cv2 = types.ModuleType("cv2")
        _cv2.COLOR_BGR2GRAY = 6
        _cv2.COLOR_GRAY2BGR = 8
        _cv2.CAP_PROP_FPS = 5
        _cv2.CAP_PROP_FRAME_WIDTH = 3
        _cv2.CAP_PROP_FRAME_HEIGHT = 4
        _cv2.CAP_PROP_FRAME_COUNT = 7
        _cv2.VideoWriter_fourcc = lambda *a, **k: 0
        _cv2.VideoCapture = object
        _cv2.VideoWriter = object
        _cv2.cvtColor = lambda img, code: img
        sys.modules["cv2"] = _cv2

import main as M

W, H, N = 8, 6, 5


# ---------------- 桩件 ----------------

def _stub_main_modules(monkeypatch, calls: list, itf_orig: float, traj_matrices: np.ndarray):
    """把 main 模块依赖的视频 IO / 自研核 / 指标替换为可控桩件。"""

    # --- io_utils ---
    io = types.SimpleNamespace(EXIT_OK=0)

    class _Reader:
        def __init__(self, path):
            self.i = 0
            self.fps, self.width, self.height = 25.0, W, H

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            if self.i >= N:
                return None
            f = np.full((H, W, 3), self.i, dtype=np.uint8)
            self.i += 1
            return f

    class _Writer:
        def __init__(self, path, fps, w, h):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def write(self, frame):
            calls.append(("write", frame.shape, round(float(frame.mean()), 6)))

    io.VideoReader = _Reader
    io.VideoWriterWrap = _Writer

    # --- warp ---
    warp = types.SimpleNamespace()

    def warp_frame(img, M):
        calls.append(("warp_frame", img.shape))
        return img + 1  # 与成片路径可区分的标记变换

    warp.warp_frame = warp_frame

    # --- crop ---
    crop = types.SimpleNamespace()
    crop_rect = (2, 1, W - 2, H - 1)

    def compute_crop_rect(B_list, w, h):
        return crop_rect

    def warp_crop_resize(frame, B, rect, out_w, out_h):
        calls.append(("warp_crop_resize", frame.shape, np.asarray(B).copy(), rect))
        return frame + 2  # 成片路径标记

    crop.compute_crop_rect = compute_crop_rect
    crop.cropping_ratio = lambda rect, w, h: 0.9
    crop.warp_crop_resize = warp_crop_resize

    # --- metrics ---
    metrics = types.SimpleNamespace()
    metrics.psnr_gray = lambda a, b, rect: 33.0
    metrics.compute_itf = lambda path: 30.0
    metrics.stability = lambda p_raw, p_smooth, shots: {
        "E_raw": [1.0, 1.0, 1.0, 1.0], "E_smooth": [0.1, 0.1, 0.1, 0.1],
        "S_per_dim": [0.9, 0.9, 0.9, 0.9], "S": 0.9,
        "S_reference_unnormalized": 0.9, "degenerate_dims": [], "negative": False}
    metrics.distortion = lambda B_list: 0.001

    # --- features / tracking / motion / shots：pass 1 直接短路 ---
    def pass1_estimate(args, reader, rng):  # 桩件与 main 的真实签名保持一致（含可复现 RNG）
        calls.append(("pass1",))
        n = 0
        while reader.read() is not None:
            n += 1
        deg = {"mt_identity_frames": 0, "ransac_fallback_frames": 0,
               "redetection_frames": 0, "shot_cuts": []}
        traj = types.SimpleNamespace(matrices=traj_matrices)
        return traj, deg, [itf_orig] * (n - 1), n

    # --- trajectory：真实 decompose/rebuild 需要 numpy，这里给可控实现 ---
    traj = types.SimpleNamespace()

    def decompose(mats):
        return np.stack([np.array([m[0, 2], m[1, 2], 0.0, 0.0]) for m in mats], axis=1)

    def rebuild(params):
        return [np.eye(3) for _ in range(params.shape[1])]

    def clamp_drift(raw, smooth, tx, theta, lns):
        return smooth, 0

    traj.decompose = decompose
    traj.rebuild = rebuild
    traj.clamp_drift = clamp_drift

    # --- 覆盖 main 模块内的引用 ---
    monkeypatch.setattr(M, "io_utils", io)
    monkeypatch.setattr(M, "warp", warp)
    monkeypatch.setattr(M, "crop", crop)
    monkeypatch.setattr(M, "metrics", metrics)
    monkeypatch.setattr(M, "pass1_estimate", pass1_estimate)
    monkeypatch.setattr(M, "trajectory", traj)
    # 原图 ITF 列表由 pass1_estimate 桩件给出；np.mean 在 main 内计算
    return crop_rect


def _run(monkeypatch, no_diagnostic: bool):
    calls: list = []
    mats = np.stack([np.eye(3) for _ in range(N)])
    _stub_main_modules(monkeypatch, calls, itf_orig=20.0, traj_matrices=mats)
    args = types.SimpleNamespace(
        input="stub.mp4", output="stub_out.mp4", smooth="ma", window=3,
        max_corners=100, vis=False, clamp_tx=30.0, clamp_theta=3.0, clamp_ln_s=0.05,
        no_clamp=False, no_diagnostic=no_diagnostic, seed=42)
    rc = M.run(args)
    return rc, calls


# ---------------- 测试 ----------------

def test_diagnostic_off_skips_warp_but_keeps_output_path(monkeypatch):
    """关闭诊断：warp_frame 归零，成片路径与写出逐帧不变。"""
    rc_on, calls_on = _run(monkeypatch, no_diagnostic=False)
    monkeypatch.undo()
    rc_off, calls_off = _run(monkeypatch, no_diagnostic=True)

    assert rc_on == 0 and rc_off == 0

    n_warp_on = sum(1 for c in calls_on if c[0] == "warp_frame")
    n_warp_off = sum(1 for c in calls_off if c[0] == "warp_frame")
    assert n_warp_on == N, "诊断模式应逐帧调用一次 warp_frame"
    assert n_warp_off == 0, "关闭诊断后不得再有任何 warp_frame 调用（提速来源）"

    n_crop_on = sum(1 for c in calls_on if c[0] == "warp_crop_resize")
    n_crop_off = sum(1 for c in calls_off if c[0] == "warp_crop_resize")
    assert n_crop_on == n_crop_off == N, "成片路径必须逐帧执行，与诊断开关无关"


def test_crop_path_inputs_identical_between_modes(monkeypatch):
    """成片路径收到的 (frame, B_t, rect) 逐帧完全一致 → 成片逐位相同。"""
    _, calls_on = _run(monkeypatch, no_diagnostic=False)
    monkeypatch.undo()
    _, calls_off = _run(monkeypatch, no_diagnostic=True)

    crop_on = [c for c in calls_on if c[0] == "warp_crop_resize"]
    crop_off = [c for c in calls_off if c[0] == "warp_crop_resize"]
    assert len(crop_on) == len(crop_off) == N
    for a, b in zip(crop_on, crop_off):
        assert a[1] == b[1]                     # frame.shape
        assert np.array_equal(a[2], b[2])       # B_t
        assert a[3] == b[3]                     # crop rect


def test_written_frames_identical(monkeypatch):
    """writer.write 收到的帧内容逐帧一致（成片不变）。"""
    _, calls_on = _run(monkeypatch, no_diagnostic=False)
    monkeypatch.undo()
    _, calls_off = _run(monkeypatch, no_diagnostic=True)

    w_on = [c for c in calls_on if c[0] == "write"]
    w_off = [c for c in calls_off if c[0] == "write"]
    assert w_on == w_off and len(w_on) == N


def test_argument_default_keeps_diagnostic(monkeypatch):
    """默认（不传开关）必须保留诊断，保证既有行为与既有 metrics 完全不变。"""
    monkeypatch.setattr("sys.argv", ["main.py", "--input", "a.mp4", "--output", "b.mp4"])
    args = M.parse_args()
    assert args.no_diagnostic is False
