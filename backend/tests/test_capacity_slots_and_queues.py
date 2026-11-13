"""LLM / OCR 通道与耐久任务队列的统一计量（spec platform-heavy-jobs-and-capacity-closure 任务 0.2）。"""

from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import pytest

from app.services import platform_metrics
from app.services.capacity_slots import (
    LLM_MAX_CONCURRENCY,
    LLM_SLOT,
    OCR_SLOT,
    SlotTracker,
)

APP_ROOT = Path(__file__).resolve().parents[1] / "app"


@pytest.fixture(autouse=True)
def _reset_durable_queues():
    platform_metrics._durable_queues.clear()
    yield
    platform_metrics._durable_queues.clear()


# ── LLM：槽必须是并发许可的唯一入口 ──────────────────────────────────


def test_llm_slot_wraps_the_one_shared_semaphore():
    """``native_engine`` 与两条既有守卫都按同一实例读 ``_value``，不得变成第二个信号量。"""
    from app.services import llm_client

    assert llm_client._llm_semaphore is LLM_SLOT.semaphore
    assert llm_client._LLM_MAX_CONCURRENCY == LLM_MAX_CONCURRENCY
    assert LLM_SLOT.concurrency_limit == LLM_MAX_CONCURRENCY


def _direct_semaphore_acquisitions() -> list[str]:
    """AST 找 ``async with _llm_semaphore``：docstring 里提它不算，真持它才算。"""
    hits: list[str] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        # 仓库里有带 BOM 的源文件，ast.parse 会因 U+FEFF 直接抛 SyntaxError。
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncWith):
                continue
            for item in node.items:
                expr = item.context_expr
                name = (
                    expr.id
                    if isinstance(expr, ast.Name)
                    else expr.attr
                    if isinstance(expr, ast.Attribute)
                    else None
                )
                if name == "_llm_semaphore":
                    hits.append(f"{path.relative_to(APP_ROOT)}:{node.lineno}")
    return hits


def test_no_module_bypasses_the_llm_slot():
    """绕过 slot 直接持信号量 ⇒ 这次调用的排队 / 执行时长不会被任何指标看到。"""
    assert _direct_semaphore_acquisitions() == []


# ── 有界通道 ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bounded_slot_limits_concurrency_and_reports_real_queue():
    slot = SlotTracker(
        "test_bounded",
        semaphore=asyncio.Semaphore(1),
        concurrency_limit=1,
        register=False,
    )
    holder_entered = asyncio.Event()
    release_holder = asyncio.Event()

    async def holder():
        async with slot.use():
            holder_entered.set()
            await release_holder.wait()

    async def waiter():
        async with slot.use():
            pass

    holder_task = asyncio.create_task(holder())
    await holder_entered.wait()
    waiter_task = asyncio.create_task(waiter())
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    busy = slot.snapshot()
    assert busy["active"] == 1
    assert busy["waiting"] == 1
    assert busy["oldest_active_seconds"] >= 0.0

    release_holder.set()
    await asyncio.gather(holder_task, waiter_task)

    idle = slot.snapshot()
    assert idle["active"] == 0 and idle["waiting"] == 0
    assert idle["oldest_wait_seconds"] == 0.0


@pytest.mark.asyncio
async def test_cancelled_waiter_leaves_queue_without_leaking_a_permit():
    """等待期间被取消时没拿到许可，绝不能 release —— 否则上限会被悄悄放大。"""
    slot = SlotTracker(
        "test_cancel",
        semaphore=asyncio.Semaphore(1),
        concurrency_limit=1,
        register=False,
    )
    entered = asyncio.Event()
    release = asyncio.Event()

    async def holder():
        async with slot.use():
            entered.set()
            await release.wait()

    async def waiter():
        async with slot.use():
            pass

    holder_task = asyncio.create_task(holder())
    await entered.wait()
    waiter_task = asyncio.create_task(waiter())
    await asyncio.sleep(0)
    waiter_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter_task

    assert slot.snapshot()["waiting"] == 0
    release.set()
    await holder_task
    assert slot.semaphore._value == 1


# ── 无界通道（OCR）────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ocr_slot_declares_absence_of_admission_queue():
    """OCR 的 waiting 恒 0 是「没有准入队列」，不是「测到没排队」。"""
    assert OCR_SLOT.bounded is False
    before = OCR_SLOT.snapshot()
    assert before["concurrency_limit"] is None

    async with OCR_SLOT.use():
        during = OCR_SLOT.snapshot()
        assert during["active"] == before["active"] + 1
        assert during["waiting"] == 0

    assert OCR_SLOT.snapshot()["active"] == before["active"]


@pytest.mark.asyncio
async def test_unified_ocr_recognize_runs_inside_the_ocr_slot():
    from app.services.unified_ocr_service import OCREngine, UnifiedOCRService

    service = UnifiedOCRService()
    observed: list[int] = []

    async def fake_routed(image_path: str, mode: OCREngine) -> dict:
        observed.append(int(OCR_SLOT.snapshot()["active"]))
        return {"text": "ok", "engine": "stub"}

    service._recognize_routed = fake_routed  # type: ignore[method-assign]
    baseline = int(OCR_SLOT.snapshot()["active"])

    assert await service.recognize("x.png") == {"text": "ok", "engine": "stub"}

    assert observed == [baseline + 1]
    assert int(OCR_SLOT.snapshot()["active"]) == baseline


# ── 耐久队列：失败不得伪装成 0 ────────────────────────────────────────


def test_unsampled_queue_is_reported_stale_not_empty():
    snapshot = platform_metrics.durable_queue_snapshot(1000.0)
    for name in platform_metrics.DURABLE_QUEUE_NAMES:
        assert snapshot[name] == {
            "available": False,
            "reason": "not_sampled",
            "stale": True,
        }


def test_failed_sample_keeps_last_known_depth_and_flags_unavailable():
    platform_metrics.observe_durable_queue(
        "platform_jobs",
        counts={"queued": 7, "retry_wait": 1, "running": 2},
        oldest_age_seconds=42.5,
        sampled_at=100.0,
    )
    healthy = platform_metrics.durable_queue_snapshot(100.0)["platform_jobs"]
    assert healthy["available"] is True
    assert healthy["queued"] == 7
    assert healthy["oldest_queue_age_seconds"] == 42.5
    assert healthy["stale"] is False

    platform_metrics.mark_durable_queue_unavailable(
        "platform_jobs",
        reason="OperationalError: connection refused",
        sampled_at=130.0,
    )
    broken = platform_metrics.durable_queue_snapshot(130.0)["platform_jobs"]
    assert broken["available"] is False
    assert "connection refused" in str(broken["reason"])
    # 读不到 ≠ 队列空了：上次已知深度必须留着，不能被 0 覆盖。
    assert broken["queued"] == 7


def test_stale_sample_is_flagged_after_the_window():
    platform_metrics.observe_durable_queue(
        "ai_task_items",
        counts={"queued": 1, "retry_wait": 0, "running": 0},
        oldest_age_seconds=1.0,
        sampled_at=10.0,
    )
    window = platform_metrics.DURABLE_QUEUE_STALE_AFTER_SECONDS
    fresh = platform_metrics.durable_queue_snapshot(10.0 + window - 1)
    aged = platform_metrics.durable_queue_snapshot(10.0 + window + 1)
    assert fresh["ai_task_items"]["stale"] is False
    assert aged["ai_task_items"]["stale"] is True


# ── 采样 worker ─────────────────────────────────────────────────────


class _Session:
    def __init__(self, log: list[str]) -> None:
        self._log = log

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def rollback(self):
        self._log.append("rollback")


@pytest.mark.asyncio
async def test_one_failing_queue_does_not_block_the_other(monkeypatch):
    """每条队列一个独立 session：PG 上一条查询失败会让事务 aborted，不能连累另一条。"""
    from app.services import ai_task_job_service, platform_job_service
    from app.workers import capacity_queue_worker as worker

    sessions: list[str] = []
    monkeypatch.setattr(worker, "async_session", lambda: _Session(sessions))

    async def broken(_db):
        raise RuntimeError("connection refused")

    async def healthy(_db):
        return {
            "queued": 3,
            "retry_wait": 0,
            "running": 1,
            "oldest_queue_age_seconds": 12.0,
        }

    monkeypatch.setattr(platform_job_service, "queue_snapshot", broken)
    monkeypatch.setattr(ai_task_job_service, "queue_snapshot", healthy)

    await worker.sample_once()

    snapshot = platform_metrics.durable_queue_snapshot(
        asyncio.get_running_loop().time()
    )
    assert snapshot["platform_jobs"]["available"] is False
    assert "connection refused" in str(snapshot["platform_jobs"]["reason"])
    assert snapshot["ai_task_items"]["available"] is True
    assert snapshot["ai_task_items"]["queued"] == 3
    # 两条队列各开各的 session，成功那条读完回滚、不把只读事务留给连接池。
    assert sessions == ["rollback"]


def test_sampler_is_registered_as_a_startup_worker():
    from app.core.startup_registry import WORKER_TASK_NAMES, _WORKER_BINDINGS

    assert "capacity_queue_worker" in WORKER_TASK_NAMES
    assert (
        "capacity_queue_worker",
        "app.workers.capacity_queue_worker",
    ) in _WORKER_BINDINGS
