"""热重载交接的应用侧（spec backend-startup-and-request-overhead R2.3 / R2.4 / R2.6，任务 4）。

判据：standalone 与原来相同（singleton 当场执行）；overlap 下 singleton 记 deferred、成为 primary 后在后台按原顺序
执行并回写报告（skip 条件 / 失败记录与启动时相同，失败不抛）；never 永不执行；交接退出先关 SSE 再置 should_exit；
``/api/health`` 带 reload 字段。
"""
from __future__ import annotations

import asyncio
import json
import threading
from unittest.mock import AsyncMock, patch

import pytest

from app.core import reload_handoff as rh
from app.core import startup_registry as sr
from app.core.startup_registry import StartupContext, StartupTaskSpec


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.delenv(rh.NEVER_PRIMARY_ENV, raising=False)
    saved = sr.get_startup_report()
    rh.detach()
    yield
    rh.detach()
    if saved is None:
        sr.reset_startup_report()
    else:
        sr._set_runtime_report(saved)


def _attach(primary: bool = False, *, candidate: bool = False, error_file: str = "") -> threading.Event:
    ev = threading.Event()
    if primary:
        ev.set()
    rh.attach(
        ready=threading.Event(),
        stop=threading.Event(),
        handoff_stop=threading.Event(),
        primary=ev,
        primary_ready=threading.Event(),
        primary_failed=threading.Event(),
        candidate=candidate,
        error_file=error_file,
    )
    return ev


def _specs(ran: list[str], *, fail: str | None = None, skip: str | None = None) -> list[StartupTaskSpec]:
    def make(name: str, singleton: bool, criticality: str = "critical") -> StartupTaskSpec:
        def run(_ctx):
            if name == fail:
                raise RuntimeError(f"{name} 炸了")
            ran.append(name)

        return StartupTaskSpec(name=name, phase="t", criticality=criticality, run=run, singleton=singleton,
                               skip_condition=(lambda _c: "关着") if name == skip else None)

    return [make("a", False), make("s1", True), make("b", False), make("s2", True, "best_effort")]


def _report() -> dict[str, tuple[str, str | None]]:
    return {r.name: (r.status, r.detail) for r in sr.get_startup_report()}


def test_mode_resolution(monkeypatch):
    assert (rh.mode(), rh.is_primary()) == ("standalone", True)
    primary = _attach()
    assert (rh.mode(), rh.is_primary(), rh.defers_singletons()) == ("overlap", False, True)
    primary.set()
    assert (rh.mode(), rh.is_primary()) == ("overlap", True)
    monkeypatch.setenv(rh.NEVER_PRIMARY_ENV, "1")
    assert (rh.mode(), rh.is_primary()) == ("never", False)


@pytest.mark.asyncio
async def test_standalone_runs_singletons_in_place():
    ran: list[str] = []
    ctx = StartupContext()
    results = await sr.run_startup_tasks(_specs(ran), context=ctx)
    assert ran == ["a", "s1", "b", "s2"]
    assert [r.status for r in results] == ["ok"] * 4
    assert ctx.worker_tasks == []


@pytest.mark.asyncio
async def test_overlap_defers_until_primary_then_runs_in_original_order():
    primary = _attach()
    ran: list[str] = []
    ctx = StartupContext()
    results = await sr.run_startup_tasks(_specs(ran), context=ctx)
    assert ran == ["a", "b"]
    assert [r.status for r in results] == ["ok", "deferred", "ok", "deferred"]
    assert sr.startup_report_as_dict()["deferred"] == ["s1", "s2"]
    assert len(ctx.worker_tasks) == 1, "等待 primary 的后台任务要登记进 worker_tasks（关闭时取消）"
    await asyncio.sleep(0.3)
    assert ran == ["a", "b"], "成为 primary 之前不得执行"
    primary.set()
    await asyncio.wait_for(ctx.worker_tasks[0], 5)
    assert ran == ["a", "b", "s1", "s2"]
    assert rh.primary_transition_state() == "ready"
    assert _report() == {"a": ("ok", None), "s1": ("ok", None), "b": ("ok", None), "s2": ("ok", None)}


@pytest.mark.asyncio
async def test_deferred_failure_and_skip_are_recorded_not_raised(monkeypatch):
    errors: list[str] = []
    monkeypatch.setattr(rh.logger, "error", lambda msg, *a: errors.append(msg % a))
    primary = _attach()
    ran: list[str] = []
    ctx = StartupContext()
    await sr.run_startup_tasks(_specs(ran, fail="s1", skip="s2"), context=ctx)
    primary.set()
    await asyncio.wait_for(ctx.worker_tasks[0], 5)
    report = _report()
    assert report["s1"][0] == "failed" and "s1 炸了" in report["s1"][1]
    assert report["s2"] == ("skipped", "关着")
    assert rh.primary_transition_state() == "failed"
    assert any("推迟执行的关键启动任务 s1 失败" in e for e in errors)


@pytest.mark.asyncio
async def test_never_mode_never_runs_singletons(monkeypatch):
    monkeypatch.setenv(rh.NEVER_PRIMARY_ENV, "1")
    _attach(primary=True)
    ran: list[str] = []
    ctx = StartupContext()
    await sr.run_startup_tasks(_specs(ran), context=ctx)
    assert ran == ["a", "b"] and ctx.worker_tasks == []
    status, detail = _report()["s1"]
    assert status == "deferred" and rh.NEVER_PRIMARY_ENV in detail


@pytest.mark.asyncio
async def test_shutdown_before_primary_runs_nothing():
    primary = _attach()
    ran: list[str] = []
    ctx = StartupContext()
    await sr.run_startup_tasks(_specs(ran), context=ctx)
    ctx.stop_event.set()
    await asyncio.wait_for(ctx.worker_tasks[0], 5)
    primary.set()
    assert ran == ["a", "b"] and _report()["s1"][0] == "deferred"


def test_registry_marks_exactly_the_single_process_tasks():
    singletons = {t.name for t in sr.STARTUP_TASKS if t.singleton}
    assert singletons == {"replay_startup_events", "acnr_invalidation_outbox_start", "recover_ai_chat_runs",
                          "acnr_catalog_snapshot_gc", "warm_workpaper_sync_registry", "prewarm_openapi_schema",
                          "seed_builtin_template_sets",  # 写全局内置模板集（trim-followup-residual-findings-closure R2）
                          *sr.WORKER_TASK_NAMES}
    sr.assert_sequence_matches_frozen()
    sr.assert_criticality_matches_frozen()


@pytest.mark.asyncio
async def test_drain_for_handoff_order(monkeypatch):
    """停 accept → 关 SSE → 留时间让已接下的连接读进请求 → should_exit。"""
    from app.core.runtime_state import shutdown_state
    from app.core.sse_registry import sse_registry

    monkeypatch.setattr(shutdown_state, "_draining", False)
    monkeypatch.setattr(rh, "ACCEPT_GRACE_S", 0.2)
    order: list[str] = []

    class Listener:
        def close(self):
            order.append("stop-accept")

    class Server:
        should_exit = False
        servers = [Listener(), Listener()]

    server = Server()

    async def on_close():
        order.append(f"sse-closed should_exit={server.should_exit}")

    sse_registry.register(close_callback=on_close)
    real_sleep = asyncio.sleep
    requested_sleeps: list[float] = []

    async def tracked_sleep(delay: float):
        requested_sleeps.append(delay)
        await real_sleep(delay)

    monkeypatch.setattr(rh.asyncio, "sleep", tracked_sleep)
    started = asyncio.get_running_loop().time()
    await rh.drain_for_handoff(server)
    waited = asyncio.get_running_loop().time() - started
    assert order == ["stop-accept", "stop-accept", "sse-closed should_exit=False"], order
    # Windows monotonic/event-loop timer 分辨率会让请求 0.2s 的 sleep 观测成约 0.188s；判据锁
    # 实际传给 asyncio.sleep 的 grace 值，而不是用低分辨率墙钟制造偶发红。
    assert requested_sleeps == [0.2]
    assert waited > 0.15
    assert server.should_exit is True and shutdown_state.is_draining() and sse_registry.active_count == 0
    assert rh.handoff_pre_drain_complete() is True


def test_status_snapshot_reads_parent_status_file(tmp_path, monkeypatch):
    path = tmp_path / "status.json"
    monkeypatch.setenv(rh.STATUS_FILE_ENV, str(path))
    assert rh.status_snapshot() == {
        "mode": "standalone", "primary": True, "primary_state": "ready", "candidate": False, "last": None,
    }
    path.write_text(json.dumps({
        "result": "failed",
        "reason": r"SyntaxError: C:\secret\x.py token=abc",
        "old_pid": 12,
        "phase": "candidate_start",
    }), encoding="utf-8")
    last = rh.status_snapshot()["last"]
    assert last == {"result": "failed", "reason": "SyntaxError: [PATH] [REDACTED]", "phase": "candidate_start"}
    path.write_text("{半截", encoding="utf-8")
    assert rh.status_snapshot()["last"] is None


@pytest.mark.asyncio
async def test_health_exposes_reload_field(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.api.health import router
    from app.core.database import get_db
    from app.core.redis import get_redis

    path = tmp_path / "status.json"
    path.write_text(json.dumps({"result": "ok", "duration_s": 6.1}), encoding="utf-8")
    monkeypatch.setenv(rh.STATUS_FILE_ENV, str(path))
    _attach(primary=True)

    async def _db():
        s = AsyncMock()
        s.execute = AsyncMock(return_value=None)
        yield s

    async def _redis():
        c = AsyncMock()
        c.ping = AsyncMock(return_value=True)
        yield c

    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_redis] = _redis
    clean = AsyncMock(return_value={"applied_count": 0, "failures": []})
    drift = AsyncMock(return_value={"count": 0, "critical_count": 0, "items": []})
    with patch("app.api.health._query_migration_status", new=clean), patch("app.api.health._query_schema_drift", new=drift):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            body = (await client.get("/api/health")).json()
            path.write_text(json.dumps({"result": "degraded", "phase": "primary_failed"}), encoding="utf-8")
            degraded = (await client.get("/api/health")).json()
    assert body["reload"] == {
        "mode": "overlap",
        "primary": True,
        "primary_state": "pending",
        "candidate": False,
        "last": {"result": "ok", "duration_s": 6.1},
    }
    assert body["status"] == "healthy"
    assert degraded["status"] == "degraded"
    assert degraded["reload"]["last"]["phase"] == "primary_failed"


# ── follow-up：候选 lazy routes 在 ready 前同步验证 ───────────────────────────────


def test_candidate_lazy_routes_use_production_materializer(monkeypatch):
    from app.core import lazy_api_routes as lazy

    _attach(candidate=True)
    app = type("App", (), {"router": type("Router", (), {"routes": [object(), object()]})()})()
    # 生产函数是同步函数；普通 Mock 可精确证明候选没有误走后台 scheduler。
    from unittest.mock import Mock

    materialize = Mock(return_value=[])
    background = Mock()
    monkeypatch.setattr(lazy, "materialize_all", materialize)
    monkeypatch.setattr(lazy, "schedule_background_verification", background)
    sr._task_schedule_lazy_route_verification(StartupContext(extras={"app": app}))
    materialize.assert_called_once_with(app.router.routes)
    background.assert_not_called()
    assert next(t for t in sr.STARTUP_TASKS if t.name == "verify_lazy_routes").criticality == "critical"


def test_candidate_lazy_route_failure_aborts_startup_task(monkeypatch):
    from app.core import lazy_api_routes as lazy
    from unittest.mock import Mock

    _attach(candidate=True)
    app = type("App", (), {"router": type("Router", (), {"routes": [object()]})()})()
    monkeypatch.setattr(lazy, "materialize_all", Mock(return_value=[("/bad", "TypeError: broken")]))
    with pytest.raises(RuntimeError, match="候选 lazy route 验证失败 1 项"):
        sr._task_schedule_lazy_route_verification(StartupContext(extras={"app": app}))


def test_first_worker_keeps_background_lazy_route_verification(monkeypatch):
    from app.core import lazy_api_routes as lazy
    from unittest.mock import Mock

    _attach(candidate=False)
    app = type("App", (), {"router": type("Router", (), {"routes": []})()})()
    background = Mock(return_value=True)
    materialize = Mock()
    monkeypatch.setattr(lazy, "schedule_background_verification", background)
    monkeypatch.setattr(lazy, "materialize_all", materialize)
    ctx = StartupContext(extras={"app": app})
    sr._task_schedule_lazy_route_verification(ctx)
    background.assert_called_once()
    materialize.assert_not_called()


def test_lifespan_skips_only_duplicate_handoff_predrain():
    """AST 守卫：2 s sleep 与第二次 close_all 必须同受 handoff 标记控制，HTTP drain 仍在分支外。"""
    import ast
    from pathlib import Path

    tree = ast.parse((Path(__file__).parents[1] / "app" / "main.py").read_text(encoding="utf-8"))
    lifespan = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "lifespan")
    gate = next(
        node for node in ast.walk(lifespan)
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.UnaryOp)
        and isinstance(node.test.op, ast.Not)
        and isinstance(node.test.operand, ast.Call)
        and ast.unparse(node.test.operand.func).endswith("handoff_pre_drain_complete")
    )
    gated_awaits = {ast.unparse(node.value.func) for node in ast.walk(gate) if isinstance(node, ast.Await) and isinstance(node.value, ast.Call)}
    assert "asyncio.sleep" in gated_awaits
    assert "sse_registry.close_all" in gated_awaits
    outside = [node for node in lifespan.body if node is not gate]
    outside_awaits = {
        ast.unparse(node.value.func)
        for root in outside
        for node in ast.walk(root)
        if isinstance(node, ast.Await) and isinstance(node.value, ast.Call)
    }
    assert "drain_http_requests" in outside_awaits


@pytest.mark.asyncio
async def test_candidate_lazy_route_failure_is_critical_to_startup(monkeypatch):
    from app.core import lazy_api_routes as lazy
    from unittest.mock import Mock

    _attach(candidate=True)
    app = type("App", (), {"router": type("Router", (), {"routes": [object()]})()})()
    monkeypatch.setattr(lazy, "materialize_all", Mock(return_value=[("/bad", "RuntimeError: invalid")]))
    spec = next(t for t in sr.STARTUP_TASKS if t.name == "verify_lazy_routes")
    with pytest.raises(RuntimeError, match="候选 lazy route 验证失败"):
        await sr.run_startup_tasks([spec], context=StartupContext(extras={"app": app}))
