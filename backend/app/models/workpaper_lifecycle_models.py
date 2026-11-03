"""底稿生命周期领域事件（spec procedure-chain-hardening-and-java-contracts R18）。

移入 / 恢复回收站原先只记在 ``wp_index.cross_ref_codes["_recycle_lineage"]``（JSON，随行可改、不能按事件查询）。
现在同事务另写一条只追加的事件（迁移 V207 拥有 DDL、CHECK 与只追加触发器；ORM 只映射列）。旧 JSON 照写（兼容）。

- 不对 ``wp_index`` 建外键：事件要比被引用的行活得久；对 ``projects`` 建外键，项目彻底删除时随项目清掉。
- ``created_at`` 由应用在写入时给（微秒精度）：库默认 ``now()`` 是事务开始时间，同一事务里先移入再恢复会同一时刻。
- 只追加表不带 ``updated_at`` / 软删列。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

EVENT_RECYCLED = "recycled"
EVENT_RESTORED = "restored"


class WorkpaperLifecycleEvent(Base):
    """一张底稿（wp_index + 名下 working_paper）的一次移入 / 恢复回收站。"""

    __tablename__ = "workpaper_lifecycle_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    wp_index_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    wp_code: Mapped[str] = mapped_column(String, nullable=False)
    #: 'recycled' | 'restored'（DB CHECK 约束）
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    #: 原因类别：trim（程序裁剪）/ standard_conversion（准则切换）/ 空（回收站手工恢复不限原因时取最后一次移入的类别）
    kind: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    reason: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    request_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    working_paper_ids: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    #: 导致移入的程序行编码（如 H3-2 ← H3），恢复事件为空
    trim_codes: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
