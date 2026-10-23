"""重驱 worker 的循环、选主与入口（spec writeback-followup-issue-closure R3.2）。

候选判据的真库语义见 `test_oo_apply_redrive_pg.py`；这里钉住：

1. 有候选 ⇒ 走与回调**同一个**入口 `_apply_durable_incoming`，`attempt=2`、沿用候选的 operation；
2. 无候选 ⇒ 什么都不调；
3. 只有拿到选主锁的副本才重驱；每轮写心跳；单轮出错不让 worker 退出；
4. 已登记进启动清单（不登记就从不运行）。
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.workers import oo_apply_redrive_worker as W


class _Factory:
    def __call__(self) -> Any:
        return self

    async def __aenter__(self) -> Any:
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        return None


@pytest.fixture
def entry(monkeypatch):
    import app.routers.wp_sync_router as R

    calls: list[dict[str, Any]] = []

    async def _apply(db, *, outcome, attempt=1):
        calls.append({"app": outcome.application_id, "op": outcome.operation_id, "attempt": attempt})

    monkeypatch.setattr(R, "_apply_durable_incoming", _apply)
    return calls


@pytest.mark.asyncio
async def test_candidate_is_redriven_through_the_callback_entry(entry, monkeypatch):
    app_id, op_id = uuid.uuid4(), uuid.uuid4()
    monkeypatch.setattr(W, "find_stuck_application", AsyncMock(return_value=(app_id, op_id)))
    assert await W.redrive_once(session_factory=_Factory()) == app_id
    assert entry == [{"app": app_id, "op": op_id, "attempt": 2}]


@pytest.mark.asyncio
async def test_no_candidate_no_call(entry, monkeypatch):
    monkeypatch.setattr(W, "find_stuck_application", AsyncMock(return_value=None))
    assert await W.redrive_once(session_factory=_Factory()) is None
    assert entry == []


@pytest.mark.asyncio
@pytest.mark.parametrize("leader", [True, False])
async def test_only_the_leader_redrives_and_every_round_beats(monkeypatch, leader):
    beats: list[str] = []
    rounds: list[int] = []

    async def _beat(name: str) -> None:
        beats.append(name)

    async def _redrive(**_k: Any) -> None:
        rounds.append(1)
        raise RuntimeError("单轮出错")

    import app.workers._leader_lock as L

    monkeypatch.setattr(W, "write_heartbeat", _beat)
    monkeypatch.setattr(W, "redrive_once", _redrive)
    monkeypatch.setattr(L, "try_acquire_leadership", AsyncMock(return_value=leader))
    monkeypatch.setattr(W, "POLL_SECONDS", 0.01)
    stop = asyncio.Event()
    task = asyncio.create_task(W.run(stop))
    await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(task, timeout=2)
    assert len(beats) >= 2 and set(beats) == {"oo_apply_redrive_worker"}
    assert (len(rounds) >= 2) is leader, "只有选主成功才重驱；单轮出错后循环继续"


def test_redrive_states_are_the_mid_apply_stations():
    """由协调器准入集合推出（去掉等用户的 error / conflict）；状态机加一站时这里逼着显式确认。"""
    from app.services.workpaper_sync.oo_apply_redrive import REDRIVE_STATES

    assert {s.value for s in REDRIVE_STATES} == {
        "queued", "validating", "extracting", "merging", "rematerializing", "applying",
    }


def test_worker_is_registered_for_startup():
    from app.core import startup_registry as sr

    assert ("oo_apply_redrive_worker", "app.workers.oo_apply_redrive_worker") in sr._WORKER_BINDINGS
    assert "oo_apply_redrive_worker" in sr.WORKER_TASK_NAMES
