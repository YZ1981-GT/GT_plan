"""函证管理 ORM 模型

能力域 D — global-refinement-v5-closure：
函证表 confirmations，项目级，含类型枚举（应收/应付/银行/借款）、
状态枚举（待发函/已发函/已回函/相符/差异）。
"""

import enum
import uuid
from decimal import Decimal
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ConfirmationType(str, enum.Enum):
    """函证类型"""
    receivable = "receivable"   # 应收
    payable = "payable"         # 应付
    bank = "bank"               # 银行
    loan = "loan"               # 借款


class ConfirmationStatus(str, enum.Enum):
    """函证状态"""
    pending = "pending"           # 待发函
    sent = "sent"                 # 已发函
    returned = "returned"         # 已回函
    matched = "matched"           # 相符
    discrepancy = "discrepancy"   # 差异


class Confirmation(Base, TimestampMixin):
    """函证记录

    每条函证关联一个项目，可选关联底稿（wp_id）和 TB 科目编码（account_code）。
    状态机：pending → sent → returned → matched / discrepancy
    """

    __tablename__ = "confirmations"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    confirm_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )
    counterparty: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    wp_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("working_paper.id"), nullable=True
    )
    account_code: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )
    book_amount: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    confirmed_amount: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    diff_amount: Mapped[Decimal | None] = mapped_column(
        sa.Numeric(20, 2), nullable=True
    )
    diff_note: Mapped[str | None] = mapped_column(
        sa.Text, nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
