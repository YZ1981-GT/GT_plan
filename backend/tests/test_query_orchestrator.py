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

from app.services.acnr.resolver import ResolveResult
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
    """AddressingService 桩：记录寻址调用，所有目标解析为 L1 底稿单元格。

    业务视图入口经 ``resolve_acnr_targets`` 逐项调 ``resolve_target``（acnr-foundation-defect-closure T15），
    分类表只接受 L1 底稿单元格，故桩返回带 ``result``（``source_layer="L1_cell"``）的结果。
    """

    def __init__(self, events: list[str]) -> None:
        self._events = events
        self.called_with: list[str] = []

    async def resolve_target(self, raw, *, project_id=None, db=None, timeout_s=5.0):
        if not self.called_with:
            self._events.append("resolve")
        self.called_with.append(raw)
        res = ResolveResult(found=True, addr_id=f"WP/S/{raw}", entry_type="cell", source_layer="L1_cell")
        return ResolvedTarget(raw=raw, found=True, addr_id=res.addr_id, entry_type="cell", result=res)

    async def resolve_many(self, raws, *, project_id, db):
        self._events.append("resolve")
        self.called_with = list(raws)
        return [
            ResolvedTarget(raw=r, found=True, addr_id=f"WP/S/{r}") for r in raws
        ]


_BLOCK = {"registry_version": "stub", "year": 2025, "items": []}


@pytest.fixture(autouse=True)
def _stub_value_reader(monkeypatch):
    """单元格取值换成记录桩（取值本身见 ``tests/acnr/test_acnr_target_values.py`` 与 T15 端到端）。"""
    from app.services.custom_query import query_orchestrator as orch_module

    calls: list[tuple] = []

    async def _read(resolved, *, project_id, year, db):
        calls.append((tuple(t.raw for t in resolved), project_id, year))
        return _BLOCK if resolved else None

    monkeypatch.setattr(orch_module, "read_acnr_target_values", _read)
    return calls


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
async def test_business_entry_chain_order_and_detail(_stub_value_reader) -> None:
    """business 入口：Ownership_Check → resolve → fetch → 单元格取值，无维度返回明细结果集。"""
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

    req = QueryRequest(entry="business", project_id="p-1", year=2025, targets=["E1/E1-14/C10"])
    result = await orch.execute(req, user=_User(), db=None)

    # 链顺序：准入 → 寻址 → 取数 → 单元格取值（取值在缓存读取之后、不进缓存）
    assert events == ["ownership_check", "resolve", "fetch_business"]
    assert _stub_value_reader == [(("E1/E1-14/C10",), "p-1", 2025)]
    assert result.acnr_results == _BLOCK
    # 寻址收到业务目标
    assert addressing.called_with == ["E1/E1-14/C10"]

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
async def test_cache_hit_returns_cached_without_compute(_stub_value_reader) -> None:
    """缓存命中：cache_hit=True，且不执行取数（fetcher 不被调用）；单元格取值仍现读（不进缓存）。"""
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

    req = QueryRequest(entry="business", project_id="p-1", year=2025, targets=["E1/E1-14/C10"])
    result = await orch.execute(req, user=_User(), db=None)

    # 命中：准入 + 寻址仍发生，但取数未执行；单元格取值照读
    assert "fetch_business" not in events
    assert len(_stub_value_reader) == 1 and result.acnr_results == _BLOCK
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

    req = QueryRequest(entry="business", project_id="p-1", year=2025, targets=["E1/E1-14/C10"])
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
