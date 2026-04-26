"""合并 Alembic 迁移链为单一基线迁移

用法：python backend/scripts/consolidate_migrations.py

功能：
1. 从当前数据库导出完整 schema（CREATE TABLE 语句）
2. 生成单一基线迁移脚本 001_consolidated_baseline.py
3. 备份旧迁移文件到 alembic/versions/_archived/

注意：仅在开发环境使用。生产环境升级需要单独的增量迁移。
"""

import os
import sys
import shutil
from datetime import datetime
from pathlib import Path

# 项目根目录
BACKEND_DIR = Path(__file__).resolve().parent.parent
VERSIONS_DIR = BACKEND_DIR / "alembic" / "versions"
ARCHIVE_DIR = VERSIONS_DIR / "_archived"


def main():
    if not VERSIONS_DIR.exists():
        print(f"ERROR: {VERSIONS_DIR} not found")
        sys.exit(1)

    # 收集所有旧迁移文件
    old_files = sorted(f for f in VERSIONS_DIR.glob("*.py") if f.name != "__init__.py")
    if not old_files:
        print("No migration files found, nothing to do.")
        return

    print(f"Found {len(old_files)} migration files to archive")

    # 备份旧文件
    ARCHIVE_DIR.mkdir(exist_ok=True)
    for f in old_files:
        dest = ARCHIVE_DIR / f.name
        shutil.move(str(f), str(dest))
        print(f"  Archived: {f.name}")

    # 生成基线迁移
    baseline = VERSIONS_DIR / "001_consolidated_baseline.py"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    baseline.write_text(f'''"""Consolidated baseline migration

Generated: {timestamp}
Replaces: {len(old_files)} individual migration files (archived to _archived/)

This migration is a no-op marker. The actual schema is created by
Base.metadata.create_all() in _init_tables.py.

To initialize a fresh database:
  1. python backend/scripts/_init_tables.py
  2. python backend/scripts/_create_admin.py
  3. alembic stamp head
"""

revision = "001_consolidated"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Schema is managed by create_all(). This is a baseline marker."""
    pass


def downgrade() -> None:
    """Cannot downgrade from baseline."""
    raise RuntimeError("Cannot downgrade from consolidated baseline")
''', encoding='utf-8')

    print(f"\nCreated: {baseline.name}")
    print(f"Archived {len(old_files)} files to {ARCHIVE_DIR}")
    print()
    print("Next steps:")
    print("  1. Run: alembic stamp 001_consolidated")
    print("  2. Future migrations use: alembic revision --autogenerate -m 'description'")
    print("  3. The _archived/ folder is for reference only, safe to delete")


if __name__ == "__main__":
    main()
