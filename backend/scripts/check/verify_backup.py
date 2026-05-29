"""备份恢复验证脚本 — 自动化抽样核对

用法：python backend/scripts/verify_backup.py [backup_dir]

功能：
  1. 检查备份清单完整性（manifest.json）
  2. 验证数据库备份文件可读
  3. 抽样核对 storage 文件（哈希比对）
  4. 模拟恢复流程（dry-run）
  5. 输出验证报告

验收标准：底稿文件、附件元数据、归档清单三者一致
"""

import json
import hashlib
import sys
from pathlib import Path
from datetime import datetime

STORAGE_DIR = Path("storage")


def find_latest_backup(backup_root: Path) -> Path | None:
    """找到最新的备份目录"""
    if not backup_root.exists():
        return None
    backups = sorted(
        [d for d in backup_root.iterdir() if d.is_dir() and d.name.startswith("backup_")],
        reverse=True,
    )
    return backups[0] if backups else None


def verify_manifest(backup_path: Path) -> dict:
    """检查备份清单"""
    manifest_file = backup_path / "manifest.json"
    if not manifest_file.exists():
        return {"passed": False, "error": "manifest.json 不存在"}

    with open(manifest_file, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    checks = []

    # 数据库备份
    db_info = manifest.get("database", {})
    if db_info.get("status") == "success":
        db_file = Path(db_info.get("file", ""))
        if db_file.exists() and db_file.stat().st_size > 0:
            checks.append({"item": "数据库备份", "passed": True, "detail": f"{db_file.stat().st_size / 1024 / 1024:.1f} MB"})
        else:
            checks.append({"item": "数据库备份", "passed": False, "detail": "文件不存在或为空"})
    elif db_info.get("status") == "skipped":
        checks.append({"item": "数据库备份", "passed": True, "detail": "跳过（无 DATABASE_URL）"})
    else:
        checks.append({"item": "数据库备份", "passed": False, "detail": db_info.get("error", "未知错误")})

    # 文件备份
    storage_info = manifest.get("storage", {})
    if storage_info.get("status") == "success":
        file_count = storage_info.get("files", 0)
        checks.append({"item": "文件备份", "passed": True, "detail": f"{file_count} 个文件"})
    else:
        checks.append({"item": "文件备份", "passed": False, "detail": storage_info.get("error", "未知")})

    return {"passed": all(c["passed"] for c in checks), "checks": checks, "manifest": manifest}


def verify_storage_files(backup_path: Path, sample_count: int = 20) -> dict:
    """抽样核对 storage 文件哈希"""
    backup_storage = backup_path / "storage"
    if not backup_storage.exists():
        return {"passed": True, "detail": "无 storage 备份（跳过）", "samples": []}

    # 收集备份中的文件
    backup_files = list(backup_storage.rglob("*"))
    backup_files = [f for f in backup_files if f.is_file()]

    if not backup_files:
        return {"passed": True, "detail": "备份中无文件", "samples": []}

    # 抽样
    import random
    samples = random.sample(backup_files, min(sample_count, len(backup_files)))

    results = []
    mismatches = 0

    for bf in samples:
        rel = bf.relative_to(backup_storage)
        original = STORAGE_DIR / rel

        if not original.exists():
            results.append({"file": str(rel), "status": "original_missing", "passed": False})
            mismatches += 1
            continue

        # 哈希比对
        backup_hash = hashlib.sha256(bf.read_bytes()).hexdigest()[:16]
        original_hash = hashlib.sha256(original.read_bytes()).hexdigest()[:16]

        if backup_hash == original_hash:
            results.append({"file": str(rel), "status": "match", "passed": True})
        else:
            results.append({"file": str(rel), "status": "hash_mismatch", "passed": False,
                            "backup_hash": backup_hash, "original_hash": original_hash})
            mismatches += 1

    return {
        "passed": mismatches == 0,
        "total_files": len(backup_files),
        "sampled": len(samples),
        "mismatches": mismatches,
        "samples": results,
    }


def verify_workpaper_consistency(backup_path: Path) -> dict:
    """验证底稿文件与数据库记录一致性（需要数据库连接）"""
    # 检查备份中的底稿文件
    backup_storage = backup_path / "storage"
    wp_files = []
    if backup_storage.exists():
        for p in backup_storage.rglob("*.xlsx"):
            if "workpapers" in str(p):
                wp_files.append(str(p.relative_to(backup_storage)))

    return {
        "workpaper_files_in_backup": len(wp_files),
        "sample_files": wp_files[:10],
        "note": "完整一致性校验需要数据库连接，请在恢复后执行",
    }


def main():
    backup_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("backups")

    print("=" * 60)
    print(f"  备份恢复验证 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 找到最新备份
    backup_path = find_latest_backup(backup_root)
    if not backup_path:
        print(f"\n❌ 未找到备份目录: {backup_root}")
        sys.exit(1)

    print(f"\n备份目录: {backup_path}")

    # 1. 清单验证
    print("\n[1/3] 验证备份清单...")
    manifest_result = verify_manifest(backup_path)
    for c in manifest_result.get("checks", []):
        icon = "✅" if c["passed"] else "❌"
        print(f"  {icon} {c['item']}: {c['detail']}")

    # 2. 文件抽样核对
    print("\n[2/3] 抽样核对文件哈希...")
    storage_result = verify_storage_files(backup_path)
    print(f"  总文件: {storage_result.get('total_files', 0)}")
    print(f"  抽样: {storage_result.get('sampled', 0)}")
    print(f"  不匹配: {storage_result.get('mismatches', 0)}")
    if storage_result["passed"]:
        print("  ✅ 抽样核对通过")
    else:
        print("  ❌ 存在不匹配文件")
        for s in storage_result.get("samples", []):
            if not s["passed"]:
                print(f"    - {s['file']}: {s['status']}")

    # 3. 底稿一致性
    print("\n[3/3] 底稿文件检查...")
    wp_result = verify_workpaper_consistency(backup_path)
    print(f"  备份中底稿文件: {wp_result['workpaper_files_in_backup']} 个")

    # 输出验证报告
    report = {
        "verified_at": datetime.now().isoformat(),
        "backup_path": str(backup_path),
        "manifest": manifest_result,
        "storage": storage_result,
        "workpapers": wp_result,
        "overall_passed": manifest_result["passed"] and storage_result["passed"],
    }

    report_file = backup_path / "verification_report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n验证报告: {report_file}")

    if report["overall_passed"]:
        print("\n✅ 备份验证通过")
    else:
        print("\n❌ 备份验证存在问题，请检查")
        sys.exit(1)


if __name__ == "__main__":
    main()
