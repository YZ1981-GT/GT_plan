"""抵销审批 HTTP 回执的事件发布三态契约。"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.models.consolidation_schemas import EliminationEntryResponse, EliminationReviewAction
from app.models.consolidation_models import ReviewStatusEnum
from app.routers import consolidation as router


def _entry():
    now = datetime.now(timezone.utc)
    return EliminationEntryResponse.model_construct(
        id=uuid4(), project_id=uuid4(), entry_no="E-1", entry_group_id=uuid4(), year=2025,
        entry_type="internal_ar_ap", description="测试", lines=[], debit_amount="1.00", credit_amount="1.00",
        related_company_codes=None, branch_entity_code=None, origin=None, origin_key=None,
        is_continuous=False, prior_year_entry_id=None, review_status=ReviewStatusEnum.approved, reviewer_id=None,
        reviewed_at=now, is_deleted=False, created_at=now, updated_at=now,
    )


@pytest.mark.asyncio
async def test_review_response_reports_event_failed(monkeypatch):
    entry = _entry()
    user = SimpleNamespace(id=uuid4())
    db = SimpleNamespace(flush=AsyncMock(), commit=AsyncMock())
    event_bus = __import__("app.services.event_bus", fromlist=["event_bus"]).event_bus

    monkeypatch.setattr("app.services.elimination_service.get_entry", AsyncMock(return_value=entry))
    monkeypatch.setattr(router, "change_review_status", AsyncMock(return_value=entry))
    monkeypatch.setattr("app.services.consol_audit_helper.log_consol_action", AsyncMock())
    monkeypatch.setattr(event_bus, "publish", AsyncMock(side_effect=RuntimeError("EventBus 暂不可用")))

    response = await router.review_elimination(
        entry.id, entry.project_id, EliminationReviewAction(action="approve"), db, user,
    )

    assert response.recalc_trigger == "event_failed"
    assert response.recalc_notice and "手动重试" in response.recalc_notice
    db.commit.assert_awaited_once()
