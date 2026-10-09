"""有分公司时的母公司汇总金额（报表母公司列 / 附注母公司章共用）。

审定数唯一来源：``load_calc_basis`` + ``node_measures[parent][consolidated]``，因此包含
本部、全部分公司以及已审批母分差额；未审数/期初数只汇总 parent 子树的数据叶子，
绝不叠加母分差额。报表与附注不得各写一套求和。
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TrialBalance
from app.services.consol_calc_basis import (
    MEASURE_CONSOLIDATED,
    data_leaves,
    load_calc_basis,
    node_measures,
)
from app.services.parent_company_scope import ParentCompanyContext

ZERO = Decimal("0")


@dataclass(frozen=True)
class ParentCompanyValues:
    parent_node_key: str
    audited: dict[str, Decimal]
    unadjusted: dict[str, Decimal]
    opening: dict[str, Decimal]
    names: dict[str, str]
    categories: dict[str, Any]


def _amount(value: Any) -> Decimal:
    return ZERO if value is None else Decimal(str(value))


async def load_parent_company_values(
    db: AsyncSession,
    consolidated_project_id: UUID,
    year: int,
    context: ParentCompanyContext,
) -> ParentCompanyValues:
    """装载有直属分公司的母公司三列科目值。

    ``context`` 必须来自 ``resolve_parent_company_context``，避免按 company_code 猜节点。
    调用方只在 ``has_branches`` 时进入；误用立即抛错，不静默回落到集团根节点。
    """
    if not context.has_branches or context.tree is None or context.parent_node is None or not context.parent_node_key:
        raise ValueError("母公司没有可汇总的分公司节点")

    basis = await load_calc_basis(db, consolidated_project_id, year, tree=context.tree)
    if basis is None:
        raise LookupError("无法装载母公司汇总计算口径")
    audited = dict(node_measures(basis)[context.parent_node_key][MEASURE_CONSOLIDATED])

    leaf_ids = sorted(
        {node.project_id for node in data_leaves(context.parent_node) if node.project_id is not None},
        key=str,
    )
    unadjusted: dict[str, Decimal] = {}
    opening: dict[str, Decimal] = {}
    names = dict(basis.names)
    categories = dict(basis.categories)
    if leaf_ids:
        rows = (await db.execute(
            sa.select(
                TrialBalance.standard_account_code,
                TrialBalance.account_name,
                TrialBalance.account_category,
                TrialBalance.unadjusted_amount,
                TrialBalance.opening_balance,
            ).where(
                TrialBalance.project_id.in_(leaf_ids),
                TrialBalance.year == year,
                TrialBalance.is_deleted == sa.false(),
            )
        )).all()
        for code, name, category, unadj, opn in rows:
            key = (code or "").strip()
            if not key:
                continue
            unadjusted[key] = unadjusted.get(key, ZERO) + _amount(unadj)
            opening[key] = opening.get(key, ZERO) + _amount(opn)
            if name and key not in names:
                names[key] = name
            if category is not None and key not in categories:
                categories[key] = category

    return ParentCompanyValues(
        parent_node_key=context.parent_node_key,
        audited=audited,
        unadjusted=unadjusted,
        opening=opening,
        names=names,
        categories=categories,
    )


__all__ = ["ParentCompanyValues", "load_parent_company_values"]
