"""Phase 16 验收脚本：取证包 hash 校验

随机选 5 个导出包，verify_package 断言全部 passed。
用法: python -m scripts.phase16.check_export_integrity_hash
"""
import asyncio
import sys


async def main():
    from app.core.database import async_engine
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import text
    from app.services.export_integrity_service import export_integrity_service

    fail = 0
    async with AsyncSession(async_engine) as db:
        result = await db.execute(text("""
            SELECT DISTINCT export_id FROM evidence_hash_checks LIMIT 5
        """))
        exports = [r[0] for r in result.fetchall()]
        if not exports:
            print("  [INFO] No evidence_hash_checks yet — export a package first")
            return

        for eid in exports:
            check = await export_integrity_service.verify_package(db, str(eid))
            if check["check_status"] == "passed":
                print(f"  [PASS] export={str(eid)[:8]} all files passed")
            else:
                print(f"  [FAIL] export={str(eid)[:8]} mismatched: {check.get('mismatched_files', [])}")
                fail += 1

    print(f"\n[RESULT] {'ALL PASS' if fail == 0 else f'{fail} FAILURES'}")
    sys.exit(0 if fail == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
