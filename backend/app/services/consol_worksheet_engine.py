"""合并差额表计算引擎（spec consol-tree-three-code-autobuild 任务 7.2）。

``consol_worksheet.node_company_code`` 存节点键 ``node_key``（``{企业代码}:{角色}``，ADR-CTREE-002），
每个企业树节点 × 科目一行。三类节点（design §5.1）：

- data：``children_amount_sum`` = 单体项目审定数，差额列 0，``consolidated_amount`` = 审定数；
- elim：借贷列 = 归属本节点的已审批分录明细行按录入方向的合计（「其他调整」进调整列，其余进抵销列），
  ``net_difference`` = ``consolidated_amount`` = Σ ``sign(a)·(借−贷)``；
- aggregate：``children_amount_sum`` = ``consolidated_amount`` = Σ 直接子节点合并数，自身差额列恒 0（P7）。

取数、分录归属与科目方向全部来自 ``consol_calc_basis``（与合并试算同一函数，P8）；
``related_company_codes`` 不参与金额（ADR-CTREE-003）。

全量重算：本次结果之外的旧行（旧的纯企业代码键、已消失的节点或科目）软删（需求 5.8）；
同键的软删行复活而不是新插 —— SQLite 忽略唯一索引的 ``postgresql_where``，新插会撞键。
本函数自行提交（级联刷新与抵销审批重算依赖此语义）。
"""

from __future__ import annotations

import uuid
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consolidation_models import ConsolWorksheet
from app.schemas.consol_context import ConsolContext
from app.services.consol_calc_basis import NodeAmounts, load_calc_basis, worksheet_rows
from app.services.consol_context_service import validate_context
from app.services.consol_tree_service import TreeNode, build_tree, iter_nodes

# consol_worksheet.node_company_code 列宽（V034）
NODE_KEY_MAX_LEN = 50


async def recalc_full(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    *,
    context: ConsolContext | None = None,
    tree: TreeNode | None = None,
) -> dict:
    """全量重算差额表并提交。

    ``tree`` 与 ``context`` 由级联 / push 编排器成对透传；旧调用不传时仍在本入口建树。

    Returns: ``node_count`` / ``account_count`` / ``rows_written`` / ``rows_removed`` /
    ``orphan_entries``（未归属分录清单，两条路径都不计入，需求 6.4）。
    """
    resolved_tree = tree if tree is not None else await build_tree(db, project_id)
    validate_context(context, project_id, year, tree=resolved_tree)
    if resolved_tree is None:
        return {"node_count": 0, "account_count": 0, "rows_written": 0, "rows_removed": 0, "orphan_entries": []}
    basis = await load_calc_basis(db, project_id, year, tree=resolved_tree)
    assert basis is not None
    rows = worksheet_rows(basis)
    written, removed = await _write_rows(db, project_id, year, rows)
    await db.commit()
    return {
        "node_count": sum(1 for _ in iter_nodes(resolved_tree)),
        "account_count": len(basis.accounts),
        "rows_written": written,
        "rows_removed": removed,
        "orphan_entries": [o.to_dict() for o in basis.orphans],
    }


def _apply(ws: ConsolWorksheet, amounts: NodeAmounts) -> bool:
    """把 7 个金额列写到行上；返回是否有变化（未变的列不置脏）。"""
    changed = False
    for column, value in amounts.columns().items():
        if getattr(ws, column) != value:
            setattr(ws, column, value)
            changed = True
    return changed


async def _write_rows(
    db: AsyncSession, project_id: UUID, year: int, rows: list[tuple[str, str, NodeAmounts]],
) -> tuple[int, int]:
    """按 (node_key, 科目) 写入：已有行更新、软删行复活、没有才新插；结果之外的旧行软删。"""
    too_long = sorted({key for key, _a, _v in rows if len(key) > NODE_KEY_MAX_LEN})
    if too_long:
        raise ValueError(
            f"企业代码过长，节点键超过 {NODE_KEY_MAX_LEN} 个字符，无法写入差额表：{', '.join(too_long[:5])}"
        )
    existing = (await db.execute(
        sa.select(ConsolWorksheet).where(
            ConsolWorksheet.project_id == project_id,
            ConsolWorksheet.year == year,
        )
    )).scalars().all()
    active: dict[tuple[str, str], ConsolWorksheet] = {}
    deleted: dict[tuple[str, str], ConsolWorksheet] = {}
    duplicates: list[ConsolWorksheet] = []
    for ws in sorted(existing, key=lambda w: str(w.id)):
        key = (ws.node_company_code, ws.account_code)
        if ws.is_deleted:
            deleted.setdefault(key, ws)
        elif key in active:
            duplicates.append(ws)
        else:
            active[key] = ws

    wanted: set[tuple[str, str]] = set()
    written = 0
    for node_key, account, amounts in rows:
        key = (node_key, account)
        wanted.add(key)
        ws = active.get(key)
        revived = False
        if ws is None and key in deleted:
            ws = deleted[key]
            ws.is_deleted = False
            ws.deleted_at = None
            revived = True
        if ws is None:
            ws = ConsolWorksheet(
                id=uuid.uuid4(), project_id=project_id, node_company_code=node_key,
                account_code=account, year=year,
            )
            db.add(ws)
            revived = True
        if _apply(ws, amounts) or revived:
            written += 1

    removed = 0
    for key, ws in active.items():
        if key not in wanted:
            ws.soft_delete()
            removed += 1
    for ws in duplicates:
        ws.soft_delete()
        removed += 1
    await db.flush()
    return written, removed
