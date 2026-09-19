"""审计程序裁剪与委派 ORM 模型

Phase 9 Task 9.12: procedure_instances + procedure_trim_schemes
"""

import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import CHAR, ForeignKey, Index, Integer, String, Text, func, text
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
    # V146（procedure-trimming-and-delegation-intelligence Task 11）：裁剪建议态与理由码。
    #
    # 结构：{reason_code, rejected, rejected_by, rejected_at, evidence}
    #   reason_code —— 与 `skip_reason` 并列写在同一事务（R8.8：理由码与状态同一次落库）
    #   rejected    —— 审计师驳回系统建议；驳回后不再被重新建议（R6.4）
    #   evidence    —— 本次判定实际用到的判据数值与来源（R3.10 复核追溯）
    #
    # 🔴 为什么不落 `procedure_trim_schemes.trim_data`：后者实测是**带日期的多份历史
    #    方案快照**（`裁剪方案-D-20260706` 等），键空间是 procedure_instance UUID；
    #    把「当前建议态」塞进历史快照语义错位。建议态跟着**程序实例**走。
    suggestion_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

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


# ---------------------------------------------------------------------------
# V105 expand 模型（procedure-delegation-notification / Task 2）
#
# 分两层真源：
#   - ProcedureRowDefinition：模板级程序行定义（跨项目稳定身份 definition_key）
#   - ProcedureRowTask：项目级程序行任务（适用性/委派/执行/一级复核唯一真源）
# 另有追加式 ProcedureRowTaskHistory 与一次性 ProcedureOperationPreview。
# 索引（active partial unique / covering / claim-order）由 V105 迁移拥有，
# ORM 不重复声明（避免 SQLite create_all 与 PG 方言差异），由契约测试对 DB 精校。
# ---------------------------------------------------------------------------


class ProcedureRowDefinition(Base, TimestampMixin):
    """模板级程序行定义真源（跨项目稳定）。"""

    __tablename__ = "procedure_row_definitions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    definition_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    template_code: Mapped[str] = mapped_column(String(80), nullable=False)
    template_revision_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    sheet_key: Mapped[str] = mapped_column(String(160), nullable=False)
    source_locator: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))
    program_no: Mapped[str | None] = mapped_column(String(80), nullable=True)
    procedure_text: Mapped[str] = mapped_column(Text, nullable=False)
    ref_snapshot: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    legacy_aliases: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    normalized_content: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))


class ProcedureRowTask(Base, SoftDeleteMixin, TimestampMixin):
    """项目级程序行任务真源（先委派后生成底稿）。"""

    __tablename__ = "procedure_row_tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    wp_index_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("wp_index.id"), nullable=False)
    wp_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("working_paper.id"), nullable=True)
    definition_key: Mapped[str] = mapped_column(
        String(200), ForeignKey("procedure_row_definitions.definition_key"), nullable=False
    )
    sheet_key: Mapped[str] = mapped_column(String(160), nullable=False)
    # 审计/展示快照
    wp_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    sheet_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    program_no: Mapped[str | None] = mapped_column(String(80), nullable=True)
    procedure_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ref_snapshot: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    definition_revision_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    audit_cycle_snapshot: Mapped[str] = mapped_column(String(40), nullable=False)
    # 适用性与独立状态机
    applicability_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'execute'"))
    workflow_status: Mapped[str] = mapped_column(String(30), nullable=False, server_default=text("'unassigned'"))
    # 参与者
    assignee_staff_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("staff_members.id"), nullable=True)
    reviewer_staff_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("staff_members.id"), nullable=True)
    # 版本与并发
    assignment_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    # SLA 时间戳
    due_at: Mapped[datetime | None] = mapped_column(nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # 提交材料
    execution_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_snapshot: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    # 迁移证据
    migration_confidence: Mapped[str | None] = mapped_column(String(20), nullable=True)
    migration_detail: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))


class ProcedureRowTaskHistory(Base):
    """程序行任务追加式历史（不可覆盖）。"""

    __tablename__ = "procedure_row_task_history"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("procedure_row_tasks.id"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    old_assignee_staff_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("staff_members.id"), nullable=True)
    new_assignee_staff_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("staff_members.id"), nullable=True)
    old_reviewer_staff_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("staff_members.id"), nullable=True)
    new_reviewer_staff_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("staff_members.id"), nullable=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    assignment_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    definition_revision_hash: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    audit_cycle_snapshot: Mapped[str | None] = mapped_column(String(40), nullable=True)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


# ---------------------------------------------------------------------------
# V109 cutover-hardening 模型（procedure-delegation-notification / Task 2）
#
# procedure_template_revisions: 运行时 current-revision 唯一选择器。
# procedure_row_definition_revisions: revision 成员关系。
# 索引（identity unique / partial unique WHERE is_current=true / resolve）由 V109 迁移拥有。
# ---------------------------------------------------------------------------


class ProcedureTemplateRevision(Base):
    """Current-revision registry；每个 template_code 最多一个 active current。"""

    __tablename__ = "procedure_template_revisions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    template_code: Mapped[str] = mapped_column(String(80), nullable=False)
    revision_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default=text("'registered'"))
    is_current: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=text("false"))
    supersedes_revision_hash: Mapped[str | None] = mapped_column(CHAR(64), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(nullable=True)
    activated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reconcile_detail: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class ProcedureRowDefinitionRevision(Base):
    """Revision membership: 哪些 definition_key 属于 (template_code, revision_hash)。"""

    __tablename__ = "procedure_row_definition_revisions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    template_code: Mapped[str] = mapped_column(String(80), nullable=False)
    revision_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    sheet_key: Mapped[str] = mapped_column(String(160), nullable=False)
    definition_key: Mapped[str] = mapped_column(
        String(200), ForeignKey("procedure_row_definitions.definition_key"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class ProcedureOperationPreview(Base):
    """敏感操作 server-side 一次性预览凭证（裁剪/委派/转派）。"""

    __tablename__ = "procedure_operation_previews"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    operation: Mapped[str] = mapped_column(String(40), nullable=False)
    request_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    request_payload_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))
    target_versions: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))
    membership_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))
    membership_snapshot_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    scheme_revision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    consumed_request_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
