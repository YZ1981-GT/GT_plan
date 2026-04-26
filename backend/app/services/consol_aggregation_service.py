"""节点汇总查询服务

三种汇总模式：
- self: 单节点差额表
- children: 当前节点 + 直接子节点
- descendants: 当前节点 + 所有后代节点
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consolidation_models import ConsolWorksheet
from app.services.consol_tree_service import TreeNode, build_tree, find_node, get_descendants


ZERO = Decimal("0")


async def query_node(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    node_company_code: str,
    mode: str = "self",
) -> list[dict]:
    """按模式查询节点汇总数据。

    mode: self | children | descendants
    Returns list of {account_code, children_amount_sum, net_difference, consolidated_amount, ...}
    """
    tree = await build_tree(db, project_id)
    if not tree:
        return []

    target = find_node(tree, node_company_code)
    if not target:
        return []

    if mode == "self":
        return await _query_self(db, project_id, year, target)
    elif mode == "children":
        return await _query_children(db, project_id, year, target)
    elif mode == "descendants":
        return await _query_descendants(db, project_id, year, target)
    else:
        return await _query_self(db, project_id, year, target)


async def _query_self(
    db: AsyncSession, project_id: UUID, year: int, node: TreeNode
) -> list[dict]:
    """返回单节点差额表"""
    result = await db.execute(
        sa.select(ConsolWorksheet).where(
            ConsolWorksheet.project_id == project_id,
            ConsolWorksheet.node_company_code == node.company_code,
            ConsolWorksheet.year == year,
            ConsolWorksheet.is_deleted == sa.false(),
        ).order_by(ConsolWorksheet.account_code)
    )
    rows = result.scalars().all()
    return [_ws_to_dict(r) for r in rows]


async def _query_children(
    db: AsyncSession, project_id: UUID, year: int, node: TreeNode
) -> list[dict]:
    """当前节点 + 直接子节点汇总"""
    codes = [node.company_code] + [c.company_code for c in node.children]
    return await _aggregate_codes(db, project_id, year, codes)


async def _query_descendants(
    db: AsyncSession, project_id: UUID, year: int, node: TreeNode
) -> list[dict]:
    """当前节点 + 所有后代节点汇总"""
    all_nodes = [node] + get_descendants(node)
    codes = [n.company_code for n in all_nodes]
    return await _aggregate_codes(db, project_id, year, codes)


async def _aggregate_codes(
    db: AsyncSession, project_id: UUID, year: int, codes: list[str]
) -> list[dict]:
    """按科目汇总多个节点的差额表数据"""
    result = await db.execute(
        sa.select(
            ConsolWorksheet.account_code,
            sa.func.sum(ConsolWorksheet.children_amount_sum).label("children_amount_sum"),
            sa.func.sum(ConsolWorksheet.adjustment_debit).label("adjustment_debit"),
            sa.func.sum(ConsolWorksheet.adjustment_credit).label("adjustment_credit"),
            sa.func.sum(ConsolWorksheet.elimination_debit).label("elimination_debit"),
            sa.func.sum(ConsolWorksheet.elimination_credit).label("elimination_credit"),
            sa.func.sum(ConsolWorksheet.net_difference).label("net_difference"),
            sa.func.sum(ConsolWorksheet.consolidated_amount).label("consolidated_amount"),
        ).where(
            ConsolWorksheet.project_id == project_id,
            ConsolWorksheet.node_company_code.in_(codes),
            ConsolWorksheet.year == year,
            ConsolWorksheet.is_deleted == sa.false(),
        ).group_by(ConsolWorksheet.account_code)
        .order_by(ConsolWorksheet.account_code)
    )
    rows = result.all()
    return [
        {
            "account_code": r.account_code,
            "children_amount_sum": str(r.children_amount_sum or ZERO),
            "adjustment_debit": str(r.adjustment_debit or ZERO),
            "adjustment_credit": str(r.adjustment_credit or ZERO),
            "elimination_debit": str(r.elimination_debit or ZERO),
            "elimination_credit": str(r.elimination_credit or ZERO),
            "net_difference": str(r.net_difference or ZERO),
            "consolidated_amount": str(r.consolidated_amount or ZERO),
        }
        for r in rows
    ]


def _ws_to_dict(ws: ConsolWorksheet) -> dict:
    """ConsolWorksheet → dict"""
    return {
        "id": str(ws.id),
        "node_company_code": ws.node_company_code,
        "account_code": ws.account_code,
        "year": ws.year,
        "children_amount_sum": str(ws.children_amount_sum),
        "adjustment_debit": str(ws.adjustment_debit),
        "adjustment_credit": str(ws.adjustment_credit),
        "elimination_debit": str(ws.elimination_debit),
        "elimination_credit": str(ws.elimination_credit),
        "net_difference": str(ws.net_difference),
        "consolidated_amount": str(ws.consolidated_amount),
    }
