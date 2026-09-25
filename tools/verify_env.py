"""上机环境与红线自检（跨 agent / 跨机器迁移的第一入口）。

用途：任何新会话或新机器接手本工程后，先跑本脚本，一次性回答三个问题：
1. 环境是否就绪（Python 版本、6 个锁定依赖能否 import、版本是否与 requirements.txt 精确一致）；
2. 数据是否就绪（合成视频能否重建、data/test1.mp4 是否在位）——决定能跑哪一档验收；
3. 工程红线是否被破坏（§4 禁用 API 是否只出现在 tests/ 或注释文字中）。

退出码：
  0 = 环境就绪（依赖齐 + 版本匹配 + 红线通过）；
  1 = 阻断（缺依赖 / 版本不匹配 / 红线违规 / pytest 未全绿）；
  2 = 依赖就绪但缺 data/test1.mp4（只能做单元测试与合成档验收）。

用法：
  python tools/verify_env.py                  # 环境 + 数据 + 红线（不跑测试）
  python tools/verify_env.py --run-tests      # 追加 pytest
  python tools/verify_env.py --cov            # 追加 pytest + 核心模块覆盖率
  python tools/verify_env.py --json out.json  # 结果同时写 JSON（供记录/对比）
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tokenize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EXIT_OK = 0
EXIT_BLOCKED = 1
EXIT_PARTIAL = 2

# 依赖锁定（与 requirements.txt 一一对应；新增依赖须先经用户确认，§3）
DEPENDENCIES = [
    ("numpy", "2.5.3"),
    ("cv2", "5.0.0.93"),
    ("matplotlib", "3.11.2"),
    ("pytest", "9.1.1"),
    ("pytest_cov", "7.1.0"),
    ("coverage", "7.16.1"),
]

# 红线 1/2/3/4/7：禁用 API（AGENTS.md §4）
# 规则：主实现（main.py、src/、ds/、tools/）中禁止出现；tests/ 中允许（数值对照基准）。
REDLINE_FORBIDDEN = [
    r"cv2\.estimateAffinePartial2D",
    r"cv2\.estimateAffine2D",
    r"cv2\.findHomography",
    r"cv2\.estimateRigidTransform",
    r"cv2\.warpAffine",
    r"cv2\.warpPerspective",
    r"cv2\.remap",
    r"cv2\.resize",
    r"cv2\.goodFeaturesToTrack",
    r"cv2\.calcOpticalFlowPyrLK",
    r"cv2\.cornerHarris",
    r"cv2\.cornerSubPix",
    r"cv2\.filter2D",
    r"cv2\.GaussianBlur",
    r"cv2\.Sobel",
    r"cv2\.boxFilter",
    r"scipy\.ndimage",
    r"from\s+scipy",
    r"\bimport\s+scipy\b",
    r"heapq\.",
    r"\bdeque\b",
]

# TODO(SELF-IMPL) 是 M0 阶段临时标记；M1 起必须全部清除（§4 红线 3、§5）
TODO_SELF_IMPL = r"TODO\(SELF-IMPL\)"


def _safe_import(name: str):
    try:
        mod = __import__(name)
    except Exception as exc:  # ImportError / DLL 加载失败等
        return None, f"{type(exc).__name__}: {exc}"
    return mod, None


def check_python() -> dict:
    v = sys.version_info
    ok = (v.major, v.minor) >= (3, 10)
    return {"name": "Python 版本 >= 3.10", "ok": ok,
            "detail": f"{sys.version.split()[0]} ({sys.executable})"}


def check_dependencies() -> list:
    rows = []
    for mod_name, want in DEPENDENCIES:
        mod, err = _safe_import(mod_name)
        if mod is None:
            rows.append({"name": f"依赖 {mod_name}", "ok": False,
                         "detail": f"不可用：{err}"})
            continue
        got = getattr(mod, "__version__", "未知")
        # 版本归一化：部分包上报的 __version__ 少于锁定号（实测 opencv-python 5.0.0.93
        # 的 cv2.__version__ 只报 "5.0.0"）。故接受「相等」或「一方是另一方前缀」。
        gs, ws = str(got), str(want)
        ok = (gs == ws) or gs.startswith(ws) or ws.startswith(gs + ".")
        detail = f"实装 {got} / 锁定 {want}"
        if ok and gs != ws:
            detail += "（上报号较短，按前缀归一化判定通过）"
        elif not ok:
            detail += "（版本不一致！）"
        rows.append({"name": f"依赖 {mod_name}", "ok": ok, "detail": detail})
    return rows


def check_data() -> list:
    synth_mp4 = os.path.join(ROOT, "data", "synthetic", "synthetic_shaky.mp4")
    synth_gt = os.path.join(ROOT, "data", "synthetic", "ground_truth.json")
    test1 = os.path.exists(os.path.join(ROOT, "data", "test1.mp4"))
    rows = [
        {"name": "合成视频 data/synthetic/synthetic_shaky.mp4",
         "ok": os.path.exists(synth_mp4),
         "detail": (f"在位（{os.path.getsize(synth_mp4) / 1024:.0f} KB）"
                    if os.path.exists(synth_mp4)
                    else "缺失，但可重建：python tools/make_synthetic.py（种子 42）")},
        {"name": "合成真值 data/synthetic/ground_truth.json",
         "ok": os.path.exists(synth_gt),
         "detail": ("在位" if os.path.exists(synth_gt)
                    else "缺失（由 make_synthetic.py 生成）")},
        {"name": "实拍素材 data/test1.mp4",
         "ok": test1,
         "detail": ("在位" if test1 else
                    "缺失（不入库，需手动获取）→ 实拍档验收（test1 ITF/S/裁剪率）无法执行")},
    ]
    return rows


def _code_stripped(path: str) -> str:
    """用 tokenize 去掉注释与字符串字面量，只留可执行代码 token。

    这样「注释里提到 cv2.warpAffine」不会被误报（沿用工程既有红线自检口径）。
    """
    parts = []
    try:
        with open(path, "rb") as f:
            for tok in tokenize.tokenize(f.readline):
                if tok.type in (tokenize.COMMENT, tokenize.STRING,
                                tokenize.NL, tokenize.NEWLINE):
                    continue
                if tok.type in (tokenize.NAME, tokenize.OP, tokenize.NUMBER):
                    parts.append(tok.string)
    except Exception as exc:
        return f"__TOKENIZE_FAILED__ {exc}"
    return "\n".join(parts)


def check_redlines() -> list:
    """扫描主实现目录，报告禁用 API 与遗留 TODO(SELF-IMPL)。"""
    targets = []
    for item in ("main.py", "src", "ds", "tools"):
        full = os.path.join(ROOT, item)
        if os.path.isfile(full):
            targets.append(full)
        elif os.path.isdir(full):
            for root, _dirs, files in os.walk(full):
                for fn in files:
                    if fn.endswith(".py"):
                        targets.append(os.path.join(root, fn))

    violations = []
    for path in targets:
        code = _code_stripped(path)
        rel = os.path.relpath(path, ROOT)
        for pat in REDLINE_FORBIDDEN:
            for m in re.finditer(pat, code):
                snippet = code[max(0, m.start() - 30):m.end() + 15].replace("\n", " ")
                violations.append(f"{rel}: /{pat}/ <- ...{snippet}...")
        for m in re.finditer(TODO_SELF_IMPL, code):
            snippet = code[max(0, m.start() - 30):m.end() + 15].replace("\n", " ")
            violations.append(f"{rel}: 遗留 TODO(SELF-IMPL) <- ...{snippet}...")

    return [{
        "name": "红线静态自检（§4 禁用 API + 遗留 TODO）",
        "ok": not violations,
        "detail": (f"扫描 {len(targets)} 个主实现文件，无违规" if not violations
                   else f"发现 {len(violations)} 处违规：\n    " + "\n    ".join(violations)),
    }]


def run_pytest(with_cov: bool) -> dict:
    args = [sys.executable, "-m", "pytest", "tests/", "-q", "--no-header",
            "-p", "no:cacheprovider"]
    if with_cov:
        for mod in ("ds", "src.smoothing", "src.motion", "src.warp",
                    "src.features", "src.tracking"):
            args.append(f"--cov={mod}")
        args.append("--cov-report=term-missing")
    proc = subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    tail = "\n".join([ln for ln in (proc.stdout or "").strip().splitlines() if ln.strip()][-25:])
    return {"name": f"pytest{'（含覆盖率）' if with_cov else ''}",
            "ok": proc.returncode == 0,
            "detail": f"退出码 {proc.returncode}\n{tail}"}


def main() -> int:
    ap = argparse.ArgumentParser(description="上机环境与红线自检（迁移第一入口）")
    ap.add_argument("--run-tests", action="store_true", help="追加运行 pytest")
    ap.add_argument("--cov", action="store_true", help="覆盖率（隐含 --run-tests）")
    ap.add_argument("--json", metavar="PATH", help="结果同时写 JSON")
    args = ap.parse_args()

    rows = [check_python()]
    rows += check_dependencies()
    rows += check_data()
    rows += check_redlines()
    if args.run_tests or args.cov:
        rows.append(run_pytest(args.cov))

    print("=" * 78)
    print("上机环境与红线自检 —— video-stabilization（AGENTS.md §3/§4/§11）")
    print("=" * 78)
    for r in rows:
        print(f"[{'PASS' if r['ok'] else 'MISS'}] {r['name']}\n       {r['detail']}")

    deps_ok = all(r["ok"] for r in rows if r["name"].startswith(("Python", "依赖")))
    tests_row = next((r for r in rows if r["name"].startswith("pytest")), None)
    redlines_ok = next((r["ok"] for r in rows if "红线" in r["name"]), True)
    data_rows = [r for r in rows if r["name"].startswith(("合成视频", "合成真值", "实拍素材"))]
    has_synth = next((r["ok"] for r in data_rows if r["name"].startswith("合成视频")), False)
    has_test1 = next((r["ok"] for r in data_rows if r["name"].startswith("实拍素材")), False)

    print("-" * 78)
    print("结论：")
    if not deps_ok:
        # 依赖缺失/版本不符 = 阻断：此时连 import 都会失败，任何端到端都跑不了
        print("  x 环境未就绪：依赖缺失或版本与 requirements.txt 不一致 -> 先按 README 第二节安装。")
        print("    （缺 cv2 时流水线与 shots/tracking/warp 测试均无法收集，勿强行继续）")
        code = EXIT_BLOCKED
    elif tests_row is not None and not tests_row["ok"]:
        print("  x pytest 未全绿 -> 先排查测试失败，再谈指标。")
        code = EXIT_BLOCKED
    elif not redlines_ok:
        print("  x 发现红线违规 -> 违反 §4，必属返工，先修再继续。")
        code = EXIT_BLOCKED
    elif has_test1:
        print("  v 环境就绪，且实拍素材在位 -> 可执行全部验收（单元测试 + 合成档 + 实拍档）。")
        code = EXIT_OK
    else:
        print("  ~ 依赖就绪但缺 data/test1.mp4 -> 只能执行单元测试与合成档验收；")
        print("    实拍档（test1 ITF/S/裁剪率/切换检出）需先补齐素材。")
        code = EXIT_PARTIAL
    if not has_synth:
        print("  ! 合成视频缺失：先跑 python tools/make_synthetic.py 再验收。")
    print("=" * 78)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"rows": rows, "exit_code": code}, f, ensure_ascii=False, indent=2)
        print(f"JSON -> {args.json}")
    return code


if __name__ == "__main__":
    sys.exit(main())
