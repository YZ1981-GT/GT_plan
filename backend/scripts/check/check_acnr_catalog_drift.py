#!/usr/bin/env python3
"""
check_acnr_catalog_drift.py — ACNR Catalog 治理守卫

校验 catalog_report.json：
1. gap_count 守恒：gap_count == alias_conflicts(未确认) + unregistered_aliases + gaps + skip_reason
2. generated_at 陈旧度：不超过 7 天
3. 明细计数字段一致性

零依赖（仅 stdlib）。显式 UTF-8 读写。

Usage:
    python check_acnr_catalog_drift.py             # 报告模式（退出码恒 0）
    python check_acnr_catalog_drift.py --strict    # 严格模式（CI 用，有违规退出码 1）

Feature: acnr-runtime-convergence, Task 12
Requirements: Req-10
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ─── UTF-8 输出 ───────────────────────────────────────────────────────────────
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

# ─── 路径 ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent  # GT_plan/
REPORT_PATH = PROJECT_ROOT / "backend" / "data" / "acnr" / "catalog_report.json"

# ─── 常量 ─────────────────────────────────────────────────────────────────────
MAX_STALENESS_DAYS = 7


def load_report(path: Path) -> dict:
    """加载 catalog_report.json。"""
    if not path.exists():
        print(f"[ERROR] catalog_report.json not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def compute_expected_gap_count(report: dict) -> int:
    """根据明细计算期望 gap_count。

    gap_count = (alias_conflicts 未确认数) + unregistered_aliases数 + gaps数 + skip_reason数

    acknowledged_conflicts（action=="acknowledged"）从 alias_conflicts 中扣除。
    """
    alias_conflicts = report.get("alias_conflicts", [])
    acknowledged = report.get("acknowledged_conflicts", [])

    # 未确认的 alias conflict = 全部 - acknowledged
    # acknowledged 的 alias 在 alias_conflicts 中 action == "acknowledged"
    acknowledged_aliases = {c.get("alias") for c in acknowledged}
    effective_conflicts = [
        c for c in alias_conflicts
        if c.get("alias") not in acknowledged_aliases
    ]

    unregistered_count = len(report.get("unregistered_aliases", []))
    gaps_count = len(report.get("gaps", []))
    skip_reason_count = report.get("summary", {}).get("sheets_with_skip_reason", 0)

    return len(effective_conflicts) + unregistered_count + gaps_count + skip_reason_count


def check_gap_count_conservation(report: dict) -> list[str]:
    """校验 gap_count 与明细计数一致。"""
    errors: list[str] = []
    summary = report.get("summary", {})
    actual_gap_count = summary.get("gap_count", -1)
    expected = compute_expected_gap_count(report)

    if actual_gap_count != expected:
        errors.append(
            f"gap_count mismatch: reported={actual_gap_count}, "
            f"expected={expected} (alias_conflicts_effective + "
            f"unregistered_aliases + gaps + skip_reason)"
        )

    # 额外校验：alias_conflict_count 与列表长度一致
    alias_conflict_count = summary.get("alias_conflict_count", 0)
    alias_conflicts_len = len(report.get("alias_conflicts", []))
    if alias_conflict_count != alias_conflicts_len:
        errors.append(
            f"alias_conflict_count mismatch: summary={alias_conflict_count}, "
            f"actual list length={alias_conflicts_len}"
        )

    # 额外校验：unregistered_alias_count 与列表长度一致
    unregistered_alias_count = summary.get("unregistered_alias_count", 0)
    unregistered_aliases_len = len(report.get("unregistered_aliases", []))
    if unregistered_alias_count != unregistered_aliases_len:
        errors.append(
            f"unregistered_alias_count mismatch: summary={unregistered_alias_count}, "
            f"actual list length={unregistered_aliases_len}"
        )

    return errors


def check_staleness(report: dict) -> list[str]:
    """校验 generated_at 不超过 MAX_STALENESS_DAYS 天。"""
    errors: list[str] = []
    generated_at_str = report.get("generated_at")

    if not generated_at_str:
        errors.append("generated_at field is missing from catalog_report.json")
        return errors

    try:
        generated_at = datetime.fromisoformat(generated_at_str)
        # 确保 timezone-aware
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError) as e:
        errors.append(f"generated_at is not a valid ISO timestamp: {e}")
        return errors

    now = datetime.now(timezone.utc)
    age = now - generated_at

    if age > timedelta(days=MAX_STALENESS_DAYS):
        errors.append(
            f"catalog_report.json is stale: generated_at={generated_at_str}, "
            f"age={age.days} days (max allowed={MAX_STALENESS_DAYS} days)"
        )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ACNR Catalog Drift Guard — 校验 gap_count 守恒 + 陈旧度"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="严格模式（有违规则退出码 1）",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=REPORT_PATH,
        help="catalog_report.json 路径（默认自动定位）",
    )
    args = parser.parse_args()

    report = load_report(args.report_path)

    print("[ACNR Catalog Drift] Checking catalog_report.json...")

    all_errors: list[str] = []

    # Check 1: gap_count 守恒
    gap_errors = check_gap_count_conservation(report)
    all_errors.extend(gap_errors)

    # Check 2: 陈旧度
    staleness_errors = check_staleness(report)
    all_errors.extend(staleness_errors)

    # 输出结果
    summary = report.get("summary", {})
    print(f"  gap_count (reported): {summary.get('gap_count', '?')}")
    print(f"  gap_count (expected): {compute_expected_gap_count(report)}")
    print(f"  alias_conflict_count: {summary.get('alias_conflict_count', '?')}")
    print(f"  unregistered_alias_count: {summary.get('unregistered_alias_count', '?')}")
    print(f"  acknowledged_conflict_count: {summary.get('acknowledged_conflict_count', '?')}")
    print(f"  generated_at: {report.get('generated_at', '?')}")

    if all_errors:
        print(f"\n[FAIL] {len(all_errors)} issue(s) found:")
        for err in all_errors:
            print(f"  - {err}")
        if args.strict:
            return 1
    else:
        print("\n[OK] All checks passed.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
