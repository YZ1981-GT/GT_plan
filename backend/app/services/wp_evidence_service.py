"""底稿证据链管理服务

Sprint 6 Task 6.1:
  - 创建证据链接（单元格→附件）
  - 删除证据链接
  - 批量关联（区域→多附件）
  - 证据充分性检查（必做程序有附件）
"""

from __future__ import annotations

import logging
import uuid
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wp_optimization_models import EvidenceLink, WorkpaperProcedure

logger = logging.getLogger(__name__)


class WpEvidenceService:
    """证据链管理服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ─── 查询 ────────────────────────────────────────────────────────────────

    async def list_links(self, wp_id: UUID) -> list[dict]:
        """获取底稿所有证据链接"""
        q = (
            sa.select(EvidenceLink)
            .where(EvidenceLink.wp_id == wp_id)
            .order_by(EvidenceLink.created_at.desc())
        )
        rows = (await self.db.execute(q)).scalars().all()
        return [self._to_dict(r) for r in rows]

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
    ) -> dict:
        """创建单条证据链接"""
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

    # ─── 删除 ────────────────────────────────────────────────────────────────

    async def delete_link(self, link_id: UUID) -> bool:
        """删除证据链接"""
        q = sa.select(EvidenceLink).where(EvidenceLink.id == link_id)
        link = (await self.db.execute(q)).scalar_one_or_none()
        if not link:
            return False
        await self.db.delete(link)
        return True

    # ─── 批量关联 ─────────────────────────────────────────────────────────────

    async def batch_link(
        self,
        *,
        wp_id: UUID,
        created_by: UUID,
        links: list[dict],
    ) -> list[dict]:
        """批量创建证据链接（区域→多附件）"""
        results = []
        for item in links:
            link = EvidenceLink(
                id=uuid.uuid4(),
                wp_id=wp_id,
                sheet_name=item.get("sheet_name"),
                cell_ref=item.get("cell_ref"),
                attachment_id=UUID(item["attachment_id"]),
                page_ref=item.get("page_ref"),
                evidence_type=item.get("evidence_type"),
                check_conclusion=item.get("check_conclusion"),
                created_by=created_by,
            )
            self.db.add(link)
            results.append(link)
        await self.db.flush()
        return [self._to_dict(r) for r in results]

    # ─── 充分性检查 ───────────────────────────────────────────────────────────

    async def check_sufficiency(self, wp_id: UUID) -> dict:
        """检查证据充分性：必做程序是否都有至少一条证据链接"""
        # 获取必做程序
        proc_q = sa.select(WorkpaperProcedure).where(
            WorkpaperProcedure.wp_id == wp_id,
            WorkpaperProcedure.is_mandatory == True,  # noqa: E712
            WorkpaperProcedure.status != "not_applicable",
        )
        procs = (await self.db.execute(proc_q)).scalars().all()

        # 获取该底稿所有证据链接
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
            "created_by": str(link.created_by),
            "created_at": link.created_at.isoformat() if link.created_at else None,
        }
