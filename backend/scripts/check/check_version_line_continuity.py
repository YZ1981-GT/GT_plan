"""Phase 16 验收脚本：版本号连续性检查

遍历所有 object_type+object_id 组合，断言 version_no 连续无跳号。
用法: python -m scripts.phase16.check_version_line_continuity
"""
import asyncio
import sys


async def main():
    from app.core.database import async_engine
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import text

    fail = 0
    async with AsyncSession(async_engine) as db:
        result = await db.execute(text("""
            SELECT object_type, object_id,
                   array_agg(version_no ORDER BY version_no) as versions
            FROM version_line_stamps
            GROUP BY object_type, object_id
        """))
        rows = result.fetchall()
        if not rows:
            print("  [INFO] No version_line_stamps yet")
            return

        for obj_type, obj_id, versions in rows:
            # 检查连续性
            for i in range(1, len(versions)):
                if versions[i] != versions[i-1] + 1:
                    print(f"  [FAIL] {obj_type}:{str(obj_id)[:8]} gap: v{versions[i-1]}→v{versions[i]}")
                    fail += 1
                    break
            else:
                print(f"  [PASS] {obj_type}:{str(obj_id)[:8]} versions={versions} continuous")

    print(f"\n[RESULT] {'ALL PASS' if fail == 0 else f'{fail} FAILURES'}")
    sys.exit(0 if fail == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
