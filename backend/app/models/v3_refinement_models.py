"""V3 收官增强 ORM 模型

Tables: ai_content_log, cross_module_conflicts, time_machine_snapshots
对应迁移: V017__v3_refinement_tables.sql
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class AiContentLog(Base, TimestampMixin):
    """AI 生成内容溯源日志 — 字段级追踪 AI 输出及人工确认状态"""

    __tablename__ = "ai_content_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    wp_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    target_cell: Mapped[str | None] = mapped_column(String(255), nullable=True)
    prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    generated_content: Mapped[str] = mapped_column(Text, nullable=False)
    revised_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirm_action: Mapped[str] = mapped_column(
        String(20), server_default=text("'pending'"), nullable=False
    )
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), nullable=False
    )


class CrossModuleConflict(Base, TimestampMixin):
    """跨模块冲突调解记录 — 上游数据变更与手工覆盖的冲突追踪"""

    __tablename__ = "cross_module_conflicts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    source_module: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    target_module: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    target_field: Mapped[str] = mapped_column(String(100), nullable=False)
    upstream_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    manual_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(20), nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), server_default=text("'pending'"), nullable=False
    )


class TimeMachineSnapshot(Base):
    """时光机增量快照 — RFC 6902 JSON Patch 反向 diff"""

    __tablename__ = "time_machine_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    instance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    instance_type: Mapped[str] = mapped_column(String(50), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    diff_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    parent_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("time_machine_snapshots.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), nullable=False
    )
    # DB 扩展列
    diff_patch: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    module: Mapped[str] = mapped_column(String(50), nullable=False, server_default=text("''"))
    # NOTE: 不写 `'{}'::jsonb`（PG 字面 cast）—— SQLite 测试 dialect 不识别 `::`
    # 会导致建表 DDL 报 "unrecognized token"。`'{}'` 在 PG/SQLite 双方言下
    # 都能解析为合法空 JSON 对象（同 report_models / custom_query_models 约定）。
    snapshot_data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
