"""G5 导入导出 — 基础契约测试."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.deps import get_current_user
from app.main import app
from app.models.base import UserRole
from app.core.database import get_db
from unittest.mock import AsyncMock


class _FakeUser:
    id = "test-user-id"
    name = "Test User"
    email = "test@example.com"
    role = UserRole.admin


@pytest.fixture(autouse=True)
def override_deps():
    mock_db = AsyncMock()
    mock_db.commit = AsyncMock()
    mock_db.execute = AsyncMock()

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    app.dependency_overrides[get_db] = _override_db
    yield mock_db
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_g5_export_template_g5_7():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/workpapers/test-wp/g5/export-template?sheet=G5-7")
    assert resp.status_code == 200
    assert "spreadsheet" in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_g5_export_template_g5_10_not_found():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/workpapers/test-wp/g5/export-template?sheet=G5-10")
    assert resp.status_code in (400, 422)
