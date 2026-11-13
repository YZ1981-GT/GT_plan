"""R4：真实 operation 请求与跨提交重放；只替换 snapshot 和 worker 通知。"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, Mock

import pytest
import sqlalchemy as sa

from app.models.consol_operation_models import ConsolOperation
from app.models.dataset_models import ImportEventOutbox, OutboxStatus
from app.services import consol_operation_service as operations
from app.services.formula_settings import propagation

from ._env import add_project, make_db
from ._r4_test_data import T0, operation_row, outbox_row, snapshot_pair


@pytest.fixture
async def operation_world(monkeypatch):
    from app.workers import consol_operation_worker

    async def snapshot(_db, project_id, year, operation_id):
        return snapshot_pair(project_id, year, operation_id)

    snapshot_spy, wake = AsyncMock(side_effect=snapshot), Mock()
    monkeypatch.setattr(operations, "_snapshot", snapshot_spy)
    monkeypatch.setattr(consol_operation_worker, "wake", wake)
    async with make_db(extra_models=(ConsolOperation, ImportEventOutbox)) as factory:
        async with factory() as db:
            pid = await add_project(db, "【合成】R4 合并项目", report_scope="consolidated")
            await db.commit()
        monkeypatch.setattr(propagation, "_session_factory", factory)
        yield factory, pid, snapshot_spy, wake


async def _request(db, pid, key, *, operation_type="push", actions=("notes",), source="formula"):
    return await operations.request_operation(
        db, project_id=pid, year=2025, operation_type=operation_type,
        idempotency_key=key, trigger_source=source, requested_actions=actions,
    )


async def _propagate_event(pid, event_id):
    token = propagation._delivery_event_id.set(str(event_id))
    try:
        return await propagation.propagate_consol_note(pid, 2025, ["五、1|余额"])
    finally:
        propagation._delivery_event_id.reset(token)


async def test_same_event_reuses_committed_terminal_operation(operation_world):
    factory, pid, snapshot, wake = operation_world
    async with factory() as db:
        event = outbox_row(pid, domain="consol_note", status=OutboxStatus.pending)
        db.add(event)
        await db.commit()
        event_id = event.id
    first = await _propagate_event(pid, event_id)
    assert (first["disposition"], first["status"]) == ("created", "queued")
    operation_id = uuid.UUID(first["operation_id"])
    async with factory() as db:
        row = await db.get(ConsolOperation, operation_id)
        assert row.idempotency_key == f"formula:{event_id}"
        row.status = "succeeded"
        await db.commit()
    second = await _propagate_event(pid, event_id)
    assert (second["operation_id"], second["disposition"], second["status"]) == (
        str(operation_id), "replayed", "succeeded")
    async with factory() as db:
        assert await db.scalar(sa.select(sa.func.count()).select_from(ConsolOperation)) == 1
    assert snapshot.await_count == 1 and wake.call_count == 2
    assert propagation._delivery_event_id.get() is None


async def test_coalescing_preserves_each_original_incoming_hash(operation_world):
    factory, pid, snapshot, _wake = operation_world
    main_key, alias_key = "formula:main", "formula:alias"
    async with factory() as db:
        first = await _request(db, pid, main_key)
        operation_id, first_hash = first.operation.id, first.operation.request_hash
        await db.commit()
    async with factory() as db:
        merged = await _request(db, pid, alias_key, operation_type="refresh_all", actions=("reports",))
        assert merged.disposition == "coalesced" and merged.operation.id == operation_id
        assert merged.operation.revision == 2
        assert merged.operation.request_hash != first_hash
        assert merged.operation.idempotency_keys[main_key] == first_hash
        assert set(merged.operation.idempotency_keys) == {main_key, alias_key}
        assert merged.operation.request_payload["requested_actions"] == ["notes", "reports"]
        await db.commit()
    async with factory() as db:
        main = await _request(db, pid, main_key)
        alias = await _request(db, pid, alias_key, operation_type="refresh_all", actions=("reports",))
        assert main.disposition == alias.disposition == "replayed"
        assert main.operation.id == alias.operation.id == operation_id
        assert main.operation.revision == 2
        await db.commit()
    assert snapshot.await_count == 2

@pytest.mark.parametrize("lookup", ["main", "alias"])
async def test_exact_history_lookup_is_not_limited_to_latest_hundred(operation_world, lookup):
    from datetime import timedelta

    factory, pid, snapshot, _wake = operation_world
    async with factory() as db:
        first = await _request(db, pid, "history-main")
        operation_id = first.operation.id
        await _request(db, pid, "history-alias", operation_type="refresh_all", actions=("reports",))
        first.operation.status = "succeeded"
        first.operation.created_at = T0 - timedelta(days=1)
        db.add_all([operation_row(pid, minutes=i, key=f"newer-{i}") for i in range(105)])
        await db.commit()
    async with factory() as db:
        params = {} if lookup == "main" else {"operation_type": "refresh_all", "actions": ("reports",)}
        result = await _request(db, pid, f"history-{lookup}", **params)
        assert result.disposition == "replayed" and result.operation.id == operation_id
        assert await db.scalar(sa.select(sa.func.count()).select_from(ConsolOperation)) == 106
        await db.commit()
    assert snapshot.await_count == 2


async def test_alias_is_exact_and_scoped_by_project_and_year(operation_world):
    factory, pid, snapshot, _wake = operation_world
    key = "formula:exact"
    async with factory() as db:
        other = await add_project(db, "【合成】其他合并项目", report_scope="consolidated")
        wrong_project = operation_row(other, key=key)
        wrong_year = operation_row(pid, year=2024, key=key)
        prefix = operation_row(pid, key=key + "-extra")
        prefix.idempotency_keys = {key + "-alias": prefix.request_hash}
        db.add_all([wrong_project, wrong_year, prefix])
        await db.commit()
    async with factory() as db:
        result = await _request(db, pid, key)
        assert result.disposition == "created"
        assert result.operation.id not in {wrong_project.id, wrong_year.id, prefix.id}
        assert result.operation.project_id == pid and result.operation.year == 2025
        await db.commit()
    assert snapshot.await_count == 1


@pytest.mark.parametrize("key", ["hash-main", "hash-alias"])
async def test_replay_rejects_a_different_incoming_request(operation_world, key):
    factory, pid, _snapshot, _wake = operation_world
    async with factory() as db:
        await _request(db, pid, "hash-main")
        await _request(db, pid, "hash-alias", operation_type="refresh_all", actions=("reports",))
        await db.commit()
    async with factory() as db:
        with pytest.raises(operations.OperationConflict, match="同一幂等键对应了不同的合并请求"):
            await _request(db, pid, key, actions=("different-action",))

@pytest.mark.parametrize("persisted_status", ["queued", "succeeded"])
async def test_real_outbox_retry_reuses_committed_operation(operation_world, persisted_status):
    """真实派发链的两库局部接缝；不声称同库 PG 事务隔离或进程崩溃已验证。"""
    from app.models.base import ProjectStatus
    from app.models.core import Project
    from app.models.dataset_models import EventOutboxDLQ, ImportEventConsumption
    from app.services.formula_settings import outbox as fs_outbox
    from app.services.import_event_outbox_service import ImportEventOutboxService
    from app.services.workpaper_sync.outbox import (
        DurableEventOutboxService, FANOUT_HANDLER_NAME, FANOUT_HANDLER_VERSION,
    )

    operation_factory, pid, snapshot, wake = operation_world
    assert propagation.HANDLERS["consol_note"] is propagation.propagate_consol_note
    assert propagation._delivery_event_id.get() is None

    async def publish(factory, event_id):
        async with factory() as db:
            ok = await ImportEventOutboxService.publish_one(db, event_id)
            await db.commit()
        return ok

    # 两套纯内存库保留两侧真实提交，避免 SQLite 单连接的内层 commit 结束外层保存点。
    models = (ImportEventOutbox, ImportEventConsumption, EventOutboxDLQ)
    async with make_db(extra_models=models) as delivery_factory:
        async with delivery_factory() as db:
            db.add(Project(
                id=pid, name="【合成】R4 派发项目", client_name="【合成】R4 派发项目",
                status=ProjectStatus.execution, template_type="soe",
                report_scope="consolidated", audit_year=2025,
            ))
            await db.flush()
            event = outbox_row(
                pid, domain="consol_note", status=OutboxStatus.pending,
                include_receipt=False,
            )
            event.payload = {**event.payload, "slot_keys": ["五、1|余额"]}
            event_id = event.id
            db.add(event)
            await db.commit()

        # operation 独立提交之后才注入通知失败；不替换 handler/deliver/request_operation。
        wake.side_effect = RuntimeError("注入：operation 提交后通知失败")
        assert await publish(delivery_factory, event_id) is False
        assert propagation._delivery_event_id.get() is None
        async with delivery_factory() as db:
            event = await db.get(ImportEventOutbox, event_id)
            assert (event.status, event.attempt_count) == (OutboxStatus.failed, 1)
            assert "operation 提交后通知失败" in event.last_error
            receipt = event.payload[fs_outbox.RECEIPT_KEY]
            assert receipt["outbox_id"] == str(event_id)
            assert receipt["delivery_status"] == receipt["action_status"] == "failed"
            assert await db.scalar(sa.select(sa.func.count()).select_from(ImportEventConsumption)) == 0

        # fresh session 读回首轮已提交 operation，分别覆盖排队态与已完成终态。
        async with operation_factory() as db:
            operation = (await db.execute(sa.select(ConsolOperation))).scalar_one()
            operation_id = operation.id
            original_hash = operation.request_hash
            assert operation.idempotency_key == f"formula:{event_id}"
            assert operation.idempotency_keys == {f"formula:{event_id}": original_hash}
            assert operation.revision == 1
            operation.status = persisted_status
            await db.commit()

        wake.side_effect = None
        assert await publish(delivery_factory, event_id) is True
        assert propagation._delivery_event_id.get() is None
        async with delivery_factory() as db:
            event = await db.get(ImportEventOutbox, event_id)
            assert (event.status, event.attempt_count, event.last_error) == (OutboxStatus.published, 1, None)
            assert event.published_at is not None
            receipt = event.payload[fs_outbox.RECEIPT_KEY]
            assert receipt["outbox_id"] == str(event_id)
            assert receipt["delivery_status"] == "published"
            assert receipt["operation_id"] == str(operation_id)
            assert receipt["operation_status"] == receipt["action_status"] == persisted_status
            assert receipt["handler_result"]["disposition"] == "replayed"
            assert receipt["handler_result"]["sections"] == ["五、1"]
            consumption = (await db.execute(sa.select(ImportEventConsumption))).scalar_one()
            assert consumption.event_id == str(event_id)
            assert consumption.handler_name == DurableEventOutboxService.handler_key(
                FANOUT_HANDLER_NAME, FANOUT_HANDLER_VERSION,
            )
            assert (consumption.project_id, consumption.year) == (pid, 2025)
            assert await db.scalar(sa.select(sa.func.count()).select_from(ImportEventOutbox)) == 1

        async with operation_factory() as db:
            operation = (await db.execute(sa.select(ConsolOperation))).scalar_one()
            assert (operation.id, operation.status, operation.revision) == (
                operation_id, persisted_status, 1,
            )
            assert operation.request_hash == original_hash
            assert operation.idempotency_keys == {f"formula:{event_id}": original_hash}

        assert snapshot.await_count == 1
        assert wake.call_count == 2
        assert await publish(delivery_factory, event_id) is False
        assert snapshot.await_count == 1 and wake.call_count == 2
