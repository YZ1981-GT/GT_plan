"""Property-based tests for QueryCache — advanced-query-module Tasks 12.2 / 12.3 / 12.4.

覆盖三条设计属性（design.md §Correctness Properties）：

- **Property 22: 缓存命中一致性**（Task 12.2）
  Validates: Requirements 12.3
  同一 TTL 窗口内，缓存命中返回的结果与直接查询数据库对同一查询定义得到的结果一致。

- **Property 23: 缓存隔离**（Task 12.3）
  Validates: Requirements 12.5
  相同查询定义但不同 project_id / 不同用户可访问范围，缓存键互不相同、不复用彼此结果。

- **Property 24: 缓存击穿 single-flight**（Task 12.4）
  Validates: Requirements 12.6
  一组针对同一缓存键的并发相同请求（缓存缺失/过期时），底层 DB 查询恰好被发起一次，
  其余并发请求复用该次查询结果，且所有并发请求返回相同结果。

铁律：每条属性 `@settings(max_examples=5)`；redis 全部以 fakeredis.aioredis 隔离，
不触真实基础设施；`app.core.redis.redis_client` 是 QueryCache 唯一的 Redis 依赖入口，
经 patch 注入 fakeredis。
"""

from __future__ import annotations

import asyncio
import json
import os
from unittest.mock import patch

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

import fakeredis.aioredis
import pytest
from hypothesis import given, settings, strategies as st

from app.services.custom_query.query_cache import QueryCache

# patch 目标：QueryCache._get_redis 内 `from app.core.redis import redis_client`
_REDIS_CLIENT = "app.core.redis.redis_client"


# ─── JSON 安全生成器（保证 json round-trip 后严格相等）────────────────────────
_JSON_SCALARS = st.one_of(
    st.integers(min_value=-10_000, max_value=10_000),
    st.text(max_size=12),
    st.booleans(),
    st.none(),
)

# 查询定义：键排序稳定序列化的字典（QueryRequest.cache_def() 的最小形态）
_QUERY_DEF = st.dictionaries(
    st.text(min_size=1, max_size=8),
    st.one_of(_JSON_SCALARS, st.lists(_JSON_SCALARS, max_size=4)),
    max_size=5,
)

# DB 结果 payload：JSON 可序列化（QueryResult.to_payload() 的最小形态）
_DB_PAYLOAD = st.fixed_dictionaries(
    {
        "rows": st.lists(
            st.dictionaries(st.text(min_size=1, max_size=6), _JSON_SCALARS, max_size=4),
            max_size=6,
        ),
        "total": st.integers(min_value=0, max_value=1000),
    }
)

_PROJECT_ID = st.uuids().map(str)
_SCOPE_SIG = st.text(min_size=1, max_size=12)


# ═══════════════════════════════════════════════════════════════════════════
# Property 22: 缓存命中一致性 (Task 12.2)
# Validates: Requirements 12.3
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@settings(max_examples=5)
@given(
    query_def=_QUERY_DEF,
    project_id=_PROJECT_ID,
    scope_sig=_SCOPE_SIG,
    payload=_DB_PAYLOAD,
)
async def test_p22_cache_hit_consistency(query_def, project_id, scope_sig, payload):
    """Feature: advanced-query-module, Property 22: 缓存命中一致性

    同一 TTL 窗口内，缓存命中返回的结果与「直接查询 DB 对同一查询定义」的结果一致：
      - 直查 DB（直接执行 compute）得到 direct。
      - 命中缓存后返回值逐字段等于 direct（即使 DB 之后被改动，窗口内命中仍返回缓存值，
        且该缓存值 == 缓存写入时的直查结果）。
      - 命中路径不重新触达 DB（compute 不再被调用）。

    **Validates: Requirements 12.3**
    """
    redis = fakeredis.aioredis.FakeRedis()
    try:
        with patch(_REDIS_CLIENT, redis):
            # cache_threshold=1：首次 compute 即写缓存，便于在同一窗口内制造命中
            cache = QueryCache(cache_threshold=1)
            key = cache.cache_key(query_def, project_id, scope_sig)

            # 「直接查询 DB」的确定性结果（同一查询定义在窗口内不变）
            direct = json.loads(json.dumps(payload, default=str))

            calls = {"n": 0}

            async def compute():
                calls["n"] += 1
                # 返回 DB 当前状态（首次即为 direct）
                return json.loads(json.dumps(payload, default=str))

            # 第一次：miss → 直查 DB 并写缓存
            first = await cache.get_or_compute(key, compute, ttl=30)
            assert first == direct
            assert calls["n"] == 1

            # 窗口内 DB「被改动」：后续命中必须返回缓存的直查结果，不受此影响
            async def compute_changed():
                calls["n"] += 1
                return {"rows": [{"MUTATED": 1}], "total": -1}

            hit = await cache.get_or_compute(key, compute_changed, ttl=30)

            # 命中一致性：命中值 == 缓存写入时的直查 DB 结果
            assert hit == direct
            # 命中路径未重新触达 DB
            assert calls["n"] == 1
    finally:
        await redis.flushall()
        await redis.aclose()


# ═══════════════════════════════════════════════════════════════════════════
# Property 23: 缓存隔离 (Task 12.3)
# Validates: Requirements 12.5
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@settings(max_examples=5)
@given(
    query_def=_QUERY_DEF,
    project_a=_PROJECT_ID,
    project_b=_PROJECT_ID,
    scope_a=_SCOPE_SIG,
    scope_b=_SCOPE_SIG,
)
async def test_p23_cache_key_isolation(query_def, project_a, project_b, scope_a, scope_b):
    """Feature: advanced-query-module, Property 23: 缓存隔离

    相同查询定义在不同 project_id / 不同可访问范围（scope_sig）下缓存键互不相同：
      - 相同 (query_def, project, scope) → 键确定且相等（可复用）。
      - 仅 project_id 不同 → 键不同（不跨项目复用）。
      - 仅 scope_sig 不同 → 键不同（不跨可访问范围复用）。

    **Validates: Requirements 12.5**
    """
    cache = QueryCache()

    # 确定性：同输入恒等键
    assert cache.cache_key(query_def, project_a, scope_a) == cache.cache_key(
        query_def, project_a, scope_a
    )

    # 不同 project_id → 键不同
    if project_a != project_b:
        assert cache.cache_key(query_def, project_a, scope_a) != cache.cache_key(
            query_def, project_b, scope_a
        )

    # 不同 scope_sig → 键不同
    if scope_a != scope_b:
        assert cache.cache_key(query_def, project_a, scope_a) != cache.cache_key(
            query_def, project_a, scope_b
        )


@pytest.mark.asyncio
@settings(max_examples=5)
@given(
    query_def=_QUERY_DEF,
    project_a=_PROJECT_ID,
    project_b=_PROJECT_ID,
    scope_sig=_SCOPE_SIG,
)
async def test_p23_no_cross_project_reuse(query_def, project_a, project_b, scope_sig):
    """Feature: advanced-query-module, Property 23: 缓存隔离

    行为级隔离：相同查询定义在 project_a 缓存后，project_b 的相同定义请求不复用
    project_a 的缓存结果，而是独立计算自己的结果。

    **Validates: Requirements 12.5**
    """
    from hypothesis import assume

    assume(project_a != project_b)

    redis = fakeredis.aioredis.FakeRedis()
    try:
        with patch(_REDIS_CLIENT, redis):
            cache = QueryCache(cache_threshold=1)
            key_a = cache.cache_key(query_def, project_a, scope_sig)
            key_b = cache.cache_key(query_def, project_b, scope_sig)
            assert key_a != key_b

            value_a = {"rows": [{"owner": "A"}], "total": 1}
            value_b = {"rows": [{"owner": "B"}], "total": 2}

            # project_a：写缓存
            await cache.get_or_compute(key_a, lambda: _const(value_a), ttl=30)
            # project_b：相同查询定义、不同 project → 独立计算 value_b（不复用 A）
            got_b = await cache.get_or_compute(key_b, lambda: _const(value_b), ttl=30)

            assert got_b == value_b
            assert got_b != value_a
    finally:
        await redis.flushall()
        await redis.aclose()


async def _const(value):
    """返回给定常量值的 async compute 回调。"""
    return value


# ═══════════════════════════════════════════════════════════════════════════
# Property 24: 缓存击穿 single-flight (Task 12.4)
# Validates: Requirements 12.6
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
@settings(max_examples=5, deadline=None)
@given(
    query_def=_QUERY_DEF,
    project_id=_PROJECT_ID,
    scope_sig=_SCOPE_SIG,
    n_concurrent=st.integers(min_value=2, max_value=8),
    payload=_DB_PAYLOAD,
)
async def test_p24_single_flight_thundering_herd(
    query_def, project_id, scope_sig, n_concurrent, payload
):
    """Feature: advanced-query-module, Property 24: 缓存击穿 single-flight

    N 路针对同一缓存键的并发相同请求（缓存缺失时）：
      - 底层 DB compute 恰好被发起 1 次（其余并发请求复用该次结果）。
      - 所有并发请求返回相同结果，且等于该次 DB compute 的结果。

    **Validates: Requirements 12.6**
    """
    redis = fakeredis.aioredis.FakeRedis()
    try:
        with patch(_REDIS_CLIENT, redis):
            cache = QueryCache(cache_threshold=1)
            key = cache.cache_key(query_def, project_id, scope_sig)

            direct = json.loads(json.dumps(payload, default=str))
            calls = {"n": 0}

            async def compute():
                calls["n"] += 1
                # 人为延迟，确保 N 路并发在计算窗口内充分重叠（放大击穿风险）
                await asyncio.sleep(0.02)
                return json.loads(json.dumps(payload, default=str))

            results = await asyncio.gather(
                *[
                    cache.get_or_compute(key, compute, ttl=30, singleflight=True)
                    for _ in range(n_concurrent)
                ]
            )

            # DB 恰查一次（single-flight 生效，无击穿）
            assert calls["n"] == 1
            # 所有并发请求返回相同结果，且等于该次 DB compute 结果
            assert all(r == direct for r in results)
    finally:
        await redis.flushall()
        await redis.aclose()
