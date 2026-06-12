# Feature: workpaper-bad-debt-nested-structure, Property 7: AJE 方向正确性
"""BadDebtAjeGenerator 的 Property-Based Test（hypothesis, max_examples=5）。

- Property 7: AJE 方向正确性  (Validates Requirements 5.2, 5.3, 5.4)

验证：对任意 (审定数 N, 未审数 K)：
- N > K（补提）→ 借 信用减值损失 / 贷 坏账准备 1231
- N < K（冲回）→ 借 坏账准备 1231 / 贷 信用减值损失
- N == K → 不生成建议（None）
- 金额 = |N - K|

DB 策略：in-process 内存 SQLite，仅建 bad_debt_detail_rows 表，每个 example
新建独立 engine。用一个无子行父行承载 Summary 的 amount_n / amount_k。
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.bad_debt_models import BadDebtDetailRow, ProvisionMethod
from app.schemas.bad_debt_schemas import CreateParentRowDTO, RowAmounts, UpdateRowDTO
from app.services.bad_debt_aje_generator import (
    BAD_DEBT_ACCOUNT_CODE,
    IMPAIRMENT_LOSS_ACCOUNT_CODE,
    AjeDirection,
    BadDebtAjeGenerator,
)
from app.services.bad_debt_nested_table_service import NestedTableService

_PBT = settings(
    max_examples=5,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)


async def _fresh_session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all, tables=[BadDebtDetailRow.__table__]
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
@given(audited_n=st_amount, unaudited_k=st_amount)
def test_property_7_aje_direction_and_amount(audited_n: Decimal, unaudited_k: Decimal):
    """Property 7: AJE 方向与金额绝对值正确。

    Validates: Requirements 5.2, 5.3, 5.4
    """

    async def _run():
        session, engine = await _fresh_session()
        try:
            wp_index_id = uuid.uuid4()
            svc = NestedTableService(session)
            parent = await svc.create_parent_row(
                wp_index_id,
                CreateParentRowDTO(
                    provision_method=ProvisionMethod.INDIVIDUAL, row_label="单项"
                ),
            )
            await svc.update_row(
                parent.id,
                UpdateRowDTO(
                    version=parent.version,
                    amounts=RowAmounts(amount_n=audited_n, amount_k=unaudited_k),
                ),
            )

            suggestion = await BadDebtAjeGenerator(session).generate_suggestion(
                wp_index_id
            )

            diff = (audited_n - unaudited_k).quantize(Decimal("0.01"))
            expected_amount = abs(diff)

            if diff == Decimal("0.00"):
                # 零差额不生成
                assert suggestion is None
                return

            assert suggestion is not None
            # 金额 = |差额|
            assert suggestion.amount == expected_amount

            if diff > Decimal("0.00"):
                # 补提：借 信用减值损失 / 贷 坏账准备
                assert suggestion.direction == AjeDirection.PROVISION
                assert suggestion.debit_account == IMPAIRMENT_LOSS_ACCOUNT_CODE
                assert suggestion.credit_account == BAD_DEBT_ACCOUNT_CODE
            else:
                # 冲回：借 坏账准备 / 贷 信用减值损失
                assert suggestion.direction == AjeDirection.REVERSAL
                assert suggestion.debit_account == BAD_DEBT_ACCOUNT_CODE
                assert suggestion.credit_account == IMPAIRMENT_LOSS_ACCOUNT_CODE

            # 分录行借贷各一条，金额都等于绝对值
            debit_lines = [ln for ln in suggestion.lines if ln.side == "debit"]
            credit_lines = [ln for ln in suggestion.lines if ln.side == "credit"]
            assert len(debit_lines) == 1
            assert len(credit_lines) == 1
            assert debit_lines[0].amount == expected_amount
            assert credit_lines[0].amount == expected_amount
            # 金额恒为正
            assert suggestion.amount >= Decimal("0.00")
        finally:
            await session.close()
            await engine.dispose()

    asyncio.run(_run())
