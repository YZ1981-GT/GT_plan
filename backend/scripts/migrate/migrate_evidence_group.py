"""迁移脚本：voucher_row attachment_id → evidence_group JSONB 数组

将 parsed_data.voucher_rows 中的单值 attachment_id 升级为 evidence_group 数组。
幂等：已有 evidence_group 的行跳过。

用法：
  python backend/scripts/migrate/migrate_evidence_group.py [--dry-run]
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# 确保 backend 在 sys.path
backend_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(backend_dir))


async def migrate_evidence_group(dry_run: bool = False):
    """将 voucher_rows 中 attachment_id 单值升级为 evidence_group 数组"""
    from app.core.database import get_engine
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    engine = get_engine()
    async with AsyncSession(engine) as db:
        # 查找所有有 voucher_rows 的底稿
        result = await db.execute(text(
            "SELECT id, parsed_data FROM working_papers "
            "WHERE parsed_data::text LIKE '%voucher_rows%'"
        ))
        rows = result.fetchall()
        print(f"找到 {len(rows)} 个含 voucher_rows 的底稿")

        migrated = 0
        for row in rows:
            wp_id, parsed_data = row
            if not parsed_data:
                continue

            voucher_rows = parsed_data.get("voucher_rows", [])
            changed = False

            for vr in voucher_rows:
                # 已有 evidence_group 则跳过
                if "evidence_group" in vr:
                    continue

                # 将 attachment_id 单值转为 evidence_group 数组
                att_id = vr.pop("attachment_id", None)
                if att_id:
                    vr["evidence_group"] = [{
                        "attachment_id": att_id,
                        "source": "legacy_migration",
                    }]
                else:
                    vr["evidence_group"] = []
                changed = True

            if changed:
                parsed_data["voucher_rows"] = voucher_rows
                if not dry_run:
                    await db.execute(text(
                        "UPDATE working_papers SET parsed_data = :pd::jsonb WHERE id = :wid"
                    ), {
                        "pd": json.dumps(parsed_data, ensure_ascii=False, default=str),
                        "wid": str(wp_id),
                    })
                migrated += 1

        if not dry_run:
            await db.commit()

        print(f"{'[DRY-RUN] ' if dry_run else ''}迁移完成: {migrated} 个底稿已升级")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    asyncio.run(migrate_evidence_group(dry_run))
