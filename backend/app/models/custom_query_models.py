"""自定义查询模板模型 [advanced-query-enhancements-p1p2 Task 8]

支持用户保存自定义查询配置（数据源/筛选条件/字段选择/选区/分页/排序），
并按"私有/团队/公开"控制可见性。

config JSONB 完整 schema（Req 15 AC3）：
  {project_id, year, source, sheet_name, cell_range, filter_text,
   conditions[], selected_columns[], available_columns[],
   page_size, sort_field, sort_order}

Validates: Requirements 15.1-15.5 (advanced-query-enhancements-p1p2)
"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CustomQueryTemplate(Base):
    """自定义查询模板。

    - scope='private'：仅创建者可见
    - scope='team'：团队可见
    - scope='public'：全员共享
    - scope='global'：全员共享（legacy alias）
    - config 含完整查询参数（含 cell_range / sheet_name / page_size / sort）
    """

    __tablename__ = "custom_query_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    data_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # NOTE: 不写 `'{}'::jsonb`（PG 字面 cast）—— SQLite 测试 dialect 不识别 `::`
    # JSON 字面量在 PG/SQLite 双方言下都能解析为合法 JSON 对象
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=sa.text("'{}'"))
    scope: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=sa.text("'private'")
    )
    # shared_project_ids: 显式分享的项目 id 列表（scope='personal' + 分享场景）
    # 与 V101 逐列对齐：UUID[] NOT NULL DEFAULT '{}'
    # NOTE: 数组列需要两处适配，缺任一在 SQLite 测试方言下都会炸：
    #   ① 方言变体 —— SQLite 无 ARRAY 类型，绑定 list 参数直接
    #      `ProgrammingError: type 'list' is not supported`，故退化为 JSON；
    #   ② Python 侧 `default=list` —— PG 数组字面量 `'{}'` 作为 server_default
    #      在 SQLite 上被当普通字符串存入，读回时 ARRAY 的 item processor 会对
    #      "{}" 逐字符调 `UUID()` → `badly formed hexadecimal UUID string`。
    #      显式 default 使 INSERT 自带空列表，两种方言行为一致。
    # PG 侧语义完全不变（仍是 UUID[] / TEXT[] + GIN 索引）。
    shared_project_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(PG_UUID(as_uuid=True)).with_variant(sa.JSON(), "sqlite"),
        nullable=False,
        default=list,
        server_default=sa.text("'{}'"),
    )
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(sa.Text).with_variant(sa.JSON(), "sqlite"),
        nullable=False,
        default=list,
        server_default=sa.text("'{}'"),
    )
    use_count: Mapped[int] = mapped_column(
        sa.Integer, nullable=False, server_default=sa.text("0")
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )
    # creator_id is the canonical FK; created_by kept for backward compat
    creator_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
        nullable=False,
    )

    @property
    def owner_id(self) -> uuid.UUID:
        """Canonical owner: prefer creator_id, fallback to created_by."""
        return self.creator_id or self.created_by

    __table_args__ = (
        sa.Index("idx_custom_query_templates_scope", "scope", "updated_at"),
        sa.Index("idx_custom_query_templates_creator", "created_by", "updated_at"),
        sa.Index("idx_cqt_scope_updated", "scope", sa.desc("updated_at")),
        sa.Index("idx_cqt_creator_updated", "creator_id", sa.desc("updated_at")),
        sa.Index("idx_cqt_tags", "tags", postgresql_using="gin"),
        sa.Index(
            "idx_cqt_shared_projects", "shared_project_ids", postgresql_using="gin"
        ),
    )


class AdvancedQueryWriteback(Base):
    """高级查询回写身份 / 审计记录表 [advanced-query-module Task 1.3]

    回写落点为 `working_papers.parsed_data.univer_snapshot`（cell 值原地更新），
    本表记录回写的 addr_id 身份（与 WP() 公式引用同一身份，R3.2/R3.3），
    供 stale chip 追踪对齐与快照列下钻的结构化索引。

    字段与 V102 表结构逐列对齐（design Data Models §2）：
      id/project_id/addr_id/wp_id/old_value/new_value/operator_id/result/created_at

    Validates: Requirements 3.1, 14.3 (advanced-query-module)
    """

    __tablename__ = "advanced_query_writeback"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    # addr_id: {wp_code}/{sheet_code}/{coordinate_key}（R3.1）
    addr_id: Mapped[str] = mapped_column(sa.Text, nullable=False)
    # wp_id: resolve_instance 附加（可空）
    wp_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )
    old_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    operator_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False
    )
    # result: success/failed
    result: Mapped[str] = mapped_column(sa.Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )

    __table_args__ = (
        sa.Index("idx_aqw_addr_id", "addr_id"),
        sa.Index("idx_aqw_project", "project_id", sa.desc("created_at")),
    )
