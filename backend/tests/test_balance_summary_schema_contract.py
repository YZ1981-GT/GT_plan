"""契约测试：get_balance_summary 返回字段完整性。

防止再次漏查 direction 字段导致前端方向显示错误。
使用真实 PG 中已存在的项目数据（不插入测试数据，避免 FK 依赖）。

用法：python -m pytest tests/test_balance_summary_schema_contract.py -v
"""

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ledger_penetration_service import LedgerPenetrationService

# 必须返回的字段列表（前端 resolveDir 依赖）
REQUIRED_FIELDS = {
    "account_code",
    "account_name",
    "level",
    "opening_balance",
    "debit_amount",
    "credit_amount",
    "closing_balance",
    "opening_direction",
    "closing_direction",
}


@pytest.fixture
async def db_session():
    from app.core.database import async_session
    async with async_session() as session:
        yield session


@pytest.mark.asyncio
async def test_balance_summary_schema_contract(db_session: AsyncSession):
    """get_balance_summary 必须返回 direction 字段 + 值合法（前端方向显示依赖）

    验证：
    1. 所有行都包含 REQUIRED_FIELDS 中的每个字段
    2. direction 值只能是 debit/credit/None
    """
    from app.models.audit_platform_models import TbBalance
    tbl = TbBalance.__table__
    r = await db_session.execute(
        sa.select(tbl.c.project_id, tbl.c.year)
        .where(tbl.c.is_deleted == sa.false())
        .limit(1)
    )
    row = r.first()
    if row is None:
        pytest.skip("无余额数据，跳过契约测试")

    pid, year = row[0], row[1]
    svc = LedgerPenetrationService(db_session)
    rows = await svc.get_balance_summary(pid, year)

    assert len(rows) > 0, "应该有数据"

    valid_direction_values = {"debit", "credit", None}

    # 抽样检查前 20 行（包括可能的合成行）
    for row in rows[:20]:
        # 1. 字段完整性
        missing = REQUIRED_FIELDS - set(row.keys())
        assert not missing, (
            f"get_balance_summary 缺少必须字段: {missing} "
            f"(account={row.get('account_code')}, synthetic={row.get('_is_synthetic')})"
        )

        # 2. 值合法性
        assert row.get("opening_direction") in valid_direction_values, \
            f"opening_direction 值异常: {row.get('opening_direction')} for {row['account_code']}"
        assert row.get("closing_direction") in valid_direction_values, \
            f"closing_direction 值异常: {row.get('closing_direction')} for {row['account_code']}"
