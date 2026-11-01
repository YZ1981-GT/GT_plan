"""合并持久 operation 的输入版本与 API 契约。"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

OperationType = Literal["refresh_all", "push"]
OperationStatus = Literal[
    "queued", "running", "succeeded", "partial", "failed", "stale", "cancelled",
]


class ConsolVersionVector(BaseModel):
    """影响一次合并输出的不可变输入摘要。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    tree_revision: int | None = None
    tree_fingerprint: str
    recorded_tree_fingerprint: str | None = None
    worksheet_versions: dict[str, int] = Field(default_factory=dict)
    tb_digest: str
    elimination_digest: str
    formula_digest: str
    note_mapping_digest: str
    template_digest: str
    digest: str


class ConsolOperationCreate(BaseModel):
    operation_type: OperationType = "refresh_all"
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)
    trigger_source: str = Field(default="manual", min_length=1, max_length=40)
    requested_actions: tuple[str, ...] = ()

    @field_validator("trigger_source")
    @classmethod
    def normalize_trigger(cls, value: str) -> str:
        return value.strip()

    @field_validator("requested_actions")
    @classmethod
    def normalize_actions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted({item.strip() for item in value if item.strip()}))


class ConsolOperationResponse(BaseModel):
    id: str
    project_id: str
    year: int
    operation_type: OperationType
    idempotency_key: str
    request_hash: str
    status: OperationStatus
    revision: int
    attempt: int
    context: dict[str, Any]
    version_vector: dict[str, Any]
    steps: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    result_refs: dict[str, Any]
    metrics: dict[str, Any]
    queued_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    updated_at: str | None = None
