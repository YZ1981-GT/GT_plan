"""CanonicalEventEnvelopeV1 — 两条事件链共享的身份/因果/幂等信封。

EventBus（进程内 fan-out）与 TaskEventBus（DB delivery）只共享本模型与 adapter，
transport 不合并。构造器集中生成 event_id / occurred_at / trace_id / idempotency_key。
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

ENVELOPE_VERSION_V1: Literal["1"] = "1"
EVENT_KIND_IN_PROCESS = "in_process"
EVENT_KIND_DURABLE = "durable"
PRODUCER_EVENT_BUS = "event_bus"
PRODUCER_TASK_EVENT_BUS = "task_event_bus"
ENVELOPE_SIDECAR_KEY = "_envelope_v1"

_SENSITIVE_KEY_FRAGMENTS: tuple[str, ...] = (
    "token",
    "password",
    "secret",
    "api_key",
    "authorization",
    "cookie",
    "credential",
    "connection_string",
    "attachment_body",
    "file_content",
    "raw_bytes",
    "content_base64",
)


class EnvelopeConstructionError(ValueError):
    """信封缺必填业务字段，或身份字段无法在构造期生成。"""


def redact_secrets(value: Any) -> Any:
    """递归脱敏 token/密码/附件正文；不修改入参。"""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, inner in value.items():
            lowered = str(key).lower()
            if any(fragment in lowered for fragment in _SENSITIVE_KEY_FRAGMENTS):
                out[key] = "[REDACTED]"
            else:
                out[key] = redact_secrets(inner)
        return out
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    return value


def payload_digest(data: dict[str, Any]) -> str:
    """稳定 payload digest，供 round-trip 守恒断言。"""
    canonical = json.dumps(data, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_durable_idempotency_key(
    project_id: UUID | None,
    event_type: str,
    payload: dict[str, Any],
) -> str:
    """TaskEvent 历史算法：project_id + event_type + payload.ref_id + payload.version。

    不得改哈希口径；Task 17 只要求把该键写入/等值查询 ``idempotency_key`` 列。
    """
    ref_id = (payload or {}).get("ref_id", "")
    version = (payload or {}).get("version", "")
    raw = f"{project_id}:{event_type}:{ref_id}:{version}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _new_trace_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"trc_{ts}_{uuid.uuid4().hex[:12]}"


class CanonicalEventEnvelopeV1(BaseModel):
    """共享 wire/domain 信封。双写期不得删除 EventPayload / TaskEvent 旧字段。"""

    model_config = ConfigDict(extra="forbid")

    envelope_version: Literal["1"] = ENVELOPE_VERSION_V1
    event_id: UUID
    event_type: str
    event_schema_version: int = 1
    event_kind: str
    occurred_at: datetime
    project_id: UUID | None = None
    year: int | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    producer: str
    trace_id: str
    correlation_id: str
    causation_id: str | None = None
    actor_id: UUID | None = None
    actor_role: str | None = None
    reason_code: str | None = None
    idempotency_key: str
    aggregate_type: str | None = None
    aggregate_id: str | None = None
    aggregate_version: int | None = None

    @model_validator(mode="after")
    def _reject_blank_required(self) -> CanonicalEventEnvelopeV1:
        if not str(self.event_type).strip():
            raise EnvelopeConstructionError("event_type is required")
        if not str(self.event_kind).strip():
            raise EnvelopeConstructionError("event_kind is required")
        if not str(self.producer).strip():
            raise EnvelopeConstructionError("producer is required")
        if not str(self.trace_id).strip():
            raise EnvelopeConstructionError("trace_id is required")
        if not str(self.correlation_id).strip():
            raise EnvelopeConstructionError("correlation_id is required")
        if not str(self.idempotency_key).strip():
            raise EnvelopeConstructionError("idempotency_key is required")
        if self.data is None:
            raise EnvelopeConstructionError("data is required")
        return self

    @classmethod
    def create(
        cls,
        *,
        event_type: str,
        event_kind: str,
        data: dict[str, Any],
        producer: str,
        project_id: UUID | None = None,
        year: int | None = None,
        event_id: UUID | None = None,
        event_schema_version: int = 1,
        occurred_at: datetime | None = None,
        trace_id: str | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
        actor_id: UUID | None = None,
        actor_role: str | None = None,
        reason_code: str | None = None,
        idempotency_key: str | None = None,
        aggregate_type: str | None = None,
        aggregate_id: str | None = None,
        aggregate_version: int | None = None,
    ) -> CanonicalEventEnvelopeV1:
        if event_type is None or not str(event_type).strip():
            raise EnvelopeConstructionError("event_type is required")
        if event_kind is None or not str(event_kind).strip():
            raise EnvelopeConstructionError("event_kind is required")
        if producer is None or not str(producer).strip():
            raise EnvelopeConstructionError("producer is required")
        if data is None:
            raise EnvelopeConstructionError("data is required")

        resolved_id = event_id or uuid.uuid4()
        resolved_time = occurred_at or datetime.now(timezone.utc)
        resolved_trace = (trace_id or "").strip() or _new_trace_id()
        resolved_correlation = (correlation_id or "").strip() or resolved_trace
        if idempotency_key is None or not str(idempotency_key).strip():
            resolved_idem = compute_durable_idempotency_key(
                project_id, str(event_type), dict(data)
            )
        else:
            resolved_idem = str(idempotency_key)

        return cls(
            envelope_version=ENVELOPE_VERSION_V1,
            event_id=resolved_id,
            event_type=str(event_type),
            event_schema_version=event_schema_version,
            event_kind=str(event_kind),
            occurred_at=resolved_time,
            project_id=project_id,
            year=year,
            data=dict(data),
            producer=str(producer),
            trace_id=resolved_trace,
            correlation_id=resolved_correlation,
            causation_id=causation_id,
            actor_id=actor_id,
            actor_role=actor_role,
            reason_code=reason_code,
            idempotency_key=resolved_idem,
            aggregate_type=aggregate_type,
            aggregate_id=str(aggregate_id) if aggregate_id is not None else None,
            aggregate_version=aggregate_version,
        )

    def serialize(self) -> dict[str, Any]:
        """JSON 形态序列化；data 内敏感键已脱敏。"""
        dumped = self.model_dump(mode="json")
        dumped["data"] = redact_secrets(dumped.get("data") or {})
        return dumped
