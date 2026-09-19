"""ACNR Catalog 快照 DB-aware GC CLI（P2-1：该清理清理）

查 projects.registry_version 得引用集，删除「非最近 keep_recent 且无项目锁定引用」
的 catalog_snapshots/*.json，防止无界增长。

用法（cwd=backend）：
    python -m scripts.acnr.gc_snapshots            # 真删（keep_recent=10）
    python -m scripts.acnr.gc_snapshots --dry-run  # 仅预览
    python -m scripts.acnr.gc_snapshots --keep 20  # 保留最近 20 版
"""
from __future__ import annotations

import argparse
import asyncio
import sys


async def _main() -> int:
    parser = argparse.ArgumentParser(description="ACNR catalog 快照 DB-aware GC")
    parser.add_argument("--keep", type=int, default=10, help="保留最近版本数（默认 10）")
    parser.add_argument("--dry-run", action="store_true", help="仅预览不实际删除")
    args = parser.parse_args()

    from app.services.acnr.catalog_snapshot_gc import run_db_aware_gc

    report = await run_db_aware_gc(keep_recent=args.keep, dry_run=args.dry_run)

    print("[ACNR snapshot GC]")
    print(f"  total_snapshots   = {report['total_snapshots']}")
    print(f"  keep_recent       = {report['keep_recent']}")
    print(f"  reference_status  = {report['reference_status']}")
    print(f"  referenced_count  = {report['referenced_count']}")
    print(f"  deleted           = {len(report['deleted'])} {report['deleted']}")
    print(f"  skipped_referenced= {len(report['skipped_referenced'])}")
    print(f"  dry_run           = {report['dry_run']}")
    if report["reference_status"] == "unverifiable":
        print("  [WARN] 引用集不可验证 → fail-closed，未删除任何快照")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
