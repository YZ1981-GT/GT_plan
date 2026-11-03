"""创建公式 E2E 一次性库 gt_e2e_formula 并跑迁移 — ADR-FEC-05。

用法::

    python backend/scripts/e2e/create_formula_e2e_db.py

前置：PG 在 localhost:5432 且 postgres 超级用户可连。
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

DB_NAME = "gt_e2e_formula"
# asyncpg 需要先连到已有库来创建新库
ADMIN_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"
TARGET_URL = f"postgresql+asyncpg://postgres:postgres@localhost:5432/{DB_NAME}"


async def main() -> int:
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import create_async_engine

    # 1. 建库（幂等）
    engine = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        exists = await conn.scalar(
            sa.text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": DB_NAME},
        )
        if not exists:
            await conn.execute(sa.text(f'CREATE DATABASE "{DB_NAME}"'))
            print(f"✅ 库 {DB_NAME} 已创建")
        else:
            print(f"ℹ️  库 {DB_NAME} 已存在，跳过创建")
    await engine.dispose()

    # 2. 跑迁移
    from app.core.migration_runner import MigrationRunner

    runner = MigrationRunner(database_url=TARGET_URL)
    await runner.run_pending()
    print(f"✅ 迁移完成（{TARGET_URL}）")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
