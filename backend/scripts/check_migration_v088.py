"""Check V088 migration status and apply pending migrations via MigrationRunner."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.core.migration_runner import MigrationRunner


async def main() -> None:
    runner = MigrationRunner(database_url=settings.DATABASE_URL)
    result = await runner.run_pending()
    print("Executed migrations:", result.executed)
    if result.failed:
        for f in result.failed:
            print(f"FAILED {f.filename}: {f.error_message[:120]}")
    await runner.close()

    eng = create_async_engine(settings.DATABASE_URL)
    async with eng.connect() as conn:
        versions = (
            await conn.execute(
                sa.text("SELECT version FROM schema_version ORDER BY version DESC LIMIT 5")
            )
        ).fetchall()
        print("Recent schema_version:", [v[0] for v in versions])
        col = (
            await conn.execute(
                sa.text(
                    """
                    SELECT character_maximum_length
                    FROM information_schema.columns
                    WHERE table_name = 'checklist_responses' AND column_name = 'conclusion'
                    """
                )
            )
        ).scalar_one_or_none()
        print("checklist_responses.conclusion max_length:", col)
    await eng.dispose()


if __name__ == "__main__":
    asyncio.run(main())
