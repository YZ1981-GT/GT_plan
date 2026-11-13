"""R4 用例专用合成行；只交给各用例的隔离 SQLite session。"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.models.audit_platform_schemas import EventType
from app.models.consol_operation_models import ConsolOperation
from app.models.dataset_models import ImportEventOutbox, OutboxStatus
from app.schemas.consol_context import ConsolContext
from app.schemas.consol_operation import ConsolVersionVector
from app.services.consol_operation_service import canonical_request, request_digest
from app.services.formula_settings.outbox import ORIGIN, RECEIPT_KEY

T0 = datetime(2026, 11, 3, 8, 0, tzinfo=timezone.utc)


def snapshot_pair(project_id, year, operation_id):
    context = ConsolContext(project_id=project_id, year=year, run_id=operation_id)
    vector = ConsolVersionVector(
        tree_fingerprint="a" * 64, tb_digest="b" * 64,
        elimination_digest="c" * 64, formula_digest="d" * 64,
        note_mapping_digest="e" * 64, template_digest="f" * 64, digest="0" * 64,
    )
    return context, vector


def operation_row(project_id, *, year=2025, status="succeeded", minutes=0, key=None):
    operation_id = uuid.uuid4()
    key = key or f"synthetic:{operation_id}"
    payload = canonical_request(project_id=project_id, year=year, operation_type="push",
                                trigger_source="synthetic", requested_actions=("notes",))
    digest = request_digest(payload)
    context, vector = snapshot_pair(project_id, year, operation_id)
    moment = T0 + timedelta(minutes=minutes)
    return ConsolOperation(
        id=operation_id, project_id=project_id, year=year, operation_type="push",
        idempotency_key=key, idempotency_keys={key: digest}, request_hash=digest,
        request_payload=payload, context_json=context.to_dict(),
        version_vector=vector.model_dump(mode="json"), status=status,
        revision=1, attempt=0, trigger_source="synthetic", steps=[], errors=[],
        result_refs={}, metrics={}, queued_at=moment, created_at=moment, updated_at=moment,
        lease_owner=uuid.uuid4() if status == "running" else None,
        lease_expires_at=moment + timedelta(minutes=5) if status == "running" else None,
    )


def outbox_row(project_id, *, year=2025, domain="report", token="batch-1", minutes=0,
               status=OutboxStatus.published, origin=ORIGIN, action="succeeded",
               operation_id=None, include_receipt=True):
    outbox_id = uuid.uuid4()
    payload = {"origin": origin, "domain": domain, "slot_keys": ["synthetic-slot"],
               "publish_token": token, "source": "synthetic"}
    if include_receipt:
        payload[RECEIPT_KEY] = {
            "schema_version": 1, "outbox_id": str(outbox_id), "year": year,
            "domain": domain, "publish_token": token, "delivery_status": "published",
            "action_status": action, "handler_result": {},
            "operation_id": str(operation_id) if operation_id is not None else None,
            "operation_status": "queued" if operation_id is not None else None,
        }
    moment = T0 + timedelta(minutes=minutes)
    return ImportEventOutbox(
        id=outbox_id, project_id=project_id, year=year,
        event_type=EventType.FORMULA_CONFIG_CHANGED.value, payload=payload,
        status=status, attempt_count=1 if status == OutboxStatus.failed else 0,
        last_error="合成派发失败" if status == OutboxStatus.failed else None,
        created_at=moment, published_at=moment if status == OutboxStatus.published else None,
    )
