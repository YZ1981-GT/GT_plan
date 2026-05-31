"""合并模块 B1：子公司本体自动汇总服务（consol-phase0-core-pipeline）

职责：遍历企业树，按 `standard_account_code` 把各子公司
`trial_balance.audited_amount` 加总写入 `consol_trial.individual_sum`，
同时写 `consolidation_breakdown` provenance（哪些子公司贡献了多少）。

取数口径铁律：`_load_audited_amounts` 必须与
`consol_worksheet_engine._get_audited_amount` 完全一致 ——
读 `audited_amount`、`is_deleted == false`、按 `standard_account_code`。
否则 B2（worksheet ↔ trial 对账）必然失败。

设计边界（Phase 0 单层合并）：本算法用「无 children 的叶子节点」求和，
仅对单层合并（母 + 直接子公司）正确。多级合并树的中间节点本体由
`consol_worksheet_engine._calc_node` 后序遍历负责，不在本服务守护范围。

全程金额使用 `Decimal`；provenance JSON 中金额以 `str(Decimal)` 序列化，
无 `float` 中转（属性 P7）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TrialBalance
from app.services.consol_tree_service import TreeNode, build_tree

ZERO = Decimal("0")


@dataclass
class AggregationResult:
    """B1 汇总统计结果。"""

    project_id: UUID
    year: int
    accounts_aggregated: int        # 写入 individual_sum 的科目数
    companies_traversed: int        # 遍历的子公司（叶子）节点数
    total_individual_sum: Decimal   # 全表 individual_sum 合计（debug 用）


# ---------------------------------------------------------------------------
# 纯函数：汇总核心逻辑（无 DB / 无副作用，便于 PBT 喂内存字典）
# ---------------------------------------------------------------------------

def _iter_nodes(node: TreeNode) -> list[TreeNode]:
    """前序遍历企业树，返回所有节点（含根）。"""
    nodes: list[TreeNode] = [node]
    for child in node.children:
        nodes.extend(_iter_nodes(child))
    return nodes


def _collect_leaves(root: TreeNode) -> list[TreeNode]:
    """叶子节点 = children 为空的节点 = 单体子公司（Phase 0 单层合并假设）。"""
    return [n for n in _iter_nodes(root) if not n.children]


def _aggregate_from_company_amounts(
    company_amounts: list[tuple[dict, dict[str, Decimal]]],
) -> tuple[dict[str, Decimal], dict[str, list[dict]]]:
    """纯汇总：跨子公司按科目加总 + 构建 provenance。

    Args:
        company_amounts: [(company_meta, {account_code: Decimal}), ...]
            company_meta 至少含 `company_code` / `company_name`。

    Returns:
        (acc, prov)
        - acc: {account_code: Decimal}  各科目跨子公司加总
        - prov: {account_code: [{company_code, company_name, amount(str)}, ...]}
            amount == 0 的子公司不写入 provenance（后置条件 + 属性 P2）。

    不变式：遍历过程中 acc[code] 始终等于「已处理子公司在 code 上的 audited_amount 之和」。
    金额全程 Decimal，序列化为 str(Decimal)，无 float 中转（属性 P7）。
    """
    acc: dict[str, Decimal] = {}
    prov: dict[str, list[dict]] = {}

    for meta, amounts in company_amounts:
        for code, amount in amounts.items():
            if amount == ZERO:
                # 0 贡献不写溯源行（后置条件 / 属性 P2）
                continue
            acc[code] = acc.get(code, ZERO) + amount
            prov.setdefault(code, []).append({
                "company_code": meta.get("company_code"),
                "company_name": meta.get("company_name"),
                "amount": str(amount),
            })

    return acc, prov


# ---------------------------------------------------------------------------
# DB 取数：严格复用 _get_audited_amount 同口径
# ---------------------------------------------------------------------------

async def _load_audited_amounts(
    db: AsyncSession, project_id: UUID, year: int
) -> dict[str, Decimal]:
    """加载某子公司全部审定数 `{account_code: Decimal}`。

    一次性查询（避免 N 次单科目查询），口径与
    `consol_worksheet_engine._get_audited_amount` 严格一致：
    `audited_amount` + `is_deleted == false` + 按 `standard_account_code`。
    """
    result = await db.execute(
        sa.select(
            TrialBalance.standard_account_code,
            TrialBalance.audited_amount,
        ).where(
            TrialBalance.project_id == project_id,
            TrialBalance.year == year,
            TrialBalance.is_deleted == sa.false(),
        )
    )
    out: dict[str, Decimal] = {}
    for code, amount in result.all():
        if amount is not None:
            # 同 _get_audited_amount：Decimal(str(...))，无 float 中转
            out[code] = Decimal(str(amount))
    return out


async def _load_account_names(
    db: AsyncSession, project_id: UUID, year: int
) -> dict[str, str]:
    """加载某子公司科目名 `{account_code: account_name}`（用于建行时带入 account_name）。

    同样的 soft-delete 过滤口径；仅收集非空名字。
    """
    result = await db.execute(
        sa.select(
            TrialBalance.standard_account_code,
            TrialBalance.account_name,
        ).where(
            TrialBalance.project_id == project_id,
            TrialBalance.year == year,
            TrialBalance.is_deleted == sa.false(),
        )
    )
    out: dict[str, str] = {}
    for code, name in result.all():
        if name and code not in out:
            out[code] = name
    return out


# ---------------------------------------------------------------------------
# 编排：遍历树 → 取数 → 纯汇总 → 写回 consol_trial
# ---------------------------------------------------------------------------

async def aggregate_individual_sum(
    db: AsyncSession, project_id: UUID, year: int
) -> AggregationResult:
    """遍历企业树，把各子公司 audited_amount 按科目加总写入 individual_sum，
    并写 consolidation_breakdown provenance。返回汇总统计。

    责任边界：只负责「加总到 individual_sum + 写 provenance」，
    不修改 consol_adjustment / consol_elimination（由 recalculate_trial 叠加）。
    """
    tree = await build_tree(db, project_id)
    if tree is None:
        raise ValueError(f"企业树构建失败：找不到合并母项目 {project_id}")

    # 叶子 = 单体子公司（Phase 0 单层合并假设）
    leaves = _collect_leaves(tree)

    # 逐子公司取数（每公司 O(1) 次查询，非按科目 N 次）
    company_amounts: list[tuple[dict, dict[str, Decimal]]] = []
    name_map: dict[str, str] = {}
    for leaf in leaves:
        amounts = await _load_audited_amounts(db, leaf.project_id, year)
        company_amounts.append((
            {"company_code": leaf.company_code, "company_name": leaf.company_name},
            amounts,
        ))
        names = await _load_account_names(db, leaf.project_id, year)
        for code, name in names.items():
            name_map.setdefault(code, name)

    # 纯汇总
    acc, prov = _aggregate_from_company_amounts(company_amounts)

    # 写回 consol_trial（无对应行自动建行，account_name 从 TB 带入）
    # 延迟导入打破潜在循环依赖（recalculate_trial 在 task 3 反向 import 本服务）
    from app.services.consol_trial_service import upsert_trial_row

    computed_at = datetime.now(timezone.utc).isoformat()
    for code, total in acc.items():
        trial = await upsert_trial_row(
            db, project_id, year, code, account_name=name_map.get(code)
        )
        trial.individual_sum = total
        trial.consolidation_breakdown = {
            "by_company": prov[code],
            "individual_sum": str(total),
            "computed_at": computed_at,
        }

    await db.flush()

    return AggregationResult(
        project_id=project_id,
        year=year,
        accounts_aggregated=len(acc),
        companies_traversed=len(leaves),
        total_individual_sum=sum(acc.values(), ZERO),
    )
