"""审计程序裁剪与委派 ORM 模型

Phase 9 Task 9.12: procedure_instances + procedure_trim_schemes
"""

import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin


class ProcedureStatus(str, enum.Enum):
    execute = "execute"
    skip = "skip"
    not_applicable = "not_applicable"


class ExecutionStatus(str, enum.Enum):
    not_started = "not_started"
    in_progress = "in_progress"
    completed = "completed"
    reviewed = "reviewed"


class ProcedureInstance(Base, SoftDeleteMixin, TimestampMixin):
    """审计程序实例（裁剪后的程序步骤）"""

    __tablename__ = "procedure_instances"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    audit_cycle: Mapped[str] = mapped_column(String(10), nullable=False)
    procedure_code: Mapped[str] = mapped_column(String(50), nullable=False)
    procedure_name: Mapped[str] = mapped_column(String(500), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("procedure_instances.id"), nullable=True)
    sort_order: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(20), default="execute")
    skip_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_custom: Mapped[bool] = mapped_column(default=False)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("staff_members.id"), nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(nullable=True)
    execution_status: Mapped[str] = mapped_column(String(20), default="not_started")
    wp_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    wp_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    __table_args__ = (
        Index("idx_proc_project_cycle", "project_id", "audit_cycle",
              postgresql_where=text("is_deleted = false")),
    )


class ProcedureTrimScheme(Base, SoftDeleteMixin, TimestampMixin):
    """审计程序裁剪方案"""

    __tablename__ = "procedure_trim_schemes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    audit_cycle: Mapped[str] = mapped_column(String(10), nullable=False)
    scheme_name: Mapped[str] = mapped_column(String(200), nullable=False)
    trim_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
