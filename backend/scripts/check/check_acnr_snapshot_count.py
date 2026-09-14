#!/usr/bin/env python3
"""
check_acnr_snapshot_count.py — ACNR 快照数量守卫

校验快照目录总数 ≤ keep_recent + referenced_count。
防止清理逻辑失效导致快照膨胀。

零依赖（仅 stdlib）。显式 UTF-8 读写。

Usage:
    python check_acnr_snapshot_count.py             # 报告模式（退出码恒 0）
    python check_acnr_snapshot_count.py --strict    # 严格模式（CI 用，超限退出码 1）

Feature: acnr-runtime-convergence, Task 19
Requirements: Req-16.4
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ─── UTF-8 输出 ───────────────────────────────────────────────────────────────
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

# ─── 路径 ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent  # GT_plan/
SNAPSHOTS_DIR = PROJECT_ROOT / "backend" / "data" / "acnr" / "catalog_snapshots"
CATALOG_PATH = PROJECT_ROOT / "backend" / "data" / "acnr" / "global_catalog.json"

# ─── 常量 ─────────────────────────────────────────────────────────────────────
DEFAULT_KEEP_RECENT = 10


def count_snapshots(snapshots_dir: Path) -> int:
    """统计快照目录下 .json 文件数量。"""
    if not snapshots_dir.exists():
        return 0
    return sum(1 for f in snapshots_dir.iterdir() if f.suffix == ".json")


def get_referenced_count_from_catalog(catalog_path: Path) -> int:
    """从 catalog_report 或 projects 维度估算被引用版本数。

    离线 CI 模式：无法查 DB，使用保守估计。
    如果 catalog 存在，至少当前版本被引用（=1）。
    实际生产中应查 PG: SELECT COUNT(DISTINCT registry_version) FROM projects
    WHERE registry_version IS NOT NULL。

    CI 守卫用近似值：referenced_count = 已知快照中被项目使用的版本数。
    保守默认 = 0（最严格校验）。
    """
    # 如果有 catalog，可以检查当前版本作为最低保底
    if catalog_path.exists():
        try:
            data = json.loads(catalog_path.read_text(encoding="utf-8"))
            # 当前版本至少被一个项目引用（保守计 0，实际可能更多）
            _ = data.get("registry_version", "")
            return 0  # CI 保守模式：假设 0 被引用 → 最严格
        except (json.JSONDecodeError, OSError):
            pass
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ACNR Snapshot Count Guard — 校验快照总数不超限"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="严格模式（超限则退出码 1）",
    )
    parser.add_argument(
        "--keep-recent",
        type=int,
        default=DEFAULT_KEEP_RECENT,
        help=f"保留最近版本数（默认 {DEFAULT_KEEP_RECENT}）",
    )
    parser.add_argument(
        "--referenced-count",
        type=int,
        default=None,
        help="手动指定被引用版本数（默认从 catalog 推断）",
    )
    parser.add_argument(
        "--snapshots-dir",
        type=Path,
        default=SNAPSHOTS_DIR,
        help="快照目录路径（默认自动定位）",
    )
    args = parser.parse_args()

    print("[ACNR Snapshot Count] Checking snapshot directory...")

    # 统计快照数量
    total = count_snapshots(args.snapshots_dir)

    # 被引用数量
    if args.referenced_count is not None:
        referenced = args.referenced_count
    else:
        referenced = get_referenced_count_from_catalog(CATALOG_PATH)

    max_allowed = args.keep_recent + referenced

    print(f"  Snapshots directory: {args.snapshots_dir}")
    print(f"  Total snapshots: {total}")
    print(f"  keep_recent: {args.keep_recent}")
    print(f"  referenced_count: {referenced}")
    print(f"  Max allowed: {max_allowed}")

    if total > max_allowed:
        print(
            f"\n[FAIL] Snapshot count ({total}) exceeds "
            f"keep_recent ({args.keep_recent}) + referenced ({referenced}) = {max_allowed}"
        )
        print(
            "  This indicates cleanup_stale_snapshots is not running properly "
            "or referenced_count is underestimated."
        )
        if args.strict:
            return 1
    else:
        print(f"\n[OK] Snapshot count ({total}) <= max allowed ({max_allowed}).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
