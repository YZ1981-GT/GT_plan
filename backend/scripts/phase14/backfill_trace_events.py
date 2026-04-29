"""Phase 14: 历史审计日志回填到 trace_events

从 audit_logs / logs 表读取关键事件，映射到 trace_events 字段。
标记 reason_code='BACKFILL_MIGRATION' 与正常事件区分。

用法: python -m scripts.phase14.backfill_trace_events [--dry-run]
"""
import asyncio
import sys
import uuid
from datetime import datetime

# 事件类型映射
EVENT_TYPE_MAP = {
    "workpaper_online_save": "wp_saved",
    "workpaper_online_open": "wopi_access",
    "submit_review": "submit_review",
    "review_passed": "review_passed",
    "review_returned": "review_returned",
}

BATCH_SIZE = 1000


async def main(dry_run: bool = False):
    from app.core.database import async_engine
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import text

    async with AsyncSession(async_engine) as db:
        # 检查 logs 表是否存在
        try:
            result = await db.execute(text("SELECT COUNT(*) FROM logs"))
            total = result.scalar()
            print(f"[BACKFILL] logs 表共 {total} 条记录")
        except Exception as e:
            print(f"[BACKFILL] logs 表不存在或不可访问: {e}")
            return

        # 分批读取
        offset = 0
        migrated = 0

        while True:
            stmt = text(f"""
                SELECT id, user_id, action_type, object_type, object_id,
                       new_value, created_at
                FROM logs
                WHERE action_type IN :types
                ORDER BY created_at ASC
                LIMIT :limit OFFSET :offset
            """)
            result = await db.execute(stmt, {
                "types": tuple(EVENT_TYPE_MAP.keys()),
                "limit": BATCH_SIZE,
                "offset": offset,
            })
            rows = result.fetchall()
            if not rows:
                break

            for row in rows:
                log_id, user_id, action_type, obj_type, obj_id, new_value, created_at = row
                event_type = EVENT_TYPE_MAP.get(action_type, action_type)

                if dry_run:
                    print(f"  [DRY] {event_type} obj={obj_id} actor={user_id} at={created_at}")
                    migrated += 1
                    continue

                trace_id = f"trc_backfill_{str(uuid.uuid4())[:12]}"
                insert_stmt = text("""
                    INSERT INTO trace_events (id, project_id, event_type, object_type, object_id,
                        actor_id, action, reason_code, trace_id, created_at)
                    VALUES (:id, :pid, :etype, :otype, :oid, :aid, :action, :reason, :tid, :cat)
                    ON CONFLICT DO NOTHING
                """)
                await db.execute(insert_stmt, {
                    "id": str(uuid.uuid4()),
                    "pid": str(new_value.get("project_id", user_id)) if isinstance(new_value, dict) else str(user_id),
                    "etype": event_type,
                    "otype": obj_type or "unknown",
                    "oid": str(obj_id) if obj_id else str(uuid.uuid4()),
                    "aid": str(user_id) if user_id else str(uuid.uuid4()),
                    "action": f"backfill:{action_type}",
                    "reason": "BACKFILL_MIGRATION",
                    "tid": trace_id,
                    "cat": created_at or datetime.utcnow(),
                })
                migrated += 1

            if not dry_run:
                await db.commit()
                print(f"  [COMMIT] batch offset={offset} migrated={migrated}")

            offset += BATCH_SIZE

        print(f"[BACKFILL] 完成: 共迁移 {migrated} 条{'（dry-run）' if dry_run else ''}")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    asyncio.run(main(dry_run))
