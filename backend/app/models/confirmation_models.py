"""函证管理 ORM 模型

能力域 D — global-refinement-v5-closure：
函证表 confirmations，项目级，含类型枚举（应收/应付/银行/借款）、
状态枚举（待发函/已发函/已回函/相符/差异）。

confirmation-attachment-ocr-linkage（V128）追加：
- Confirmation.sent_date / reply_date
- ConfirmationAttachmentLink（附件角色 + 回函件↔发函件强配对）
- ConfirmationActionLog（append-only 审计留痕）
"""

import enum
import uuid
from decimal import Decimal
from datetime import datetime, date

import sqlalchemy as sa
from sqlalchemy import ForeignKey, String, Index, CheckConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
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
    returned = "returned"        # 已回函
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
    # V128 additive: 发函/回函日期
    sent_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    reply_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)


class ConfirmationAttachmentLink(Base):
    """函证↔附件关联（含角色、强配对、匹配状态）"""

    __tablename__ = "confirmation_attachment_link"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    confirmation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("confirmations.id", ondelete="CASCADE"),
        nullable=False,
    )
    attachment_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("attachments.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(10), nullable=False,  # outbound / inbound
    )
    # 回函件强绑到具体某份发函件（role=inbound 时必填）
    paired_outbound_attachment_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True,
    )
    match_status: Mapped[str] = mapped_column(
        String(12), nullable=False, server_default=text("'manual'"),
        # manual / auto / pending（人工队列）/ assigned
    )
    match_evidence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("idx_conf_att_link_conf_role", "confirmation_id", "role"),
        Index("idx_conf_att_link_att", "attachment_id"),
        CheckConstraint(
            "role IN ('outbound', 'inbound')",
            name="chk_conf_att_link_role",
        ),
        CheckConstraint(
            "match_status IN ('manual', 'auto', 'pending', 'assigned')",
            name="chk_conf_att_link_match_status",
        ),
    )


class ConfirmationActionLog(Base):
    """函证操作审计留痕（append-only，DB 触发器禁 UPDATE/DELETE）"""

    __tablename__ = "confirmation_action_log"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    confirmation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False,
    )
    action: Mapped[str] = mapped_column(
        String(24), nullable=False,
        # reverse / apply_reply / match_assign / attachment_link / attachment_unlink
    )
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ocr_original: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    final_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    attachment_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("idx_conf_action_log_conf", "confirmation_id"),
        Index("idx_conf_action_log_project", "project_id"),
        CheckConstraint(
            "action IN ('reverse','apply_reply','match_assign','attachment_link','attachment_unlink')",
            name="chk_conf_action_log_action",
        ),
    )
