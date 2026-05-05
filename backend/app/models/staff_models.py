"""人员库 + 团队委派 + 工时管理 ORM 模型

Phase 9 Task 1.1: staff_members, project_assignments, work_hours
"""

import enum
import uuid
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin


# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------


class StaffTitle(str, enum.Enum):
    """人员职级"""
    partner = "合伙人"
    director = "总监"
    senior_manager = "高级经理"
    manager = "经理"
    senior_auditor = "高级审计员"
    auditor = "审计员"
    intern = "实习生"


class AssignmentRole(str, enum.Enum):
    """委派角色

    R1 一次性预留 ``eqcr``（EQCR 独立复核合伙人）以供 R5 使用，
    避免后续轮次再做枚举迁移。
    """
    signing_partner = "signing_partner"
    manager = "manager"
    auditor = "auditor"
    qc = "qc"
    eqcr = "eqcr"  # 预留 R5，本轮仅模型层承载


class WorkHourStatus(str, enum.Enum):
    """工时状态"""
    draft = "draft"
    confirmed = "confirmed"
    approved = "approved"


# ---------------------------------------------------------------------------
# StaffMember 模型
# ---------------------------------------------------------------------------


class StaffMember(Base, SoftDeleteMixin, TimestampMixin):
    """全局人员库"""

    __tablename__ = "staff_members"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    employee_no: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title: Mapped[str | None] = mapped_column(String(50), nullable=True)
    partner_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    partner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("staff_members.id"), nullable=True
    )
    specialty: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    join_date: Mapped[date | None] = mapped_column(nullable=True)
    resume_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    source: Mapped[str] = mapped_column(String(20), server_default=text("'custom'"), nullable=False)  # seed / custom

    __table_args__ = (
        Index("idx_staff_department", "department", postgresql_where=text("is_deleted = false")),
        Index("idx_staff_partner", "partner_id", postgresql_where=text("is_deleted = false")),
    )


# ---------------------------------------------------------------------------
# ProjectAssignment 模型
# ---------------------------------------------------------------------------


class ProjectAssignment(Base, SoftDeleteMixin, TimestampMixin):
    """项目团队委派"""

    __tablename__ = "project_assignments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    staff_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("staff_members.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    assigned_cycles: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(nullable=True)
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    __table_args__ = (
        Index(
            "idx_assignment_project_staff",
            "project_id", "staff_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
        Index("idx_assignment_staff", "staff_id", postgresql_where=text("is_deleted = false")),
    )


# ---------------------------------------------------------------------------
# WorkHour 模型
# ---------------------------------------------------------------------------


class WorkHour(Base, SoftDeleteMixin, TimestampMixin):
    """工时记录"""

    __tablename__ = "work_hours"
    __table_args__ = (
        Index("idx_workhour_staff_date", "staff_id", "work_date"),
        Index("idx_workhour_project", "project_id",
              postgresql_where=text("is_deleted = false")),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    staff_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("staff_members.id"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    work_date: Mapped[date] = mapped_column(nullable=False)
    hours: Mapped[Decimal] = mapped_column(nullable=False)
    start_time: Mapped[time | None] = mapped_column(nullable=True)
    end_time: Mapped[time | None] = mapped_column(nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    ai_suggested: Mapped[bool] = mapped_column(default=False)
