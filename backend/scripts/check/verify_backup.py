"""备份恢复验证脚本 — 自动化抽样核对

用法：python backend/scripts/check/verify_backup.py [backup_dir]

功能：
  1. 检查备份清单完整性（manifest.json）
  2. 验证数据库备份文件可读
  3. 抽样核对 storage 文件（哈希比对）
  4. 模拟恢复流程（dry-run）
  5. 输出验证报告

验收标准：底稿文件、附件元数据、归档清单三者一致

## 🔴 2026-09-04：storage 根口径与两处 fail-open 修正

原实现有三个问题，叠在一起会让"备份校验通过"变成一句空话：

1. ``STORAGE_DIR = Path("storage")`` **硬编码**，连 ``STORAGE_ROOT`` 都不读，
   更没有考虑后端 cwd 是 ``backend/`` ⇒ 比对的原始目录本来就不是运行时落点。
2. ``verify_storage_files``：备份里没有 ``storage/`` 子目录时 ``return {"passed": True}``
   —— 什么都没备份反而判通过。
3. 同一函数：``backup_files`` 为空时同样 ``passed: True`` —— 空集上恒真。

现改为：原始根从 manifest 的 ``storage.roots`` 逐根回溯（口径与 ``backup.py`` 同源，
见 ``scripts/_storage_roots.py``）；上面两处改为 **failed**。
"""

import json
import hashlib
import random
import sys
from pathlib import Path
from datetime import datetime

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _storage_roots import backup_scan_roots  # noqa: E402  —— 需先补 sys.path


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


def _resolve_backed_up_roots(backup_path: Path, manifest: dict) -> list[tuple[Path, Path, str]]:
    """得出 (备份内目录, 原始根, label) 三元组。

    优先读 manifest 的 ``storage.roots``（``backup.py`` 现写的形态）；旧备份没有该
    字段时回落到当前解析口径的 ``storage`` label，并在 label 上标注 ``legacy-manifest``
    以便报告里能看出这次比对的原始根是**推断**来的而非备份时记录的。
    """
    declared = (manifest.get("storage") or {}).get("roots") or []
    triples: list[tuple[Path, Path, str]] = []
    for entry in declared:
        label = entry.get("label")
        source = entry.get("source")
        if not label or not source:
            continue
        triples.append((backup_path / label, Path(source), label))
    if triples:
        return triples

    for root in backup_scan_roots(require_existing=False):
        candidate = backup_path / root.label
        if candidate.is_dir():
            triples.append((candidate, root.path, f"{root.label} (legacy-manifest)"))
    return triples


def verify_storage_files(backup_path: Path, manifest: dict, sample_count: int = 20) -> dict:
    """抽样核对 storage 文件哈希。

    🔴 「备份里没有 storage 目录」与「备份里一个文件都没有」一律判 **failed**。
    原实现这两处都 ``passed: True``，等于备份校验在最该报警的情形下保持沉默。
    """
    triples = _resolve_backed_up_roots(backup_path, manifest)
    if not triples:
        return {
            "passed": False,
            "detail": "备份里找不到任何 storage 根目录 —— 文件备份缺失，不是可跳过的情形",
            "total_files": 0,
            "sampled": 0,
            "mismatches": 0,
            "roots": [],
            "samples": [],
        }

    per_root: list[dict] = []
    all_results: list[dict] = []
    total_files = 0
    total_sampled = 0
    total_mismatches = 0
    empty_roots: list[str] = []

    for backup_root, original_root, label in triples:
        if not backup_root.is_dir():
            per_root.append({
                "label": label, "passed": False,
                "detail": f"备份内缺目录 {backup_root.name}",
                "total_files": 0, "sampled": 0, "mismatches": 0,
            })
            empty_roots.append(label)
            continue

        backup_files = [f for f in backup_root.rglob("*") if f.is_file()]
        total_files += len(backup_files)
        if not backup_files:
            per_root.append({
                "label": label, "passed": False,
                "detail": "该根备份内 0 个文件",
                "total_files": 0, "sampled": 0, "mismatches": 0,
            })
            empty_roots.append(label)
            continue

        samples = random.sample(backup_files, min(sample_count, len(backup_files)))
        mismatches = 0
        for bf in samples:
            rel = bf.relative_to(backup_root)
            original = original_root / rel
            record = {"root": label, "file": str(rel)}

            if not original.exists():
                record.update({"status": "original_missing", "passed": False})
                mismatches += 1
            else:
                backup_hash = hashlib.sha256(bf.read_bytes()).hexdigest()[:16]
                original_hash = hashlib.sha256(original.read_bytes()).hexdigest()[:16]
                if backup_hash == original_hash:
                    record.update({"status": "match", "passed": True})
                else:
                    record.update({
                        "status": "hash_mismatch", "passed": False,
                        "backup_hash": backup_hash, "original_hash": original_hash,
                    })
                    mismatches += 1
            all_results.append(record)

        total_sampled += len(samples)
        total_mismatches += mismatches
        per_root.append({
            "label": label,
            "passed": mismatches == 0,
            "source": str(original_root),
            "total_files": len(backup_files),
            "sampled": len(samples),
            "mismatches": mismatches,
        })

    return {
        "passed": total_mismatches == 0 and not empty_roots,
        "total_files": total_files,
        "sampled": total_sampled,
        "mismatches": total_mismatches,
        "empty_roots": empty_roots,
        "roots": per_root,
        "samples": all_results,
    }


def verify_workpaper_consistency(backup_path: Path, manifest: dict) -> dict:
    """验证底稿文件与数据库记录一致性（需要数据库连接）"""
    wp_files: list[str] = []
    for backup_root, _original_root, label in _resolve_backed_up_roots(backup_path, manifest):
        if not backup_root.is_dir():
            continue
        for p in backup_root.rglob("*.xlsx"):
            if "workpapers" in str(p):
                wp_files.append(f"{label}/{p.relative_to(backup_root)}")

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
    manifest = manifest_result.get("manifest") or {}
    storage_result = verify_storage_files(backup_path, manifest)
    for r in storage_result.get("roots", []):
        icon = "✅" if r.get("passed") else "❌"
        detail = r.get("detail") or (
            f"{r.get('total_files', 0)} files, 抽样 {r.get('sampled', 0)}, "
            f"不匹配 {r.get('mismatches', 0)}"
        )
        print(f"  {icon} {r.get('label')}: {detail}")
    print(f"  合计总文件: {storage_result.get('total_files', 0)}")
    print(f"  合计抽样: {storage_result.get('sampled', 0)}")
    print(f"  合计不匹配: {storage_result.get('mismatches', 0)}")
    if storage_result["passed"]:
        print("  ✅ 抽样核对通过")
    else:
        if storage_result.get("detail"):
            print(f"  ❌ {storage_result['detail']}")
        if storage_result.get("empty_roots"):
            print(f"  ❌ 空/缺失的根: {', '.join(storage_result['empty_roots'])}")
        for s in storage_result.get("samples", []):
            if not s["passed"]:
                print(f"    - {s['root']}/{s['file']}: {s['status']}")

    # 3. 底稿一致性
    print("\n[3/3] 底稿文件检查...")
    wp_result = verify_workpaper_consistency(backup_path, manifest)
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
