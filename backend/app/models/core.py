"""5张核心业务表模型：User, Project, ProjectUser, Log, Notification"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Index, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import (
    AuditMixin,
    Base,
    PermissionLevel,
    ProjectStatus,
    ProjectType,
    ProjectUserRole,
    SoftDeleteMixin,
    TimestampMixin,
    UserRole,
)


# ---------------------------------------------------------------------------
# User 模型
# ---------------------------------------------------------------------------


class User(Base, SoftDeleteMixin, TimestampMixin, AuditMixin):
    """系统用户"""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(nullable=False)
    office_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    language: Mapped[str] = mapped_column(String(10), server_default=text("'zh-CN'"), nullable=False)

    __table_args__ = (
        Index("idx_users_active", "is_active", postgresql_where=text("is_deleted = false")),
    )


# ---------------------------------------------------------------------------
# Project 模型
# ---------------------------------------------------------------------------


class Project(Base, SoftDeleteMixin, TimestampMixin, AuditMixin):
    """审计项目"""

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    client_name: Mapped[str] = mapped_column(String(255), nullable=False)
    audit_period_start: Mapped[date | None] = mapped_column(nullable=True)
    audit_period_end: Mapped[date | None] = mapped_column(nullable=True)
    project_type: Mapped[ProjectType | None] = mapped_column(nullable=True)
    materiality_level: Mapped[float | None] = mapped_column(nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(default=ProjectStatus.created)
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    partner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    version: Mapped[int] = mapped_column(default=1)
    wizard_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    accounting_standard_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("accounting_standards.id"), nullable=True
    )
    company_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    short_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    audit_year: Mapped[int | None] = mapped_column(nullable=True, comment="审计年度（物化列，唯一性索引依赖）")
    template_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    report_scope: Mapped[str | None] = mapped_column(String(20), nullable=True)
    parent_company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    parent_company_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ultimate_company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ultimate_company_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    parent_project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    consol_level: Mapped[int] = mapped_column(default=1)
    # 合并类型：subsidiary=母子合并（需抵销）/ branch=母分汇总（直接加总，无抵销）
    consolidation_type: Mapped[str | None] = mapped_column(
        String(20), nullable=True, default=None
    )

    # 合并锁定（Phase 0 — consol-phase0-core-pipeline / C3 三层一致 + F2 锁定闭环）
    consol_lock: Mapped[bool] = mapped_column(
        Boolean, server_default=text("false"), nullable=False
    )
    consol_lock_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    consol_lock_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Round 1 需求 11：归档保留期
    archived_at: Mapped[datetime | None] = mapped_column(nullable=True)
    retention_until: Mapped[datetime | None] = mapped_column(nullable=True)

    # Round 2 需求 9：项目预算
    budget_hours: Mapped[int | None] = mapped_column(nullable=True)
    contract_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 2), nullable=True
    )
    budgeted_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    budgeted_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Batch 3 Fix 4: 风险等级持久化（manager_dashboard 计算后回写）
    risk_level: Mapped[str | None] = mapped_column(String(10), nullable=True, comment="风险等级: high/medium/low")
    risk_level_updated_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # E1 Sprint 2 Task 2.1: 场景驱动裁剪（F1.1 + F1.6）
    scenario: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'normal'"),
        comment="项目场景: normal/ipo/listed/transfer/restructure/fraud_response",
    )
    has_foreign_currency: Mapped[bool] = mapped_column(
        nullable=False,
        server_default=text("false"),
        comment="是否有外币业务（驱动 E1-1 双区显隐 + E1-3 双版本二选一）",
    )
    # V045 扩展列
    prior_year_project_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    migration_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # multi-standard-unification 需求 1.1: 结构化统一准则状态源（单一真理源）
    # {entity_type: "soe"|"listed"|"private", scope: "standalone"|"consolidated",
    #  stage: "normal"|"ipo"|"transfer"|"restructure"|"fraud_response"}
    applicable_standard_v2: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Phase 6 F8: 复核链配置（2-4 级可配置状态机）
    review_config: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=None,
        comment='复核链配置: {"levels":2|3|4,"level_roles":{"L1":"manager","L2":"partner",...}}',
    )

    # Phase 7 F8: 工时预算配置
    budget_config: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        default=None,
        comment='工时预算配置: {"by_cycle":{"D":100,"E":80,...},"by_user":{"user_id":160,...},"total":800}',
    )

    # 软删除标记
    is_deleted: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )

    __table_args__ = (
        Index(
            "idx_projects_status",
            "status",
            postgresql_where=text("is_deleted = false"),
        ),
    )


# ---------------------------------------------------------------------------
# ProjectUser 模型
# ---------------------------------------------------------------------------


class ProjectUser(Base, SoftDeleteMixin, TimestampMixin):
    """项目成员关联"""

    __tablename__ = "project_users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    role: Mapped[ProjectUserRole] = mapped_column(nullable=False)
    permission_level: Mapped[PermissionLevel] = mapped_column(
        default=PermissionLevel.readonly
    )
    scope_cycles: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope_accounts: Mapped[str | None] = mapped_column(Text, nullable=True)
    valid_from: Mapped[date | None] = mapped_column(nullable=True)
    valid_to: Mapped[date | None] = mapped_column(nullable=True)

    __table_args__ = (
        Index(
            "idx_project_users_project_user",
            "project_id",
            "user_id",
            unique=True,
            postgresql_where=text("is_deleted = false"),
        ),
    )


# ---------------------------------------------------------------------------
# Log 模型
# ---------------------------------------------------------------------------


class Log(Base):
    """操作日志"""

    __tablename__ = "logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    object_type: Mapped[str] = mapped_column(String(100), nullable=False)
    object_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    old_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("idx_logs_object", "object_type", "object_id"),
        Index("idx_logs_user_time", "user_id", text("created_at DESC")),
    )


# ---------------------------------------------------------------------------
# Notification 模型
# ---------------------------------------------------------------------------


class Notification(Base):
    """系统通知"""

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    message_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_object_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    related_object_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    is_read: Mapped[bool] = mapped_column(default=False)
    read_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("idx_notifications_recipient_read", "recipient_id", "is_read"),
    )
