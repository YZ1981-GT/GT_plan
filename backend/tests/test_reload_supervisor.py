"""热重载交接的父进程与 worker 入口（spec backend-startup-and-request-overhead R2.1 / R2.2 / R2.4 / R2.5，任务 5）。

父进程用假子进程：新 worker 就绪后才停旧的、停完才给新的 primary；新 worker 起不来 / 超时没就绪时旧的照常服务并写
状态文件；旧 worker 不退出时超时强制结束；shutdown 全部退出。worker 入口用假 server：就绪置 ready、收到 stop 先关 SSE
再置 should_exit、启动失败把原因写进错误文件。另有项目事件流在 drain 时立刻收到 server_draining。
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
import types
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import uvicorn

import reload_supervisor as rs
from app.core import reload_handoff


class FakeProcess:
    """按脚本行动的假子进程：ready_after 秒后就绪（None = 不就绪）；exit_after 秒后自己退出（None = 不退出）；
    收到 stop 后 stop_delay 秒退出（None = 不理 stop，只能 terminate）。"""

    _next_pid = 1000

    def __init__(
        self,
        worker_events,
        log,
        name,
        *,
        ready_after=0.05,
        exit_after=None,
        stop_delay=0.05,
        error=None,
        primary_after=0.02,
        primary_failure=None,
    ):
        FakeProcess._next_pid += 1
        self.pid = FakeProcess._next_pid
        self.exitcode = None
        self.events, self.log, self.name = worker_events, log, name
        self.ready_after, self.exit_after, self.stop_delay, self.error = ready_after, exit_after, stop_delay, error
        self.primary_after, self.primary_failure = primary_after, primary_failure
        self._exited = threading.Event()
        self.terminated = False

    def start(self) -> None:
        threading.Thread(target=self._script, daemon=True).start()

    def _exit(self, code: int) -> None:
        if not self._exited.is_set():
            self.exitcode = code
            self.log.append(f"{self.name} exited")
            self._exited.set()

    def _script(self) -> None:
        t0 = time.monotonic()
        primary_started = None
        ready, stop, _handoff_stop, primary, primary_ready, primary_failed, error_file = self.events
        while not self._exited.is_set():
            now = time.monotonic() - t0
            if self.exit_after is not None and now >= self.exit_after:
                if self.error:
                    Path(error_file).write_text(self.error, encoding="utf-8")
                self._exit(1)
                return
            if self.ready_after is not None and now >= self.ready_after and not ready.is_set():
                self.log.append(f"{self.name} ready")
                ready.set()
            if primary.is_set() and primary_started is None:
                primary_started = now
            if primary_started is not None and self.primary_after is not None and now - primary_started >= self.primary_after:
                if self.primary_failure:
                    Path(error_file).write_text(self.primary_failure, encoding="utf-8")
                    primary_failed.set()
                else:
                    primary_ready.set()
            if stop.is_set() and self.stop_delay is not None:
                time.sleep(self.stop_delay)
                self._exit(0)
                return
            time.sleep(0.01)

    def is_alive(self) -> bool:
        return not self._exited.is_set()

    def join(self, timeout=None) -> None:
        self._exited.wait(timeout)

    def terminate(self) -> None:
        self.terminated = True
        self.log.append(f"{self.name} terminated")
        self._exit(-15)


class LoggedEvent(threading.Event):
    def __init__(self, log, label):
        super().__init__()
        self.log, self.label = log, label

    def set(self) -> None:
        if not self.is_set():
            self.log.append(self.label)
        super().set()


@pytest.fixture
def make_sup(tmp_path, monkeypatch):
    monkeypatch.setenv(rs.STATUS_FILE_ENV, str(tmp_path / "status.json"))
    monkeypatch.setenv("GT_RELOAD_STOP_TIMEOUT", "2")
    monkeypatch.setenv("GT_RELOAD_READY_TIMEOUT", "3")
    log: list[str] = []
    plans: list[dict] = []
    sockets: list[types.SimpleNamespace] = []

    def factory():
        config = uvicorn.Config("app.main:app", reload=True, reload_dirs=[str(tmp_path)], port=9999)
        sock = types.SimpleNamespace(closed=False)
        sock.close = lambda: setattr(sock, "closed", True)
        sockets.append(sock)
        sup = rs.OverlapReload(config, target=lambda sockets=None: None, sockets=[sock])
        count = {"n": 0}

        def spawn(*, candidate: bool):
            count["n"] += 1
            name = f"w{count['n']}"
            plan = plans.pop(0) if plans else {}
            err = tmp_path / f"{name}.err"
            ready = LoggedEvent(log, f"{name} ready-flag")
            stop = LoggedEvent(log, f"stop {name}")
            handoff_stop = LoggedEvent(log, f"handoff {name}")
            primary = LoggedEvent(log, f"primary {name}")
            primary_ready = LoggedEvent(log, f"primary-ready {name}")
            primary_failed = LoggedEvent(log, f"primary-failed {name}")
            process = FakeProcess(
                (ready, stop, handoff_stop, primary, primary_ready, primary_failed, err), log, name, **plan,
            )
            process.start()
            return rs._Worker(
                process,
                ready,
                stop,
                handoff_stop,
                primary,
                primary_ready,
                primary_failed,
                candidate,
                err,
            )

        monkeypatch.setattr(sup, "_spawn", spawn)
        return sup

    factory.log, factory.plans, factory.sockets = log, plans, sockets
    factory.status = lambda: json.loads((tmp_path / "status.json").read_text(encoding="utf-8"))
    return factory


def _order(log: list[str], *labels: str) -> list[int]:
    return [log.index(x) for x in labels]


def test_startup_first_worker_is_primary_immediately(make_sup):
    sup = make_sup()
    sup.startup()
    w1 = sup.serving
    assert w1.primary.is_set() and w1.candidate is False and make_sup.status()["result"] == "started"
    sup.shutdown()


def test_restart_stops_old_only_after_new_is_ready_then_hands_primary(make_sup):
    sup = make_sup()
    sup.startup()
    old = sup.serving
    make_sup.plans.append({"ready_after": 0.3})
    sup.restart()
    new = sup.serving
    log = make_sup.log
    a, b, c, d = _order(log, "w2 ready", "stop w1", "w1 exited", "primary w2")
    assert a < b < c < d, log
    assert sup.workers == [new] and new is not old and new.candidate is True and not old.process.terminated
    st = make_sup.status()
    assert (st["result"], st["phase"], st["forced_stop"], st["old_pid"], st["new_pid"]) == (
        "ok", "primary_ready", False, old.pid, new.pid,
    )
    assert st["spawn_to_ready_s"] >= 0.25
    assert st["ready_to_old_exit_s"] >= 0
    assert st["old_exit_to_primary_ready_s"] >= 0
    sup.shutdown()


def test_new_worker_that_dies_keeps_old_serving(make_sup):
    sup = make_sup()
    sup.startup()
    old = sup.serving
    make_sup.plans.append({"ready_after": None, "exit_after": 0.1, "error": "SyntaxError: invalid syntax (x.py, line 3)"})
    sup.restart()
    assert sup.workers == [old] and old.process.is_alive() and not old.stop.is_set()
    st = make_sup.status()
    assert st["result"] == "failed" and st["reason"] == "SyntaxError: invalid syntax (x.py, line 3)"
    assert st["serving_pid"] == old.pid
    sup.shutdown()


def test_new_worker_never_ready_times_out_and_is_stopped(make_sup, monkeypatch):
    sup = make_sup()
    sup.ready_timeout = 0.3
    sup.startup()
    old = sup.serving
    make_sup.plans.append({"ready_after": None})
    sup.restart()
    assert sup.workers == [old] and not old.stop.is_set()
    assert "stop w2" in make_sup.log and "w2 exited" in make_sup.log
    assert "内没有就绪" in make_sup.status()["reason"]
    sup.shutdown()


def test_old_worker_ignoring_stop_is_terminated_after_timeout(make_sup):
    sup = make_sup()
    sup.stop_timeout = 0.3
    make_sup.plans.append({"stop_delay": None})
    sup.startup()
    old = sup.serving
    sup.restart()
    log = make_sup.log
    assert old.process.terminated
    assert log.index("w1 terminated") < log.index("primary w2"), log
    assert make_sup.status()["forced_stop"] is True
    sup.shutdown()


def test_shutdown_stops_every_live_worker_and_closes_sockets(make_sup):
    sup = make_sup()
    sup.stop_timeout = 0.3
    make_sup.plans.append({"stop_delay": None})
    sup.startup()
    w1 = sup.serving
    sup.shutdown()
    assert w1.stop.is_set() and not w1.handoff_stop.is_set()
    assert w1.process.terminated and not w1.process.is_alive()
    assert all(s.closed for s in make_sup.sockets)


def test_install_switch(monkeypatch):
    import importlib

    um = importlib.import_module("uvicorn.main")  # `import uvicorn.main as um` 拿到的是同名 click 命令
    original = um.ChangeReload
    try:
        monkeypatch.setenv("GT_OVERLAP_RELOAD", "0")
        assert rs.install() is False and um.ChangeReload is original
        monkeypatch.delenv("GT_OVERLAP_RELOAD")
        assert rs.install() is True and um.ChangeReload is rs.OverlapReload
    finally:
        um.ChangeReload = original


def test_run_uvicorn_installs_before_main():
    import ast

    src = (Path(rs.__file__).with_name("run_uvicorn.py")).read_text(encoding="utf-8")
    main_block = next(n for n in ast.parse(src).body if isinstance(n, ast.If))
    calls = [ast.unparse(n.value) for n in main_block.body if isinstance(n, ast.Expr)]
    assert calls.index("reload_supervisor.install()") < calls.index("main(windows_expand_args=False)")


# ── worker 入口（子进程里那一半）────────────────────────────────────────────────────


class FakeServer:
    def __init__(self, behaviour: str = "serve") -> None:
        self.started = False
        self.should_exit = False
        self.servers: list = []
        self.behaviour = behaviour

    def run(self, sockets=None) -> None:
        if self.behaviour == "raise":
            raise SyntaxError("bad syntax")
        if self.behaviour == "log_and_return":
            try:
                raise RuntimeError("db down")
            except RuntimeError as exc:
                logging.getLogger("uvicorn.error").error("Exception in 'lifespan' protocol\n", exc_info=exc)
            logging.getLogger("uvicorn.error").error("Application startup failed. Exiting.")
            return

        async def main() -> None:
            loop = asyncio.get_running_loop()
            if self.behaviour == "serve":
                self.servers = [types.SimpleNamespace(get_loop=lambda: loop, close=lambda: None)]
                self.started = True
            while not self.should_exit:
                await asyncio.sleep(0.01)

        asyncio.run(main())


@pytest.fixture
def events():
    ready = threading.Event()
    stop = threading.Event()
    handoff_stop = threading.Event()
    primary = threading.Event()
    primary_ready = threading.Event()
    primary_failed = threading.Event()
    yield ready, stop, handoff_stop, primary, primary_ready, primary_failed
    stop.set()  # 让没就绪就退出的用例留下的监视线程结束
    reload_handoff.detach()


def _worker_target(server, events, error_file: Path, *, candidate: bool = False):
    ready, stop, handoff_stop, primary, primary_ready, primary_failed = events
    return rs._WorkerTarget(
        server.run,
        ready,
        stop,
        handoff_stop,
        primary,
        primary_ready,
        primary_failed,
        candidate,
        str(error_file),
    )


def test_worker_target_ready_then_drains_sse_before_exit(events, tmp_path, monkeypatch):
    from app.core.runtime_state import shutdown_state
    from app.core.sse_registry import sse_registry

    monkeypatch.setattr(shutdown_state, "_draining", False)
    ready, stop, handoff_stop, _primary, _primary_ready, _primary_failed = events
    server = FakeServer()
    target = _worker_target(server, events, tmp_path / "w.err", candidate=True)
    th = threading.Thread(target=target, daemon=True)
    th.start()
    assert ready.wait(3), "server.started 之后要置 ready"
    assert reload_handoff.mode() == "overlap" and reload_handoff.is_candidate() is True
    seen: list[bool] = []

    async def on_close():
        seen.append(server.should_exit)

    sse_registry.register(close_callback=on_close)
    handoff_stop.set()
    stop.set()
    th.join(3)
    assert not th.is_alive() and seen == [False] and server.should_exit and shutdown_state.is_draining()
    assert not (tmp_path / "w.err").exists()


def test_worker_target_records_exception_before_ready(events, tmp_path):
    ready = events[0]
    target = _worker_target(FakeServer("raise"), events, tmp_path / "w.err", candidate=True)
    with pytest.raises(SyntaxError):
        target()
    assert (tmp_path / "w.err").read_text(encoding="utf-8") == "SyntaxError: bad syntax"
    assert not ready.is_set()


def test_worker_target_records_logged_startup_failure(events, tmp_path):
    target = _worker_target(FakeServer("log_and_return"), events, tmp_path / "w.err", candidate=True)
    target()
    assert (tmp_path / "w.err").read_text(encoding="utf-8") == (
        "RuntimeError: db down；Application startup failed. Exiting.")


def test_worker_target_stop_before_ready_exits(events, tmp_path):
    ready, stop = events[:2]
    server = FakeServer("never_ready")
    stop.set()
    th = threading.Thread(target=_worker_target(server, events, tmp_path / "w.err", candidate=True), daemon=True)
    th.start()
    th.join(3)
    assert not th.is_alive() and server.should_exit and not ready.is_set()


# ── 项目事件流：drain 时立刻收到 server_draining（不必等 30 s 心跳）──────────────────


@pytest.mark.asyncio
async def test_project_event_stream_gets_server_draining_promptly():
    import uuid

    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_db
    from app.core.sse_registry import sse_registry
    from app.deps import get_current_user_sse
    from app.routers import events as events_router

    app = FastAPI()
    app.include_router(events_router.router)
    app.dependency_overrides[get_current_user_sse] = lambda: types.SimpleNamespace(id=uuid.uuid4())

    async def _db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = _db
    before = sse_registry.active_count
    with patch.object(events_router, "check_project_access", new=AsyncMock(return_value=None)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
            req = asyncio.create_task(client.get(f"/api/projects/{uuid.uuid4()}/events/stream"))
            for _ in range(200):
                if sse_registry.active_count > before:
                    break
                await asyncio.sleep(0.01)
            assert sse_registry.active_count > before, "事件流应已登记进 sse_registry"
            started = time.monotonic()
            await sse_registry.close_all()
            resp = await asyncio.wait_for(req, 5)
    assert time.monotonic() - started < 2
    body = resp.text
    assert body.startswith("event: connected") and body.rstrip().endswith("event: server_draining\ndata: {}")


# ── follow-up：候选稳定性 / primary 状态机 / 分段计时 ───────────────────────────────


def test_candidate_dies_during_stability_keeps_old_serving(make_sup):
    sup = make_sup()
    sup.stability_seconds = 0.3
    sup.startup()
    old = sup.serving
    make_sup.plans.append({"ready_after": 0.02, "exit_after": 0.12, "error": "candidate crashed"})
    sup.restart()
    assert sup.serving is old and old.process.is_alive() and not old.stop.is_set()
    status = make_sup.status()
    assert status["result"] == "failed" and status["phase"] == "candidate_stability"
    assert status["spawn_to_ready_s"] is not None and status["ready_to_old_exit_s"] is None
    sup.shutdown()


def test_candidate_dies_while_old_drains_starts_one_recovery_worker(make_sup):
    sup = make_sup()
    sup.stability_seconds = 0.1
    make_sup.plans.append({"stop_delay": 0.45})
    sup.startup()
    old = sup.serving
    make_sup.plans.extend([
        {"ready_after": 0.02, "exit_after": 0.2, "error": "candidate drain crash"},
        {"ready_after": 0.02},
    ])
    sup.restart()
    recovery = sup.serving
    status = make_sup.status()
    assert recovery is not None and recovery is not old and recovery.process.is_alive()
    assert status["result"] == "degraded"
    assert status["phase"] == "recovered_after_candidate_failure"
    assert "candidate drain crash" in status["reason"]
    assert status["old_exit_to_primary_ready_s"] is not None
    sup.shutdown()


def test_primary_critical_failure_is_degraded_not_ok(make_sup):
    sup = make_sup()
    sup.stability_seconds = 0
    sup.primary_timeout = 0.3
    sup.startup()
    make_sup.plans.append({"primary_failure": "replay_startup_events: redis down"})
    sup.restart()
    status = make_sup.status()
    assert status["result"] == "degraded"
    assert status["phase"] == "primary_failed"
    assert "replay_startup_events" in status["reason"]
    assert sup.serving is not None and sup.serving.process.is_alive()
    sup.shutdown()


def test_reload_reason_is_sanitized_before_status_file(make_sup):
    sup = make_sup()
    sup.startup()
    make_sup.plans.append({
        "ready_after": None,
        "exit_after": 0.05,
        "error": r"RuntimeError C:\private\secrets.py token=top-secret",
    })
    sup.restart()
    reason = make_sup.status()["reason"]
    assert "private" not in reason and "top-secret" not in reason
    assert reason.count("[REDACTED]") == 2
    sup.shutdown()


def test_worker_target_normal_stop_does_not_run_handoff_predrain(events, tmp_path, monkeypatch):
    ready, stop = events[:2]
    server = FakeServer()
    drained = AsyncMock()
    monkeypatch.setattr(reload_handoff, "drain_for_handoff", drained)
    th = threading.Thread(target=_worker_target(server, events, tmp_path / "normal.err"), daemon=True)
    th.start()
    assert ready.wait(3)
    stop.set()
    th.join(3)
    assert not th.is_alive() and server.should_exit is True
    drained.assert_not_awaited()
    assert reload_handoff.handoff_pre_drain_complete() is False


def test_old_drain_loop_checks_candidate_liveness_by_ast():
    import ast
    import inspect
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(rs.OverlapReload._drain_old_while_monitoring)))
    loop = next(node for node in ast.walk(tree) if isinstance(node, ast.While))
    calls = {ast.unparse(node.func) for node in ast.walk(loop) if isinstance(node, ast.Call)}
    assert "candidate.process.is_alive" in calls
