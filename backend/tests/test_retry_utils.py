"""Sprint 10.37: retry_on_serialization_failure 装饰器单元测试。"""

from __future__ import annotations

import asyncio

import pytest

from app.services.retry_utils import retry_on_serialization_failure


class _FakeSerializationError(Exception):
    """模拟 asyncpg.SerializationError（按 class name 识别）。"""

    pgcode = "40001"


class _FakeDeadlockError(Exception):
    pgcode = "40P01"


class _FakeOtherError(Exception):
    pgcode = "22001"  # string_data_right_truncation，不应重试


@pytest.mark.asyncio
async def test_success_first_try_no_retry():
    calls = {"n": 0}

    @retry_on_serialization_failure(max_retries=3)
    async def ok() -> str:
        calls["n"] += 1
        return "ok"

    assert await ok() == "ok"
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_retries_on_serialization_failure():
    calls = {"n": 0}

    @retry_on_serialization_failure(max_retries=3, initial_delay_ms=1)
    async def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise _FakeSerializationError("deadlock")
        return "after-retry"

    assert await flaky() == "after-retry"
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_retries_exhausted_raises_last():
    calls = {"n": 0}

    @retry_on_serialization_failure(max_retries=2, initial_delay_ms=1)
    async def always_fails() -> None:
        calls["n"] += 1
        raise _FakeSerializationError("persistent")

    with pytest.raises(_FakeSerializationError):
        await always_fails()
    assert calls["n"] == 3  # 1 first + 2 retries


@pytest.mark.asyncio
async def test_non_serialization_error_not_retried():
    calls = {"n": 0}

    @retry_on_serialization_failure(max_retries=3, initial_delay_ms=1)
    async def wrong_error() -> None:
        calls["n"] += 1
        raise _FakeOtherError("truncate")

    with pytest.raises(_FakeOtherError):
        await wrong_error()
    assert calls["n"] == 1  # 不应重试


@pytest.mark.asyncio
async def test_deadlock_also_retried():
    calls = {"n": 0}

    @retry_on_serialization_failure(max_retries=2, initial_delay_ms=1)
    async def deadlock_then_ok() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise _FakeDeadlockError("deadlock detected")
        return "recovered"

    assert await deadlock_then_ok() == "recovered"
    assert calls["n"] == 2
