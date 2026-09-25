"""三平滑器对比实验 runner（B，纯参数实验，零算法改动）。

目的（AGENTS.md §8.4 选型理由 + 课程报告核心素材）：
用同一套自研流水线，对 `ma` / `median` / `gauss` × 窗口 {15, 31, 61} 做端到端对比，
回答两个问题：
  1. 平滑器与窗口如何影响 ITF / 稳定度 S / 裁剪率 / 失真 D；
  2. §8.4 的选型（高斯 + 窗口 31）是否被实验数据支持。

设计要点：
- **不修改任何算法与口径**：每个配置只调用一次 `python main.py`，参数仅 `--smooth/--window`；
- **输出隔离**：每个配置写入 `output/sweep/<dataset>/<smoother>_<window>/`，
  避免 metrics.json / 成片互相覆盖（`output/` 已 gitignore）；
- **幂等**：已有 metrics.json 的配置默认跳过（`--force` 重跑）；
- **单次失败不中断**：记录 stderr，最后汇总失败清单并以非零码退出；
- 结果落盘 `docs/smoother_sweep.json` + 终端/`--md` markdown 对比表。

运行成本（v2.5 实测外推，单配置 pass1+pass2）：
  合成视频 ≈ 50 s × 9 配置 ≈ 8 min；test1 ≈ 1153 s × 9 配置 ≈ 2.9 h。
  故默认只跑合成档（`--stage synth`）；test1 需显式 `--stage test1`。
  加 `--no-diagnostic`（P2 提速）可显著缩短——诊断量与本实验结论无关，推荐开启。

用法：
  python tools/profile_smoothers.py                          # 合成档 9 配置
  python tools/profile_smoothers.py --stage test1 --no-diagnostic
  python tools/profile_smoothers.py --stage both --force --md docs/RESULTS.md
  python tools/profile_smoothers.py --max-configs 2          # 冒烟：只跑前 2 个配置
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SMOOTHERS = ("ma", "median", "gauss")
WINDOWS = (15, 31, 61)
# §11 验收线（用于自动判定，不用于放松标准）
S_SYNTH_MIN = 0.5
S_TEST1_MIN = 0.0
CROP_MIN = 0.85
D_SYNTH_MAX = 0.05

DATASETS = {
    "synth": {"input": os.path.join("data", "synthetic", "synthetic_shaky.mp4"),
              "label": "合成视频"},
    "test1": {"input": os.path.join("data", "test1.mp4"), "label": "test1.mp4（实拍）"},
}


def run_one(dataset: str, smoother: str, window: int, extra_args: list, force: bool) -> dict:
    ds = DATASETS[dataset]
    out_dir = os.path.join("output", "sweep", dataset, f"{smoother}_{window}")
    metrics_path = os.path.join(out_dir, "metrics.json")
    video_path = os.path.join(out_dir, "stabilized.mp4")
    tag = f"{dataset}/{smoother}_w{window}"

    if os.path.exists(metrics_path) and not force:
        with open(metrics_path, encoding="utf-8-sig") as f:
            m = json.load(f)
        return {"tag": tag, "status": "cached", "metrics": m}

    os.makedirs(out_dir, exist_ok=True)
    cmd = [sys.executable, "main.py",
           "--input", ds["input"], "--output", video_path,
           "--smooth", smoother, "--window", str(window)] + extra_args
    print(f"\n>>> [{tag}] {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0 or not os.path.exists(metrics_path):
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-8:])
        return {"tag": tag, "status": "failed", "returncode": proc.returncode,
                "stderr_tail": tail}

    with open(metrics_path, encoding="utf-8-sig") as f:
        m = json.load(f)
    return {"tag": tag, "status": "ok", "metrics": m}


def summarize(runs: list) -> list:
    """把原始 metrics 摊平成可比较的行。"""
    rows = []
    for r in runs:
        m = r.get("metrics")
        if not m:
            continue
        met = m["metrics"]
        stab = met.get("stability") or {}
        rows.append({
            "tag": r["tag"],
            "dataset": r["tag"].split("/")[0],
            "smoother": m["smoother"]["type"],
            "window": m["smoother"]["window"],
            "itf_orig": met["itf_original_db"],
            "itf_stab": met["itf_stabilized_db"],
            "itf_gain": met["itf_stabilized_db"] - met["itf_original_db"],
            "S": stab.get("S"),
            "crop": met["cropping_ratio"],
            "D": met["distortion"],
            "clamp_events": (m.get("clamp") or {}).get("events"),
            "redetection": (m.get("degradations") or {}).get("redetection_frames"),
            "pass1_s": (m.get("runtime_sec") or {}).get("pass1"),
            "pass2_s": (m.get("runtime_sec") or {}).get("pass2"),
        })
    rows.sort(key=lambda x: (x["dataset"], x["smoother"], x["window"]))
    return rows


def markdown_table(rows: list) -> str:
    if not rows:
        return "_（无有效结果）_\n"
    out = ["| 数据集 | 平滑器 | 窗口 | ITF 原 | ITF 稳定 | ITF 增益 | 稳定度 S | 裁剪率 | 失真 D | 限幅 | 重检测 | pass2 s |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        out.append("| {dataset} | {smoother} | {window} | {itf_orig:.3f} | {itf_stab:.3f} | "
                   "{itf_gain:+.3f} | {S:.4f} | {crop:.4f} | {D:.5f} | {clamp} | {redet} | {p2:.1f} |".format(
                       dataset=r["dataset"], smoother=r["smoother"], window=r["window"],
                       itf_orig=r["itf_orig"], itf_stab=r["itf_stab"], itf_gain=r["itf_gain"],
                       S=(r["S"] if r["S"] is not None else float("nan")),
                       crop=r["crop"], D=r["D"], clamp=r["clamp_events"],
                       redet=r["redetection"], p2=(r["pass2_s"] or 0.0)))
    return "\n".join(out) + "\n"


def analysis(rows: list) -> list:
    """规则化小结（供报告「选型理由」章节引用；不替代用户判断）。"""
    notes = []
    for ds in ("synth", "test1"):
        sub = [r for r in rows if r["dataset"] == ds]
        if not sub:
            continue
        s_min = S_SYNTH_MIN if ds == "synth" else S_TEST1_MIN
        d_max = D_SYNTH_MAX if ds == "synth" else float("inf")
        ok = [r for r in sub if (r["S"] or -1) >= s_min and r["crop"] >= CROP_MIN and r["D"] <= d_max]
        notes.append(f"- [{ds}] 有效配置 {len(sub)} 个；同时达标的 {len(ok)} 个。")
        if ok:
            best_s = max(ok, key=lambda r: r["S"])
            best_i = max(ok, key=lambda r: r["itf_gain"])
            notes.append(f"  - 稳定度最高：`{best_s['smoother']}` w{best_s['window']}（S={best_s['S']:.4f}，"
                         f"ITF 增益 {best_s['itf_gain']:+.3f}）")
            notes.append(f"  - ITF 增益最高：`{best_i['smoother']}` w{best_i['window']}（{best_i['itf_gain']:+.3f} dB，"
                         f"S={best_i['S']:.4f}）")
        # 每个平滑器的窗口趋势
        for sm in SMOOTHERS:
            g = sorted([r for r in sub if r["smoother"] == sm], key=lambda r: r["window"])
            if len(g) >= 2:
                notes.append(f"  - `{sm}`：S 随窗口 " +
                             " → ".join(f"w{r['window']}={r['S']:.4f}" for r in g) + "；" +
                             "ITF 增益 " + " → ".join(f"w{r['window']}={r['itf_gain']:+.3f}" for r in g))
    return notes


def main() -> int:
    ap = argparse.ArgumentParser(description="三平滑器 × 窗口 端到端对比实验（B）")
    ap.add_argument("--stage", choices=["synth", "test1", "both"], default="synth",
                    help="跑哪个数据集（默认 synth；test1 约 2.9 h/9 配置）")
    ap.add_argument("--smoothers", default=",".join(SMOOTHERS))
    ap.add_argument("--windows", default=",".join(str(w) for w in WINDOWS))
    ap.add_argument("--force", action="store_true", help="重跑已有 metrics.json 的配置")
    ap.add_argument("--no-diagnostic", action="store_true",
                    help="跳过纯诊断 warp（P2 提速；对本质验结论无影响，推荐开启）")
    ap.add_argument("--max-configs", type=int, default=0, help="只跑前 N 个配置（冒烟用）")
    ap.add_argument("--json", default=os.path.join("docs", "smoother_sweep.json"))
    ap.add_argument("--md", help="把对比表追加到该 markdown（如 docs/RESULTS.md）")
    args = ap.parse_args()

    datasets = ["synth", "test1"] if args.stage == "both" else [args.stage]
    smoothers = [s.strip() for s in args.smoothers.split(",") if s.strip()]
    windows = [int(w) for w in args.windows.split(",") if w.strip()]

    # 数据集就位检查
    for ds in datasets:
        path = DATASETS[ds]["input"]
        if not os.path.exists(os.path.join(ROOT, path)):
            if ds == "test1":
                print(f"! 跳过 test1：{path} 不存在（不入库，需手动提供）")
                datasets = [d for d in datasets if d != "test1"]
            else:
                print(f"x 缺少 {path}：请先运行 python tools/make_synthetic.py")
                return 1
    if not datasets:
        print("x 没有可跑的数据集。")
        return 1

    extra = ["--no-diagnostic"] if args.no_diagnostic else []
    combos = [(ds, sm, w) for ds in datasets for sm in smoothers for w in windows]
    if args.max_configs > 0:
        combos = combos[:args.max_configs]

    est_per_run = {"synth": 50.0, "test1": 1153.0}
    est = sum(est_per_run[ds] for ds, _, _ in combos)
    print("=" * 78)
    print(f"三平滑器对比实验：{len(combos)} 个配置"
          f"（{len(datasets)} 数据集 × {len(smoothers)} 平滑器 × {len(windows)} 窗口）")
    print(f"预计耗时 ≈ {est / 60:.1f} min（按 v2.5 单配置外推；--no-diagnostic 会更快）")
    print(f"额外参数：{extra or '（无）'}")
    print("=" * 78)

    runs = []
    for ds, sm, w in combos:
        runs.append(run_one(ds, sm, w, extra, args.force))

    failed = [r for r in runs if r["status"] == "failed"]
    rows = summarize(runs)
    notes = analysis(rows)

    print("\n" + "=" * 78)
    print("对比表")
    print("=" * 78)
    print(markdown_table(rows))
    print("小结（规则化，供报告引用）")
    for n in notes:
        print(n)
    print(f"\n状态：ok/cached = {len(runs) - len(failed)}，failed = {len(failed)}")
    for r in failed:
        print(f"  x {r['tag']}：returncode={r.get('returncode')}\n{r.get('stderr_tail', '')}")

    payload = {"configs": combos, "extra_args": extra, "runs": runs,
               "table_rows": rows, "notes": notes,
               "acceptance": {"S_synth_min": S_SYNTH_MIN, "S_test1_min": S_TEST1_MIN,
                              "crop_min": CROP_MIN, "D_synth_max": D_SYNTH_MAX}}
    os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
    with open(args.json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\nJSON -> {args.json}")

    if args.md:
        with open(args.md, "a", encoding="utf-8") as f:
            f.write("\n### 三平滑器 × 窗口 端到端对比（tools/profile_smoothers.py 实测）\n\n")
            f.write(f"> 配置：{len(combos)} 个（{', '.join(datasets)}）；"
                    f"额外参数 {extra or '无'}。\n\n")
            f.write(markdown_table(rows))
            f.write("\n**规则化小结**\n\n")
            for n in notes:
                f.write(n + "\n")
        print(f"markdown 已追加 -> {args.md}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
