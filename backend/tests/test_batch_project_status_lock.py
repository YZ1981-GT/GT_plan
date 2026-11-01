"""批量建项 status 有界锁等待回归。"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.batch_project_status_lock import (
    BatchPlanStatusBusy,
    STATUS_BUSY_ERROR_CODE,
    with_status_lock_timeout,
)

pytest_plugins = ("tests._batch_project_fixtures",)


@pytest.mark.asyncio
async def test_sqlite_status_lock_wrapper_keeps_original_read(db):
    calls = 0

    async def operation():
        nonlocal calls
        calls += 1
        return "validated"

    assert await with_status_lock_timeout(db, operation, timeout_ms=1) == "validated"
    assert calls == 1


@pytest.mark.asyncio
async def test_status_route_returns_typed_busy_with_retry_after(monkeypatch):
    from app.routers import batch_project as router

    async def busy(*_args, **_kwargs):
        raise BatchPlanStatusBusy("locked")

    monkeypatch.setattr(router, "with_status_lock_timeout", busy)
    actor = SimpleNamespace(id=uuid4(), role=SimpleNamespace(value="admin"))
    with pytest.raises(Exception) as captured:
        await router.get_batch_import_status(
            uuid4(), db=SimpleNamespace(), current_user=actor
        )
    assert getattr(captured.value, "status_code", None) == 503
    assert getattr(captured.value, "detail", {})["error_code"] == STATUS_BUSY_ERROR_CODE
    assert getattr(captured.value, "headers", {})["Retry-After"] == "1"
