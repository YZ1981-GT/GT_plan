"""``AddressingService.resolve_many`` 带会话时顺序执行（acnr-foundation-defect-closure T14，design §1.2）。

同一个 AsyncSession 不能被并发协程同时使用；原来 ``asyncio.gather`` 让多个 ``full_resolve`` 同时用同一会话。
在 ``full_resolve`` 这一层（被测函数的下一层）放计数桩：带 db 时同时在途恰为 1、结果与输入同序且每项带
``result``；不带 db 照旧并发（在途 > 1）。改回 gather ⇒ 第一例红。
"""
from __future__ import annotations

import asyncio

from app.services.acnr.resolver import ResolveResult
from app.services.custom_query import addressing_service as mod


def _install(monkeypatch):
    state = {"now": 0, "peak": 0, "order": []}

    async def _fake(**kwargs):
        state["now"] += 1
        state["peak"] = max(state["peak"], state["now"])
        await asyncio.sleep(0.01)
        state["now"] -= 1
        addr = kwargs.get("addr_id") or "?"
        state["order"].append(addr)
        return ResolveResult(found=True, addr_id=addr, entry_type="cell", source_layer="L1_cell")

    monkeypatch.setattr(mod, "full_resolve", _fake)
    return state


async def test_with_session_runs_one_at_a_time(monkeypatch):
    state = _install(monkeypatch)
    raws = ["E1/E1-14/C10", "E1/E1-15/C8", "E1/E1-14/C10"]
    got = await mod.AddressingService().resolve_many(raws, project_id="p", db=object())
    assert state["peak"] == 1
    assert [t.raw for t in got] == raws and state["order"] == raws
    assert all(t.result is not None and t.result.addr_id == t.raw for t in got)


async def test_without_session_still_concurrent(monkeypatch):
    state = _install(monkeypatch)
    got = await mod.AddressingService().resolve_many(["a/b/C1", "a/b/C2", "a/b/C3"], db=None)
    assert state["peak"] > 1 and [t.raw for t in got] == ["a/b/C1", "a/b/C2", "a/b/C3"]
