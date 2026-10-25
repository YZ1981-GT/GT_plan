"""Candidate guidance 预览 —— 消费 G-C0 candidate handoff variant（Task 9）。

Spec: custom-workpaper-template-ingestion-and-sync-closure
Requirements: 9.4, 9.5

## 严格 by-reference 消费 G-C0（Requirement 16.4 / design §1）

本模块**不**重定义 ``CustomGuidanceHandoff`` / ``SourceRef`` /
``TemplateAuthorityIdentity`` / ``GuidanceSection`` 任何 schema。它：

* 用 :func:`guidance_gc0_contract.validate_contract_version` 做 fail-closed 版本门；
* 用 :data:`guidance_gc0_contract.GC0_DISCRIMINATORS` 的 ``CustomGuidanceHandoff``
  与 ``TemplateAuthorityIdentity`` 的 ``phase`` 判别子，确认这是 **candidate**
  variant（而不是 finalized）；
* 拒绝任何 finalized-only 字段（``finalizationId`` / ``confirmedBy`` /
  ``confirmedAt``，含 top-level 与 authority-level）；
* 预览输出**永不**含 ``custom_confirmed`` 语义（Requirement 9.4）。

任何本地重定义 C0 top-level schema 由 ``test_gc0_reverse_dup_scan.py`` 的
``discover_local_dupes`` 反向扫描拦截。
"""
from __future__ import annotations

from typing import Any, Mapping

from app.services.guidance_gc0_contract import (
    GC0_DISCRIMINATORS,
    validate_contract_version,
)

__all__ = [
    "CandidateGuidanceError",
    "FINALIZED_ONLY_FIELDS",
    "build_candidate_guidance_preview",
]


class CandidateGuidanceError(ValueError):
    """guidance handoff 不是合法的 candidate variant（或伪造了 finalization）。"""


#: finalized-only 字段（top-level 与 authority-level 都禁止出现在 candidate）。
#: 与 test_guidance_gc0_conformance.test_req1_4_candidate_handoff_shape 同源。
FINALIZED_ONLY_FIELDS: tuple[str, ...] = (
    "finalizationId",
    "confirmedBy",
    "confirmedAt",
)


def build_candidate_guidance_preview(handoff: Mapping[str, Any]) -> dict[str, Any]:
    """校验并投影 candidate guidance handoff 为只读预览。

    步骤（全 fail-closed）:
      1. G-C0 版本门：``validate_contract_version`` 非 ACCEPT → 阻断；
      2. phase 判别子：必须等于 ``CustomGuidanceHandoff`` 的 candidate variant；
         authority.phase 同样必须是 candidate；
      3. 拒绝 finalized-only 字段（top-level + authority）；
      4. 投影 sections + sourceRefs（内容原样保留供只读展示，不做 confirmed）。

    返回的预览 dict 显式带 ``phase="candidate"`` 与 ``confirmed=False``，**绝不**
    产出 ``custom_confirmed`` 或 finalized 字段。
    """
    if not isinstance(handoff, Mapping):
        raise CandidateGuidanceError("handoff 必须是对象")

    decision = validate_contract_version(handoff, consumer_role="consumer")
    if not decision.is_accept:
        raise CandidateGuidanceError(
            f"G-C0 版本门未通过: {decision.outcome} "
            f"{[r.code for r in decision.reasons]}"
        )

    handoff_variants = GC0_DISCRIMINATORS["CustomGuidanceHandoff"]["variants"]
    candidate_variant = "candidate"
    # candidate_variant 必须是 C0 声明的合法 variant（防呆：常量漂移即抛）。
    if candidate_variant not in handoff_variants:
        raise CandidateGuidanceError(
            "G-C0 未声明 candidate handoff variant —— 契约漂移"
        )

    phase = handoff.get("phase")
    if phase != candidate_variant:
        raise CandidateGuidanceError(
            f"guidance 预览只接受 candidate handoff，收到 phase={phase!r}"
        )

    authority = handoff.get("authority")
    if not isinstance(authority, Mapping):
        raise CandidateGuidanceError("handoff.authority 缺失或非对象")
    if authority.get("phase") != candidate_variant:
        raise CandidateGuidanceError(
            f"authority 必须是 candidate phase，收到 {authority.get('phase')!r}"
        )

    # 3) 拒绝 finalized-only 字段（top-level + authority-level）。
    for fld in FINALIZED_ONLY_FIELDS:
        if fld in handoff:
            raise CandidateGuidanceError(
                f"candidate guidance 不得携带 finalized-only 字段 {fld!r}（top-level）"
            )
        if fld in authority:
            raise CandidateGuidanceError(
                f"candidate guidance.authority 不得携带 finalized-only 字段 {fld!r}"
            )

    sections = handoff.get("sections") or []
    projected_sections = [_project_section(s) for s in sections]

    return {
        "phase": candidate_variant,
        # 🔴 candidate 预览永不 confirmed（Requirement 9.4）。
        "confirmed": False,
        "completionStatus": "review_pending",
        "handoffId": handoff.get("handoffId"),
        "guidanceRevision": handoff.get("guidanceRevision"),
        "sections": projected_sections,
    }


def _project_section(section: Any) -> dict[str, Any]:
    if not isinstance(section, Mapping):
        raise CandidateGuidanceError("guidance section 必须是对象")
    refs = section.get("sourceRefs") or []
    return {
        "key": section.get("key"),
        "title": section.get("title"),
        "content": section.get("content"),
        "sourceRefs": [_project_source_ref(r) for r in refs],
        # 每段都是候选，绝不 confirmed。
        "completionStatus": "review_pending",
    }


def _project_source_ref(ref: Any) -> dict[str, Any]:
    if not isinstance(ref, Mapping):
        raise CandidateGuidanceError("sourceRef 必须是对象")
    return {
        "refId": ref.get("refId"),
        "locator": ref.get("locator"),
        "authorityDigest": ref.get("authorityDigest"),
        "contentDigest": ref.get("contentDigest"),
    }
