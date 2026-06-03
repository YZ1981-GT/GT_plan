# Feature: custom-workpaper-formula-binding — 组③任务 6.5
"""WorkpaperGenerationService.ensure_working_paper 幂等（先查后建）。"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.workpaper_models import WpSourceType
from app.services.workpaper_generation_service import WorkpaperGenerationService


@pytest.mark.anyio
async def test_ensure_working_paper_idempotent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    project_id = uuid.uuid4()
    wp_index_id = uuid.uuid4()

    mock_index = MagicMock()
    mock_index.wp_code = "CUST-01"
    mock_index.wp_name = "测试自定义底稿"
    mock_index.audit_cycle = "A"
    mock_index.project_id = project_id

    stored_wp: list = []
    exec_calls = 0

    async def fake_execute(_stmt):
        nonlocal exec_calls
        exec_calls += 1
        result = MagicMock()
        if stored_wp:
            result.scalar_one_or_none.return_value = stored_wp[0]
        elif exec_calls == 1:
            result.scalar_one_or_none.return_value = None
        else:
            result.scalar_one_or_none.return_value = mock_index
        return result

    db = AsyncMock()
    db.execute = fake_execute

    def _add(wp):
        stored_wp.append(wp)

    db.add = _add
    db.flush = AsyncMock()

    svc = WorkpaperGenerationService()
    wp1 = await svc.ensure_working_paper(
        db, project_id, wp_index_id, source_type=WpSourceType.manual
    )
    wp2 = await svc.ensure_working_paper(db, project_id, wp_index_id)

    assert wp1 is wp2
    assert len(stored_wp) == 1
    assert stored_wp[0].parsed_data is None
    assert "CUST-01" in stored_wp[0].file_path.replace("\\", "/")


@pytest.mark.anyio
async def test_generate_from_index_endpoint_idempotent():
    """POST /api/workpapers/generate-from-index 两次调用返回同一 working_paper_id。"""
    import uuid as _uuid
    from unittest.mock import AsyncMock, patch

    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_db
    from app.deps import get_current_user
    from app.routers.wp_render_config import router as wp_render_router

    wp_index_id = _uuid.uuid4()
    project_id = _uuid.uuid4()
    wp_id = _uuid.uuid4()

    mock_index = MagicMock()
    mock_index.id = wp_index_id
    mock_index.project_id = project_id
    mock_index.wp_code = "CUST-02"
    mock_index.is_deleted = False

    mock_wp = MagicMock()
    mock_wp.id = wp_id
    mock_wp.file_path = "storage/projects/x/workpapers/A/CUST-02.xlsx"

    class _User:
        id = _uuid.uuid4()
        is_active = True

    app = FastAPI()
    app.include_router(wp_render_router)

    session = AsyncMock()

    async def _db():
        yield session

    async def _user():
        return _User()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user

    with patch(
        "app.services.workpaper_generation_service.workpaper_generation_service.ensure_working_paper",
        new_callable=AsyncMock,
        return_value=mock_wp,
    ) as mock_ensure:
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_index
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r1 = await client.post(
                "/api/workpapers/generate-from-index",
                params={"wp_index_id": str(wp_index_id)},
            )
            r2 = await client.post(
                "/api/workpapers/generate-from-index",
                params={"wp_index_id": str(wp_index_id)},
            )

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["working_paper_id"] == str(wp_id)
        assert mock_ensure.await_count == 2
