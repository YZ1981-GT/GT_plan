"""查 1122 应收账款翻倍根因: 是否 level1+level2 子科目都映射到 1122 导致双计。"""
import asyncio
from decimal import Decimal
from uuid import UUID
from app.core.database import async_session, engine
from sqlalchemy import text
from app.services.dataset_service import DatasetService

PID = UUID('12c15a96-b826-45b5-84ae-3f80f3e96f98')
YEAR = 2025


async def main():
    async with async_session() as db:
        active_id = await DatasetService.get_active_dataset_id(db, PID, YEAR)

        r = await db.execute(text("""
            SELECT tb.account_code, tb.account_name, tb.level, tb.closing_balance
            FROM tb_balance tb
            JOIN account_mapping am ON am.original_account_code=tb.account_code
                 AND am.project_id=tb.project_id AND am.is_deleted=false
            WHERE tb.project_id=:p AND tb.year=:y AND tb.is_deleted=false
              AND tb.dataset_id=:d AND am.standard_account_code='1122'
            ORDER BY tb.level, tb.account_code
        """), {"p": str(PID), "y": YEAR, "d": str(active_id)})
        print("=== 映射到标准科目 1122 应收账款 的 active tb_balance 行 ===")
        tot = Decimal(0)
        for row in r.fetchall():
            print(f"  {row[0]:18s} {row[1][:14] if row[1] else '':14s} L{row[2]} closing={float(row[3] or 0):>16,.2f}")
            tot += Decimal(str(row[3] or 0))
        print(f"  SUM(all)={float(tot):,.2f}  <- recalc 取值(双计父子)")

        r = await db.execute(text("""
            SELECT SUM(tb.closing_balance)
            FROM tb_balance tb
            JOIN account_mapping am ON am.original_account_code=tb.account_code
                 AND am.project_id=tb.project_id AND am.is_deleted=false
            WHERE tb.project_id=:p AND tb.year=:y AND tb.is_deleted=false
              AND tb.dataset_id=:d AND am.standard_account_code='1122' AND tb.level=1
        """), {"p": str(PID), "y": YEAR, "d": str(active_id)})
        print(f"  level=1 only={float(r.scalar() or 0):,.2f}  <- 正确值")

        r = await db.execute(text("""
            SELECT original_account_code FROM account_mapping
            WHERE project_id=:p AND is_deleted=false AND standard_account_code='1122'
            ORDER BY original_account_code
        """), {"p": str(PID)})
        print("\n=== account_mapping ->1122 的 original code ===")
        for row in r.fetchall():
            print(f"  {row[0]}")

    await engine.dispose()


asyncio.run(main())
