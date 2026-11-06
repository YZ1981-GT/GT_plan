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

# R10: upper limit from historical valid count
_HISTORICAL_UPPER_LIMIT = 88


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

    # Load core files
    core_files: frozenset[str] = frozenset()

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
        print(f"❌ {SCAN_SCOPE_DRIFT}: {len(drift_errors)} scope issues:", file=sys.stderr)
        for e in drift_errors:
            print(f"  {e}", file=sys.stderr)
        return 1

    # Check core violations
    if scan.total_core_violations > 0:
        print(
            f"❌ {scan.total_core_violations} core violations found",
            file=sys.stderr,
        )
        return 1

    # Compare against baseline
    baseline = _load_baseline(baseline_path)
    if baseline is None:
        print(
            f"❌ {SCAN_SCOPE_DRIFT}: 缺少或无法解析基线 {baseline_path}；"
            "只允许在受控 --update-baseline 流程首次生成，CI 不得放行。",
            file=sys.stderr,
        )
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
        print(f"❌ Baseline check failed ({len(issues)} issues):", file=sys.stderr)
        for issue in issues:
            print(f"  {issue}", file=sys.stderr)
        return 1

    print(f"✅ Amount guard check passed: {scan.total_candidates} candidates "
          f"(baseline {baseline_total}), {len(scan.scopes)} scopes")
    return 0


def _run_update_baseline(args: argparse.Namespace) -> int:
    """Run --update-baseline mode: generate a new baseline JSON."""
    baseline_path = Path(args.baseline) if args.baseline else _DEFAULT_BASELINE

    # §16 F9: --update-baseline requires clean worktree
    if not args.force and not _check_worktree_clean():
        print(
            "❌ --update-baseline 要求 git status --porcelain 为空。"
            "在候选 worktree 中运行，或使用 --force 跳过检查。",
            file=sys.stderr,
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

    core_files: frozenset[str] = frozenset()
    scan = run_scan(_FRONTEND_SRC, exemptions, core_files)

    # Check for drift errors
    drift_errors = [e for e in scan.errors if SCAN_SCOPE_DRIFT in e]
    if drift_errors:
        print(f"❌ {SCAN_SCOPE_DRIFT}: cannot generate baseline with scope issues",
              file=sys.stderr)
        for e in drift_errors:
            print(f"  {e}", file=sys.stderr)
        return 1

    # R10: baseline must not exceed historical upper limit
    if scan.total_candidates > _HISTORICAL_UPPER_LIMIT:
        print(
            f"❌ total_candidates={scan.total_candidates} > historical limit {_HISTORICAL_UPPER_LIMIT}。"
            "拒绝生成会放宽历史上限的基线，请先修复违规。",
            file=sys.stderr,
        )
        return 1

    # Check that we're not raising the baseline
    old_baseline = _load_baseline(baseline_path)
    if old_baseline:
        old_total = old_baseline.get("total_candidates", 0)
        if scan.total_candidates > old_total:
            print(
                f"❌ 拒绝上调基线: {old_total} → {scan.total_candidates}。"
                f"请先修复违规，不得抬高基线。",
                file=sys.stderr,
            )
            return 1

    scan_json = scan.to_json()
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(
        json.dumps(scan_json, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"✅ Baseline updated: {scan.total_candidates} candidates, "
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
