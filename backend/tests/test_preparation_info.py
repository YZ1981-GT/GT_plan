# Feature: custom-workpaper-formula-binding — 组④任务 7.6
"""_build_preparation_info / preparation-info 端点：7 字段、无 accounting_period。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.deps import get_current_user
from app.routers.wp_render_config import _build_preparation_info, router as wp_render_router

REQUIRED_KEYS = {
    "entity_name",
    "period_end",
    "preparer",
    "prep_date",
    "reviewer",
    "review_date",
    "index_no",
}


@pytest.mark.anyio
async def test_build_preparation_info_no_accounting_period():
    project_id = uuid.uuid4()
    wp_id = uuid.uuid4()

    db = AsyncMock()

    async def fake_execute(stmt, params=None):
        r = MagicMock()
        sql = str(stmt)
        if "projects" in sql:
            r.first.return_value = ("致同测试公司", datetime(2025, 12, 31, tzinfo=timezone.utc))
        elif "project_assignments" in sql:

            class _Rows:
                def __iter__(self):
                    return iter([("preparer", "张三"), ("reviewer", "李四")])

            return _Rows()
        elif "working_paper" in sql.lower() or "wp_index" in sql.lower():
            r.first.return_value = (datetime(2026, 1, 15, tzinfo=timezone.utc), "D1-1")
        else:
            r.first.return_value = None
        return r

    db.execute = fake_execute

    info = await _build_preparation_info(db, project_id, wp_id)

    assert set(info.keys()) == REQUIRED_KEYS
    assert "accounting_period" not in info
    assert info["entity_name"] == "致同测试公司"
    assert info["period_end"] == "2025-12-31"
    assert info["preparer"] == "张三"
    assert info["reviewer"] == "李四"
    assert info["index_no"] == "D1-1"
    assert info["prep_date"] == "2026-01-15"


@pytest.mark.anyio
async def test_build_preparation_info_null_period_end():
    project_id = uuid.uuid4()
    wp_id = uuid.uuid4()
    db = AsyncMock()

    async def fake_execute(stmt, params=None):
        r = MagicMock()
        sql = str(stmt)
        if "projects" in sql:
            r.first.return_value = ("某公司", None)
        elif "project_assignments" in sql:
            r.__iter__ = lambda self: iter([])
        else:
            r.first.return_value = (None, "")
        return r

    db.execute = fake_execute
    info = await _build_preparation_info(db, project_id, wp_id)

    assert info["period_end"] == ""
    assert info["entity_name"] == "某公司"


@pytest.mark.anyio
async def test_preparation_info_endpoint():
    wp_id = uuid.uuid4()
    project_id = uuid.uuid4()

    class _User:
        id = uuid.uuid4()
        is_active = True

    mock_wp = MagicMock()
    mock_wp.project_id = project_id

    app = FastAPI()
    app.include_router(wp_render_router)
    session = AsyncMock()

    async def _db():
        yield session

    async def _user():
        return _User()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user

    expected = {k: "—" if k != "entity_name" else "测试单位" for k in REQUIRED_KEYS}
    expected["entity_name"] = "测试单位"

    with patch(
        "app.routers.wp_render_config._build_preparation_info",
        new_callable=AsyncMock,
        return_value=expected,
    ):
        with patch(
            "app.routers.wp_render_config.sa.select",
        ):
            scalar = MagicMock()
            scalar.scalar_one_or_none.return_value = mock_wp
            session.execute = AsyncMock(return_value=scalar)

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.get(f"/api/workpapers/{wp_id}/preparation-info")

    assert resp.status_code == 200
    body = resp.json()
    assert "accounting_period" not in body
    assert set(body.keys()) == REQUIRED_KEYS

