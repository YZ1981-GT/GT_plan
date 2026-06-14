import asyncio, sqlalchemy as sa
from app.core.database import async_engine
from sqlalchemy.ext.asyncio import AsyncSession

async def main():
    async with AsyncSession(async_engine) as db:
        r = await db.execute(sa.text(
            "SELECT wp.id, wi.wp_code, wi.wp_name "
            "FROM working_paper wp "
            "JOIN wp_index wi ON wi.id = wp.wp_index_id "
            "WHERE wp.project_id = '37814426-a29e-4fc2-9313-a59d229bf7b0' "
            "AND wi.wp_code LIKE 'A%' "
            "AND wp.is_deleted = false "
            "ORDER BY wi.wp_code"
        ))
        for wid, code, name in r.all():
            print(f"{code} | {wid} | {name}")

asyncio.run(main())
