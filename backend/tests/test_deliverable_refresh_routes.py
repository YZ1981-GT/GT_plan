"""交付件增量刷新路由（spec deliverable-trio-generation-accuracy §7.2）。

- 路由必须提交：get_db 不自动提交，原实现漏了 ⇒ 新版本文件落了盘、版本记录与「清过期」随会话关闭回滚；
- refresh-stale 不再「>100 节转异步」：那条分支建的 export_jobs_v2 任务没有任何 worker 处理（静默不执行）。
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.deps import get_current_user, get_db
from app.main import app
from app.models.core import User


def _mock_db(stale_count: int = 0):
    db = AsyncMock()
    bind = MagicMock()
    bind.dialect.name = "postgresql"
    db.get_bind = MagicMock(return_value=bind)

    async def _execute(stmt, params=None):
        result = MagicMock()
        result.first.return_value = ("editing", "disclosure_notes")
        result.all.return_value = []
        result.scalar_one_or_none.return_value = None
        scalars = MagicMock()
        scalars.all.return_value = []
        result.scalars.return_value = scalars
        return result

    db.execute = AsyncMock(side_effect=_execute)
    return db


def _user():
    user = MagicMock(spec=User)
    user.id = uuid.uuid4()
    user.username = "admin"
    user.role = MagicMock()
    user.role.value = "admin"
    return user


_RESULT = {"version_no": 5, "refreshed": ["八、1"], "skipped": [], "requires_confirm": False,
           "pending_confirm_sections": [], "messages": []}


@pytest.mark.asyncio
@pytest.mark.parametrize("path,body,method", [
    ("refresh-section", {"year": 2025, "section_code": "八、1", "confirm_overwrite": True}, "refresh_section"),
    ("refresh-stale", {"year": 2025, "confirm_overwrite": True}, "refresh_all_stale_sections"),
])
async def test_refresh_routes_commit_and_never_delegate_to_async_job(path, body, method):
    db = _mock_db()
    stale_states = [{"section_code": f"八、{i}", "is_stale": True} for i in range(1, 150)]
    app.dependency_overrides[get_db] = lambda: db
    user = _user()
    app.dependency_overrides[get_current_user] = lambda: user
    project_id, task_id = uuid.uuid4(), uuid.uuid4()
    try:
        with patch("app.routers.deliverable_lineage._require_capability", new=AsyncMock()), \
                patch("app.services.deliverable_section_state_service.DeliverableSectionStateService.get_section_states",
                      new=AsyncMock(return_value=stale_states)), \
                patch(f"app.services.deliverable_refresh_service.DeliverableRefreshService.{method}",
                      new=AsyncMock(return_value=_RESULT)) as refresh, \
                patch("app.services.export_job_service.ExportJobService.create_job", new=AsyncMock()) as create_job:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(f"/api/projects/{project_id}/deliverables/{task_id}/{path}", json=body)
        assert resp.status_code == 200, resp.text
        refresh.assert_awaited_once()
        create_job.assert_not_awaited()  # 149 个过期章节也同步执行，不建无人处理的异步任务
        db.commit.assert_awaited()
        payload = resp.json()
        data = payload.get("data", payload)
        assert data["refreshed"] == ["八、1"] and data["messages"] == []
    finally:
        app.dependency_overrides.clear()
