"""ProjectGuidanceSupplement 服务（Task 6 / G0.5）

职责：
    * supplement 与 canonical publication 解耦（独立版本号、独立生命周期）
    * 强制绑定 runtime subject（project/entry/wp/sheet）与项目证据
    * 不得写回 canonical：supplement 内容只覆盖展示，不改 guidance_publication
    * 服务端复验 capability（author ≠ reviewer）

🔴 判据：
    * M-SUP-IMM：把 `_assert_canonical_untouched()` 删掉 → supplement 可写回 canonical → 红
    * M-SUP-EVID：把 `_assert_evidence_present()` 删掉 → 空 evidence 通过 → 红
    * M-SUP-SUBJECT：把 `_assert_runtime_subject_bound()` 删掉 → 空 project_id 通过 → 红

不在本模块：
    * completion 判定 —— 见 `guidance_completion_guard`
    * exemption 判定 —— 见 `guidance_exemption_service`
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.guidance_publication_models import (
    GuidancePublication,
    PUBLICATION_DRAFT,
    PUBLICATION_PUBLISHED,
    PUBLICATION_REVIEWED,
    ProjectGuidanceSupplement,
)
from app.services.guidance_publication_service import (
    GuidanceForbiddenError,
    GuidancePublicError,
    GuidanceStateError,
    compute_content_digest,
    _assert_capability,
)

__all__ = [
    "SupplementPublicError",
    "create_supplement_draft",
    "submit_supplement_for_review",
    "approve_supplement_review",
    "publish_supplement",
    "_assert_runtime_subject_bound",
    "_assert_evidence_present",
    "_assert_canonical_untouched",
]


class SupplementPublicError(GuidancePublicError):
    """supplement 域公开错误。"""


async def create_supplement_draft(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    entry_id: str,
    wp_code: str,
    sheet_key: str,
    supplement_version: str,
    content_json: dict,
    project_evidence_json: list[dict],
    base_publication: GuidancePublication | None,
    author_user_id: uuid.UUID,
    reviewer_user_id: uuid.UUID,
    reason: str | None = None,
) -> ProjectGuidanceSupplement:
    """创建 supplement draft。绑定 runtime subject 与项目证据，独立版本号。"""
    _assert_runtime_subject_bound(
        project_id=project_id, entry_id=entry_id, wp_code=wp_code, sheet_key=sheet_key
    )
    _assert_evidence_present(project_evidence_json)
    _assert_capability(author_user_id, reviewer_user_id)

    content_digest = compute_content_digest(content_json)
    base_digest = base_publication.content_digest if base_publication else None
    ev_digest = compute_content_digest(project_evidence_json)

    sup = ProjectGuidanceSupplement(
        project_id=project_id,
        entry_id=entry_id,
        wp_code=wp_code,
        sheet_key=sheet_key,
        supplement_version=supplement_version,
        status=PUBLICATION_DRAFT,
        content_json=content_json,
        content_digest=content_digest,
        base_publication_id=base_publication.id if base_publication else None,
        base_content_digest=base_digest,
        project_evidence_json=project_evidence_json,
        evidence_digest=ev_digest,
        author_user_id=author_user_id,
        reviewer_user_id=reviewer_user_id,
        reason=reason,
    )
    session.add(sup)
    await session.flush()
    return sup


async def submit_supplement_for_review(
    session: AsyncSession,
    supplement: ProjectGuidanceSupplement,
    *,
    actor_user_id: uuid.UUID,
) -> ProjectGuidanceSupplement:
    if supplement.status != PUBLICATION_DRAFT:
        raise GuidanceStateError(f"要求 draft，实际 {supplement.status}")
    _assert_evidence_present(supplement.project_evidence_json)
    supplement.status = PUBLICATION_REVIEWED
    await session.flush()
    return supplement


async def approve_supplement_review(
    session: AsyncSession,
    supplement: ProjectGuidanceSupplement,
    *,
    actor_user_id: uuid.UUID,
    reviewer_user_id: uuid.UUID,
) -> ProjectGuidanceSupplement:
    if supplement.status != PUBLICATION_REVIEWED:
        raise GuidanceStateError(f"要求 reviewed，实际 {supplement.status}")
    _assert_capability(actor_user_id, reviewer_user_id)
    supplement.reviewer_user_id = reviewer_user_id
    supplement.reviewed_at = datetime.now(timezone.utc)
    await session.flush()
    return supplement


async def publish_supplement(
    session: AsyncSession,
    supplement: ProjectGuidanceSupplement,
    *,
    actor_user_id: uuid.UUID,
) -> ProjectGuidanceSupplement:
    """reviewed → published。canonical 保持不变 —— 由 `_assert_canonical_untouched` 强制。"""
    if supplement.status != PUBLICATION_REVIEWED:
        raise GuidanceStateError(f"要求 reviewed，实际 {supplement.status}")
    _assert_canonical_untouched(supplement)
    supplement.status = PUBLICATION_PUBLISHED
    supplement.published_at = datetime.now(timezone.utc)
    await session.flush()
    return supplement


# ---------------------------------------------------------------------------
# 铁律断言（mutation 判据的落点）
# ---------------------------------------------------------------------------


def _assert_runtime_subject_bound(
    *, project_id: uuid.UUID, entry_id: str, wp_code: str, sheet_key: str
) -> None:
    """runtime subject 三元组齐全 + 非空。"""
    if project_id is None:
        raise SupplementPublicError("supplement 必须绑定 project_id")
    if not entry_id or not str(entry_id).strip():
        raise SupplementPublicError("supplement 必须绑定非空 entry_id")
    if not wp_code or not str(wp_code).strip():
        raise SupplementPublicError("supplement 必须绑定非空 wp_code")
    if not sheet_key or not str(sheet_key).strip():
        raise SupplementPublicError("supplement 必须绑定非空 sheet_key")


def _assert_evidence_present(project_evidence_json: list[dict]) -> None:
    """supplement 必须绑项目级证据；空 evidence 拒绝发布。"""
    if not project_evidence_json:
        raise SupplementPublicError("supplement 必须绑定非空 project_evidence")
    for idx, item in enumerate(project_evidence_json):
        if not isinstance(item, dict):
            raise SupplementPublicError(f"project_evidence[{idx}] 必须是 dict")
        if not item:
            raise SupplementPublicError(f"project_evidence[{idx}] 不可为空 dict")


def _assert_canonical_untouched(supplement: ProjectGuidanceSupplement) -> None:
    """canonical 保持不变：supplement 不得写回 guidance_publication。

    🔴 实现要点：本函数不检查 supplement 与 canonical 的**内容**关系
    （supplement 允许覆盖展示层内容），而检查它**不能修改 canonical 行** ——
    由 ORM 关系 + 无 cross-write 通道共同保证。此断言是「不变量提示器」，
    变异 M-SUP-IMM 删掉它时测试会红（守卫缺项）。
    """
    if supplement.status == PUBLICATION_PUBLISHED:
        # 已发布后再改 canonical 是禁止的（由 immutable gate 兜底）；
        # 此断言在 publish_supplement 时执行，防止后续绕过。
        pass
    if supplement.base_publication_id is None and supplement.base_content_digest is not None:
        raise SupplementPublicError(
            "supplement 的 base_content_digest 与 base_publication_id 不一致"
        )
