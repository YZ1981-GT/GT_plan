"""G-HANDOFF-CONSUMER 的 durable ACK ledger 与 visibility saga ORM 模型（V157）

两张表：
    guidance_consumer_ack        durable、幂等的 ConsumerAck ledger
    guidance_handoff_visibility  finalize visibility saga 状态（PENDING/ACTIVE/REJECTED）

═══ 为什么需要它（spec Requirement 13）═══

C0 wire bundle 只定义了 ``CustomGuidanceHandoff`` / ``ConsumerAck`` 的**线格式**，
没有任何 durable 消费方。custom finalize 采用
``PENDING visibility → durable ACK ledger → producer commit-visibility`` saga
（design §11），guidance 作为 consumer 必须：

    1. 对 finalized handoff 跑有序校验，产出 ACCEPTED/REJECTED ``ConsumerAck``；
    2. 把 ACK 写成 durable、对 ``(handoff_id, handoff_digest, consumer, consumer_version)``
       幂等的 ledger 行——重复提交返回同一结果，不产生第二行；
    3. 只有全部 required ACK = ACCEPTED，visibility 才允许 PENDING→ACTIVE；
       任一 REJECTED/超时，visibility 保持 0（PENDING/REJECTED）。

🔴 铁律（由服务层 enforcement，不由表结构保证）：
    * candidate handoff 永远只登记 review_pending，绝不写 ACCEPTED（不得成为 exact）。
    * ACK 幂等键 = (handoff_id, handoff_digest, consumer, consumer_version)——
      partial 唯一索引，重复写命中同一行。
    * ACK verdict=REJECTED 时 visibility 必须 = 0（PENDING 或 REJECTED，绝不 ACTIVE）。
    * handoff 变化（digest 变）产生**新** handoff_digest，旧 ACTIVE 行 stale，
      需重新 ACK；不复用旧 digest 的 ACCEPTED。
"""

from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


# ---------------------------------------------------------------------------
# 枚举常量（与服务层保持一致；DB CHECK 约束在迁移里定义）
# ---------------------------------------------------------------------------

# ConsumerAck.consumer 枚举——与 C0 schema ConsumerAck.consumer 完全一致
ACK_CONSUMER_GUIDANCE = "guidance"
ACK_CONSUMER_RENDERER = "renderer"
ACK_CONSUMER_PUBLIC_SHELL = "public_shell"
ACK_CONSUMER_ENTRY_NAMESPACE = "entry_namespace"
ACK_CONSUMERS = frozenset(
    {
        ACK_CONSUMER_GUIDANCE,
        ACK_CONSUMER_RENDERER,
        ACK_CONSUMER_PUBLIC_SHELL,
        ACK_CONSUMER_ENTRY_NAMESPACE,
    }
)

ACK_ACCEPTED = "ACCEPTED"
ACK_REJECTED = "REJECTED"
ACK_VERDICTS = frozenset({ACK_ACCEPTED, ACK_REJECTED})

# visibility saga 状态
VISIBILITY_PENDING = "PENDING"
VISIBILITY_ACTIVE = "ACTIVE"
VISIBILITY_REJECTED = "REJECTED"
VISIBILITY_STATES = frozenset({VISIBILITY_PENDING, VISIBILITY_ACTIVE, VISIBILITY_REJECTED})

# handoff 阶段（review_pending 仅供 candidate 使用；不写进 ACK ledger）
HANDOFF_PHASE_CANDIDATE = "candidate"
HANDOFF_PHASE_FINALIZED = "finalized"


class GuidanceConsumerAck(Base):
    """durable、幂等的 ConsumerAck ledger 行。

    幂等键 = (handoff_id, handoff_digest, consumer, consumer_version)。重复
    提交同一 (handoff, consumer, version) 命中同一行、返回同 verdict，不产生
    第二行——由迁移里的 partial 唯一索引 + 服务层 upsert 双重保证。
    """

    __tablename__ = "guidance_consumer_ack"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ack_id: Mapped[str] = mapped_column(String(128), nullable=False)
    handoff_id: Mapped[str] = mapped_column(String(128), nullable=False)
    handoff_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    consumer: Mapped[str] = mapped_column(String(32), nullable=False, default=ACK_CONSUMER_GUIDANCE)
    consumer_version: Mapped[str] = mapped_column(String(64), nullable=False)
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)

    #: sha256 of the digests actually validated during verification（authority /
    #: artifact / mapping / formulaBoundary / guidance），供跨消费方复核。
    validated_digests_json: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    #: 结构化 reason 码（REJECTED 时非空；ACCEPTED 时为空列表）。
    reason_codes_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    recorded_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )

    @property
    def is_accepted(self) -> bool:
        return self.verdict == ACK_ACCEPTED


class GuidanceHandoffVisibility(Base):
    """finalize visibility saga 的 guidance 侧视图。

    guidance 不拥有 custom 的 runtime，但对每个 (handoff_id, handoff_digest)
    维护一个 visibility 判定：只有本消费方 ACCEPTED 时才允许 ACTIVE；REJECTED
    或未 ACK 时保持 0（PENDING/REJECTED）。这是 saga「durable ACK ledger →
    commit-visibility」环节里 guidance 能诚实表达的部分，不宣称跨系统 ACID。
    """

    __tablename__ = "guidance_handoff_visibility"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    handoff_id: Mapped[str] = mapped_column(String(128), nullable=False)
    handoff_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    organization_id: Mapped[str] = mapped_column(String(128), nullable=False)
    project_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    wp_code: Mapped[str] = mapped_column(String(32), nullable=False)
    entry_id: Mapped[str] = mapped_column(String(512), nullable=False)
    sheet_uid: Mapped[str] = mapped_column(String(128), nullable=False)

    state: Mapped[str] = mapped_column(String(16), nullable=False, default=VISIBILITY_PENDING)
    #: 反映本次判定所依据的 ACK ledger 行 ack_id（REJECTED/PENDING 时可能为空）。
    decisive_ack_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reason_codes_json: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    #: supersede 链：新 handoff_digest ACTIVE 后旧行标 stale（写入被取代者 id）。
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    stale: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()
    )

    @property
    def is_visible(self) -> bool:
        """runtime 是否可见——只有 ACTIVE 且未 stale 才可见。"""
        return self.state == VISIBILITY_ACTIVE and not self.stale
