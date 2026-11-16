"""finalize saga 的持久化 ACK ledger（替代 `InMemoryAckLedger`）。

Spec: custom-workpaper-template-ingestion-and-sync-closure, Task 16

## 本模块补的接线

`finalize_saga.run_finalize_saga` 的 `ledger` 参数此前**只接受**
`InMemoryAckLedger`：进程一退，ACK 与 visibility 全丢，`publication` 永远停在
PENDING_VISIBILITY —— 于是 `POST /publications/instantiate`（已就绪）在真实
链路里永远拿不到 ACTIVE。

而持久化能力其实早就在：`guidance_handoff_consumer_service.record_ack` 与
`resolve_visibility` 读写真实 `guidance_consumer_ack` /
`guidance_handoff_visibility` 表。本模块把它们包装成与 `InMemoryAckLedger`
**同形**的接口（`upsert` / `resolve`），使 saga 无需改动即可落库。

## 语义对齐（与内存版逐条一致，不另立判据）

* `upsert` 幂等键 = (handoff_id, handoff_digest, consumer, consumer_version)；
  已存在返回既有行（`record_ack` 原样实现）。
* `upsert` 在 verdict 冲突时抛 `FinalizeSagaError` —— 内存版有此检查，
  `record_ack` 没有（它直接返回既有行）。这里**保留内存版的严格语义**：
  同一幂等键换 verdict 是调用方缺陷，必须暴露而不是静默吞掉。
* `resolve` 只认 ACCEPTED / REJECTED，缺 ACK = PENDING；有 REJECTED =
  REJECTED（`resolve_visibility` 原样实现）。
* 必需 consumer 集合取 `finalize_saga.REQUIRED_FINALIZE_CONSUMERS`（四个），
  与内存版一致 —— 不用 `resolve_visibility` 的默认单 consumer。
"""
from __future__ import annotations

from typing import Any, Sequence

from app.models.guidance_handoff_ack_models import (
    ACK_ACCEPTED,
    ACK_REJECTED,
    VISIBILITY_ACTIVE,
    VISIBILITY_PENDING,
    VISIBILITY_REJECTED,
)
from app.services.custom_template_ingestion.finalize_saga import (
    AckVerdict,
    FinalizeSagaError,
    REQUIRED_FINALIZE_CONSUMERS,
)
from app.services.guidance_handoff_consumer_service import (
    VerificationResult,
    record_ack,
    resolve_visibility,
)

__all__ = ["DurableAckLedger"]


class DurableAckLedger:
    """把 `record_ack` / `resolve_visibility` 适配成 saga 的 ledger 协议。"""

    def __init__(self, session: Any) -> None:
        self._session = session

    def upsert(
        self,
        *,
        handoff_id: str,
        handoff_digest: str,
        consumer: str,
        consumer_version: str,
        verdict: str,
        reason_codes: Sequence[str] = (),
    ) -> AckVerdict:
        if verdict not in (ACK_ACCEPTED, ACK_REJECTED):
            raise FinalizeSagaError(f"非法 verdict: {verdict}")

        existing = self._existing(handoff_id, handoff_digest, consumer, consumer_version)
        if existing is not None:
            # 🔴 与内存版同判据：同一幂等键换 verdict 是缺陷，必须暴露。
            if existing.verdict != verdict:
                raise FinalizeSagaError(
                    f"idempotency digest conflict for {consumer}: "
                    f"{existing.verdict} vs {verdict}"
                )
            return existing

        result = VerificationResult(
            verdict=verdict,
            handoff_digest=handoff_digest,
            reason_codes=tuple(reason_codes),
            validated_digests={},
        )
        row = record_ack(
            self._session,
            handoff_id=handoff_id,
            result=result,
            consumer=consumer,
            consumer_version=consumer_version,
        )
        return AckVerdict(
            consumer=row.consumer,
            consumer_version=row.consumer_version,
            verdict=row.verdict,
            reason_codes=tuple(row.reason_codes_json or ()),
            ack_id=row.ack_id,
        )

    def resolve(
        self,
        *,
        handoff_id: str,
        handoff_digest: str,
        required: Sequence[str] = REQUIRED_FINALIZE_CONSUMERS,
    ) -> str:
        handoff = {"handoffId": handoff_id}
        row = resolve_visibility(
            self._session,
            handoff=handoff,
            handoff_digest=handoff_digest,
            required_consumers=tuple(required),
        )
        state = row.state
        if state not in (VISIBILITY_ACTIVE, VISIBILITY_PENDING, VISIBILITY_REJECTED):
            # fail-closed：未知状态当 PENDING，绝不当 ACTIVE
            return VISIBILITY_PENDING
        return state

    # ── 内部 ────────────────────────────────────────────────────────────────

    def _existing(
        self,
        handoff_id: str,
        handoff_digest: str,
        consumer: str,
        consumer_version: str,
    ) -> AckVerdict | None:
        from app.models.guidance_handoff_ack_models import GuidanceConsumerAck

        row = (
            self._session.query(GuidanceConsumerAck)
            .filter(
                GuidanceConsumerAck.handoff_id == handoff_id,
                GuidanceConsumerAck.handoff_digest == handoff_digest,
                GuidanceConsumerAck.consumer == consumer,
                GuidanceConsumerAck.consumer_version == consumer_version,
            )
            .one_or_none()
        )
        if row is None:
            return None
        return AckVerdict(
            consumer=row.consumer,
            consumer_version=row.consumer_version,
            verdict=row.verdict,
            reason_codes=tuple(row.reason_codes_json or ()),
            ack_id=row.ack_id,
        )
