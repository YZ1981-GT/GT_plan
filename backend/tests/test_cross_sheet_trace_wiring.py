"""跨 sheet 溯源端点接线守卫（addr_id 不得静默降级）。

Feature: advanced-query-hardening-wiring-closure（收口遗留项②）
覆盖 Requirements 4.2 / 4.4 / 8.4 / 14.3 / 14.4。

背景：`/api/custom-query/cross-sheet-trace` 是 async 端点，却直接调同步
``cross_sheet_resolver.resolve()``。同步 BFS 内部的 ``_sync_resolve`` 一探测到
running loop 就返回 None 降级（这是它的正确行为），于是**每个链节点的 addr_id 恒为
None** —— 溯源结果无法跳转，审计日志（R14.3/R14.4 要求记「目标 addr_id 集合」）拿到
的其实是 ``sheet!cell`` 字符串。

同一缺口当时有**两个**互不接线的修复并存：
  - ``CrossSheetTraceOrchestrator``（组合同步 BFS + 一次批量 async 解析，有测试）
  - ``CrossSheetResolver.full_resolve_async``（整段复制 BFS 只换 ACNR 调用，无测试）
现保留前者并接进 router，后者删除（零引用 + 零测试 + 重复 BFS）。

判据落在**行为**上：直调端点函数（不经 SQLite —— 端点 SQL 用了 PG 的
``CAST(:pid AS uuid)``），用假 db 与替身 orchestrator，断言 addr_id 真的进了响应与
审计留痕；另加结构判据锁死「BFS 只有一份」。
"""

from __future__ import annotations

import ast
import inspect
import uuid
from pathlib import Path

import pytest

RESOLVER_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "services"
    / "custom_query"
    / "cross_sheet_resolver.py"
)


class _FakeUser:
    def __init__(self) -> None:
        self.id = uuid.uuid4()
        self.role = "admin"


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _FakeDb:
    """只需支撑端点那一条 ``SELECT id, parsed_data FROM working_paper``。"""

    def __init__(self, row):
        self._row = row
        self.executed: list[str] = []

    async def execute(self, stmt, params=None):
        self.executed.append(str(stmt))
        return _FakeResult(self._row)


@pytest.fixture
def wired_endpoint(monkeypatch):
    """把端点的三个协作方换成可观测替身，返回 (调用端点的函数, 记录字典)。"""
    from app.routers import custom_query as router_mod
    from app.services.custom_query import audit_helper, cross_sheet_trace_orchestrator as orch_mod
    from app.services.custom_query import ownership_guard as guard_mod
    from app.services.custom_query.cross_sheet_trace_orchestrator import (
        CrossSheetTraceResponse,
        TracedRefNode,
    )

    seen: dict = {"trace_kwargs": None, "audit_addr_ids": None, "guard_called": False}

    class _StubGuard:
        async def assert_target_accessible(self, *, user, project_id, db):
            seen["guard_called"] = True

    class _StubOrchestrator:
        async def trace(self, parsed_data, sheet_name, cell_ref, **kwargs):
            seen["trace_kwargs"] = {
                "parsed_data": parsed_data,
                "sheet_name": sheet_name,
                "cell_ref": cell_ref,
                **kwargs,
            }
            return CrossSheetTraceResponse(
                chain=[
                    TracedRefNode(
                        depth=0,
                        uri="Sheet1!A1",
                        addr_id="D2-1/审定表/A1",
                        wp_id="wp-1",
                        jump_route="/workpapers/wp-1",
                        resolved=True,
                    ),
                    TracedRefNode(depth=1, uri="Sheet2!B2", resolved=False),
                ],
                has_cycle=False,
                truncated_at_depth=None,
            )

    async def _stub_audit(*, user_id, addr_ids, result, project_id, object_id, extra):
        seen["audit_addr_ids"] = list(addr_ids)

    monkeypatch.setattr(guard_mod, "ownership_guard", _StubGuard())
    monkeypatch.setattr(orch_mod, "cross_sheet_trace_orchestrator", _StubOrchestrator())
    monkeypatch.setattr(audit_helper, "record_cross_sheet_trace", _stub_audit)

    async def _call(parsed_data=None):
        db = _FakeDb((uuid.uuid4(), parsed_data or {"univer_snapshot": {"sheets": []}}))
        return await router_mod.cross_sheet_trace(
            wp_code="D2-1",
            sheet_name="Sheet1",
            cell_ref="A1",
            project_id=str(uuid.uuid4()),
            max_depth=3,
            db=db,
            current_user=_FakeUser(),
        )

    return _call, seen


@pytest.mark.asyncio
async def test_endpoint_goes_through_orchestrator(wired_endpoint):
    """端点必须 await orchestrator —— 直调同步 resolve 会让 addr_id 恒 None。"""
    call, seen = wired_endpoint
    await call()
    assert seen["trace_kwargs"] is not None, (
        "端点未调用 CrossSheetTraceOrchestrator.trace —— 若回到同步 "
        "cross_sheet_resolver.resolve()，_sync_resolve 在 running loop 下降级，"
        "每个链节点 addr_id 恒为 None"
    )
    # project_id / db 必须传下去：ACNR full_resolve 要靠它们定位与查库。
    # 用 .get() 而非 [] —— 少传参数时要以「断言失败」变红，而不是 KeyError。
    kwargs = seen["trace_kwargs"]
    assert kwargs.get("project_id"), "未把 project_id 传给 orchestrator，ACNR 无法定位"
    assert kwargs.get("db") is not None, "未把 db 传给 orchestrator，ACNR 无法查库"
    assert kwargs.get("max_depth") == 3


@pytest.mark.asyncio
async def test_response_carries_addr_id(wired_endpoint):
    """响应链节点必须带 addr_id / jump_route（可跳转是溯源的全部意义）。"""
    call, _seen = wired_endpoint
    payload = await call()
    chain = payload["chain"]
    assert chain[0]["addr_id"] == "D2-1/审定表/A1"
    assert chain[0]["jump_route"] == "/workpapers/wp-1"
    assert chain[0]["resolved"] is True
    # 未解析节点优雅降级，不中断整条链
    assert chain[1]["addr_id"] is None and chain[1]["resolved"] is False


@pytest.mark.asyncio
async def test_audit_records_real_addr_ids(wired_endpoint):
    """审计留痕要记真 addr_id（R14.3/R14.4），未解析节点才退回 uri 占位。"""
    call, seen = wired_endpoint
    await call()
    recorded = seen["audit_addr_ids"]
    assert recorded is not None, "审计未被调用"
    assert "D2-1/审定表/A1" in recorded, (
        f"审计记的不是真 addr_id：{recorded}——回到同步 BFS 时这里只会是 sheet!cell"
    )
    assert "Sheet2!B2" in recorded, "未解析节点应退回 uri 占位，保证留痕完整"


@pytest.mark.asyncio
async def test_ownership_guard_still_precedes_read(wired_endpoint):
    """归属校验仍在任何数据读取之前（防 IDOR，R9.1/R9.2）。"""
    call, seen = wired_endpoint
    await call()
    assert seen["guard_called"] is True


def test_resolver_has_single_bfs():
    """结构判据：BFS 只能有一份。

    ``full_resolve_async`` 曾是同步 ``resolve`` 的 71% 复制品（只把
    ``_sync_resolve`` 换成 ``await full_resolve``），零引用零测试。两份 BFS 必然漂移，
    故锁死「返回 RefChainResponse 的方法只有一个」。
    """
    from app.services.custom_query.cross_sheet_resolver import CrossSheetResolver

    tree = ast.parse(RESOLVER_PATH.read_text(encoding="utf-8"))
    cls = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.ClassDef) and n.name == "CrossSheetResolver"
    )
    bfs_methods = [
        n.name
        for n in cls.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and isinstance(n.returns, ast.Name)
        and n.returns.id == "RefChainResponse"
    ]
    assert bfs_methods == ["resolve"], (
        f"CrossSheetResolver 有多份 BFS：{bfs_methods}——异步变体应由 "
        f"CrossSheetTraceOrchestrator 组合实现，不要复制 BFS 循环"
    )
    # 反向自检：解析器确实认得出该类的方法，否则上一条会假绿
    assert hasattr(CrossSheetResolver, "resolve")


def test_endpoint_does_not_call_sync_resolver():
    """结构判据：端点函数体内不得出现同步 resolver 的调用。

    与行为判据互补 —— 行为判据证明「orchestrator 被调用」，本条防「两条路径并存、
    同步那条又被悄悄加回来」。
    """
    from app.routers import custom_query as router_mod

    src = inspect.getsource(router_mod.cross_sheet_trace)
    tree = ast.parse(src.lstrip())
    banned = {"resolve", "full_resolve_async"}
    called_attrs = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not (banned & called_attrs), (
        f"端点直调了同步 BFS：{banned & called_attrs}（应只 await orchestrator.trace）"
    )
    assert "trace" in called_attrs, "反向自检失败：解析器没认出 orchestrator.trace 调用"
