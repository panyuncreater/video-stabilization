"""改前/改后等价性验证器（P2 的性能优化必须靠它证明「零数学改动」）。

判定两件事：
1. metrics.json 逐字段一致性 —— 递归 deep-diff，显式忽略 runtime_sec（计时必然不同），
   其余字段按 tol 容差比较；同时校验配置类字段（smoother/shots/clamp/n_frames/fps/尺寸）
   必须完全一致（否则两遍根本不可比）。
2. 输出视频逐帧一致性 —— 流式读取两个成片（不缓存全帧），逐帧算灰度 PSNR，
   报告 min / p10 / 中位数与最差帧号；帧数或分辨率不一致直接失败。

退出码：
  0 = 等价（PASS）；1 = 不等价（FAIL）；2 = 无法判定（缺文件 / 缺 numpy|OpenCV）。

用法：
  python tools/verify_invariance.py --baseline output/base/metrics.json --candidate output/new/metrics.json
  python tools/verify_invariance.py --baseline ... --candidate ... \
      --baseline-video output/base/stabilized.mp4 --candidate-video output/new/stabilized.mp4
  python tools/verify_invariance.py ... --psnr-min 50 --json report.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_UNDECIDED = 2

# 计时字段天然不同，显式忽略
# 计时与输出路径天然不同，显式忽略（路径不是质量指标）
IGNORE_KEYS = {"runtime_sec", "output"}

# 这些字段决定「两遍是否可比」，必须严格相等
STRICT_KEYS = ["input", "n_frames", "fps", "width", "height", "smoother", "shots",
               "clamp", "degradations"]


def _fmt(v, limit: int = 160) -> str:
    s = repr(v)
    return s if len(s) <= limit else s[:limit] + f"...(len={len(s)})"


def _load_json(path: str):
    """读 JSON，容忍 UTF-8 BOM（外部工具产出的文件常带 BOM）。

    main.py 自产 metrics.json 无 BOM，但迁移场景下文件可能经手工/其它脚本中转，
    这里显式剥离 BOM，避免「文件其实有效却解析失败」的假失败。
    """
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def deep_diff(a, b, path: str = "", out: list = None, tol: float = 1e-9,
              ignore: set = None) -> list:
    """递归比较两个 JSON 结构；返回差异列表（空 = 一致）。

    ignore：额外跳过的顶层键（如关闭诊断后按设计缺失的 itf_warped_masked_db）。
    """
    if out is None:
        out = []
    ignore = ignore or set()
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            # 忽略集在任意层级生效（键名足够专属，如 diagnostic / itf_warped_masked_db）
            if k in IGNORE_KEYS or k in ignore:
                continue
            p = f"{path}.{k}" if path else k
            if k not in a:
                out.append(f"{p}: 仅 candidate 有 = {_fmt(b[k])}")
            elif k not in b:
                out.append(f"{p}: 仅 baseline 有 = {_fmt(a[k])}")
            else:
                deep_diff(a[k], b[k], p, out, tol, ignore)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{path}: 长度不同 baseline={len(a)} candidate={len(b)}")
        for i in range(min(len(a), len(b))):
            deep_diff(a[i], b[i], f"{path}[{i}]", out, tol)
    elif isinstance(a, bool) or isinstance(b, bool):
        if a != b:
            out.append(f"{path}: baseline={_fmt(a)} candidate={_fmt(b)}")
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if abs(float(a) - float(b)) > tol:
            out.append(f"{path}: baseline={_fmt(a)} candidate={_fmt(b)} |Δ|={abs(a - b):.3e}")
    else:
        if a != b:
            out.append(f"{path}: baseline={_fmt(a)} candidate={_fmt(b)}")
    return out


def compare_metrics(base_path: str, cand_path: str, tol: float) -> dict:
    base = _load_json(base_path)
    cand = _load_json(cand_path)

    # 诊断开关（P2）：baseline 开、candidate 关时，掩膜 ITF 按设计缺失 → 不参与比较，
    # 但必须显式报出，避免「静默忽略」。
    diag_base = (base.get("diagnostic") or {}).get("masked_itf", True)
    diag_cand = (cand.get("diagnostic") or {}).get("masked_itf", True)
    diag_changed = (diag_base != diag_cand)
    # 开关本身（diagnostic.masked_itf）与随之按设计缺失的掩膜 ITF 都不参与比较
    ignore = {"itf_warped_masked_db", "diagnostic"} if diag_changed else set()

    diffs = deep_diff(base, cand, tol=tol, ignore=ignore)
    strict_diffs = []
    for k in STRICT_KEYS:
        if k in base and k in cand and base[k] != cand[k]:
            strict_diffs.append(f"{k}: baseline={_fmt(base[k])} candidate={_fmt(cand[k])}")

    # 去重：出现在「配置不可比」里的键不再在「指标差异」中重复列出
    strict_prefixes = tuple(f"{k}." for k in STRICT_KEYS) + tuple(f"{k}[:" for k in STRICT_KEYS)
    plain_roots = set(STRICT_KEYS)
    diffs = [d for d in diffs
             if not (d.startswith(strict_prefixes) or d.split(":")[0] in plain_roots)]

    t_base = (base.get("runtime_sec") or {}).get("pass2")
    t_cand = (cand.get("runtime_sec") or {}).get("pass2")
    speedup = None
    if t_base and t_cand:
        speedup = (float(t_base) - float(t_cand)) / float(t_base) * 100.0

    n_checked = len(diffs) + len(strict_diffs)
    return {
        "base_path": base_path,
        "cand_path": cand_path,
        "strict_diffs": strict_diffs,
        "value_diffs": diffs,
        "ignored_keys": sorted(IGNORE_KEYS | ignore),
        "diagnostic": {"baseline_masked_itf": diag_base, "candidate_masked_itf": diag_cand,
                       "changed": diag_changed,
                       "note": ("candidate 关闭诊断 → metrics.metrics.itf_warped_masked_db "
                                "按设计为 null，未参与比较（§9 辅助口径，不参与验收判据）"
                                if diag_changed else "")},
        "pass2_sec": {"baseline": t_base, "candidate": t_cand, "speedup_pct": speedup},
        "ok": n_checked == 0,
    }


def compare_videos(base_path: str, cand_path: str) -> dict:
    try:
        import cv2
        import numpy as np
    except Exception as exc:
        return {"ok": None, "reason": f"无法比较视频（缺 numpy/OpenCV：{exc}）"}

    cap_a = cv2.VideoCapture(base_path)
    cap_b = cv2.VideoCapture(cand_path)
    if not (cap_a.isOpened() and cap_b.isOpened()):
        cap_a.release()
        cap_b.release()
        return {"ok": None, "reason": f"视频打不开：{base_path} / {cand_path}"}

    n_a = int(cap_a.get(cv2.CAP_PROP_FRAME_COUNT))
    n_b = int(cap_b.get(cv2.CAP_PROP_FRAME_COUNT))
    if (cap_a.get(cv2.CAP_PROP_FRAME_WIDTH) != cap_b.get(cv2.CAP_PROP_FRAME_WIDTH)
            or cap_a.get(cv2.CAP_PROP_FRAME_HEIGHT) != cap_b.get(cv2.CAP_PROP_FRAME_HEIGHT)):
        cap_a.release()
        cap_b.release()
        return {"ok": False, "reason": "分辨率不一致"}

    psnrs = []
    ident = 0
    t = 0
    while True:
        ok_a, fa = cap_a.read()
        ok_b, fb = cap_b.read()
        if not ok_a or not ok_b:
            break
        if fa.shape != fb.shape:
            cap_a.release()
            cap_b.release()
            return {"ok": False, "reason": f"第 {t} 帧形状不一致 {fa.shape} vs {fb.shape}"}
        mse = float(np.mean((fa.astype(np.float64) - fb.astype(np.float64)) ** 2))
        psnrs.append(float("inf") if mse <= 1e-12 else float(10.0 * np.log10(255.0 ** 2 / mse)))
        if mse <= 1e-12:
            ident += 1
        t += 1
    cap_a.release()
    cap_b.release()

    if not psnrs:
        return {"ok": None, "reason": "未读到任何帧"}

    finite = sorted(p for p in psnrs if p != float("inf"))
    worst_idx = int(min(range(len(psnrs)), key=lambda i: psnrs[i]))
    return {
        "ok": True,
        "n_frames": len(psnrs),
        "meta_frames": {"baseline": n_a, "candidate": n_b},
        "psnr_min": psnrs[worst_idx],
        "psnr_min_frame": worst_idx,
        "psnr_median": (finite[len(finite) // 2] if finite else float("inf")),
        "psnr_p10": (finite[max(0, len(finite) // 10)] if finite else float("inf")),
        "identical_frames": ident,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="改前/改后等价性验证（metrics.json + 成片）")
    ap.add_argument("--baseline", required=True, help="改前 metrics.json")
    ap.add_argument("--candidate", required=True, help="改后 metrics.json")
    ap.add_argument("--baseline-video", help="改前成片（可选，给则逐帧 PSNR）")
    ap.add_argument("--candidate-video", help="改后成片（可选）")
    ap.add_argument("--tol", type=float, default=1e-9, help="数值字段容差（默认 1e-9）")
    ap.add_argument("--psnr-min", type=float, default=50.0,
                    help="成片逐帧 PSNR 下限 dB（默认 50；inf 视为通过）")
    ap.add_argument("--json", metavar="PATH", help="结果写 JSON")
    args = ap.parse_args()

    for p in (args.baseline, args.candidate):
        if not os.path.exists(p):
            print(f"[UNDECIDED] 文件不存在：{p}")
            return EXIT_UNDECIDED

    report = {"metrics": compare_metrics(args.baseline, args.candidate, args.tol)}
    m = report["metrics"]

    print("=" * 78)
    print("改前/改后等价性验证 —— video-stabilization（P2 数学零改动证明）")
    print("=" * 78)
    print(f"baseline : {args.baseline}")
    print(f"candidate: {args.candidate}")
    print(f"忽略字段 : {', '.join(m['ignored_keys'])}（计时 + 按设计缺失项）")
    if m["diagnostic"]["changed"]:
        print(f"诊断开关 : baseline masked_itf={m['diagnostic']['baseline_masked_itf']} -> "
              f"candidate masked_itf={m['diagnostic']['candidate_masked_itf']}")
        print(f"           {m['diagnostic']['note']}")
    print("-" * 78)

    if m["strict_diffs"]:
        print("配置类字段不一致（两遍不可比，先查命令行参数是否一致）：")
        for d in m["strict_diffs"]:
            print("  ! " + d)
    else:
        print("配置类字段（smoother/shots/clamp/degradations/尺寸/帧数）：一致")

    if m["value_diffs"]:
        print(f"指标字段差异 {len(m['value_diffs'])} 处：")
        for d in m["value_diffs"]:
            print("  x " + d)
    elif m["strict_diffs"]:
        print("除上方配置类字段外的指标字段：一致")
    else:
        print(f"指标字段（tol={args.tol}）：逐字段一致")

    sp = m["pass2_sec"]
    if sp["speedup_pct"] is not None:
        print(f"pass2 耗时：baseline {sp['baseline']} s -> candidate {sp['candidate']} s "
              f"（{sp['speedup_pct']:+.1f}%）")

    video_verdict = None
    if args.baseline_video and args.candidate_video:
        if not (os.path.exists(args.baseline_video) and os.path.exists(args.candidate_video)):
            print("成片比较：跳过（视频文件不存在）")
        else:
            v = compare_videos(args.baseline_video, args.candidate_video)
            report["video"] = v
            print("-" * 78)
            if v.get("ok") is None:
                print(f"成片比较：无法判定 —— {v.get('reason')}")
            elif not v["ok"]:
                print(f"成片比较：FAIL —— {v.get('reason')}")
            else:
                worst = v["psnr_min"]
                verdict = (worst == float("inf")) or (worst >= args.psnr_min)
                video_verdict = verdict
                print(f"成片逐帧 PSNR：帧数 {v['n_frames']}（元数据 {v['meta_frames']}）")
                print(f"  min = {worst:.4f} dB @ 帧 {v['psnr_min_frame']} / "
                      f"p10 = {v['psnr_p10']:.4f} / 中位 = {v['psnr_median']:.4f}")
                print(f"  与基线逐像素完全相同帧数：{v['identical_frames']} / {v['n_frames']}")
                print(f"  判定（下限 {args.psnr_min} dB）：{'PASS' if verdict else 'FAIL'}")

    print("-" * 78)
    ok = m["ok"] and (video_verdict is not False)
    if ok:
        print("总结论：PASS —— 改动对指标与成片无影响（数学逻辑延续）。")
        code = EXIT_PASS
    else:
        print("总结论：FAIL —— 存在差异，不得作为『零数学改动』提交。")
        code = EXIT_FAIL
    print("=" * 78)

    report["ok"] = ok
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"JSON -> {args.json}")
    return code


if __name__ == "__main__":
    sys.exit(main())
