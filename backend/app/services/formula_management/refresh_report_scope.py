"""Draft Refresh 报表范围执行（spec formula-hub-integrity-closure ADR-FHIC-08；需求 3.1 / 3.5）。

报表范围不交 Runtime（计划段只登记预设页面，见 ``draft_refresh_orchestrator._dispatch``）。编排器取项目锁、执行完
runtime / marker 路径之后，在同一事务里调 :func:`execute_report_scope`：

1. 保存点内 ``TrialBalanceService.full_recalc``：抛错 ⇒ 本范围失败、保存点回滚（试算表不变）、不生成报表；
2. 另一个保存点内按项目真实准则（``ReportConfigService.resolve_applicable_standard``）、审定模式（``generate_all_reports``
   的默认 ``mode="audited"``）调报表权威生成路径，``skip_recalc=True``（上一步已重算）、``publish_events=False``（事件由
   路由在提交成功后投递）：抛错 ⇒ 本范围失败、保存点回滚；
3. 由逐行分类 ``GenerateSummary`` 得 :class:`ScopeOutcome`：金额变化 = ``changed_rows``、仅重算 = ``recomputed_rows``、失败行
   进 ``failures``；金额变化 > 0 时登记两个提交后事件 ``REPORT_ROW_CHANGED``（只含 before ≠ after 的行次）与
   ``REPORTS_UPDATED``（写法同 ``ReportEngine.generate_all_reports`` / ``routers/reports.py``）。

保存点失效（调用链内部 ``db.rollback()`` 撤销了整个事务，如 ``get_active_filter`` 默认的 fail-open 分支）不当成本范围
失败：此前各范围的写入已一并撤销、结果对象里的计数不再真实 ⇒ 抛 :class:`SavepointLost`，由路由按 500 处理、不提交。
只 flush 不 commit；不发事件；不调 ``trigger_recalc``（编排方决定：报表范围只规定两个提交后事件）。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.formula_management.refresh_outcome import ScopeOutcome

logger = logging.getLogger(__name__)

REPORT_SCOPE = "report"
#: 报表范围执行过 ⇒ ``rollback_available=False``，响应 ``warnings`` 带这句（ADR-FHIC-08）
ROLLBACK_UNAVAILABLE_WARNING = "报表可重新生成，不支持一键回滚"
#: ``REPORT_ROW_CHANGED`` 行次上限（与 ``ReportEngine.generate_all_reports`` 自己发事件时同口径）
ROW_CODE_LIMIT = 100
#: ``generate_all_reports`` 返回 dict 里不是报表类型的键
_NON_REPORT_KEYS = ("coverage_stats", "debug_info")


class SavepointLost(RuntimeError):
    """报表范围的保存点连同整个事务被调用链内部回滚：本次刷新此前的写入已撤销，不能再如实报告结果。"""


@asynccontextmanager
async def _savepoint(db: AsyncSession, stage: str) -> AsyncIterator[None]:
    """一个保存点；结束时核对会话的根事务仍是进入时那一个且未关闭，否则抛 :class:`SavepointLost`（覆盖原异常）。"""
    sync = getattr(db, "sync_session", None)
    root = sync.get_transaction() if sync is not None else None
    try:
        async with db.begin_nested():
            yield
    finally:
        if root is not None and (not root.is_active or sync.get_transaction() is not root):
            raise SavepointLost(f"报表范围{stage}期间事务被内部回滚，本次刷新此前的写入已全部撤销，请重试")


def _stage_failure(stage: str, label: str, exc: Exception) -> dict[str, Any]:
    return {"scope": REPORT_SCOPE, "stage": stage, "error": f"{label}：{type(exc).__name__}: {exc}"}


def _row_failure(row: dict[str, Any]) -> dict[str, Any]:
    reason = row.get("error") or row.get("state") or "计算失败"
    return {
        "scope": REPORT_SCOPE, "stage": "report_row", "report_type": row.get("report_type"),
        "row_code": row.get("row_code"), "state": row.get("state"),
        "error": f"报表 {row.get('report_type')} 行 {row.get('row_code')} 计算失败：{reason}",
    }


async def execute_report_scope(db: AsyncSession, *, project_id: UUID, year: int) -> ScopeOutcome:
    """执行报表范围并返回其 :class:`ScopeOutcome`（不提交、不发事件；保存点失效抛 :class:`SavepointLost`）。"""
    from app.models.audit_platform_schemas import EventPayload, EventType
    from app.services.report_config_service import ReportConfigService
    from app.services.report_engine import ReportEngine
    from app.services.report_row_compute import GenerateSummary
    from app.services.trial_balance_service import TrialBalanceService

    try:
        async with _savepoint(db, "试算表重算"):
            await TrialBalanceService(db).full_recalc(project_id, year)
    except SavepointLost:
        raise
    except Exception as exc:  # noqa: BLE001 — 试算表重算失败 = 本范围失败（需求 3.1），不生成报表
        logger.warning("Draft Refresh 报表范围：试算表重算失败 project=%s year=%s", project_id, year, exc_info=True)
        return ScopeOutcome(REPORT_SCOPE, failures=[_stage_failure("trial_balance_recalc", "试算表重算失败", exc)])

    summary = GenerateSummary()
    try:
        async with _savepoint(db, "报表生成"):
            standard = await ReportConfigService.resolve_applicable_standard(db, project_id)
            results = await ReportEngine(db).generate_all_reports(
                project_id, year, applicable_standard=standard,
                skip_recalc=True, publish_events=False, summary_out=summary,
            )
    except SavepointLost:
        raise
    except Exception as exc:  # noqa: BLE001 — 报表生成整体失败 = 本范围失败（保存点已回滚，逐行分类作废）
        logger.warning("Draft Refresh 报表范围：报表生成失败 project=%s year=%s", project_id, year, exc_info=True)
        return ScopeOutcome(REPORT_SCOPE, failures=[_stage_failure("report_generate", "报表生成失败", exc)])

    outcome = ScopeOutcome(
        REPORT_SCOPE, value_changes=len(summary.changed_rows), recomputed=len(summary.recomputed_rows),
        failures=[_row_failure(row) for row in summary.failed_rows],
    )
    if outcome.value_changes > 0:
        row_codes = list(dict.fromkeys(row["row_code"] for row in summary.changed_rows))
        outcome.post_commit_events = [
            EventPayload(event_type=EventType.REPORT_ROW_CHANGED, project_id=project_id, year=year,
                         extra={"changed_row_codes": row_codes[:ROW_CODE_LIMIT]}),
            EventPayload(event_type=EventType.REPORTS_UPDATED, project_id=project_id, year=year,
                         extra={"report_types": [key for key in results if key not in _NON_REPORT_KEYS]}),
        ]
    return outcome
