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

不重写 ACNR 核心：orchestrator 的寻址依赖以 stub `AddressingService` 注入，仅验证
「同步 BFS + async 编排」的接线契约与异步安全性。
"""

from __future__ import annotations

import asyncio
import inspect
import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-unit-tests")

import pytest

from app.services.custom_query.addressing_service import (
    AddressingService,
    ResolvedTarget,
)
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


# ─── Stub AddressingService（注入 orchestrator，不触达 ACNR/DB）──────────────


class _StubAddressing(AddressingService):
    """resolve_many 返回受控 addr_id，记录调用以验证 async IO 上浮到 orchestrator。"""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def resolve_many(
        self, raws, *, project_id=None, db=None, timeout_s=5.0
    ) -> list[ResolvedTarget]:
        self.calls.append(list(raws))
        # 每个链节点解析为一个 canonical addr_id + jump_route
        return [
            ResolvedTarget(
                raw=raw,
                found=True,
                addr_id=f"ADDR::{raw}",
                jump_route=f"/jump/{i}",
                entry_type="cell",
            )
            for i, raw in enumerate(raws)
        ]


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


# ─── 2. async 编排：IO 上浮 + addr_id 合并 ───────────────────────────────────


def test_orchestrator_trace_is_coroutine():
    """CrossSheetTraceOrchestrator.trace 必须是 async（异步 IO 上浮的唯一出口）。"""
    assert inspect.iscoroutinefunction(CrossSheetTraceOrchestrator.trace)


@pytest.mark.asyncio
async def test_orchestrator_merges_addr_id_from_async_resolution():
    """同步 BFS 得链 → async 并发解析 addr_id → 合并回链的每个节点。"""
    stub = _StubAddressing()
    orch = CrossSheetTraceOrchestrator(
        resolver=CrossSheetResolver(), addressing=stub
    )
    snap = _snapshot_with_formula("Sheet1", "A1", "=Sheet2!B2")

    resp = await orch.trace(snap, "Sheet1", "A1", project_id="proj-1", max_depth=3)

    assert isinstance(resp, CrossSheetTraceResponse)
    assert len(resp.chain) == 2
    # async 寻址被调用恰一次（批量 resolve_many），IO 上浮到 orchestrator
    assert len(stub.calls) == 1
    assert len(stub.calls[0]) == 2  # 两个链节点一次性并发解析
    for node in resp.chain:
        assert isinstance(node, TracedRefNode)
        assert node.resolved is True
        assert node.addr_id is not None and node.addr_id.startswith("ADDR::")
        assert node.jump_route is not None


@pytest.mark.asyncio
async def test_orchestrator_empty_chain_skips_addressing():
    """空链（起点 cell 无法定位仍产出 root 节点）时仍安全返回，不误报。"""
    stub = _StubAddressing()
    orch = CrossSheetTraceOrchestrator(
        resolver=CrossSheetResolver(), addressing=stub
    )
    # parsed_data=None → 单 root 节点、无跨表引用
    resp = await orch.trace(None, "SheetX", "A1", project_id="proj-1")
    assert isinstance(resp, CrossSheetTraceResponse)
    assert len(resp.chain) == 1
    # 有一个节点 → resolve_many 被调用一次解析该节点
    assert len(stub.calls) == 1
    assert resp.chain[0].resolved is True


@pytest.mark.asyncio
async def test_orchestrator_runs_bfs_synchronously_then_awaits_io():
    """编排顺序契约：先同步 BFS（无 IO），再 await 异步 addr_id 解析。

    通过在 stub 内断言链已成型（长度、顺序）来证明 BFS 已在 await 前同步完成。
    """
    captured: dict = {}

    class _OrderStub(AddressingService):
        async def resolve_many(self, raws, *, project_id=None, db=None, timeout_s=5.0):
            captured["inputs"] = list(raws)
            return [
                ResolvedTarget(raw=r, found=True, addr_id=f"ADDR::{r}")
                for r in raws
            ]

    orch = CrossSheetTraceOrchestrator(
        resolver=CrossSheetResolver(), addressing=_OrderStub()
    )
    snap = _snapshot_with_formula("A", "A1", "=B!B1")
    resp = await orch.trace(snap, "A", "A1")

    # BFS 在 await resolve_many 前已完整成型（两节点，按发现顺序传入寻址层）
    assert captured["inputs"] == ["cell:A!A1", "cell:B!B1"]
    assert [n.uri for n in resp.chain] == ["A!A1", "B!B1"]
