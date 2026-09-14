"""底稿可见性隔离 ORM 模型（procedure-delegation-visibility-isolation / Task 2）

四张持久真源（迁移 V113 拥有 DDL、约束与 append-only 触发器；ORM 只映射列，不重复声明
索引/触发器，由 tests/procedure_delegation_visibility/test_v113_schema_contract.py 对 DB 精校）：

- ``WorkpaperDelegationHistory``：History_Set 唯一来源，append-only 委派历史快照
  （lead/assignee/reviewer 事件时 user/staff/wp/task/sheet/scope 均固定）。
- ``WpAccessSecurityOutbox``：内部安全审计发件箱，append-only，保留真实拒绝 reason。
- ``WpVisibilityPolicyEpoch``：每项目持久单调 policy epoch（可变，非 append-only）。
- ``WpVisibilityInvalidationOutbox``：失效发件箱，append-only。

设计约定：
- append-only 表不使用 SoftDeleteMixin，也不带 ``updated_at``（DB 无此列，避免 orm_extra 漂移）；
  仅显式声明 ``created_at``（TIMESTAMPTZ）。
- ``epoch`` 用 ``BigInteger`` 精确对齐 DB ``BIGINT``（普通 int 会映射 INTEGER → type_mismatch）。
- 枚举字段用 ``String`` + DB CHECK 约束（不建 PG enum 类型，规避 enum 漂移与迁移复杂度）。
- 敏感正文/名称/文件字节/prompt/token 不入表，仅存标识、reason 与脱敏 detail/scope。
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WorkpaperDelegationHistory(Base):
    """History_Set 唯一来源：append-only 委派历史快照。

    快照事件时 user/staff/wp/task/sheet/scope；History_Set 计算禁止 JOIN 当前
    StaffMember/ProcedureRowTask/sheet 反推参与人及页面。
    """

    __tablename__ = "workpaper_delegation_history"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    request_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    wp_index_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("wp_index.id"), nullable=False)
    wp_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("working_paper.id"), nullable=True)
    # 委派层与目标角色
    layer: Mapped[str] = mapped_column(String(20), nullable=False)          # 'lead' | 'row'
    target_role: Mapped[str] = mapped_column(String(20), nullable=False)    # 'lead' | 'assignee' | 'reviewer'
    action: Mapped[str] = mapped_column(String(20), nullable=False)         # 'assign' | 'reassign' | 'clear'
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("procedure_row_tasks.id"), nullable=True)
    sheet_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    # 事件时身份快照（同一自然人 user+staff 均固定）
    old_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    new_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    old_staff_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("staff_members.id"), nullable=True)
    new_staff_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("staff_members.id"), nullable=True)
    # 操作人与理由
    actor_user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # scope 快照（脱敏为 audit_cycle 列表）
    scope_before: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    scope_after: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class WpAccessSecurityOutbox(Base):
    """内部安全审计发件箱（append-only）：保留真实拒绝原因，对外统一 404/429。"""

    __tablename__ = "wp_access_security_outbox"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    request_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    # 可空绑定（拒绝时资源可能未解析/不存在）
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    wp_index_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("wp_index.id"), nullable=True)
    wp_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("working_paper.id"), nullable=True)
    sheet_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    requested_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # 入口与动作
    entrypoint: Mapped[str] = mapped_column(String(200), nullable=False)
    entry_family: Mapped[str | None] = mapped_column(String(60), nullable=True)
    route_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    http_method: Mapped[str | None] = mapped_column(String(10), nullable=True)
    action: Mapped[str | None] = mapped_column(String(60), nullable=True)
    # 内部真实拒绝原因（DB CHECK 约束校验取值域）
    reason: Mapped[str] = mapped_column(String(40), nullable=False)
    # enqueue 期投递元数据
    delivery_state: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    delivery_attempt: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    # 脱敏 detail
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class WpVisibilityPolicyEpoch(Base):
    """每项目持久单调 policy epoch（可变；BEFORE UPDATE 触发器强制非递减）。"""

    __tablename__ = "wp_visibility_policy_epoch"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    epoch: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("1"))
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class WpVisibilityInvalidationOutbox(Base):
    """可见性失效发件箱（append-only）：与 policy epoch 递增同事务写入。"""

    __tablename__ = "wp_visibility_invalidation_outbox"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    epoch: Mapped[int] = mapped_column(BigInteger, nullable=False)
    change_type: Mapped[str] = mapped_column(String(20), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    delivery_state: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"))
    delivery_attempt: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
