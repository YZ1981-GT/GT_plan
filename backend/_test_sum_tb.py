"""Revert formula changes and test the subtract overlay approach."""
import asyncio
from uuid import UUID
from decimal import Decimal
from app.core.database import engine, async_session
from sqlalchemy import text


# Revert formulas to their original (pre-my-changes) state
REVERTS = [
    ("BS-005", "listed_standalone", "TB('1121','期末余额')"),
    ("BS-006", "listed_standalone", "TB('1122','期末余额')"),
    ("BS-009", "listed_standalone", "TB('1221','期末余额')"),
    ("BS-010", "listed_standalone", "SUM_TB('1401~1499','期末余额')"),
    ("BS-014", "listed_standalone", "TB('1901','期末余额')"),
    ("BS-027", "listed_standalone", "TB('1521','期末余额')"),
    ("BS-050", "listed_standalone", "TB('2241','期末余额')"),
]


async def main():
    from app.services.report_engine import ReportEngine

    pid = UUID('12c15a96-b826-45b5-84ae-3f80f3e96f98')

    async with async_session() as db:
        # Revert formulas
        for row_code, std, formula in REVERTS:
            await db.execute(
                text(
                    "UPDATE report_config SET formula = :f "
                    "WHERE row_code = :rc AND applicable_standard = :std AND is_deleted = false"
                ),
                {"f": formula, "rc": row_code, "std": std},
            )
        await db.commit()
        print("Formulas reverted")

    # Regenerate with subtract overlay
    async with async_session() as db:
        svc = ReportEngine(db)
        result = await svc.generate_all_reports(pid, 2025, 'listed_standalone')
        await db.commit()

        bs = result.get('balance_sheet', [])
        asset_total = next((r for r in bs if r['row_code'] == 'BS-039'), None)
        le_total = next((r for r in bs if r['row_code'] == 'BS-099'), None)
        if asset_total and le_total:
            a = float(asset_total['current_period_amount'])
            le = float(le_total['current_period_amount'])
            print(f"资产总计: {a:,.2f}")
            print(f"负债和权益总计: {le:,.2f}")
            print(f"差额: {a - le:,.2f}")
            print(f"平衡: {'✓' if abs(a - le) < 1 else '✗'}")

            # Show key rows
            for code in ['BS-005', 'BS-006', 'BS-009', 'BS-010', 'BS-027']:
                row = next((r for r in bs if r['row_code'] == code), None)
                if row:
                    print(f"  {code} {row['row_name']}: {row['current_period_amount']}")
    await engine.dispose()


asyncio.run(main())
