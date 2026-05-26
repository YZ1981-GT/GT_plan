"""Tests for GET /api/workpapers/trace endpoint.

Validates: Requirements 3.11.6（报表附注溯源链路）

Strategy: bypass real DB by mocking trace_upstream / trace_downstream service
calls. We focus on router-level behavior:
- 200 OK for each (source, direction) combo
- 422 for missing / invalid params
- 403 for non-admin without project access
- best-effort behavior on internal exceptions
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User, UserRole
from app.routers.wp_trace import router as wp_trace_router
from app.services.wp_trace_service import (
    TraceItem,
    TraceResult,
    _parse_workpaper_identifier,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


ADMIN_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
AUDITOR_USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
PROJECT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def _make_app(*, role: UserRole = UserRole.admin) -> tuple[FastAPI, MagicMock]:
    """Build a FastAPI app with mocked deps. Returns (app, mock_db)."""
    app = FastAPI()
    app.include_router(wp_trace_router)

    mock_db = MagicMock(spec=AsyncSession)
    mock_db.execute = AsyncMock()

    async def _override_db():
        yield mock_db

    user_id = ADMIN_USER_ID if role == UserRole.admin else AUDITOR_USER_ID

    async def _override_user():
        return User(
            id=user_id,
            username="user",
            email="user@test.com",
            hashed_password="x",
            role=role,
            is_active=True,
            is_deleted=False,
        )

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    return app, mock_db


# ─── Service-layer unit tests (pure function, no FastAPI) ────────────────────


class TestParseWorkpaperIdentifier:
    """Test the _parse_workpaper_identifier helper."""

    def test_wp_code_only(self):
        assert _parse_workpaper_identifier("D2") == ("D2", None, None)

    def test_wp_with_sheet_colon(self):
        assert _parse_workpaper_identifier("D2:审定表D2-1") == ("D2", "审定表D2-1", None)

    def test_wp_with_sheet_and_cell_colon(self):
        result = _parse_workpaper_identifier("D2:审定表D2-1:K15")
        assert result == ("D2", "审定表D2-1", "K15")

    def test_wp_with_sheet_and_cell_bang(self):
        result = _parse_workpaper_identifier("D2!审定表D2-1!K15")
        assert result == ("D2", "审定表D2-1", "K15")

    def test_empty_string(self):
        assert _parse_workpaper_identifier("") == ("", None, None)

    def test_whitespace_trimmed(self):
        assert _parse_workpaper_identifier("  D2  ") == ("D2", None, None)


# ─── Router-level tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_trace_upstream_workpaper_200_admin():
    """admin user + valid params → 200 + service called."""
    app, _ = _make_app(role=UserRole.admin)

    fake_result = TraceResult(
        source="workpaper",
        identifier="D2",
        direction="upstream",
        items=[
            TraceItem(wp_code="H1", sheet="折旧分配分析表H1-13", cell="D1", label="折旧分摊"),
        ],
    )

    with patch(
        "app.routers.wp_trace.trace_upstream",
        new=AsyncMock(return_value=fake_result),
    ) as mock_svc, patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                "/api/workpapers/trace",
                params={
                    "source": "workpaper",
                    "identifier": "D2",
                    "direction": "upstream",
                    "project_id": str(PROJECT_ID),
                },
            )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "workpaper"
    assert body["identifier"] == "D2"
    assert body["direction"] == "upstream"
    assert len(body["items"]) == 1
    assert body["items"][0]["wp_code"] == "H1"
    assert body["items"][0]["cell"] == "D1"
    assert mock_svc.await_count == 1


@pytest.mark.asyncio
async def test_trace_downstream_workpaper_200_admin():
    """downstream direction routes to trace_downstream service."""
    app, _ = _make_app(role=UserRole.admin)

    fake_result = TraceResult(
        source="workpaper",
        identifier="H1",
        direction="downstream",
        items=[
            TraceItem(wp_code="K8", sheet="审定表K8-1", cell="D1"),
            TraceItem(wp_code="F5", sheet="营业务成本审定表F5-1", cell="D1"),
        ],
    )

    with patch(
        "app.routers.wp_trace.trace_downstream",
        new=AsyncMock(return_value=fake_result),
    ) as mock_svc, patch(
        "app.routers.wp_trace.trace_upstream",
        new=AsyncMock(return_value=TraceResult(source="x", identifier="x", direction="x")),
    ) as mock_up, patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                "/api/workpapers/trace",
                params={
                    "source": "workpaper",
                    "identifier": "H1",
                    "direction": "downstream",
                    "project_id": str(PROJECT_ID),
                },
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["direction"] == "downstream"
    assert len(body["items"]) == 2
    assert body["items"][0]["wp_code"] == "K8"
    assert mock_svc.await_count == 1
    assert mock_up.await_count == 0  # downstream path should NOT call upstream


@pytest.mark.asyncio
async def test_trace_upstream_report_200():
    """source=report + upstream direction → 200."""
    app, _ = _make_app(role=UserRole.admin)

    fake_result = TraceResult(
        source="report",
        identifier="BS-007",
        direction="upstream",
        items=[TraceItem(wp_code="D2", label="应收账款主底稿")],
    )

    with patch(
        "app.routers.wp_trace.trace_upstream",
        new=AsyncMock(return_value=fake_result),
    ), patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                "/api/workpapers/trace",
                params={
                    "source": "report",
                    "identifier": "BS-007",
                    "direction": "upstream",
                    "project_id": str(PROJECT_ID),
                },
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "report"
    assert body["identifier"] == "BS-007"


@pytest.mark.asyncio
async def test_trace_upstream_disclosure_200():
    """source=disclosure + upstream direction → 200."""
    app, _ = _make_app(role=UserRole.admin)

    fake_result = TraceResult(
        source="disclosure",
        identifier="五-1-1",
        direction="upstream",
        items=[],
    )

    with patch(
        "app.routers.wp_trace.trace_upstream",
        new=AsyncMock(return_value=fake_result),
    ), patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                "/api/workpapers/trace",
                params={
                    "source": "disclosure",
                    "identifier": "五-1-1",
                    "direction": "upstream",
                    "project_id": str(PROJECT_ID),
                },
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []


@pytest.mark.asyncio
async def test_trace_downstream_report_returns_empty():
    """source=report + downstream direction → items=[] (报表是终点)."""
    app, _ = _make_app(role=UserRole.admin)

    fake_result = TraceResult(
        source="report",
        identifier="BS-007",
        direction="downstream",
        items=[],
    )

    with patch(
        "app.routers.wp_trace.trace_downstream",
        new=AsyncMock(return_value=fake_result),
    ), patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                "/api/workpapers/trace",
                params={
                    "source": "report",
                    "identifier": "BS-007",
                    "direction": "downstream",
                    "project_id": str(PROJECT_ID),
                },
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []


# ─── 422 / validation tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_trace_422_missing_source():
    app, _ = _make_app()
    with patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                "/api/workpapers/trace",
                params={
                    "identifier": "D2",
                    "direction": "upstream",
                    "project_id": str(PROJECT_ID),
                },
            )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_trace_422_missing_identifier():
    app, _ = _make_app()
    with patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                "/api/workpapers/trace",
                params={
                    "source": "workpaper",
                    "direction": "upstream",
                    "project_id": str(PROJECT_ID),
                },
            )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_trace_422_missing_direction():
    app, _ = _make_app()
    with patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                "/api/workpapers/trace",
                params={
                    "source": "workpaper",
                    "identifier": "D2",
                    "project_id": str(PROJECT_ID),
                },
            )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_trace_422_missing_project_id():
    app, _ = _make_app()
    with patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                "/api/workpapers/trace",
                params={
                    "source": "workpaper",
                    "identifier": "D2",
                    "direction": "upstream",
                },
            )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_trace_422_invalid_source():
    app, _ = _make_app()
    with patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                "/api/workpapers/trace",
                params={
                    "source": "invalid_value",
                    "identifier": "D2",
                    "direction": "upstream",
                    "project_id": str(PROJECT_ID),
                },
            )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_trace_422_invalid_direction():
    app, _ = _make_app()
    with patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                "/api/workpapers/trace",
                params={
                    "source": "workpaper",
                    "identifier": "D2",
                    "direction": "sideways",
                    "project_id": str(PROJECT_ID),
                },
            )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_trace_422_empty_identifier():
    app, _ = _make_app()
    with patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                "/api/workpapers/trace",
                params={
                    "source": "workpaper",
                    "identifier": "   ",
                    "direction": "upstream",
                    "project_id": str(PROJECT_ID),
                },
            )
    assert resp.status_code == 422


# ─── 403 RBAC test ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_trace_403_for_non_admin_without_project_access():
    """auditor without project_users record → 403."""
    app, mock_db = _make_app(role=UserRole.auditor)

    # require_project_access queries project_users via db.execute
    # → return None to trigger 403
    fake_result = MagicMock()
    fake_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=fake_result)

    with patch("app.deps.set_rls_context", new=AsyncMock()), \
         patch("app.deps._get_cached_permission", new=AsyncMock(return_value=None)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                "/api/workpapers/trace",
                params={
                    "source": "workpaper",
                    "identifier": "D2",
                    "direction": "upstream",
                    "project_id": str(PROJECT_ID),
                },
            )

    assert resp.status_code == 403


# ─── best-effort behavior on internal exception ──────────────────────────────


@pytest.mark.asyncio
async def test_trace_returns_empty_items_on_service_exception():
    """If service throws, return 200 with items=[] (best-effort)."""
    app, _ = _make_app(role=UserRole.admin)

    with patch(
        "app.routers.wp_trace.trace_upstream",
        new=AsyncMock(side_effect=RuntimeError("DB error")),
    ), patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                "/api/workpapers/trace",
                params={
                    "source": "workpaper",
                    "identifier": "D2",
                    "direction": "upstream",
                    "project_id": str(PROJECT_ID),
                },
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["source"] == "workpaper"
    assert body["identifier"] == "D2"
