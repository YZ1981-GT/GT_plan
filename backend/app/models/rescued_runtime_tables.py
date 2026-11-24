"""V275/V276 补齐的运行时表 ORM（2026-11-25 平台技术债清偿）。

三张表此前的形态是「生产裸 SQL 在用、ORM 无模型、迁移无建表」——
`linkage_audit_log` / `seed_load_history` / `wp_review_records` 在共享库根本
不存在，对应代码路径被 try/except 吞掉，功能静默失效（联动审计日志不落库、
种子加载历史恒空、复核深度评分恒走默认值）。V275 补齐迁移建表，本文件补齐
ORM 声明（三层一致：DB 迁移 + ORM `Mapped[]` + service）。

🔴 列型对齐记录：
* `seed_load_history.errors` 是 **JSONB**（错误明细数组）——V275 首版按
  SELECT 反推建成了 integer，与生产 INSERT 的 `CAST(:errors AS JSONB)` 不匹配
  （一写就炸、被 try/except 吞掉）。V276 修正为 JSONB NOT NULL DEFAULT '[]'。
* `wp_review_records` 的列集按生产唯一消费方
  `quality_rating_service._review_depth_score` 的 SELECT 反推
  （project_id / review_status 两列参与聚合）；若后续接入真实写入方，
  列集需按业务扩展并同步迁移。
"""
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

__all__ = [
    "LinkageAuditLog",
    "SeedLoadHistory",
    "WpReviewRecord",
]


class LinkageAuditLog(Base):
    """联动传播审计日志（stale_propagation_engine 写 / linkage_bus 读）。

    列集与 `stale_propagation_engine._write_audit_log` 的 INSERT 逐列一致
    （id 由 DB gen_random_uuid() 生成，写入方不传）。
    """

    __tablename__ = "linkage_audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.dialects.postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    source_uri: Mapped[str] = mapped_column(String, nullable=False)
    affected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.dialects.postgresql.UUID(as_uuid=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now(),
    )


class SeedLoadHistory(Base):
    """模板库种子加载审计轨迹（template_library_mgmt 写/读）。

    🔴 `errors` 是 JSONB（错误明细数组），不是条数 —— 见模块 docstring 的
    V275/V276 列型修正记录。
    """

    __tablename__ = "seed_load_history"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.dialects.postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    seed_name: Mapped[str] = mapped_column(String, nullable=False)
    loaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now(),
    )
    loaded_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.dialects.postgresql.UUID(as_uuid=True), nullable=True,
    )
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=sa.text("'[]'::jsonb"),
    )
    status: Mapped[str] = mapped_column(String, nullable=False, server_default="ok")


class WpReviewRecord(Base):
    """底稿复核记录（quality_rating_service._review_depth_score 读）。

    列集按生产唯一消费方的 SELECT 反推：`review_status='rejected'` 参与退回率
    聚合、`project_id` 过滤。`wp_id` / `reviewer_id` / `review_comment` 是
    复核记录的常规归属列，为后续真实写入方预留（当前无生产写入方）。
    """

    __tablename__ = "wp_review_records"

    id: Mapped[uuid.UUID] = mapped_column(
        sa.dialects.postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        sa.dialects.postgresql.UUID(as_uuid=True), nullable=False,
    )
    wp_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.dialects.postgresql.UUID(as_uuid=True), nullable=True,
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.dialects.postgresql.UUID(as_uuid=True), nullable=True,
    )
    review_status: Mapped[str] = mapped_column(
        String, nullable=False, server_default="pending",
    )
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now(),
    )
