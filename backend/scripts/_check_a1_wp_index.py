"""临时检查脚本：查看A1相关wp_index记录"""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings

async def check():
    engine = create_async_engine(settings.DATABASE_URL, pool_size=2)
    async with engine.begin() as conn:
        r = await conn.execute(text(
            "SELECT wi.wp_code, wi.id, wp.id as wp_id "
            "FROM wp_index wi "
            "LEFT JOIN working_paper wp ON wp.wp_index_id = wi.id "
            "WHERE wi.wp_code LIKE 'A1%' "
            "ORDER BY wi.wp_code LIMIT 30"
        ))
        rows = r.fetchall()
        print(f"A1* wp_index records: {len(rows)}")
        for row in rows:
            wp_id_str = str(row[2])[:12] if row[2] else "NULL"
            print(f"  {row[0]:12s} wi.id={str(row[1])[:12]}... wp.id={wp_id_str}...")

        # Check projects table name
        r2 = await conn.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name IN ('projects', 'project') AND table_schema = 'public'"
        ))
        tables = r2.fetchall()
        print(f"\nProject tables found: {[t[0] for t in tables]}")

        # Try to get project count
        for tname in [t[0] for t in tables]:
            r3 = await conn.execute(text(f"SELECT count(*) FROM {tname}"))
            cnt = r3.scalar()
            print(f"  {tname}: {cnt} rows")

    await engine.dispose()

asyncio.run(check())
