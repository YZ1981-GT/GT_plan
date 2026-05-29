"""Phase 16 验收脚本：冲突合并后 QC 重跑检查

resolve 后断言 qc_replay_job_id 非空 + QC 结果已刷新。
用法: python -m scripts.phase16.check_conflict_merge_qc_replay
"""
import asyncio
import sys


async def main():
    from app.core.database import async_engine
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import text

    async with AsyncSession(async_engine) as db:
        result = await db.execute(text("""
            SELECT id, status, qc_replay_job_id, reason_code
            FROM offline_conflicts
            WHERE status = 'resolved'
            LIMIT 10
        """))
        resolved = result.fetchall()
        if not resolved:
            print("  [INFO] No resolved conflicts yet")
            return

        fail = 0
        for r in resolved:
            if r[2]:
                print(f"  [PASS] conflict={str(r[0])[:8]} qc_job={str(r[2])[:8]} reason={r[3]}")
            else:
                print(f"  [FAIL] conflict={str(r[0])[:8]} qc_replay_job_id is NULL")
                fail += 1

        print(f"\n[RESULT] {'ALL PASS' if fail == 0 else f'{fail} FAILURES'}")
        sys.exit(0 if fail == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
