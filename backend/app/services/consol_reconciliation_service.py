"""合并模块 B2：worksheet ↔ trial 单一事实源对账服务（consol-phase0-core-pipeline）

职责：逐科目对比差额表引擎（worksheet 根节点）算出的 `consolidated_amount`
与报表数据源（`consol_trial.consol_amount`），差异超容差则记 error 日志并
返回 `is_reconciled=false` + diffs 清单，但 **不阻断**接口（仍正常返回，E5）。

口径变更（spec consol-tree-three-code-autobuild 任务 7.5，有意）：两条路径已共用同一棵树、
同一分录归属与同一科目方向（`consol_calc_basis`），根节点合并数与试算合并数逐科目恒等（P8，
需求 5.5）。旧版「两条路径归集维度不同、diff 只是观测信号」的前提不再成立 ——
现在任何超容差差异都是缺陷（常见原因：只重算了其中一条路径，或重算后树结构/分录又变了）。
根节点的差额表键是 `node_key`（`{企业代码}:consol`），不再是纯企业代码。

架构：对账核心逻辑是纯函数 `_reconcile_amounts`（喂两个内存字典 + tolerance），
DB 取数在外层 `reconcile_worksheet_vs_trial` —— PBT（P4）验「对账逻辑自洽」
（`is_reconciled == (max_abs_diff <= tolerance)` 且 diffs 集合正确），
两路径数值相等由 P8（真 SQLite 全链路）守护。

全程金额使用 `Decimal`，无 `float` 中转（属性 P7）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consolidation_models import ConsolWorksheet
from app.services.consol_tree_service import build_tree
from app.services.consol_trial_service import get_trial_balance

logger = logging.getLogger(__name__)

ZERO = Decimal("0")


@dataclass
class ReconciliationResult:
    """B2 对账结果。

    - is_reconciled: 是否对平（== diffs 为空 == max_abs_diff <= tolerance）
    - tolerance: 本次对账采用的容差
    - diffs: 超容差科目清单，每项 {account_code, worksheet_amount, trial_amount, diff}
             金额字段全部为 str(Decimal)，无 float 中转
    - max_abs_diff: 所有科目 |worksheet - trial| 的最大值
    """

    is_reconciled: bool
    tolerance: Decimal
    diffs: list[dict] = field(default_factory=list)
    max_abs_diff: Decimal = ZERO


# ---------------------------------------------------------------------------
# 纯函数：对账核心逻辑（无 DB / 无副作用，便于 PBT 喂内存字典）
# ---------------------------------------------------------------------------

def _reconcile_amounts(
    ws_map: dict[str, Decimal],
    trial_map: dict[str, Decimal],
    tolerance: Decimal,
) -> ReconciliationResult:
    """纯对账：取两侧科目并集，逐科目 diff，超容差进 diffs。

    Args:
        ws_map: {account_code: Decimal}  worksheet 根节点合并数
        trial_map: {account_code: Decimal}  trial 合并数（consol_amount）
        tolerance: 容差（>= 此值才算 diff；恰好等于 tolerance 不进 diffs）

    Returns:
        ReconciliationResult

    后置条件（属性 P4）：
        - is_reconciled == (max_abs_diff <= tolerance)
        - diffs 集合恰为 {code | abs(ws - trial) > tolerance}
        - 只在一侧存在的科目，另一侧视为 ZERO

    全程 Decimal，无 float 中转。
    """
    diffs: list[dict] = []
    max_abs = ZERO

    all_codes = set(ws_map) | set(trial_map)
    for code in sorted(all_codes):
        w = ws_map.get(code, ZERO)
        t = trial_map.get(code, ZERO)
        d = w - t
        abs_d = abs(d)
        if abs_d > tolerance:
            diffs.append({
                "account_code": code,
                "worksheet_amount": str(w),
                "trial_amount": str(t),
                "diff": str(d),
            })
        if abs_d > max_abs:
            max_abs = abs_d

    return ReconciliationResult(
        is_reconciled=(len(diffs) == 0),
        tolerance=tolerance,
        diffs=diffs,
        max_abs_diff=max_abs,
    )


# ---------------------------------------------------------------------------
# DB 取数
# ---------------------------------------------------------------------------

async def _get_root_node_key(db: AsyncSession, project_id: UUID) -> str | None:
    """取企业树根节点的 `node_key`（差额表引擎用它作 node_company_code 写入）。

    健壮性：找不到根（build_tree 返回 None）则返回 None，由外层降级为空对账结果，
    不抛异常中断（对账不应让缺数据崩溃）。
    """
    root = await build_tree(db, project_id)
    if root is None:
        return None
    return root.node_key or root.company_code


async def _load_worksheet_root(
    db: AsyncSession, project_id: UUID, root_code: str, year: int
) -> dict[str, Decimal]:
    """加载 worksheet 根节点各科目合并数 `{account_code: Decimal}`。

    根节点的 `consolidated_amount` 即最终合并数（worksheet 引擎后序遍历的输出）。
    口径：`node_company_code == 根 node_key` + `is_deleted == false`。
    金额 `Decimal(str(...))`，无 float 中转。
    """
    result = await db.execute(
        sa.select(
            ConsolWorksheet.account_code,
            ConsolWorksheet.consolidated_amount,
        ).where(
            ConsolWorksheet.project_id == project_id,
            ConsolWorksheet.node_company_code == root_code,
            ConsolWorksheet.year == year,
            ConsolWorksheet.is_deleted == sa.false(),
        )
    )
    out: dict[str, Decimal] = {}
    for code, amount in result.all():
        if amount is not None:
            out[code] = Decimal(str(amount))
    return out


# ---------------------------------------------------------------------------
# 编排：取数 → 纯对账 → 不阻断地返回结果
# ---------------------------------------------------------------------------

async def reconcile_worksheet_vs_trial(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    tolerance: Decimal = Decimal("0.01"),
) -> ReconciliationResult:
    """对账 worksheet 根节点 consolidated_amount 与 consol_trial.consol_amount。

    逐科目对比，返回差异清单 + is_reconciled 标志。diff > tolerance 时记 warning
    并返回 is_reconciled=false，但 **不阻断**（接口仍正常返回，E5）。绝不抛异常中断。

    前置条件：worksheet 已 `recalc_full`（根节点 consolidated_amount 已算）；
              trial 已 `recalculate_trial`。
    """
    root_code = await _get_root_node_key(db, project_id)
    if root_code is None:
        # 找不到企业树根 → 降级为空对账结果（不崩），仍记 warning 便于运维感知
        logger.warning(
            "B2 对账跳过：项目 %s 找不到企业树根节点（build_tree 返回 None）",
            project_id,
        )
        return ReconciliationResult(
            is_reconciled=True, tolerance=tolerance, diffs=[], max_abs_diff=ZERO,
        )

    ws_map = await _load_worksheet_root(db, project_id, root_code, year)
    trials = await get_trial_balance(db, project_id, year)
    trial_map = {
        t.standard_account_code: Decimal(str(t.consol_amount))
        for t in trials
        if t.consol_amount is not None
    }

    result = _reconcile_amounts(ws_map, trial_map, tolerance)

    if not result.is_reconciled:
        # 两条路径同源（P8）：差异即缺陷，记 error 概要，但不阻断接口
        logger.error(
            "B2 对账发现差异（两条路径同源，差异即缺陷；请先全量重算差额表与合并试算）："
            "项目=%s 年度=%s 容差=%s max_abs_diff=%s 超容差科目数=%d 示例=%s",
            project_id, year, tolerance, result.max_abs_diff,
            len(result.diffs), result.diffs[:5],
        )

    return result
