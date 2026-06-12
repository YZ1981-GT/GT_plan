# Feature: workpaper-bad-debt-nested-structure, Property 6: 预填仅空值
"""BadDebtPrefillService 的 Property-Based Test（hypothesis, max_examples=5）。

- Property 6: 预填仅空值  (Validates Requirements 4.3)

验证：预填操作仅填充预填前为 None（空）的 Summary 单元格，已有值的单元格保持不变。

DB 策略：in-process 内存 SQLite，建 bad_debt_detail_rows + trial_balance 两张表，
每个 hypothesis example 新建独立 engine 保证隔离。
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.base import Base
from app.models.bad_debt_models import BadDebtDetailRow, ProvisionMethod
from app.schemas.bad_debt_schemas import CreateParentRowDTO, RowAmounts, UpdateRowDTO
from app.services.bad_debt_nested_table_service import NestedTableService
from app.services.bad_debt_prefill_service import (
    BAD_DEBT_ACCOUNT_CODE,
    PREFILL_SOURCE,
    BadDebtPrefillService,
)

_PBT = settings(
    max_examples=5,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)


async def _fresh_session() -> tuple[AsyncSession, object]:
    """新建独立内存 engine + 建 bad_debt_detail_rows + trial_balance 表。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[BadDebtDetailRow.__table__, TrialBalance.__table__],
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return factory(), engine


st_amount = st.decimals(
    min_value=Decimal("0.00"),
    max_value=Decimal("1000000.00"),
    places=2,
    allow_nan=False,
    allow_infinity=False,
)


@_PBT
@given(
    b_has_value=st.booleans(),
    k_has_value=st.booleans(),
    summary_b=st_amount,
    summary_k=st_amount,
    tb_opening=st_amount,
    tb_unadjusted=st_amount,
)
def test_property_6_prefill_only_empty_cells(
    b_has_value: bool,
    k_has_value: bool,
    summary_b: Decimal,
    summary_k: Decimal,
    tb_opening: Decimal,
    tb_unadjusted: Decimal,
):
    """Property 6: 仅 None 单元格被预填，已有值单元格不变。

    Validates: Requirements 4.3
    """

    async def _run():
        session, engine = await _fresh_session()
        try:
            wp_index_id = uuid.uuid4()
            project_id = uuid.uuid4()
            year = 2025
            svc = NestedTableService(session)

            # 用一个无子行父行承载 Summary 的 amount_b / amount_k
            parent = await svc.create_parent_row(
                wp_index_id,
                CreateParentRowDTO(
                    provision_method=ProvisionMethod.OTHER, row_label="其他"
                ),
            )
            amounts = RowAmounts(
                amount_b=summary_b if b_has_value else None,
                amount_k=summary_k if k_has_value else None,
            )
            await svc.update_row(
                parent.id, UpdateRowDTO(version=parent.version, amounts=amounts)
            )

            # 试算表 1231
            session.add(
                TrialBalance(
                    id=uuid.uuid4(),
                    project_id=project_id,
                    year=year,
                    company_code="MAIN",
                    standard_account_code=BAD_DEBT_ACCOUNT_CODE,
                    account_name="坏账准备",
                    account_category=AccountCategory.asset,
                    opening_balance=tb_opening,
                    unadjusted_amount=tb_unadjusted,
                )
            )
            await session.flush()

            # 预填前 Summary 状态快照
            before = (await svc.get_tree(wp_index_id)).summary.amounts

            result = await BadDebtPrefillService(session).prefill_summary(
                wp_index_id, project_id, year
            )

            # amount_b：预填前有值 → 不应被预填；预填前为 None → 应被预填且值=TB opening
            if before.amount_b is not None:
                assert "amount_b" not in result.prefilled_columns
            else:
                assert "amount_b" in result.prefilled_columns
                assert result.values["amount_b"] == tb_opening.quantize(Decimal("0.01"))

            if before.amount_k is not None:
                assert "amount_k" not in result.prefilled_columns
            else:
                assert "amount_k" in result.prefilled_columns
                assert result.values["amount_k"] == tb_unadjusted.quantize(
                    Decimal("0.01")
                )

            # 实际预填时来源标注正确
            if result.prefilled_columns:
                assert result.prefilled is True
                assert result.source == PREFILL_SOURCE
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_run())
