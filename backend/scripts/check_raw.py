# -*- coding: utf-8 -*-
import sys, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

async def main():
    from app.core.database import engine
    import sqlalchemy as sa
    async with engine.begin() as conn:
        r = await conn.execute(sa.text("""
            SELECT aux_type, aux_name, aux_dimensions_raw
            FROM tb_aux_balance
            WHERE project_id = '6687b8ce-7a83-4816-bd4a-c2d173d4b683'
              AND year = 2025 AND is_deleted = false
              AND account_code = '1122.01' AND aux_type = '客户'
            LIMIT 3
        """))
        for row in r.fetchall():
            print(f"{row[0]}:{row[1][:30]}")
            raw = row[2] or "NULL"
            print(f"  raw: {raw[:100]}")

asyncio.run(main())
