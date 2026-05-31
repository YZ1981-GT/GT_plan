"""合并模块 A6/C2：统一级联刷新编排者（consol-phase2-orchestration）

ADR-CONSOL-201：重建被删的 `consolidation_orchestrator`（C2，源码被删剩 stale pyc）。
合并"建树→worksheet→trial→对账→报表→附注"全链路此前无统一入口、散落各 router，
依赖顺序（notes 依赖 report 依赖 trial 依赖 worksheet）无保证。本服务把整条链路
收敛为单一编排入口 `refresh_all`，**只编排不重算**（复用既有 service，不重写）。

DAG 自底向上（顺序恒定，属性 S1）：
    tree → worksheet → trial → reconcile → report → notes

失败隔离（属性 S2 / 错误场景 EH1）：
    每步 try/except 记 `errors[{step, node, error}]`；
    - 关键步（worksheet / trial）失败 → 中断剩余步骤（无正确合并数，下游无意义）；
    - 下游步（reconcile / report / notes）失败 → 记错误并继续（部分成功）。

幂等（属性 S6）：同 project/year 连续两次 refresh_all 结果数值一致
（recalc_full / recalculate_trial 都是全量重算覆盖式写入）。

commit 语义：recalc_full 内部自行 commit；recalculate_trial 只 flush，
因此 trial 成功后本服务统一 `await db.commit()` 一次，确保 individual_sum /
consol_elimination 落库后 report / notes 读到的是最新合并数。

进度上报：可选 `progress_cb(step, current, total, current_node, status)`，
在每步开始 / 结束时回调（worker 经 SSE 推进度，见 Task 2）。回调失败不影响编排。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.consol_disclosure_service import generate_full_consol_notes
from app.services.consol_reconciliation_service import (
    ReconciliationResult,
    reconcile_worksheet_vs_trial,
)
from app.services.consol_report_service import generate_consol_reports_sync
from app.services.consol_trial_service import recalculate_trial
from app.services.consol_tree_service import build_tree, get_descendants
from app.services.consol_worksheet_engine import recalc_full

logger = logging.getLogger(__name__)

# DAG 步骤名（顺序恒定，属性 S1）
STEP_TREE = "tree"
STEP_WORKSHEET = "worksheet"
STEP_TRIAL = "trial"
STEP_RECONCILE = "reconcile"
STEP_REPORT = "report"
STEP_NOTES = "notes"

# 总步骤数（progress_cb 用）
TOTAL_STEPS = 6

# 关键步：失败则中断剩余步骤（无正确合并数下游无意义）
_CRITICAL_STEPS = frozenset({STEP_WORKSHEET, STEP_TRIAL})


@dataclass
class CascadeRefreshResult:
    """级联刷新结果（设计 §四 数据模型）。

    - nodes_refreshed: 企业树节点数（含根）
    - steps_completed: 已成功完成的步骤，按 DAG 顺序的子集
                       [tree, worksheet, trial, reconcile, report, notes]
    - errors: 失败步骤清单 [{step, node, error}]
    - duration_ms: 编排总耗时（毫秒）
    - reconciliation: Phase 0 对账结果（观测，不阻断）
    """

    parent_project_id: UUID
    year: int
    nodes_refreshed: int = 0
    steps_completed: list[str] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    duration_ms: int = 0
    reconciliation: ReconciliationResult | None = None


def _emit(
    progress_cb: Callable | None,
    step: str,
    current: int,
    total: int,
    current_node: str | None,
    status: str,
) -> None:
    """安全调用进度回调（可同步、可为 None）。回调异常不影响编排链路。"""
    if progress_cb is None:
        return
    try:
        progress_cb(step, current, total, current_node, status)
    except Exception:  # noqa: BLE001 - 进度回调失败绝不应中断编排
        logger.warning("级联刷新进度回调失败（已忽略）：step=%s status=%s", step, status, exc_info=True)


async def refresh_all(
    db: AsyncSession,
    parent_project_id: UUID,
    year: int,
    progress_cb: Callable | None = None,
) -> CascadeRefreshResult:
    """合并链路唯一编排入口（A6/C2，ADR-CONSOL-201）。

    按 DAG 自底向上执行：tree → worksheet → trial → reconcile → report → notes。
    每步失败隔离记 errors；关键步（worksheet/trial）失败中断剩余步骤，
    下游步（reconcile/report/notes）失败记录后继续（部分成功）。

    Args:
        db: AsyncSession
        parent_project_id: 合并母项目 ID
        year: 报告年度
        progress_cb: 可选进度回调 (step, current, total, current_node, status)

    Returns:
        CascadeRefreshResult（steps_completed 反映实际完成步骤，errors 含失败步骤）
    """
    result = CascadeRefreshResult(parent_project_id=parent_project_id, year=year)
    t0 = time.monotonic()
    root_node_label: str | None = None

    # ---- 步骤 1：build_tree（基础，统计节点数）-------------------------------
    _emit(progress_cb, STEP_TREE, 1, TOTAL_STEPS, None, "running")
    try:
        tree = await build_tree(db, parent_project_id)
        if tree is not None:
            result.nodes_refreshed = 1 + len(get_descendants(tree))
            root_node_label = tree.company_code
        else:
            result.nodes_refreshed = 0
            logger.warning("级联刷新：项目 %s 未找到企业树（build_tree 返回 None）", parent_project_id)
        result.steps_completed.append(STEP_TREE)
        _emit(progress_cb, STEP_TREE, 1, TOTAL_STEPS, root_node_label, "completed")
    except Exception as exc:  # noqa: BLE001 - 失败隔离
        # 建树失败：无树则下游全部无意义，中断
        result.errors.append({"step": STEP_TREE, "node": None, "error": str(exc)})
        logger.exception("级联刷新建树失败，中断：项目=%s 年度=%s", parent_project_id, year)
        _emit(progress_cb, STEP_TREE, 1, TOTAL_STEPS, None, "error")
        result.duration_ms = int((time.monotonic() - t0) * 1000)
        return result

    # ---- 步骤 2：worksheet recalc_full（关键步，内部自行 commit）-------------
    _emit(progress_cb, STEP_WORKSHEET, 2, TOTAL_STEPS, root_node_label, "running")
    try:
        await recalc_full(db, parent_project_id, year)
        result.steps_completed.append(STEP_WORKSHEET)
        _emit(progress_cb, STEP_WORKSHEET, 2, TOTAL_STEPS, root_node_label, "completed")
    except Exception as exc:  # noqa: BLE001 - 失败隔离
        result.errors.append({"step": STEP_WORKSHEET, "node": root_node_label, "error": str(exc)})
        logger.exception("级联刷新 worksheet 失败（关键步），中断：项目=%s 年度=%s", parent_project_id, year)
        _emit(progress_cb, STEP_WORKSHEET, 2, TOTAL_STEPS, root_node_label, "error")
        result.duration_ms = int((time.monotonic() - t0) * 1000)
        return result

    # ---- 步骤 3：trial recalculate_trial（关键步，只 flush → 本步后统一 commit）
    _emit(progress_cb, STEP_TRIAL, 3, TOTAL_STEPS, root_node_label, "running")
    try:
        await recalculate_trial(db, parent_project_id, year)
        # recalculate_trial 只 flush，统一 commit 一次确保 individual_sum /
        # consol_elimination 落库后 report / notes 读到最新合并数。
        await db.commit()
        result.steps_completed.append(STEP_TRIAL)
        _emit(progress_cb, STEP_TRIAL, 3, TOTAL_STEPS, root_node_label, "completed")
    except Exception as exc:  # noqa: BLE001 - 失败隔离
        result.errors.append({"step": STEP_TRIAL, "node": root_node_label, "error": str(exc)})
        logger.exception("级联刷新 trial 失败（关键步），中断：项目=%s 年度=%s", parent_project_id, year)
        _emit(progress_cb, STEP_TRIAL, 3, TOTAL_STEPS, root_node_label, "error")
        result.duration_ms = int((time.monotonic() - t0) * 1000)
        return result

    # ---- 步骤 4：reconcile（下游观测，永不阻断；仍防御式 try/except）---------
    _emit(progress_cb, STEP_RECONCILE, 4, TOTAL_STEPS, root_node_label, "running")
    try:
        result.reconciliation = await reconcile_worksheet_vs_trial(db, parent_project_id, year)
        result.steps_completed.append(STEP_RECONCILE)
        _emit(progress_cb, STEP_RECONCILE, 4, TOTAL_STEPS, root_node_label, "completed")
    except Exception as exc:  # noqa: BLE001 - 失败隔离（下游步：记录后继续）
        result.errors.append({"step": STEP_RECONCILE, "node": root_node_label, "error": str(exc)})
        logger.exception("级联刷新对账失败（下游步，继续）：项目=%s 年度=%s", parent_project_id, year)
        _emit(progress_cb, STEP_RECONCILE, 4, TOTAL_STEPS, root_node_label, "error")

    # ---- 步骤 5：report 生成（下游步，SYNC 调用，失败记录后继续）------------
    _emit(progress_cb, STEP_REPORT, 5, TOTAL_STEPS, root_node_label, "running")
    try:
        generate_consol_reports_sync(db, parent_project_id, year)
        result.steps_completed.append(STEP_REPORT)
        _emit(progress_cb, STEP_REPORT, 5, TOTAL_STEPS, root_node_label, "completed")
    except Exception as exc:  # noqa: BLE001 - 失败隔离（下游步：记录后继续）
        result.errors.append({"step": STEP_REPORT, "node": root_node_label, "error": str(exc)})
        logger.exception("级联刷新报表失败（下游步，继续）：项目=%s 年度=%s", parent_project_id, year)
        _emit(progress_cb, STEP_REPORT, 5, TOTAL_STEPS, root_node_label, "error")

    # ---- 步骤 6：notes V2（下游步，feature flag 门控；失败记录后继续）--------
    # 门控：CONSOL_NOTES_V2_ENABLED 存在则按其值；尚未定义（Task 3 才新增）时默认运行。
    _emit(progress_cb, STEP_NOTES, 6, TOTAL_STEPS, root_node_label, "running")
    if getattr(settings, "CONSOL_NOTES_V2_ENABLED", True):
        try:
            await generate_full_consol_notes(db, parent_project_id, year)
            result.steps_completed.append(STEP_NOTES)
            _emit(progress_cb, STEP_NOTES, 6, TOTAL_STEPS, root_node_label, "completed")
        except Exception as exc:  # noqa: BLE001 - 失败隔离（下游步：记录后继续）
            result.errors.append({"step": STEP_NOTES, "node": root_node_label, "error": str(exc)})
            logger.exception("级联刷新合并附注失败（下游步，继续）：项目=%s 年度=%s", parent_project_id, year)
            _emit(progress_cb, STEP_NOTES, 6, TOTAL_STEPS, root_node_label, "error")
    else:
        # flag 显式关闭：附注步骤跳过（视为无操作完成，不计入失败）
        result.steps_completed.append(STEP_NOTES)
        logger.info("级联刷新：CONSOL_NOTES_V2_ENABLED=False，跳过 V2 附注生成（项目=%s）", parent_project_id)
        _emit(progress_cb, STEP_NOTES, 6, TOTAL_STEPS, root_node_label, "skipped")

    result.duration_ms = int((time.monotonic() - t0) * 1000)
    logger.info(
        "级联刷新完成：项目=%s 年度=%s 节点=%d 完成步骤=%s 错误=%d 耗时=%dms",
        parent_project_id, year, result.nodes_refreshed,
        result.steps_completed, len(result.errors), result.duration_ms,
    )
    return result
