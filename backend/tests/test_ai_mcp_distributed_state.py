"""MCP 配额与撤销在多 worker 间共享 Redis 权威状态。"""

import asyncio
from uuid import uuid4

import pytest

from app.services.ai_chat import mcp_budget, mcp_token


class FakeRedis:
    def __init__(self):
        self.hashes: dict[str, dict[str, int | str]] = {}
        self.values: dict[str, str] = {}
        self.lock = asyncio.Lock()

    async def eval(self, script, _keys, key, *args):
        async with self.lock:
            row = self.hashes.setdefault(key, {"calls": 0, "bytes": 0})
            if "HINCRBY" not in script:
                calls = int(row["calls"])
                return [-1, calls] if calls >= int(args[0]) else [1, calls]
            max_calls, response_bytes, max_bytes, _ttl = map(int, args)
            calls = int(row["calls"])
            total = int(row["bytes"])
            if calls >= max_calls:
                return [-1, calls, total]
            if response_bytes > max_bytes:
                return [-2, calls, total]
            row["calls"] = calls + 1
            row["bytes"] = total + response_bytes
            return [1, calls + 1, total + response_bytes]

    async def hmget(self, key, *fields):
        row = self.hashes.get(key, {})
        return [row.get(field) for field in fields]

    async def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

    async def hset(self, key, mapping):
        self.hashes.setdefault(key, {}).update(mapping)

    async def expire(self, *_args):
        return True

    async def set(self, key, value, **_kwargs):
        self.values[key] = value

    async def exists(self, *keys):
        return sum(1 for key in keys if key in self.values)

    async def delete(self, key):
        self.hashes.pop(key, None)
        self.values.pop(key, None)


@pytest.mark.asyncio
async def test_two_workers_share_one_atomic_call_budget(monkeypatch) -> None:
    redis = FakeRedis()
    monkeypatch.setattr(mcp_budget, "_redis_client", lambda: _async_value(redis))
    monkeypatch.setattr(mcp_budget.settings, "AI_MCP_MAX_CALLS_PER_RUN", 1)
    monkeypatch.setattr(mcp_budget.settings, "AI_MCP_MAX_BYTES_PER_CALL", 1024)
    run_id = uuid4()
    results = await asyncio.gather(
        mcp_budget.distributed_check_and_consume(mcp_budget.McpBudgetTracker(), run_id, response_bytes=10),
        mcp_budget.distributed_check_and_consume(mcp_budget.McpBudgetTracker(), run_id, response_bytes=20),
        return_exceptions=True,
    )
    assert sum(isinstance(result, mcp_budget.McpBudget) for result in results) == 1
    assert sum(isinstance(result, mcp_budget.McpBudgetExceeded) for result in results) == 1
    status = await mcp_budget.distributed_get_or_create(mcp_budget.McpBudgetTracker(), run_id)
    assert status.calls_used == 1


@pytest.mark.asyncio
async def test_revocation_is_visible_to_another_service_instance(monkeypatch) -> None:
    redis = FakeRedis()
    monkeypatch.setattr(mcp_token, "_revocation_redis", lambda: _async_value(redis))
    service_a = mcp_token.McpTokenService()
    service_b = mcp_token.McpTokenService()
    scoped = service_a.create_token(
        user_id=uuid4(), project_id=uuid4(), run_id=uuid4(), role="auditor",
        cycle_scope=frozenset({"D"}), ttl_seconds=60,
    )
    await mcp_token.register_token_distributed(scoped)
    assert await mcp_token.token_revoked_distributed(service_b, scoped.payload) is False
    await mcp_token.revoke_token_distributed(service_a, scoped.payload.token_id)
    assert await mcp_token.token_revoked_distributed(service_b, scoped.payload) is True


@pytest.mark.asyncio
async def test_run_revocation_invalidates_all_child_tokens(monkeypatch) -> None:
    redis = FakeRedis()
    monkeypatch.setattr(mcp_token, "_revocation_redis", lambda: _async_value(redis))
    service = mcp_token.McpTokenService()
    root = service.create_token(
        user_id=uuid4(), project_id=uuid4(), run_id=uuid4(), role="manager",
        cycle_scope=frozenset({"D", "E"}), ttl_seconds=60,
    )
    child = service.create_child_token(root.payload, narrowed_scope=frozenset({"D"}))
    await mcp_token.revoke_run_distributed(service, root.payload.run_id)
    assert await mcp_token.token_revoked_distributed(mcp_token.McpTokenService(), root.payload)
    assert await mcp_token.token_revoked_distributed(mcp_token.McpTokenService(), child.payload)


async def _async_value(value):
    return value


@pytest.mark.asyncio
async def test_token_revoke_rejects_other_user(monkeypatch) -> None:
    redis = FakeRedis()
    monkeypatch.setattr(mcp_token, "_revocation_redis", lambda: _async_value(redis))
    service = mcp_token.McpTokenService()
    scoped = service.create_token(
        user_id=uuid4(), project_id=uuid4(), run_id=uuid4(), role="auditor",
        cycle_scope=frozenset(), ttl_seconds=60,
    )
    await mcp_token.register_token_distributed(scoped)
    with pytest.raises(mcp_token.McpTokenScopeMismatch):
        await mcp_token.revoke_token_for_user_distributed(
            service, scoped.payload.token_id, user_id=uuid4()
        )
    assert await mcp_token.token_revoked_distributed(service, scoped.payload) is False
