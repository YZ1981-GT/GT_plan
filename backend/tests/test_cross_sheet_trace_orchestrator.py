"""异步陷阱回归测试 — CrossSheetTraceOrchestrator (Task 3.3).

Spec: .kiro/specs/advanced-query-module (design.md §Architecture 异步陷阱处理).

回归目标（防 memory 记录的 async pitfall）：
  - `CrossSheetResolver.resolve` 保持 **同步纯 BFS**：仅公式字符串 BFS + snapshot
    cell 提取 + 环检测/深度截断，不在同步上下文内 `await` / `asyncio.run`。
  - 异步 IO（ACNR `full_resolve` 解析 addr_id）全部 **上浮** 到 async
    `CrossSheetTraceOrchestrator.trace`（router 层 await）。
  - 在已运行的事件循环中调用同步 `resolve()` 不得抛 "event loop is already
    running"（`_sync_resolve` 探测 running loop → 优雅降级，不阻塞 BFS）。

**Validates: Requirements 1.6, 4.2**

节点身份（acnr-foundation-defect-closure T20）：编排器对每个节点经 `exact_identity.cell_of`
（真实目录，不打桩）判定「父底稿 + sheet + A1」，不再把节点拼成 `cell:{sheet 名}!{A1}` 交寻址层；
端到端（真 PG + TestClient）见 `tests/acnr/test_cross_sheet_trace_async_e2e.py`。
"""

from __future__ import annotations

import asyncio
import inspect
import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

import pytest

from app.services.custom_query import addressing_service as addressing_mod
from app.services.custom_query.cross_sheet_resolver import (
    CrossSheetResolver,
    _cell_ref_to_indices,
    cross_sheet_resolver,
)
from app.services.custom_query.cross_sheet_trace_orchestrator import (
    CrossSheetTraceOrchestrator,
    CrossSheetTraceResponse,
    TracedRefNode,
)


#: 目录权威名（真实目录 E1 下的两张表）
_E1_14 = "货币资金分析表E1-14"
_E1_15 = "利息收入月度分析E1-15"


@pytest.fixture
def no_addressing(monkeypatch):
    """编排器不得再经统一寻址层解析节点（旧做法把节点拼成 cell:{sheet 名}!{A1}，真实 sheet 名恒解析不到）。"""
    calls: list = []

    async def _forbidden(self, raws, **kwargs):
        calls.append(list(raws))
        raise AssertionError("编排器不应调用 AddressingService.resolve_many")

    monkeypatch.setattr(addressing_mod.AddressingService, "resolve_many", _forbidden)
    return calls


def _snapshot_with_formula(sheet_name: str, cell_ref: str, formula: str) -> dict:
    """Build a parsed_data snapshot where sheet!cell holds a given formula."""
    row_idx, col_idx = _cell_ref_to_indices(cell_ref)
    assert row_idx is not None and col_idx is not None
    return {
        "univer_snapshot": {
            "sheets": [
                {
                    "name": sheet_name,
                    "cellData": {str(row_idx): {str(col_idx): {"f": formula}}},
                }
            ]
        }
    }


# ─── 1. 同步纯函数契约（不在同步上下文内 await / asyncio.run）─────────────────


def test_resolver_resolve_is_synchronous_not_coroutine():
    """CrossSheetResolver.resolve 必须是同步方法（非 coroutine function）。"""
    assert not inspect.iscoroutinefunction(CrossSheetResolver.resolve)


def test_resolver_resolve_source_has_no_await_or_asyncio_run():
    """回归守卫：同步 BFS 方法体内不得出现 `await` 或 `asyncio.run(`。

    异步 IO 只允许存在于 orchestrator 的 await 中；同步纯 BFS 若内联 await /
    asyncio.run 会在运行 loop 抛错（防回归标注的 async pitfall）。
    """
    src = inspect.getsource(CrossSheetResolver.resolve)
    assert "await " not in src, "sync BFS resolve() must not contain `await`"
    assert "asyncio.run(" not in src, "sync BFS resolve() must not call asyncio.run"


def test_resolver_resolve_pure_bfs_without_event_loop():
    """纯同步上下文（无 running loop）下 resolve() 正常返回 BFS 链。"""
    snap = _snapshot_with_formula("Sheet1", "A1", "=Sheet2!B2")
    resp = cross_sheet_resolver.resolve(snap, "Sheet1", "A1", max_depth=3)
    # root(Sheet1!A1) → referenced(Sheet2!B2)
    assert len(resp.chain) == 2
    assert resp.chain[0].uri == "Sheet1!A1"
    assert resp.chain[1].uri == "Sheet2!B2"
    assert resp.chain[0].resolve_missed is True  # 无 catalog → snapshot fallback


@pytest.mark.asyncio
async def test_resolver_resolve_inside_running_loop_does_not_raise():
    """核心 pitfall 守卫：在已运行的事件循环中调用同步 resolve() 不得抛错。

    `_sync_resolve` 探测到 running loop → 返回 None（降级 snapshot fallback），
    绝不 `asyncio.run` / `await` 于同步上下文，故不产生 "event loop is already
    running" RuntimeError。
    """
    assert asyncio.get_running_loop() is not None  # 确认处于运行的 loop 中
    snap = _snapshot_with_formula("审定表", "A2", "=明细表!E100")
    # 直接同步调用（不 await）——不得抛异常
    resp = cross_sheet_resolver.resolve(snap, "审定表", "A2", max_depth=3)
    assert len(resp.chain) == 2
    for node in resp.chain:
        assert node.resolve_missed is True  # running loop → 全部降级 fallback


# ─── 2. async 编排：身份经 exact_identity 判定（acnr T20）───────────────────


def test_orchestrator_trace_is_coroutine():
    """CrossSheetTraceOrchestrator.trace 必须是 async（异步 IO 上浮的唯一出口）。"""
    assert inspect.iscoroutinefunction(CrossSheetTraceOrchestrator.trace)


@pytest.mark.asyncio
async def test_orchestrator_merges_canonical_identity(no_addressing):
    """同步 BFS 得链 → 每个节点按「父底稿 + sheet 名 + A1」判出规范 addr_id，并标是否为登记 cell。"""
    orch = CrossSheetTraceOrchestrator(resolver=CrossSheetResolver(resolve_identity=False))
    snap = _snapshot_with_formula(_E1_14, "C10", f"='{_E1_15}'!C8+'{_E1_14}'!Z99")

    resp = await orch.trace(snap, _E1_14, "C10", parent_wp_code="E1", max_depth=3)

    assert isinstance(resp, CrossSheetTraceResponse)
    got = [(n.uri, n.addr_id, n.resolved, n.in_catalog, n.unresolved_reason) for n in resp.chain]
    assert got == [
        (f"{_E1_14}!C10", "E1/E1-14/C10", True, True, None),
        (f"{_E1_15}!C8", "E1/E1-15/C8", True, True, None),
        # sheet 已识别、A1 合法但不是登记 cell：仍是规范身份（R2-F8）
        (f"{_E1_14}!Z99", "E1/E1-14/Z99", True, False, None),
    ]
    for node in resp.chain:
        assert isinstance(node, TracedRefNode)
        # 无项目上下文：不查底稿实例
        assert node.wp_id is None and node.jump_route is None
    assert no_addressing == []


@pytest.mark.asyncio
async def test_orchestrator_unresolvable_nodes_carry_chinese_reason(no_addressing):
    """sheet 不在目录 / A1 非法 / 父级内多义 ⇒ resolved=False、addr_id=None、带中文原因，不中断整条链。"""
    orch = CrossSheetTraceOrchestrator(resolver=CrossSheetResolver(resolve_identity=False))
    snap = _snapshot_with_formula(_E1_14, "C10", "='不存在的表'!A1")
    resp = await orch.trace(snap, _E1_14, "C10", parent_wp_code="E1")
    assert [n.resolved for n in resp.chain] == [True, False]
    missing = resp.chain[1]
    assert missing.addr_id is None and "不存在的表" in (missing.unresolved_reason or "")

    bad = await orch.trace(None, _E1_14, "A1B", parent_wp_code="E1")
    assert bad.chain[0].resolved is False and "A1B" in (bad.chain[0].unresolved_reason or "")

    ambiguous = await orch.trace(None, "底稿目录", "A1", parent_wp_code="F2")
    node = ambiguous.chain[0]
    assert node.resolved is False and node.addr_id is None
    assert "F2-33" in (node.unresolved_reason or "") and "F2-34" in (node.unresolved_reason or "")
    assert no_addressing == []


@pytest.mark.asyncio
async def test_orchestrator_without_parent_reports_reason(no_addressing):
    """没给父底稿编码（端点总会给）⇒ 单 root 节点 resolved=False 且原因说明缺父底稿。"""
    orch = CrossSheetTraceOrchestrator(resolver=CrossSheetResolver(resolve_identity=False))
    resp = await orch.trace(None, "SheetX", "A1")
    assert len(resp.chain) == 1
    assert resp.chain[0].resolved is False
    assert resp.chain[0].unresolved_reason == "缺少父底稿编码，无法确定单元格身份"
    assert no_addressing == []


def test_production_singleton_does_not_bridge_identity():
    """编排器缺省用的模块单例只做 BFS（resolve_identity=False），不经同步桥接取身份。"""
    assert cross_sheet_resolver._resolve_identity is False
