"""检查A1-11~A1-16的wp_id是否正确"""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings

async def check():
    engine = create_async_engine(settings.DATABASE_URL, pool_size=2)
    async with engine.begin() as conn:
        r = await conn.execute(text(
            "SELECT wi.wp_code, wi.id as wi_id, wp.id as wp_id "
            "FROM wp_index wi "
            "LEFT JOIN working_paper wp ON wp.wp_index_id = wi.id "
            "WHERE wi.wp_code LIKE 'A1-1%' "
            "AND wi.project_id = '0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49' "
            "ORDER BY wi.wp_code"
        ))
        rows = r.fetchall()
        print(f"A1-1x records for this project:")
        for row in rows:
            wp_id = str(row[2]) if row[2] else "NULL"
            wi_id = str(row[1])
            print(f"  {row[0]:8s} wi_id={wi_id}  wp_id={wp_id}")
            # Check if 96477fac matches any
            if '96477fac' in wi_id or '96477fac' in wp_id:
                print(f"    ^^^ MATCHES the Not Found ID!")
    await engine.dispose()

asyncio.run(check())
