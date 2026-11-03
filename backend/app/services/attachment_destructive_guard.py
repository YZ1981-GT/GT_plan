"""附件破坏性操作守卫（spec attachment-security-baseline 需求 4，ADR-ASB-05）。

删除（进回收站）与回收站永久删除共用一组判定，任一不过都不改库：
- 所属项目已归档 ⇒ 423（复用 ``deps._check_project_not_archived``，与项目权限同一实现；对管理员同样生效）；
- 附件或其治理版本处于有效法定保全 ⇒ 423 ``LEGAL_HOLD_ACTIVE``（复用 ``RetentionLegalHoldService.authorize_destructive``，
  任何角色都不能绕过）；
- 仍被底稿、函证、证据链接、溯源关联或业务引用 ⇒ 409，列出各类引用数（先解除关联再删）。

改造前：删除只判成员级别；回收站三条永久删除路径（单条 / 批量 / 清空）都不查保全与引用，管理员直接放行不判归档。
保全判定的裸 SQL 按 ``str(uuid)`` 绑定，SQLite 上恒不命中 ⇒ 保全用例只能在真 PG 上测。
"""
from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import deps
from app.models.attachment_lineage_model import AttachmentLineage
from app.models.attachment_models import Attachment, AttachmentWorkingPaper
from app.models.confirmation_models import ConfirmationAttachmentLink
from app.models.core import User
from app.models.evidence_governance_models import AttachmentVersion
from app.models.wp_optimization_models import EvidenceLink

#: 引用类别 → 中文名（409 文案与回执用）
REFERENCE_LABELS: dict[str, str] = {
    "workpaper_links": "底稿关联",
    "confirmation_links": "函证挂载",
    "evidence_links": "证据链接",
    "lineage_links": "溯源关联",
    "business_reference": "业务引用",
}
#: ``reference_type`` 指向底稿或函证时算业务引用（与关联写入方同口径）
_REFERENCE_TYPES = frozenset({"working_paper", "confirmation_list"})

#: 批量 / 清空时跳过原因 → 中文
SKIP_REASONS: dict[str, str] = {
    "archived": "所属项目已归档",
    "legal_hold": "处于法定保全中",
    "referenced": "仍被引用",
}

LEGAL_HOLD_DETAIL = {"error_code": "LEGAL_HOLD_ACTIVE", "message": "附件处于法定保全中，不能删除"}


async def assert_project_writable(db: AsyncSession, project_id: UUID, user: User) -> None:
    """所属项目已归档 ⇒ 423（与 ``assert_project_permission`` 的归档判定同一函数）。"""
    await deps._check_project_not_archived(db, project_id, user, "edit")


async def count_references(db: AsyncSession, attachment: Attachment) -> dict[str, int]:
    aid = attachment.id

    async def _count(stmt) -> int:
        return int((await db.execute(stmt)).scalar_one() or 0)

    counts = {
        "workpaper_links": await _count(
            sa.select(sa.func.count()).select_from(AttachmentWorkingPaper)
            .where(AttachmentWorkingPaper.attachment_id == aid)),
        "confirmation_links": await _count(
            sa.select(sa.func.count()).select_from(ConfirmationAttachmentLink).where(sa.or_(
                ConfirmationAttachmentLink.attachment_id == aid,
                ConfirmationAttachmentLink.paired_outbound_attachment_id == aid,
            ))),
        "evidence_links": await _count(
            sa.select(sa.func.count()).select_from(EvidenceLink).where(EvidenceLink.attachment_id == aid)),
        "lineage_links": await _count(
            sa.select(sa.func.count()).select_from(AttachmentLineage).where(AttachmentLineage.attachment_id == aid)),
        "business_reference": int(
            attachment.reference_id is not None and attachment.reference_type in _REFERENCE_TYPES),
    }
    return counts


def references_detail(counts: dict[str, int]) -> dict:
    parts = "、".join(f"{REFERENCE_LABELS[k]} {v}" for k, v in counts.items() if v)
    return {
        "error_code": "ATTACHMENT_IN_USE",
        "message": f"附件仍被引用（{parts}），请先解除关联再删除",
        "references": {k: v for k, v in counts.items() if v},
    }


async def is_under_legal_hold(db: AsyncSession, attachment: Attachment, *, actor_role: str, operation: str) -> bool:
    """附件节点或其任一治理版本节点处于有效保全 ⇒ True（判定交给治理侧 ``authorize_destructive``）。"""
    from app.services.evidence_governance.frozen_contracts import EvidenceErrorCode, EvidenceGovernanceError
    from app.services.evidence_governance.retention_legal_hold_service import RetentionLegalHoldService

    version_ids = (await db.execute(
        sa.select(AttachmentVersion.id).where(AttachmentVersion.attachment_id == attachment.id)
    )).scalars().all()
    nodes = [("attachment", attachment.id), *(("attachment_version", vid) for vid in version_ids)]
    service = RetentionLegalHoldService(db)
    for node_type, node_id in nodes:
        try:
            await service.authorize_destructive(
                actor_role=actor_role, operation=operation, project_id=attachment.project_id,
                node_type=node_type, node_id=str(node_id),
            )
        except EvidenceGovernanceError as exc:
            if exc.error_code == EvidenceErrorCode.LEGAL_HOLD_ACTIVE:
                return True
            raise
    return False


def _role(user: User) -> str:
    return getattr(user.role, "value", str(user.role))


async def assert_destructible(db: AsyncSession, user: User, attachment: Attachment, *, operation: str) -> None:
    """删除 / 永久删除前的三项判定（归档 423 → 保全 423 → 引用 409）。"""
    await assert_project_writable(db, attachment.project_id, user)
    if await is_under_legal_hold(db, attachment, actor_role=_role(user), operation=operation):
        raise HTTPException(status_code=423, detail=LEGAL_HOLD_DETAIL)
    counts = await count_references(db, attachment)
    if any(counts.values()):
        raise HTTPException(status_code=409, detail=references_detail(counts))


async def partition_purgeable(
    db: AsyncSession, user: User, attachments: Iterable[Attachment],
) -> tuple[list[Attachment], dict[str, list[Attachment]]]:
    """批量 / 清空用：返回（可永久删除的附件，按原因分组的跳过附件）。判定与单条相同。"""
    purgeable: list[Attachment] = []
    skipped: dict[str, list[Attachment]] = {reason: [] for reason in SKIP_REASONS}
    archived: dict[UUID, bool] = {}
    for att in attachments:
        if att.project_id not in archived:
            try:
                await assert_project_writable(db, att.project_id, user)
                archived[att.project_id] = False
            except HTTPException as exc:
                if exc.status_code != 423:
                    raise
                archived[att.project_id] = True
        if archived[att.project_id]:
            skipped["archived"].append(att)
        elif await is_under_legal_hold(db, att, actor_role=_role(user), operation="purge"):
            skipped["legal_hold"].append(att)
        elif any((await count_references(db, att)).values()):
            skipped["referenced"].append(att)
        else:
            purgeable.append(att)
    return purgeable, skipped


def skipped_summary(skipped: dict[str, list[Attachment]]) -> dict[str, int]:
    return {reason: len(rows) for reason, rows in skipped.items() if rows}
