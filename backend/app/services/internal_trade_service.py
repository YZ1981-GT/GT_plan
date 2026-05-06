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


# ========== 内部抵消表自动汇总 [R11.3] ==========


async def auto_generate_elimination_entries(
    db: AsyncSession, project_id: UUID, year: int,
) -> list[dict]:
    """
    从 3 张内部抵消表（内部交易、内部往来、未实现利润）自动汇总生成合并抵消分录。

    流程：
    1. 汇总内部交易表 → 生成内部交易抵消分录（收入/成本对冲）
    2. 汇总内部往来表 → 生成内部往来抵消分录（应收/应付对冲）
    3. 计算未实现利润 → 生成未实现利润抵消分录

    返回待创建的抵消分录列表（尚未写入数据库，需调用方确认后创建）。
    """
    generated_entries: list[dict] = []

    # ── 1. 内部交易抵消 ──
    trades = await get_trades(db, project_id, year)
    # 按交易对（seller→buyer）汇总
    trade_pairs: dict[tuple[str, str], dict] = {}
    for t in trades:
        pair_key = (t.seller_company_code, t.buyer_company_code)
        if pair_key not in trade_pairs:
            trade_pairs[pair_key] = {
                "trade_amount": Decimal("0"),
                "cost_amount": Decimal("0"),
                "unrealized_profit": Decimal("0"),
            }
        trade_pairs[pair_key]["trade_amount"] += t.trade_amount or Decimal("0")
        trade_pairs[pair_key]["cost_amount"] += t.cost_amount or Decimal("0")
        trade_pairs[pair_key]["unrealized_profit"] += t.unrealized_profit or Decimal("0")

    for (seller, buyer), amounts in trade_pairs.items():
        if amounts["trade_amount"] > 0:
            generated_entries.append({
                "entry_type": "internal_trade",
                "description": f"内部交易抵消：{seller} → {buyer}",
                "related_company_codes": [seller, buyer],
                "lines": [
                    {
                        "account_code": "6001",
                        "account_name": "营业收入",
                        "debit_amount": str(amounts["trade_amount"]),
                        "credit_amount": "0",
                    },
                    {
                        "account_code": "6401",
                        "account_name": "营业成本",
                        "debit_amount": "0",
                        "credit_amount": str(amounts["cost_amount"]),
                    },
                ],
            })

            # 未实现利润抵消
            if amounts["unrealized_profit"] > 0:
                generated_entries.append({
                    "entry_type": "unrealized_profit",
                    "description": f"未实现利润抵消：{seller} → {buyer}",
                    "related_company_codes": [seller, buyer],
                    "lines": [
                        {
                            "account_code": "6401",
                            "account_name": "营业成本",
                            "debit_amount": str(amounts["unrealized_profit"]),
                            "credit_amount": "0",
                        },
                        {
                            "account_code": "1405",
                            "account_name": "库存商品",
                            "debit_amount": "0",
                            "credit_amount": str(amounts["unrealized_profit"]),
                        },
                    ],
                })

    # ── 2. 内部往来抵消 ──
    arap_list = await get_arap_list(db, project_id, year)
    # 按往来对汇总
    arap_pairs: dict[tuple[str, str], Decimal] = {}
    for a in arap_list:
        pair_key = (a.debtor_company_code, a.creditor_company_code)
        if pair_key not in arap_pairs:
            arap_pairs[pair_key] = Decimal("0")
        # 取较小值作为可抵消金额（差额需要单独处理）
        debtor_amt = a.debtor_amount or Decimal("0")
        creditor_amt = a.creditor_amount or Decimal("0")
        offset_amount = min(debtor_amt, creditor_amt)
        arap_pairs[pair_key] += offset_amount

    for (debtor, creditor), amount in arap_pairs.items():
        if amount > 0:
            generated_entries.append({
                "entry_type": "internal_ar_ap",
                "description": f"内部往来抵消：{debtor} ↔ {creditor}",
                "related_company_codes": [debtor, creditor],
                "lines": [
                    {
                        "account_code": "2202",
                        "account_name": "应付账款",
                        "debit_amount": str(amount),
                        "credit_amount": "0",
                    },
                    {
                        "account_code": "1122",
                        "account_name": "应收账款",
                        "debit_amount": "0",
                        "credit_amount": str(amount),
                    },
                ],
            })

    return generated_entries
