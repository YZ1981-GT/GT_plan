"""初始化 4 个项目的数据状态（DB 重建后一键恢复）

执行顺序：auto-match → recalc → generate_all_reports
确保 e2e_business_flow_verify.py Layer 1-4 全绿

用法:
    python scripts/init_4_projects.py
"""
import asyncio
import io
import os
import sys
from pathlib import Path
from uuid import UUID

# Windows GBK 终端兼容
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.services.mapping_service import auto_match
from app.services.trial_balance_service import TrialBalanceService
from app.services.report_engine import ReportEngine
from app.services.report_config_service import ReportConfigService

PROJECTS = [
    (UUID("005a6f2d-cecd-4e30-bcbd-9fb01236c194"), "陕西华氏", 2025),
    (UUID("5942c12e-65fb-4187-ace3-79d45a90cb53"), "和平药房", 2025),
    (UUID("37814426-a29e-4fc2-9313-a59d229bf7b0"), "辽宁卫生", 2025),
    (UUID("14fb8c10-9462-45f6-8f56-d023f5b6df13"), "宜宾大药房", 2025),
]


async def init_project(db: AsyncSession, project_id: UUID, name: str, year: int):
    """初始化单个项目：auto-match → recalc → generate_reports"""
    print(f"\n{'='*60}")
    print(f"  {name} ({project_id})")
    print(f"{'='*60}")

    # 1. 检查 tb_balance 是否有数据
    r = await db.execute(sa.text(
        "SELECT COUNT(*) FROM tb_balance WHERE project_id = :pid AND year = :yr AND is_deleted = false"
    ), {"pid": project_id, "yr": year})
    tb_count = r.scalar() or 0
    print(f"  [1] tb_balance: {tb_count} rows")

    if tb_count == 0:
        print(f"  ⚠️  无余额表数据，跳过该项目")
        return False

    # 2. Auto-match
    print(f"  [2] 执行 auto-match...", end=" ")
    try:
        result = await auto_match(project_id, db, year)
        await db.commit()
        saved = result.saved if hasattr(result, 'saved') else (result.get("saved", 0) if isinstance(result, dict) else 0)
        print(f"OK (saved={saved})")
    except Exception as e:
        await db.rollback()
        print(f"WARN: {str(e)[:60]}")

    # 3. Recalc
    print(f"  [3] 执行 recalc...", end=" ")
    try:
        tb_svc = TrialBalanceService(db)
        await tb_svc.full_recalc(project_id, year, "001")
        await db.commit()
        # 验证
        r2 = await db.execute(sa.text(
            "SELECT COUNT(*) FROM trial_balance WHERE project_id = :pid AND year = :yr AND is_deleted = false"
        ), {"pid": project_id, "yr": year})
        tb_rows = r2.scalar() or 0
        print(f"OK (trial_balance={tb_rows} rows)")
    except Exception as e:
        await db.rollback()
        print(f"FAIL: {str(e)[:80]}")
        return False

    # 4. Generate reports
    print(f"  [4] 生成报表...", end=" ")
    try:
        # Resolve applicable_standard
        std = await ReportConfigService.resolve_applicable_standard(db, project_id)
        engine = ReportEngine(db, redis=None)
        results = await engine.generate_all_reports(project_id, year, std)
        await db.commit()

        # Count non-zero BS rows
        total_rows = sum(len(v) for v in results.values()) if isinstance(results, dict) else 0
        bs_rows = results.get("balance_sheet", []) if isinstance(results, dict) else []
        from decimal import Decimal
        bs_nonzero = sum(1 for r in bs_rows if Decimal(r.get("current_period_amount", "0")) != 0)
        print(f"OK (total={total_rows}, BS non-zero={bs_nonzero})")
    except Exception as e:
        await db.rollback()
        print(f"FAIL: {str(e)[:80]}")
        return False

    return True


async def main():
    url = settings.DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    print("=" * 60)
    print("  4 项目数据初始化（auto-match → recalc → generate）")
    print("=" * 60)

    success_count = 0
    for project_id, name, year in PROJECTS:
        async with async_session() as db:
            try:
                ok = await init_project(db, project_id, name, year)
                if ok:
                    success_count += 1
            except Exception as e:
                print(f"  ❌ 异常: {str(e)[:80]}")

    await engine.dispose()

    print(f"\n{'='*60}")
    print(f"  完成: {success_count}/{len(PROJECTS)} 项目初始化成功")
    print(f"{'='*60}")
    return 0 if success_count == len(PROJECTS) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
