# Feature: workpaper-bad-debt-nested-structure — Task 13.2 校验集成单元测试
"""validate_integrity 接入 TB 1231 audited_amount 比对的集成单元测试。

覆盖（Req 10.1）：
- N 等于 TB audited_amount → 无 SUMMARY_TB_MISMATCH
- N 不等于 TB audited_amount → 标记 SUMMARY_TB_MISMATCH
- TB 无 1231 数据 → 跳过（无可比基准，不报）
- 不提供 project_id/year（向后兼容）→ 不做 TB 比对

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
from app.schemas.bad_debt_schemas import (
    CreateChildRowDTO,
    CreateParentRowDTO,
)
from app.services.bad_debt_nested_table_service import (
    BAD_DEBT_ACCOUNT_CODE,
    NestedTableService,
)

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


def _add_tb_1231(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    audited: Decimal | None,
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
            audited_amount=audited,
        )
    )


async def _build_summary_n(session: AsyncSession, wp: uuid.UUID, n_value: Decimal) -> None:
    """建一个父行(1子行)，使 Summary 期末审定数(N) = n_value。"""
    svc = NestedTableService(session)
    parent = await svc.create_parent_row(
        wp, CreateParentRowDTO(provision_method=ProvisionMethod.INDIVIDUAL, row_label="单项")
    )
    await svc.create_child_row(
        parent.id, CreateChildRowDTO(row_label="甲", amount_n=n_value)
    )


@pytest.mark.asyncio
async def test_validate_summary_equals_tb_no_mismatch(session: AsyncSession):
    """N == TB audited_amount → 无 SUMMARY_TB_MISMATCH。"""
    wp = uuid.uuid4()
    project_id = uuid.uuid4()
    await _build_summary_n(session, wp, Decimal("300.00"))
    _add_tb_1231(session, project_id, audited=Decimal("300.00"))
    await session.flush()

    errors = await NestedTableService(session).validate_integrity(wp, project_id, YEAR)
    assert not [e for e in errors if e.code == "SUMMARY_TB_MISMATCH"]


@pytest.mark.asyncio
async def test_validate_summary_differs_from_tb_mismatch(session: AsyncSession):
    """N != TB audited_amount → 标记 SUMMARY_TB_MISMATCH。"""
    wp = uuid.uuid4()
    project_id = uuid.uuid4()
    await _build_summary_n(session, wp, Decimal("300.00"))
    _add_tb_1231(session, project_id, audited=Decimal("250.00"))
    await session.flush()

    errors = await NestedTableService(session).validate_integrity(wp, project_id, YEAR)
    mismatch = [e for e in errors if e.code == "SUMMARY_TB_MISMATCH"]
    assert mismatch
    assert "300.00" in mismatch[0].message
    assert "250.00" in mismatch[0].message


@pytest.mark.asyncio
async def test_validate_skips_when_no_tb_1231(session: AsyncSession):
    """TB 无 1231 数据 → 跳过，不报 SUMMARY_TB_MISMATCH。"""
    wp = uuid.uuid4()
    project_id = uuid.uuid4()
    await _build_summary_n(session, wp, Decimal("300.00"))
    # 仅别的科目
    _add_tb_1231(session, project_id, audited=Decimal("999.00"), code="1122")
    await session.flush()

    errors = await NestedTableService(session).validate_integrity(wp, project_id, YEAR)
    assert not [e for e in errors if e.code == "SUMMARY_TB_MISMATCH"]


@pytest.mark.asyncio
async def test_validate_skips_when_tb_audited_null(session: AsyncSession):
    """TB 1231 存在但 audited_amount 为 NULL → 无可比基准，跳过。"""
    wp = uuid.uuid4()
    project_id = uuid.uuid4()
    await _build_summary_n(session, wp, Decimal("300.00"))
    _add_tb_1231(session, project_id, audited=None)
    await session.flush()

    errors = await NestedTableService(session).validate_integrity(wp, project_id, YEAR)
    assert not [e for e in errors if e.code == "SUMMARY_TB_MISMATCH"]


@pytest.mark.asyncio
async def test_validate_backward_compatible_without_project_year(session: AsyncSession):
    """不提供 project_id/year → 不做 TB 比对（向后兼容单参调用）。"""
    wp = uuid.uuid4()
    project_id = uuid.uuid4()
    await _build_summary_n(session, wp, Decimal("300.00"))
    _add_tb_1231(session, project_id, audited=Decimal("250.00"))
    await session.flush()

    # 单参调用：不应触发 TB 比对，即便差额存在
    errors = await NestedTableService(session).validate_integrity(wp)
    assert not [e for e in errors if e.code == "SUMMARY_TB_MISMATCH"]
