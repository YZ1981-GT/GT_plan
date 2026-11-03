#!/usr/bin/env python3
"""ACNR 快照生命周期守卫（CI 作业 acnr-snapshot-count，RV14.1-01）。

判据与运行时快照清理是同一份：按文件加载 `backend/app/services/acnr/catalog_snapshot_gc.py`
（该模块顶层只用标准库；按文件加载不经 app 包初始化，CI 作业不装依赖也能跑），用它的
`committed_snapshot_versions` 与 `cleanup_stale_snapshots(dry_run=True)` 现算「引用集已证实时，运行时
清理会删掉哪些快照」—— 不在最近 keep_recent 份之内、没有登记进 git 索引、也没有被 `--referenced-version`
精确点名的快照。有一份即违规（--strict 退出 1）。

已登记进 git 索引的快照不算违规：它们是生成器的发布历史，运行时一律不删（RV13.1-01），保留与删除
只经生成器发布流程（随 git 提交删除并同时改两份登记）。旧口径「快照总数 ≤ keep_recent + 被引用数」
与这条保证矛盾：本 spec 每发一个批次就多一份已登记快照，总数必然超过 keep_recent。
判定不了哪些已登记（不在 git 仓库、没有 git、git 出错或超时）→ --strict 退出 2，不把未知当作可清理。
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent
SNAPSHOTS_DIR = PROJECT_ROOT / "backend" / "data" / "acnr" / "catalog_snapshots"
GC_MODULE_PATH = PROJECT_ROOT / "backend" / "app" / "services" / "acnr" / "catalog_snapshot_gc.py"
DEFAULT_KEEP_RECENT = 10


def _load_gc() -> ModuleType:
    """按文件加载运行时清理模块（单一判据来源）。"""
    spec = importlib.util.spec_from_file_location("_acnr_catalog_snapshot_gc", GC_MODULE_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载运行时快照清理模块：{GC_MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gc = _load_gc()


def lifecycle_problems(
    snapshots_dir: Path,
    *,
    keep_recent: int,
    referenced_versions: set[str],
) -> tuple[list[str], frozenset[str] | None, list[str]]:
    """返回 (目录里的全部版本, 已登记进 git 索引的版本或 None, 运行时清理会删掉的散落版本)。

    判定不了哪些已登记时第三项为全部版本（全部算未知、一个都不能当作可清理）。
    """
    versions = gc.list_snapshot_versions(snapshots_dir)
    committed = gc.committed_snapshot_versions(snapshots_dir)
    if committed is None:
        return versions, None, versions
    report = gc.cleanup_stale_snapshots(
        keep_recent=keep_recent, snapshots_dir=snapshots_dir,
        referenced_versions=set(referenced_versions), protected_versions=committed, dry_run=True,
    )
    return versions, committed, sorted(report["deleted"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ACNR 快照生命周期守卫")
    parser.add_argument("--strict", action="store_true", help="违规时退出码非 0（CI 用）")
    parser.add_argument("--keep-recent", type=int, default=DEFAULT_KEEP_RECENT, help="保留最近版本数")
    parser.add_argument("--referenced-version", action="append", default=[],
                        help="被项目锁定的版本（可重复；精确匹配）")
    parser.add_argument("--snapshots-dir", type=Path, default=SNAPSHOTS_DIR, help="快照目录")
    args = parser.parse_args(argv)

    referenced = set(args.referenced_version)
    versions, committed, strays = lifecycle_problems(
        args.snapshots_dir, keep_recent=args.keep_recent, referenced_versions=referenced,
    )
    print("[ACNR Snapshot Lifecycle]")
    print(f"  directory: {args.snapshots_dir}")
    print(f"  total: {len(versions)}")
    print(f"  keep_recent: {args.keep_recent}")
    print(f"  committed: {'unverifiable' if committed is None else len(committed)}")
    print(f"  referenced_versions: {sorted(referenced)}")

    if committed is None:
        print("[FAIL] 无法确认快照的 git 登记状态；拒绝把未知快照视为可清理。")
        return 2 if args.strict else 0
    if strays:
        print(f"[FAIL] 运行时清理会删掉的散落快照（不在最近保留范围、未登记进 git 索引、未被锁定）: {strays}")
        return 1 if args.strict else 0
    print("[OK] 没有运行时清理会删掉的散落快照。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
