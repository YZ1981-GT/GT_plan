"""平台事件信封：共享语义，不共享运输。"""
from app.core.events.adapters import EventPayloadAdapter, TaskEventAdapter
from app.core.events.envelope import (
    ENVELOPE_SIDECAR_KEY,
    ENVELOPE_VERSION_V1,
    EVENT_KIND_DURABLE,
    EVENT_KIND_IN_PROCESS,
    PRODUCER_EVENT_BUS,
    PRODUCER_TASK_EVENT_BUS,
    CanonicalEventEnvelopeV1,
    EnvelopeConstructionError,
    compute_durable_idempotency_key,
    payload_digest,
    redact_secrets,
)

__all__ = [
    "ENVELOPE_SIDECAR_KEY",
    "ENVELOPE_VERSION_V1",
    "EVENT_KIND_DURABLE",
    "EVENT_KIND_IN_PROCESS",
    "PRODUCER_EVENT_BUS",
    "PRODUCER_TASK_EVENT_BUS",
    "CanonicalEventEnvelopeV1",
    "EnvelopeConstructionError",
    "EventPayloadAdapter",
    "TaskEventAdapter",
    "compute_durable_idempotency_key",
    "payload_digest",
    "redact_secrets",
]
