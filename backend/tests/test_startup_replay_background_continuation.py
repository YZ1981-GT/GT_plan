# -*- coding: utf-8 -*-
"""事件恢复整体移出启动路径（spec runtime-performance-and-reload-hardening-followup R3.3）。

🔴 判据来自真实重启实测，不是推演：恢复要对每条条目真实重跑业务 handler（带 DB 往返），真库 PEL
积压 264 条时**一批 25 条**也超过原来的 ``wait_for(5s)``；超时异常被启动任务的 ``except`` 吞掉后
报告从不更新、后台续跑也排不上 ⇒ 启动报告实测 ``replay_startup_events=5047ms`` 且
``events.replay_available=False``（恢复一条没做）。因此启动任务只许**排后台任务**。

判据：启动任务不在前台调 `replay_pending_events`；总是排一个后台 drain 任务（进 `worker_tasks`，
关闭时随 worker 取消）；后台完成后把条数与剩余 pending 回写启动报告；Redis 不可用记 skipped；
`stop_event` 已置位时不恢复。
"""
from __future__ import annotations

import asyncio
import inspect

import pytest

from app.core import startup_registry as sr
from app.core.startup_registry import StartupContext


class _Bus:
    def __init__(self, report: dict, *, recovered: int = 0, boom: bool = False) -> None:
        self.report = report
        self.recovered = recovered
        self.boom = boom
        self.foreground_replays = 0
        self.drains = 0
        self.stop_events: list[object] = []

    async def replay_pending_events(self, **_kwargs) -> int:
        self.foreground_replays += 1
        return 0

    def get_replay_report(self) -> dict:
        return dict(self.report)

    async def drain_pending_events_in_background(self, stop_event=None) -> int:
        self.drains += 1
        self.stop_events.append(stop_event)
        if self.boom:
            raise RuntimeError("redis 掉了")
        if stop_event is not None and stop_event.is_set():
            return 0
        return self.recovered


def _patch(monkeypatch, bus: _Bus, *, delay: float = 0.0) -> None:
    """只替换事件总线；同任务里的导入 outbox 重放不连真库（否则留下未关闭连接）。"""
    import app.core.database as database
    import app.services.event_bus as eb

    monkeypatch.setattr(eb, "event_bus", bus)
    monkeypatch.setattr(sr, "EVENT_DRAIN_START_DELAY_S", delay)

    def _no_db(*_args, **_kwargs):
        raise RuntimeError("本用例不连数据库")

    monkeypatch.setattr(database, "async_session", _no_db)


def _report_of(name: str) -> tuple[str, str | None]:
    item = next(r for r in (sr.get_startup_report() or ()) if r.name == name)
    return item.status, item.detail


@pytest.fixture(autouse=True)
def _keep_report():
    saved = sr.get_startup_report()
    yield
    if saved is None:
        sr.reset_startup_report()
    else:
        sr._set_runtime_report(saved)


def _seed_report() -> None:
    sr._set_runtime_report([
        sr.StartupTaskResult("replay_startup_events", "handlers", "ok", 0, None),
    ])


@pytest.mark.asyncio
async def test_startup_never_replays_in_foreground(monkeypatch):
    bus = _Bus({"redis_available": True, "pending_remaining": 120}, recovered=25)
    _patch(monkeypatch, bus)
    _seed_report()
    ctx = StartupContext()
    await sr._task_replay_startup_events(ctx)
    assert bus.foreground_replays == 0, "启动路径上不得 await 任何一批恢复"
    assert len(ctx.worker_tasks) == 1, "恢复要登记成 worker 任务，关闭时一起取消"
    await asyncio.gather(*ctx.worker_tasks)
    assert bus.drains == 1 and bus.stop_events == [ctx.stop_event]
    status, detail = _report_of("replay_startup_events")
    assert status == "ok" and "后台恢复 25 条" in detail and "剩余 pending 120" in detail


@pytest.mark.asyncio
async def test_background_drain_records_redis_unavailable_as_skipped(monkeypatch):
    bus = _Bus({"redis_available": False, "pending_remaining": None, "last_error": "redis down"})
    _patch(monkeypatch, bus)
    _seed_report()
    ctx = StartupContext()
    await sr._task_replay_startup_events(ctx)
    await asyncio.gather(*ctx.worker_tasks)
    status, detail = _report_of("replay_startup_events")
    assert status == "skipped" and "redis down" in detail and "补拉不可用" in detail


@pytest.mark.asyncio
async def test_background_drain_failure_is_recorded_not_raised(monkeypatch):
    bus = _Bus({"redis_available": True}, boom=True)
    _patch(monkeypatch, bus)
    _seed_report()
    ctx = StartupContext()
    await sr._task_replay_startup_events(ctx)
    await asyncio.gather(*ctx.worker_tasks)
    status, detail = _report_of("replay_startup_events")
    assert status == "failed" and "RuntimeError: redis 掉了" in detail


@pytest.mark.asyncio
async def test_shutdown_before_drain_recovers_nothing(monkeypatch):
    bus = _Bus({"redis_available": True, "pending_remaining": 7}, recovered=9)
    _patch(monkeypatch, bus)
    _seed_report()
    ctx = StartupContext()
    ctx.stop_event.set()
    await sr._task_replay_startup_events(ctx)
    await asyncio.gather(*ctx.worker_tasks)
    status, detail = _report_of("replay_startup_events")
    assert status == "ok" and "后台恢复 0 条" in detail


def test_startup_task_body_has_no_foreground_replay():
    """静态判据走 AST，不走文本匹配。

    🔴 首版用 `"wait_for" not in src` 当场被自己的 docstring 咬住（里面写着「超过
    ``wait_for(5s)``」）—— 注释与 docstring 正反两向都会骗过文本匹配（memory 铁律 ㉖）。
    AST 里 docstring 是 ``Expr(Constant)``，不产生 Name / Attribute / Call 节点。
    """
    import ast
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(sr._task_replay_startup_events)))

    def tail(node: ast.AST) -> str:
        return ast.unparse(node).split(".")[-1]

    called = {tail(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
    assert "replay_pending_events" not in called, "启动任务体不得前台调恢复"
    assert "wait_for" not in called, "不得再用 wait_for 在前台等恢复"

    # 🔴 只断言「_drain_events_after_ready 被调用」不够：把它换成 `await _drain_events_after_ready(ctx)`
    # 照样是一次 Call，首版判据因此让这条退化存活。要判的是**排成后台任务并登记**这一形态。
    scheduled = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and tail(node.func) == "create_task"
        and node.args
        and isinstance(node.args[0], ast.Call)
        and tail(node.args[0].func) == "_drain_events_after_ready"
    ]
    registered = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and tail(node.func) == "append"
        and "worker_tasks" in ast.unparse(node.func)
        and node.args
        and ast.unparse(node.args[0]) == "drain_task"
    ]
    assert len(scheduled) == len(registered) == 1, (
        "恢复必须 create_task 后登记进 ctx.worker_tasks", scheduled, registered
    )
    awaited = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Await)
        and isinstance(node.value, ast.Call)
        and tail(node.value.func) == "_drain_events_after_ready"
    ]
    assert not awaited, "不得在启动路径上直接 await 恢复"


@pytest.mark.asyncio
async def test_drain_waits_before_starting_so_report_writeback_survives(monkeypatch):
    """起跑延迟是必需的，不是保险。

    🔴 真实重启实测：后台任务若立刻开跑，回写会被 `run_startup_tasks` 随后的
    `_set_runtime_report(results)` 整份覆盖 —— 启动报告里 `replay_startup_events` 的 detail
    实测为空。判据同时锁住「默认延迟 > 0」与「延迟真的被 await」。
    """
    assert sr.EVENT_DRAIN_START_DELAY_S > 0, "默认起跑延迟必须 > 0"

    bus = _Bus({"redis_available": True, "pending_remaining": 0}, recovered=3)
    _patch(monkeypatch, bus, delay=0.25)
    _seed_report()
    ctx = StartupContext()
    await sr._task_replay_startup_events(ctx)
    await asyncio.sleep(0.05)
    assert bus.drains == 0, "延迟期间不得开始恢复"
    await asyncio.gather(*ctx.worker_tasks)
    assert bus.drains == 1
    status, detail = _report_of("replay_startup_events")
    assert status == "ok" and "后台恢复 3 条" in detail


def test_drain_delay_is_configurable_by_env():
    import ast
    import inspect as _inspect
    import textwrap

    src = textwrap.dedent(_inspect.getsource(sr))
    tree = ast.parse(src)
    assign = next(
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "EVENT_DRAIN_START_DELAY_S" for t in node.targets)
    )
    assert "GT_EVENT_DRAIN_DELAY" in ast.unparse(assign.value)
