"""R4：完整槽位、冻结年度、持久回执与唯一派发口；仅合成 SQLite 数据。"""
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from app.models.core import Project
from app.models.dataset_models import ImportEventOutbox, OutboxStatus
from app.services.formula_settings import outbox as fs_outbox, propagation

from .test_outbox_delivery_semantics import (
    SLOTS, _consumptions, _enqueue, _publish_one, _row, handler, world,
)


@pytest.mark.parametrize("size", [201, 2000])
async def test_complete_slots_are_persisted_and_delivered(world, handler, size):
    factory, pid = world
    slots = [f"balance_sheet:BS-{i:04d}" for i in range(size)]
    async with factory() as db:
        pubs = await fs_outbox.record_changes(
            db, domain="report", events=[{"project_id": pid, "slot_keys": slots}], source="r4")
        fs_outbox._take_pending(db)
        await db.commit()
    oid = pubs[0].outbox_id
    assert (await _row(factory, oid)).payload["slot_keys"] == slots
    assert await _publish_one(factory, oid)
    assert handler.calls == [(pid, 2025, slots)]
    receipt = (await _row(factory, oid)).payload[fs_outbox.RECEIPT_KEY]
    assert (receipt["outbox_id"], receipt["year"], receipt["delivery_status"]) == (str(oid), 2025, "published")
    assert receipt["action_status"] == "unknown", "只有 marked 不足以证明报表重算成功"


async def test_delivery_uses_enqueued_year_after_project_year_changes(world, handler):
    factory, pid = world
    oid = await _enqueue(factory, pid)
    async with factory() as db:
        project = await db.get(Project, pid)
        project.audit_year = 2026
        await db.commit()
    assert await _publish_one(factory, oid)
    assert handler.calls == [(pid, 2025, SLOTS)]
    assert (await _row(factory, oid)).payload[fs_outbox.RECEIPT_KEY]["year"] == 2025


async def test_legacy_missing_year_fails_without_borrowing_current_year(world, handler):
    factory, pid = world
    oid = await _enqueue(factory, pid)
    async with factory() as db:
        row = await db.get(ImportEventOutbox, oid)
        row.year = None
        await db.commit()
    assert await _publish_one(factory, oid) is False
    row = await _row(factory, oid)
    assert row.status == OutboxStatus.failed and handler.calls == []
    assert "冻结审计年度" in row.last_error
    assert row.payload[fs_outbox.RECEIPT_KEY]["action_status"] == "failed"
    assert await _consumptions(factory) == 0


@pytest.mark.parametrize("patch, message", [
    ({"slot_keys": []}, "完整槽位"), ({"slot_keys": ["ok", 1]}, "完整槽位"),
    ({"domain": "not-a-domain"}, "未知公式传播域"),
])
async def test_malformed_payload_fails_and_keeps_receipt(world, handler, patch, message):
    factory, pid = world
    oid = await _enqueue(factory, pid)
    async with factory() as db:
        row = await db.get(ImportEventOutbox, oid)
        row.payload = {**row.payload, **patch}
        await db.commit()
    assert await _publish_one(factory, oid) is False
    row = await _row(factory, oid)
    receipt = row.payload[fs_outbox.RECEIPT_KEY]
    assert row.status == OutboxStatus.failed and message in row.last_error
    assert receipt["delivery_status"] == receipt["action_status"] == "failed"
    assert handler.calls == [] and await _consumptions(factory) == 0

async def test_database_flush_error_isolated_and_retry_receipt_is_durable(world, monkeypatch):
    factory, pid = world
    oid = await _enqueue(factory, pid)
    calls = []

    async def fail_inside_delivery(project_id, year, slots):
        calls.append((project_id, year, list(slots)))
        active.add(Project(id=pid, name="重复主键", client_name="重复主键", audit_year=2025))
        await active.flush()
        return {"marked": 1}

    monkeypatch.setitem(propagation.HANDLERS, "report", fail_inside_delivery)
    from app.services.import_event_outbox_service import ImportEventOutboxService

    async with factory() as active:
        assert await ImportEventOutboxService.publish_one(active, oid) is False
        assert await active.scalar(sa.select(sa.func.count()).select_from(Project)) == 1
        await active.commit()
    failed = await _row(factory, oid)
    assert failed.status == OutboxStatus.failed and failed.attempt_count == 1
    receipt = failed.payload[fs_outbox.RECEIPT_KEY]
    assert receipt["action_status"] == "failed" and receipt["last_error"]
    assert await _consumptions(factory) == 0

    async def repaired(project_id, year, slots):
        calls.append((project_id, year, list(slots)))
        return {"closure": ["BS-001"], "marked": 1, "recalculated": {
            "recalculated_count": 1, "failed_count": 0, "failed_rows": []}}

    monkeypatch.setitem(propagation.HANDLERS, "report", repaired)
    assert await _publish_one(factory, oid)
    recovered = await _row(factory, oid)
    assert recovered.status == OutboxStatus.published and recovered.last_error is None
    assert recovered.payload[fs_outbox.RECEIPT_KEY]["action_status"] == "succeeded"
    assert len(calls) == 2 and await _consumptions(factory) == 1
    assert propagation._delivery_event_id.get() is None


@pytest.mark.parametrize("result", [None, "not-a-receipt", ["not", "a", "dict"], 7])
async def test_non_mapping_handler_result_fails_with_structured_failure_receipt(world, monkeypatch, result):
    factory, pid = world
    oid = await _enqueue(factory, pid)

    async def malformed(_project_id, _year, _slots):
        return result

    monkeypatch.setitem(propagation.HANDLERS, "report", malformed)
    assert await _publish_one(factory, oid) is False
    row = await _row(factory, oid)
    receipt = row.payload[fs_outbox.RECEIPT_KEY]
    assert row.status == OutboxStatus.failed and "未返回结构化回执" in row.last_error
    assert receipt["handler_result"] == {} and receipt["action_status"] == "failed"
    assert await _consumptions(factory) == 0
    assert propagation._delivery_event_id.get() is None

@pytest.mark.parametrize("detail", ["plain-detail", ["list-detail"], 4])
async def test_non_mapping_exception_detail_does_not_hide_original_error(world, monkeypatch, detail):
    factory, pid = world
    oid = await _enqueue(factory, pid)

    class SyntheticFailure(RuntimeError):
        def __init__(self):
            self.detail = detail
            super().__init__("R4 合成执行失败")

    async def failed(_project_id, _year, _slots):
        raise SyntheticFailure()

    monkeypatch.setitem(propagation.HANDLERS, "report", failed)
    assert await _publish_one(factory, oid) is False
    row = await _row(factory, oid)
    receipt = row.payload[fs_outbox.RECEIPT_KEY]
    assert row.last_error == receipt["last_error"] == "R4 合成执行失败"
    assert receipt["handler_result"] == {} and receipt["action_status"] == "failed"
    assert await _consumptions(factory) == 0


@pytest.mark.parametrize("fail_failure_receipt", [False, True])
async def test_receipt_flush_error_does_not_poison_outer_transaction(world, monkeypatch, fail_failure_receipt):
    """向回执 flush 的下一层注入真实唯一键错误；生产 deliver/publish_one 保持原样。"""
    from app.services.import_event_outbox_service import ImportEventOutboxService

    factory, pid = world
    oid = await _enqueue(factory, pid)
    injections, calls = [], []
    result = {"recalculated": {"recalculated_count": 1, "failed_count": 0, "failed_rows": []}}

    def inject_duplicate(session, _flush_context, _instances):
        for item in list(session.dirty):
            if not isinstance(item, ImportEventOutbox) or item.id != oid:
                continue
            receipt = (item.payload or {}).get(fs_outbox.RECEIPT_KEY)
            if not isinstance(receipt, dict):
                continue
            status = receipt.get("delivery_status")
            if status == "published" or (fail_failure_receipt and status == "failed"):
                injections.append(status)
                session.add(Project(id=pid, name="【合成】回执冲突", client_name="【合成】回执冲突", audit_year=2025))
                break

    async with factory() as active:
        original_name = await active.scalar(sa.select(Project.name).where(Project.id == pid))

        async def effect_inside_savepoint(_project_id, _year, _slots):
            calls.append("first")
            await active.execute(sa.update(Project).where(Project.id == pid).values(name="【合成】待回滚"))
            return result

        monkeypatch.setitem(propagation.HANDLERS, "report", effect_inside_savepoint)
        sa.event.listen(active.sync_session, "before_flush", inject_duplicate)
        try:
            assert await ImportEventOutboxService.publish_one(active, oid) is False
            assert await active.scalar(sa.select(Project.name).where(Project.id == pid)) == original_name
            assert await active.scalar(sa.select(sa.func.count()).select_from(Project)) == 1
            await active.commit()
        finally:
            sa.event.remove(active.sync_session, "before_flush", inject_duplicate)
    row = await _row(factory, oid)
    assert row.status == OutboxStatus.failed and row.attempt_count == 1 and row.last_error
    receipt = row.payload.get(fs_outbox.RECEIPT_KEY)
    if fail_failure_receipt:
        assert injections == ["published", "failed"] and receipt is None
    else:
        assert injections == ["published"] and receipt["action_status"] == "failed"
    assert await _consumptions(factory) == 0

    async def repaired(_project_id, _year, _slots):
        calls.append("retry")
        return result

    monkeypatch.setitem(propagation.HANDLERS, "report", repaired)
    assert await _publish_one(factory, oid) is True
    row = await _row(factory, oid)
    assert row.status == OutboxStatus.published
    assert row.payload[fs_outbox.RECEIPT_KEY]["action_status"] == "succeeded"
    assert calls == ["first", "retry"] and await _consumptions(factory) == 1
    assert propagation._delivery_event_id.get() is None
