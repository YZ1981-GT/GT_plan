"""无 worker 时治理上传不得把 staged 202 当作成功返回。"""
from __future__ import annotations

import importlib
import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.database import get_db
from app.deps import get_current_user

attachments_router = importlib.import_module(
    "app.routers.evidence_governance.attachments_router"
)


@pytest.mark.asyncio
async def test_async_finalize_is_rejected_before_gateway_or_file_read(monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    app.include_router(attachments_router.router)

    async def _db():
        yield object()

    async def _user():
        return type("User", (), {"id": uuid.uuid4(), "role": "auditor"})()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    gateway_called = False

    def _gateway(_db):
        nonlocal gateway_called
        gateway_called = True
        raise AssertionError("拒绝异步模式前不得构造网关")

    monkeypatch.setattr(attachments_router, "_build_gateway", _gateway)

    async def _allow(*_args, **_kwargs):
        return None

    permission = AsyncMock(side_effect=_allow)
    monkeypatch.setattr(attachments_router, "assert_project_permission", permission)
    url = f"/api/projects/{uuid.uuid4()}/years/2025/evidence/attachments"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            url,
            data={"synchronous_finalize": "false"},
            files={"file": ("evidence.pdf", b"%PDF-never-read", "application/pdf")},
        )

    assert response.status_code == 503
    assert response.json()["detail"]["error_code"] == "ASYNC_FINALIZE_UNAVAILABLE"
    permission.assert_awaited_once()
    assert gateway_called is False
