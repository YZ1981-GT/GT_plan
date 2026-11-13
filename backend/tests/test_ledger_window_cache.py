"""窗口缓存：命中不再查库、键随数据集 / 用户 / 查询变化、Redis 故障时退回直接查库。"""
from __future__ import annotations

import uuid

import pytest

from app.schemas.ledger_window import (
    LedgerWindowPage, LedgerWindowQuery, LedgerWindowResponse, LedgerWindowSummary,
)
from app.services import ledger_window_cache as cache

PID = uuid.uuid4()


def _response(tag: str = "a") -> LedgerWindowResponse:
    summary = LedgerWindowSummary(
        total=1, annual_opening="0.00", annual_opening_signed="0.00", annual_opening_direction="debit",
        range_opening="0.00", range_opening_signed="0.00", range_opening_direction="debit",
        debit_total="1.00", credit_total="0.00", undated_count=0, months=[], warnings=[],
    )
    return LedgerWindowResponse(
        kind="ledger", dataset_id="d", query_fingerprint=tag, entries=[], summary=summary,
        page=LedgerWindowPage(limit=10, page_index=0, start=0, end=0, has_more=False, next_cursor=None),
        extra_columns=[], subtotals=[],
    )


class FakeRedis:
    def __init__(self):
        self.store: dict[str, str] = {}
        self.ttl: dict[str, int] = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.store[key] = value
        self.ttl[key] = ex


class BrokenRedis:
    async def get(self, key):
        raise ConnectionError("down")

    async def set(self, key, value, ex=None):
        raise ConnectionError("down")


class FakeService:
    def __init__(self, dataset):
        self.dataset = dataset
        self.calls = 0

    async def _active_dataset(self, project_id, year):
        return self.dataset

    async def fetch(self, kind, project_id, subject, query):
        self.calls += 1
        return _response(str(self.calls))


def _q(**kw):
    return LedgerWindowQuery(year=2025, account_code="*", **kw)


@pytest.mark.asyncio
async def test_second_call_hits_cache_and_ttl_is_below_cursor_ttl():
    from app.services import ledger_window_cursor
    redis, svc = FakeRedis(), FakeService(uuid.uuid4())
    first = await cache.fetch_window_cached(redis, svc, "ledger", PID, "u1", _q())
    second = await cache.fetch_window_cached(redis, svc, "ledger", PID, "u1", _q())
    assert svc.calls == 1 and first.query_fingerprint == second.query_fingerprint == "1"
    assert all(t < ledger_window_cursor._TTL_SECONDS for t in redis.ttl.values())


@pytest.mark.asyncio
async def test_key_changes_with_dataset_user_and_query():
    redis = FakeRedis()
    svc = FakeService(uuid.uuid4())
    await cache.fetch_window_cached(redis, svc, "ledger", PID, "u1", _q())
    await cache.fetch_window_cached(redis, svc, "ledger", PID, "u2", _q())              # 另一个用户
    await cache.fetch_window_cached(redis, svc, "ledger", PID, "u1", _q(keyword="x"))   # 另一个查询
    svc.dataset = uuid.uuid4()
    await cache.fetch_window_cached(redis, svc, "ledger", PID, "u1", _q())              # 重新导入后数据集变化
    assert svc.calls == 4


@pytest.mark.asyncio
async def test_redis_failure_falls_back_to_database():
    svc = FakeService(uuid.uuid4())
    result = await cache.fetch_window_cached(BrokenRedis(), svc, "ledger", PID, "u1", _q())
    assert result.query_fingerprint == "1" and svc.calls == 1


@pytest.mark.asyncio
async def test_no_redis_goes_straight_to_service():
    svc = FakeService(uuid.uuid4())
    await cache.fetch_window_cached(None, svc, "ledger", PID, "u1", _q())
    assert svc.calls == 1


@pytest.mark.asyncio
async def test_redis_summary_cache_roundtrip_and_failure_tolerance():
    redis = FakeRedis()
    sc = cache.RedisSummaryCache(redis)
    assert await sc.get("k") is None
    await sc.set("k", {"anchor": "1.00", "extra_columns": ["经办人"], "summary": {}})
    assert await sc.get("k") == {"anchor": "1.00", "extra_columns": ["经办人"], "summary": {}}
    assert list(redis.store) == ["ledger:winsum:k"]          # 前缀须与 invalidate_ledger_caches 的 pattern 对得上
    assert redis.ttl["ledger:winsum:k"] == cache.SUMMARY_TTL_SECONDS
    broken = cache.RedisSummaryCache(BrokenRedis())
    assert await broken.get("k") is None
    await broken.set("k", {})                                 # 不抛
