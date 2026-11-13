"""ACNR Catalog 快照 DB-aware GC CLI（P2-1：该清理清理）

与启动任务走同一入口 run_db_aware_gc（不带会话，入口自开短会话）：引用集只认数据库里
项目表落库的版本锁（`projects.acnr_registry_version`，含移入回收站的项目），没有会话或查库失败
就一个都不删；已提交进仓库的快照一律不删（RV13.1-01）。只清理「非最近 keep_recent、无项目
锁定引用、未提交」的 catalog_snapshots/*.json。

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
    print(f"  lifecycle_lock    = {report.get('lifecycle_lock_status', 'unknown')}")
    print(f"  referenced_count  = {report['referenced_count']}")
    print(f"  deleted           = {len(report['deleted'])} {report['deleted']}")
    if report.get("would_delete"):
        print(f"  would_delete      = {len(report['would_delete'])} {report['would_delete']}")
    print(f"  already_absent    = {len(report.get('already_absent', []))}")
    print(f"  failed            = {len(report.get('failed', []))} {report.get('failed', [])}")
    print(f"  skipped_referenced= {len(report['skipped_referenced'])}")
    print(f"  skipped_committed = {len(report['skipped_protected'])}（已提交进仓库，运行时不删）")
    print(f"  dry_run           = {report['dry_run']}")
    if report["reference_status"] == "unverifiable":
        print("  [WARN] 引用集不可验证或生命周期锁忙 → fail-closed，未删除任何快照")
    if report.get("failed"):
        print("  [ERROR] 部分快照删除失败；已逐项列出，请处理占用 / 权限后重试")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
