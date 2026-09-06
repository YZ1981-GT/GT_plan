"""数据库与文件备份脚本

用法：python backend/scripts/ops/backup.py

功能：
  1. pg_dump 全量备份 PostgreSQL
  2. 复制全部 storage 根（解析口径见 ``scripts/_storage_roots.py``）
  3. 记录备份清单和校验信息
  4. 清理超过 30 天的旧备份

建议：每日凌晨 cron 执行
  RPO = 1 天（最多丢一天数据）
  RTO = 4 小时（从备份恢复到可用）

## 🔴 2026-09-04：storage 根解析口径修正

原实现 ``STORAGE_DIR = Path(os.environ.get("STORAGE_ROOT", "storage"))`` 相对 **cwd**
解析。本脚本从仓库根跑，后端进程却以 ``backend/`` 为 cwd ⇒ 同一个 ``"./storage"``
指向两个不同目录：

* 后端实际写入 ``backend/storage/`` —— 实测 2308 个文件 / 655 个子目录，最近写入当天
* 本脚本备份 ``<repo>/storage/`` —— 实测 281 个文件，最近写入 2026-09-01（陈旧）

即**备份每天"成功"，备的却是错的目录**。且原实现里根不存在时返回 ``skipped``，
而 ``main()`` 的失败判定只查 ``status == "failed"`` ⇒ 连"什么都没备"也是退出码 0。

现改为：根解析走 ``_storage_roots.backup_scan_roots()``（相对 ``backend/`` 解析，
并把仓库根的历史 storage 一并纳入），且**解析不出任何根即 failed，不再 skipped**。
"""

import os
import sys
import shutil
import hashlib
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _storage_roots import (  # noqa: E402  —— 需先补 sys.path
    StorageRootResolutionError,
    backup_scan_roots,
    describe_scan_roots,
)

BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", "backups"))
RETENTION_DAYS = int(os.environ.get("BACKUP_RETENTION_DAYS", "30"))


def get_timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def backup_database(backup_path: Path) -> dict:
    """pg_dump 全量备份"""
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("WARNING: DATABASE_URL not set, skipping database backup")
        return {"status": "skipped", "reason": "DATABASE_URL not set"}

    dump_file = backup_path / "database.sql.gz"
    try:
        # 使用 pg_dump + gzip
        cmd = f'pg_dump "{db_url}" | gzip > "{dump_file}"'
        subprocess.run(cmd, shell=True, check=True, timeout=600)
        size = dump_file.stat().st_size
        print(f"  Database backup: {size / 1024 / 1024:.1f} MB")
        return {"status": "success", "file": str(dump_file), "size": size}
    except Exception as e:
        print(f"  Database backup FAILED: {e}")
        return {"status": "failed", "error": str(e)}


def backup_storage(backup_path: Path) -> dict:
    """复制全部 storage 根。

    根解析见 ``_storage_roots.backup_scan_roots``；每个根落在备份目录下自己的
    ``label`` 子目录里，label 两两不同以免互相覆盖。

    🔴 任一根复制失败即整体 ``failed``；解析不出任何根同样 ``failed``。
    不保留"跳过文件备份仍算成功"的分支。
    """
    print(f"  storage 扫描面：\n{describe_scan_roots()}")
    try:
        roots = backup_scan_roots()
    except StorageRootResolutionError as exc:
        print(f"  Storage backup FAILED: {exc}")
        return {"status": "failed", "error": str(exc)}

    per_root: list[dict] = []
    total_files = 0
    total_size = 0
    failures: list[str] = []

    for root in roots:
        dest = backup_path / root.label
        try:
            shutil.copytree(root.path, dest, dirs_exist_ok=True)
            size = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file())
            count = sum(1 for f in dest.rglob("*") if f.is_file())
            total_files += count
            total_size += size
            per_root.append({
                "label": root.label,
                "source": str(root.path),
                "origin": root.origin,
                "status": "success",
                "files": count,
                "size": size,
            })
            print(f"    {root.label}: {count} files, {size / 1024 / 1024:.1f} MB "
                  f"← {root.path}")
        except Exception as e:  # noqa: BLE001 —— 逐根记账，不吞掉整体失败
            failures.append(f"{root.label}: {e}")
            per_root.append({
                "label": root.label,
                "source": str(root.path),
                "origin": root.origin,
                "status": "failed",
                "error": str(e),
            })
            print(f"    {root.label} FAILED: {e}")

    if failures:
        print(f"  Storage backup FAILED: {'; '.join(failures)}")
        return {
            "status": "failed",
            "error": "; ".join(failures),
            "roots": per_root,
            "files": total_files,
            "size": total_size,
        }

    print(f"  Storage backup: {total_files} files, {total_size / 1024 / 1024:.1f} MB "
          f"（{len(per_root)} 个根）")
    return {
        "status": "success",
        "files": total_files,
        "size": total_size,
        "roots": per_root,
    }


def cleanup_old_backups():
    """清理超过保留期的旧备份"""
    if not BACKUP_DIR.exists():
        return 0
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    removed = 0
    for d in BACKUP_DIR.iterdir():
        if d.is_dir() and d.name.startswith("backup_"):
            try:
                ts = datetime.strptime(d.name.split("_", 1)[1][:15], "%Y%m%d_%H%M%S")
                if ts < cutoff:
                    shutil.rmtree(d)
                    removed += 1
            except (ValueError, IndexError):
                pass
    return removed


def main():
    ts = get_timestamp()
    backup_path = BACKUP_DIR / f"backup_{ts}"
    backup_path.mkdir(parents=True, exist_ok=True)

    print(f"=== 开始备份 {ts} ===")
    print(f"  备份目录: {backup_path}")

    results = {
        "timestamp": ts,
        "backup_path": str(backup_path),
    }

    # 1. 数据库备份
    print("\n[1/3] 数据库备份...")
    results["database"] = backup_database(backup_path)

    # 2. 文件备份
    print("\n[2/3] 文件备份...")
    results["storage"] = backup_storage(backup_path)

    # 3. 清理旧备份
    print("\n[3/3] 清理旧备份...")
    removed = cleanup_old_backups()
    results["cleanup"] = {"removed": removed, "retention_days": RETENTION_DAYS}
    print(f"  清理了 {removed} 个过期备份")

    # 写入备份清单
    manifest = backup_path / "manifest.json"
    with open(manifest, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n=== 备份完成 ===")
    print(f"  清单: {manifest}")

    # 检查是否有失败
    has_failure = any(
        v.get("status") == "failed"
        for v in [results.get("database", {}), results.get("storage", {})]
    )
    if has_failure:
        print("  ⚠️ 存在失败项，请检查！")
        sys.exit(1)


if __name__ == "__main__":
    main()
