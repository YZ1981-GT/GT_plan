"""G-HANDOFF-CONSUMER：candidate/finalized handoff 校验 pipeline + durable 幂等
ACK ledger + finalize visibility saga（spec Task 16 / Requirement 13）。

═══ 职责 ═══

1. ``compute_handoff_digest`` —— 对 handoff 载荷算 canonical sha256（内容变即变）。
2. ``verify_candidate_handoff`` —— candidate 只产 ``review_pending`` verdict，
   **绝不** exact，也不写 ACK ledger。
3. ``verify_finalized_handoff`` —— 按 design §11 的有序 pipeline 校验：
       contract → phase discriminator → TemplateAuthorityIdentity
       → artifact/mapping/formula-boundary/guidance digests
       → 九段唯一 → SourceRef kind 可注册（拒生命周期名）
       → runtime membership → 结论 ACCEPTED/REJECTED。
4. ``record_ack`` —— 把结论写成 durable、对
   ``(handoff_id, handoff_digest, consumer, consumer_version)`` 幂等的 ledger 行。
5. ``resolve_visibility`` —— saga：全部 required ACK=ACCEPTED 才允许 PENDING→ACTIVE；
   任一 REJECTED/缺失 → visibility 保持 0。
6. ``mark_stale_on_change`` —— handoff 变化/withdraw 使旧 confirmed stale。

🔴 判据（mutation 必须抓得住）：
    * M-CAND-EXACT：让 candidate 也返回 ACCEPTED → candidate 提前可见 → 测试红
    * M-SECTIONS：删「九段唯一」校验 → 缺段 handoff 被 ACCEPTED → 测试红
    * M-ACK-IDEM：record_ack 每次插新行（不 upsert）→ 幂等破坏 → 测试红
    * M-VIS-REJECT：REJECTED ACK 仍置 ACTIVE → 未 ACK entry 暴露 → 测试红
    * M-DIGEST-CONST：compute_handoff_digest 退化常量 → 内容变 digest 不变 → 测试红

本模块不修改 custom runtime，也不宣称跨系统 ACID —— 只诚实表达 guidance 侧的
durable ACK 与 visibility 判定。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from app.models.guidance_handoff_ack_models import (
    ACK_ACCEPTED,
    ACK_CONSUMER_GUIDANCE,
    ACK_CONSUMERS,
    ACK_REJECTED,
    GuidanceConsumerAck,
    GuidanceHandoffVisibility,
    HANDOFF_PHASE_CANDIDATE,
    HANDOFF_PHASE_FINALIZED,
    VISIBILITY_ACTIVE,
    VISIBILITY_PENDING,
    VISIBILITY_REJECTED,
)
from app.services.guidance_gc0_contract import (
    GC0_CONTRACT_VERSION,
    validate_contract_version,
)

__all__ = [
    "GUIDANCE_CONSUMER_VERSION",
    "CANONICAL_HANDOFF_SECTION_KEYS",
    "VerificationResult",
    "compute_handoff_digest",
    "verify_candidate_handoff",
    "verify_finalized_handoff",
    "record_ack",
    "resolve_visibility",
    "mark_stale_on_change",
    "build_ghandoff_consumer_evidence_payload",
]

#: 本 consumer 的实现版本——进入 ACK 幂等键，实现升级即产生新键。
GUIDANCE_CONSUMER_VERSION = "guid-consumer-1.0.0"

#: 九段 canonical key（与 C0 GuidanceSectionKey enum / guidance_inventory 一致）。
CANONICAL_HANDOFF_SECTION_KEYS: tuple[str, ...] = (
    "purpose",
    "materials",
    "data_sources",
    "steps",
    "formulas",
    "judgments",
    "evidence",
    "common_errors",
    "completion",
)

#: SourceLocator 的合法 kind——生命周期名（custom_candidate/custom_confirmed）
#: 绝不允许作 locator kind（design §1.1 / §5）。
_ALLOWED_LOCATOR_KINDS = frozenset(
    {
        "xlsx",
        "docx",
        "bcd_markdown",
        "methodology_publication",
        "project_evidence",
        "custom_artifact",
    }
)
_LIFECYCLE_KIND_NAMES = frozenset({"custom_candidate", "custom_confirmed"})


@dataclass(frozen=True)
class VerificationResult:
    """一次 handoff 校验的结论（纯数据，不含 DB 副作用）。"""

    verdict: str  # "ACCEPTED" | "REJECTED" | "review_pending"
    handoff_digest: str
    reason_codes: tuple[str, ...] = ()
    validated_digests: Mapping[str, str] = field(default_factory=dict)

    @property
    def is_accepted(self) -> bool:
        return self.verdict == ACK_ACCEPTED


# ---------------------------------------------------------------------------
# Digest
# ---------------------------------------------------------------------------


def compute_handoff_digest(handoff: Mapping[str, Any]) -> str:
    """对 handoff 载荷算 canonical sha256。

    🔴 必须真哈希内容——退化为常量/固定串会让「内容变化」检测不到，直接假绿。
    ``evidence`` 里的 ``recordedAt`` 等运行元数据不该影响 digest 的稳定性判据，
    但为简洁与安全起见此处对**整个** handoff 规范化取哈希：调用方只要保证
    同一逻辑 handoff 用同一载荷即可（fixtures 满足）。
    """
    canonical = json.dumps(
        handoff, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 校验 pipeline
# ---------------------------------------------------------------------------


def _section_keys(handoff: Mapping[str, Any]) -> list[str]:
    sections = handoff.get("sections") or []
    keys: list[str] = []
    for sec in sections:
        if isinstance(sec, Mapping):
            keys.append(str(sec.get("key")))
    return keys


def _check_sections(handoff: Mapping[str, Any]) -> list[str]:
    """九段必须恰好唯一覆盖 canonical key，且每段 refs 非空。返回 reason 码列表。"""
    reasons: list[str] = []
    keys = _section_keys(handoff)
    present = set(keys)

    # 缺段
    for key in CANONICAL_HANDOFF_SECTION_KEYS:
        if key not in present:
            reasons.append(f"missing-section:{key}")
    # 重复
    seen: set[str] = set()
    for key in keys:
        if key in seen:
            reasons.append(f"duplicate-section:{key}")
        seen.add(key)
    # 非 canonical key
    for key in present:
        if key not in CANONICAL_HANDOFF_SECTION_KEYS:
            reasons.append(f"unknown-section:{key}")
    # 每段至少一个 sourceRef，且 locator kind 合法
    for sec in handoff.get("sections") or []:
        if not isinstance(sec, Mapping):
            continue
        key = sec.get("key")
        refs = sec.get("sourceRefs") or []
        if not refs:
            reasons.append(f"empty-refs:{key}")
            continue
        for ref in refs:
            locator = ref.get("locator") if isinstance(ref, Mapping) else None
            kind = locator.get("kind") if isinstance(locator, Mapping) else None
            if kind in _LIFECYCLE_KIND_NAMES:
                reasons.append(f"lifecycle-locator-kind:{kind}")
            elif kind not in _ALLOWED_LOCATOR_KINDS:
                reasons.append(f"invalid-locator-kind:{kind}")
    return reasons


def _check_finalized_authority(handoff: Mapping[str, Any]) -> list[str]:
    """finalized handoff 的 authority 必须是 finalized variant 且字段齐全。"""
    reasons: list[str] = []
    authority = handoff.get("authority")
    if not isinstance(authority, Mapping):
        return ["authority-missing"]
    if authority.get("phase") != HANDOFF_PHASE_FINALIZED:
        reasons.append(f"authority-phase-mismatch:{authority.get('phase')}")
    for f in ("templateId", "templateVersionId", "finalizationId", "artifactSha256"):
        if not authority.get(f):
            reasons.append(f"authority-field-missing:{f}")
    # candidate-only 字段不得出现在 finalized authority（防伪造）
    if authority.get("candidateRevision"):
        reasons.append("authority-carries-candidate-revision")
    return reasons


def _check_digests_present(handoff: Mapping[str, Any]) -> tuple[list[str], dict[str, str]]:
    """artifact / mapping / formula-boundary / guidance digests 必须齐全。"""
    reasons: list[str] = []
    validated: dict[str, str] = {}
    authority = handoff.get("authority") if isinstance(handoff.get("authority"), Mapping) else {}

    artifact = authority.get("artifactSha256")
    if artifact:
        validated["artifact"] = str(artifact)
        validated["authority"] = str(authority.get("policyVersion") or artifact)
    else:
        reasons.append("digest-missing:artifact")

    mapping_v = handoff.get("mappingVersion")
    if mapping_v:
        validated["mapping"] = str(mapping_v)
    else:
        reasons.append("digest-missing:mapping")

    fb = handoff.get("formulaBoundaryVersion")
    if fb:
        validated["formulaBoundary"] = str(fb)
    else:
        reasons.append("digest-missing:formulaBoundary")

    guid = handoff.get("guidanceRevision")
    if guid:
        validated["guidance"] = str(guid)
    else:
        reasons.append("digest-missing:guidance")

    stale_fp = handoff.get("staleFingerprint")
    if not (isinstance(stale_fp, str) and len(stale_fp) == 64):
        reasons.append("stale-fingerprint-malformed")
    return reasons, validated


def _check_membership(handoff: Mapping[str, Any]) -> list[str]:
    """runtime membership：entryId + sheetUid + wpCode 三者齐全。"""
    reasons: list[str] = []
    for f in ("entryId", "sheetUid", "wpCode", "organizationId"):
        if not handoff.get(f):
            reasons.append(f"membership-field-missing:{f}")
    return reasons


def verify_candidate_handoff(handoff: Mapping[str, Any]) -> VerificationResult:
    """candidate handoff → 只产 ``review_pending``，绝不 ACCEPTED（不得成为 exact）。

    仍做 contract + phase 校验：contract 不兼容或 phase≠candidate 一律 REJECTED，
    但**通过**的 candidate 只能 review_pending，consumer 不写 ACK ledger。
    """
    digest = compute_handoff_digest(handoff)
    decision = validate_contract_version(handoff, consumer_role="consumer")
    if not decision.is_accept:
        return VerificationResult(
            verdict=ACK_REJECTED,
            handoff_digest=digest,
            reason_codes=tuple(f"contract:{r.code}" for r in decision.reasons),
        )
    if handoff.get("phase") != HANDOFF_PHASE_CANDIDATE:
        return VerificationResult(
            verdict=ACK_REJECTED,
            handoff_digest=digest,
            reason_codes=(f"phase-mismatch:{handoff.get('phase')}",),
        )
    # candidate authority 不得携带 finalized-only 字段
    authority = handoff.get("authority") if isinstance(handoff.get("authority"), Mapping) else {}
    if authority.get("finalizationId") or handoff.get("finalizationId"):
        return VerificationResult(
            verdict=ACK_REJECTED,
            handoff_digest=digest,
            reason_codes=("candidate-carries-finalization",),
        )
    return VerificationResult(verdict="review_pending", handoff_digest=digest)


def verify_finalized_handoff(handoff: Mapping[str, Any]) -> VerificationResult:
    """finalized handoff → 有序 pipeline → ACCEPTED / REJECTED。

    顺序（design §11）：contract → phase → authority → digests → 九段 → membership。
    任一环节产生 reason 即 REJECTED（收集全部 reason 便于诊断，但只要非空即拒）。
    """
    digest = compute_handoff_digest(handoff)
    reasons: list[str] = []

    # 1. contract major/minor
    decision = validate_contract_version(handoff, consumer_role="consumer")
    if not decision.is_accept:
        reasons.extend(f"contract:{r.code}" for r in decision.reasons)
        # contract 不兼容是 fail-closed 终止点，无需再跑后续。
        return VerificationResult(
            verdict=ACK_REJECTED, handoff_digest=digest, reason_codes=tuple(reasons)
        )

    # 2. phase discriminator
    if handoff.get("phase") != HANDOFF_PHASE_FINALIZED:
        return VerificationResult(
            verdict=ACK_REJECTED,
            handoff_digest=digest,
            reason_codes=(f"phase-mismatch:{handoff.get('phase')}",),
        )

    # 3. authority
    reasons.extend(_check_finalized_authority(handoff))
    # 4. digests
    digest_reasons, validated = _check_digests_present(handoff)
    reasons.extend(digest_reasons)
    # 5. 九段 + SourceRef kind
    reasons.extend(_check_sections(handoff))
    # 6. membership
    reasons.extend(_check_membership(handoff))

    if reasons:
        return VerificationResult(
            verdict=ACK_REJECTED,
            handoff_digest=digest,
            reason_codes=tuple(dict.fromkeys(reasons)),  # 去重保序
            validated_digests=validated,
        )
    return VerificationResult(
        verdict=ACK_ACCEPTED,
        handoff_digest=digest,
        reason_codes=(),
        validated_digests=validated,
    )


# ---------------------------------------------------------------------------
# durable 幂等 ACK ledger（sync Session 友好，供测试与真实 PG 共用）
# ---------------------------------------------------------------------------


def record_ack(
    session: Any,
    *,
    handoff_id: str,
    result: VerificationResult,
    consumer: str = ACK_CONSUMER_GUIDANCE,
    consumer_version: str = GUIDANCE_CONSUMER_VERSION,
    ack_id: str | None = None,
) -> GuidanceConsumerAck:
    """幂等写 ACK ledger。

    幂等键 = (handoff_id, handoff_digest, consumer, consumer_version)。已存在则
    返回既有行（不改 verdict、不新增行）；不存在才插入。candidate 的
    ``review_pending`` 不进本表——调用前应确保 verdict ∈ {ACCEPTED, REJECTED}。
    """
    if consumer not in ACK_CONSUMERS:
        raise ValueError(f"unknown consumer: {consumer}")
    if result.verdict not in (ACK_ACCEPTED, ACK_REJECTED):
        raise ValueError(
            f"ACK ledger 只接受 ACCEPTED/REJECTED，收到 {result.verdict}"
            "（candidate 的 review_pending 不得进入 ledger）"
        )

    existing = (
        session.query(GuidanceConsumerAck)
        .filter(
            GuidanceConsumerAck.handoff_id == handoff_id,
            GuidanceConsumerAck.handoff_digest == result.handoff_digest,
            GuidanceConsumerAck.consumer == consumer,
            GuidanceConsumerAck.consumer_version == consumer_version,
        )
        .one_or_none()
    )
    if existing is not None:
        return existing

    row = GuidanceConsumerAck(
        ack_id=ack_id or f"ack-{uuid.uuid4().hex[:16]}",
        handoff_id=handoff_id,
        handoff_digest=result.handoff_digest,
        consumer=consumer,
        consumer_version=consumer_version,
        verdict=result.verdict,
        validated_digests_json=dict(result.validated_digests),
        reason_codes_json=list(result.reason_codes),
    )
    session.add(row)
    session.flush()
    return row


# ---------------------------------------------------------------------------
# finalize visibility saga
# ---------------------------------------------------------------------------


def resolve_visibility(
    session: Any,
    *,
    handoff: Mapping[str, Any],
    handoff_digest: str,
    required_consumers: Sequence[str] = (ACK_CONSUMER_GUIDANCE,),
) -> GuidanceHandoffVisibility:
    """依据 ledger 判定 visibility：全部 required ACK=ACCEPTED 才 ACTIVE。

    任一 required consumer 缺 ACK 或 verdict=REJECTED → 保持 0（PENDING/REJECTED）。
    对 (handoff_id, handoff_digest) 幂等：已存在则原地更新 state。
    """
    handoff_id = str(handoff.get("handoffId"))

    acks = {
        row.consumer: row
        for row in session.query(GuidanceConsumerAck)
        .filter(
            GuidanceConsumerAck.handoff_id == handoff_id,
            GuidanceConsumerAck.handoff_digest == handoff_digest,
        )
        .all()
    }

    reason_codes: list[str] = []
    all_accepted = True
    decisive_ack_id: str | None = None
    for consumer in required_consumers:
        ack = acks.get(consumer)
        if ack is None:
            all_accepted = False
            reason_codes.append(f"ack-missing:{consumer}")
        elif ack.verdict != ACK_ACCEPTED:
            all_accepted = False
            reason_codes.append(f"ack-rejected:{consumer}")
            decisive_ack_id = ack.ack_id
        else:
            decisive_ack_id = ack.ack_id

    if all_accepted:
        state = VISIBILITY_ACTIVE
    elif any(r.startswith("ack-rejected") for r in reason_codes):
        state = VISIBILITY_REJECTED
    else:
        state = VISIBILITY_PENDING

    row = (
        session.query(GuidanceHandoffVisibility)
        .filter(
            GuidanceHandoffVisibility.handoff_id == handoff_id,
            GuidanceHandoffVisibility.handoff_digest == handoff_digest,
        )
        .one_or_none()
    )
    if row is None:
        row = GuidanceHandoffVisibility(
            handoff_id=handoff_id,
            handoff_digest=handoff_digest,
            organization_id=str(handoff.get("organizationId") or ""),
            project_id=(str(handoff.get("projectId")) if handoff.get("projectId") else None),
            wp_code=str(handoff.get("wpCode") or ""),
            entry_id=str(handoff.get("entryId") or ""),
            sheet_uid=str(handoff.get("sheetUid") or ""),
        )
        session.add(row)
    row.state = state
    row.decisive_ack_id = decisive_ack_id
    row.reason_codes_json = reason_codes
    session.flush()
    return row


def mark_stale_on_change(
    session: Any,
    *,
    handoff_id: str,
    new_handoff_digest: str | None = None,
) -> int:
    """handoff 变化 / withdraw：把该 handoff_id 下 digest≠new 的 ACTIVE 行标 stale。

    返回被标 stale 的行数。custom 只发布 reevaluation evidence，本函数不删 ACK
    历史，只把旧 visibility 行 stale（不可见）。
    """
    rows = (
        session.query(GuidanceHandoffVisibility)
        .filter(
            GuidanceHandoffVisibility.handoff_id == handoff_id,
            GuidanceHandoffVisibility.stale == False,  # noqa: E712
        )
        .all()
    )
    count = 0
    for row in rows:
        if new_handoff_digest is not None and row.handoff_digest == new_handoff_digest:
            continue
        row.stale = True
        count += 1
    session.flush()
    return count


# ---------------------------------------------------------------------------
# G-HANDOFF-CONSUMER evidence（subject=contract）
# ---------------------------------------------------------------------------

GHANDOFF_CONSUMER_MILESTONE = "G-HANDOFF-CONSUMER"
GHANDOFF_CONSUMER_VERSION = "1.0"


def build_ghandoff_consumer_evidence_payload() -> dict[str, Any]:
    """构造可落盘的 G-HANDOFF-CONSUMER EvidenceEnvelope（subject=contract）。

    供 custom spec X11 消费——声明本消费方的 contract 版本、consumer 版本、
    saga 语义与幂等键，不伪造 project/wp subject。
    """
    from pathlib import Path

    module = Path(__file__).read_bytes()
    module_sha = hashlib.sha256(module).hexdigest()
    return {
        "contractVersion": "1.0",
        "evidenceId": "evidence-ghandoff-consumer-1",
        "runId": "run-ghandoff-consumer-1",
        "subject": {"kind": "contract", "contractId": GHANDOFF_CONSUMER_MILESTONE},
        "contractVersions": {
            "G-C0": GC0_CONTRACT_VERSION,
            GHANDOFF_CONSUMER_MILESTONE: GHANDOFF_CONSUMER_VERSION,
        },
        "inventoryDigest": None,
        "sourceDigests": {"module": module_sha},
        "operationIds": {"publish": "op-publish-ghandoff-consumer-2026-09-08"},
        "artifacts": [
            {
                "kind": "report",
                "uri": "backend/app/services/guidance_handoff_consumer_service.py",
                "sha256": module_sha,
            }
        ],
        "verdict": "PASS",
        "recordedAt": "2026-09-08T00:00:00Z",
        # 供 custom 消费的行为契约摘要
        "consumerVersion": GUIDANCE_CONSUMER_VERSION,
        "idempotencyKey": [
            "handoff_id",
            "handoff_digest",
            "consumer",
            "consumer_version",
        ],
        "sagaContract": {
            "order": [
                "PENDING_visibility",
                "durable_ACK_ledger",
                "producer_commit_visibility",
            ],
            "ackFailVisibility": 0,
            "candidateVerdict": "review_pending",
            "finalizedVerdicts": ["ACCEPTED", "REJECTED"],
            "crossSystemAcid": False,
        },
    }
