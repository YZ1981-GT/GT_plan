"""内部交易与往来服务

功能覆盖：
- 内部交易 CRUD（自动计算 unrealized_profit）
- 内部往来 CRUD（自动计算 difference_amount 和 reconciliation_status）
- 内部交易矩阵（get_transaction_matrix）
- 批量核对内部往来（reconcile_ar_ap）
- 自动生成抵消分录（auto_generate_eliminations）
- 事件发布：INTERNAL_TRADE_CHANGED / INTERNAL_ARAP_CHANGED
"""

from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.audit_platform_schemas import EventPayload, EventType
from app.models.consolidation_models import (
    EliminationEntry,
    EliminationEntryType,
    InternalArAp,
    InternalTrade,
    ReconciliationStatus,
    TradeType,
)
from app.models.consolidation_schemas import (
    EliminationEntryBatchCreate,
    InternalArApCreate,
    InternalArApResponse,
    InternalArApUpdate,
    InternalTradeCreate,
    InternalTradeResponse,
    InternalTradeUpdate,
    TransactionMatrix,
)
from app.services.event_bus import event_bus


# ---------------------------------------------------------------------------
# 内部交易
# ---------------------------------------------------------------------------


def _calc_unrealized_profit(
    trade_amount: Decimal | None,
    cost_amount: Decimal | None,
    inventory_remaining_ratio: Decimal | None,
) -> Decimal | None:
    """计算未实现利润 = (售价 - 成本) × 期末存货留存比例"""
    if trade_amount is None or cost_amount is None:
        return None
    ratio = inventory_remaining_ratio if inventory_remaining_ratio is not None else Decimal("1")
    profit = trade_amount - cost_amount
    return profit * ratio


def _publish_trade_event(project_id: UUID, year: int) -> None:
    """发布内部交易变更事件（同步，不阻塞）"""
    try:
        payload = EventPayload(
            event_type=EventType.INTERNAL_TRADE_CHANGED,
            project_id=project_id,
            year=year,
            account_codes=[],
        )
        # 同步发布，不等待
        import asyncio
        loop = asyncio.get_event_loop()
        loop.create_task(event_bus.publish(payload))
    except Exception:
        pass


def get_trades(db: Session, project_id: UUID, year: int) -> list[InternalTrade]:
    return (
        db.query(InternalTrade)
        .filter(
            InternalTrade.project_id == project_id,
            InternalTrade.year == year,
            InternalTrade.is_deleted.is_(False),
        )
        .all()
    )


def get_trade(db: Session, trade_id: UUID, project_id: UUID) -> InternalTrade | None:
    return (
        db.query(InternalTrade)
        .filter(
            InternalTrade.id == trade_id,
            InternalTrade.project_id == project_id,
            InternalTrade.is_deleted.is_(False),
        )
        .first()
    )


def create_trade(
    db: Session, project_id: UUID, data: InternalTradeCreate
) -> InternalTrade:
    """创建内部交易，自动计算未实现利润。

    未实现利润公式：
    - 商品类交易：unrealized_profit = (trade_amount - cost_amount) * inventory_remaining_ratio
    - 全部未实现时（inventory_remaining_ratio=1）：unrealized_profit = trade_amount - cost_amount
    """
    unrealized = data.unrealized_profit
    if unrealized is None and data.trade_amount is not None and data.cost_amount is not None:
        unrealized = _calc_unrealized_profit(
            data.trade_amount,
            data.cost_amount,
            data.inventory_remaining_ratio,
        )

    trade = InternalTrade(
        project_id=project_id,
        unrealized_profit=unrealized,
        **data.model_dump(exclude={"unrealized_profit"}),
    )
    db.add(trade)
    db.commit()
    db.refresh(trade)
    _publish_trade_event(project_id, data.year)
    return trade


def update_trade(
    db: Session, trade_id: UUID, project_id: UUID, data: InternalTradeUpdate
) -> InternalTrade | None:
    """更新内部交易，若 trade_amount/cost_amount/inventory_remaining_ratio 变化则重算 unrealized_profit。"""
    trade = get_trade(db, trade_id, project_id)
    if not trade:
        return None

    changes = data.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(trade, key, value)

    # 如果相关字段变化则重算
    recalc = (
        "trade_amount" in changes
        or "cost_amount" in changes
        or "inventory_remaining_ratio" in changes
    )
    if recalc:
        trade.unrealized_profit = _calc_unrealized_profit(
            trade.trade_amount,
            trade.cost_amount,
            trade.inventory_remaining_ratio,
        )

    db.commit()
    db.refresh(trade)
    _publish_trade_event(project_id, trade.year)
    return trade


def delete_trade(db: Session, trade_id: UUID, project_id: UUID) -> bool:
    trade = get_trade(db, trade_id, project_id)
    if not trade:
        return False
    year = trade.year
    trade.is_deleted = True
    db.commit()
    _publish_trade_event(project_id, year)
    return True


# ---------------------------------------------------------------------------
# 内部往来
# ---------------------------------------------------------------------------


def _recalc_arap_fields(debtor_amount: Decimal | None, creditor_amount: Decimal | None):
    """根据借方/贷方金额计算差额和核对状态"""
    if debtor_amount is None or creditor_amount is None:
        return Decimal("0"), ReconciliationStatus.unmatched
    diff = debtor_amount - creditor_amount
    if diff == 0:
        return Decimal("0"), ReconciliationStatus.matched
    return abs(diff), ReconciliationStatus.unmatched


def _publish_arap_event(project_id: UUID, year: int) -> None:
    try:
        payload = EventPayload(
            event_type=EventType.INTERNAL_ARAP_CHANGED,
            project_id=project_id,
            year=year,
            account_codes=[],
        )
        import asyncio
        loop = asyncio.get_event_loop()
        loop.create_task(event_bus.publish(payload))
    except Exception:
        pass


def get_arap_list(db: Session, project_id: UUID, year: int) -> list[InternalArAp]:
    return (
        db.query(InternalArAp)
        .filter(
            InternalArAp.project_id == project_id,
            InternalArAp.year == year,
            InternalArAp.is_deleted.is_(False),
        )
        .all()
    )


def get_arap(db: Session, arap_id: UUID, project_id: UUID) -> InternalArAp | None:
    return (
        db.query(InternalArAp)
        .filter(
            InternalArAp.id == arap_id,
            InternalArAp.project_id == project_id,
            InternalArAp.is_deleted.is_(False),
        )
        .first()
    )


def create_arap(db: Session, project_id: UUID, data: InternalArApCreate) -> InternalArAp:
    """创建内部往来，自动计算差额和核对状态。

    - difference_amount = |debtor_amount - creditor_amount|
    - reconciliation_status = matched（差额=0）/ unmatched（差额≠0）
    """
    diff = data.difference_amount
    status = data.reconciliation_status
    if diff is None and data.debtor_amount is not None and data.creditor_amount is not None:
        diff, status = _recalc_arap_fields(data.debtor_amount, data.creditor_amount)
    elif diff is not None and status == ReconciliationStatus.unmatched:
        pass  # 用户显式传入则用用户值

    arap = InternalArAp(
        project_id=project_id,
        difference_amount=diff,
        reconciliation_status=status,
        **data.model_dump(exclude={"difference_amount", "reconciliation_status"}),
    )
    db.add(arap)
    db.commit()
    db.refresh(arap)
    _publish_arap_event(project_id, data.year)
    return arap


def update_arap(
    db: Session, arap_id: UUID, project_id: UUID, data: InternalArApUpdate
) -> InternalArAp | None:
    """更新内部往来，若借方/贷方金额变化则重算差额和核对状态。"""
    arap = get_arap(db, arap_id, project_id)
    if not arap:
        return None

    changes = data.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(arap, key, value)

    # 若金额字段变化则重算
    recalc = "debtor_amount" in changes or "creditor_amount" in changes
    if recalc:
        arap.difference_amount, arap.reconciliation_status = _recalc_arap_fields(
            arap.debtor_amount, arap.creditor_amount
        )
    # 若用户显式修改核对状态则覆盖
    if "reconciliation_status" in changes and data.reconciliation_status is not None:
        arap.reconciliation_status = data.reconciliation_status

    db.commit()
    db.refresh(arap)
    _publish_arap_event(project_id, arap.year)
    return arap


def delete_arap(db: Session, arap_id: UUID, project_id: UUID) -> bool:
    arap = get_arap(db, arap_id, project_id)
    if not arap:
        return False
    year = arap.year
    arap.is_deleted = True
    db.commit()
    _publish_arap_event(project_id, year)
    return True


# ---------------------------------------------------------------------------
# 交易矩阵
# ---------------------------------------------------------------------------


def get_transaction_matrix(
    db: Session, project_id: UUID, year: int
) -> TransactionMatrix:
    """生成内部交易矩阵，行=销售方，列=采购方，值=交易金额合计。"""
    trades = get_trades(db, project_id, year)
    codes = sorted(
        set(t.seller_company_code for t in trades)
        | set(t.buyer_company_code for t in trades)
    )

    matrix: dict[str, dict[str, Decimal]] = {
        c: {c2: Decimal("0") for c2 in codes} for c in codes
    }
    for t in trades:
        if t.trade_amount is not None:
            matrix[t.seller_company_code][t.buyer_company_code] += t.trade_amount

    # 只返回非零行/列
    return TransactionMatrix(
        company_codes=codes,
        matrix={
            k: {k2: v for k2, v in inner.items() if v != 0}
            for k, inner in matrix.items()
            if any(v != 0 for v in inner.values())
        },
    )


# ---------------------------------------------------------------------------
# 批量核对内部往来
# ---------------------------------------------------------------------------


def reconcile_arap(db: Session, project_id: UUID, year: int) -> list[InternalArAp]:
    """批量核对内部往来：

    1. 对每对（A, B）往来，按 debtor_company_code/creditor_company_code 配对
    2. 差异金额 = abs(debtor_amount - creditor_amount)
    3. 差异为0 → matched；差异≠0 → unmatched
    4. 对已核对行可标记为 adjusted（用户手动调整后）
    5. 返回所有更新后的往来记录
    """
    arap_list = get_arap_list(db, project_id, year)

    updated: list[InternalArAp] = []
    for arap in arap_list:
        changed = False
        if arap.debtor_amount is not None and arap.creditor_amount is not None:
            diff = abs(arap.debtor_amount - arap.creditor_amount)
            status = (
                ReconciliationStatus.matched
                if diff == 0
                else ReconciliationStatus.unmatched
            )
            if arap.difference_amount != diff:
                arap.difference_amount = diff
                changed = True
            if arap.reconciliation_status != status:
                arap.reconciliation_status = status
                changed = True
            if changed:
                updated.append(arap)

    if updated:
        db.commit()
        for arap in updated:
            db.refresh(arap)
        _publish_arap_event(project_id, year)

    return updated


# ---------------------------------------------------------------------------
# 自动生成抵消分录
# ---------------------------------------------------------------------------

# 标准科目编码约定（可通过配置覆盖）
_REVENUE_ACCOUNT = "6001"          # 主营业务收入
_COGS_ACCOUNT = "6401"              # 主营业务成本
_INVENTORY_ACCOUNT = "1405"         # 库存商品
_AR_ACCOUNT = "1122"                # 应收账款
_AP_ACCOUNT = "2202"                # 应付账款
_RETAINED_EARNINGS_ACCOUNT = "4104" # 未分配利润


def _ensure_elimination_entry(
    db: Session,
    project_id: UUID,
    year: int,
    entry_type: EliminationEntryType,
    description: str,
    lines: list[dict],
    related_company_codes: list[str],
    is_continuous: bool = False,
) -> UUID:
    """创建或查找已存在的同组抵消分录组。返回 entry_group_id。"""
    group_id = uuid4()

    # 生成编号
    prefix_map = {
        EliminationEntryType.internal_trade: "IT",
        EliminationEntryType.unrealized_profit: "UP",
        EliminationEntryType.internal_ar_ap: "IA",
        EliminationEntryType.equity: "CE",
        EliminationEntryType.other: "OT",
    }
    prefix = prefix_map.get(entry_type, "OT")

    seq = (
        db.query(EliminationEntry)
        .filter(
            EliminationEntry.project_id == project_id,
            EliminationEntry.year == year,
            EliminationEntry.entry_no.like(f"{prefix}-{year}-%"),
            EliminationEntry.is_deleted.is_(False),
        )
        .count()
    ) + 1
    entry_no = f"{prefix}-{year}-{seq:03d}"

    for line in lines:
        entry = EliminationEntry(
            project_id=project_id,
            year=year,
            entry_no=entry_no,
            entry_type=entry_type,
            description=description,
            account_code=line["account_code"],
            account_name=line.get("account_name"),
            debit_amount=line.get("debit_amount", Decimal("0")),
            credit_amount=line.get("credit_amount", Decimal("0")),
            entry_group_id=group_id,
            related_company_codes=related_company_codes,
            is_continuous=is_continuous,
        )
        db.add(entry)

    db.flush()
    return group_id


def auto_generate_eliminations(
    db: Session, project_id: UUID, year: int
) -> list[EliminationEntry]:
    """根据内部交易和内部往来自动生成抵消分录。

    规则：
    1. 商品类内部交易（goods）：
       a) 收入成本抵消：借 主营业务收入，贷 主营业务成本
       b) 期末存货未实现利润抵消（如 inventory_remaining_ratio > 0）：
          借 主营业务成本，贷 库存商品
    2. 服务类交易（services/assets）：仅做收入成本抵消
    3. 内部往来：
       a) 应收应付抵消：借 应付账款，贷 应收账款（如金额一致）
       b) 如金额不一致，记录差异（需人工确认原因）

    Returns:
        新创建的 EliminationEntry 列表（按 entry_group_id 分组）
    """
    created_entries: list[EliminationEntry] = []

    # 1. 处理内部交易
    trades = get_trades(db, project_id, year)
    for trade in trades:
        if trade.trade_amount is None:
            continue

        seller = trade.seller_company_code
        buyer = trade.buyer_company_code
        related = [seller, buyer]

        if trade.trade_type == TradeType.goods:
            # 收入成本抵消
            if trade.trade_amount and trade.trade_amount > 0:
                lines = [
                    {
                        "account_code": _REVENUE_ACCOUNT,
                        "account_name": "主营业务收入",
                        "debit_amount": trade.trade_amount,
                        "credit_amount": Decimal("0"),
                    },
                    {
                        "account_code": _COGS_ACCOUNT,
                        "account_name": "主营业务成本",
                        "debit_amount": Decimal("0"),
                        "credit_amount": trade.trade_amount,
                    },
                ]
                _ensure_elimination_entry(
                    db,
                    project_id,
                    year,
                    EliminationEntryType.internal_trade,
                    f"内部商品交易抵消：{seller} → {buyer}",
                    lines,
                    related,
                )
                created_entries.extend(
                    db.query(EliminationEntry)
                    .filter(
                        EliminationEntry.project_id == project_id,
                        EliminationEntry.year == year,
                        EliminationEntry.description
                        == f"内部商品交易抵消：{seller} → {buyer}",
                        EliminationEntry.is_deleted.is_(False),
                    )
                    .all()
                )

            # 未实现利润抵消（期末存货）
            if (
                trade.unrealized_profit
                and trade.unrealized_profit > 0
                and trade.inventory_remaining_ratio
                and trade.inventory_remaining_ratio > 0
            ):
                unreal_lines = [
                    {
                        "account_code": _COGS_ACCOUNT,
                        "account_name": "主营业务成本",
                        "debit_amount": trade.unrealized_profit,
                        "credit_amount": Decimal("0"),
                    },
                    {
                        "account_code": _INVENTORY_ACCOUNT,
                        "account_name": "库存商品",
                        "debit_amount": Decimal("0"),
                        "credit_amount": trade.unrealized_profit,
                    },
                ]
                _ensure_elimination_entry(
                    db,
                    project_id,
                    year,
                    EliminationEntryType.unrealized_profit,
                    f"未实现利润抵消（存货）：{seller} → {buyer}，"
                    f"比例={trade.inventory_remaining_ratio}",
                    unreal_lines,
                    related,
                )
                created_entries.extend(
                    db.query(EliminationEntry)
                    .filter(
                        EliminationEntry.project_id == project_id,
                        EliminationEntry.year == year,
                        EliminationEntry.description
                        == f"未实现利润抵消（存货）：{seller} → {buyer}，"
                        f"比例={trade.inventory_remaining_ratio}",
                        EliminationEntry.is_deleted.is_(False),
                    )
                    .all()
                )

        elif trade.trade_type in (TradeType.services, TradeType.assets):
            # 服务/资产交易：仅收入成本抵消
            if trade.trade_amount and trade.trade_amount > 0:
                lines = [
                    {
                        "account_code": _REVENUE_ACCOUNT,
                        "account_name": "主营业务收入",
                        "debit_amount": trade.trade_amount,
                        "credit_amount": Decimal("0"),
                    },
                    {
                        "account_code": _COGS_ACCOUNT,
                        "account_name": "主营业务成本",
                        "debit_amount": Decimal("0"),
                        "credit_amount": trade.trade_amount,
                    },
                ]
                _ensure_elimination_entry(
                    db,
                    project_id,
                    year,
                    EliminationEntryType.internal_trade,
                    f"内部{trade.trade_type.value}交易抵消：{seller} → {buyer}",
                    lines,
                    related,
                )
                created_entries.extend(
                    db.query(EliminationEntry)
                    .filter(
                        EliminationEntry.project_id == project_id,
                        EliminationEntry.year == year,
                        EliminationEntry.description
                        == f"内部{trade.trade_type.value}交易抵消：{seller} → {buyer}",
                        EliminationEntry.is_deleted.is_(False),
                    )
                    .all()
                )

    # 2. 处理内部往来
    arap_list = get_arap_list(db, project_id, year)
    for arap in arap_list:
        if arap.debtor_amount is None or arap.creditor_amount is None:
            continue

        debtor = arap.debtor_company_code
        creditor = arap.creditor_company_code
        related = [debtor, creditor]

        if arap.reconciliation_status == ReconciliationStatus.matched:
            # 借贷金额一致，完全抵消
            amount = arap.debtor_amount  # = creditor_amount
            lines = [
                {
                    "account_code": _AP_ACCOUNT,
                    "account_name": "应付账款",
                    "debit_amount": amount,
                    "credit_amount": Decimal("0"),
                },
                {
                    "account_code": _AR_ACCOUNT,
                    "account_name": "应收账款",
                    "debit_amount": Decimal("0"),
                    "credit_amount": amount,
                },
            ]
            _ensure_elimination_entry(
                db,
                project_id,
                year,
                EliminationEntryType.internal_ar_ap,
                f"内部往来抵消（已匹配）：{debtor} ←→ {creditor}",
                lines,
                related,
            )
            created_entries.extend(
                db.query(EliminationEntry)
                .filter(
                    EliminationEntry.project_id == project_id,
                    EliminationEntry.year == year,
                    EliminationEntry.description
                    == f"内部往来抵消（已匹配）：{debtor} ←→ {creditor}",
                    EliminationEntry.is_deleted.is_(False),
                )
                .all()
            )
        elif arap.reconciliation_status == ReconciliationStatus.unmatched:
            # 金额不一致，生成差异抵消并记录
            lines = [
                {
                    "account_code": _AP_ACCOUNT,
                    "account_name": "应付账款",
                    "debit_amount": arap.creditor_amount,
                    "credit_amount": Decimal("0"),
                },
                {
                    "account_code": _AR_ACCOUNT,
                    "account_name": "应收账款",
                    "debit_amount": Decimal("0"),
                    "credit_amount": arap.debtor_amount,
                },
            ]
            _ensure_elimination_entry(
                db,
                project_id,
                year,
                EliminationEntryType.internal_ar_ap,
                f"内部往来抵消（有差异）：{debtor} ←→ {creditor}，"
                f"差异={arap.difference_amount}，原因={arap.difference_reason or '待查'}",
                lines,
                related,
            )
            created_entries.extend(
                db.query(EliminationEntry)
                .filter(
                    EliminationEntry.project_id == project_id,
                    EliminationEntry.year == year,
                    EliminationEntry.description
                    == f"内部往来抵消（有差异）：{debtor} ←→ {creditor}，"
                    f"差异={arap.difference_amount}，原因={arap.difference_reason or '待查'}",
                    EliminationEntry.is_deleted.is_(False),
                )
                .all()
            )

    db.commit()

    # 发布事件触发合并试算表重算
    try:
        payload = EventPayload(
            event_type=EventType.ELIMINATION_CREATED,
            project_id=project_id,
            year=year,
            account_codes=[],
        )
        import asyncio
        loop = asyncio.get_event_loop()
        loop.create_task(event_bus.publish(payload))
    except Exception:
        pass

    return created_entries
