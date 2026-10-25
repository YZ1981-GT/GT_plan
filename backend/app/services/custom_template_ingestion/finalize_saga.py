"""Finalize visibility saga —— 消费 G-HANDOFF-CONSUMER（Task 11）。

Spec: custom-workpaper-template-ingestion-and-sync-closure
Requirements: 10.1–10.7, 16.4

流程（design §11）：
  lock candidate digests + ApprovalIntent + idempotency
  → 事务只写 PENDING_VISIBILITY metadata / rollback / outbox
  → 提交 finalized handoff，收集 durable ACK ledger
    （guidance / renderer / public_shell / entry_namespace）
  → 全 ACCEPTED → producer commit-visibility → ACTIVE
  → ACTIVE 后才允许 instantiate
  → reject / timeout / crash：visibility=0，可幂等重试或 compensation

本模块 **import** ``guidance_handoff_consumer_service``，不复制 ACK/visibility schema。
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, MutableMapping, Protocol, Sequence

from app.models.guidance_handoff_ack_models import (
    ACK_ACCEPTED,
    ACK_CONSUMER_ENTRY_NAMESPACE,
    ACK_CONSUMER_GUIDANCE,
    ACK_CONSUMER_PUBLIC_SHELL,
    ACK_CONSUMER_RENDERER,
    ACK_REJECTED,
    VISIBILITY_ACTIVE,
    VISIBILITY_PENDING,
    VISIBILITY_REJECTED,
)
from app.services.custom_template_ingestion.lifecycles import (
    Clock,
    InvalidLifecycleTransition,
    PublicationState,
    SystemClock,
    TemplatePublicationRecord,
)
from app.services.guidance_handoff_consumer_service import (
    GUIDANCE_CONSUMER_VERSION,
    VerificationResult,
    compute_handoff_digest,
    record_ack,
    resolve_visibility,
    verify_finalized_handoff,
)

__all__ = [
    "REQUIRED_FINALIZE_CONSUMERS",
    "FinalizeSagaError",
    "FinalizeLock",
    "AckVerdict",
    "FinalizeSagaResult",
    "InMemoryAckLedger",
    "begin_pending_visibility",
    "collect_consumer_acks",
    "commit_visibility_if_ready",
    "run_finalize_saga",
    "assert_instantiate_allowed",
]

REQUIRED_FINALIZE_CONSUMERS: tuple[str, ...] = (
    ACK_CONSUMER_GUIDANCE,
    ACK_CONSUMER_RENDERER,
    ACK_CONSUMER_PUBLIC_SHELL,
    ACK_CONSUMER_ENTRY_NAMESPACE,
)

#: 各 consumer 实现版本——进入幂等键。
CONSUMER_VERSIONS: Mapping[str, str] = {
    ACK_CONSUMER_GUIDANCE: GUIDANCE_CONSUMER_VERSION,
    ACK_CONSUMER_RENDERER: "renderer-consumer-1.0.0",
    ACK_CONSUMER_PUBLIC_SHELL: "fshell-consumer-1.0.0",
    ACK_CONSUMER_ENTRY_NAMESPACE: "entry-ns-consumer-1.0.0",
}


class FinalizeSagaError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class FinalizeLock:
    """不可变锁：candidate / ApprovalIntent / digests / idempotency。"""

    candidate_id: str
    candidate_digest: str
    approval_intent_id: str
    approval_intent_digest: str
    policy_fingerprint: str
    scanner_fingerprint: str
    authority_ref: str
    mapping_digest: str
    guidance_digest: str
    idempotency_key: str
    organization_id: str

    def fingerprint(self) -> str:
        payload = {
            "candidateId": self.candidate_id,
            "candidateDigest": self.candidate_digest,
            "approvalIntentId": self.approval_intent_id,
            "approvalIntentDigest": self.approval_intent_digest,
            "policyFingerprint": self.policy_fingerprint,
            "scannerFingerprint": self.scanner_fingerprint,
            "authorityRef": self.authority_ref,
            "mappingDigest": self.mapping_digest,
            "guidanceDigest": self.guidance_digest,
            "idempotencyKey": self.idempotency_key,
            "organizationId": self.organization_id,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class AckVerdict:
    consumer: str
    consumer_version: str
    verdict: str
    reason_codes: tuple[str, ...]
    ack_id: str


@dataclass
class FinalizeSagaResult:
    publication: TemplatePublicationRecord
    handoff_id: str
    handoff_digest: str
    lock_fingerprint: str
    visibility_state: str
    acks: list[AckVerdict] = field(default_factory=list)
    runtime_discoverable: bool = False


class InMemoryAckLedger:
    """测试用 ACK ledger：模拟 ``record_ack`` 幂等语义，不依赖 DB。"""

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str, str, str], AckVerdict] = {}
        self.visibility: dict[tuple[str, str], str] = {}

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
        key = (handoff_id, handoff_digest, consumer, consumer_version)
        existing = self._rows.get(key)
        if existing is not None:
            if existing.verdict != verdict:
                raise FinalizeSagaError(
                    f"idempotency digest conflict for {consumer}: "
                    f"{existing.verdict} vs {verdict}"
                )
            return existing
        row = AckVerdict(
            consumer=consumer,
            consumer_version=consumer_version,
            verdict=verdict,
            reason_codes=tuple(reason_codes),
            ack_id=f"ack-{uuid.uuid4()}",
        )
        self._rows[key] = row
        return row

    def resolve(
        self,
        *,
        handoff_id: str,
        handoff_digest: str,
        required: Sequence[str] = REQUIRED_FINALIZE_CONSUMERS,
    ) -> str:
        reasons: list[str] = []
        all_ok = True
        for consumer in required:
            # 取该 consumer 任一 version 的最新行（测试 ledger 每 consumer 一行）
            matches = [
                v
                for (hid, hd, c, _ver), v in self._rows.items()
                if hid == handoff_id and hd == handoff_digest and c == consumer
            ]
            if not matches:
                all_ok = False
                reasons.append(f"ack-missing:{consumer}")
            elif matches[0].verdict != ACK_ACCEPTED:
                all_ok = False
                reasons.append(f"ack-rejected:{consumer}")
        if all_ok:
            state = VISIBILITY_ACTIVE
        elif any(r.startswith("ack-rejected") for r in reasons):
            state = VISIBILITY_REJECTED
        else:
            state = VISIBILITY_PENDING
        self.visibility[(handoff_id, handoff_digest)] = state
        return state


def begin_pending_visibility(
    *,
    lock: FinalizeLock,
    clock: Clock | None = None,
    publication_id: str | None = None,
) -> TemplatePublicationRecord:
    """只写 PENDING_VISIBILITY —— 此时 runtime 不可发现。"""
    clk = clock or SystemClock()
    now = clk.now()
    return TemplatePublicationRecord(
        publication_id=publication_id or f"pub-{uuid.uuid4()}",
        organization_id=lock.organization_id,
        candidate_id=lock.candidate_id,
        candidate_digest=lock.candidate_digest,
        authority_ref=lock.authority_ref,
        state=PublicationState.PENDING_VISIBILITY,
        created_at=now,
        updated_at=now,
    )


def collect_consumer_acks(
    ledger: InMemoryAckLedger,
    *,
    handoff: Mapping[str, Any],
    handoff_digest: str,
    consumer_results: Mapping[str, VerificationResult | str],
) -> list[AckVerdict]:
    """把各 consumer 结论写入 ledger（幂等）。

    ``consumer_results`` 值可以是 ``VerificationResult`` 或 ``ACCEPTED``/``REJECTED``。
    """
    handoff_id = str(handoff.get("handoffId") or "")
    if not handoff_id:
        raise FinalizeSagaError("finalized handoff 缺少 handoffId")
    out: list[AckVerdict] = []
    for consumer in REQUIRED_FINALIZE_CONSUMERS:
        raw = consumer_results.get(consumer)
        if raw is None:
            continue
        if isinstance(raw, VerificationResult):
            verdict = raw.verdict
            reasons = tuple(raw.reason_codes)
        else:
            verdict = str(raw)
            reasons = ()
        if verdict not in (ACK_ACCEPTED, ACK_REJECTED):
            raise FinalizeSagaError(f"非法 verdict: {verdict}")
        out.append(
            ledger.upsert(
                handoff_id=handoff_id,
                handoff_digest=handoff_digest,
                consumer=consumer,
                consumer_version=CONSUMER_VERSIONS[consumer],
                verdict=verdict,
                reason_codes=reasons,
            )
        )
    return out


def commit_visibility_if_ready(
    publication: TemplatePublicationRecord,
    ledger: InMemoryAckLedger,
    *,
    handoff_id: str,
    handoff_digest: str,
    clock: Clock | None = None,
) -> str:
    """全 ACCEPTED → ACTIVE；否则保持 PENDING/FAILED，runtime_discoverable=False。"""
    clk = clock or SystemClock()
    state = ledger.resolve(handoff_id=handoff_id, handoff_digest=handoff_digest)
    if state == VISIBILITY_ACTIVE:
        publication.transition(
            PublicationState.ACTIVE, clock=clk, reason="all_acks_accepted"
        )
    elif state == VISIBILITY_REJECTED:
        publication.transition(
            PublicationState.FAILED, clock=clk, reason="ack_rejected"
        )
    # PENDING：保持 PENDING_VISIBILITY，不 transition
    return state


def assert_instantiate_allowed(publication: TemplatePublicationRecord) -> None:
    if publication.state != PublicationState.ACTIVE:
        raise FinalizeSagaError(
            f"instantiate 仅允许 ACTIVE publication，当前={publication.state.value}"
        )


def run_finalize_saga(
    *,
    lock: FinalizeLock,
    finalized_handoff: Mapping[str, Any],
    consumer_results: Mapping[str, VerificationResult | str],
    ledger: InMemoryAckLedger | None = None,
    clock: Clock | None = None,
    prior_result: FinalizeSagaResult | None = None,
) -> FinalizeSagaResult:
    """完整 saga；相同 idempotency_key 重复调用返回同结果或 digest conflict。"""
    clk = clock or SystemClock()
    ledger = ledger or InMemoryAckLedger()
    lock_fp = lock.fingerprint()

    if prior_result is not None:
        if prior_result.lock_fingerprint != lock_fp:
            raise FinalizeSagaError(
                "idempotency digest conflict: lock fingerprint mismatch"
            )
        return prior_result

    # phase 必须是 finalized
    phase = str(finalized_handoff.get("phase") or "")
    if phase != "finalized":
        raise FinalizeSagaError(f"finalize saga 只接受 finalized handoff，收到 phase={phase!r}")

    publication = begin_pending_visibility(lock=lock, clock=clk)
    handoff_digest = compute_handoff_digest(finalized_handoff)
    handoff_id = str(finalized_handoff.get("handoffId") or "")
    acks = collect_consumer_acks(
        ledger,
        handoff=finalized_handoff,
        handoff_digest=handoff_digest,
        consumer_results=consumer_results,
    )
    vis = commit_visibility_if_ready(
        publication,
        ledger,
        handoff_id=handoff_id,
        handoff_digest=handoff_digest,
        clock=clk,
    )
    return FinalizeSagaResult(
        publication=publication,
        handoff_id=handoff_id,
        handoff_digest=handoff_digest,
        lock_fingerprint=lock_fp,
        visibility_state=vis,
        acks=acks,
        runtime_discoverable=(publication.state == PublicationState.ACTIVE),
    )
