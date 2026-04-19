# -*- coding: utf-8 -*-
import asyncio
import sys
import uuid
import json

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

async def main():
    from app.core.database import engine
    import sqlalchemy as sa

    pid = uuid.uuid4()
    ws = json.dumps({
        "steps": {
            "basic_info": {
                "data": {
                    "client_name": "重庆和平药房连锁有限责任公司",
                    "audit_year": 2025,
                }
            }
        }
    })

    async with engine.begin() as conn:
        await conn.execute(
            sa.text(
                "INSERT INTO projects (id, name, client_name, status, wizard_state, version, consol_level, is_deleted) "
                "VALUES (:id, :name, :cname, 'planning', CAST(:ws AS jsonb), 1, 1, false)"
            ),
            {"id": str(pid), "name": "重庆和平药房连锁有限责任公司", "cname": "重庆和平药房连锁有限责任公司", "ws": ws},
        )
    print(f"Created project: {pid}")

asyncio.run(main())
