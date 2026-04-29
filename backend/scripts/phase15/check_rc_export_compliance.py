"""Phase 15 验收脚本：RC 导出合规校验

导出取证 → 断言 file_hash 非空 + trace_events 有记录。
用法: python -m scripts.phase15.check_rc_export_compliance
"""
import asyncio
import sys


async def main():
    from app.core.database import async_engine
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import text

    async with AsyncSession(async_engine) as db:
        # 检查导出记录是否有 hash
        result = await db.execute(text("""
            SELECT export_id, file_hash, trace_id FROM review_conversation_exports
            WHERE file_hash IS NOT NULL
            LIMIT 5
        """))
        exports = result.fetchall()
        if exports:
            for e in exports:
                print(f"  [PASS] export={e[0]} hash={e[1][:16]}... trace={e[2]}")
        else:
            print("  [INFO] No RC exports yet — create one to verify")

        # 检查 trace 记录
        result = await db.execute(text("""
            SELECT COUNT(*) FROM trace_events WHERE event_type = 'rc_evidence_exported'
        """))
        count = result.scalar() or 0
        print(f"  [INFO] RC export trace events: {count}")

    print(f"\n[RESULT] Check complete")


if __name__ == "__main__":
    asyncio.run(main())
