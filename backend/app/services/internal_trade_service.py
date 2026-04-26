"""内部交易与往来服务 — 异步 ORM"""

from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consolidation_models import (
    InternalTrade,
    InternalArAp,
    ReconciliationStatus,
)
from app.models.consolidation_schemas import (
    InternalTradeCreate,
    InternalTradeUpdate,
    InternalTradeResponse,
    InternalArApCreate,
    InternalArApUpdate,
    InternalArApResponse,
    TransactionMatrix,
)


# ========== 内部交易 ==========


async def get_trades(db: AsyncSession, project_id: UUID, year: int) -> list[InternalTrade]:
    result = await db.execute(
        sa.select(InternalTrade).where(
            InternalTrade.project_id == project_id,
            InternalTrade.year == year,
            InternalTrade.is_deleted.is_(False),
        )
    )
    return list(result.scalars().all())


async def get_trade(db: AsyncSession, trade_id: UUID, project_id: UUID) -> InternalTrade | None:
    result = await db.execute(
        sa.select(InternalTrade).where(
            InternalTrade.id == trade_id,
            InternalTrade.project_id == project_id,
        )
    )
    return result.scalar_one_or_none()


async def create_trade(db: AsyncSession, project_id: UUID, data: InternalTradeCreate) -> InternalTrade:
    unrealized = data.unrealized_profit
    if unrealized is None and data.trade_amount is not None and data.cost_amount is not None:
        unrealized = data.trade_amount - data.cost_amount

    trade = InternalTrade(
        project_id=project_id,
        unrealized_profit=unrealized,
        **data.model_dump(exclude={"unrealized_profit"}),
    )
    db.add(trade)
    await db.commit()
    await db.refresh(trade)
    return trade


async def update_trade(
    db: AsyncSession, trade_id: UUID, project_id: UUID, data: InternalTradeUpdate
) -> InternalTrade | None:
    trade = await get_trade(db, trade_id, project_id)
    if not trade:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(trade, key, value)
    await db.commit()
    await db.refresh(trade)
    return trade


async def delete_trade(db: AsyncSession, trade_id: UUID, project_id: UUID) -> bool:
    trade = await get_trade(db, trade_id, project_id)
    if not trade:
        return False
    trade.soft_delete()
    await db.commit()
    return True


# ========== 内部往来 ==========


async def get_arap_list(db: AsyncSession, project_id: UUID, year: int) -> list[InternalArAp]:
    result = await db.execute(
        sa.select(InternalArAp).where(
            InternalArAp.project_id == project_id,
            InternalArAp.year == year,
            InternalArAp.is_deleted.is_(False),
        )
    )
    return list(result.scalars().all())


async def get_arap(db: AsyncSession, arap_id: UUID, project_id: UUID) -> InternalArAp | None:
    result = await db.execute(
        sa.select(InternalArAp).where(
            InternalArAp.id == arap_id,
            InternalArAp.project_id == project_id,
        )
    )
    return result.scalar_one_or_none()


async def create_arap(db: AsyncSession, project_id: UUID, data: InternalArApCreate) -> InternalArAp:
    diff = data.difference_amount
    if diff is None and data.debtor_amount is not None and data.creditor_amount is not None:
        diff = abs(data.debtor_amount - data.creditor_amount)

    arap = InternalArAp(
        project_id=project_id,
        difference_amount=diff,
        **data.model_dump(exclude={"difference_amount"}),
    )
    db.add(arap)
    await db.commit()
    await db.refresh(arap)
    return arap


async def update_arap(
    db: AsyncSession, arap_id: UUID, project_id: UUID, data: InternalArApUpdate
) -> InternalArAp | None:
    arap = await get_arap(db, arap_id, project_id)
    if not arap:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(arap, key, value)
    await db.commit()
    await db.refresh(arap)
    return arap


async def delete_arap(db: AsyncSession, arap_id: UUID, project_id: UUID) -> bool:
    arap = await get_arap(db, arap_id, project_id)
    if not arap:
        return False
    arap.soft_delete()
    await db.commit()
    return True


async def get_transaction_matrix(db: AsyncSession, project_id: UUID, year: int) -> TransactionMatrix:
    """生成内部交易矩阵"""
    trades = await get_trades(db, project_id, year)
    codes = sorted(set(t.seller_company_code for t in trades) | set(t.buyer_company_code for t in trades))

    matrix: dict[str, dict[str, Decimal]] = {c: {c2: Decimal("0") for c2 in codes} for c in codes}
    for t in trades:
        if t.trade_amount is not None:
            matrix[t.seller_company_code][t.buyer_company_code] += t.trade_amount

    return TransactionMatrix(company_codes=codes, matrix={
        k: {k2: v for k2, v in inner.items() if v != 0}
        for k, inner in matrix.items()
        if any(v != 0 for v in inner.values())
    })
