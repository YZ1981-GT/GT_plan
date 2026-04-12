import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def check_tables():
    engine = create_async_engine('postgresql+asyncpg://postgres:postgres@localhost:5432/audit_platform')
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
        print('Tables:')
        for row in result:
            print(f'  - {row[0]}')
    await engine.dispose()

if __name__ == '__main__':
    asyncio.run(check_tables())
