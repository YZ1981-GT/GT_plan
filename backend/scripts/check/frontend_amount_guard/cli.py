"""
CLI entry point for the frontend amount display guard.

Usage:
    python -m scripts.check.frontend_amount_guard.cli --check [--baseline path]
    python -m scripts.check.frontend_amount_guard.cli --update-baseline [--baseline path]

Design reference: §15 A8, §16 F9, §17 G6.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .rules import SCAN_SCOPE_DRIFT
from .scanner import ScanResult, run_scan


_REPO_ROOT = Path(__file__).resolve().parents[4]  # backend/scripts/check/frontend_amount_guard/cli.py → repo root
_FRONTEND_SRC = _REPO_ROOT / "audit-platform" / "frontend" / "src"
_DEFAULT_BASELINE = _REPO_ROOT / "audit-platform" / "frontend" / "scripts" / "amount-guard-baseline.json"

#: 核心文件清单（唯一来源：`scripts/gen/gen_frontend_amount_core_manifest.py`）。
#: 🔴 原先两处都是 `core_files: frozenset[str] = frozenset()` —— **恒为空集合、无任何
#: 加载逻辑**，于是「核心面零违规」这条结论建立在「核心面 = 空集」之上，等于没检
#: （spec platform-global-display-settings-closure 任务 11A 复核记录的四条实证缺口之二）。
_DEFAULT_CORE_MANIFEST = (
    _REPO_ROOT / "audit-platform" / "frontend" / "scripts" / "amount-guard-core.json"
)

#: AC-23 的硬上限。原值 88；2026-11-06 曾被改成 2000（注释自陈「原占位值 88 从未
#: 与真实基线对账」）⇒ **放宽 22 倍**。本轮回填真实核算结果（见下方口径说明）。
#:
#: 🔴 口径澄清（这是原 88 与 2000 能同时「合理」的原因）：
#: - **88 是旧的 `total_core_violations` 上限**（核心面违规数，AC-23 原文）；
#: - **1451 是 `total_candidates`**（全仓金额候选格，非违规）。
#: 原实现把这**两个不同量**都塞进同一个常量，于是无论填 88 还是 2000 总有一头错：
#: 填 88 会让 `total_candidates`（1451）立刻越限、填 2000 就让核心违规上限形同不存在。
#: 现在拆成两个常量，各自对各自的量，且都取**实测值**而非占位值。
_CORE_VIOLATION_UPPER_LIMIT = 0          # AC-23：核心面必须零违规（实测 0）
_CANDIDATE_UPPER_LIMIT = 1500            # 候选格上限（实测 1451，留 49 格余量，只许变短）


def _load_core_files(path: Path | None = None) -> frozenset[str]:
    """加载核心文件清单；缺失即**失败**（不能静默退化成空集）。

    静默退化成空集正是本条缺陷的成因：门禁照跑、数字照出，但核心面是空的。
    所以这里对「文件缺失 / 解析失败 / files 为空」三种情况一律抛错，
    由调用方转成 exit 1。
    """
    target = path or _DEFAULT_CORE_MANIFEST
    if not target.exists():
        raise FileNotFoundError(
            f"缺少核心清单 {target}；先跑 "
            "`python -m scripts.gen.gen_frontend_amount_core_manifest --write`"
        )
    data = json.loads(target.read_text(encoding="utf-8"))
    files = data.get("files") or []
    if not files:
        raise ValueError(
            f"核心清单 {target} 的 files 为空；核心面不得为空集合（会让判据恒绿）"
        )
    return frozenset(files)


def _emit(text: str, *, err: bool = False) -> None:
    """输出到 stdout/stderr，**在 GBK 终端下不崩**。

    🔴 本轮实测：`--check` 通过时打印 `✅` 会抛 `UnicodeEncodeError: 'gbk' codec
    can't encode character '\u2705'`。CI（Linux）不受影响，但本地 Windows 直接在
    print 上崩、退出码非 0 —— 看起来像「门禁红了」，实际判据根本没跑完。
    """
    stream = sys.stderr if err else sys.stdout
    enc = getattr(stream, "encoding", None) or "utf-8"
    try:
        text.encode(enc)
    except (UnicodeEncodeError, LookupError):
        text = text.encode(enc, errors="replace").decode(enc, errors="replace")
    print(text, file=stream)


def _check_worktree_clean() -> bool:
    """Check that git working tree has no changes (for --update-baseline)."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True,
            cwd=str(_REPO_ROOT), timeout=15,
        )
        return result.returncode == 0 and result.stdout.strip() == ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _load_baseline(path: Path) -> dict | None:
    """Load a baseline JSON file."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _run_check(args: argparse.Namespace) -> int:
    """Run --check mode: compare scan results against baseline."""
    baseline_path = Path(args.baseline) if args.baseline else _DEFAULT_BASELINE
    exemptions_path = Path(args.exemptions) if args.exemptions else None

    # Load parser exemptions
    exemptions: dict[str, str] = {}
    if exemptions_path and exemptions_path.exists():
        try:
            exemptions = json.loads(exemptions_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    # Load core files（🔴 缺失即失败，不得静默退化成空集合）
    try:
        core_files = _load_core_files(Path(args.core_manifest) if args.core_manifest else None)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        _emit(f"❌ {SCAN_SCOPE_DRIFT}: 核心清单不可用 —— {exc}")
        return 1

    scan = run_scan(_FRONTEND_SRC, exemptions, core_files)
    scan_json = scan.to_json()

    # Output the scan results
    if args.output:
        Path(args.output).write_text(
            json.dumps(scan_json, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # Check for scan errors (SCAN_SCOPE_DRIFT etc.)
    drift_errors = [e for e in scan.errors if SCAN_SCOPE_DRIFT in e]
    if drift_errors:
        _emit(f"❌ {SCAN_SCOPE_DRIFT}: {len(drift_errors)} scope issues:", err=True)
        for e in drift_errors:
            _emit(f"  {e}", err=True)
        return 1

    # Check core violations
    if scan.total_core_violations > 0:
        _emit(f"❌ {scan.total_core_violations} core violations found", err=True)
        return 1

    # Compare against baseline
    baseline = _load_baseline(baseline_path)
    if baseline is None:
        _emit(
            f"❌ {SCAN_SCOPE_DRIFT}: 缺少或无法解析基线 {baseline_path}；"
            "只允许在受控 --update-baseline 流程首次生成，CI 不得放行。")
        return 1

    # Compare per-scope
    baseline_scopes = baseline.get("scopes", {})
    issues: list[str] = []

    # Check that total candidates did not increase
    baseline_total = baseline.get("total_candidates", 0)
    if scan.total_candidates > baseline_total:
        issues.append(
            f"total_candidates increased: {baseline_total} → {scan.total_candidates}"
        )

    # Check that no scope has more candidates than baseline
    for scope, sr_json in scan_json["scopes"].items():
        bl_scope = baseline_scopes.get(scope, {})
        bl_candidates = bl_scope.get("candidates", 0)
        if sr_json["candidates"] > bl_candidates:
            issues.append(
                f"scope {scope}: candidates increased "
                f"{bl_candidates} → {sr_json['candidates']}"
            )

    if issues:
        _emit(f"❌ Baseline check failed ({len(issues)} issues):", err=True)
        for issue in issues:
            _emit(f"  {issue}", err=True)
        return 1

    _emit(f"✅ Amount guard check passed: {scan.total_candidates} candidates "
          f"(baseline {baseline_total}), {len(scan.scopes)} scopes, "
          f"{scan.total_core_violations} core violations, "
          f"{len(core_files)} core files scanned")
    return 0


def _run_update_baseline(args: argparse.Namespace) -> int:
    """Run --update-baseline mode: generate a new baseline JSON."""
    baseline_path = Path(args.baseline) if args.baseline else _DEFAULT_BASELINE

    # §16 F9: --update-baseline requires clean worktree
    if not args.force and not _check_worktree_clean():
        _emit(
            "❌ --update-baseline 要求 git status --porcelain 为空。"
            "在候选 worktree 中运行，或使用 --force 跳过检查。",
            err=True,
        )
        return 1

    exemptions: dict[str, str] = {}
    if args.exemptions:
        exemptions_path = Path(args.exemptions)
        if exemptions_path.exists():
            try:
                exemptions = json.loads(exemptions_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass

    core_files = _load_core_files(Path(args.core_manifest) if args.core_manifest else None)
    scan = run_scan(_FRONTEND_SRC, exemptions, core_files)

    # Check for drift errors
    drift_errors = [e for e in scan.errors if SCAN_SCOPE_DRIFT in e]
    if drift_errors:
        _emit(f"❌ {SCAN_SCOPE_DRIFT}: cannot generate baseline with scope issues")
        for e in drift_errors:
            _emit(f"  {e}")
        return 1

    # AC-23（R10）：核心面必须零违规；候选总数不得越过实测上限。
    # 这两个量不同，必须分开判（原实现共用一个常量，于是填 88 或 2000 都必有一头错）。
    if scan.total_core_violations > _CORE_VIOLATION_UPPER_LIMIT:
        _emit(
            f"❌ total_core_violations={scan.total_core_violations} > "
            f"{_CORE_VIOLATION_UPPER_LIMIT}（AC-23 要求核心面零违规）。请先修复违规。"
        )
        return 1
    if scan.total_candidates > _CANDIDATE_UPPER_LIMIT:
        _emit(
            f"❌ total_candidates={scan.total_candidates} > 实测上限 "
            f"{_CANDIDATE_UPPER_LIMIT}。拒绝生成会放宽上限的基线，请先修复违规。"
        )
        return 1

    # Check that we're not raising the baseline
    old_baseline = _load_baseline(baseline_path)
    if old_baseline:
        old_total = old_baseline.get("total_candidates", 0)
        if scan.total_candidates > old_total:
            _emit(
                f"❌ 拒绝上调基线: {old_total} → {scan.total_candidates}。"
                f"请先修复违规，不得抬高基线。")
            return 1

    scan_json = scan.to_json()
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(
        json.dumps(scan_json, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    _emit(f"✅ Baseline updated: {scan.total_candidates} candidates, "
          f"{len(scan.scopes)} scopes → {baseline_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Frontend amount display AST guard"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="Check against baseline")
    group.add_argument("--update-baseline", action="store_true", help="Generate/update baseline")

    parser.add_argument("--baseline", type=str, help="Path to baseline JSON")
    parser.add_argument("--output", type=str, help="Write full scan output to this path")
    parser.add_argument("--exemptions", type=str, help="Path to parser exemptions JSON")
    parser.add_argument("--force", action="store_true", help="Skip worktree clean check")
    parser.add_argument("--src", type=str, help="Override frontend src path")
    parser.add_argument(
        "--core-manifest",
        type=str,
        help="Path to the core-files manifest (default: audit-platform/frontend/scripts/amount-guard-core.json)",
    )

    args = parser.parse_args(argv)

    global _FRONTEND_SRC
    if args.src:
        _FRONTEND_SRC = Path(args.src)

    if args.check:
        return _run_check(args)
    elif args.update_baseline:
        return _run_update_baseline(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
