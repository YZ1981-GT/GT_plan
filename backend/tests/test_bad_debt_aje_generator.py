# Feature: workpaper-bad-debt-nested-structure — Task 6.3 AjeGenerator 单元测试
"""BadDebtAjeGenerator 单元测试。

覆盖：
- 零差额（不生成，返回 None）
- 补提（审定 > 未审）→ 借 信用减值损失 / 贷 坏账准备
- 冲回（审定 < 未审）→ 借 坏账准备 / 贷 信用减值损失
- 用户修改后覆盖旧建议（重新生成反映新差额）

DB：in-process 内存 SQLite，仅建 bad_debt_detail_rows 表。
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
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


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all, tables=[BadDebtDetailRow.__table__]
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _setup_summary(
    session: AsyncSession, wp: uuid.UUID, *, n: Decimal | None, k: Decimal | None
) -> None:
    """建无子行父行并设置 amount_n/amount_k，使 Summary 反映该值。"""
    svc = NestedTableService(session)
    parent = await svc.create_parent_row(
        wp, CreateParentRowDTO(provision_method=ProvisionMethod.INDIVIDUAL, row_label="单项")
    )
    await svc.update_row(
        parent.id,
        UpdateRowDTO(version=parent.version, amounts=RowAmounts(amount_n=n, amount_k=k)),
    )


@pytest.mark.asyncio
async def test_zero_diff_no_suggestion(session: AsyncSession):
    """零差额（N == K）→ 不生成建议。"""
    wp = uuid.uuid4()
    await _setup_summary(session, wp, n=Decimal("100.00"), k=Decimal("100.00"))
    result = await BadDebtAjeGenerator(session).generate_suggestion(wp)
    assert result is None


@pytest.mark.asyncio
async def test_both_none_no_suggestion(session: AsyncSession):
    """N、K 均为空（都视作 0，差额 0）→ 不生成。"""
    wp = uuid.uuid4()
    await _setup_summary(session, wp, n=None, k=None)
    result = await BadDebtAjeGenerator(session).generate_suggestion(wp)
    assert result is None


@pytest.mark.asyncio
async def test_provision_more(session: AsyncSession):
    """补提：审定数 > 未审数 → 借 信用减值损失 / 贷 坏账准备。"""
    wp = uuid.uuid4()
    await _setup_summary(session, wp, n=Decimal("150.00"), k=Decimal("100.00"))
    result = await BadDebtAjeGenerator(session).generate_suggestion(wp)
    assert result is not None
    assert result.direction == AjeDirection.PROVISION
    assert result.amount == Decimal("50.00")
    assert result.debit_account == IMPAIRMENT_LOSS_ACCOUNT_CODE
    assert result.credit_account == BAD_DEBT_ACCOUNT_CODE
    assert result.status == "suggested"
    # 摘要含补提说明
    assert "补提" in result.summary
    # 分录行借贷各一
    sides = sorted(ln.side for ln in result.lines)
    assert sides == ["credit", "debit"]


@pytest.mark.asyncio
async def test_reversal_less(session: AsyncSession):
    """冲回：审定数 < 未审数 → 借 坏账准备 / 贷 信用减值损失。"""
    wp = uuid.uuid4()
    await _setup_summary(session, wp, n=Decimal("80.00"), k=Decimal("100.00"))
    result = await BadDebtAjeGenerator(session).generate_suggestion(wp)
    assert result is not None
    assert result.direction == AjeDirection.REVERSAL
    assert result.amount == Decimal("20.00")
    assert result.debit_account == BAD_DEBT_ACCOUNT_CODE
    assert result.credit_account == IMPAIRMENT_LOSS_ACCOUNT_CODE
    assert "冲回" in result.summary


@pytest.mark.asyncio
async def test_regenerate_overrides_old_suggestion(session: AsyncSession):
    """用户修改 Summary 后重新生成 → 新建议反映新差额（覆盖旧建议）。"""
    wp = uuid.uuid4()
    svc = NestedTableService(session)
    parent = await svc.create_parent_row(
        wp, CreateParentRowDTO(provision_method=ProvisionMethod.OTHER, row_label="其他")
    )
    # 初始：补提 50
    await svc.update_row(
        parent.id,
        UpdateRowDTO(
            version=parent.version,
            amounts=RowAmounts(amount_n=Decimal("150.00"), amount_k=Decimal("100.00")),
        ),
    )
    gen = BadDebtAjeGenerator(session)
    first = await gen.generate_suggestion(wp)
    assert first is not None
    assert first.direction == AjeDirection.PROVISION
    assert first.amount == Decimal("50.00")

    # 用户改未审数 → 变冲回 30
    db_parent = await session.get(BadDebtDetailRow, parent.id)
    await svc.update_row(
        parent.id,
        UpdateRowDTO(
            version=db_parent.version,
            amounts=RowAmounts(amount_n=Decimal("150.00"), amount_k=Decimal("180.00")),
        ),
    )
    second = await gen.generate_suggestion(wp)
    assert second is not None
    assert second.direction == AjeDirection.REVERSAL
    assert second.amount == Decimal("30.00")
    assert second.debit_account == BAD_DEBT_ACCOUNT_CODE
