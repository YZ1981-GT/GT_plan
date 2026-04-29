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
    """全量重算差额表（后序遍历，批量查询优化）。

    优化：预加载所有 trial_balance 和 worksheet 数据到内存，
    避免 N×M 次单行查询（N=节点数, M=科目数）。

    Returns summary dict with node_count and account_count.
    """
    tree = await build_tree(db, project_id)
    if not tree:
        return {"node_count": 0, "account_count": 0}

    all_nodes = [tree] + get_descendants(tree)
    all_project_ids = [n.project_id for n in all_nodes]

    # 批量预加载所有数据
    account_codes = await _collect_account_codes(db, project_id, year, tree)
    if not account_codes:
        return {"node_count": len(all_nodes), "account_count": 0}

    # 预加载所有 trial_balance 审定数 → {(project_id, account_code): Decimal}
    tb_map = await _batch_load_audited(db, all_project_ids, year)

    # 预加载所有已有 worksheet → {(company_code, account_code): ConsolWorksheet}
    ws_map = await _batch_load_worksheet(db, project_id, year)

    # 预加载抵消分录 → {(company_code, account_code): (debit_sum, credit_sum)}
    elim_map = await _batch_load_eliminations(db, project_id, year)

    # 后序遍历计算（纯内存，无 DB 查询）
    results: list[dict] = []
    _calc_node_batch(tree, account_codes, tb_map, ws_map, elim_map, results)

    # 批量写入结果
    await _batch_upsert_worksheet(db, project_id, year, results, ws_map)
    await db.commit()

    return {"node_count": len(all_nodes), "account_count": len(account_codes)}


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


# ---------------------------------------------------------------------------
# 批量加载函数（优化版，替代逐行查询）
# ---------------------------------------------------------------------------

async def _batch_load_audited(
    db: AsyncSession, project_ids: list[UUID], year: int
) -> dict[tuple[UUID, str], Decimal]:
    """批量加载所有项目的 trial_balance 审定数。

    Returns: {(project_id, account_code): audited_amount}
    """
    result = await db.execute(
        sa.select(
            TrialBalance.project_id,
            TrialBalance.standard_account_code,
            TrialBalance.audited_amount,
        ).where(
            TrialBalance.project_id.in_(project_ids),
            TrialBalance.year == year,
            TrialBalance.is_deleted == sa.false(),
        )
    )
    tb_map: dict[tuple[UUID, str], Decimal] = {}
    for row in result.all():
        pid, code, amount = row
        tb_map[(pid, code)] = Decimal(str(amount)) if amount is not None else ZERO
    return tb_map


async def _batch_load_worksheet(
    db: AsyncSession, project_id: UUID, year: int
) -> dict[tuple[str, str], ConsolWorksheet]:
    """批量加载已有差额表。

    Returns: {(company_code, account_code): ConsolWorksheet}
    """
    result = await db.execute(
        sa.select(ConsolWorksheet).where(
            ConsolWorksheet.project_id == project_id,
            ConsolWorksheet.year == year,
            ConsolWorksheet.is_deleted == sa.false(),
        )
    )
    ws_map: dict[tuple[str, str], ConsolWorksheet] = {}
    for ws in result.scalars().all():
        ws_map[(ws.node_company_code, ws.account_code)] = ws
    return ws_map


async def _batch_load_eliminations(
    db: AsyncSession, project_id: UUID, year: int
) -> dict[tuple[str, str], tuple[Decimal, Decimal]]:
    """批量加载抵消分录，按 (company_code, account_code) 汇总借贷。

    Returns: {(company_code, account_code): (debit_sum, credit_sum)}
    """
    result = await db.execute(
        sa.select(EliminationEntry).where(
            EliminationEntry.project_id == project_id,
            EliminationEntry.year == year,
            EliminationEntry.is_deleted == sa.false(),
        )
    )
    entries = result.scalars().all()

    elim_map: dict[tuple[str, str], tuple[Decimal, Decimal]] = {}
    for entry in entries:
        codes = entry.related_company_codes
        company_codes: list[str] = []
        if isinstance(codes, list):
            company_codes = codes
        elif isinstance(codes, dict):
            company_codes = [v for v in codes.values() if isinstance(v, str)]

        for cc in company_codes:
            key = (cc, entry.account_code)
            existing = elim_map.get(key, (ZERO, ZERO))
            elim_map[key] = (
                existing[0] + (entry.debit_amount or ZERO),
                existing[1] + (entry.credit_amount or ZERO),
            )

    return elim_map


def _calc_node_batch(
    node: TreeNode,
    account_codes: set[str],
    tb_map: dict[tuple[UUID, str], Decimal],
    ws_map: dict[tuple[str, str], ConsolWorksheet],
    elim_map: dict[tuple[str, str], tuple[Decimal, Decimal]],
    results: list[dict],
) -> dict[str, Decimal]:
    """纯内存后序遍历计算（无 DB 查询）。

    Returns: {account_code: consolidated_amount} 供父节点汇总使用。
    """
    is_leaf = len(node.children) == 0

    # 先递归计算子节点
    child_consolidated: dict[str, dict[str, Decimal]] = {}
    for child in node.children:
        child_consolidated[child.company_code] = _calc_node_batch(
            child, account_codes, tb_map, ws_map, elim_map, results
        )

    node_amounts: dict[str, Decimal] = {}

    for acct_code in account_codes:
        if is_leaf:
            children_sum = tb_map.get((node.project_id, acct_code), ZERO)
        else:
            children_sum = ZERO
            for child in node.children:
                child_amounts = child_consolidated.get(child.company_code, {})
                children_sum += child_amounts.get(acct_code, ZERO)

        # 抵消分录
        elim_debit, elim_credit = elim_map.get((node.company_code, acct_code), (ZERO, ZERO))

        # 已有调整值
        existing = ws_map.get((node.company_code, acct_code))
        adj_debit = existing.adjustment_debit if existing else ZERO
        adj_credit = existing.adjustment_credit if existing else ZERO

        net_diff = (adj_debit - adj_credit) + (elim_debit - elim_credit)
        consolidated = children_sum + net_diff

        node_amounts[acct_code] = consolidated

        results.append({
            "company_code": node.company_code,
            "account_code": acct_code,
            "adjustment_debit": adj_debit,
            "adjustment_credit": adj_credit,
            "elimination_debit": elim_debit,
            "elimination_credit": elim_credit,
            "net_difference": net_diff,
            "children_amount_sum": children_sum,
            "consolidated_amount": consolidated,
        })

    return node_amounts


async def _batch_upsert_worksheet(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    results: list[dict],
    ws_map: dict[tuple[str, str], ConsolWorksheet],
) -> None:
    """批量写入差额表结果"""
    for row in results:
        key = (row["company_code"], row["account_code"])
        existing = ws_map.get(key)
        if existing:
            existing.adjustment_debit = row["adjustment_debit"]
            existing.adjustment_credit = row["adjustment_credit"]
            existing.elimination_debit = row["elimination_debit"]
            existing.elimination_credit = row["elimination_credit"]
            existing.net_difference = row["net_difference"]
            existing.children_amount_sum = row["children_amount_sum"]
            existing.consolidated_amount = row["consolidated_amount"]
        else:
            ws = ConsolWorksheet(
                id=uuid.uuid4(),
                project_id=project_id,
                node_company_code=row["company_code"],
                account_code=row["account_code"],
                year=year,
                adjustment_debit=row["adjustment_debit"],
                adjustment_credit=row["adjustment_credit"],
                elimination_debit=row["elimination_debit"],
                elimination_credit=row["elimination_credit"],
                net_difference=row["net_difference"],
                children_amount_sum=row["children_amount_sum"],
                consolidated_amount=row["consolidated_amount"],
            )
            db.add(ws)


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
