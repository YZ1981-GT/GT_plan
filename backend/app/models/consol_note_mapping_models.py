"""合并附注明细模板与多企业行映射规则 ORM（对应迁移 V186）。

spec: consol-note-detail-template-and-mapping Phase 1 Task 2

5 个 ORM 类：
* :class:`ConsolNoteDetailTemplate`        — 合并附注明细模板
* :class:`ConsolNoteDetailTemplateVersion`  — 模板不可变版本
* :class:`ConsolNoteTemplateBinding`        — 项目绑定到版本
* :class:`ConsolNoteMappingRule`            — 来源行→目标行转换规则
* :class:`ConsolNoteMappingBinding`         — 企业级规则绑定与 stale 状态

取值集合与 V186 的 CHECK 同源。
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

#: 模板可见范围
TEMPLATE_VISIBILITY: tuple[str, ...] = ("draft", "project", "firm")
#: 模板类型
TEMPLATE_TYPES: tuple[str, ...] = ("soe", "listed")
#: 映射绑定状态
MAPPING_BINDING_STATUSES: tuple[str, ...] = ("confirmed", "stale", "excluded")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


# ─── 1. 合并附注明细模板 ────────────────────────────────────────────────────


class ConsolNoteDetailTemplate(Base):
    """合并附注明细模板——按 template_type + section_id 组织。"""

    __tablename__ = "consol_note_detail_template"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    template_type: Mapped[str] = mapped_column(String(20), nullable=False)
    section_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(
        String(200), nullable=False, default="", server_default=text("''")
    )
    visibility: Mapped[str] = mapped_column(
        String(20), nullable=False, default="project", server_default=text("'project'")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    is_deleted: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=text("false")
    )

    __table_args__ = (
        CheckConstraint(
            _in_list("template_type", TEMPLATE_TYPES),
            name="ck_cndt_template_type",
        ),
        CheckConstraint(
            _in_list("visibility", TEMPLATE_VISIBILITY),
            name="ck_cndt_visibility",
        ),
        Index(
            "ux_cndt_active",
            "template_type", "section_id", "created_by",
            unique=True,
            postgresql_where=text("is_deleted = false"),
            sqlite_where=text("is_deleted = 0"),
        ),
    )


# ─── 2. 模板不可变版本 ──────────────────────────────────────────────────────


class ConsolNoteDetailTemplateVersion(Base):
    """模板不可变版本。rows JSONB 格式：
    ``[{target_row_id, canonical_name, aliases, sort_order, row_type}]``
    """

    __tablename__ = "consol_note_detail_template_version"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("consol_note_detail_template.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    rows: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'")
    )
    change_note: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("version_number > 0", name="ck_cndtv_version_positive"),
        Index(
            "ux_cndtv_template_version",
            "template_id", "version_number",
            unique=True,
        ),
    )


# ─── 3. 项目绑定到版本 ──────────────────────────────────────────────────────


class ConsolNoteTemplateBinding(Base):
    """项目绑定到某一模板版本——一个项目一个章节只绑一个版本。"""

    __tablename__ = "consol_note_template_binding"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_id: Mapped[str] = mapped_column(String(64), nullable=False)
    template_version_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("consol_note_detail_template_version.id", ondelete="RESTRICT"),
        nullable=False,
    )
    bound_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    bound_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index(
            "ux_cntb_project_section",
            "project_id", "section_id",
            unique=True,
        ),
    )


# ─── 4. 来源行→目标行转换规则 ──────────────────────────────────────────────


class ConsolNoteMappingRule(Base):
    """映射规则。mappings JSONB 格式：
    ``[{source_label, source_row_key, target_row_id, mapping_action, ignore_reason?}]``

    mapping_action ∈ {map, map_merge, create, ignore}
    """

    __tablename__ = "consol_note_mapping_rule"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_id: Mapped[str] = mapped_column(String(64), nullable=False)
    template_version_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("consol_note_detail_template_version.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_structure_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    version_number: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, default=1, server_default=text("1")
    )
    mappings: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'")
    )
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=True, server_default=text("true")
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # V202 的 promoted_to_template_id（规则提升为模板）已随规则模板库退役（V208 删列，spec note-pull-followup-closure R16）

    __table_args__ = (
        CheckConstraint("version_number > 0", name="ck_cnmr_version_positive"),
        CheckConstraint(
            "length(source_structure_hash) = 64",
            name="ck_cnmr_hash_length",
        ),
        Index(
            "ux_cnmr_unique_rule",
            "project_id", "section_id", "template_version_id",
            "source_structure_hash", "version_number",
            unique=True,
            postgresql_where=text("is_active = true"),
            sqlite_where=text("is_active = 1"),
        ),
        Index(
            "idx_cnmr_project_section",
            "project_id", "section_id",
            postgresql_where=text("is_active = true"),
            sqlite_where=text("is_active = 1"),
        ),
    )


# ─── 5. 企业级规则绑定 ──────────────────────────────────────────────────────


class ConsolNoteMappingBinding(Base):
    """企业级绑定——记录每家企业确认使用哪条规则，以及绑定时的来源结构指纹。"""

    __tablename__ = "consol_note_mapping_binding"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_id: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_node_key: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False,
        comment="不加 FK：来源企业 project_id 可能不在当前合并项目 projects 表中",
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("consol_note_mapping_rule.id", ondelete="CASCADE"),
        nullable=False,
    )
    bound_source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="confirmed", server_default=text("'confirmed'")
    )
    bound_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            _in_list("status", MAPPING_BINDING_STATUSES),
            name="ck_cnmb_status",
        ),
        CheckConstraint(
            "length(bound_source_hash) = 64",
            name="ck_cnmb_hash_length",
        ),
        Index(
            "ux_cnmb_project_section_entity",
            "project_id", "section_id", "entity_node_key",
            unique=True,
        ),
        Index("idx_cnmb_rule", "rule_id"),
    )
