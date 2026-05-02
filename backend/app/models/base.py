"""SQLAlchemy 声明式基类、Mixin 和 PostgreSQL 枚举类型定义"""

import enum
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# ---------------------------------------------------------------------------
# PostgreSQL 枚举类型
# ---------------------------------------------------------------------------


class UserRole(str, enum.Enum):
    """系统用户角色"""

    admin = "admin"
    partner = "partner"
    manager = "manager"
    auditor = "auditor"
    qc = "qc"
    readonly = "readonly"


class ProjectType(str, enum.Enum):
    """项目类型"""

    annual = "annual"
    special = "special"
    ipo = "ipo"
    internal_control = "internal_control"


class ProjectStatus(str, enum.Enum):
    """项目状态"""

    created = "created"
    planning = "planning"
    execution = "execution"
    completion = "completion"
    reporting = "reporting"
    archived = "archived"


class ProjectUserRole(str, enum.Enum):
    """项目成员角色"""

    partner = "partner"
    manager = "manager"
    auditor = "auditor"
    qc = "qc"
    readonly = "readonly"


class PermissionLevel(str, enum.Enum):
    """项目权限级别：edit > review > readonly"""

    edit = "edit"
    review = "review"
    readonly = "readonly"


# ---------------------------------------------------------------------------
# 声明式基类
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 声明式基类"""

    pass


# ---------------------------------------------------------------------------
# Mixin 类
# ---------------------------------------------------------------------------


class SoftDeleteMixin:
    """软删除 Mixin — 所有业务表必须包含。

    设置 is_deleted=True 时会通过 @event.listens_for 自动填充 deleted_at。
    """

    is_deleted: Mapped[bool] = mapped_column(default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)

    def soft_delete(self) -> None:
        """标记为软删除，自动设置 deleted_at 时间戳。"""
        self.is_deleted = True
        self.deleted_at = datetime.utcnow()


class TimestampMixin:
    """时间戳 Mixin — 自动记录创建和更新时间"""

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )


class AuditMixin:
    """审计追踪 Mixin — 记录创建人和更新人"""

    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    updated_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
