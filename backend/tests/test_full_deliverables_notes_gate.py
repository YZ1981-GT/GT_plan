"""一键生成全套的附注导出前一致性闸门 —— deliverable-writeback-and-online-edit-integrity（复盘修复）。

「生成附注」在导出前比对附注与底稿、不一致让用户确认（render_disclosure_notes）；一键全套此前直接导出附注、
全程无提示（执行器只在批处理后给步骤打一个无人读取的 needs_confirmation 标记，已删除）。
现与「生成附注」用同一判定 check_note_consistency，在建任务之前拦截：

- 会导出附注 + 未确认 + 不一致 ⇒ 409 notes_inconsistent，**不建任务**（执行器一次都不构造）；
- 已确认 ⇒ 不再检查、照常执行，payload 留痕 confirm_inconsistent；一致 ⇒ 照常执行；
- 步骤不含附注 ⇒ 不检查；
- 409 经全局异常处理器后 detail 在 ``message``（前端拦截器回填到 detail）—— 线形守卫走真实 app。

鉴权（项目成员 + 交付件角色矩阵）不在本文件测：直调时把 ``_guard_action`` 换成桩，只断言闸门之前先鉴权；
端点级鉴权见 test_deliverable_generation_membership_auth.py。
"""
from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.models.phase13_schemas import FullDeliverablesRequest
from app.services.deliverable_permissions import DeliverableAction
from app.services.full_deliverables_executor import FULL_DELIVERABLES_STEPS, resolve_full_steps

PROJECT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
JOB_ID = uuid.uuid4()
YEAR = 2025

_INCONSISTENT = {
    "consistent": False,
    "never_synced": [
        {
            "note_section": "八、1",
            "section_title": "货币资金",
            "wp_codes": ["E1"],
            "wp_ids": {"E1": "wp-e1"},
            "wp_sheet": "E1-审定表",
        }
    ],
    "stale": [{"note_section": "八、5", "section_title": "应收账款"}],
}
_CONSISTENT = {"consistent": True, "never_synced": [], "stale": []}

_CHECK = "app.services.deliverable_note_consistency.check_note_consistency"
_EXECUTOR = "app.services.full_deliverables_executor.FullDeliverablesExecutor"


def test_resolve_full_steps_matches_executor_contract():
    """路由闸门与执行器同一步骤口径：空 / 全无效 ⇒ 全部；其余按权威顺序过滤。"""
    assert resolve_full_steps(None) == FULL_DELIVERABLES_STEPS
    assert resolve_full_steps([]) == FULL_DELIVERABLES_STEPS
    assert resolve_full_steps(["bogus"]) == FULL_DELIVERABLES_STEPS
    assert resolve_full_steps(["report_body", "financial_reports"]) == ["financial_reports", "report_body"]


class _Harness:
    def __init__(self, consistency: dict) -> None:
        self.check = AsyncMock(return_value=consistency)
        self.guard = AsyncMock(return_value=None)
        self.executor = MagicMock()
        self.executor.run = AsyncMock(return_value=SimpleNamespace(job_id=JOB_ID))
        self.executor_cls = MagicMock(return_value=self.executor)
        job = SimpleNamespace(
            id=JOB_ID, project_id=PROJECT_ID, job_type="full_deliverables", status="succeeded",
            payload={}, progress_total=3, progress_done=3, failed_count=0, initiated_by=USER_ID,
            created_at=None, updated_at=None,
        )
        self.job_svc = MagicMock()
        self.job_svc.get_job = AsyncMock(return_value=job)
        self.job_svc.get_job_items = AsyncMock(return_value=[])

    def run(self, body: FullDeliverablesRequest):
        from app.routers import word_export as mod

        with (
            patch.object(mod, "_guard_action", new=self.guard),
            patch(_CHECK, new=self.check),
            patch(_EXECUTOR, new=self.executor_cls),
            patch("app.services.export_job_service.ExportJobService", return_value=self.job_svc),
        ):
            return asyncio.run(
                mod.create_full_deliverables(
                    PROJECT_ID, body, db=AsyncMock(), current_user=SimpleNamespace(id=USER_ID)
                )
            )


def test_inconsistent_unconfirmed_returns_409_and_never_builds_job():
    h = _Harness(_INCONSISTENT)
    with pytest.raises(HTTPException) as ei:
        h.run(FullDeliverablesRequest(year=YEAR))
    assert ei.value.status_code == 409
    detail = ei.value.detail
    assert detail["code"] == "notes_inconsistent"
    # 清单只带确认框显示的三项（wp_ids / wp_sheet 不外发）
    assert detail["never_synced"] == [{"note_section": "八、1", "section_title": "货币资金", "wp_codes": ["E1"]}]
    assert detail["stale"] == [{"note_section": "八、5", "section_title": "应收账款", "wp_codes": []}]
    assert h.check.await_args.args[1:] == (PROJECT_ID, YEAR)
    # 🔴 核心：闸门在建任务之前 —— 执行器一次都不构造
    h.executor_cls.assert_not_called()
    # 先鉴权（与交付中心生成同一判定）再进闸门
    h.guard.assert_awaited_once()
    assert h.guard.await_args.args[2:] == (PROJECT_ID, DeliverableAction.export)


def test_inconsistent_confirmed_skips_check_and_runs():
    h = _Harness(_INCONSISTENT)
    resp = h.run(FullDeliverablesRequest(year=YEAR, confirm_inconsistent=True))
    assert resp.id == JOB_ID
    h.check.assert_not_awaited()
    h.executor.run.assert_awaited_once()
    assert h.executor.run.await_args.kwargs["payload"]["confirm_inconsistent"] is True


def test_consistent_runs_without_confirmation():
    h = _Harness(_CONSISTENT)
    resp = h.run(FullDeliverablesRequest(year=YEAR))
    assert resp.id == JOB_ID
    h.check.assert_awaited_once()
    h.executor.run.assert_awaited_once()
    assert h.executor.run.await_args.kwargs["payload"]["confirm_inconsistent"] is False


def test_steps_without_notes_skip_the_gate():
    h = _Harness(_INCONSISTENT)
    h.run(FullDeliverablesRequest(year=YEAR, steps=["financial_reports", "report_body"]))
    h.check.assert_not_awaited()
    h.executor.run.assert_awaited_once()


@pytest.mark.asyncio
async def test_409_wire_shape_through_app_error_handler():
    """真实 app：全局处理器把 HTTPException.detail 放在 message（前端 notesInconsistencyFromError 两处都读）。"""
    from httpx import ASGITransport, AsyncClient

    import app.deps as deps
    from app.deps import get_current_user, get_db
    from app.main import app
    from app.models.core import User

    user = MagicMock(spec=User)
    user.id = USER_ID
    user.role = MagicMock()
    user.role.value = "admin"
    db = AsyncMock()

    async def _db():
        return db

    async def _user():
        return user

    executor_cls = MagicMock()
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    try:
        # 真实鉴权链照跑（admin 跳过成员校验）；只把归档守卫 / RLS / EQCR 判定这几个取数点置空（db 是 AsyncMock）
        with (
            patch.object(deps, "_check_project_not_archived", new=AsyncMock(return_value=None)),
            patch.object(deps, "set_rls_context", new=AsyncMock(return_value=None)),
            patch("app.routers.deliverable._is_project_eqcr", new=AsyncMock(return_value=False)),
            patch(_CHECK, new=AsyncMock(return_value=_INCONSISTENT)),
            patch(_EXECUTOR, new=executor_cls),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    f"/api/projects/{PROJECT_ID}/word-exports/full-deliverables", json={"year": YEAR}
                )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["message"]["code"] == "notes_inconsistent"
    assert body["message"]["never_synced"][0]["section_title"] == "货币资金"
    executor_cls.assert_not_called()
