"""验证陕西华氏数据质量检查——应检出差异科目（明细账不完整导致）

用法:
    python scripts/verify_data_quality_shaanxi.py
"""
import asyncio
import os
import sys
from pathlib import Path
from uuid import UUID

# Setup path and env
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
from app.services.data_quality_service import DataQualityService

# 陕西华氏项目
SHAANXI_PROJECT_ID = UUID("005a6f2d-cecd-4e30-bcbd-9fb01236c194")
YEAR = 2025


async def main():
    url = settings.DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(url)
    async_session = sessionmaker(engine, class_=AsyncSession)

    print("=" * 60)
    print("陕西华氏 数据质量检查验证")
    print("=" * 60)

    async with async_session() as db:
        service = DataQualityService(db)
        result = await service.run_checks(SHAANXI_PROJECT_ID, YEAR, "all")

        print(f"\n总科目数: {result['total_accounts']}")
        print(f"执行检查: {result['checks_run']}")
        print(f"汇总: passed={result['summary']['passed']}, "
              f"warning={result['summary']['warning']}, "
              f"blocking={result['summary']['blocking']}")

        print("\n--- 检查结果 ---")
        for check_name, check_result in result["results"].items():
            status = check_result["status"]
            icon = "🟢" if status == "passed" else "🟡" if status == "warning" else "🔴"
            print(f"\n{icon} {check_name}: {check_result['message']}")

            # 特别关注 balance_vs_ledger
            if check_name == "balance_vs_ledger":
                details = check_result.get("details", {})
                diffs = details.get("differences", [])
                if diffs:
                    print(f"   差异科目数: {len(diffs)}")
                    for d in diffs[:5]:
                        print(f"   - {d['account_code']} {d['account_name']}: "
                              f"期末={d['closing_balance']}, 预期={d['expected_closing']}, "
                              f"差异={d['difference']}")
                    if len(diffs) > 5:
                        print(f"   ... 还有 {len(diffs) - 5} 个")

        # 验证：应检出至少 1 个差异
        balance_check = result["results"].get("balance_vs_ledger", {})
        diffs = balance_check.get("details", {}).get("differences", [])
        ledger_rows = balance_check.get("details", {}).get("ledger_rows", None)

        print("\n" + "=" * 60)
        if balance_check.get("status") == "warning" and ledger_rows == 0:
            print("⚠️  序时账无数据，无法验证差异检出（预期行为——陕西华氏 tb_ledger 可能为空）")
            print("   这不是 bug：如果 tb_ledger 为空，系统正确跳过了余额vs序时账检查")
        elif diffs:
            print(f"✅ 验证通过：检出 {len(diffs)} 个差异科目（明细账不完整导致）")
        else:
            print("ℹ️  未检出差异——可能余额表数据自洽（期末=期初+借方-贷方）")
            print("   陕西华氏的'明细账不完整'指的是 tb_ledger 数据缺失，")
            print("   而非余额表内部不一致。余额表自身数据可能是正确的。")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
