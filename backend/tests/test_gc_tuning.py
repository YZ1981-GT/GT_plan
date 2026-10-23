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
