"""pass 2 代价剖析（P2/C：为「跳过纯诊断 warp」的收益提供实测依据）。

问题（KNOWN_ISSUES #17）：pass 2 每帧做 **两次独立几何重采样**
  ① 诊断：`warp.warp_frame(frame, B_t)`（未裁剪 warp，仅用于掩膜 ITF 辅助口径）；
  ② 成片：`crop.warp_crop_resize(frame, B_t, rect, w, h)`（补偿+裁剪+缩放复合单次重采样）。
`main.py --no-diagnostic` 跳过 ①；本工具量化 ① 占 pass 2 的比例。

测量口径（与 tools/bench_ds.py 一致）：`time.perf_counter`、预热 3 轮、重复取中位、固定种子。
B_list 由合成器真值 M_t 累积得到（真实轨迹分布，非恒等矩阵）。

输出：终端表格 + `docs/profile_pass2.json`；`--md` 追加 markdown 表到指定文件（便于并入 RESULTS.md）。

用法：
  python tools/profile_pipeline.py                          # 默认 960x540、64 帧
  python tools/profile_pipeline.py --frames 20 --width 640 --height 360
  python tools/profile_pipeline.py --input data/synthetic/ground_truth.json \
      --json docs/profile_pass2.json --md docs/RESULTS.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src import crop, warp  # noqa: E402

WARMUP = 3
REPEAT = 5
SEED = 42

# 实测（test1.mp4, 1280x976, v2.5）：pass2 ≈ 1055 s / 1440 帧；此处用文档值估算总收益
DOC_TEST1_FRAMES = 1440
DOC_TEST1_PASS2_SEC = 1055.0


def _bench(fn, *args) -> float:
    for _ in range(WARMUP):
        fn(*args)
    ts = []
    for _ in range(REPEAT):
        t0 = time.perf_counter()
        fn(*args)
        ts.append(time.perf_counter() - t0)
    return float(np.median(ts))


def _load_ground_truth(path: str, n_want: int, height: int, width: int) -> list:
    """从合成器真值 JSON 取前 n_want 个 M_t，累积为 B_list（恒等平滑 → B_t = I 除外）。

    若文件缺失 / 格式不符（本沙箱无合成视频时），退化为可控随机相似变换序列。
    """
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
        keys = ("M_list", "M", "mats", "matrices")
        raw = next((data[k] for k in keys if k in data), None)
        if raw:
            Ms = [np.asarray(m, dtype=np.float64) for m in raw[:n_want]]
            B = []
            C = np.eye(3)
            for M in Ms:
                C = M @ C
                B.append(C)  # 简化：以累积轨迹直接当作 B_t（只为产生真实量级的变换）
            return B
    except Exception:
        pass

    rng = np.random.default_rng(SEED)
    B = []
    for _ in range(n_want):
        th = rng.normal(0, 0.01)
        s = float(np.exp(rng.normal(0, 0.002)))
        c, sn = np.cos(th) * s, np.sin(th) * s
        M = np.array([[c, -sn, rng.normal(0, 8.0)],
                      [sn, c, rng.normal(0, 8.0)],
                      [0.0, 0.0, 1.0]])
        B.append(M)
    return B


def main() -> int:
    ap = argparse.ArgumentParser(description="pass 2 代价剖析（诊断 warp 占比）")
    ap.add_argument("--width", type=int, default=960)
    ap.add_argument("--height", type=int, default=540)
    ap.add_argument("--frames", type=int, default=64)
    ap.add_argument("--input", default=os.path.join("data", "synthetic", "ground_truth.json"),
                    help="合成真值 JSON（缺失则用可控随机相似变换序列）")
    ap.add_argument("--json", default=os.path.join("docs", "profile_pass2.json"))
    ap.add_argument("--md", help="把结果表追加到该 markdown 文件（如 docs/RESULTS.md）")
    args = ap.parse_args()

    w, h = args.width, args.height
    rng = np.random.default_rng(SEED)
    frame = rng.integers(0, 256, size=(h, w, 3), dtype=np.uint8)  # 结构化纹理非必需，代价与内容无关

    B_list = _load_ground_truth(args.input, args.frames, h, w)
    n = min(len(B_list), args.frames)
    rect = crop.compute_crop_rect(B_list[:n], w, h)

    t_warp = _bench(lambda: [warp.warp_frame(frame, B_list[i]) for i in range(n)])
    t_crop = _bench(lambda: [crop.warp_crop_resize(frame, B_list[i], rect, w, h) for i in range(n)])
    t_both = _bench(lambda: [(warp.warp_frame(frame, B_list[i]),
                              crop.warp_crop_resize(frame, B_list[i], rect, w, h)) for i in range(n)])

    per_warp_ms = t_warp / n * 1e3
    per_crop_ms = t_crop / n * 1e3
    per_both_ms = t_both / n * 1e3
    diag_share = t_warp / t_both * 100.0 if t_both > 0 else 0.0

    est_saved_sec = DOC_TEST1_PASS2_SEC * (t_warp / t_both) if t_both > 0 else 0.0

    print("=" * 78)
    print(f"pass 2 代价剖析 —— {w}x{h}，{n} 帧，预热 {WARMUP} 轮 / 取 {REPEAT} 次中位")
    print("=" * 78)
    print(f"分辨率 / 帧数           : {w}x{h} / {n}")
    print(f"诊断 warp 单帧           : {per_warp_ms:8.2f} ms")
    print(f"成片复合重采样单帧       : {per_crop_ms:8.2f} ms")
    print(f"两者合计单帧（现状）     : {per_both_ms:8.2f} ms")
    print(f"诊断 warp 占两次重采样   : {diag_share:8.2f} %")
    print("-" * 78)
    print("说明：--no-diagnostic 省掉「诊断 warp + 掩膜 PSNR」，")
    print(f"      其可省时间 ≈ 两次重采样耗时的 {diag_share:.1f}%（掩膜 PSNR 另计）。")
    print(f"      按 docs/RESULTS.md 记录 test1 pass2 ≈ {DOC_TEST1_PASS2_SEC:.0f} s / "
          f"{DOC_TEST1_FRAMES} 帧估算，预计可省 ≈ {est_saved_sec:.0f} s "
          f"（{t_warp / t_both * 100:.1f}% 的 pass2）。")
    print("      注意：整条 pass2 还含读帧/写盘/warp 之外的其它开销，故端到端收益低于该比例；")
    print("            真实数值须用 tools/transfer_check.ps1 或 main.py 计时对比取得。")
    print("=" * 78)

    result = {
        "width": w, "height": h, "frames": n,
        "warmup": WARMUP, "repeat": REPEAT, "seed": SEED,
        "per_frame_ms": {"diagnostic_warp": per_warp_ms, "crop_resample": per_crop_ms,
                         "both": per_both_ms},
        "diagnostic_share_of_two_resamples_pct": diag_share,
        "estimate_test1": {"pass2_sec_doc": DOC_TEST1_PASS2_SEC, "frames_doc": DOC_TEST1_FRAMES,
                           "saved_sec_est": est_saved_sec},
    }
    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"JSON -> {args.json}")

    if args.md:
        table = (
            "\n### pass 2 诊断 warp 代价（tools/profile_pipeline.py 实测）\n\n"
            f"> 环境：{w}x{h}，{n} 帧，预热 {WARMUP} 轮 / {REPEAT} 次取中位，种子 {SEED}。\n\n"
            "| 项 | 单帧耗时 | 占两次重采样 |\n|---|---|---|\n"
            f"| 诊断 warp（`warp.warp_frame`） | {per_warp_ms:.2f} ms | {diag_share:.1f}% |\n"
            f"| 成片复合重采样（`warp_crop_resize`） | {per_crop_ms:.2f} ms | {100 - diag_share:.1f}% |\n"
            f"| 合计（现状 pass 2 每帧） | {per_both_ms:.2f} ms | 100% |\n\n"
            f"→ `--no-diagnostic` 可省约 **{diag_share:.1f}%** 的几何重采样时间；"
            f"按 test1（1440 帧、pass2 ≈ {DOC_TEST1_PASS2_SEC:.0f} s）估算 ≈ {est_saved_sec:.0f} s。\n"
        )
        with open(args.md, "a", encoding="utf-8") as f:
            f.write(table)
        print(f"markdown 表已追加 -> {args.md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
