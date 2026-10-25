"""节点汇总查询服务

三种汇总模式：
- self: 单节点差额表
- children: 当前节点 + 直接子节点
- descendants: 当前节点 + 所有后代节点

节点参数（spec consol-tree-three-code-autobuild 任务 7.5）：传 ``node_key``（``{企业代码}:{角色}``）
精确定位；传纯企业代码时取该代码首个节点（兼容旧调用方）。差额表行按 ``node_key`` 匹配。
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consolidation_models import ConsolWorksheet
from app.services.consol_tree_service import (
    TreeNode,
    build_tree,
    find_node,
    get_descendants,
    worksheet_key,
)


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

    if mode == "children":
        return await _query_children(db, project_id, year, target)
    if mode == "descendants":
        return await _query_descendants(db, project_id, year, target)
    return await _query_self(db, project_id, year, target)


async def _query_self(
    db: AsyncSession, project_id: UUID, year: int, node: TreeNode
) -> list[dict]:
    """返回单节点差额表"""
    result = await db.execute(
        sa.select(ConsolWorksheet).where(
            ConsolWorksheet.project_id == project_id,
            ConsolWorksheet.node_company_code == worksheet_key(node),
            ConsolWorksheet.year == year,
            ConsolWorksheet.is_deleted == sa.false(),
        ).order_by(ConsolWorksheet.account_code)
    )
    rows = result.scalars().all()
    return [_ws_to_dict(r, node) for r in rows]


async def _query_children(
    db: AsyncSession, project_id: UUID, year: int, node: TreeNode
) -> list[dict]:
    """当前节点 + 直接子节点汇总"""
    keys = [worksheet_key(node)] + [worksheet_key(c) for c in node.children]
    return await _aggregate_keys(db, project_id, year, keys)


async def _query_descendants(
    db: AsyncSession, project_id: UUID, year: int, node: TreeNode
) -> list[dict]:
    """当前节点 + 所有后代节点汇总"""
    keys = [worksheet_key(n) for n in [node] + get_descendants(node)]
    return await _aggregate_keys(db, project_id, year, keys)


async def _aggregate_keys(
    db: AsyncSession, project_id: UUID, year: int, keys: list[str]
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
            ConsolWorksheet.node_company_code.in_(keys),
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


def _ws_to_dict(ws: ConsolWorksheet, node: TreeNode | None = None) -> dict:
    """ConsolWorksheet → dict（带节点展示信息）"""
    return {
        "id": str(ws.id),
        "node_company_code": ws.node_company_code,
        "node_key": ws.node_company_code,
        "display_name": (node.display_name or node.company_name) if node is not None else None,
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
