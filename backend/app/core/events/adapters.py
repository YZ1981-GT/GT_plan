"""EventPayload / TaskEvent ↔ CanonicalEventEnvelopeV1 双向 adapter。

两条链各自 round-trip；禁止 adapter 把一条 bus 代理到另一条。
旧 EventPayload 订阅签名保持不变：sidecar 写入 extra[_envelope_v1]。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.core.events.envelope import (
    ENVELOPE_SIDECAR_KEY,
    EVENT_KIND_DURABLE,
    EVENT_KIND_IN_PROCESS,
    PRODUCER_EVENT_BUS,
    PRODUCER_TASK_EVENT_BUS,
    CanonicalEventEnvelopeV1,
    EnvelopeConstructionError,
    compute_durable_idempotency_key,
)
from app.models.audit_platform_schemas import EventPayload, EventType
from app.models.phase15_enums import TaskEventStatus
from app.models.phase15_models import TaskEvent


def _as_uuid(value: Any) -> UUID | None:
    if value is None or value == "":
        return None
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def _sidecar_from_envelope(envelope: CanonicalEventEnvelopeV1) -> dict[str, Any]:
    return {
        "event_id": str(envelope.event_id),
        "envelope_version": envelope.envelope_version,
        "event_schema_version": envelope.event_schema_version,
        "event_kind": envelope.event_kind,
        "occurred_at": envelope.occurred_at.isoformat(),
        "producer": envelope.producer,
        "trace_id": envelope.trace_id,
        "correlation_id": envelope.correlation_id,
        "causation_id": envelope.causation_id,
        "actor_id": str(envelope.actor_id) if envelope.actor_id else None,
        "actor_role": envelope.actor_role,
        "reason_code": envelope.reason_code,
        "idempotency_key": envelope.idempotency_key,
        "aggregate_type": envelope.aggregate_type,
        "aggregate_id": envelope.aggregate_id,
        "aggregate_version": envelope.aggregate_version,
    }


class EventPayloadAdapter:
    """进程内 EventPayload ↔ 信封。不触碰 TaskEventBus。"""

    @staticmethod
    def to_envelope(payload: EventPayload) -> CanonicalEventEnvelopeV1:
        extra = dict(payload.extra or {})
        sidecar = extra.pop(ENVELOPE_SIDECAR_KEY, None) or {}
        data = {
            "account_codes": list(payload.account_codes) if payload.account_codes else None,
            "batch_id": str(payload.batch_id) if payload.batch_id else None,
            "entry_group_id": str(payload.entry_group_id) if payload.entry_group_id else None,
            "extra": extra,
        }
        occurred_at = None
        if sidecar.get("occurred_at"):
            occurred_at = datetime.fromisoformat(str(sidecar["occurred_at"]))
        return CanonicalEventEnvelopeV1.create(
            event_type=payload.event_type.value
            if isinstance(payload.event_type, EventType)
            else str(payload.event_type),
            event_kind=str(sidecar.get("event_kind") or EVENT_KIND_IN_PROCESS),
            data=data,
            producer=str(sidecar.get("producer") or PRODUCER_EVENT_BUS),
            project_id=payload.project_id,
            year=payload.year,
            event_id=_as_uuid(sidecar.get("event_id")),
            event_schema_version=int(sidecar.get("event_schema_version") or 1),
            occurred_at=occurred_at,
            trace_id=sidecar.get("trace_id"),
            correlation_id=sidecar.get("correlation_id"),
            causation_id=sidecar.get("causation_id"),
            actor_id=_as_uuid(sidecar.get("actor_id")),
            actor_role=sidecar.get("actor_role"),
            reason_code=sidecar.get("reason_code"),
            idempotency_key=sidecar.get("idempotency_key"),
            aggregate_type=sidecar.get("aggregate_type"),
            aggregate_id=sidecar.get("aggregate_id"),
            aggregate_version=sidecar.get("aggregate_version"),
        )

    @staticmethod
    def from_envelope(envelope: CanonicalEventEnvelopeV1) -> EventPayload:
        try:
            event_type = EventType(envelope.event_type)
        except ValueError as exc:
            raise EnvelopeConstructionError(
                f"cannot adapt event_type {envelope.event_type!r} to EventPayload"
            ) from exc
        if envelope.project_id is None:
            raise EnvelopeConstructionError(
                "EventPayload.project_id is required; envelope.project_id is missing"
            )
        body = dict(envelope.data or {})
        extra = dict(body.get("extra") or {})
        extra[ENVELOPE_SIDECAR_KEY] = _sidecar_from_envelope(envelope)
        batch_id = _as_uuid(body.get("batch_id"))
        entry_group_id = _as_uuid(body.get("entry_group_id"))
        account_codes = body.get("account_codes")
        return EventPayload(
            event_type=event_type,
            project_id=envelope.project_id,
            year=envelope.year,
            account_codes=list(account_codes) if account_codes else None,
            batch_id=batch_id,
            entry_group_id=entry_group_id,
            extra=extra,
        )


class TaskEventAdapter:
    """持久 TaskEvent ↔ 信封。不触碰 EventBus transport。"""

    @staticmethod
    def envelope_for_publish(
        *,
        project_id: UUID,
        event_type: str,
        payload: dict[str, Any],
        trace_id: str,
        task_node_id: UUID | None = None,
        actor_id: UUID | None = None,
        reason_code: str | None = None,
    ) -> CanonicalEventEnvelopeV1:
        data = dict(payload or {})
        if task_node_id is not None:
            data.setdefault("task_node_id", str(task_node_id))
        return CanonicalEventEnvelopeV1.create(
            event_type=event_type,
            event_kind=EVENT_KIND_DURABLE,
            data=data,
            producer=PRODUCER_TASK_EVENT_BUS,
            project_id=project_id,
            trace_id=trace_id,
            correlation_id=trace_id,
            actor_id=actor_id,
            reason_code=reason_code,
            idempotency_key=compute_durable_idempotency_key(
                project_id, event_type, dict(payload or {})
            ),
            aggregate_type=data.get("aggregate_type"),
            aggregate_id=data.get("aggregate_id"),
            aggregate_version=data.get("aggregate_version"),
        )

    @staticmethod
    def to_envelope(event: TaskEvent) -> CanonicalEventEnvelopeV1:
        payload = dict(event.payload or {})
        occurred = event.created_at
        if occurred is not None and occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=timezone.utc)
        idem = event.idempotency_key or compute_durable_idempotency_key(
            event.project_id, event.event_type, payload
        )
        aggregate_id = event.aggregate_id
        return CanonicalEventEnvelopeV1.create(
            event_id=event.id,
            event_type=event.event_type,
            event_kind=EVENT_KIND_DURABLE,
            data=payload,
            producer=PRODUCER_TASK_EVENT_BUS,
            project_id=event.project_id,
            occurred_at=occurred,
            trace_id=event.trace_id,
            correlation_id=payload.get("correlation_id") or event.trace_id,
            causation_id=payload.get("causation_id"),
            idempotency_key=idem,
            aggregate_type=event.aggregate_type,
            aggregate_id=str(aggregate_id) if aggregate_id else None,
            aggregate_version=event.aggregate_version,
        )

    @staticmethod
    def from_envelope(envelope: CanonicalEventEnvelopeV1) -> TaskEvent:
        if envelope.project_id is None:
            raise EnvelopeConstructionError(
                "TaskEvent.project_id is required; envelope.project_id is missing"
            )
        occurred = envelope.occurred_at
        if occurred.tzinfo is not None:
            occurred = occurred.replace(tzinfo=None)
        aggregate_id = _as_uuid(envelope.aggregate_id)
        task_node_raw = (envelope.data or {}).get("task_node_id")
        return TaskEvent(
            id=envelope.event_id,
            project_id=envelope.project_id,
            event_type=envelope.event_type,
            task_node_id=_as_uuid(task_node_raw),
            payload=dict(envelope.data or {}),
            status=TaskEventStatus.queued,
            trace_id=envelope.trace_id,
            created_at=occurred,
            idempotency_key=envelope.idempotency_key,
            aggregate_type=envelope.aggregate_type,
            aggregate_id=aggregate_id,
            aggregate_version=envelope.aggregate_version,
        )
