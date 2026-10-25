# -*- coding: utf-8 -*-
"""注册缓存冷时只为本请求的 entry 准备注册（spec oo-return-to-form-dead-end-and-save-speed R2）。

钉住：
1. ``prepare_entry_only``：目标底稿没有 current representation ⇒ False（调用方整套建）；有 ⇒ True，
   绑定缓存未命中时在工作线程预热源码事实与**本 entry 自己**的模板结构 hash，命中则什么都不做；
2. ``_attach_pilot_adapters(entry_scope=...)``：冷缓存 + 有 representation ⇒ 不进全局冷建锁（锁被占也
   立刻返回）、不跑 pilot / manifest 注册、不写 ROI-0 缓存；冷缓存 + 无 representation ⇒ 照旧整套建；
   热缓存 ⇒ 照旧重放；
3. 两个生产接线点（``_registration`` / ``_apply_durable_incoming``）都把本请求的 (entry, 底稿) 交进去；
4. 源码事实预热单飞（``warm_source_facts_once``）：并发首算只算一次，冷建与按 entry 准备都经它。
"""
from __future__ import annotations

import ast
import asyncio
import importlib
import threading
import time
import uuid
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from app.routers import wp_sync_router as SR
from app.services.workpaper_sync import entry_scoped_registration as ESR
from app.services.workpaper_sync import entry_source_facts as F
from app.services.workpaper_sync import registration_template_warmup as W
from app.services.workpaper_sync import target_bound_registration as TB

ENTRY = "xlsx/r2-entry-scoped"
ROUTER = Path(SR.__file__)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(SR, "_REGISTRATION_CACHE", type(SR._REGISTRATION_CACHE)(maxsize=8))
    monkeypatch.setattr(SR, "_REGISTRATION_BUILD_LOCK", None)
    TB.clear_target_registration_cache()
    yield
    TB.clear_target_registration_cache()


def _install(monkeypatch: pytest.MonkeyPatch, *, representation: Any) -> dict[str, list]:
    """替身：指纹恒定、目标 representation 固定、四条 pilot / manifest / 两段预热都只记录。"""
    calls: dict[str, list] = {"pilot": [], "manifest": [], "facts": [], "templates": []}

    async def fake_fingerprint(svc: Any) -> str:
        return "R2-FP"

    async def fake_target(session: Any, *, wp_id: Any, entry_id: str) -> Any:
        return representation

    monkeypatch.setattr(SR, "_registration_state_fingerprint", fake_fingerprint)
    monkeypatch.setattr(TB, "target_representation_id", fake_target)
    for module_path in W.PILOT_PROVIDER_MODULES:
        async def attach(registry: Any, *, session: Any, _m: str = module_path) -> tuple[str, ...]:
            calls["pilot"].append(_m)
            return ()

        monkeypatch.setattr(importlib.import_module(module_path), "attach_pilot_adapters", attach)

    def warm_facts() -> tuple[str, ...]:
        calls["facts"].append(threading.current_thread().name)
        return ()

    def warm_templates(modules: Any) -> int:
        calls["templates"].append(tuple(modules))
        return 0

    monkeypatch.setattr(F, "warm_source_fact_caches", warm_facts)
    monkeypatch.setattr(W, "warm_template_structure_hashes", warm_templates)
    monkeypatch.setattr(W, "supplied_entry_ids", _async_value(frozenset({ENTRY})))
    return calls


def _async_value(value: Any):
    async def _fn(*_a: Any, **_k: Any) -> Any:
        return value

    return _fn


class _Registry:
    """有注册计划的最小 registry（`entry_provider_module` 从计划里取本 entry 的 provider 模块）。"""

    manifest_entries: dict[str, Any] = {}

    def __init__(self, calls: dict[str, list]) -> None:
        self._calls = calls
        self.registration_plan = (
            SimpleNamespace(entry_id=ENTRY, blocked_reason=None, provider_module="app.services.r2.entry_provider"),
            SimpleNamespace(entry_id="xlsx/other", blocked_reason=None, provider_module="app.services.r2.other"),
        )

    def registrations(self) -> tuple[Any, ...]:
        return ()

    def register(self, registration: Any) -> None:  # pragma: no cover - 空快照
        raise AssertionError("不该重放")

    async def register_from_manifest(self, *, session: Any) -> Any:
        self._calls["manifest"].append("manifest")
        return SimpleNamespace(registered_adapter_ids=())


def _context(calls: dict[str, list]) -> Any:
    return SR._RegistrationWarmupContext(session=object(), registry=_Registry(calls))


# ═══════════════════════════════════════════════════════════════════════════
# 1. prepare_entry_only
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_no_current_representation_means_the_full_build_is_needed(monkeypatch) -> None:
    calls = _install(monkeypatch, representation=None)
    ctx = _context(calls)
    assert await ESR.prepare_entry_only(session=ctx.session, registry=ctx.registry, entry_id=ENTRY, wp_id=uuid.uuid4()) is False
    assert calls["facts"] == [] and calls["templates"] == []


@pytest.mark.asyncio
async def test_binding_cache_miss_warms_only_this_entry_in_a_worker_thread(monkeypatch) -> None:
    calls = _install(monkeypatch, representation=uuid.uuid4())
    ctx = _context(calls)
    loop_thread = threading.current_thread().name
    assert await ESR.prepare_entry_only(session=ctx.session, registry=ctx.registry, entry_id=ENTRY, wp_id=uuid.uuid4()) is True
    assert len(calls["facts"]) == 1 and calls["facts"][0] != loop_thread, "源码事实首算必须在工作线程"
    assert calls["templates"] == [("app.services.r2.entry_provider",)], (
        "只预热本 entry 自己的 provider 模板（不是四条 pilot + 全部有供给 entry）"
    )


@pytest.mark.asyncio
async def test_binding_cache_hit_needs_no_warming(monkeypatch) -> None:
    rep = uuid.uuid4()
    calls = _install(monkeypatch, representation=rep)
    TB.TARGET_REGISTRATION_CACHE.put((ENTRY, str(rep)), object())
    ctx = _context(calls)
    assert await ESR.prepare_entry_only(session=ctx.session, registry=ctx.registry, entry_id=ENTRY, wp_id=uuid.uuid4()) is True
    assert calls["facts"] == [] and calls["templates"] == []


def test_entry_provider_module_reads_the_plan_and_tolerates_registries_without_one() -> None:
    reg = _Registry({"manifest": []})
    assert W.entry_provider_module(reg, ENTRY) == "app.services.r2.entry_provider"
    assert W.entry_provider_module(reg, "xlsx/not-in-plan") is None
    blocked = SimpleNamespace(registration_plan=(SimpleNamespace(entry_id=ENTRY, blocked_reason="x", provider_module="m"),))
    assert W.entry_provider_module(blocked, ENTRY) is None
    assert W.entry_provider_module(SimpleNamespace(), ENTRY) is None


# ═══════════════════════════════════════════════════════════════════════════
# 2. _attach_pilot_adapters(entry_scope=...)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cold_cache_with_representation_skips_the_global_build_and_its_lock(monkeypatch) -> None:
    calls = _install(monkeypatch, representation=uuid.uuid4())
    lock = SR._registration_build_lock()
    await lock.acquire()  # 模拟启动预热正持锁冷建
    try:
        got = await asyncio.wait_for(
            SR._attach_pilot_adapters(_context(calls), entry_scope=(ENTRY, uuid.uuid4())), timeout=2.0
        )
    finally:
        lock.release()
    assert got == ()
    assert calls["pilot"] == [] and calls["manifest"] == [], "不得跑整套注册"
    assert SR._REGISTRATION_CACHE.get("R2-FP") is None, "不得把部分注册写进 ROI-0 缓存"


@pytest.mark.asyncio
async def test_cold_cache_without_representation_still_builds_everything(monkeypatch) -> None:
    calls = _install(monkeypatch, representation=None)
    await SR._attach_pilot_adapters(_context(calls), entry_scope=(ENTRY, uuid.uuid4()))
    assert sorted(calls["pilot"]) == sorted(W.PILOT_PROVIDER_MODULES)
    assert calls["manifest"] == ["manifest"]
    assert SR._REGISTRATION_CACHE.get("R2-FP") is not None


@pytest.mark.asyncio
async def test_no_entry_scope_keeps_the_full_build(monkeypatch) -> None:
    """启动预热等调用方不给 entry_scope：照旧整套建（有 representation 也一样）。"""
    calls = _install(monkeypatch, representation=uuid.uuid4())
    await SR._attach_pilot_adapters(_context(calls))
    assert calls["manifest"] == ["manifest"]


@pytest.mark.asyncio
async def test_warm_cache_replays_without_preparing(monkeypatch) -> None:
    calls = _install(monkeypatch, representation=uuid.uuid4())
    SR._REGISTRATION_CACHE.put("R2-FP", SR._RegistrationSnapshot(registrations=(), adapter_ids=("a",)))
    got = await SR._attach_pilot_adapters(_context(calls), entry_scope=(ENTRY, uuid.uuid4()))
    assert got == ("a",)
    assert calls["facts"] == [] and calls["templates"] == [] and calls["manifest"] == []


# ═══════════════════════════════════════════════════════════════════════════
# 3. 生产接线（AST：注释 / docstring 不算）
# ═══════════════════════════════════════════════════════════════════════════


def _function(name: str) -> ast.AST:
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    return next(
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    )


@pytest.mark.parametrize(
    ("func", "entry_expr", "wp_expr"),
    [
        ("_registration", "scope.entry_id", "scope.wp_id"),
        ("_apply_durable_incoming", "str(app_row.entry_id)", "app_row.wp_id"),
    ],
)
def test_production_paths_hand_their_own_entry_and_workpaper(func: str, entry_expr: str, wp_expr: str) -> None:
    calls = [
        node for node in ast.walk(_function(func))
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_attach_pilot_adapters"
    ]
    assert len(calls) == 1, f"{func} 里 `_attach_pilot_adapters` 调用应恰一处：{len(calls)}"
    scope_kw = [kw for kw in calls[0].keywords if kw.arg == "entry_scope"]
    assert scope_kw, f"{func} 没把 entry_scope 交给共享注册入口 ⇒ 冷缓存仍排在全局锁后面"
    value = scope_kw[0].value
    assert isinstance(value, ast.Tuple) and [ast.unparse(e) for e in value.elts] == [entry_expr, wp_expr]


# ═══════════════════════════════════════════════════════════════════════════
# 4. 源码事实预热单飞
# ═══════════════════════════════════════════════════════════════════════════


def test_concurrent_source_fact_warmups_compute_each_fact_once(monkeypatch) -> None:
    """``lru_cache`` 不合并并发首算：不经单飞时 4 个线程各算一遍（重载后预热与回调各扫一遍前端源码）。"""
    counts: dict[str, int] = {}

    def make(name: str):
        @lru_cache(maxsize=1)
        def fact() -> str:
            counts[name] = counts.get(name, 0) + 1
            time.sleep(0.05)
            return name

        return fact

    for name in F._WARMABLE_SOURCE_FACTS:
        monkeypatch.setattr(F, name, make(name))
    threads = [threading.Thread(target=W.warm_source_facts_once) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert set(counts) == set(F._WARMABLE_SOURCE_FACTS), counts
    assert all(n == 1 for n in counts.values()), f"并发首算各算了多次：{counts}"


def _to_thread_targets(tree: ast.AST) -> set[str]:
    return {
        node.args[0].id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "to_thread"
        and node.args and isinstance(node.args[0], ast.Name)
    }


def test_both_paths_warm_source_facts_through_the_single_flight() -> None:
    """冷建与按 entry 准备必须经同一个单飞入口，否则二者照样各算一遍。"""
    for tree in (_function("_attach_pilot_adapters"), ast.parse(Path(ESR.__file__).read_text(encoding="utf-8"))):
        targets = _to_thread_targets(tree)
        assert "warm_source_facts_once" in targets and "warm_source_fact_caches" not in targets, targets
