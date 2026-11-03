"""readiness 路由的真实 HTTP 匹配、guard 顺序与响应形状。"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import wp_sync_router as ROUTER
from app.services.workpaper_sync.entry_readiness import (
    AcceptanceReadiness,
    EntryReadinessNotFound,
    EntrySyncReadiness,
    ReadinessReason,
    RuntimeReadiness,
)

PROJECT = uuid.uuid4()
WP = uuid.uuid4()
ENTRY = "xlsx/d4/analysis/d4-tab-customer-price"


def result() -> EntrySyncReadiness:
    return EntrySyncReadiness(
        entry_id=ENTRY,
        effective_entry_id="xlsx/gt-d4-operating-revenue",
        capability="bidirectional",
        adjudication_state="inherited",
        allowed_modes=("html",),
        can_claim_bidirectional=False,
        runtime=RuntimeReadiness(ready=False),
        acceptance=AcceptanceReadiness(state="missing", stale=False),
        reason=ReadinessReason(
            code="REPRESENTATION_MISSING",
            message="当前底稿尚未发布可用于在线编辑的版本。",
            next_action="先完成首版发布。",
        ),
    )


def client(monkeypatch, evaluator) -> tuple[TestClient, AsyncMock]:
    app = FastAPI()
    app.include_router(ROUTER.router)
    services = SimpleNamespace(session=object(), registry=object())
    app.dependency_overrides[ROUTER._services] = lambda: services
    guard = AsyncMock(return_value=SimpleNamespace(
        project_id=PROJECT, wp_id=WP, entry_id=ENTRY, user_id=uuid.uuid4(),
    ))
    monkeypatch.setattr(ROUTER, "_guard", guard)
    monkeypatch.setattr(ROUTER, "evaluate_entry_readiness", evaluator)
    return TestClient(app), guard


def test_http_route_calls_guard_before_evaluator(monkeypatch) -> None:
    evaluator = AsyncMock(return_value=result())
    http, guard = client(monkeypatch, evaluator)
    response = http.get(
        f"/api/projects/{PROJECT}/workpapers/{WP}/sync/entries/{ENTRY}/readiness"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["reason"]["code"] == "REPRESENTATION_MISSING"
    assert body["runtime"]["ready"] is False
    guard.assert_awaited_once()
    evaluator.assert_awaited_once()
    assert guard.await_args.kwargs["action"] == "read_entry_readiness"


def test_unknown_entry_uses_unified_404(monkeypatch) -> None:
    evaluator = AsyncMock(side_effect=EntryReadinessNotFound("missing"))
    http, guard = client(monkeypatch, evaluator)
    response = http.get(
        f"/api/projects/{PROJECT}/workpapers/{WP}/sync/entries/{ENTRY}/readiness"
    )
    assert response.status_code == 404
    assert response.json()["detail"] == ROUTER.EXTERNAL_NOT_FOUND_DETAIL
    guard.assert_awaited_once()


def test_endpoint_has_no_write_side_effect_calls(monkeypatch) -> None:
    evaluator = AsyncMock(return_value=result())
    http, _guard = client(monkeypatch, evaluator)
    response = http.get(
        f"/api/projects/{PROJECT}/workpapers/{WP}/sync/entries/{ENTRY}/readiness"
    )
    assert response.status_code == 200
    kwargs = evaluator.await_args.kwargs
    assert set(kwargs) == {"session", "registry", "project_id", "wp_id", "entry_id"}
