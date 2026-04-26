"""合并差额表计算引擎

核心公式：
- 叶子节点: children_amount_sum = 本企业审定数（从 trial_balance 取）
- 中间节点: children_amount_sum = Σ(直接下级 consolidated_amount)
- net_difference = (adjustment_debit - adjustment_credit) + (elimination_debit - elimination_credit)
- consolidated_amount = children_amount_sum + net_difference

recalc_full: 后序遍历，从叶子到根逐层计算
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TrialBalance
from app.models.consolidation_models import ConsolWorksheet, EliminationEntry
from app.services.consol_tree_service import TreeNode, build_tree, get_descendants


ZERO = Decimal("0")


async def recalc_full(
    db: AsyncSession,
    project_id: UUID,
    year: int,
) -> dict:
    """全量重算差额表（后序遍历）。

    Returns summary dict with node_count and account_count.
    """
    tree = await build_tree(db, project_id)
    if not tree:
        return {"node_count": 0, "account_count": 0}

    # 收集所有科目编码（从 trial_balance 和已有 worksheet）
    account_codes = await _collect_account_codes(db, project_id, year, tree)

    # 预加载抵消分录映射
    elim_map = await _get_elimination_map(db, project_id, year)

    # 后序遍历计算
    node_count = 0
    await _calc_node(db, project_id, year, tree, account_codes, elim_map)
    node_count = 1 + len(get_descendants(tree))

    await db.commit()
    return {"node_count": node_count, "account_count": len(account_codes)}


async def _collect_account_codes(
    db: AsyncSession, project_id: UUID, year: int, tree: TreeNode
) -> set[str]:
    """收集所有涉及的科目编码"""
    codes: set[str] = set()

    # 从所有叶子节点的 trial_balance 收集
    all_nodes = [tree] + get_descendants(tree)
    project_ids = [n.project_id for n in all_nodes]

    result = await db.execute(
        sa.select(TrialBalance.standard_account_code).distinct().where(
            TrialBalance.project_id.in_(project_ids),
            TrialBalance.year == year,
            TrialBalance.is_deleted == sa.false(),
        )
    )
    for row in result.all():
        codes.add(row[0])

    # 从已有 worksheet 收集
    result = await db.execute(
        sa.select(ConsolWorksheet.account_code).distinct().where(
            ConsolWorksheet.project_id == project_id,
            ConsolWorksheet.year == year,
            ConsolWorksheet.is_deleted == sa.false(),
        )
    )
    for row in result.all():
        codes.add(row[0])

    # 从抵消分录收集
    result = await db.execute(
        sa.select(EliminationEntry.account_code).distinct().where(
            EliminationEntry.project_id == project_id,
            EliminationEntry.year == year,
            EliminationEntry.is_deleted == sa.false(),
        )
    )
    for row in result.all():
        codes.add(row[0])

    return codes


async def _get_elimination_map(
    db: AsyncSession, project_id: UUID, year: int
) -> dict[str, list[EliminationEntry]]:
    """按 related_company_codes 关联抵消分录到节点。

    Returns {company_code: [entries]} mapping.
    """
    result = await db.execute(
        sa.select(EliminationEntry).where(
            EliminationEntry.project_id == project_id,
            EliminationEntry.year == year,
            EliminationEntry.is_deleted == sa.false(),
        )
    )
    entries = result.scalars().all()

    elim_map: dict[str, list[EliminationEntry]] = {}
    for entry in entries:
        # related_company_codes is JSONB, could be list or dict
        codes = entry.related_company_codes
        if isinstance(codes, list):
            for code in codes:
                elim_map.setdefault(code, []).append(entry)
        elif isinstance(codes, dict):
            for code in codes.values():
                if isinstance(code, str):
                    elim_map.setdefault(code, []).append(entry)
        # Also index by account_code for the parent project
        # (entries without specific company codes apply to the root)

    return elim_map


async def _calc_node(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    node: TreeNode,
    account_codes: set[str],
    elim_map: dict[str, list[EliminationEntry]],
) -> None:
    """递归计算单个节点的差额表（后序遍历：先算子节点再算自身）"""
    # 先递归计算所有子节点
    for child in node.children:
        await _calc_node(db, project_id, year, child, account_codes, elim_map)

    is_leaf = len(node.children) == 0

    for acct_code in account_codes:
        if is_leaf:
            # 叶子节点: children_amount_sum = 本企业审定数
            children_sum = await _get_audited_amount(db, node.project_id, year, acct_code)
        else:
            # 中间节点: children_amount_sum = Σ(直接下级 consolidated_amount)
            children_sum = ZERO
            for child in node.children:
                child_ws = await _get_worksheet_row(
                    db, project_id, child.company_code, acct_code, year
                )
                if child_ws:
                    children_sum += child_ws.consolidated_amount

        # 获取本节点的抵消分录
        elim_debit = ZERO
        elim_credit = ZERO
        node_entries = elim_map.get(node.company_code, [])
        for entry in node_entries:
            if entry.account_code == acct_code:
                elim_debit += entry.debit_amount or ZERO
                elim_credit += entry.credit_amount or ZERO

        # 计算 net_difference 和 consolidated_amount
        # 获取已有的 adjustment 值（如果有）
        existing = await _get_worksheet_row(db, project_id, node.company_code, acct_code, year)
        adj_debit = existing.adjustment_debit if existing else ZERO
        adj_credit = existing.adjustment_credit if existing else ZERO

        net_diff = (adj_debit - adj_credit) + (elim_debit - elim_credit)
        consolidated = children_sum + net_diff

        # Upsert worksheet row
        await _upsert_worksheet(
            db, project_id, node.company_code, acct_code, year,
            adjustment_debit=adj_debit,
            adjustment_credit=adj_credit,
            elimination_debit=elim_debit,
            elimination_credit=elim_credit,
            net_difference=net_diff,
            children_amount_sum=children_sum,
            consolidated_amount=consolidated,
        )


async def _get_audited_amount(
    db: AsyncSession, project_id: UUID, year: int, account_code: str
) -> Decimal:
    """从 trial_balance 获取叶子节点的审定数"""
    result = await db.execute(
        sa.select(TrialBalance.audited_amount).where(
            TrialBalance.project_id == project_id,
            TrialBalance.year == year,
            TrialBalance.standard_account_code == account_code,
            TrialBalance.is_deleted == sa.false(),
        )
    )
    row = result.scalar_one_or_none()
    return Decimal(str(row)) if row is not None else ZERO


async def _get_worksheet_row(
    db: AsyncSession, project_id: UUID, company_code: str, account_code: str, year: int
) -> ConsolWorksheet | None:
    """获取差额表中的一行"""
    result = await db.execute(
        sa.select(ConsolWorksheet).where(
            ConsolWorksheet.project_id == project_id,
            ConsolWorksheet.node_company_code == company_code,
            ConsolWorksheet.account_code == account_code,
            ConsolWorksheet.year == year,
            ConsolWorksheet.is_deleted == sa.false(),
        )
    )
    return result.scalar_one_or_none()


async def _upsert_worksheet(
    db: AsyncSession,
    project_id: UUID,
    company_code: str,
    account_code: str,
    year: int,
    **values: Decimal,
) -> None:
    """插入或更新差额表行"""
    existing = await _get_worksheet_row(db, project_id, company_code, account_code, year)
    if existing:
        for k, v in values.items():
            setattr(existing, k, v)
    else:
        ws = ConsolWorksheet(
            id=uuid.uuid4(),
            project_id=project_id,
            node_company_code=company_code,
            account_code=account_code,
            year=year,
            **values,
        )
        db.add(ws)
