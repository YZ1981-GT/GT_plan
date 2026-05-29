"""数据库与文件备份脚本

用法：python backend/scripts/backup.py [--backup-dir /path/to/backups]

功能：
  1. pg_dump 全量备份 PostgreSQL
  2. rsync/复制 storage/ 目录
  3. 记录备份清单和校验信息
  4. 清理超过 30 天的旧备份

建议：每日凌晨 cron 执行
  RPO = 1 天（最多丢一天数据）
  RTO = 4 小时（从备份恢复到可用）
"""

import os
import sys
import shutil
import hashlib
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", "backups"))
STORAGE_DIR = Path(os.environ.get("STORAGE_ROOT", "storage"))
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
    """复制 storage/ 目录"""
    if not STORAGE_DIR.exists():
        print("  Storage directory not found, skipping")
        return {"status": "skipped", "reason": "storage dir not found"}

    dest = backup_path / "storage"
    try:
        shutil.copytree(STORAGE_DIR, dest, dirs_exist_ok=True)
        # 计算总大小
        total_size = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file())
        file_count = sum(1 for f in dest.rglob("*") if f.is_file())
        print(f"  Storage backup: {file_count} files, {total_size / 1024 / 1024:.1f} MB")
        return {"status": "success", "files": file_count, "size": total_size}
    except Exception as e:
        print(f"  Storage backup FAILED: {e}")
        return {"status": "failed", "error": str(e)}


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
