"""Exact COUNT token is bound to query and caller, and skips repeat SQL."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
import sqlalchemy as sa

from app.routers.custom_query import QueryRequest as WireQueryRequest
from app.services.custom_query import count_token
from app.services.custom_query.execute_compatibility import ExecuteCompatibilityAdapter
from app.services.custom_query.paged_fetch import StreamPlan, _count, _count_page, count_plan


class _ScalarResult:
    def __init__(self, value: int):
        self.value = value

    def scalar_one(self) -> int:
        return self.value


class _Db:
    def __init__(self, total: int = 37):
        self.bind = sa.create_engine("sqlite://")
        self.total = total
        self.calls = 0

    def get_bind(self):
        return self.bind

    async def execute(self, _stmt):
        self.calls += 1
        return _ScalarResult(self.total)


@pytest.mark.asyncio
async def test_paged_count_reuses_signed_total_without_second_sql() -> None:
    db = _Db(348_780)
    ctx = SimpleNamespace(db=db, user=SimpleNamespace(id="user-a"))
    stmt = sa.select(sa.literal("1002").label("account_code"))

    total, token, reused = await _count_page(ctx, stmt)
    assert (total, reused, db.calls) == (348_780, False, 1)

    total2, token2, reused2 = await _count_page(ctx, stmt, reuse_token=token)
    assert (total2, token2, reused2, db.calls) == (348_780, token, True, 1)


@pytest.mark.asyncio
async def test_precount_paths_keep_plain_int_total() -> None:
    """分组 / 透视与导出预检只要行数：返回 int，不签发凭证（导出曾因拿到三元组而 500）。"""
    db = _Db(12)
    ctx = SimpleNamespace(db=db, user=SimpleNamespace(id="user-a"))
    stmt = sa.select(sa.literal(1).label("x"))

    assert await _count(ctx, stmt) == 12
    plan = StreamPlan(spec=None, ctx=ctx, stmt=stmt, order=[], columns=[], warnings=[])
    total = await count_plan(plan)
    assert type(total) is int and total == 12


@pytest.mark.asyncio
async def test_token_cannot_cross_query_user_or_expiry() -> None:
    db = _Db(8)
    stmt = sa.select(sa.literal(1).label("x"))
    digest = count_token.statement_digest(stmt, db.get_bind(), subject="u1")
    token = count_token.issue(digest=digest, total=8, subject="u1", now=100)

    assert count_token.reuse(token, digest=digest, subject="u1", now=101) == 8
    assert count_token.reuse(token, digest=digest + "x", subject="u1", now=101) is None
    assert count_token.reuse(token, digest=digest, subject="u2", now=101) is None
    assert count_token.reuse(token, digest=digest, subject="u1", now=701) is None
    changed = token[:-1] + ("A" if token[-1] != "A" else "B")
    assert count_token.reuse(changed, digest=digest, subject="u1", now=101) is None


def test_wire_and_compatibility_adapter_preserve_optional_token() -> None:
    wire = WireQueryRequest(
        project_id="p1", year=2025, source="aux_ledger",
        filters={"account_code": "1002"}, count_token="signed-token",
    )
    internal = ExecuteCompatibilityAdapter.to_orchestrator_request(wire)
    assert internal.count_token == "signed-token"
    assert internal.cache_def()["offset"] == 0
    assert "count_token" not in internal.cache_def()
