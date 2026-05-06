"""EQCR（独立复核合伙人）ORM 模型

Refinement Round 5 — EQCR 工作台所需的意见留痕、独立复核笔记、
影子计算与异议合议四张表。

对应 Alembic 迁移脚本 ``round5_eqcr_20260505.py``。

设计要点：
- ``EqcrOpinion.domain`` 使用 ``String(32)``，前后端约定枚举值（materiality /
  estimate / related_party / going_concern / opinion_type / component_auditor），
  不新建 DB enum，与项目既有 String-based role/source 做法一致。
- ``EqcrShadowComputation`` 不含 SoftDeleteMixin：影子计算是独立取数留痕，
  永久保留用于事后争议。
- ``EqcrDisagreementResolution.participants`` 用 JSONB list[UUID] 存合议参与人。
"""

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin


# ---------------------------------------------------------------------------
# EQCR 意见留痕
# ---------------------------------------------------------------------------


class EqcrOpinion(Base, SoftDeleteMixin, TimestampMixin):
    """EQCR 对判断类事项的意见留痕。

    domain 允许值（前后端约定）：
    - ``materiality``       重要性水平
    - ``estimate``          会计估计
    - ``related_party``     关联方
    - ``going_concern``     持续经营
    - ``opinion_type``      审计意见类型
    - ``component_auditor`` 组成部分审计师（需求 11）

    verdict 允许值：``agree`` / ``disagree`` / ``need_more_evidence``。

    需求 11 场景下 payload 可带 ``auditor_id / auditor_name`` 区分组成部分审计师，
    存于 ``extra_payload`` JSONB 字段。
    """

    __tablename__ = "eqcr_opinions"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    domain: Mapped[str] = mapped_column(String(32), nullable=False)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    __table_args__ = (
        Index(
            "idx_eqcr_opinions_project_domain",
            "project_id",
            "domain",
            postgresql_where=text("is_deleted = false"),
        ),
    )


# ---------------------------------------------------------------------------
# EQCR 独立复核笔记
# ---------------------------------------------------------------------------


class EqcrReviewNote(Base, SoftDeleteMixin, TimestampMixin):
    """EQCR 独立复核笔记（默认仅 EQCR 可见）。

    需求 3：默认 ``shared_to_team=False``，项目组成员不可见；
    EQCR 单条点击"分享给项目组"切 True，并同步到
    ``Project.wizard_state.communications`` 沟通记录。
    """

    __tablename__ = "eqcr_review_notes"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    shared_to_team: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    shared_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    __table_args__ = (
        Index(
            "idx_eqcr_review_notes_project",
            "project_id",
            postgresql_where=text("is_deleted = false"),
        ),
    )


# ---------------------------------------------------------------------------
# EQCR 影子计算
# ---------------------------------------------------------------------------


class EqcrShadowComputation(Base, TimestampMixin):
    """EQCR 独立跑一遍勾稽的结果永久留痕。

    需求 4：为避免争议，影子计算结果 **不做软删除**。
    ``computation_type`` 允许值（前后端约定）：
    ``cfs_supplementary`` / ``debit_credit_balance`` / ``tb_vs_report`` /
    ``intercompany_elimination``。
    """

    __tablename__ = "eqcr_shadow_computations"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    computation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    params: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    team_result_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    has_diff: Mapped[bool] = mapped_column(
        server_default=text("false"), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    __table_args__ = (
        Index(
            "idx_eqcr_shadow_comp_project_type",
            "project_id",
            "computation_type",
        ),
    )


# ---------------------------------------------------------------------------
# EQCR 异议合议记录
# ---------------------------------------------------------------------------


class EqcrDisagreementResolution(Base, TimestampMixin):
    """EQCR 与项目组意见不一致时触发的合议结论。

    需求 5：EQCR verdict='disagree' 时创建一条记录，
    参与人包括项目合伙人 / EQCR / 质控合伙人（用 JSONB list[UUID]）。
    """

    __tablename__ = "eqcr_disagreement_resolutions"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    eqcr_opinion_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("eqcr_opinions.id"), nullable=False
    )
    participants: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_verdict: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)

    __table_args__ = (
        Index(
            "idx_eqcr_disagreement_project",
            "project_id",
        ),
    )
