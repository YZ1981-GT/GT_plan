"""迁移版本冲突检查（pre-commit hook）。

扫描 backend/migrations/V*.sql 文件，提取版本号，检测重复。
同时检查 R*.sql 回滚文件是否与 V* 配对（缺失回滚仅警告）。

D6 MigrationRunner 按版本号顺序执行，重复版本号会导致：
- 后一个同版本迁移被跳过（静默丢失）
- 或启动时报错中断整条管线

用法：
    python backend/scripts/check/check_migration_versions.py

退出码：
    0 - 无版本冲突
    1 - 存在重复版本号
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = ROOT / "backend" / "migrations"

# 从文件名提取版本号：V001__xxx.sql → 1, V028__xxx.sql → 28
VERSION_RE = re.compile(r"^V(\d+)__.*\.sql$")
ROLLBACK_RE = re.compile(r"^R(\d+)__.*\.sql$")


def extract_version(filename: str, pattern: re.Pattern[str]) -> int | None:
    """从文件名提取版本号整数。"""
    m = pattern.match(filename)
    if m:
        return int(m.group(1))
    return None


def main() -> int:
    if not MIGRATIONS_DIR.exists():
        print("迁移目录不存在，跳过检查", file=sys.stderr)
        return 0

    # 收集 V*.sql 版本号 → 文件名列表
    version_files: dict[int, list[str]] = {}
    for f in sorted(MIGRATIONS_DIR.iterdir()):
        if not f.is_file():
            continue
        ver = extract_version(f.name, VERSION_RE)
        if ver is not None:
            version_files.setdefault(ver, []).append(f.name)

    # 收集 R*.sql 回滚版本号
    rollback_versions: dict[int, list[str]] = {}
    for f in sorted(MIGRATIONS_DIR.iterdir()):
        if not f.is_file():
            continue
        ver = extract_version(f.name, ROLLBACK_RE)
        if ver is not None:
            rollback_versions.setdefault(ver, []).append(f.name)

    # 检测重复版本号
    duplicates: dict[int, list[str]] = {}
    for ver, files in version_files.items():
        if len(files) > 1:
            duplicates[ver] = files

    has_error = False

    if duplicates:
        has_error = True
        print(f"❌ 发现 {len(duplicates)} 个重复迁移版本号：", file=sys.stderr)
        for ver in sorted(duplicates.keys()):
            files = duplicates[ver]
            print(f"  V{ver:03d} ({len(files)} 个文件):", file=sys.stderr)
            for fname in files:
                print(f"    - {fname}", file=sys.stderr)
        print("\n请修改文件名使版本号唯一（D6 MigrationRunner 按版本号顺序执行）。", file=sys.stderr)

    # 检查 V* 是否有对应 R*（仅警告，不阻断）
    missing_rollback: list[int] = []
    for ver in sorted(version_files.keys()):
        if ver not in rollback_versions:
            missing_rollback.append(ver)

    if missing_rollback:
        print(f"\n⚠️  {len(missing_rollback)} 个迁移缺少回滚文件（仅警告）：")
        for ver in missing_rollback:
            files = version_files[ver]
            print(f"  V{ver:03d}: {', '.join(files)} → 缺少 R{ver:03d}__*.sql")

    # 同时检查 R* 重复
    rollback_duplicates: dict[int, list[str]] = {}
    for ver, files in rollback_versions.items():
        if len(files) > 1:
            rollback_duplicates[ver] = files

    if rollback_duplicates:
        print(f"\n⚠️  {len(rollback_duplicates)} 个重复回滚版本号（仅警告）：")
        for ver in sorted(rollback_duplicates.keys()):
            files = rollback_duplicates[ver]
            print(f"  R{ver:03d} ({len(files)} 个文件):")
            for fname in files:
                print(f"    - {fname}")

    if not has_error and not duplicates:
        total_v = sum(len(fs) for fs in version_files.values())
        total_r = sum(len(fs) for fs in rollback_versions.values())
        print(f"✅ 迁移版本无冲突（V: {total_v} 个, R: {total_r} 个）")

    return 1 if has_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
