"""内部交易与往来服务"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_

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


def get_trades(db, project_id: UUID, year: int) -> list[InternalTrade]:
    return (
        db.query(InternalTrade)
        .filter(
            InternalTrade.project_id == project_id,
            InternalTrade.year == year,
            InternalTrade.is_deleted.is_(False),
        )
        .all()
    )


def get_trade(db, trade_id: UUID, project_id: UUID) -> InternalTrade | None:
    return (
        db.query(InternalTrade)
        .filter(InternalTrade.id == trade_id, InternalTrade.project_id == project_id)
        .first()
    )


def create_trade(db, project_id: UUID, data: InternalTradeCreate) -> InternalTrade:
    # 自动计算未实现利润
    unrealized = data.unrealized_profit
    if unrealized is None and data.trade_amount is not None and data.cost_amount is not None:
        unrealized = data.trade_amount - data.cost_amount

    trade = InternalTrade(
        project_id=project_id,
        unrealized_profit=unrealized,
        **data.model_dump(exclude={"unrealized_profit"}),
    )
    db.add(trade)
    db.commit()
    db.refresh(trade)
    return trade


def update_trade(
    db, trade_id: UUID, project_id: UUID, data: InternalTradeUpdate
) -> InternalTrade | None:
    trade = get_trade(db, trade_id, project_id)
    if not trade:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(trade, key, value)
    db.commit()
    db.refresh(trade)
    return trade


def delete_trade(db, trade_id: UUID, project_id: UUID) -> bool:
    trade = get_trade(db, trade_id, project_id)
    if not trade:
        return False
    trade.is_deleted = True
    db.commit()
    return True


# ========== 内部往来 ==========


def get_arap_list(db, project_id: UUID, year: int) -> list[InternalArAp]:
    return (
        db.query(InternalArAp)
        .filter(
            InternalArAp.project_id == project_id,
            InternalArAp.year == year,
            InternalArAp.is_deleted.is_(False),
        )
        .all()
    )


def get_arap(db, arap_id: UUID, project_id: UUID) -> InternalArAp | None:
    return (
        db.query(InternalArAp)
        .filter(InternalArAp.id == arap_id, InternalArAp.project_id == project_id)
        .first()
    )


def create_arap(db, project_id: UUID, data: InternalArApCreate) -> InternalArAp:
    # 自动计算差额
    diff = data.difference_amount
    if diff is None and data.debtor_amount is not None and data.creditor_amount is not None:
        diff = abs(data.debtor_amount - data.creditor_amount)

    arap = InternalArAp(
        project_id=project_id,
        difference_amount=diff,
        **data.model_dump(exclude={"difference_amount"}),
    )
    db.add(arap)
    db.commit()
    db.refresh(arap)
    return arap


def update_arap(
    db, arap_id: UUID, project_id: UUID, data: InternalArApUpdate
) -> InternalArAp | None:
    arap = get_arap(db, arap_id, project_id)
    if not arap:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(arap, key, value)
    db.commit()
    db.refresh(arap)
    return arap


def delete_arap(db, arap_id: UUID, project_id: UUID) -> bool:
    arap = get_arap(db, arap_id, project_id)
    if not arap:
        return False
    arap.is_deleted = True
    db.commit()
    return True


def get_transaction_matrix(db, project_id: UUID, year: int) -> TransactionMatrix:
    """生成内部交易矩阵"""
    trades = get_trades(db, project_id, year)
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
