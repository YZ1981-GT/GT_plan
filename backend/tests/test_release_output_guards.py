"""platform-release-blocker-closure Task 14: reporting and deliverable hard stops."""
from __future__ import annotations

import inspect
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException


@pytest.mark.asyncio
async def test_report_generation_stops_when_trial_balance_recalc_fails():
    from app.services.report_engine import ReportEngine

    # generate_all_reports 现由 report_provenance 包裹（advisory lock + building run）。
    # get_bind 返回同步非 PG bind 以跳过 advisory lock；核心仍是：TB recalc 失败必须在
    # 报表生成（_generate_report）开始前传播、不 fail-open。
    db = AsyncMock()
    db.get_bind = lambda: SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    failure = RuntimeError("TB recalc failed")
    with patch(
        "app.services.trial_balance_service.TrialBalanceService.full_recalc",
        new=AsyncMock(side_effect=failure),
    ), patch.object(ReportEngine, "_generate_report", new=AsyncMock()) as gen:
        with pytest.raises(RuntimeError, match="TB recalc failed"):
            await ReportEngine(db).generate_all_reports(uuid.uuid4(), 2025)
    gen.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_full_deliverables_is_authenticated_410(monkeypatch):
    from app.routers import word_export

    guard = AsyncMock()
    monkeypatch.setattr(word_export, "_guard_action", guard)
    project_id = uuid.uuid4()
    body = word_export.FullDeliverablesRequest(year=2025)
    db = AsyncMock()
    user = SimpleNamespace(id=uuid.uuid4())
    with pytest.raises(HTTPException) as caught:
        await word_export.create_full_deliverables(project_id, body, db, user)
    assert caught.value.status_code == 410
    assert caught.value.detail["code"] == "LEGACY_FULL_DELIVERABLES_RETIRED"
    guard.assert_awaited_once()


def test_report_engine_has_no_fail_open_recalc_branch():
    from app.services.report_engine import ReportEngine

    source = inspect.getsource(ReportEngine.generate_all_reports)
    assert "使用现有 trial_balance 数据" not in source
    assert "await tb_svc.full_recalc" in source
