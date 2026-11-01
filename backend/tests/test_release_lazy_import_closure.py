"""最新远端中被异常吞掉的 lazy import 必须真实调用现有 API。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, call
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_formula_reverse_index_uses_platform_redis_module(monkeypatch):
    import app.services.formula_reverse_index as reverse_index

    redis = SimpleNamespace(
        get=AsyncMock(return_value=b"7"),
        incr=AsyncMock(),
    )
    get_redis = AsyncMock(return_value=redis)
    monkeypatch.setattr("app.core.redis.get_redis", get_redis)

    assert await reverse_index._remote_version() == 7
    await reverse_index._incr_remote_version()

    assert get_redis.await_count == 2
    redis.get.assert_awaited_once_with("formula:reverse_index:version")
    redis.incr.assert_awaited_once_with("formula:reverse_index:version")


@pytest.mark.asyncio
async def test_formula_outbox_stale_propagation_uses_report_uris(monkeypatch):
    from app.services.formula_settings.outbox import (
        _stale_engine_for_formula_change,
    )
    from app.services.stale_propagation_engine import stale_engine

    on_change = AsyncMock(return_value={"affected": [], "total": 0})
    monkeypatch.setattr(stale_engine, "on_change", on_change)
    monkeypatch.setattr(
        "app.services.formula_reverse_index.invalidate_reverse_index",
        lambda: None,
    )
    project_id = uuid4()

    await _stale_engine_for_formula_change(
        SimpleNamespace(), project_id, 2025, ["BS-002", "BS-001", "BS-002"]
    )

    assert on_change.await_args_list == [
        call("REPORT:BS-001::", project_id, 2025),
        call("REPORT:BS-002::", project_id, 2025),
    ]


@pytest.mark.asyncio
async def test_formula_outbox_propagation_failure_is_retryable(monkeypatch):
    from app.services.formula_settings.outbox import (
        _stale_engine_for_formula_change,
    )
    from app.services.stale_propagation_engine import stale_engine

    monkeypatch.setattr(
        "app.services.formula_reverse_index.invalidate_reverse_index",
        lambda: None,
    )
    monkeypatch.setattr(
        stale_engine,
        "on_change",
        AsyncMock(side_effect=RuntimeError("stale write failed")),
    )

    with pytest.raises(RuntimeError, match="stale write failed"):
        await _stale_engine_for_formula_change(
            SimpleNamespace(), uuid4(), 2025, ["BS-001"]
        )
