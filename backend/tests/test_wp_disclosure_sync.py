"""Tests for POST /api/projects/{pid}/disclosure-notes/sync-from-workpaper.

Validates: Requirements 3.11.5 §4.2（附注双源问题）+ design §12.1 推荐选项 A

Strategy: bypass real DB by mocking `sync_from_workpaper` service + `get_db` dep,
so we focus on router-level behavior (status codes, RBAC, schema validation).
A separate service-level integration test covers the create/update branches.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User, UserRole
from app.routers.wp_disclosure_sync import router as wp_disclosure_sync_router

# ─── Fixtures ────────────────────────────────────────────────────────────────


ADMIN_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
AUDITOR_USER_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
PROJECT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
WP_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def _make_app(*, role: UserRole = UserRole.admin) -> tuple[FastAPI, MagicMock]:
    """Build a FastAPI app with mocked deps. Returns (app, mock_db)."""
    app = FastAPI()
    app.include_router(wp_disclosure_sync_router)

    mock_db = MagicMock(spec=AsyncSession)
    mock_db.execute = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()
    mock_db.add = MagicMock()

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


class TestServiceHelpers:
    """Direct tests for service-level helper functions."""

    def test_count_rows_synced_empty(self):
        from app.services.wp_disclosure_sync_service import _count_rows_synced
        assert _count_rows_synced(None) == 0
        assert _count_rows_synced({}) == 0

    def test_count_rows_synced_with_data(self):
        from app.services.wp_disclosure_sync_service import _count_rows_synced
        assert _count_rows_synced({"a": [1, 2, 3]}) == 3
        assert _count_rows_synced({"a": [1, 2], "b": [{"x": 1}]}) == 3

    def test_count_rows_synced_skips_non_lists(self):
        from app.services.wp_disclosure_sync_service import _count_rows_synced
        assert _count_rows_synced({"a": "not_a_list", "b": [1]}) == 1

    def test_derive_section_title_with_space(self):
        from app.services.wp_disclosure_sync_service import _derive_section_title
        assert _derive_section_title("五-1-1 应收账款") == "应收账款"
        assert _derive_section_title("六-2 存货") == "存货"

    def test_derive_section_title_no_space(self):
        from app.services.wp_disclosure_sync_service import _derive_section_title
        assert _derive_section_title("五-1-1") == "五-1-1"
        assert _derive_section_title("") == ""


# ─── Router-level tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sync_happy_path_admin(monkeypatch):
    """admin user + valid payload → 200 + service called with correct args."""
    app, _mock_db = _make_app(role=UserRole.admin)

    payload = {
        "wp_id": str(WP_ID),
        "sheet_name": "应收账款附注C",
        "section_id": "五-1-1 应收账款",
        "sub_table_data": {
            "subtable_aging": [{"v": 1}, {"v": 2}],
            "subtable_top5": [{"v": 3}],
        },
        "current_standard": "soe_standalone",
        "year": 2025,
    }

    fake_now = datetime(2026, 5, 26, 10, 0, 0, tzinfo=timezone.utc)
    fake_result = {
        "success": True,
        "section_id": "五-1-1 应收账款",
        "synced_at": fake_now.isoformat(),
        "rows_synced": 3,
        "created": True,
    }

    with patch(
        "app.routers.wp_disclosure_sync.sync_from_workpaper",
        new=AsyncMock(return_value=fake_result),
    ) as mock_svc, \
         patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/projects/{PROJECT_ID}/disclosure-notes/sync-from-workpaper",
                json=payload,
            )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["section_id"] == "五-1-1 应收账款"
    assert body["rows_synced"] == 3
    assert body["created"] is True
    assert body["synced_at"] == fake_now.isoformat()

    # Verify service called with kwargs
    assert mock_svc.await_count == 1
    kwargs = mock_svc.await_args.kwargs
    assert kwargs["wp_id"] == WP_ID
    assert kwargs["section_id"] == "五-1-1 应收账款"
    assert kwargs["sheet_name"] == "应收账款附注C"
    assert kwargs["current_standard"] == "soe_standalone"
    assert kwargs["year"] == 2025
    assert kwargs["user"].id == ADMIN_USER_ID


@pytest.mark.asyncio
async def test_sync_422_when_section_id_missing():
    """Pydantic catches missing required field → 422."""
    app, _mock_db = _make_app()

    payload = {
        "wp_id": str(WP_ID),
        "sheet_name": "C-sheet",
        # missing section_id
        "sub_table_data": {},
        "current_standard": "soe_standalone",
    }

    with patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/projects/{PROJECT_ID}/disclosure-notes/sync-from-workpaper",
                json=payload,
            )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_sync_422_when_section_id_empty():
    """min_length=1 rejects empty string → 422."""
    app, _mock_db = _make_app()
    payload = {
        "wp_id": str(WP_ID),
        "sheet_name": "C-sheet",
        "section_id": "",
        "sub_table_data": {},
        "current_standard": "soe_standalone",
    }

    with patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/projects/{PROJECT_ID}/disclosure-notes/sync-from-workpaper",
                json=payload,
            )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_sync_422_when_section_id_blank_passed_to_service():
    """Whitespace-only section_id passes Pydantic min_length but service rejects → 422."""
    app, _mock_db = _make_app()
    payload = {
        "wp_id": str(WP_ID),
        "sheet_name": "C-sheet",
        "section_id": "   ",
        "sub_table_data": {},
        "current_standard": "soe_standalone",
    }

    async def _raise(*args, **kwargs):
        raise ValueError("section_id 不能为空")

    with patch(
        "app.routers.wp_disclosure_sync.sync_from_workpaper",
        new=AsyncMock(side_effect=_raise),
    ), patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/projects/{PROJECT_ID}/disclosure-notes/sync-from-workpaper",
                json=payload,
            )

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_sync_422_when_wp_id_invalid():
    """Invalid wp_id (not a UUID) → 422 from Pydantic."""
    app, _mock_db = _make_app()
    payload = {
        "wp_id": "not-a-uuid",
        "sheet_name": "C-sheet",
        "section_id": "五-1-1",
        "sub_table_data": {},
        "current_standard": "soe_standalone",
    }

    with patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/projects/{PROJECT_ID}/disclosure-notes/sync-from-workpaper",
                json=payload,
            )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_sync_403_for_non_admin_without_project_access():
    """auditor without project_users record → 403."""
    app, mock_db = _make_app(role=UserRole.auditor)

    # Mock DB execute to return no project_users row (→ 403)
    fake_result = MagicMock()
    fake_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=fake_result)

    payload = {
        "wp_id": str(WP_ID),
        "sheet_name": "C-sheet",
        "section_id": "五-1-1 应收账款",
        "sub_table_data": {},
        "current_standard": "soe_standalone",
    }

    with patch("app.deps.set_rls_context", new=AsyncMock()), \
         patch("app.deps._get_cached_permission", new=AsyncMock(return_value=None)):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/projects/{PROJECT_ID}/disclosure-notes/sync-from-workpaper",
                json=payload,
            )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_sync_403_for_readonly_user():
    """Non-admin user with cached readonly permission → 403."""
    app, _mock_db = _make_app(role=UserRole.auditor)

    payload = {
        "wp_id": str(WP_ID),
        "sheet_name": "C-sheet",
        "section_id": "五-1-1 应收账款",
        "sub_table_data": {},
        "current_standard": "soe_standalone",
    }

    # 模拟 Redis 缓存返回 readonly（require_project_access('edit') 应拒绝）
    with patch("app.deps.set_rls_context", new=AsyncMock()), \
         patch(
             "app.deps._get_cached_permission",
             new=AsyncMock(return_value="readonly"),
         ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/projects/{PROJECT_ID}/disclosure-notes/sync-from-workpaper",
                json=payload,
            )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_sync_with_edit_user_succeeds():
    """Non-admin user with cached edit permission → 200."""
    app, _mock_db = _make_app(role=UserRole.auditor)

    payload = {
        "wp_id": str(WP_ID),
        "sheet_name": "C-sheet",
        "section_id": "五-1-1 应收账款",
        "sub_table_data": {"st1": [{"v": 1}]},
        "current_standard": "soe_standalone",
    }

    fake_result = {
        "success": True,
        "section_id": "五-1-1 应收账款",
        "synced_at": "2026-05-26T10:00:00+00:00",
        "rows_synced": 1,
        "created": True,
    }

    with patch(
        "app.routers.wp_disclosure_sync.sync_from_workpaper",
        new=AsyncMock(return_value=fake_result),
    ), patch("app.deps.set_rls_context", new=AsyncMock()), \
       patch(
           "app.deps._get_cached_permission",
           new=AsyncMock(return_value="edit"),
       ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/projects/{PROJECT_ID}/disclosure-notes/sync-from-workpaper",
                json=payload,
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] is True


@pytest.mark.asyncio
async def test_sync_500_on_unexpected_error():
    """Unexpected service exception → 500 with message."""
    app, _mock_db = _make_app(role=UserRole.admin)

    async def _raise_generic(*args, **kwargs):
        raise RuntimeError("DB connection lost")

    payload = {
        "wp_id": str(WP_ID),
        "sheet_name": "C-sheet",
        "section_id": "五-1-1 应收账款",
        "sub_table_data": {},
        "current_standard": "soe_standalone",
    }

    with patch(
        "app.routers.wp_disclosure_sync.sync_from_workpaper",
        new=AsyncMock(side_effect=_raise_generic),
    ), patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/projects/{PROJECT_ID}/disclosure-notes/sync-from-workpaper",
                json=payload,
            )

    assert resp.status_code == 500
    assert "DB connection lost" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_sync_year_optional():
    """payload omitting year is accepted (service applies default)."""
    app, _mock_db = _make_app()

    payload = {
        "wp_id": str(WP_ID),
        "sheet_name": "C-sheet",
        "section_id": "五-1-1 应收账款",
        "sub_table_data": {},
        "current_standard": "soe_standalone",
        # year intentionally omitted
    }

    fake_result = {
        "success": True,
        "section_id": "五-1-1 应收账款",
        "synced_at": "2026-05-26T10:00:00+00:00",
        "rows_synced": 0,
        "created": True,
    }

    with patch(
        "app.routers.wp_disclosure_sync.sync_from_workpaper",
        new=AsyncMock(return_value=fake_result),
    ) as mock_svc, patch("app.deps.set_rls_context", new=AsyncMock()):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                f"/api/projects/{PROJECT_ID}/disclosure-notes/sync-from-workpaper",
                json=payload,
            )

    assert resp.status_code == 200
    # year passed through as None
    assert mock_svc.await_args.kwargs["year"] is None
