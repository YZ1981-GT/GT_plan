"""一次性检查迁移状态（不执行迁移）。"""
from __future__ import annotations

import asyncio

from sqlalchemy import text

from app.core.config import settings
from app.core.migration_runner import MigrationRunner


async def main() -> None:
    runner = MigrationRunner(database_url=settings.DATABASE_URL)
    try:
        applied = await runner.get_applied_versions()
        all_migrations = runner.scan_migrations()
        pending = [m for m in all_migrations if m.version not in applied]
        db_tail = settings.DATABASE_URL.split("@")[-1] if "@" in settings.DATABASE_URL else settings.DATABASE_URL
        print("DATABASE:", db_tail)
        print("applied count:", len(applied))
        for v in ("025", "052"):
            key = v.zfill(3)
            print(f"  V{v} applied:", key in applied)
        print(
            "pending (first 20):",
            [(m.version, m.filename) for m in pending[:20]],
        )
        print("pending total:", len(pending))
        async with runner._engine.connect() as conn:
            wp = await conn.execute(text("SELECT to_regclass('public.wp_formula')"))
            smf = await conn.execute(text("SELECT to_regclass('public.schema_migration_failures')"))
            print("wp_formula exists:", wp.scalar())
            print("schema_migration_failures exists:", smf.scalar())
            rows = await conn.execute(
                text(
                    "SELECT version, filename, applied_at FROM schema_version "
                    "WHERE version IN ('025', '052') ORDER BY version"
                )
            )
            print("schema_version rows:", [tuple(r) for r in rows])
            cols = await conn.execute(
                text(
                    "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'wp_formula' "
                    "ORDER BY ordinal_position"
                )
            )
            print("wp_formula columns:", [tuple(r) for r in cols])
            uq = await conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE tablename = 'wp_formula' ORDER BY indexname"
                )
            )
            print("wp_formula indexes:", [r[0] for r in uq])
    finally:
        await runner.close()


if __name__ == "__main__":
    asyncio.run(main())
