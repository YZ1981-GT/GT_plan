"""Check D1 sheet classification in DB."""
import asyncio, sys
sys.path.insert(0, "backend")

async def main():
    from app.core.database import async_engine
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import text
    async with AsyncSession(async_engine) as db:
        r = await db.execute(text(
            "SELECT wp_code, sheet_name, class_code FROM workpaper_sheet_classification "
            "WHERE wp_code = 'D1' ORDER BY sheet_name"
        ))
        rows = r.fetchall()
        print(f"D1 classifications: {len(rows)}")
        for row in rows:
            print(f"  {row[1]:40s} -> {row[2]}")

asyncio.run(main())
