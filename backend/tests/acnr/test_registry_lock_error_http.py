"""ACNR 版本锁治理错误经真实应用与真实 /api/acnr/resolve 返回稳定 409。"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.database import get_db
from app.deps import get_current_user
from app.main import app
from app.routers import acnr as acnr_router
from app.services.acnr.project_registry_lock import RegistryLockError
from app.services.acnr.resolver import VersionInvalidError, VersionNotFoundError


@pytest.mark.parametrize(
    "exc,error_code,text",
    [
        (VersionNotFoundError("20260101000000"), "ACNR_REGISTRY_SNAPSHOT_MISSING", "快照缺失"),
        (VersionInvalidError("20260202000000", "JSON 无法解析"), "ACNR_REGISTRY_SNAPSHOT_INVALID", "快照内容损坏"),
        (RegistryLockError("lock_failed", "无法记录归档时的地址目录版本：数据库拒绝；本次归档未生效",
                           version="20260303000000"), "ACNR_REGISTRY_LOCK_FAILED", "无法记录归档时"),
    ],
)
async def test_real_resolve_route_returns_unwrapped_stable_409(monkeypatch, exc, error_code, text):
    async def _db():
        yield object()

    async def _user():
        return SimpleNamespace(id="test-user")

    async def _allow(*_args, **_kwargs):
        return None

    async def _raise(**_kwargs):
        raise exc

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    monkeypatch.setattr(acnr_router, "check_project_access", _allow)
    monkeypatch.setattr(acnr_router, "full_resolve", _raise)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/acnr/resolve",
                json={"addr_id": "E1/E1-14/C10", "project_id": "00000000-0000-0000-0000-000000000001"},
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["code"] == 409
    assert body["error_code"] == error_code
    assert text in body["message"]
    assert body["version"] == exc.version
    assert "data" not in body, "非 2xx 不得被 ResponseWrapperMiddleware 二次包装"


async def test_resolve_batch_does_not_swallow_governance_error(monkeypatch):
    async def _raise(**_kwargs):
        raise VersionNotFoundError("20260101000000")

    monkeypatch.setattr(acnr_router, "full_resolve", _raise)
    body = acnr_router.AcnrResolveBatchRequest(
        items=[acnr_router.AcnrResolveBatchItem(addr_id="E1/E1-14/C10")]
    )
    with pytest.raises(VersionNotFoundError):
        await acnr_router.acnr_resolve_batch(body=body, _user=object(), db=object())


async def test_addressing_service_propagates_governance_error(monkeypatch):
    from app.services.custom_query import addressing_service

    monkeypatch.setattr(
        addressing_service,
        "full_resolve",
        AsyncMock(side_effect=VersionInvalidError("20260202000000", "损坏")),
    )
    with pytest.raises(VersionInvalidError):
        await addressing_service.AddressingService().resolve_target(
            "E1/E1-14/C10", project_id="00000000-0000-0000-0000-000000000001", db=object()
        )
