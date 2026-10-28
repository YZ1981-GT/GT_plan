"""SQLAlchemy 声明式基类、Mixin 和 PostgreSQL 枚举类型定义"""

import enum
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, func
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
    eqcr = "eqcr"  # EQCR 技术复核人（DB userrole 枚举已含此值，此处对齐消除 schema 漂移）
    readonly = "readonly"
    # 与 PG enum userrole 对齐（库为准）：gt-new-plan 血统的 V206 给库加了该值，
    # 且 users 表有 1 行 role='site_lead' 在用；代码缺此值会让 /api/users 全表
    # 反序列化抛 LookupError 500。
    site_lead = "site_lead"


class ProjectType(str, enum.Enum):
    """项目类型"""

    annual = "annual"
    special = "special"
    ipo = "ipo"
    internal_control = "internal_control"
    capital_verification = "capital_verification"
    tax_audit = "tax_audit"
    # 与 PG enum projecttype 对齐（V053 同精神：库为准，代码补齐）。
    # 2026-10-22 起库中已有项目行使用该值（如「辽宁卫生服务有限公司_2025」），
    # ORM 反序列化整表时缺此值会抛 LookupError 使 GET /api/projects 500。
    enterprise_income_tax_settlement = "enterprise_income_tax_settlement"


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
    eqcr = "eqcr"  # EQCR 技术复核人：Wave 0 冻结角色契约将 eqcr 定为独立合法项目角色
    # （design §2.1 / role_capability_contract.PROJECT_ROLE_SET）。PG enum `projectuserrole`
    # 已含此值（迁移 V109），此处对齐消除 ORM↔DB enum_mismatch 漂移。
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
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def soft_delete(self) -> None:
        """标记为软删除，自动设置 deleted_at 时间戳。"""
        self.is_deleted = True
        self.deleted_at = datetime.now(timezone.utc)


class TimestampMixin:
    """时间戳 Mixin — 自动记录创建和更新时间（全部使用 aware datetime / timestamptz）"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AuditMixin:
    """审计追踪 Mixin — 记录创建人和更新人"""

    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    updated_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )


# ---------------------------------------------------------------------------
# 全局类型映射：所有 datetime 列默认使用 timezone-aware TIMESTAMPTZ
# ---------------------------------------------------------------------------
# 历史问题：SQLAlchemy 2.0 默认 Mapped[datetime] → TIMESTAMP WITHOUT TIME ZONE，
# 和代码中 datetime.now(timezone.utc) 不兼容，asyncpg 报"can't subtract offset-naive
# and offset-aware datetimes"。
#
# 通过注册 type_annotation_map 将 Python datetime 统一映射为 timestamptz，
# 所有 Mapped[datetime] / Mapped[datetime | None] 无需显式传 DateTime(timezone=True) 即可 aware。
from sqlalchemy import DateTime as _DateTime  # noqa: E402

Base.registry.update_type_annotation_map(
    {datetime: _DateTime(timezone=True)}
)
