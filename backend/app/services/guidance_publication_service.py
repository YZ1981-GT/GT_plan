"""Guidance 发布生命周期服务（Task 6 / G0.5）

职责：
    * draft → reviewed → published 状态迁移（含 supersede / withdraw / restore）
    * immutable gate：published 后拒绝任何 content_json 变更
    * capability 前置：actor ≠ reviewer，服务端复验，非仅 UI 隐藏按钮
    * 事件留痕：每次迁移写一行 guidance_publication_event（diff/digests/reason）

🔴 判据（mutation 变异必须抓得住）：
    * M-IMM：把 `_assert_mutable()` 改成 no-op → published 后可改内容 → 测试红
    * M-AUTH：删掉 `actor != reviewer` 断言 → 自检可发布 → 测试红
    * M-STATE：`publish()` 只改 status 不写 event → event 缺行 → 测试红
    * M-DIGEST：`_digest()` 退化为 `str(...)` → digest 不再是 sha256 → 测试红

不在本模块做：
    * supplement 与 canonical 关系判断 —— 见 `project_guidance_supplement_service`
    * exemption 判定 —— 见 `guidance_exemption_service`
    * completion 判定 —— 见 `guidance_completion_guard`
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.guidance_publication_models import (
    EVENT_DRAFTED,
    EVENT_PUBLISHED,
    EVENT_RESTORED,
    EVENT_REVIEW_APPROVED,
    EVENT_REVIEW_REJECTED,
    EVENT_SUBMITTED_FOR_REVIEW,
    EVENT_SUPERSEDED,
    EVENT_WITHDRAWN,
    PUBLICATION_DRAFT,
    PUBLICATION_PUBLISHED,
    PUBLICATION_REVIEWED,
    PUBLICATION_WITHDRAWN,
    REVIEW_APPROVED,
    REVIEW_REJECTED,
    GuidancePublication,
    GuidancePublicationEvent,
)

__all__ = [
    "GuidancePublicError",
    "GuidanceForbiddenError",
    "GuidanceImmutableError",
    "GuidanceStateError",
    "compute_content_digest",
    "create_draft",
    "submit_for_review",
    "approve_review",
    "reject_review",
    "publish",
    "withdraw",
    "restore",
    "supersede",
    "_assert_mutable",
    "_assert_capability",
    "_transition",
]


class GuidancePublicError(Exception):
    """公开错误基类（调用方可映射为 HTTP 4xx）。"""


class GuidanceForbiddenError(GuidancePublicError):
    """权限/capability 不足 —— 服务端拒绝，非仅隐藏按钮。"""


class GuidanceImmutableError(GuidancePublicError):
    """published 后试图修改内容。"""


class GuidanceStateError(GuidancePublicError):
    """状态迁移非法（如 draft 直接 publish）。"""


class ReviewContext:
    """actor/reviewer 分离的最小上下文。"""

    __slots__ = ("actor_user_id", "reviewer_user_id")

    def __init__(self, actor_user_id: uuid.UUID, reviewer_user_id: uuid.UUID | None = None) -> None:
        self.actor_user_id = actor_user_id
        self.reviewer_user_id = reviewer_user_id


# ---------------------------------------------------------------------------
# Digests（mutation C01 判据：content 与 source 必须解耦）
# ---------------------------------------------------------------------------


def _digest(payload: Any) -> str:
    """稳定 sha256 —— JSON 序列化排序保证同内容得同 digest。"""
    if isinstance(payload, (dict, list, tuple)):
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    else:
        canonical = str(payload)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_content_digest(content_json: dict) -> str:
    """对 content_json 计算 content_digest。"""
    return _digest(content_json)


def compute_source_digest(source_material: Any) -> str:
    """对源材料计算 source_digest。与 content_digest 不同源。"""
    return _digest(source_material)


# ---------------------------------------------------------------------------
# Capability / immutable gate（服务端复验，非仅 UI 隐藏）
# ---------------------------------------------------------------------------


def _assert_capability(actor: uuid.UUID, reviewer: uuid.UUID) -> None:
    """actor 与 reviewer 必须不同 —— capability 前置复验。"""
    if actor == reviewer:
        raise GuidanceForbiddenError(
            "actor 与 reviewer 必须分离（服务端复验，禁止自检自发布）"
        )


def _assert_mutable(pub: GuidancePublication, *, operation: str) -> None:
    """published 后 content_json 冻结。"""
    if pub.status == PUBLICATION_PUBLISHED:
        raise GuidanceImmutableError(
            f"publication {pub.id} 已 published，禁止操作：{operation}"
        )


# ---------------------------------------------------------------------------
# 生命周期迁移
# ---------------------------------------------------------------------------


async def create_draft(
    session: AsyncSession,
    *,
    lineage_id: str,
    version: str,
    wp_code: str,
    sheet_key: str,
    content_json: dict,
    source_refs_json: list,
    source_digest: str | None = None,
    schema_ref: str | None = None,
    author_user_id: uuid.UUID,
    reviewer_user_id: uuid.UUID,
    reason: str | None = None,
) -> GuidancePublication:
    """创建 draft 版本。legacy/template/BCD 抽取只导入此状态。"""
    _assert_capability(actor_user_id, reviewer_user_id)
    content_digest = compute_content_digest(content_json)
    pub = GuidancePublication(
        lineage_id=lineage_id,
        version=version,
        wp_code=wp_code,
        sheet_key=sheet_key,
        status=PUBLICATION_DRAFT,
        content_json=content_json,
        source_refs_json=source_refs_json,
        content_digest=content_digest,
        source_digest=source_digest,
        schema_ref=schema_ref,
        author_user_id=actor_user_id,
        reviewer_user_id=reviewer_user_id,
        reason=reason,
    )
    session.add(pub)
    session.add(
        GuidancePublicationEvent(
            publication_id=pub.id,
            event_type=EVENT_DRAFTED,
            from_status=None,
            to_status=PUBLICATION_DRAFT,
            actor_user_id=actor_user_id,
            diff_json={"op": "drafted", "sections": _section_keys(content_json)},
            before_digest=None,
            after_digest=content_digest,
            reason=reason,
        )
    )
    await session.flush()
    return pub


async def submit_for_review(
    session: AsyncSession,
    publication: GuidancePublication,
    *,
    actor_user_id: uuid.UUID,
    reason: str | None = None,
) -> GuidancePublicationEvent:
    """draft → reviewed（提交复核）。内容变更走 update_draft，此处只推进状态。"""
    return await _transition(
        session,
        publication,
        EVENT_SUBMITTED_FOR_REVIEW,
        from_status=PUBLICATION_DRAFT,
        to_status=PUBLICATION_REVIEWED,
        actor_user_id=actor_user_id,
        reviewer_user_id=None,
        reason=reason,
        content_changed=False,
    )


async def update_draft(
    session: AsyncSession,
    publication: GuidancePublication,
    *,
    new_content_json: dict,
    actor_user_id: uuid.UUID,
    reason: str | None = None,
) -> GuidancePublication:
    """draft/reviewed 阶段允许改内容；published 后服务端拒绝。"""
    _assert_mutable(publication, operation="update_draft")
    before_digest = publication.content_digest
    before_content = publication.content_json
    publication.content_json = new_content_json
    publication.content_digest = compute_content_digest(new_content_json)
    session.add(
        GuidancePublicationEvent(
            publication_id=publication.id,
            event_type="draft_edited",
            from_status=publication.status,
            to_status=publication.status,
            actor_user_id=actor_user_id,
            diff_json={
                "op": "draft_edited",
                "sections_added": _section_keys(new_content_json) - _section_keys(before_content),
                "sections_removed": _section_keys(before_content) - _section_keys(new_content_json),
            },
            before_digest=before_digest,
            after_digest=publication.content_digest,
            reason=reason,
        )
    )
    await session.flush()
    return publication


async def approve_review(
    session: AsyncSession,
    publication: GuidancePublication,
    *,
    actor_user_id: uuid.UUID,
    reviewer_user_id: uuid.UUID,
    reason: str | None = None,
) -> GuidancePublicationEvent:
    """复核通过：review_status = approved，状态仍为 reviewed，等 publish() 推进。"""
    _assert_capability(actor_user_id, reviewer_user_id)
    if publication.status != PUBLICATION_REVIEWED:
        raise GuidanceStateError(
            f"approve_review 要求 status=reviewed，实际 {publication.status}"
        )
    publication.review_status = REVIEW_APPROVED
    publication.reviewer_user_id = reviewer_user_id
    publication.reviewed_at = datetime.now(timezone.utc)
    ev = GuidancePublicationEvent(
        publication_id=publication.id,
        event_type=EVENT_REVIEW_APPROVED,
        from_status=PUBLICATION_REVIEWED,
        to_status=PUBLICATION_REVIEWED,
        actor_user_id=actor_user_id,
        reviewer_user_id=reviewer_user_id,
        diff_json={"op": "review_approved", "review_status": REVIEW_APPROVED},
        before_digest=publication.content_digest,
        after_digest=publication.content_digest,
        reason=reason,
    )
    session.add(ev)
    await session.flush()
    return ev


async def reject_review(
    session: AsyncSession,
    publication: GuidancePublication,
    *,
    actor_user_id: uuid.UUID,
    reviewer_user_id: uuid.UUID,
    reason: str | None = None,
) -> GuidancePublicationEvent:
    """复核驳回：review_status = rejected，状态仍为 reviewed。"""
    _assert_capability(actor_user_id, reviewer_user_id)
    if publication.status != PUBLICATION_REVIEWED:
        raise GuidanceStateError(
            f"reject_review 要求 status=reviewed，实际 {publication.status}"
        )
    publication.review_status = REVIEW_REJECTED
    publication.reviewer_user_id = reviewer_user_id
    publication.reviewed_at = datetime.now(timezone.utc)
    ev = GuidancePublicationEvent(
        publication_id=publication.id,
        event_type=EVENT_REVIEW_REJECTED,
        from_status=PUBLICATION_REVIEWED,
        to_status=PUBLICATION_REVIEWED,
        actor_user_id=actor_user_id,
        reviewer_user_id=reviewer_user_id,
        diff_json={"op": "review_rejected", "review_status": REVIEW_REJECTED},
        before_digest=publication.content_digest,
        after_digest=publication.content_digest,
        reason=reason,
    )
    session.add(ev)
    await session.flush()
    return ev


async def publish(
    session: AsyncSession,
    publication: GuidancePublication,
    *,
    actor_user_id: uuid.UUID,
    reason: str | None = None,
) -> GuidancePublicationEvent:
    """reviewed + approved → published（冻结内容）。"""
    if publication.status != PUBLICATION_REVIEWED:
        raise GuidanceStateError(f"publish 要求 status=reviewed，实际 {publication.status}")
    if publication.review_status != REVIEW_APPROVED:
        raise GuidanceStateError(
            f"publish 要求 review_status=approved，实际 {publication.review_status}"
        )
    _assert_capability(actor_user_id, publication.reviewer_user_id)
    ev = await _transition(
        session,
        publication,
        EVENT_PUBLISHED,
        from_status=PUBLICATION_REVIEWED,
        to_status=PUBLICATION_PUBLISHED,
        actor_user_id=actor_user_id,
        reviewer_user_id=publication.reviewer_user_id,
        reason=reason,
        content_changed=False,
        set_published_at=True,
    )
    return ev


async def withdraw(
    session: AsyncSession,
    publication: GuidancePublication,
    *,
    actor_user_id: uuid.UUID,
    reason: str,
) -> GuidancePublicationEvent:
    """published → withdrawn（内容不动，只撤出 active 集合）。reason 必填。"""
    if publication.status != PUBLICATION_PUBLISHED:
        raise GuidanceStateError(
            f"withdraw 要求 status=published，实际 {publication.status}"
        )
    if not reason:
        raise GuidancePublicError("withdraw 必须提供 reason")
    ev = await _transition(
        session,
        publication,
        EVENT_WITHDRAWN,
        from_status=PUBLICATION_PUBLISHED,
        to_status=PUBLICATION_WITHDRAWN,
        actor_user_id=actor_user_id,
        reviewer_user_id=None,
        reason=reason,
        content_changed=False,
        set_withdrawn_at=True,
        withdrawn_reason=reason,
    )
    return ev


async def restore(
    session: AsyncSession,
    publication: GuidancePublication,
    *,
    actor_user_id: uuid.UUID,
    reason: str | None = None,
) -> GuidancePublicationEvent:
    """withdrawn → published（撤销撤回）。内容不变。"""
    if publication.status != PUBLICATION_WITHDRAWN:
        raise GuidanceStateError(
            f"restore 要求 status=withdrawn，实际 {publication.status}"
        )
    ev = await _transition(
        session,
        publication,
        EVENT_RESTORED,
        from_status=PUBLICATION_WITHDRAWN,
        to_status=PUBLICATION_PUBLISHED,
        actor_user_id=actor_user_id,
        reviewer_user_id=publication.reviewer_user_id,
        reason=reason,
        content_changed=False,
        clear_withdrawn_at=True,
    )
    return ev


async def supersede(
    session: AsyncSession,
    old_publication: GuidancePublication,
    new_publication: GuidancePublication,
    *,
    actor_user_id: uuid.UUID,
    reason: str | None = None,
) -> GuidancePublicationEvent:
    """用 new_publication 取代 old_publication（old 保留留痕，从 active 集合移除）。"""
    if old_publication.status != PUBLICATION_PUBLISHED:
        raise GuidanceStateError(
            f"supersede 要求 old.status=published，实际 {old_publication.status}"
        )
    if new_publication.status != PUBLICATION_PUBLISHED:
        raise GuidanceStateError(
            f"supersede 要求 new.status=published，实际 {new_publication.status}"
        )
    old_publication.superseded_by = new_publication.id
    ev = GuidancePublicationEvent(
        publication_id=old_publication.id,
        event_type=EVENT_SUPERSEDED,
        from_status=PUBLICATION_PUBLISHED,
        to_status=PUBLICATION_PUBLISHED,
        actor_user_id=actor_user_id,
        reviewer_user_id=None,
        diff_json={"op": "superseded", "superseded_by": str(new_publication.id)},
        before_digest=old_publication.content_digest,
        after_digest=new_publication.content_digest,
        reason=reason,
    )
    session.add(ev)
    await session.flush()
    return ev


# ---------------------------------------------------------------------------
# 内部 helper
# ---------------------------------------------------------------------------


def _section_keys(content_json: dict) -> set[str]:
    """提取 content_json 的顶层 section key，供 diff 与 completion 判据。"""
    return set(content_json.keys()) if isinstance(content_json, dict) else set()


async def _transition(
    session: AsyncSession,
    publication: GuidancePublication,
    event_type: str,
    *,
    from_status: str,
    to_status: str,
    actor_user_id: uuid.UUID,
    reviewer_user_id: uuid.UUID | None,
    reason: str | None = None,
    content_changed: bool = False,
    set_published_at: bool = False,    set_withdrawn_at: bool = False,
    clear_withdrawn_at: bool = False,
    withdrawn_reason: str | None = None,
) -> GuidancePublicationEvent:
    """统一状态迁移 helper：改状态、写事件、flush。"""
    # 状态迁移本身不改 content_json，所以 immutable gate 不在这里触发。
    # 内容变更走 update_draft() / update_published()，后者由 _assert_mutable 拒绝。
    if publication.status != from_status:
        raise GuidanceStateError(
            f"{event_type} 要求 status={from_status}，实际 {publication.status}"
        )
    before_digest = publication.content_digest
    publication.status = to_status
    if set_published_at:
        publication.published_at = datetime.now(timezone.utc)
    if set_withdrawn_at:
        publication.withdrawn_at = datetime.now(timezone.utc)
        publication.withdrawn_reason = withdrawn_reason
    if clear_withdrawn_at:
        publication.withdrawn_at = None
        publication.withdrawn_reason = None
    ev = GuidancePublicationEvent(
        publication_id=publication.id,
        event_type=event_type,
        from_status=from_status,
        to_status=to_status,
        actor_user_id=actor_user_id,
        reviewer_user_id=reviewer_user_id,
        diff_json={"op": event_type, "from": from_status, "to": to_status},
        before_digest=before_digest,
        after_digest=publication.content_digest,
        reason=reason,
    )
    session.add(ev)
    await session.flush()
    return ev
