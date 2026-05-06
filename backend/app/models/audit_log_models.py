"""审计日志 ORM 模型 — 不可变追加式哈希链

Refinement Round 1 — 需求 9：审计日志真实落库 + 不可篡改。

设计要点：
- 无 updated_at / 无 is_deleted（不可改不可删）
- entry_hash = sha256(ts + user_id + action_type + object_id + payload_json + prev_hash)
- prev_hash 链接到前一条 entry_hash，形成哈希链
"""

import uuid
from datetime import datetime

from sqlalchemy import Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuditLogEntry(Base):
    """审计日志条目 — 不可变追加式

    每条记录通过 prev_hash → entry_hash 形成哈希链，
    任何篡改都会导致链断裂可被 verify-chain 端点检出。

    Refinement Round 1 — 需求 9。
    """

    __tablename__ = "audit_log_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ts: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    ua: Mapped[str | None] = mapped_column(Text, nullable=True)
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    # 注意：无 updated_at / 无 is_deleted — 不可改不可删

    __table_args__ = (
        Index("idx_audit_log_entries_ts", "ts"),
        Index("idx_audit_log_entries_user_id", "user_id"),
        Index("idx_audit_log_entries_action_type", "action_type"),
        Index("idx_audit_log_entries_object", "object_type", "object_id"),
        Index("idx_audit_log_entries_entry_hash", "entry_hash", unique=True),
    )
