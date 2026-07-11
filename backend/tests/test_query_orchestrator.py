"""QueryOrchestrator 编排链单元测试（advanced-query-module Task 8.3）

示例（非属性）测试，覆盖 design.md §Components 3「QueryOrchestrator」的编排契约：

- **两入口编排链顺序**：``business`` 走 ``Ownership_Check → resolve → fetch``；
  ``builder`` 走 ``Ownership_Check → fetch``（构建器入口不走 cell 寻址，
  ``resolve`` 步不调用 AddressingService）。
- **明细结果集**（无维度，R5.7）：``group_by`` 为空 → 不分组、原样明细行、
  结果列保留单源 addr_id 挂载（可下钻）。
- **cache_hit / warnings 字段**：命中缓存 → ``cache_hit=True`` 且不执行取数；
  未接线 fetcher → ``warnings`` 标注集成钩子、空结果。

用 stub/mock 注入 guard / addressing / cache / fetcher，隔离 ACNR 与 DB，
仅验证编排层自身逻辑（service 只读、只编排、不 commit）。

Validates: Requirements 5.7
"""

from __future__ import annotations

import pytest

from app.services.custom_query.addressing_service import ResolvedTarget
from app.services.custom_query.query_orchestrator import (
    ColumnMeta,
    QueryOrchestrator,
    QueryRequest,
    QueryResult,
)

# ─────────────────────────────────────────────────────────────────────────────
# Stubs / Mocks —— 隔离 ACNR / DB，记录调用顺序
# ─────────────────────────────────────────────────────────────────────────────


class _User:
    """最小用户对象（QueryOrchestrator 仅取 .id 作 scope 签名）。"""

    def __init__(self, uid: str = "u-1") -> None:
        self.id = uid


class StubGuard:
    """OwnershipGuard 桩：记录准入校验调用，默认放行。"""

    def __init__(self, events: list[str]) -> None:
        self._events = events

    async def assert_target_accessible(self, *, user, project_id, db) -> None:
        self._events.append("ownership_check")

    async def filter_accessible_rows(self, rows, *, user, db):
        self._events.append("filter_rows")
        return rows


class StubAddressing:
    """AddressingService 桩：记录寻址调用，所有目标解析成功。"""

    def __init__(self, events: list[str]) -> None:
        self._events = events
        self.called_with: list[str] = []

    async def resolve_many(self, raws, *, project_id, db):
        self._events.append("resolve")
        self.called_with = list(raws)
        return [
            ResolvedTarget(raw=r, found=True, addr_id=f"WP/S/{r}") for r in raws
        ]


class PassthroughCache:
    """QueryCache 桩：直接执行 compute（缓存未命中路径）。"""

    def __init__(self) -> None:
        self.key_calls = 0

    def cache_key(self, query_def, project_id, scope_sig) -> str:
        self.key_calls += 1
        return f"k:{project_id}:{scope_sig}"

    async def get_or_compute(self, key, compute, *, ttl=30):
        return await compute()


class HitCache:
    """QueryCache 桩：命中缓存路径（不执行 compute，直接返回既有 payload）。"""

    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def cache_key(self, query_def, project_id, scope_sig) -> str:
        return f"k:{project_id}:{scope_sig}"

    async def get_or_compute(self, key, compute, *, ttl=30):
        # 命中：不调用 compute
        return self._payload


def _make_fetcher(events: list[str], tag: str, rows, columns):
    async def _fetcher(req, resolved, db):
        events.append(f"fetch_{tag}")
        return list(rows), list(columns)

    return _fetcher


# ─────────────────────────────────────────────────────────────────────────────
# 两入口编排链顺序 + 明细结果集（R5.7）
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_business_entry_chain_order_and_detail() -> None:
    """business 入口：Ownership_Check → resolve → fetch，无维度返回明细结果集。"""
    events: list[str] = []
    guard = StubGuard(events)
    addressing = StubAddressing(events)
    cache = PassthroughCache()
    rows = [{"amt": 100}, {"amt": 200}]
    columns = [ColumnMeta(key="amt", title="金额", addr_id="WP/S/amt", dtype="number")]

    orch = QueryOrchestrator(
        addressing=addressing,
        guard=guard,
        cache=cache,
        business_fetcher=_make_fetcher(events, "business", rows, columns),
    )

    req = QueryRequest(entry="business", project_id="p-1", targets=["tb:1001"])
    result = await orch.execute(req, user=_User(), db=None)

    # 链顺序：准入 → 寻址 → 取数
    assert events == ["ownership_check", "resolve", "fetch_business"]
    # 寻址收到业务目标
    assert addressing.called_with == ["tb:1001"]

    # 明细结果集（无维度，R5.7）：原样行、总数、未命中缓存、无告警
    assert isinstance(result, QueryResult)
    assert result.rows == rows
    assert result.total == 2
    assert result.cache_hit is False
    assert result.warnings == []

    # 单源列保留 addr_id 挂载（可下钻）
    assert len(result.columns) == 1
    assert result.columns[0].addr_id == "WP/S/amt"
    assert result.columns[0].drillable is True


@pytest.mark.asyncio
async def test_builder_entry_skips_cell_resolve() -> None:
    """builder 入口：Ownership_Check → fetch，不走 cell 寻址（resolve 不调用）。"""
    events: list[str] = []
    guard = StubGuard(events)
    addressing = StubAddressing(events)
    cache = PassthroughCache()
    rows = [{"n": 1}]
    columns = [ColumnMeta(key="n", title="N", dtype="number")]

    orch = QueryOrchestrator(
        addressing=addressing,
        guard=guard,
        cache=cache,
        builder_fetcher=_make_fetcher(events, "builder", rows, columns),
    )

    req = QueryRequest(entry="builder", project_id="p-1", dsl={"table": "trial_balance"})
    result = await orch.execute(req, user=_User(), db=None)

    # 构建器入口不调用 AddressingService.resolve_many
    assert events == ["ownership_check", "fetch_builder"]
    assert addressing.called_with == []
    assert result.rows == rows
    assert result.total == 1
    assert result.cache_hit is False

    # 无源列不可下钻（R4.5）
    assert result.columns[0].addr_id is None
    assert result.columns[0].drillable is False


# ─────────────────────────────────────────────────────────────────────────────
# cache_hit 字段
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cache_hit_returns_cached_without_compute() -> None:
    """缓存命中：cache_hit=True，且不执行取数（fetcher 不被调用）。"""
    events: list[str] = []
    guard = StubGuard(events)
    addressing = StubAddressing(events)
    cached_payload = {
        "columns": [
            {"key": "amt", "title": "金额", "addr_id": "WP/S/amt", "dtype": "number"}
        ],
        "rows": [{"amt": 999}],
        "total": 1,
        "warnings": [],
    }
    cache = HitCache(cached_payload)

    orch = QueryOrchestrator(
        addressing=addressing,
        guard=guard,
        cache=cache,
        business_fetcher=_make_fetcher(events, "business", [{"amt": 1}], []),
    )

    req = QueryRequest(entry="business", project_id="p-1", targets=["tb:1001"])
    result = await orch.execute(req, user=_User(), db=None)

    # 命中：准入 + 寻址仍发生，但取数未执行
    assert "fetch_business" not in events
    assert result.cache_hit is True
    assert result.rows == [{"amt": 999}]
    assert result.total == 1
    assert result.columns[0].addr_id == "WP/S/amt"
    assert result.columns[0].drillable is True


# ─────────────────────────────────────────────────────────────────────────────
# warnings 字段（未接线 fetcher 的集成钩子标注）
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unwired_fetcher_emits_warning() -> None:
    """未注入 fetcher：warnings 标注集成钩子未接线，结果为空但链不崩。"""
    events: list[str] = []
    guard = StubGuard(events)
    addressing = StubAddressing(events)
    cache = PassthroughCache()

    orch = QueryOrchestrator(addressing=addressing, guard=guard, cache=cache)

    req = QueryRequest(entry="business", project_id="p-1", targets=["tb:1001"])
    result = await orch.execute(req, user=_User(), db=None)

    assert result.rows == []
    assert result.total == 0
    assert result.cache_hit is False
    assert len(result.warnings) == 1
    assert "row_fetcher 未接线" in result.warnings[0]


# ─────────────────────────────────────────────────────────────────────────────
# 未知入口拒绝
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_invalid_entry_rejected() -> None:
    """未知 entry → HTTPException(400, INVALID_ENTRY)，在准入之前拒绝。"""
    from fastapi import HTTPException

    events: list[str] = []
    orch = QueryOrchestrator(
        addressing=StubAddressing(events),
        guard=StubGuard(events),
        cache=PassthroughCache(),
    )
    req = QueryRequest(entry="bogus", project_id="p-1")

    with pytest.raises(HTTPException) as ei:
        await orch.execute(req, user=_User(), db=None)
    assert ei.value.status_code == 400
    assert ei.value.detail["error_code"] == "INVALID_ENTRY"
    # 未知入口在任何编排步之前拒绝
    assert events == []
