"""T型账户 ORM 模型

对应 Alembic 迁移脚本 010_t_accounts.py
用于现金流量表编制中复杂科目的借贷分析
"""

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TAccount(Base):
    """T型账户"""

    __tablename__ = "t_accounts"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    account_code: Mapped[str] = mapped_column(String(50), nullable=False)
    account_name: Mapped[str] = mapped_column(String(200), nullable=False)
    account_type: Mapped[str] = mapped_column(String(50), nullable=False)  # asset/liability/equity/revenue/expense
    opening_balance: Mapped[Decimal] = mapped_column(sa.Numeric(20, 2), server_default=text("0"), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(server_default=text("false"), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("idx_t_accounts_project", "project_id"),
        Index("idx_t_accounts_account", "account_code"),
    )


class TAccountEntry(Base):
    """T型账户分录"""

    __tablename__ = "t_account_entries"

    id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    t_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("t_accounts.id"), nullable=False)
    entry_type: Mapped[str] = mapped_column(String(10), nullable=False)  # debit / credit
    amount: Mapped[Decimal] = mapped_column(sa.Numeric(20, 2), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(server_default=text("false"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("idx_t_account_entries_account", "t_account_id"),
    )


# ---------------------------------------------------------------------------
# T型账户模版（常见复杂交易）
# ---------------------------------------------------------------------------

T_ACCOUNT_TEMPLATES: list[dict] = [
    {
        "name": "固定资产处置",
        "account_code": "1601",
        "account_name": "固定资产清理",
        "account_type": "asset",
        "description": "固定资产处置T型账户：借方=原值转入+清理费用，贷方=累计折旧转入+减值准备转入+处置收入+残值收入",
    },
    {
        "name": "债务重组",
        "account_code": "2201",
        "account_name": "应付账款-债务重组",
        "account_type": "liability",
        "description": "债务重组T型账户：借方=债务减免+以资产清偿，贷方=原债务余额",
    },
    {
        "name": "长期股权投资处置",
        "account_code": "1511",
        "account_name": "长期股权投资",
        "account_type": "asset",
        "description": "长期股权投资处置T型账户：借方=期初余额+追加投资+权益法调整，贷方=处置成本+减值",
    },
    {
        "name": "在建工程转固",
        "account_code": "1604",
        "account_name": "在建工程",
        "account_type": "asset",
        "description": "在建工程转固T型账户：借方=期初余额+本期增加，贷方=转入固定资产+减值",
    },
    {
        "name": "投资性房地产转换",
        "account_code": "1503",
        "account_name": "投资性房地产",
        "account_type": "asset",
        "description": "投资性房地产转换T型账户：借方=期初余额+自用转投资，贷方=投资转自用+处置",
    },
]
