"""Test report generation for a real project."""
import asyncio, os, sys
from decimal import Decimal
from pathlib import Path
from uuid import UUID
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for line in Path(Path(__file__).resolve().parent.parent / ".env").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip().strip('"')

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.services.report_engine import ReportEngine
from app.models.report_models import FinancialReport, FinancialReportType


async def main():
    url = settings.DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(url)
    async_session = sessionmaker(engine, class_=AsyncSession)

    project_id = UUID("005a6f2d-cecd-4e30-bcbd-9fb01236c194")  # 陕西华氏
    year = 2025

    async with async_session() as db:
        # Check project's applicable_standard
        r = await db.execute(sa.text(
            "SELECT id, name FROM projects WHERE id = :pid"
        ), {"pid": project_id})
        proj = r.fetchone()
        if not proj:
            print("ERROR: Project not found")
            return
        print(f"Project: {proj[1]}")

        # Generate reports using soe_standalone (国企单体)
        report_engine = ReportEngine(db, redis=None)
        print("\nGenerating reports (soe_standalone)...")

        try:
            results = await report_engine.generate_all_reports(
                project_id=project_id,
                year=year,
                applicable_standard="soe_standalone",
            )
            print(f"\nGeneration result: {type(results)}")
            if isinstance(results, dict):
                for rt, data in results.items():
                    if isinstance(data, list):
                        non_zero = sum(
                            1 for r in data
                            if Decimal(r.get("current_period_amount", "0")) != 0
                        )
                        print(f"  {rt}: {len(data)} rows, {non_zero} non-zero")
                    else:
                        print(f"  {rt}: {data}")
            elif isinstance(results, list):
                print(f"  Total rows: {len(results)}")
        except Exception as e:
            print(f"ERROR: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

        # Check what was saved
        r2 = await db.execute(sa.text(
            "SELECT report_type, COUNT(*) as cnt, "
            "SUM(CASE WHEN (current_period_amount IS NOT NULL AND current_period_amount != 0) THEN 1 ELSE 0 END) as non_zero "
            "FROM financial_report "
            "WHERE project_id = :pid AND year = :yr AND is_deleted = false "
            "GROUP BY report_type"
        ), {"pid": project_id, "yr": year})
        saved = r2.fetchall()
        if saved:
            print("\nSaved financial_reports:")
            for row in saved:
                print(f"  {row[0]}: {row[1]} rows, {row[2]} non-zero amounts")
        else:
            print("\nNo financial_reports saved yet")

    await engine.dispose()

asyncio.run(main())
