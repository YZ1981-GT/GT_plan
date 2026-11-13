"""公式变更耐久事件的投递语义（spec formula-management-repair-closure R1）。

SQLite 真 ORM（``_env`` + outbox 三张表）；只替换传播处理器（``propagation.HANDLERS`` 的一项，记录调用 / 按需抛错）。

1. 重放路径（``ImportEventOutboxService.publish_one`` = worker 与立即投递共用的唯一派发口）真的执行处理器。
   🔴 修复前：派发口先抢 fan-out 消费权，``formula_settings.outbox.deliver`` 再抢一次同一把 ⇒ 第二次必失败 ⇒ 返回
   ``already_delivered``、处理器一次都不跑，派发口照样把行标 published —— 失败重放全是空操作。
2. 处理器失败（含 ``PropagationIncomplete``）：行记 failed + 尝试次数 + 原因、消费权归还；修好后重放执行一次、标 published。
3. 已 published 的行不再派发（幂等）。
4. ``publish_pending`` 的立即投递走同一派发口：失败当场可见（failed / 次数 / 原因），不再停在 pending。
5. ``propagate_cross_check`` 重跑失败抛 ``PropagationIncomplete``（此前返回 error 字典，投递照样标 published）。
6. 投递取审计年度按 ``audit_year``（此前只读 ``audit_period_end``，共享库 17/20 个项目该列为空 ⇒ 年度恒空）。
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import date

import pytest
import sqlalchemy as sa

from app.models.audit_platform_schemas import EventType
from app.models.dataset_models import EventOutboxDLQ, ImportEventConsumption, ImportEventOutbox, OutboxStatus
from app.services.formula_settings import outbox as fs_outbox
from app.services.formula_settings import propagation
from app.services.formula_settings.propagation import PropagationIncomplete
from app.services.import_event_outbox_service import ImportEventOutboxService

from ._env import add_project, make_db

OUTBOX_MODELS = (ImportEventOutbox, ImportEventConsumption, EventOutboxDLQ)
DOMAIN = "report"
SLOTS = ["balance_sheet:BS-001"]


class _Handler:
    def __init__(self, error: BaseException | None = None) -> None:
        self.calls: list[tuple[uuid.UUID, int | None, list[str]]] = []
        self.error = error

    async def __call__(self, project_id, year, slot_keys):
        self.calls.append((project_id, year, list(slot_keys)))
        if self.error is not None:
            raise self.error
        return {"marked": 1}


@pytest.fixture
def handler(monkeypatch):
    h = _Handler()
    monkeypatch.setitem(propagation.HANDLERS, DOMAIN, h)
    return h


async def _enqueue(factory, pid) -> uuid.UUID:
    async with factory() as db:
        pubs = await fs_outbox.record_changes(db, domain=DOMAIN, events=[{"project_id": str(pid), "slot_keys": SLOTS}],
                                              source="test")
        fs_outbox._take_pending(db)  # 只验证派发口，不在这里起后台投递
        await db.commit()
    assert len(pubs) == 1
    return pubs[0].outbox_id


async def _row(factory, outbox_id):
    async with factory() as db:
        return (await db.execute(sa.select(ImportEventOutbox).where(ImportEventOutbox.id == outbox_id))).scalar_one()


async def _consumptions(factory) -> int:
    async with factory() as db:
        return int(await db.scalar(sa.select(sa.func.count()).select_from(ImportEventConsumption)))


async def _publish_one(factory, outbox_id) -> bool:
    async with factory() as db:
        ok = await ImportEventOutboxService.publish_one(db, outbox_id)
        await db.commit()
    return ok


@pytest.fixture
async def world(monkeypatch):
    async def _no_stale_engine(*_a, **_kw):  # 依赖图按报表行标下游过期：本组用例不观测
        return None

    monkeypatch.setattr(fs_outbox, "_stale_engine_for_formula_change", _no_stale_engine)
    async with make_db(extra_models=OUTBOX_MODELS) as factory:
        async with factory() as db:
            pid = await add_project(db, "传播语义")  # audit_year=2025、audit_period_end 为空（与共享库多数项目同形）
            await db.commit()
        yield factory, pid


async def test_replay_path_runs_the_handler_and_marks_published(world, handler):
    factory, pid = world
    oid = await _enqueue(factory, pid)
    assert await _publish_one(factory, oid) is True
    assert handler.calls == [(pid, 2025, SLOTS)], "派发口抢了消费权后，处理器必须真的执行（且年度取 audit_year）"
    row = await _row(factory, oid)
    assert (row.status, row.attempt_count, row.last_error) == (OutboxStatus.published, 0, None)
    assert await _consumptions(factory) == 1
    # 幂等：已 published 不再派发
    assert await _publish_one(factory, oid) is False
    assert len(handler.calls) == 1


@pytest.mark.parametrize("error", [
    PropagationIncomplete("report", "报表重算失败（过期标记已保留，将自动重试）：注入"),
    RuntimeError("注入：连接断开"),
])
async def test_failure_is_recorded_then_retry_runs_once(world, handler, error):
    factory, pid = world
    oid = await _enqueue(factory, pid)
    handler.error = error
    assert await _publish_one(factory, oid) is False
    row = await _row(factory, oid)
    assert (row.status, row.attempt_count) == (OutboxStatus.failed, 1)
    assert "注入" in (row.last_error or "")
    assert await _consumptions(factory) == 0, "失败必须归还消费权，否则重放被闸门拦下、事件永久静默"
    handler.error = None
    assert await _publish_one(factory, oid) is True
    row = await _row(factory, oid)
    assert row.status == OutboxStatus.published and len(handler.calls) == 2


async def test_immediate_delivery_failure_is_visible_at_once(world, handler, monkeypatch):
    """``publish_pending`` 后台投递失败：行当场 failed + 次数 + 原因（此前只记日志，行停在 pending、看不出失败）。"""
    factory, pid = world
    import app.core.database as database

    monkeypatch.setattr(database, "async_session", factory)
    handler.error = PropagationIncomplete("report", "报表重算失败（过期标记已保留，将自动重试）：注入")
    async with factory() as db:
        await fs_outbox.record_changes(db, domain=DOMAIN, events=[{"project_id": str(pid), "slot_keys": SLOTS}],
                                       source="test")
        await db.commit()
        before = asyncio.all_tasks()
        assert (await fs_outbox.publish_pending(db)) == {"queued": 1}
        background = asyncio.all_tasks() - before
    # 等后台投递跑完再读（内存 SQLite 只有一条连接：边投递边轮询会互相结束对方的事务 / 保存点）
    await asyncio.wait_for(asyncio.gather(*background), timeout=10)
    async with factory() as db:
        row = (await db.execute(sa.select(ImportEventOutbox))).scalar_one()
    assert (row.status, row.attempt_count) == (OutboxStatus.failed, 1)
    assert "将自动重试" in (row.last_error or "")
    assert len(handler.calls) == 1


async def test_cross_check_rerun_failure_raises_incomplete(monkeypatch):
    import app.services.formula_management.logic_check as logic_check
    import app.services.stale_degraded_logger as sdl

    async def boom(*_a, **_kw):
        raise RuntimeError("注入：勾稽执行失败")

    degraded = []
    monkeypatch.setattr(logic_check, "execute_report_cross_checks", boom)
    monkeypatch.setattr(sdl, "log_stale_degraded", lambda **kw: degraded.append(kw))
    async with make_db() as factory:
        async with factory() as db:
            pid = await add_project(db, "勾稽重跑")
            await db.commit()
        propagation.set_session_factory(factory)
        try:
            with pytest.raises(PropagationIncomplete) as caught:
                await propagation.propagate_cross_check(pid, 2025, ["user:abc"])
        finally:
            propagation.set_session_factory(None)
    assert caught.value.domain == "cross_check" and "注入" in str(caught.value)
    assert [d["source"] for d in degraded] == ["formula_settings:cross_check_rerun"]


async def test_fetch_project_year_prefers_audit_year():
    async with make_db() as factory:
        async with factory() as db:
            a = await add_project(db, "只有审计年度")
            b = await add_project(db, "只有期末日")
            from app.models.core import Project

            pa, pb = await db.get(Project, a), await db.get(Project, b)
            pa.audit_year, pa.audit_period_end = 2024, None
            pb.audit_year, pb.audit_period_end = None, date(2023, 12, 31)
            await db.commit()
            assert await fs_outbox._fetch_project_year(db, a) == 2024
            assert await fs_outbox._fetch_project_year(db, b) == 2023
            assert await fs_outbox._fetch_project_year(db, uuid.uuid4()) is None
