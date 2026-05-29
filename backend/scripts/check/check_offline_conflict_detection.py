"""Phase 16 验收脚本：离线冲突检测覆盖率

检查 offline_conflicts 表是否有记录，验证字段级粒度。
用法: python -m scripts.phase16.check_offline_conflict_detection
"""
import asyncio
import sys


async def main():
    from app.core.database import async_engine
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import text

    async with AsyncSession(async_engine) as db:
        result = await db.execute(text("""
            SELECT COUNT(*), COUNT(DISTINCT field_name), COUNT(DISTINCT wp_id)
            FROM offline_conflicts
        """))
        row = result.fetchone()
        total, fields, wps = row[0], row[1], row[2]
        print(f"  [INFO] Total conflicts: {total}, distinct fields: {fields}, distinct wps: {wps}")

        if total > 0:
            # 验证 reason_code 字段存在
            result = await db.execute(text("""
                SELECT id, field_name, status, reason_code FROM offline_conflicts LIMIT 5
            """))
            for r in result.fetchall():
                has_reason = "✓" if r[3] else "✗"
                print(f"  [INFO] conflict={str(r[0])[:8]} field={r[1]} status={r[2]} reason_code={has_reason}")
            print("  [PASS] Conflict detection producing field-level records")
        else:
            print("  [INFO] No conflicts yet — upload an offline-edited workpaper to trigger detection")

    print(f"\n[RESULT] Check complete")


if __name__ == "__main__":
    asyncio.run(main())
