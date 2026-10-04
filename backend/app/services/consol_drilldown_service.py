"""合并穿透查询服务

三层穿透：
1. drill_to_companies: 节点合并数 → 各直接子节点构成
2. drill_to_eliminations: 节点 → 相关分录明细
3. drill_to_trial_balance: 跳转到末端企业试算表

节点参数（spec consol-tree-three-code-autobuild 任务 7.5）：传 ``node_key``（``{企业代码}:{角色}``）精确定位，
传纯企业代码时取该代码首个节点（兼容旧调用方）。差额表行按 ``node_key`` 匹配；分录归属与金额计算
同一函数（``consol_calc_basis.attribute_entry``），``related_company_codes`` 只用于留痕筛选。
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consolidation_models import ConsolWorksheet, EliminationEntry, ReviewStatusEnum
from app.services.consol_calc_basis import (
    EntryDataError,
    attribute_entry,
    data_leaves,
    entry_record,
    index_tree,
    load_tree_entries,
)
from app.services.consol_group_tree import KIND_AGGREGATE, KIND_ELIM
from app.services.consol_tree_service import (
    TreeNode,
    build_tree,
    find_node,
    iter_nodes,
    worksheet_key,
)


ZERO = Decimal("0")


def _node_info(node: TreeNode) -> dict:
    return {
        "company_code": node.company_code,
        "company_name": node.company_name,
        "node_key": worksheet_key(node),
        "role": node.role,
        "kind": node.kind,
        "display_name": node.display_name or node.company_name,
    }


async def drill_to_companies(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    node_company_code: str,
    account_code: str | None = None,
) -> list[dict]:
    """给定一个节点，返回每个直接子节点对合并数的贡献（子节点按树序，科目按编码）。"""
    tree = await build_tree(db, project_id)
    if not tree:
        return []

    target = find_node(tree, node_company_code)
    if not target or not target.children:
        return []

    children = {worksheet_key(c): c for c in target.children}
    order = {key: i for i, key in enumerate(children)}
    query = sa.select(ConsolWorksheet).where(
        ConsolWorksheet.project_id == project_id,
        ConsolWorksheet.node_company_code.in_(list(children)),
        ConsolWorksheet.year == year,
        ConsolWorksheet.is_deleted == sa.false(),
    )
    if account_code:
        query = query.where(ConsolWorksheet.account_code == account_code)
    rows = (await db.execute(query)).scalars().all()

    return [
        {
            **_node_info(children[ws.node_company_code]),
            "account_code": ws.account_code,
            "consolidated_amount": str(ws.consolidated_amount),
            "children_amount_sum": str(ws.children_amount_sum),
            "net_difference": str(ws.net_difference),
        }
        for ws in sorted(rows, key=lambda w: (order[w.node_company_code], w.account_code))
    ]


def _entry_touches_account(entry: EliminationEntry, account_code: str) -> bool:
    lines = entry.lines if isinstance(entry.lines, list) else []
    if any(isinstance(ln, dict) and str(ln.get("account_code") or "") == account_code for ln in lines):
        return True
    return not lines and entry.account_code == account_code


def _related_codes(entry: EliminationEntry) -> list[str]:
    codes = entry.related_company_codes
    if isinstance(codes, list):
        return [str(c) for c in codes if c]
    if isinstance(codes, dict):
        return [v for v in codes.values() if isinstance(v, str)]
    return []


async def drill_to_eliminations(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    company_code: str,
    account_code: str | None = None,
) -> list[dict]:
    """给定一个节点，返回相关分录明细（本树全部合并项目的未删分录，含各审批状态）。

    - 差额节点：归属于它的分录（与金额计算同一归属函数）；
    - 汇总节点：子树内各差额节点的归属分录（即构成该节点合并数的全部分录）；
    - 数据节点 / 树外企业：``related_company_codes`` 含该企业的分录（留痕筛选，不代表金额归属）。
    ``account_code`` 按明细行筛选（旧数据没有明细行时看表头科目）。
    """
    tree = await build_tree(db, project_id)
    if tree is None:
        return []
    target = find_node(tree, company_code)
    index = index_tree(tree)
    entries = await load_tree_entries(db, tree, year, approved_only=False)

    attributed: dict[UUID, tuple[str | None, str | None]] = {}
    for e in entries:
        try:
            attributed[e.id] = attribute_entry(entry_record(e), index)
        except EntryDataError as err:
            attributed[e.id] = (None, f"明细行无法识别：{err}")

    if target is not None and target.kind in (KIND_ELIM, KIND_AGGREGATE):
        scope = {worksheet_key(n) for n in iter_nodes(target) if n.kind == KIND_ELIM}
        selected = [e for e in entries if attributed[e.id][0] in scope]
    else:
        code = target.company_code if target is not None else company_code
        selected = [e for e in entries if code in _related_codes(e)]
    if account_code:
        selected = [e for e in selected if _entry_touches_account(e, account_code)]

    return [
        {
            "entry_id": str(e.id),
            "entry_no": e.entry_no,
            "entry_type": getattr(e.entry_type, "value", e.entry_type),
            "description": e.description,
            "account_code": e.account_code,
            "account_name": e.account_name,
            "debit_amount": str(e.debit_amount or ZERO),
            "credit_amount": str(e.credit_amount or ZERO),
            "lines": e.lines if isinstance(e.lines, list) else [],
            "related_company_codes": e.related_company_codes,
            "branch_entity_code": e.branch_entity_code,
            "review_status": getattr(e.review_status, "value", e.review_status),
            "counted": e.review_status == ReviewStatusEnum.approved and attributed[e.id][0] is not None,
            "node_key": attributed[e.id][0],
            "orphan_reason": attributed[e.id][1],
            "host_project_id": str(e.project_id),
        }
        for e in selected
    ]


def _trial_balance_node(tree: TreeNode, ref: str) -> TreeNode | None:
    """穿透到试算表的节点：node_key 精确定位；纯企业代码取该企业首个有单体项目的数据节点。"""
    if ":" in ref:
        return find_node(tree, ref)
    for n in iter_nodes(tree):
        if n.company_code == ref and n.kind == "data" and n.project_id is not None:
            return n
    return find_node(tree, ref)


async def drill_to_trial_balance(
    db: AsyncSession,
    project_id: UUID,
    company_code: str,
) -> dict:
    """返回跳转到末端企业（数据节点）试算表的 URL 信息；差额与汇总节点没有自己的试算表。"""
    tree = await build_tree(db, project_id)
    if not tree:
        return {"drill_url": None, "message": "未找到企业树"}

    target = _trial_balance_node(tree, company_code)
    if not target:
        return {"drill_url": None, "message": f"未找到企业 {company_code}"}

    info = _node_info(target)
    if target.kind == KIND_ELIM:
        return {**info, "drill_url": None, "message": f"「{info['display_name']}」是差额节点，金额来自分录，请查看差额分录"}
    if target.kind != "data" or target.project_id is None:
        leaves = [n for n in data_leaves(target) if n.project_id is not None]
        hint = "、".join((n.display_name or n.company_name) for n in leaves[:5])
        message = f"「{info['display_name']}」是汇总节点，没有单一试算表" + (f"，可穿透到：{hint}" if hint else "")
        if target.kind == "data":
            message = f"「{info['display_name']}」没有本年度单户项目，金额按 0 计"
        return {**info, "drill_url": None, "message": message}
    return {
        **info,
        "drill_url": f"/projects/{target.project_id}/trial-balance",
        "project_id": str(target.project_id),
    }
