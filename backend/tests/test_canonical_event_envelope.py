"""CanonicalEventEnvelopeV1 与双向 adapter 契约。

Validates: Requirements 8.1-8.7 / Properties 15, 16
"""
from __future__ import annotations

import ast
import inspect
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import get_args

import pytest
from pydantic import ValidationError

from app.core.events import (
    ENVELOPE_SIDECAR_KEY,
    EVENT_KIND_DURABLE,
    EVENT_KIND_IN_PROCESS,
    CanonicalEventEnvelopeV1,
    EnvelopeConstructionError,
    EventPayloadAdapter,
    TaskEventAdapter,
    payload_digest,
)
from app.models.audit_platform_schemas import EventPayload, EventType
from app.models.phase15_models import TaskEvent
from app.services.event_bus import EventBus, EventHandler
from app.services.task_event_bus import TaskEventBus

ROOT = Path(__file__).resolve().parents[2]
EVENT_BUS_PATH = ROOT / "backend/app/services/event_bus.py"
TASK_EVENT_BUS_PATH = ROOT / "backend/app/services/task_event_bus.py"


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
    return names


def test_envelope_requires_identity_fields() -> None:
    required = {
        "envelope_version",
        "event_id",
        "event_type",
        "event_schema_version",
        "event_kind",
        "occurred_at",
        "project_id",
        "year",
        "data",
        "producer",
        "trace_id",
        "correlation_id",
        "causation_id",
        "actor_id",
        "actor_role",
        "reason_code",
        "idempotency_key",
        "aggregate_type",
        "aggregate_id",
        "aggregate_version",
    }
    assert required <= set(CanonicalEventEnvelopeV1.model_fields)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"event_type": "", "event_kind": EVENT_KIND_IN_PROCESS, "data": {}, "producer": "p"},
        {"event_type": "t", "event_kind": "", "data": {}, "producer": "p"},
        {"event_type": "t", "event_kind": EVENT_KIND_IN_PROCESS, "data": None, "producer": "p"},
        {"event_type": "t", "event_kind": EVENT_KIND_IN_PROCESS, "data": {}, "producer": ""},
    ],
)
def test_create_rejects_missing_required_fields(kwargs: dict) -> None:
    with pytest.raises(EnvelopeConstructionError):
        CanonicalEventEnvelopeV1.create(**kwargs)


def test_direct_construction_without_identity_fails() -> None:
    with pytest.raises((ValidationError, EnvelopeConstructionError)):
        CanonicalEventEnvelopeV1(
            event_type="t",
            event_kind=EVENT_KIND_IN_PROCESS,
            producer="p",
        )


def test_create_fills_event_id_time_trace_idempotency() -> None:
    env = CanonicalEventEnvelopeV1.create(
        event_type="dispatch.created",
        event_kind=EVENT_KIND_IN_PROCESS,
        data={"ok": True},
        producer="event_bus",
        project_id=uuid.uuid4(),
    )
    assert env.envelope_version == "1"
    assert env.event_id
    assert env.occurred_at
    assert env.trace_id
    assert env.correlation_id == env.trace_id
    assert env.idempotency_key
    assert env.causation_id is None


def test_serialize_redacts_secrets_and_does_not_mutate_live_data() -> None:
    env = CanonicalEventEnvelopeV1.create(
        event_type="t",
        event_kind=EVENT_KIND_IN_PROCESS,
        producer="event_bus",
        data={
            "token": "live-token",
            "password": "secret",
            "nested": {"api_key": "k", "ok": 1},
            "attachment_body": "FILEBYTES",
            "visible": "keep",
        },
    )
    dumped = env.serialize()
    assert dumped["data"]["token"] == "[REDACTED]"
    assert dumped["data"]["password"] == "[REDACTED]"
    assert dumped["data"]["nested"]["api_key"] == "[REDACTED]"
    assert dumped["data"]["nested"]["ok"] == 1
    assert dumped["data"]["attachment_body"] == "[REDACTED]"
    assert dumped["data"]["visible"] == "keep"
    assert env.data["token"] == "live-token"


def test_eventpayload_round_trip_preserves_identity_causality_and_digest() -> None:
    payload = EventPayload(
        event_type=EventType.DISPATCH_CREATED,
        project_id=uuid.uuid4(),
        year=2024,
        account_codes=["1001"],
        extra={"foo": "bar", "causation_seed": "x"},
    )
    env1 = EventPayloadAdapter.to_envelope(payload)
    restored = EventPayloadAdapter.from_envelope(env1)
    env2 = EventPayloadAdapter.to_envelope(restored)

    assert restored.event_type == payload.event_type
    assert restored.project_id == payload.project_id
    assert restored.year == payload.year
    assert restored.account_codes == payload.account_codes
    assert restored.extra["foo"] == "bar"
    assert ENVELOPE_SIDECAR_KEY in restored.extra

    assert env1.event_id == env2.event_id
    assert env1.trace_id == env2.trace_id
    assert env1.correlation_id == env2.correlation_id
    assert env1.causation_id == env2.causation_id
    assert env1.idempotency_key == env2.idempotency_key
    assert payload_digest(env1.data) == payload_digest(env2.data)


def test_eventpayload_causation_chain_survives_round_trip() -> None:
    project_id = uuid.uuid4()
    env = CanonicalEventEnvelopeV1.create(
        event_type=EventType.DISPATCH_CREATED.value,
        event_kind=EVENT_KIND_IN_PROCESS,
        data={"extra": {"k": 1}, "account_codes": None, "batch_id": None, "entry_group_id": None},
        producer="event_bus",
        project_id=project_id,
        trace_id="trc_parent",
        correlation_id="trc_parent",
        causation_id="evt_cause",
    )
    restored = EventPayloadAdapter.from_envelope(env)
    env2 = EventPayloadAdapter.to_envelope(restored)
    assert env2.trace_id == "trc_parent"
    assert env2.correlation_id == "trc_parent"
    assert env2.causation_id == "evt_cause"


def test_taskevent_round_trip_preserves_identity_and_payload() -> None:
    event = TaskEvent(
        id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        event_type="trim_applied",
        payload={"ref_id": "proc_001", "version": "1"},
        status="queued",
        trace_id="trc_task_1",
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        idempotency_key="idem-abc",
        aggregate_type=None,
        aggregate_id=None,
        aggregate_version=None,
    )
    env1 = TaskEventAdapter.to_envelope(event)
    back = TaskEventAdapter.from_envelope(env1)
    env2 = TaskEventAdapter.to_envelope(back)

    assert back.id == event.id
    assert back.project_id == event.project_id
    assert back.event_type == event.event_type
    assert back.trace_id == event.trace_id
    assert back.idempotency_key == event.idempotency_key
    assert back.payload["ref_id"] == "proc_001"
    assert env1.event_id == env2.event_id
    assert env1.idempotency_key == env2.idempotency_key == "idem-abc"
    assert env1.event_kind == EVENT_KIND_DURABLE
    assert payload_digest(env1.data) == payload_digest(env2.data)


def test_taskevent_publish_envelope_idempotency_digest_stable() -> None:
    project_id = uuid.uuid4()
    payload = {"ref_id": "r1", "version": "v2"}
    env_a = TaskEventAdapter.envelope_for_publish(
        project_id=project_id,
        event_type="trim_applied",
        payload=payload,
        trace_id="trc_stable",
    )
    env_b = TaskEventAdapter.envelope_for_publish(
        project_id=project_id,
        event_type="trim_applied",
        payload=dict(payload),
        trace_id="trc_other",
    )
    assert env_a.idempotency_key == env_b.idempotency_key
    assert env_a.trace_id != env_b.trace_id
    assert payload_digest(env_a.data) == payload_digest(env_b.data)


def test_buses_share_envelope_module_but_not_each_other() -> None:
    event_imports = _imported_modules(EVENT_BUS_PATH)
    task_imports = _imported_modules(TASK_EVENT_BUS_PATH)
    assert "app.core.events.adapters" in event_imports
    assert "app.core.events.adapters" in task_imports
    assert "app.services.task_event_bus" not in event_imports
    assert "app.services.event_bus" not in task_imports
    assert not (ROOT / "backend/app/core/event_bus.py").exists()


def test_event_handler_signature_still_eventpayload() -> None:
    src = EVENT_BUS_PATH.read_text(encoding="utf-8")
    assert "EventHandler = Callable[[EventPayload]" in src
    params = get_args(EventHandler)
    first = params[0]
    inner = first[0] if isinstance(first, (list, tuple)) else first
    assert inner is EventPayload


def test_old_eventpayload_and_taskevent_fields_not_deleted() -> None:
    payload_fields = set(EventPayload.model_fields)
    assert {"event_type", "project_id", "year", "account_codes", "extra"} <= payload_fields
    for col in (
        "id",
        "project_id",
        "event_type",
        "payload",
        "status",
        "trace_id",
        "idempotency_key",
        "aggregate_type",
    ):
        assert hasattr(TaskEvent, col), col


@pytest.mark.asyncio
async def test_eventbus_subscribe_still_receives_eventpayload() -> None:
    bus = EventBus(debounce_ms=0)
    seen: list[EventPayload] = []

    async def handler(payload: EventPayload) -> None:
        seen.append(payload)

    bus.subscribe(EventType.DISPATCH_CREATED, handler)
    original = EventPayload(
        event_type=EventType.DISPATCH_CREATED,
        project_id=uuid.uuid4(),
        extra={"k": "v"},
    )
    await bus.publish_immediate(original)
    assert len(seen) == 1
    assert isinstance(seen[0], EventPayload)
    assert seen[0].event_type is EventType.DISPATCH_CREATED
    assert seen[0].extra["k"] == "v"


def test_task_event_bus_publish_signature_unchanged() -> None:
    sig = inspect.signature(TaskEventBus.publish)
    names = list(sig.parameters)
    assert names[:6] == ["self", "db", "project_id", "event_type", "task_node_id", "payload"]
