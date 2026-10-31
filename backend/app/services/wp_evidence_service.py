"""底稿证据链管理服务（``evidence_links``：底稿表页 / 单元格 / 行槽位 → 附件 → 页码）

- 链接可带凭证键（凭证检查行的原件按凭证身份挂，spec attachment-voucher-evidence-binding）：同一（底稿, 凭证, 附件,
  位置）只一条，重复请求返回已有的；
- 列表带附件元数据，附件已软删的不返回；
- 新链接只能挂本底稿已有的附件（统一视图任一来源，spec attachment-evidence-intake 需求 3.2）；
- 删除按路径底稿限定；解除整稿关联时连带删除本底稿链接（需求 4.2）；
- 证据充分性检查（必做程序有附件）。
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment_models import Attachment
from app.models.wp_optimization_models import EvidenceLink, WorkpaperProcedure

logger = logging.getLogger(__name__)


class WpEvidenceService:
    """证据链管理服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ─── 查询 ────────────────────────────────────────────────────────────────

    async def list_links(
        self, wp_id: UUID, *, sheet_name: str | None = None, cell_ref: str | None = None,
    ) -> list[dict]:
        """底稿证据链接 + 附件元数据（新→旧）。"""
        stmt = (
            sa.select(EvidenceLink, Attachment)
            .join(Attachment, Attachment.id == EvidenceLink.attachment_id)
            .where(EvidenceLink.wp_id == wp_id, Attachment.is_deleted == sa.false())
            .order_by(EvidenceLink.created_at.desc(), EvidenceLink.id)
        )
        if sheet_name is not None:
            stmt = stmt.where(EvidenceLink.sheet_name == sheet_name)
        if cell_ref is not None:
            stmt = stmt.where(EvidenceLink.cell_ref == cell_ref)
        rows = (await self.db.execute(stmt)).all()
        return [{**self._to_dict(link), "attachment": self._attachment_brief(att)} for link, att in rows]

    async def assert_attachments_in_wp(self, wp: Any, attachment_ids: Iterable[UUID]) -> None:
        """每个附件须未删除、与底稿同项目且已在本底稿（整稿关联 / reference / 证据链接 / 函证挂载），否则 404。"""
        from app.services.attachment_ocr_writeback import is_attachment_linked_to_wp

        for att_id in dict.fromkeys(attachment_ids):
            project_id = (await self.db.execute(
                sa.select(Attachment.project_id).where(Attachment.id == att_id, Attachment.is_deleted == sa.false())
            )).scalar_one_or_none()
            in_wp = project_id == wp.project_id and (
                await is_attachment_linked_to_wp(self.db, att_id, wp.id)
                or await self._confirmation_linked(att_id, wp.id)
            )
            if not in_wp:
                raise HTTPException(status_code=404, detail="附件不存在或不在本底稿，请先上传或在附件面板关联")

    async def _confirmation_linked(self, attachment_id: UUID, wp_id: UUID) -> bool:
        from app.models.confirmation_models import Confirmation, ConfirmationAttachmentLink

        count = (await self.db.execute(
            sa.select(sa.func.count())
            .select_from(ConfirmationAttachmentLink)
            .join(Confirmation, Confirmation.id == ConfirmationAttachmentLink.confirmation_id)
            .where(ConfirmationAttachmentLink.attachment_id == attachment_id, Confirmation.wp_id == wp_id)
        )).scalar()
        return int(count or 0) > 0

    # ─── 创建 ────────────────────────────────────────────────────────────────

    async def create_link(
        self,
        *,
        wp_id: UUID,
        attachment_id: UUID,
        created_by: UUID,
        sheet_name: str | None = None,
        cell_ref: str | None = None,
        page_ref: str | None = None,
        evidence_type: str | None = None,
        check_conclusion: str | None = None,
        voucher_key: str | None = None,
    ) -> dict:
        """创建单条证据链接（只 flush）。带凭证键的链接按（底稿, 凭证, 附件, 位置）幂等，见 :meth:`create_voucher_link`。"""
        if voucher_key is not None:
            link, _existed = await self.create_voucher_link(
                wp_id=wp_id, attachment_id=attachment_id, created_by=created_by, voucher_key=voucher_key,
                sheet_name=sheet_name, cell_ref=cell_ref, page_ref=page_ref,
                evidence_type=evidence_type, check_conclusion=check_conclusion,
            )
            return link
        link = EvidenceLink(
            id=uuid.uuid4(),
            wp_id=wp_id,
            sheet_name=sheet_name,
            cell_ref=cell_ref,
            attachment_id=attachment_id,
            page_ref=page_ref,
            evidence_type=evidence_type,
            check_conclusion=check_conclusion,
            created_by=created_by,
        )
        self.db.add(link)
        await self.db.flush()
        return self._to_dict(link)

    async def _voucher_link(
        self, wp_id: UUID, voucher_key: str, attachment_id: UUID, sheet_name: str | None, cell_ref: str | None,
    ) -> EvidenceLink | None:
        return (await self.db.execute(
            sa.select(EvidenceLink).where(
                EvidenceLink.wp_id == wp_id, EvidenceLink.voucher_key == voucher_key,
                EvidenceLink.attachment_id == attachment_id,
                sa.func.coalesce(EvidenceLink.sheet_name, "") == (sheet_name or ""),
                sa.func.coalesce(EvidenceLink.cell_ref, "") == (cell_ref or ""),
            ).limit(1)
        )).scalar_one_or_none()

    async def create_voucher_link(
        self,
        *,
        wp_id: UUID,
        attachment_id: UUID,
        created_by: UUID,
        voucher_key: str,
        sheet_name: str | None = None,
        cell_ref: str | None = None,
        page_ref: str | None = None,
        evidence_type: str | None = None,
        check_conclusion: str | None = None,
    ) -> tuple[dict, bool]:
        """带凭证键的链接（只 flush）：同一（底稿, 凭证, 附件, 位置）已有 ⇒ 返回已有的（第二项 True）。

        先查再插；并发下撞唯一索引 ``uq_evidence_links_voucher_position`` 时回滚到保存点再读回（spec
        attachment-voucher-evidence-binding 需求 1.3）。
        """
        existing = await self._voucher_link(wp_id, voucher_key, attachment_id, sheet_name, cell_ref)
        if existing is not None:
            return self._to_dict(existing), True
        link = EvidenceLink(
            id=uuid.uuid4(), wp_id=wp_id, sheet_name=sheet_name, cell_ref=cell_ref, attachment_id=attachment_id,
            page_ref=page_ref, evidence_type=evidence_type, check_conclusion=check_conclusion,
            created_by=created_by, voucher_key=voucher_key,
        )
        try:
            async with self.db.begin_nested():
                self.db.add(link)
                await self.db.flush()
        except IntegrityError:
            existing = await self._voucher_link(wp_id, voucher_key, attachment_id, sheet_name, cell_ref)
            if existing is None:
                raise
            return self._to_dict(existing), True
        return self._to_dict(link), False

    async def batch_link(self, *, wp_id: UUID, created_by: UUID, links: list[dict]) -> list[dict]:
        """批量创建证据链接（字段已由调用方校验）。"""
        return [await self.create_link(wp_id=wp_id, created_by=created_by, **item) for item in links]

    # ─── 删除 ────────────────────────────────────────────────────────────────

    async def delete_link(self, link_id: UUID, *, wp_id: UUID) -> bool:
        """删除属于 ``wp_id`` 的证据链接；不属于 ⇒ False（路由回 404）。"""
        link = (await self.db.execute(
            sa.select(EvidenceLink).where(EvidenceLink.id == link_id, EvidenceLink.wp_id == wp_id)
        )).scalar_one_or_none()
        if link is None:
            return False
        await self.db.delete(link)
        await self.db.flush()
        return True

    async def delete_links_for_attachment(self, wp_id: UUID, attachment_id: UUID) -> int:
        """删除某附件在本底稿的全部证据链接（解除整稿关联时用），返回删除条数。"""
        result = await self.db.execute(
            sa.delete(EvidenceLink).where(EvidenceLink.wp_id == wp_id, EvidenceLink.attachment_id == attachment_id)
        )
        return int(result.rowcount or 0)

    # ─── 充分性检查 ───────────────────────────────────────────────────────────

    async def check_sufficiency(self, wp_id: UUID) -> dict:
        """检查证据充分性：必做程序是否都有至少一条证据链接"""
        proc_q = sa.select(WorkpaperProcedure).where(
            WorkpaperProcedure.wp_id == wp_id,
            WorkpaperProcedure.is_mandatory == True,  # noqa: E712
            WorkpaperProcedure.status != "not_applicable",
        )
        procs = (await self.db.execute(proc_q)).scalars().all()

        link_q = sa.select(EvidenceLink.cell_ref).where(EvidenceLink.wp_id == wp_id)
        link_rows = (await self.db.execute(link_q)).scalars().all()
        linked_cells = set(link_rows)

        warnings = []
        for proc in procs:
            # 如果程序已完成但没有任何证据链接，发出警告
            if proc.status == "completed" and not linked_cells:
                warnings.append({
                    "procedure_id": proc.procedure_id,
                    "description": proc.description,
                    "message": f"必做程序「{proc.description}」已完成但无附件证据",
                })

        return {
            "wp_id": str(wp_id),
            "total_mandatory": len(procs),
            "total_links": len(linked_cells),
            "sufficient": len(warnings) == 0,
            "warnings": warnings,
        }

    # ─── 内部方法 ─────────────────────────────────────────────────────────────

    @staticmethod
    def _attachment_brief(att: Attachment) -> dict:
        return {
            "id": str(att.id),
            "file_name": att.file_name,
            "file_size": att.file_size,
            "file_type": att.file_type,
            "attachment_type": att.attachment_type,
            "ocr_status": att.ocr_status,
            "created_at": att.created_at.isoformat() if att.created_at else None,
        }

    @staticmethod
    def _to_dict(link: EvidenceLink) -> dict:
        return {
            "id": str(link.id),
            "wp_id": str(link.wp_id),
            "sheet_name": link.sheet_name,
            "cell_ref": link.cell_ref,
            "attachment_id": str(link.attachment_id),
            "page_ref": link.page_ref,
            "evidence_type": link.evidence_type,
            "check_conclusion": link.check_conclusion,
            "voucher_key": link.voucher_key,
            "created_by": str(link.created_by),
            "created_at": link.created_at.isoformat() if link.created_at else None,
        }
