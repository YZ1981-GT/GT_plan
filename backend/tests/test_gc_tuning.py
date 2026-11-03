"""进程级 GC 调优（spec writeback-followup-issue-closure R9 / P12）。

判据：①冷建之前抬 gen0 阈值、开关关掉则不动；②预热结束后先回收预热期的循环垃圾再冻结（垃圾不被冻住）；
③关闭阶段取消不冻结、取消原样抛出；预热失败照样冻结、异常照样抛出；④启动清单里的预热任务真的接上了
这两步。实测收益见 `app/core/gc_tuning.py` 模块说明。用例结束一律恢复解释器原状（阈值 / unfreeze）。
"""
from __future__ import annotations

import asyncio
import gc
import weakref

import pytest

from app.core import gc_tuning


@pytest.fixture(autouse=True)
def _restore_gc(monkeypatch):
    original = gc.get_threshold()
    monkeypatch.delenv("GT_GC_TUNING", raising=False)
    yield
    gc.unfreeze()
    gc.set_threshold(*original)


class _Node:
    def __init__(self) -> None:
        self.peer: _Node | None = None


def test_configure_raises_gen0_only():
    gc.set_threshold(700, 10, 10)
    assert gc_tuning.configure_gc() is True
    assert gc.get_threshold() == (10_000, 10, 10) == gc_tuning.GC_THRESHOLD


def test_switch_off_leaves_the_interpreter_alone(monkeypatch):
    monkeypatch.setenv("GT_GC_TUNING", "0")
    gc.set_threshold(700, 10, 10)
    assert gc_tuning.configure_gc() is False
    assert gc.get_threshold() == (700, 10, 10)


@pytest.mark.asyncio
async def test_freezes_after_the_work_and_collects_its_garbage_first():
    probe: list[weakref.ref] = []

    async def work() -> None:
        a, b = _Node(), _Node()
        a.peer, b.peer = b, a  # 预热期的循环垃圾：只有循环回收能放掉
        probe.append(weakref.ref(a))

    gc.unfreeze()
    await gc_tuning.run_then_freeze(work)
    assert gc.get_freeze_count() > 0
    assert probe[0]() is None, "冻结前没先回收 ⇒ 预热期的垃圾被永久冻住"


@pytest.mark.asyncio
async def test_switch_off_does_not_freeze(monkeypatch):
    monkeypatch.setenv("GT_GC_TUNING", "0")
    gc.unfreeze()

    async def work() -> None:
        return None

    await gc_tuning.run_then_freeze(work)
    assert gc.get_freeze_count() == 0


@pytest.mark.asyncio
async def test_cancelled_at_shutdown_does_not_freeze():
    gc.unfreeze()
    started = asyncio.Event()

    async def work() -> None:
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(gc_tuning.run_then_freeze(work))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert gc.get_freeze_count() == 0


@pytest.mark.asyncio
async def test_failed_prewarm_still_freezes_and_reraises():
    gc.unfreeze()

    async def work() -> None:
        raise RuntimeError("预热炸了")

    with pytest.raises(RuntimeError):
        await gc_tuning.run_then_freeze(work)
    assert gc.get_freeze_count() > 0


@pytest.mark.asyncio
async def test_startup_prewarm_task_is_wired(monkeypatch):
    from app.core import startup_registry
    from app.services.workpaper_sync import startup_prewarm

    ran: list[str] = []

    async def fake_prewarm() -> None:
        ran.append("prewarm")

    monkeypatch.setattr(startup_prewarm, "warm_workpaper_sync_registry", fake_prewarm)
    gc.set_threshold(700, 10, 10)
    gc.unfreeze()
    ctx = startup_registry.StartupContext()
    startup_registry._task_schedule_workpaper_sync_prewarm(ctx)
    assert gc.get_threshold() == gc_tuning.GC_THRESHOLD, "阈值要在冷建开始之前就抬"
    await asyncio.wait_for(ctx.worker_tasks[0], timeout=5)
    assert ran == ["prewarm"] and gc.get_freeze_count() > 0


# ── 导入期就抬阈值（spec backend-startup-and-request-overhead R1.4）──────────────────────────
# 导入 app.main 要建约 83 万个长寿对象：默认阈值下约 8 次全量收集、合计约 1.2 s，importtime 里
# 记在恰好在执行的模块头上（wp_ai_stocktake / _g5_* 曾各「自耗时」0.26~0.31 s）。


def test_app_main_calls_configure_gc_before_any_third_party_or_app_import():
    import ast
    import sys
    from pathlib import Path

    main = Path(gc_tuning.__file__).resolve().parents[1] / "main.py"
    body = ast.parse(main.read_text(encoding="utf-8")).body

    def is_configure_call(node: ast.stmt) -> bool:
        return (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name) and node.value.func.id == "configure_gc")

    def roots(node: ast.stmt) -> list[str]:
        if isinstance(node, ast.Import):
            return [a.name for a in node.names]
        if isinstance(node, ast.ImportFrom) and node.module and node.module != "app.core.gc_tuning":
            return [node.module]
        return []

    calls = [i for i, n in enumerate(body) if is_configure_call(n)]
    heavy = [i for i, n in enumerate(body)
             if any(r.split(".")[0] not in sys.stdlib_module_names | {"__future__"} for r in roots(n))]
    assert calls and heavy, (calls, heavy)
    assert calls[0] < min(heavy), "configure_gc() 必须在导入任何第三方库 / 应用模块之前"


def test_importing_app_main_leaves_threshold_raised():
    import os
    import subprocess
    import sys
    from pathlib import Path

    backend = Path(gc_tuning.__file__).resolve().parents[2]
    env = {k: v for k, v in os.environ.items() if k != "GT_GC_TUNING"}
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run([sys.executable, "-c", "import gc, app.main; print(gc.get_threshold())"], cwd=backend,
                          env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert proc.stdout.strip().splitlines()[-1] == str(gc_tuning.GC_THRESHOLD)


# ── follow-up：只在连续空闲窗口 freeze，后台重阶段互斥 ───────────────────────


def _fast_idle_config(monkeypatch) -> None:
    monkeypatch.setenv("GT_GC_IDLE_POLL_S", "0.005")
    monkeypatch.setenv("GT_GC_IDLE_WINDOW_S", "0.02")
    monkeypatch.setenv("GT_GC_IDLE_TIMEOUT_S", "0.2")
    monkeypatch.setenv("GT_GC_IDLE_RETRY_S", "0.005")


@pytest.mark.asyncio
async def test_busy_requests_never_force_gc_after_timeout(monkeypatch):
    """等待超时只能重排，不能在用户请求中强跑 stop-the-world GC。"""
    from app.middleware.inflight import inflight_counter

    _fast_idle_config(monkeypatch)
    monkeypatch.setenv("GT_GC_IDLE_TIMEOUT_S", "0.03")
    monkeypatch.setattr(inflight_counter, "value_excluding_streams", lambda: 1)
    monkeypatch.setattr(gc, "collect", lambda: (_ for _ in ()).throw(
        AssertionError("busy 时不得 collect")
    ))
    stop = asyncio.Event()
    task = asyncio.create_task(gc_tuning.freeze_when_idle(stop))
    await asyncio.sleep(0.08)
    stop.set()
    assert await asyncio.wait_for(task, 1) is False
    report = gc_tuning.get_last_freeze_report()
    assert report["status"] == "cancelled" and int(report["requeues"]) >= 1


@pytest.mark.asyncio
async def test_idle_window_resets_when_a_request_arrives(monkeypatch):
    from app.middleware.inflight import inflight_counter

    _fast_idle_config(monkeypatch)
    busy = {"value": 0}
    monkeypatch.setattr(inflight_counter, "value_excluding_streams", lambda: busy["value"])
    calls: list[str] = []
    monkeypatch.setattr(gc, "collect", lambda: calls.append("collect") or 0)
    monkeypatch.setattr(gc, "freeze", lambda: calls.append("freeze"))
    monkeypatch.setattr(gc, "get_freeze_count", lambda: 123)

    task = asyncio.create_task(gc_tuning.freeze_when_idle())
    await asyncio.sleep(0.012)  # 还不足 20ms 空闲窗
    busy["value"] = 1
    await asyncio.sleep(0.01)
    busy["value"] = 0
    await asyncio.sleep(0.012)
    assert calls == [], "中间来过请求后必须重新累计完整窗口"
    assert await asyncio.wait_for(task, 1) is True
    assert calls == ["collect", "freeze"]


@pytest.mark.asyncio
async def test_heavy_phase_lock_blocks_gc_until_other_stage_finishes(monkeypatch):
    from app.middleware.inflight import inflight_counter

    _fast_idle_config(monkeypatch)
    monkeypatch.setattr(inflight_counter, "value_excluding_streams", lambda: 0)
    calls: list[str] = []
    monkeypatch.setattr(gc, "collect", lambda: calls.append("collect") or 0)
    monkeypatch.setattr(gc, "freeze", lambda: calls.append("freeze"))
    monkeypatch.setattr(gc, "get_freeze_count", lambda: 1)

    async with gc_tuning.heavy_phase("other-heavy-stage"):
        task = asyncio.create_task(gc_tuning.freeze_when_idle())
        await asyncio.sleep(0.05)
        assert calls == [], "其他重阶段持锁时 GC 不得运行"
    assert await asyncio.wait_for(task, 1) is True
    assert calls == ["collect", "freeze"]


@pytest.mark.asyncio
async def test_prewarm_waits_for_event_drain_before_work(monkeypatch):
    from app.core import startup_registry
    from app.middleware.inflight import inflight_counter

    _fast_idle_config(monkeypatch)
    monkeypatch.setattr(inflight_counter, "value_excluding_streams", lambda: 0)
    order: list[str] = []
    release = asyncio.Event()

    async def drain() -> None:
        order.append("drain-start")
        await release.wait()
        order.append("drain-end")

    async def work() -> None:
        order.append("prewarm")

    ctx = startup_registry.StartupContext()
    event_task = asyncio.create_task(drain())
    ctx.extras["event_drain_task"] = event_task
    prewarm = asyncio.create_task(startup_registry._run_workpaper_prewarm(ctx, work))
    await asyncio.sleep(0.02)
    assert order == ["drain-start"]
    release.set()
    await asyncio.wait_for(prewarm, 2)
    assert order == ["drain-start", "drain-end", "prewarm"]


@pytest.mark.asyncio
async def test_inflight_is_rechecked_after_heavy_lock_acquisition(monkeypatch):
    """判空闲后等待锁期间若来了请求，获取锁后必须放弃本轮 GC。"""
    from app.middleware.inflight import inflight_counter

    _fast_idle_config(monkeypatch)
    busy = {"value": 0}
    monkeypatch.setattr(inflight_counter, "value_excluding_streams", lambda: busy["value"])
    calls: list[str] = []
    monkeypatch.setattr(gc, "collect", lambda: calls.append("collect") or 0)
    monkeypatch.setattr(gc, "freeze", lambda: calls.append("freeze"))
    monkeypatch.setattr(gc, "get_freeze_count", lambda: 1)

    async with gc_tuning.heavy_phase("blocker"):
        task = asyncio.create_task(gc_tuning.freeze_when_idle())
        await asyncio.sleep(0.08)  # 已满足空闲窗口，确定正在等锁
        busy["value"] = 1
    await asyncio.sleep(0.02)
    assert calls == [], "拿到锁后不二次检查会在活跃请求中 freeze"
    busy["value"] = 0
    assert await asyncio.wait_for(task, 1) is True
    assert calls == ["collect", "freeze"]


@pytest.mark.asyncio
async def test_prewarm_work_itself_uses_heavy_phase_lock(monkeypatch):
    monkeypatch.setenv("GT_GC_TUNING", "0")
    order: list[str] = []

    async def work() -> None:
        order.append("work")

    async with gc_tuning.heavy_phase("other"):
        task = asyncio.create_task(gc_tuning.run_then_freeze(work))
        await asyncio.sleep(0.02)
        assert order == []
    await asyncio.wait_for(task, 1)
    assert order == ["work"]


@pytest.mark.asyncio
async def test_open_sse_connection_does_not_block_freeze_forever(monkeypatch):
    """现场实测过的缺陷：只要有浏览器订阅事件流，in-flight 永不为 0 ⇒ freeze 永不发生。

    SSE 作为长连接必须仍计入 ``value()``（drain 要等它），但不得挡住 GC 空闲窗口。
    这里用真实计数器（不 mock 视图），只摆出「1 条 SSE 在挂着」的状态。
    """
    from app.middleware.inflight import inflight_counter

    _fast_idle_config(monkeypatch)
    calls: list[str] = []
    monkeypatch.setattr(gc, "collect", lambda: calls.append("collect") or 0)
    monkeypatch.setattr(gc, "freeze", lambda: calls.append("freeze"))
    monkeypatch.setattr(gc, "get_freeze_count", lambda: 7)

    saved = (inflight_counter._count, inflight_counter._streaming)
    inflight_counter._count = 1          # 一条 SSE 在途
    inflight_counter._streaming = 1
    try:
        assert inflight_counter.value() == 1, "SSE 必须仍算 in-flight，否则 drain 会提前停旧 worker"
        assert inflight_counter.value_excluding_streams() == 0
        assert await asyncio.wait_for(gc_tuning.freeze_when_idle(), 2) is True
        assert calls == ["collect", "freeze"]
    finally:
        inflight_counter._count, inflight_counter._streaming = saved


@pytest.mark.asyncio
async def test_real_request_behind_an_sse_still_blocks_freeze(monkeypatch):
    """反向用例：排除 SSE 不等于不看请求 —— SSE 之外还有活跃请求时必须继续等。"""
    from app.middleware.inflight import inflight_counter

    _fast_idle_config(monkeypatch)
    monkeypatch.setenv("GT_GC_IDLE_TIMEOUT_S", "0.03")
    monkeypatch.setattr(gc, "collect", lambda: (_ for _ in ()).throw(
        AssertionError("SSE 之外仍有请求时不得 collect")
    ))
    saved = (inflight_counter._count, inflight_counter._streaming)
    inflight_counter._count = 2          # 1 条 SSE + 1 个真实请求
    inflight_counter._streaming = 1
    try:
        assert inflight_counter.value_excluding_streams() == 1
        stop = asyncio.Event()
        task = asyncio.create_task(gc_tuning.freeze_when_idle(stop))
        await asyncio.sleep(0.08)
        stop.set()
        assert await asyncio.wait_for(task, 1) is False
    finally:
        inflight_counter._count, inflight_counter._streaming = saved


def test_gc_idle_gate_reads_the_stream_excluding_view_not_raw_inflight():
    """AST 判据：``freeze_when_idle`` 只许读 ``value_excluding_streams``。

    回退成 ``inflight_counter.value()`` 时，上面两条行为用例在真实计数器下仍可能偶然通过
    （取决于当时有没有 SSE），所以这里把读法本身钉死。走 AST，不用文本匹配——
    docstring 里就写着 ``value()``，文本判据会被自己的注释咬住。
    """
    import ast
    import inspect
    import textwrap

    src = textwrap.dedent(inspect.getsource(gc_tuning.freeze_when_idle))
    tree = ast.parse(src)

    def _counter_attr(node: ast.AST) -> str | None:
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            owner = node.func.value
            if isinstance(owner, ast.Name) and owner.id == "inflight_counter":
                return node.func.attr
        return None

    # 判定分支（与 0 比较）只许用排除流的视图；日志里读 value()/streaming() 做诊断是允许的。
    decisions: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            attr = _counter_attr(node.left)
            if attr:
                decisions.add(attr)
    assert decisions == {"value_excluding_streams"}, (
        f"freeze_when_idle 的空闲判定读了 {sorted(decisions)}；只允许 value_excluding_streams"
    )
    assert len(decisions) >= 1
    # 反向：确认扫描器真的能看见另一种写法（否则 decisions 恒空也会“通过”）
    probe = ast.parse("if inflight_counter.value() == 0:\n    pass\n")
    probe_hits = {
        _counter_attr(n.left) for n in ast.walk(probe) if isinstance(n, ast.Compare)
    }
    assert probe_hits == {"value"}, f"扫描器自身失效，探针得到 {probe_hits}"
