"""合并附注映射规则复用与标准科目参考下推 ORM（对应迁移 V200）。

spec: consol-note-mapping-reuse-and-reference-push Phase 1 Task 2

4 个 ORM 类：
* :class:`ConsolNoteMappingRuleTemplate`     — 映射规则模板库（不绑 project_id）
* :class:`ConsolNoteStructureLock`           — 结构锁
* :class:`ConsolNoteStructureLockEntity`     — 结构锁子企业关联
* :class:`ConsolNoteValueConfirmation`       — 值确认
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 映射规则模板库
# ═══════════════════════════════════════════════════════════════════════════════


class ConsolNoteMappingRuleTemplate(Base):
    """映射规则模板——从项目级映射规则提升而来，不绑定 project_id，可复用。

    mappings JSONB 格式与 ``ConsolNoteMappingRule.mappings`` 完全一致：
    ``[{source_label, source_row_key, target_row_id, mapping_action, ignore_reason?}]``
    """

    __tablename__ = "consol_note_mapping_rule_template"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    template_type: Mapped[str] = mapped_column(String(20), nullable=False)
    section_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_structure_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    version_number: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=1, server_default=text("1")
    )
    mappings: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'")
    )
    account_code_hints: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=dict, server_default=text("'{}'")
    )
    # 溯源
    source_project_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    source_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    promoted_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    promoted_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # 生命周期
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "template_type IN ('soe', 'listed')",
            name="ck_cnmrt_template_type",
        ),
        CheckConstraint(
            "length(source_structure_hash) = 64",
            name="ck_cnmrt_hash_length",
        ),
        CheckConstraint(
            "version_number > 0",
            name="ck_cnmrt_version_positive",
        ),
        Index(
            "ux_cnmrt_active_rule",
            "template_type", "section_id", "source_structure_hash", "version_number",
            unique=True,
            postgresql_where=text("is_active = true"),
            sqlite_where=text("is_active = 1"),
        ),
        Index(
            "idx_cnmrt_section",
            "template_type", "section_id",
            postgresql_where=text("is_active = true"),
            sqlite_where=text("is_active = 1"),
        ),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 2. 结构锁
# ═══════════════════════════════════════════════════════════════════════════════


class ConsolNoteStructureLock(Base):
    """合并组对子企业附注章节行结构的锁定——禁止增删行，不禁改值。"""

    __tablename__ = "consol_note_structure_lock"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    consol_project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_id: Mapped[str] = mapped_column(String(64), nullable=False)
    locked_version_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("consol_note_detail_template_version.id", ondelete="RESTRICT"),
        nullable=False,
    )
    lock_scope: Mapped[str] = mapped_column(
        String(20), nullable=False, default="rows_only", server_default=text("'rows_only'")
    )
    locked_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    locked_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=text("true")
    )

    __table_args__ = (
        CheckConstraint(
            "lock_scope IN ('rows_only', 'full')",
            name="ck_cnsl_scope",
        ),
        Index(
            "ux_cnsl_project_section",
            "consol_project_id", "section_id",
            unique=True,
            postgresql_where=text("is_active = true"),
            sqlite_where=text("is_active = 1"),
        ),
    )


class ConsolNoteStructureLockEntity(Base):
    """结构锁子企业关联——激活锁时从合并树 data_leaves 展开写入。

    子企业保存时只需 ``SELECT EXISTS(...) FROM consol_note_structure_lock_entity``
    即可判定是否被锁，不需要每次重建合并树。
    """

    __tablename__ = "consol_note_structure_lock_entity"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    lock_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("consol_note_structure_lock.id", ondelete="CASCADE"),
        nullable=False,
    )
    entity_project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    entity_node_key: Mapped[str] = mapped_column(String(128), nullable=False)

    __table_args__ = (
        Index(
            "ux_cnsle_lock_entity",
            "lock_id", "entity_project_id",
            unique=True,
        ),
        Index("idx_cnsle_entity_project", "entity_project_id"),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 值确认
# ═══════════════════════════════════════════════════════════════════════════════

#: 确认状态
VALUE_CONFIRMATION_STATUSES: tuple[str, ...] = ("confirmed", "outdated")


class ConsolNoteValueConfirmation(Base):
    """值确认——记录某企业某章节的数据定稿快照。

    ``entity_node_key='_self'`` 表示本项目自身（单体确认场景）。
    用 NOT NULL + 固定值代替 NULL 以保证唯一索引生效（PG 对 NULL 不去重）。
    """

    __tablename__ = "consol_note_value_confirmation"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_id: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_node_key: Mapped[str] = mapped_column(
        String(128), nullable=False, default="_self", server_default=text("'_self'")
    )
    confirmed_value_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    confirmed_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="confirmed", server_default=text("'confirmed'")
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('confirmed', 'outdated')",
            name="ck_cnvc_status",
        ),
        CheckConstraint(
            "length(confirmed_value_hash) = 64",
            name="ck_cnvc_hash_length",
        ),
        Index(
            "ux_cnvc_project_section_entity",
            "project_id", "section_id", "entity_node_key",
            unique=True,
        ),
        Index("idx_cnvc_project_status", "project_id", "status"),
    )
