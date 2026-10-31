"""公式全局设置 / 本项目适配 / 公式模板 ORM（迁移 V199，spec formula-global-settings-sync）。

* :class:`FormulaSetting` —— 非报表域的全局层、本项目层，以及全部域的模板层。
* :class:`FormulaSyncItem` —— 待项目确认的同步事项（冲突 / 管理员暂缓）。
* :class:`FormulaPublish` —— 发布记录（全局发布 / 模板发布 / 应用到项目 / 全局候选）。
* :class:`FormulaTemplate` / :class:`FormulaTemplateVersion` / :class:`FormulaTemplateSubscription`
  —— 可共享的公式模板、每次发布的冻结快照、项目订阅。

报表域两层仍在 ``report_config``（准则行 = 全局、``project:{id}`` 行 = 本项目适配）。
所有主键 ORM 端 ``default=uuid.uuid4``（DDL 无默认值，裸插入必须自带 id）。
"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

LAYERS: tuple[str, ...] = ("global", "project", "template")
SYNC_REASONS: tuple[str, ...] = ("conflict", "deferred")
SYNC_STATUSES: tuple[str, ...] = ("pending", "resolved", "superseded")
SYNC_RESOLUTIONS: tuple[str, ...] = ("adopt", "keep", "custom")
PUBLISH_TARGETS: tuple[str, ...] = ("global", "template", "projects")
PUBLISH_STATUSES: tuple[str, ...] = ("published", "pending", "rejected")
SHARE_SCOPES: tuple[str, ...] = ("personal", "team", "group", "firm")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{column} IN ({quoted})"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _now_col() -> Mapped[datetime]:
    return mapped_column(sa.DateTime(timezone=True), nullable=False, server_default=func.now())


class ProjectBaselineColumns:
    """项目层行所依据的上游（全局或模板）定义快照与版本 —— 三方比对判断「本项目改过没有」（V199）。

    ``report_config`` 项目行与 ``wp_formula`` 自定义行共用这组列（declarative mixin，各表各自一份）；
    准则行 / 其他来源的行这些列为空。``pinned`` = 暂缓 / 冻结而固定在旧上游定义。
    """

    base_version: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    base_definition: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    pinned: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False, server_default=text("false"))
    base_origin: Mapped[str | None] = mapped_column(String(16), nullable=True)
    base_template_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)


class FormulaTemplate(Base):
    """可共享的公式模板（名称 / 共享范围 / 适用准则 / 当前版本）。"""

    __tablename__ = "formula_template"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    share_scope: Mapped[str] = mapped_column(String(16), nullable=False, default="personal",
                                             server_default=text("'personal'"))
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("users.id"),
                                                            nullable=True)
    owner_project_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    applicable_scope: Mapped[str] = mapped_column(String(40), nullable=False, default="",
                                                  server_default=text("''"))
    domains: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'"))
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1, server_default=text("1"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active",
                                        server_default=text("'active'"))
    is_deleted: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False,
                                             server_default=text("false"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = _now_col()
    updated_at: Mapped[datetime] = _now_col()

    __table_args__ = (
        CheckConstraint(_in_list("share_scope", SHARE_SCOPES), name="ck_formula_template_share_scope"),
        CheckConstraint(_in_list("status", ("active", "archived")), name="ck_formula_template_status"),
        CheckConstraint("share_scope NOT IN ('team', 'group') OR owner_project_id IS NOT NULL",
                        name="ck_formula_template_owner_project"),
        Index("ix_formula_template_owner", "owner_user_id"),
        Index("ix_formula_template_project", "owner_project_id"),
    )


class FormulaTemplateVersion(Base):
    """模板每次发布的冻结快照（三方比对、回看、暂缓订阅者读取）。"""

    __tablename__ = "formula_template_version"

    id: Mapped[uuid.UUID] = _uuid_pk()
    template_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("formula_template.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    #: ``{domain: {slot_key: definition}}``
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'"))
    change_set: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'"))
    note: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    published_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    published_at: Mapped[datetime] = _now_col()

    __table_args__ = (UniqueConstraint("template_id", "version", name="uq_formula_template_version"),)


class FormulaSetting(Base):
    """统一公式设置行：``layer`` = global（全局）/ project（本项目适配）/ template（模板）。"""

    __tablename__ = "formula_setting"

    id: Mapped[uuid.UUID] = _uuid_pk()
    domain: Mapped[str] = mapped_column(String(32), nullable=False)
    layer: Mapped[str] = mapped_column(String(16), nullable=False)
    #: 全局层：准则码 / 模板类型，``*`` = 通用；项目层与模板层为空串。
    scope: Mapped[str] = mapped_column(String(40), nullable=False, default="", server_default=text("''"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("formula_template.id", ondelete="CASCADE"), nullable=True
    )
    slot_key: Mapped[str] = mapped_column(sa.Text, nullable=False)
    slot_label: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    definition: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'"))
    definition_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1, server_default=text("1"))
    base_version: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    base_definition: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    pinned: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False, server_default=text("false"))
    base_origin: Mapped[str | None] = mapped_column(String(16), nullable=True)
    base_template_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False,
                                             server_default=text("false"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = _now_col()
    updated_at: Mapped[datetime] = _now_col()

    __table_args__ = (
        CheckConstraint(_in_list("layer", LAYERS), name="ck_formula_setting_layer"),
        CheckConstraint(
            "(layer = 'global' AND project_id IS NULL AND template_id IS NULL)"
            " OR (layer = 'project' AND project_id IS NOT NULL AND template_id IS NULL)"
            " OR (layer = 'template' AND template_id IS NOT NULL AND project_id IS NULL)",
            name="ck_formula_setting_owner",
        ),
        Index("uq_formula_setting_global", "domain", "scope", "slot_key", unique=True,
              postgresql_where=text("layer = 'global' AND is_deleted = false"),
              sqlite_where=text("layer = 'global' AND is_deleted = 0")),
        Index("uq_formula_setting_project", "domain", "project_id", "slot_key", unique=True,
              postgresql_where=text("layer = 'project' AND is_deleted = false"),
              sqlite_where=text("layer = 'project' AND is_deleted = 0")),
        Index("uq_formula_setting_template", "domain", "template_id", "slot_key", unique=True,
              postgresql_where=text("layer = 'template' AND is_deleted = false"),
              sqlite_where=text("layer = 'template' AND is_deleted = 0")),
        Index("ix_formula_setting_project", "project_id", "domain"),
    )


class FormulaSyncItem(Base):
    """待项目确认的同步事项。同一项目同一公式位只保留一条 pending（后续发布更新它）。"""

    __tablename__ = "formula_sync_item"

    id: Mapped[uuid.UUID] = _uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    domain: Mapped[str] = mapped_column(String(32), nullable=False)
    slot_key: Mapped[str] = mapped_column(sa.Text, nullable=False)
    slot_label: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    reason: Mapped[str] = mapped_column(String(16), nullable=False)
    upstream_origin: Mapped[str] = mapped_column(String(16), nullable=False, default="global",
                                                 server_default=text("'global'"))
    upstream_template_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    base_definition: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    #: 新上游定义；``None`` = 上游已删除该公式位。
    upstream_definition: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    local_definition: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    upstream_version: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    #: 修订号（V228，ADR-FHIC-11）：新建为 1，每次被覆盖原子 +1；处理待确认以它为唯一 CAS 依据。
    revision: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1, server_default=text("1"))
    publish_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending",
                                        server_default=text("'pending'"))
    resolution: Mapped[str | None] = mapped_column(String(16), nullable=True)
    resolved_definition: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _now_col()
    updated_at: Mapped[datetime] = _now_col()

    __table_args__ = (
        CheckConstraint(_in_list("reason", SYNC_REASONS), name="ck_formula_sync_item_reason"),
        CheckConstraint(_in_list("status", SYNC_STATUSES), name="ck_formula_sync_item_status"),
        CheckConstraint("resolution IS NULL OR " + _in_list("resolution", SYNC_RESOLUTIONS),
                        name="ck_formula_sync_item_resolution"),
        Index("uq_formula_sync_item_pending", "project_id", "domain", "slot_key", unique=True,
              postgresql_where=text("status = 'pending'"), sqlite_where=text("status = 'pending'")),
    )


class FormulaPublish(Base):
    """发布记录。``status=pending`` 承载非 admin 提交的全局候选（admin 审核后执行）。"""

    __tablename__ = "formula_publish"

    id: Mapped[uuid.UUID] = _uuid_pk()
    domain: Mapped[str] = mapped_column(String(32), nullable=False)
    scope: Mapped[str] = mapped_column(String(40), nullable=False, default="", server_default=text("''"))
    target: Mapped[str] = mapped_column(String(16), nullable=False, default="global",
                                        server_default=text("'global'"))
    template_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    source: Mapped[str] = mapped_column(String(24), nullable=False)
    source_project_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="published",
                                        server_default=text("'published'"))
    change_set: Mapped[list] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'"))
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'"))
    note: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    published_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    published_at: Mapped[datetime] = _now_col()
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(_in_list("target", PUBLISH_TARGETS), name="ck_formula_publish_target"),
        CheckConstraint(_in_list("status", PUBLISH_STATUSES), name="ck_formula_publish_status"),
        Index("uq_formula_publish_request", "request_id", unique=True,
              postgresql_where=text("request_id IS NOT NULL"), sqlite_where=text("request_id IS NOT NULL")),
    )


class FormulaTemplateSubscription(Base):
    """项目订阅模板（每个项目每个域最多一个有效订阅）。"""

    __tablename__ = "formula_template_subscription"

    id: Mapped[uuid.UUID] = _uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    domain: Mapped[str] = mapped_column(String(32), nullable=False)
    template_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), ForeignKey("formula_template.id"),
                                                   nullable=False)
    template_version: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    #: 暂缓：固定在 ``template_version`` 的快照，不跟随模板新版本。
    pinned: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False, server_default=text("false"))
    is_active: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=True, server_default=text("true"))
    subscribed_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    subscribed_at: Mapped[datetime] = _now_col()
    unsubscribed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("uq_formula_template_subscription_active", "project_id", "domain", unique=True,
              postgresql_where=text("is_active = true"), sqlite_where=text("is_active = 1")),
    )
