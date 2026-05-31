"""Phase 2 — B3 自动抵销生成服务（接通孤立的 4 类抵销规则引擎）.

关联：consol-phase2-orchestration Task 4 / 需求 4 / ADR-CONSOL-203。

职责：把 `consol_elimination_rules.calculate_elimination_amount`（4 类预设规则，
此前为孤儿未接通）接入端点，从子公司内部交易/往来数据自动生成 `EliminationEntry`
**草稿**（review_status=draft）。

铁律（S3 / ADR-CONSOL-203）：
- 自动生成的所有 EliminationEntry 强制 review_status == DRAFT（绝不直接 APPROVED）。
- 本服务只持久化草稿，**不触发任何重算**。
- 审计师复核草稿（→APPROVED）后，经 Phase 1 `ELIMINATION_APPROVED` 事件触发
  worksheet + trial 重算才进合并数（4.4，依赖 Phase 1）。
- 无匹配数据时 calculate_elimination_amount 返回 0 → 不生成 entry、不报错（EH4 / 4.3）。

说明：calculate_elimination_amount 是简化的启发式估算引擎；自动生成的金额是
供审计师复核/调整的**草稿估算**（符合 ADR-CONSOL-203「draft + 人工审批」原则），
非最终合并数。

Validates: Requirements 4.1~4.4 (Property S3)
"""

from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consolidation_models import (
    EliminationEntry,
    EliminationEntryType,
    InternalArAp,
    InternalTrade,
    ReviewStatusEnum,
)
from app.services.consol_elimination_rules import (
    calculate_elimination_amount,
    get_rule,
)
from app.services.internal_trade_service import get_arap_list, get_trades

logger = logging.getLogger(__name__)

ZERO = Decimal("0")

# 4 类预设规则按固定顺序生成（与 consol_elimination_rules.ELIMINATION_RULES 对齐）
_RULE_TYPES: tuple[str, ...] = (
    "internal_ar",
    "internal_revenue",
    "internal_inventory_unrealized",
    "internal_dividend",
)

# rule_type → EliminationEntryType（合并模块抵消分录类型枚举）
# 说明：枚举无「股利」专属类型，internal_dividend 归入 equity（股利分配属权益变动）。
_RULE_TYPE_TO_ENTRY_TYPE: dict[str, EliminationEntryType] = {
    "internal_ar": EliminationEntryType.internal_ar_ap,
    "internal_revenue": EliminationEntryType.internal_trade,
    "internal_inventory_unrealized": EliminationEntryType.unrealized_profit,
    "internal_dividend": EliminationEntryType.equity,
}

# rule_type → (代表性科目代码, 代表性科目名称)
_RULE_TYPE_TO_ACCOUNT: dict[str, tuple[str, str]] = {
    "internal_ar": ("1122", "应收账款"),
    "internal_revenue": ("6001", "营业收入"),
    "internal_inventory_unrealized": ("1405", "库存商品"),
    "internal_dividend": ("6111", "投资收益"),
}


def _build_child_projects_for_rule(
    rule_type: str,
    trades: list[InternalTrade],
    arap_list: list[InternalArAp],
) -> list[dict]:
    """按规则的 match_logic 从内部交易/往来数据构造 calculate_elimination_amount 的入参.

    - internal_ar (by_company_pair → internal_balance): 取内部往来每对的可抵销金额
      min(debtor, creditor)。
    - internal_revenue (by_company_pair → internal_balance): 取内部交易金额 trade_amount。
    - internal_inventory_unrealized (by_inventory_margin → unrealized_profit): 取未实现利润。
    - internal_dividend (by_dividend_declaration → internal_dividend): 系统暂无内部股利数据源，
      返回空列表 → 引擎算出 0 → 不生成 entry（EH4，属正常）。
    """
    if rule_type == "internal_ar":
        result: list[dict] = []
        for a in arap_list:
            debtor = a.debtor_amount or ZERO
            creditor = a.creditor_amount or ZERO
            offset = min(debtor, creditor)
            if offset > ZERO:
                result.append({"internal_balance": offset})
        return result

    if rule_type == "internal_revenue":
        return [
            {"internal_balance": t.trade_amount}
            for t in trades
            if t.trade_amount is not None and t.trade_amount > ZERO
        ]

    if rule_type == "internal_inventory_unrealized":
        return [
            {"unrealized_profit": t.unrealized_profit}
            for t in trades
            if t.unrealized_profit is not None and t.unrealized_profit > ZERO
        ]

    if rule_type == "internal_dividend":
        # 暂无内部股利数据源，交由引擎返回 0（EH4）
        return []

    return []


def _collect_related_company_codes(
    rule_type: str,
    trades: list[InternalTrade],
    arap_list: list[InternalArAp],
) -> list[str]:
    """收集该规则涉及的子公司代码（去重，便于审计追溯）。"""
    codes: set[str] = set()
    if rule_type == "internal_ar":
        for a in arap_list:
            if a.debtor_company_code:
                codes.add(a.debtor_company_code)
            if a.creditor_company_code:
                codes.add(a.creditor_company_code)
    else:
        # 收入/未实现利润/股利均源自内部交易
        for t in trades:
            if t.seller_company_code:
                codes.add(t.seller_company_code)
            if t.buyer_company_code:
                codes.add(t.buyer_company_code)
    return sorted(codes)


async def auto_generate_draft_eliminations(
    db: AsyncSession,
    project_id: UUID,
    year: int,
) -> list[EliminationEntry]:
    """从子公司内部交易/往来自动生成抵销分录草稿（4 类规则）.

    对 4 类预设规则分别调用 calculate_elimination_amount：
    - 金额 == 0：跳过（不生成、不报错，EH4 / 4.3）。
    - 金额 != 0：生成 EliminationEntry，**强制 review_status=draft**（S3 / 4.2），db.add。

    本函数**不触发任何重算**（S3）；审批后由 Phase 1 事件链触发（4.4）。

    Returns:
        本次生成的 EliminationEntry 列表（已持久化，含 id）。
    """
    trades = await get_trades(db, project_id, year)
    arap_list = await get_arap_list(db, project_id, year)

    # 同一次生成的草稿共享一个 entry_group_id，便于成组复核
    group_id = uuid4()
    created: list[EliminationEntry] = []
    seq = 0

    for rule_type in _RULE_TYPES:
        rule = get_rule(rule_type)
        if rule is None:
            continue

        child_projects = _build_child_projects_for_rule(rule_type, trades, arap_list)
        amount = calculate_elimination_amount(rule_type, child_projects=child_projects, ctx={})

        # EH4 / 4.3：无匹配数据返回 0 → 不生成、不报错
        if amount == ZERO:
            logger.debug(
                "auto-elimination: rule=%s amount=0, skip (project=%s year=%s)",
                rule_type, project_id, year,
            )
            continue

        seq += 1
        entry_type = _RULE_TYPE_TO_ENTRY_TYPE[rule_type]
        account_code, account_name = _RULE_TYPE_TO_ACCOUNT[rule_type]

        entry = EliminationEntry(
            id=uuid4(),
            project_id=project_id,
            year=year,
            entry_no=f"AUTO-{rule_type}-{seq:03d}",
            entry_type=entry_type,
            description=f"{rule['name']}（自动生成草稿，待复核）",
            account_code=account_code,
            account_name=account_name,
            # 抵销分录借贷成对：以估算金额构造平衡分录
            debit_amount=amount,
            credit_amount=amount,
            lines=[
                {
                    "account_code": account_code,
                    "account_name": account_name,
                    "debit_amount": str(amount),
                    "credit_amount": str(amount),
                    "rule_type": rule_type,
                }
            ],
            entry_group_id=group_id,
            related_company_codes=_collect_related_company_codes(rule_type, trades, arap_list),
            is_continuous=False,
            # S3 / ADR-CONSOL-203：自动生成强制草稿，绝不直接 APPROVED
            review_status=ReviewStatusEnum.draft,
        )
        db.add(entry)
        created.append(entry)

    if created:
        # 仅持久化草稿；不触发任何重算（S3）。审批后由 Phase 1 ELIMINATION_APPROVED 事件触发。
        await db.commit()
        for entry in created:
            await db.refresh(entry)

    logger.info(
        "auto-elimination: generated %d draft entries (project=%s year=%s group=%s)",
        len(created), project_id, year, group_id,
    )
    return created
