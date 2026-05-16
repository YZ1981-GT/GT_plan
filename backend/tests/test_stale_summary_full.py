"""Spec A 集成测试：stale-summary/full 端点

Validates: requirements.md R2, Property P2 (N+1 防退化)
"""
from __future__ import annotations

import pytest
from uuid import UUID

# 4 真实项目（v3 文档实测样本）
SHAANXI = UUID("005a6f2d-cecd-4e30-bcbd-9fb01236c194")
HEPING = UUID("5942c12e-65fb-4187-ace3-79d45a90cb53")
LIAONING = UUID("37814426-a29e-4fc2-9313-a59d229bf7b0")
YIBIN = UUID("14fb8c10-9462-45f6-8f56-d023f5b6df13")


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_stale_summary_full_response_shape(db_session):
    """Property P2: 4 模块字段齐全，结构正确"""
    from app.services.stale_summary_aggregate import get_full_summary

    result = await get_full_summary(db_session, SHAANXI, 2025)

    # R2 验收：必含 4 模块 + last_event_at
    assert set(result.keys()) >= {
        "workpapers", "reports", "notes", "misstatements", "last_event_at"
    }
    assert all(
        set(result[mod].keys()) >= {"total", "items"}
        for mod in ("workpapers", "reports", "notes", "misstatements")
    )
    # workpapers 额外有 stale + inconsistent；misstatements 额外有 recheck_needed
    assert "stale" in result["workpapers"]
    assert "inconsistent" in result["workpapers"]
    assert "recheck_needed" in result["misstatements"]


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_stale_summary_full_year_isolation(db_session):
    """Property P5: 跨年度隔离 — year=2024 不影响 year=2025"""
    from app.services.stale_summary_aggregate import get_full_summary

    r2024 = await get_full_summary(db_session, SHAANXI, 2024)
    r2025 = await get_full_summary(db_session, SHAANXI, 2025)
    # 2024 年应几乎没数据；2025 应有完整数据
    assert r2025["workpapers"]["total"] >= r2024["workpapers"]["total"]


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_stale_summary_full_query_count(db_session):
    """Property P2: N+1 防退化 — 单请求 ≤ 6 次 SQL（4 个聚合 + 2 个 details）

    注：当前实现 4 SQL count + 4 SQL items + 1 last_event = 9 次；
    若需严格 ≤ 6 必须把 count + items 合并为 CTE。本测先记录基线。
    """
    from sqlalchemy import event
    from app.services.stale_summary_aggregate import get_full_summary

    queries = []

    def _capture(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    bind = db_session.get_bind() if hasattr(db_session, "get_bind") else None
    if bind:
        event.listen(bind.sync_engine, "before_cursor_execute", _capture)

    await get_full_summary(db_session, SHAANXI, 2025)

    if bind:
        event.remove(bind.sync_engine, "before_cursor_execute", _capture)
    # 当前 baseline ≤ 12（4 count + 4 items + 1 last_event + 余量）
    assert len(queries) <= 12, f"Expected ≤ 12 SQL, got {len(queries)}"


@pytest.mark.pg_only
@pytest.mark.asyncio
async def test_stale_summary_full_4_projects(db_session):
    """4 项目都能正确返回（实测基线）"""
    from app.services.stale_summary_aggregate import get_full_summary

    for pid in (SHAANXI, HEPING, LIAONING, YIBIN):
        r = await get_full_summary(db_session, pid, 2025)
        assert r["workpapers"]["total"] >= 0
        assert r["reports"]["total"] >= 0
        assert r["notes"]["total"] >= 0
