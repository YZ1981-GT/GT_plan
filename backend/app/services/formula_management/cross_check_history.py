"""表间审核执行历史（公式管理中心「执行历史」；spec formula-settings-wiring-closure R3.1）。

* 运行记录 = ``draft_refresh_audit`` 中 ``scope = formula:report-cross-check`` 的行（按 ``operated_at``
  倒序、按年度过滤）；每次运行的计数取自写入时的 ``detail``（executed / issue / hint）。
* 逐条结论 = ``cross_check_results``（``details.run_id`` 关联）。该表按「同规则先删后插」只保留每条
  规则最近一次的结论 ⇒ 只有最近一次运行还能看到逐条明细，更早的运行如实标 ``issues_retained=False``，
  不拿别次的结论冒充。
"""
from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import DraftRefreshAudit
from app.services.formula_management.cross_check_run import _RUN_SCOPE, get_issues_by_run


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _issue(row: Any) -> dict[str, Any]:
    return {"rule_id": row.rule_id, "status": row.status, "left_value": _num(row.left_amount),
            "right_value": _num(row.right_amount), "diff": _num(row.difference), "details": row.details or {}}


async def list_history(db: AsyncSession, project_id: uuid.UUID, year: int, limit: int = 20) -> list[dict[str, Any]]:
    runs = (await db.execute(sa.select(DraftRefreshAudit).where(
        DraftRefreshAudit.project_id == project_id, DraftRefreshAudit.year == year,
        DraftRefreshAudit.scope == _RUN_SCOPE,
    ).order_by(DraftRefreshAudit.operated_at.desc()).limit(max(1, min(int(limit), 50))))).scalars().all()
    out: list[dict[str, Any]] = []
    for run in runs:
        detail = run.detail or {}
        issues = [_issue(r) for r in await get_issues_by_run(db, run.id)]
        out.append({
            "run_id": str(run.id),
            "status": detail.get("status") or ("executed" if run.result_status == "success" else "no_result"),
            "created_at": run.operated_at.isoformat() if run.operated_at else None,
            "executed_count": int(detail.get("executed_count") or 0),
            "issue_count": int(detail.get("issue_count") or 0),
            "hint_count": int(detail.get("hint_count") or 0),
            "issues_retained": bool(issues),
            "issues": issues,
        })
    return out
