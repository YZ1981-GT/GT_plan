"""Evidence Governance Pydantic 枚举/schema —— Task 2.5 (Wave 1)。

Spec: attachment-ocr-ai-evidence-governance-hardening
Requirements: R1, R3, R5, R6, R14
Design: §Data Models(actor XOR), §4.4(EvidenceRef status), §4.5(OCR enum), §4.1(legacy resolution)

**单一真源铁律**：本模块的所有枚举值集合都直接从冻结契约
``app.services.evidence_governance.contracts`` 派生，**不得 fork / 复制字面量**。
``OcrState`` / ``LegacyResolutionKind`` 已在 contracts 中定义为 ``str, Enum``，此处直接
re-export；``ActorType`` / ``OcrFieldDecision`` / ``EvidenceRefStatus`` 由 contracts 的
frozenset 动态构建，并在 import 期用断言锁定「枚举值集合 == 冻结集合」，任何漂移在
import/测试期立即暴露。

供 Wave 2+ 的 facade / API / service 层做请求校验与响应序列化时复用，避免各处重复
硬编码状态字面量（这正是 Task 1.3 冻结契约要消除的漂移源）。
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

# OcrState / LegacyResolutionKind 已是 str Enum，直接 re-export（不 fork）。
from app.services.evidence_governance.contracts import (
    ACTOR_TYPES,
    EVIDENCE_REF_STATUSES,
    LegacyResolutionKind,
    OCR_FIELD_DECISIONS,
    OCR_WRITEBACK_ELIGIBLE_DECISIONS,
    OcrState,
)

__all__ = [
    "OcrState",
    "LegacyResolutionKind",
    "ActorType",
    "OcrFieldDecision",
    "EvidenceRefStatus",
    "ActorRef",
    "assert_enum_matches_frozen_contracts",
]


def _enum_from_frozenset(name: str, values: frozenset[str]) -> type[Enum]:
    """由冻结 frozenset 构建 ``str, Enum``；成员名 = 值（清洗为合法标识符）。"""
    members = {v.replace("-", "_"): v for v in sorted(values)}
    return Enum(name, members, type=str)  # type: ignore[return-value]


# ── 由冻结契约动态构建（值集合与 contracts 严格一致，禁止 fork）─────────────────
ActorType = _enum_from_frozenset("ActorType", ACTOR_TYPES)
OcrFieldDecision = _enum_from_frozenset("OcrFieldDecision", OCR_FIELD_DECISIONS)
EvidenceRefStatus = _enum_from_frozenset("EvidenceRefStatus", EVIDENCE_REF_STATUSES)


def assert_enum_matches_frozen_contracts() -> None:
    """断言本模块每个枚举的值集合 == contracts 冻结集合（单一真源守卫）。

    在 import 期与契约测试中调用；任一漂移即 raise，杜绝「Pydantic 层悄悄 fork
    了状态字面量」的隐患。
    """
    from app.services.evidence_governance.contracts import OCR_STATES

    assert {m.value for m in OcrState} == set(OCR_STATES), "OcrState drift"
    assert {m.value for m in ActorType} == set(ACTOR_TYPES), "ActorType drift"
    assert {m.value for m in OcrFieldDecision} == set(OCR_FIELD_DECISIONS), "OcrFieldDecision drift"
    assert {m.value for m in EvidenceRefStatus} == set(EVIDENCE_REF_STATUSES), "EvidenceRefStatus drift"
    assert {m.value for m in LegacyResolutionKind} == {
        "root",
        "current_version",
        "historical_version",
    }, "LegacyResolutionKind drift"
    # writeback-eligible ⊂ 全部决定，且不含 rejected（P12）
    assert set(OCR_WRITEBACK_ELIGIBLE_DECISIONS) < set(OCR_FIELD_DECISIONS)
    assert "rejected" not in OCR_WRITEBACK_ELIGIBLE_DECISIONS


class ActorRef(BaseModel):
    """actor XOR 的 Pydantic 表达（design §Data Models）。

    校验规则与 ``contracts.validate_actor`` 一致：user ⇒ 仅 user_id；service ⇒ 仅
    service_identity_id；禁止匿名（actor_type 必填）。
    """

    actor_type: ActorType
    actor_user_id: str | None = Field(default=None)
    actor_service_identity_id: str | None = Field(default=None)

    def validate_xor(self) -> str | None:
        """返回 None 表示满足 XOR + no-anonymous，否则返回失败原因。"""
        from app.services.evidence_governance.contracts import validate_actor

        return validate_actor(
            self.actor_type.value, self.actor_user_id, self.actor_service_identity_id
        )


# import 期即锁定单一真源（漂移立即暴露）。
assert_enum_matches_frozen_contracts()
