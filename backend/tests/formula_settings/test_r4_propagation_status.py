"""R4：真实 SQLite 状态聚合；派发、业务与 operation 七态分开。"""
from __future__ import annotations

import uuid

import pytest

from app.models.audit_platform_schemas import EventType
from app.models.consol_operation_models import ConsolOperation, OPERATION_STATUSES
from app.models.dataset_models import EventOutboxDLQ, ImportEventOutbox, OutboxStatus
from app.services.formula_settings.outbox import ORIGIN, RECEIPT_KEY
from app.services.formula_settings.propagation_status import WINDOW, propagation_status

from ._env import add_project, make_db
from ._r4_test_data import T0, operation_row, outbox_row

MODELS = (ImportEventOutbox, EventOutboxDLQ, ConsolOperation)


async def test_more_than_window_of_other_origins_cannot_hide_formula_receipt():
    async with make_db(extra_models=MODELS) as factory:
        async with factory() as db:
            pid = await add_project(db, "【合成】来源过滤")
            target = outbox_row(pid, minutes=-1)
            db.add(target)
            db.add_all([outbox_row(pid, origin="other-origin", minutes=i) for i in range(WINDOW + 5)])
            await db.commit()
            result = await propagation_status(db, pid, max_attempts=20)
    assert result["counts"] == {"pending": 0, "failed": 0, "published": 1}
    assert [r["outbox_id"] for r in result["receipts"]] == [str(target.id)]

@pytest.mark.parametrize("name", ["year", "domain", "publish_token", "outbox_id"])
async def test_each_exact_filter_is_applied_before_window_limit(name):
    async with make_db(extra_models=MODELS) as factory:
        async with factory() as db:
            pid = await add_project(db, "【合成】精确过滤")
            target = outbox_row(pid, year=2025, domain="note", token="batch-1", minutes=-1)
            db.add(target)
            noise = {"year": 2024} if name == "year" else {"domain": "report"} if name == "domain" else {
                "token": "batch-10"} if name == "publish_token" else {}
            defaults = {"year": 2025, "domain": "note", "token": "batch-1"}
            db.add_all([outbox_row(pid, **{**defaults, **noise}, minutes=i) for i in range(WINDOW + 5)])
            await db.commit()
            value = {"year": 2025, "domain": "note", "publish_token": "batch-1", "outbox_id": target.id}[name]
            result = await propagation_status(db, pid, max_attempts=20, **{name: value})
    assert result["counts"]["published"] == 1
    assert [r["outbox_id"] for r in result["receipts"]] == [str(target.id)]


async def test_dead_letters_apply_same_filters_and_use_original_event_id():
    async with make_db(extra_models=MODELS) as factory:
        async with factory() as db:
            pid = await add_project(db, "【合成】死信过滤")
            other = await add_project(db, "【合成】其他项目")
            target = outbox_row(pid, domain="note", status=OutboxStatus.failed)
            sibling = outbox_row(pid, domain="note", status=OutboxStatus.failed)
            db.add_all([target, sibling])
            await db.flush()

            def dead_letter(**overrides):
                return EventOutboxDLQ(**{
                    "id": uuid.uuid4(), "original_event_id": target.id, "project_id": pid,
                    "year": 2025, "event_type": EventType.FORMULA_CONFIG_CHANGED.value,
                    "payload": {"origin": ORIGIN, "domain": "note", "publish_token": "batch-1"},
                    "attempt_count": 20, "failure_reason": "合成死信", **overrides,
                })

            target_dlq = dead_letter()
            db.add_all([
                target_dlq, dead_letter(original_event_id=sibling.id), dead_letter(year=2024),
                dead_letter(project_id=other), dead_letter(resolved_at=T0),
                dead_letter(event_type=EventType.WORKPAPER_SAVED.value),
                dead_letter(payload={"origin": "other", "domain": "note", "publish_token": "batch-1"}),
                dead_letter(payload={"origin": ORIGIN, "domain": "report", "publish_token": "batch-1"}),
                dead_letter(payload={"origin": ORIGIN, "domain": "note", "publish_token": "batch-10"}),
            ])
            await db.commit()
            assert target_dlq.id != target.id
            result = await propagation_status(
                db, pid, max_attempts=20, year=2025, domain="note",
                publish_token="batch-1", outbox_id=target.id,
            )
    assert result["dead_letter"] == 1
    assert [r["outbox_id"] for r in result["receipts"]] == [str(target.id)]
    assert result["counts"] == {"pending": 0, "failed": 1, "published": 0}

@pytest.mark.parametrize("status", OPERATION_STATUSES)
async def test_published_receipt_reads_the_actual_operation_status(status):
    async with make_db(extra_models=MODELS) as factory:
        async with factory() as db:
            pid = await add_project(db, "【合成】任务七态")
            operation = operation_row(pid, status=status)
            operation.errors = [{"step": "notes", "message": "合成任务信息"}]
            row = outbox_row(pid, domain="consol_note", operation_id=operation.id, action="queued")
            db.add_all([operation, row])
            await db.commit()
            result = await propagation_status(db, pid, max_attempts=20)
    receipt, = result["receipts"]
    assert receipt["delivery_status"] == "published"
    assert receipt["action_status"] == receipt["operation_status"] == status
    assert receipt["operation_errors"] == operation.errors
    assert result["action_counts"] == {status: 1}
    pending = int(status in {"queued", "running"})
    assert result["business_pending"] == pending
    assert result["has_pending_actions"] is bool(pending)
    assert result["state"] == ("running" if pending else "idle")


@pytest.mark.parametrize("case", ["missing", "other_project", "other_year", "invalid_id"])
async def test_operation_association_requires_real_project_year_and_uuid(case):
    async with make_db(extra_models=MODELS) as factory:
        async with factory() as db:
            pid = await add_project(db, "【合成】任务关联")
            other = await add_project(db, "【合成】其他任务项目")
            operation = operation_row(other if case == "other_project" else pid,
                                      year=2024 if case == "other_year" else 2025)
            if case not in {"missing", "invalid_id"}:
                db.add(operation)
            operation_id = "invalid-operation" if case == "invalid_id" else operation.id
            row = outbox_row(pid, domain="consol_note", operation_id=operation_id, action="queued")
            db.add(row)
            await db.commit()
            result = await propagation_status(db, pid, max_attempts=20)
    receipt, = result["receipts"]
    assert receipt["action_status"] == "unknown" and receipt["operation_status"] is None
    assert result["action_counts"] == {"unknown": 1}
    assert result["business_pending"] == 0 and result["has_pending_actions"] is False

@pytest.mark.parametrize("broken", ["legacy", "schema", "outbox_id", "year", "domain", "publish_token"])
async def test_legacy_or_mismatched_receipt_is_unknown_not_success(broken):
    async with make_db(extra_models=MODELS) as factory:
        async with factory() as db:
            pid = await add_project(db, "【合成】旧回执")
            row = outbox_row(pid, include_receipt=broken != "legacy")
            if broken != "legacy":
                field, value = {
                    "schema": ("schema_version", 2), "outbox_id": ("outbox_id", str(uuid.uuid4())),
                    "year": ("year", 2024), "domain": ("domain", "note"),
                    "publish_token": ("publish_token", "batch-10"),
                }[broken]
                row.payload = {**row.payload, RECEIPT_KEY: {**row.payload[RECEIPT_KEY], field: value}}
            db.add(row)
            await db.commit()
            result = await propagation_status(db, pid, max_attempts=20)
    receipt, = result["receipts"]
    assert receipt["delivery_status"] == "published" and receipt["action_status"] == "unknown"
    assert receipt["handler_result"] == {} and receipt["operation_id"] is None
    assert result["action_counts"] == {"unknown": 1}


async def test_failed_delivery_is_not_washed_green_by_successful_operation():
    async with make_db(extra_models=MODELS) as factory:
        async with factory() as db:
            pid = await add_project(db, "【合成】失败派发")
            operation = operation_row(pid, status="succeeded")
            row = outbox_row(pid, domain="consol_note", operation_id=operation.id,
                             status=OutboxStatus.failed, action="failed")
            db.add_all([operation, row])
            await db.commit()
            result = await propagation_status(db, pid, max_attempts=20)
    receipt, = result["receipts"]
    assert receipt["operation_status"] == "succeeded"
    assert receipt["delivery_status"] == receipt["action_status"] == "failed"
    assert receipt["last_error"] == "合成派发失败"
    assert result["state"] == "failed" and result["retrying"] == 1
    assert result["has_pending_actions"] is True

@pytest.mark.parametrize("operation_id_kind", ["real", "invalid"])
async def test_failed_delivery_overrides_stored_success_even_with_invalid_operation_id(operation_id_kind):
    async with make_db(extra_models=MODELS) as factory:
        async with factory() as db:
            pid = await add_project(db, "【合成】陈旧成功回执")
            operation = operation_row(pid, status="succeeded")
            db.add(operation)
            operation_id = operation.id if operation_id_kind == "real" else "invalid-operation"
            row = outbox_row(pid, domain="consol_note", operation_id=operation_id,
                             status=OutboxStatus.failed, action="succeeded")
            db.add(row)
            await db.commit()
            result = await propagation_status(db, pid, max_attempts=20)
    receipt, = result["receipts"]
    assert receipt["delivery_status"] == receipt["action_status"] == "failed"
    assert receipt["operation_status"] == ("succeeded" if operation_id_kind == "real" else None)
    assert result["action_counts"] == {"failed": 1} and result["state"] == "failed"


async def test_failed_legacy_row_remains_unknown_without_a_valid_receipt():
    async with make_db(extra_models=MODELS) as factory:
        async with factory() as db:
            pid = await add_project(db, "【合成】失败旧行")
            row = outbox_row(pid, status=OutboxStatus.failed, include_receipt=False)
            db.add(row)
            await db.commit()
            result = await propagation_status(db, pid, max_attempts=20)
    receipt, = result["receipts"]
    assert receipt["delivery_status"] == "failed" and receipt["action_status"] == "unknown"
    assert result["action_counts"] == {"unknown": 1} and result["state"] == "failed"


@pytest.mark.parametrize("stored_status", OPERATION_STATUSES)
async def test_operation_state_without_operation_id_is_unknown(stored_status):
    """只有任务状态字符串不是任务存在或完成的证据。"""
    async with make_db(extra_models=MODELS) as factory:
        async with factory() as db:
            pid = await add_project(db, "【合成】缺任务身份")
            row = outbox_row(pid, domain="consol_note", action=stored_status)
            db.add(row)
            await db.commit()
        async with factory() as db:
            result = await propagation_status(db, pid, max_attempts=20)
    receipt, = result["receipts"]
    assert receipt["operation_id"] is None and receipt["operation_status"] is None
    assert receipt["action_status"] == "unknown"
    assert result["action_counts"] == {"unknown": 1}
    assert result["business_pending"] == 0 and result["has_pending_actions"] is False

@pytest.mark.parametrize("stored_status", OPERATION_STATUSES)
async def test_operation_id_without_frozen_year_does_not_borrow_project_year(stored_status):
    async with make_db(extra_models=MODELS) as factory:
        async with factory() as db:
            pid = await add_project(db, "【合成】缺冻结年度")
            operation = operation_row(pid, status="succeeded")
            row = outbox_row(pid, year=None, domain="consol_note", operation_id=operation.id,
                             action=stored_status)
            db.add_all([operation, row])
            await db.commit()
        async with factory() as db:
            result = await propagation_status(db, pid, max_attempts=20)
    receipt, = result["receipts"]
    assert receipt["year"] is None and receipt["operation_status"] is None
    assert receipt["action_status"] == "unknown"
    assert result["action_counts"] == {"unknown": 1}
    assert result["business_pending"] == 0


@pytest.mark.parametrize("stored_status", [None, [], {}, ["succeeded"], 7, True, "unregistered-status"])
async def test_malformed_action_status_cannot_break_counts_or_become_success(stored_status):
    async with make_db(extra_models=MODELS) as factory:
        async with factory() as db:
            pid = await add_project(db, "【合成】坏业务状态")
            row = outbox_row(pid, action=stored_status)
            db.add(row)
            await db.commit()
        async with factory() as db:
            result = await propagation_status(db, pid, max_attempts=20)
    receipt, = result["receipts"]
    assert receipt["delivery_status"] == "published" and receipt["action_status"] == "unknown"
    assert result["action_counts"] == {"unknown": 1}
    assert result["business_pending"] == 0 and result["has_pending_actions"] is False


@pytest.mark.parametrize("style", ["uppercase", "braced"])
async def test_operation_uuid_text_is_normalized_before_identity_lookup(style):
    async with make_db(extra_models=MODELS) as factory:
        async with factory() as db:
            pid = await add_project(db, "【合成】任务 UUID 表示")
            operation = operation_row(pid, status="partial")
            text = str(operation.id).upper() if style == "uppercase" else "{" + str(operation.id) + "}"
            row = outbox_row(pid, domain="consol_note", operation_id=text, action="queued")
            db.add_all([operation, row])
            await db.commit()
        async with factory() as db:
            result = await propagation_status(db, pid, max_attempts=20)
    receipt, = result["receipts"]
    assert receipt["operation_id"] == text
    assert receipt["operation_status"] == receipt["action_status"] == "partial"
    assert result["action_counts"] == {"partial": 1}


@pytest.mark.parametrize("action", ["skipped", "no_consumer", "unknown"])
async def test_non_operation_receipt_without_operation_id_keeps_its_actual_action(action):
    async with make_db(extra_models=MODELS) as factory:
        async with factory() as db:
            pid = await add_project(db, "【合成】无任务业务回执")
            row = outbox_row(pid, domain="consol_note", action=action)
            db.add(row)
            await db.commit()
        async with factory() as db:
            result = await propagation_status(db, pid, max_attempts=20)
    receipt, = result["receipts"]
    assert receipt["operation_id"] is None and receipt["operation_status"] is None
    assert receipt["action_status"] == action and result["action_counts"] == {action: 1}
    assert result["business_pending"] == 0
