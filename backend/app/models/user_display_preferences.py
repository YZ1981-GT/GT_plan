"""账号级显示偏好 ORM 模型。

V233（platform-global-display-settings-closure 任务 1A）。
独立 typed table，用 DB CHECK + revision CAS 替代 User JSONB 并发覆盖。
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserDisplayPreferences(Base):
    """账号级显示偏好（一对一，user_id 主键）。"""

    __tablename__ = "user_display_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # 金额单位覆盖：null = 跟随项目
    amount_unit_override: Mapped[str | None] = mapped_column(
        String(8), nullable=True, default=None,
    )

    # 显示字号：xs=11px, sm=12px, md=13px, lg=14px
    font_size: Mapped[str] = mapped_column(
        String(4), nullable=False, server_default=text("'sm'"),
    )

    show_zero: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"),
    )

    # 小数位 0~6
    decimals: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("2"),
    )

    negative_red: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"),
    )

    # 变动高亮阈值 0~1，NUMERIC(5,4)
    highlight_threshold: Mapped[float] = mapped_column(
        Numeric(5, 4), nullable=False, server_default=text("0.2"),
    )

    # 表格密度
    density: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'default'"),
    )

    # 表格编辑方式
    grid_edit_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'excel'"),
    )

    # 按 pageKey 存储的固定列配置 JSONB
    # NOTE: 不写 `'{}'::jsonb`（PG 字面 cast）—— 带 `::` 的文本被 SQLAlchemy 原样塞进
    # CREATE TABLE，SQLite 解析到 `:` 直接 `unrecognized token: ":"`，使**任何**
    # `Base.metadata.create_all(sqlite)` 的测试在 setup 阶段 ERROR（与本仓 7 处同类
    # NOTE 同一条理由）。PG 对 jsonb 列的 `DEFAULT '{}'` 会隐式转型，两种写法在真实库
    # 上等价（真实表由迁移 SQL 创建，ORM 的 server_default 只影响 DDL 生成）。
    fixed_columns: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'"),
    )

    # 乐观锁版本号
    revision: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"),
    )

    updated_at: Mapped[datetime | None] = mapped_column(
        nullable=True, default=None,
    )

    __table_args__ = (
        CheckConstraint(
            "amount_unit_override IS NULL "
            "OR amount_unit_override IN ('yuan', 'qian', 'wan')",
            name="ck_udp_amount_unit_override",
        ),
        CheckConstraint(
            "font_size IN ('xs', 'sm', 'md', 'lg')",
            name="ck_udp_font_size",
        ),
        CheckConstraint(
            "decimals >= 0 AND decimals <= 6",
            name="ck_udp_decimals",
        ),
        CheckConstraint(
            "highlight_threshold >= 0 AND highlight_threshold <= 1",
            name="ck_udp_highlight_threshold",
        ),
        CheckConstraint(
            "density IN ('compact', 'default', 'comfortable')",
            name="ck_udp_density",
        ),
        CheckConstraint(
            "grid_edit_mode IN ('excel', 'click', 'classic')",
            name="ck_udp_grid_edit_mode",
        ),
        CheckConstraint(
            "revision >= 0",
            name="ck_udp_revision_nonneg",
        ),
        # NOTE: `ck_udp_fixed_columns_is_object`（`jsonb_typeof(fixed_columns) = 'object'`）
        # 只登记在真表的迁移 SQL（V235__display_preferences_and_project_amount_unit.sql
        # 第 64~65 行），**不放进 ORM 的 __table_args__**：
        # `jsonb_typeof` 是 PG 专用函数，SQLite 在 CREATE TABLE 校验 CHECK 表达式时
        # 直接报 `no such function: jsonb_typeof` ⇒ 任何
        # `Base.metadata.create_all(sqlite)` 的测试在 setup 阶段 ERROR
        # （2026-10-31 实测辐射面：合并建树 + 批量导入 8 个文件 67 例）。
        # 真实约束在 PG 上由迁移保证，ORM 的 __table_args__ 只影响 DDL 生成。
    )

    def __repr__(self) -> str:
        return (
            f"<UserDisplayPreferences user_id={self.user_id} "
            f"rev={self.revision}>"
        )
