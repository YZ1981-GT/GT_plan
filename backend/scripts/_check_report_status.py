"""Check report_config formula coverage and projects with trial_balance data."""
import asyncio, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for line in Path(Path(__file__).resolve().parent.parent / ".env").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip().strip('"')

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.config import settings


async def main():
    url = settings.DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url)
    async_session = sessionmaker(engine, class_=AsyncSession)
    async with async_session() as db:
        r = await db.execute(sa.text(
            "SELECT p.id, p.name, COUNT(tb.id) as tb_count "
            "FROM projects p "
            "JOIN trial_balance tb ON tb.project_id = p.id AND tb.is_deleted = false "
            "GROUP BY p.id, p.name "
            "ORDER BY tb_count DESC LIMIT 5"
        ))
        rows = r.fetchall()
        print("Projects with trial_balance data:")
        for row in rows:
            print(f"  {row[0]} | {row[1]} | {row[2]} rows")

        r2 = await db.execute(sa.text(
            "SELECT applicable_standard, report_type, "
            "COUNT(*) as total, COUNT(formula) as with_formula "
            "FROM report_config WHERE is_deleted = false "
            "GROUP BY applicable_standard, report_type "
            "ORDER BY applicable_standard, report_type"
        ))
        print("\nReport config formula coverage:")
        for row in r2.fetchall():
            pct = row[3] / row[2] * 100 if row[2] > 0 else 0
            print(f"  {row[0]:25s} | {row[1]:25s} | {row[3]:3d}/{row[2]:3d} ({pct:.0f}%)")

    await engine.dispose()

asyncio.run(main())
