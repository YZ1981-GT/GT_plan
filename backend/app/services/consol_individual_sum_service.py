"""合并模块 B1：个别数自动汇总（consol-phase0-core-pipeline；spec consol-tree-three-code-autobuild 任务 7.3 改口径）。

职责：把企业树**全部数据叶子**（子公司、分公司、本部、无分公司的母公司）的
``trial_balance.audited_amount`` 按 ``standard_account_code`` 加总写入 ``consol_trial.individual_sum``，
同时写 ``consolidation_breakdown`` 溯源（每行标注来自哪个节点，需求 5.9）。

口径变更（任务 7.3，有意）：旧实现取「没有子节点的节点」，三码树里差额节点也没有子节点、
而多级合并的中间企业本体不是叶子（F5）；现改取 ``kind == data`` 的叶子，母公司本体与各级本部都计入。

取数口径铁律：审定数、科目集合、科目名全部来自 ``consol_calc_basis``（与差额表引擎同一函数），
否则 B2（差额表 ↔ 合并试算对账）必然失败。全程 Decimal；溯源金额以 ``str(Decimal)`` 序列化（P7）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.consol_calc_basis import (
    CalcBasis,
    aggregate_leaf_amounts,
    data_leaves,
    load_calc_basis,
    trial_amounts,
)
from app.services.consol_tree_service import TreeNode

ZERO = Decimal("0")


@dataclass
class AggregationResult:
    """B1 汇总统计结果。"""

    project_id: UUID
    year: int
    accounts_aggregated: int        # 写入 individual_sum 的科目数（= 本树科目集合）
    companies_traversed: int        # 遍历的数据叶子节点数（含没有单体项目、按 0 计的叶子）
    total_individual_sum: Decimal   # 全表 individual_sum 合计（debug 用）


# ---------------------------------------------------------------------------
# 纯函数（PBT 直接喂内存字典；实现委托 consol_calc_basis，保证与差额表同源）
# ---------------------------------------------------------------------------


def _collect_leaves(root: TreeNode) -> list[TreeNode]:
    """数据叶子（``kind == data`` 且无子节点）。差额节点虽无子节点但不是数据叶子。"""
    return data_leaves(root)


def _aggregate_from_company_amounts(
    company_amounts: list[tuple[dict, dict[str, Decimal]]],
) -> tuple[dict[str, Decimal], dict[str, list[dict]]]:
    """纯汇总：跨数据叶子按科目加总 + 构建溯源（金额 0 不写溯源行，P2；无 float 中转，P7）。"""
    return aggregate_leaf_amounts(company_amounts)


# ---------------------------------------------------------------------------
# 编排：装载口径 → 写回 consol_trial
# ---------------------------------------------------------------------------


async def aggregate_individual_sum(
    db: AsyncSession, project_id: UUID, year: int, *, basis: CalcBasis | None = None,
) -> AggregationResult:
    """把全部数据叶子的审定数按科目加总写入 ``individual_sum`` 并写溯源。

    科目集合 = 数据叶子试算表科目 ∪ 已归属分录明细行科目（需求 5.6，没有的行自动建）；
    本次集合之外的已有行个别数清零（溯源置空），避免科目消失后残留旧数。
    责任边界：不修改 ``consol_adjustment`` / ``consol_elimination``（由 ``recalculate_trial`` 叠加）。
    只 flush 不 commit。``basis`` 可由调用方传入以保证与后续步骤同源。
    """
    if basis is None:
        basis = await load_calc_basis(db, project_id, year)
    if basis is None:
        raise ValueError(f"企业树构建失败：找不到合并母项目 {project_id}")

    from app.services.consol_trial_service import sync_trial_rows

    amounts = trial_amounts(basis)
    computed_at = datetime.now(timezone.utc).isoformat()

    def fill(trial, account: str | None) -> None:
        a = amounts.get(account) if account is not None else None
        trial.individual_sum = a.individual_sum if a is not None else ZERO
        trial.consolidation_breakdown = {
            "by_company": a.by_company if a is not None else [],
            "individual_sum": str(trial.individual_sum),
            "computed_at": computed_at,
        }

    await sync_trial_rows(db, project_id, year, basis, fill)
    return AggregationResult(
        project_id=project_id,
        year=year,
        accounts_aggregated=len(basis.accounts),
        companies_traversed=len(data_leaves(basis.tree)),
        total_individual_sum=sum((a.individual_sum for a in amounts.values()), ZERO),
    )
