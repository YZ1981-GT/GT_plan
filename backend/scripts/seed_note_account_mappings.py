"""加载 note_account_mappings_seed.json 到 PG note_account_mappings 表。

幂等：基于 (template_type, report_row_code, note_section_code, wp_code) 唯一约束去重。

用法：
    python backend/scripts/seed_note_account_mappings.py        # 增量插入
    python backend/scripts/seed_note_account_mappings.py --reset  # 清空后重灌
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import text

import asyncio
from app.core.database import engine, async_session

SEED_PATH = ROOT / "data" / "note_account_mappings_seed.json"


async def seed(reset: bool = False) -> dict:
    seed_data = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    entries = seed_data["entries"]

    inserted = 0
    skipped = 0

    async with async_session() as db:
        if reset:
            await db.execute(text("DELETE FROM note_account_mappings"))
            print("[reset] cleared note_account_mappings")

        # 取已存在的 keys 避免重复
        existing = await db.execute(
            text(
                "SELECT template_type, report_row_code, note_section_code, wp_code "
                "FROM note_account_mappings"
            )
        )
        existing_keys = {tuple(row) for row in existing.fetchall()}

        for e in entries:
            key = (
                e["template_type"],
                e["report_row_code"],
                e["note_section_code"],
                e.get("wp_code") or "",
            )
            if key in existing_keys:
                skipped += 1
                continue

            await db.execute(
                text(
                    "INSERT INTO note_account_mappings "
                    "(id, template_type, report_row_code, note_section_code, "
                    " table_index, validation_role, wp_code, fetch_mode) "
                    "VALUES (:id, :tt, :rrc, :nsc, :ti, :vr, :wp, :fm)"
                ),
                {
                    "id": str(uuid4()),
                    "tt": e["template_type"],
                    "rrc": e["report_row_code"],
                    "nsc": e["note_section_code"],
                    "ti": e.get("table_index", 0),
                    "vr": e.get("validation_role"),
                    "wp": e.get("wp_code"),
                    "fm": e.get("fetch_mode"),
                },
            )
            inserted += 1

        await db.commit()

    return {"inserted": inserted, "skipped": skipped, "total_seed": len(entries)}


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="清空 note_account_mappings 后重灌")
    args = parser.parse_args()

    result = await seed(reset=args.reset)
    print(f"\n✓ Done")
    print(f"  Inserted: {result['inserted']}")
    print(f"  Skipped (already exists): {result['skipped']}")
    print(f"  Total seed entries: {result['total_seed']}")


if __name__ == "__main__":
    asyncio.run(main())
