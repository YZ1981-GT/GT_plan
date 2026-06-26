import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings

async def f():
    engine = create_async_engine(settings.DATABASE_URL, pool_size=2)
    async with engine.begin() as c:
        r = await c.execute(text(
            "SELECT wp.id, wi.wp_code FROM working_paper wp "
            "JOIN wp_index wi ON wp.wp_index_id = wi.id "
            "WHERE wi.wp_code = 'A1' "
            "AND wi.project_id = '0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49'"
        ))
        rows = r.fetchall()
        for row in rows:
            print(f"{row[1]} wp_id={row[0]}")
    await engine.dispose()

asyncio.run(f())
