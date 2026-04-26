"""合并穿透查询服务

三层穿透：
1. drill_to_companies: 合并数 → 各企业构成
2. drill_to_eliminations: 企业 → 相关抵消分录明细
3. drill_to_trial_balance: 跳转到末端企业试算表
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consolidation_models import ConsolWorksheet, EliminationEntry
from app.services.consol_tree_service import TreeNode, build_tree, find_node


ZERO = Decimal("0")


async def drill_to_companies(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    node_company_code: str,
    account_code: str | None = None,
) -> list[dict]:
    """给定一个节点，返回每个直接子企业对合并数的贡献。"""
    tree = await build_tree(db, project_id)
    if not tree:
        return []

    target = find_node(tree, node_company_code)
    if not target:
        return []

    result_list = []
    for child in target.children:
        query = sa.select(ConsolWorksheet).where(
            ConsolWorksheet.project_id == project_id,
            ConsolWorksheet.node_company_code == child.company_code,
            ConsolWorksheet.year == year,
            ConsolWorksheet.is_deleted == sa.false(),
        )
        if account_code:
            query = query.where(ConsolWorksheet.account_code == account_code)

        result = await db.execute(query.order_by(ConsolWorksheet.account_code))
        rows = result.scalars().all()

        for ws in rows:
            result_list.append({
                "company_code": child.company_code,
                "company_name": child.company_name,
                "account_code": ws.account_code,
                "consolidated_amount": str(ws.consolidated_amount),
                "children_amount_sum": str(ws.children_amount_sum),
                "net_difference": str(ws.net_difference),
            })

    return result_list


async def drill_to_eliminations(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    company_code: str,
    account_code: str | None = None,
) -> list[dict]:
    """给定一个企业，返回相关抵消分录明细。"""
    query = sa.select(EliminationEntry).where(
        EliminationEntry.project_id == project_id,
        EliminationEntry.year == year,
        EliminationEntry.is_deleted == sa.false(),
    )
    if account_code:
        query = query.where(EliminationEntry.account_code == account_code)

    result = await db.execute(query.order_by(EliminationEntry.entry_no))
    entries = result.scalars().all()

    # 过滤与 company_code 相关的分录
    filtered = []
    for entry in entries:
        codes = entry.related_company_codes
        is_related = False
        if isinstance(codes, list) and company_code in codes:
            is_related = True
        elif isinstance(codes, dict) and company_code in codes.values():
            is_related = True
        if is_related:
            filtered.append({
                "entry_id": str(entry.id),
                "entry_no": entry.entry_no,
                "entry_type": entry.entry_type.value if entry.entry_type else None,
                "description": entry.description,
                "account_code": entry.account_code,
                "account_name": entry.account_name,
                "debit_amount": str(entry.debit_amount or ZERO),
                "credit_amount": str(entry.credit_amount or ZERO),
                "related_company_codes": codes,
            })

    return filtered


async def drill_to_trial_balance(
    db: AsyncSession,
    project_id: UUID,
    company_code: str,
) -> dict:
    """返回跳转到末端企业试算表的 URL 信息。"""
    # 找到该 company_code 对应的子项目
    tree = await build_tree(db, project_id)
    if not tree:
        return {"drill_url": None, "message": "未找到企业树"}

    target = find_node(tree, company_code)
    if not target:
        return {"drill_url": None, "message": f"未找到企业 {company_code}"}

    return {
        "drill_url": f"/projects/{target.project_id}/trial-balance",
        "project_id": str(target.project_id),
        "company_code": company_code,
        "company_name": target.company_name,
    }
