"""Read one checklist response for Playwright Round_Trip evidence (read-only)."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.core.database import async_session, dispose_engine  # noqa: E402


async def main(wp_id: str, item_id: str) -> None:
    async with async_session() as db:
        row = (
            await db.execute(
                text(
                    """SELECT wp_id, item_id, remark, conclusion, updated_at
                       FROM checklist_responses
                       WHERE wp_id = :wp_id AND item_id = :item_id"""
                ),
                {"wp_id": wp_id, "item_id": item_id},
            )
        ).mappings().first()
    payload = dict(row) if row else None
    print("CHECKLIST_DB_RESULT=" + json.dumps(payload, ensure_ascii=False, default=str))
    await dispose_engine()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: read_checklist_response.py <wp_id> <item_id>")
    asyncio.run(main(sys.argv[1], sys.argv[2]))
