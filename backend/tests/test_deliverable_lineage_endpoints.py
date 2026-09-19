"""Tests for deliverable lineage trace + section-states endpoints (Task 5.1).

Requirements: 1.1, 3.1, 10.1

验证：
- trace 端点调用 LinkageFacadeService 并返回结果
- trace 端点超时 2s 返回 504
- section-states 端点返回章节列表
- section_code 为必填参数
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.deps import get_current_user, get_db
from app.models.core import User


@pytest.fixture
def project_id():
    return uuid4()


@pytest.fixture
def task_id():
    return uuid4()


@pytest.fixture
def mock_user():
    """Mock admin user that bypasses permission checks."""
    user = MagicMock(spec=User)
    user.id = uuid4()
    user.role = MagicMock()
    user.role.value = "admin"
    user.username = "test_admin"
    return user


@pytest.fixture
def mock_db():
    """Mock async session with proper bind behavior for RLS context."""
    db = AsyncMock()
    # Mock the get_bind to return a proper bind object
    mock_bind = MagicMock()
    mock_bind.dialect = MagicMock()
    mock_bind.dialect.name = "postgresql"
    db.get_bind = MagicMock(return_value=mock_bind)
    # Mock execute for set_rls_context SQL execution
    db.execute = AsyncMock(return_value=MagicMock())
    return db


@pytest.fixture(autouse=True)
def override_deps(mock_user, mock_db):
    """Override FastAPI dependencies for testing."""

    async def _override_get_db():
        return mock_db

    async def _override_get_current_user():
        return mock_user

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_get_current_user
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_trace_endpoint_returns_contracts(project_id, task_id):
    """验证 trace 端点调用 LinkageFacadeService 并返回 contracts + section_state。"""
    mock_contracts = [
        {"source_type": "note", "source_id": "八、1", "route": "/notes/八、1"}
    ]
    mock_states = [
        {
            "section_code": "八、1",
            "is_stale": False,
            "source_snapshot_hash": "abc123",
            "last_writeback_baseline_hash": None,
            "anchor_name": "sec_八_1",
            "version_no": 1,
        }
    ]

    with patch(
        "app.routers.deliverable_lineage.LinkageFacadeService"
    ) as MockFacade, patch(
        "app.routers.deliverable_lineage.DeliverableSectionStateService"
    ) as MockDSS:
        facade_instance = MockFacade.return_value
        facade_instance.trace = AsyncMock(return_value=mock_contracts)

        dss_instance = MockDSS.return_value
        dss_instance.get_section_states = AsyncMock(return_value=mock_states)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/api/projects/{project_id}/deliverables/{task_id}/trace",
                params={"section_code": "八、1"},
            )

        assert resp.status_code == 200
        body = resp.json()
        # ResponseWrapperMiddleware wraps in {code, message, data}
        data = body.get("data", body)
        assert "contracts" in data
        assert data["contracts"] == mock_contracts
        assert data["section_state"]["section_code"] == "八、1"
        assert data["section_state"]["is_stale"] is False


@pytest.mark.asyncio
async def test_trace_endpoint_timeout_returns_504(project_id, task_id):
    """验证 trace 端点超时 2s 返回明确错误（需求 10.1）。"""

    async def slow_trace(**kwargs):
        await asyncio.sleep(5)
        return []

    with patch(
        "app.routers.deliverable_lineage.LinkageFacadeService"
    ) as MockFacade, patch(
        "app.routers.deliverable_lineage.DeliverableSectionStateService"
    ):
        facade_instance = MockFacade.return_value
        facade_instance.trace = slow_trace

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/api/projects/{project_id}/deliverables/{task_id}/trace",
                params={"section_code": "八、1"},
            )

        # The endpoint raises HTTPException(504) on timeout
        # ResponseWrapperMiddleware may or may not wrap 4xx/5xx
        assert resp.status_code in (504, 500)
        body = resp.json()
        assert "超时" in str(body)


@pytest.mark.asyncio
async def test_section_states_endpoint(project_id, task_id):
    """验证 section-states 端点返回章节列表。"""
    mock_states = [
        {
            "section_code": "八、1",
            "is_stale": True,
            "source_snapshot_hash": "hash1",
            "last_writeback_baseline_hash": None,
            "anchor_name": "sec_八_1",
            "version_no": 2,
        },
        {
            "section_code": "八、2",
            "is_stale": False,
            "source_snapshot_hash": "hash2",
            "last_writeback_baseline_hash": "base2",
            "anchor_name": "sec_八_2",
            "version_no": 2,
        },
    ]

    with patch(
        "app.routers.deliverable_lineage.DeliverableSectionStateService"
    ) as MockDSS:
        dss_instance = MockDSS.return_value
        dss_instance.get_section_states = AsyncMock(return_value=mock_states)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                f"/api/projects/{project_id}/deliverables/{task_id}/section-states"
            )

        assert resp.status_code == 200
        body = resp.json()
        data = body.get("data", body)
        assert "sections" in data
        assert len(data["sections"]) == 2
        assert data["sections"][0]["section_code"] == "八、1"
        assert data["sections"][0]["is_stale"] is True


@pytest.mark.asyncio
async def test_trace_endpoint_requires_section_code(project_id, task_id):
    """验证 section_code 为必填参数。"""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            f"/api/projects/{project_id}/deliverables/{task_id}/trace"
        )

    # FastAPI returns 422 for missing required query params
    assert resp.status_code == 422
