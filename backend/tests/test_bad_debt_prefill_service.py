# Feature: workpaper-bad-debt-nested-structure — Task 5.3 PrefillService 单元测试
"""BadDebtPrefillService 单元测试。

覆盖：
- 1231 缺失（跳过、no-op、不报错）
- 已有值不覆盖（amount_b 已有值则不预填）
- 正常预填带来源标注（amount_b ← opening_balance、amount_k ← unadjusted_amount）

DB：in-process 内存 SQLite，建 bad_debt_detail_rows + trial_balance 表。
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_models import AccountCategory, TrialBalance
from app.models.base import Base
from app.models.bad_debt_models import BadDebtDetailRow, ProvisionMethod
from app.schemas.bad_debt_schemas import CreateParentRowDTO, RowAmounts, UpdateRowDTO
from app.services.bad_debt_nested_table_service import NestedTableService
from app.services.bad_debt_account_codes import bad_debt_provision_account
from app.services.bad_debt_prefill_service import BadDebtPrefillService

BAD_DEBT_ACCOUNT_CODE, _ = bad_debt_provision_account()
PREFILL_SOURCE = f"试算表 {BAD_DEBT_ACCOUNT_CODE} {_}"

YEAR = 2025


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[BadDebtDetailRow.__table__, TrialBalance.__table__],
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _seed_parent(svc: NestedTableService, wp: uuid.UUID) -> None:
    """建一个空的父行（保证 Summary 存在但 amount_b/amount_k 为 None）。"""
    await svc.create_parent_row(
        wp, CreateParentRowDTO(provision_method=ProvisionMethod.INDIVIDUAL, row_label="单项")
    )


def _add_tb_1231(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    opening: Decimal | None,
    unadjusted: Decimal | None,
    code: str = BAD_DEBT_ACCOUNT_CODE,
) -> None:
    session.add(
        TrialBalance(
            id=uuid.uuid4(),
            project_id=project_id,
            year=YEAR,
            company_code="MAIN",
            standard_account_code=code,
            account_name="坏账准备",
            account_category=AccountCategory.asset,
            opening_balance=opening,
            unadjusted_amount=unadjusted,
        )
    )


@pytest.mark.asyncio
async def test_prefill_skips_when_no_1231(session: AsyncSession):
    """试算表无 1231 数据 → no-op，不报错，prefilled=False。"""
    wp = uuid.uuid4()
    project_id = uuid.uuid4()
    svc = NestedTableService(session)
    await _seed_parent(svc, wp)
    # 试算表里只有别的科目，无 1231
    _add_tb_1231(session, project_id, opening=Decimal("1.00"), unadjusted=Decimal("2.00"), code="1122")
    await session.flush()

    result = await BadDebtPrefillService(session).prefill_summary(wp, project_id, YEAR)
    assert result.prefilled is False
    assert result.prefilled_columns == []
    assert result.source is None
    assert result.skipped_reason is not None


@pytest.mark.asyncio
async def test_prefill_normal_with_source(session: AsyncSession):
    """正常预填：amount_b ← opening_balance、amount_k ← unadjusted_amount，带来源标注。"""
    wp = uuid.uuid4()
    project_id = uuid.uuid4()
    svc = NestedTableService(session)
    await _seed_parent(svc, wp)
    _add_tb_1231(
        session, project_id, opening=Decimal("12345.67"), unadjusted=Decimal("88888.88")
    )
    await session.flush()

    result = await BadDebtPrefillService(session).prefill_summary(wp, project_id, YEAR)
    assert result.prefilled is True
    assert result.source == PREFILL_SOURCE
    assert set(result.prefilled_columns) == {"amount_b", "amount_k"}
    assert result.values["amount_b"] == Decimal("12345.67")
    assert result.values["amount_k"] == Decimal("88888.88")


@pytest.mark.asyncio
async def test_prefill_does_not_overwrite_existing(session: AsyncSession):
    """已有值不覆盖：amount_b 已有用户输入 → 不预填 b，仅预填空的 k。"""
    wp = uuid.uuid4()
    project_id = uuid.uuid4()
    svc = NestedTableService(session)
    parent = await svc.create_parent_row(
        wp, CreateParentRowDTO(provision_method=ProvisionMethod.OTHER, row_label="其他")
    )
    # 用户已填 amount_b
    await svc.update_row(
        parent.id,
        UpdateRowDTO(version=parent.version, amounts=RowAmounts(amount_b=Decimal("500.00"))),
    )
    _add_tb_1231(
        session, project_id, opening=Decimal("999.99"), unadjusted=Decimal("777.77")
    )
    await session.flush()

    result = await BadDebtPrefillService(session).prefill_summary(wp, project_id, YEAR)
    assert result.prefilled is True
    # amount_b 已有值不覆盖
    assert "amount_b" not in result.prefilled_columns
    # amount_k 为空被预填
    assert "amount_k" in result.prefilled_columns
    assert result.values["amount_k"] == Decimal("777.77")


@pytest.mark.asyncio
async def test_prefill_aggregates_across_companies(session: AsyncSession):
    """多 company_code 下 1231 余额聚合求和。"""
    wp = uuid.uuid4()
    project_id = uuid.uuid4()
    svc = NestedTableService(session)
    await _seed_parent(svc, wp)
    session.add(
        TrialBalance(
            id=uuid.uuid4(), project_id=project_id, year=YEAR, company_code="C1",
            standard_account_code=BAD_DEBT_ACCOUNT_CODE, account_name="坏账准备",
            account_category=AccountCategory.asset,
            opening_balance=Decimal("100.00"), unadjusted_amount=Decimal("200.00"),
        )
    )
    session.add(
        TrialBalance(
            id=uuid.uuid4(), project_id=project_id, year=YEAR, company_code="C2",
            standard_account_code=BAD_DEBT_ACCOUNT_CODE, account_name="坏账准备",
            account_category=AccountCategory.asset,
            opening_balance=Decimal("50.00"), unadjusted_amount=Decimal("30.00"),
        )
    )
    await session.flush()

    result = await BadDebtPrefillService(session).prefill_summary(wp, project_id, YEAR)
    assert result.values["amount_b"] == Decimal("150.00")
    assert result.values["amount_k"] == Decimal("230.00")
