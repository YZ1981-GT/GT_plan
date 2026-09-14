"""Property test P28 — 审计节流策略（advanced-query-module Task 15.5）

Feature: advanced-query-module, Property 28: 审计节流策略
Validates: Requirements 14.4

*For any* 操作序列，每次回写与每次跨 sheet 溯源都产生恰好一条审计记录（不节流）；
而同一 60 秒窗口内的多次查询执行聚合为恰好一条节流审计记录。

策略（mirror test_advanced_query_audit_helper.py）：
- fakeredis 提供 should_record 的分布式节流后端；
- 捕获 audit_logger.log_action 调用计数验证记录条数。
"""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

import fakeredis.aioredis
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.services.custom_query import audit_helper
from app.services.custom_query.audit_helper import (
    ACTION_CROSS_SHEET_TRACE,
    ACTION_QUERY_EXECUTE,
    ACTION_WRITEBACK,
    record_cross_sheet_trace,
    record_query_execution,
    record_writeback,
)


# 操作序列元素：writeback / trace / query（query 全部同一 (user, source, filters) 键）
_OPS = st.lists(
    st.sampled_from(["writeback", "trace", "query"]),
    min_size=1,
    max_size=12,
)


@pytest.mark.asyncio
@settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(ops=_OPS)
async def test_p28_audit_throttle_strategy(ops, monkeypatch):
    """Feature: advanced-query-module, Property 28: 审计节流策略

    Validates: Requirements 14.4

    随机操作序列：
      - 每次 writeback → 恰一条审计（不节流）
      - 每次 cross_sheet_trace → 恰一条审计（不节流）
      - 同一 60s 窗口内的多次 query_execute（同 user/source/filters）→ 恰一条
    """
    # 每次属性迭代独立的捕获与 redis（function_scoped fixture 无法用于 @given，故此处内建）
    calls: list[dict] = []

    async def _fake_log_action(**kwargs):
        calls.append(kwargs)
        return kwargs

    monkeypatch.setattr(audit_helper.audit_logger, "log_action", _fake_log_action)

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    try:
        # 固定查询键：同一 60s 窗口内所有 query_execute 聚合为 1 条
        source = "workpaper:D2|审定表D2-1"
        filters = {"year": "2025"}

        writeback_count = 0
        trace_count = 0
        query_count = 0

        for op in ops:
            if op == "writeback":
                writeback_count += 1
                await record_writeback(
                    user_id="user-1",
                    addr_ids="D2/审定表D2-1/E10",
                    old_value=1,
                    new_value=2,
                )
            elif op == "trace":
                trace_count += 1
                await record_cross_sheet_trace(
                    user_id="user-1",
                    addr_ids=["D2/S/A2", "D3/S/B5"],
                )
            else:  # query
                query_count += 1
                await record_query_execution(
                    redis=redis,
                    user_id="user-1",
                    source=source,
                    filters=filters,
                    details={"row_count": 3},
                )

        # 期望审计条数：writeback 逐条 + trace 逐条 + query 聚合为 (有则 1 无则 0)
        expected = writeback_count + trace_count + (1 if query_count > 0 else 0)
        assert len(calls) == expected, (
            f"ops={ops} → 期望 {expected} 条审计，实际 {len(calls)}"
        )

        # 校验各类型 action 的条数
        wb = [c for c in calls if c["action"] == ACTION_WRITEBACK]
        tr = [c for c in calls if c["action"] == ACTION_CROSS_SHEET_TRACE]
        qe = [c for c in calls if c["action"] == ACTION_QUERY_EXECUTE]
        assert len(wb) == writeback_count
        assert len(tr) == trace_count
        assert len(qe) == (1 if query_count > 0 else 0)
    finally:
        await redis.aclose()


@pytest.mark.asyncio
@settings(max_examples=5, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(n=st.integers(min_value=1, max_value=8))
async def test_p28_distinct_query_keys_not_throttled(n, monkeypatch):
    """Feature: advanced-query-module, Property 28: 审计节流策略

    Validates: Requirements 14.4

    补充：N 个**不同** source 的查询执行互不节流 → 恰 N 条（节流键含 source）。
    """
    calls: list[dict] = []

    async def _fake_log_action(**kwargs):
        calls.append(kwargs)
        return kwargs

    monkeypatch.setattr(audit_helper.audit_logger, "log_action", _fake_log_action)

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    try:
        for i in range(n):
            await record_query_execution(
                redis=redis,
                user_id="user-1",
                source=f"workpaper:WP{i}",
                filters={"year": "2025"},
                details={},
            )
        assert len(calls) == n
    finally:
        await redis.aclose()
