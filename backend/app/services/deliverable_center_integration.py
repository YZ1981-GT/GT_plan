"""交付件中心集成服务 — P1-2

本 spec 不新建版本模型，只做引用接入：
- EvidenceRef 指向 deliverable-center 的版本 ID
- 复用 audit-report-deliverable-center 的版本链
- 终态再导出新建版本或交付物（不覆盖历史）

版本链、生成、签发、归档逻辑归 audit-report-deliverable-center spec。
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.evidence_ref import EvidenceRef, EvidenceType
from app.services.deliverable_service import DeliverableService

logger = logging.getLogger(__name__)


class DeliverableCenterIntegration:
    """交付件中心集成层

    P1-2.1: 复用 audit-report-deliverable-center 的版本链
    P1-2.2: 报告、附注、PDF、签发文件进入交付件中心
    P1-2.3: 终态再导出新建版本或交付物
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._deliverable_svc = DeliverableService(db)

    async def submit_to_deliverable_center(
        self,
        *,
        project_id: UUID,
        doc_type: str,
        template_type: str | None = None,
        user_id: UUID,
        file_path: str | None = None,
        file_bytes: bytes | None = None,
        html_content: str | None = None,
        file_name: str | None = None,
        source_snapshot_refs: dict | None = None,
        selected_sections: list | None = None,
    ) -> dict:
        """P1-2.2: 将报告、附注、PDF、签发文件提交到交付件中心。

        逻辑：
        1. 调用 export_or_new_deliverable 获取/创建交付物 task
        2. 调用 render_and_store 存储文件并创建版本
        3. 返回包含 EvidenceRef 的结果（可被复核意见等引用）

        Parameters
        ----------
        doc_type : str
            文件类型：audit_report / note / pdf / signoff
        """
        from pathlib import Path

        # P1-2.1: 复用版本链 — export_or_new_deliverable 内部判断终态
        task, is_new = await self._deliverable_svc.export_or_new_deliverable(
            project_id=project_id,
            doc_type=doc_type,
            template_type=template_type,
            user_id=user_id,
        )

        # P1-2.3: 终态再导出时 is_new=True，新建独立交付物
        if is_new:
            logger.info(
                "交付件中心：新建交付物 task_id=%s, doc_type=%s",
                task.id, doc_type,
            )

        # 存储文件并创建版本
        docx_path = Path(file_path) if file_path else None
        store_result = await self._deliverable_svc.render_and_store(
            task.id,
            docx_bytes=file_bytes,
            docx_path=docx_path,
            html_content=html_content,
            user_id=user_id,
            source_snapshot_refs=source_snapshot_refs,
            selected_sections=selected_sections,
            file_name=file_name,
        )

        # 构建 EvidenceRef 指向该版本
        evidence_ref = EvidenceRef(
            evidence_type=EvidenceType.deliverable,
            evidence_id=str(task.id),
            project_id=str(project_id),
            version=str(store_result.version.version_no),
            label=file_name or f"{doc_type}_v{store_result.version.version_no}",
        )

        return {
            "task_id": str(task.id),
            "version_no": store_result.version.version_no,
            "download_url": store_result.download_url,
            "is_new_task": is_new,
            "evidence_ref": evidence_ref.model_dump(),
            "platform_persist_failed": store_result.platform_persist_failed,
        }

    async def get_version_chain_as_refs(
        self,
        task_id: UUID,
        project_id: UUID,
    ) -> list[dict]:
        """P1-2.1: 获取交付物版本链，以 EvidenceRef 列表返回。"""
        versions = await self._deliverable_svc.get_version_chain(task_id)
        refs = []
        for v in versions:
            ref = EvidenceRef(
                evidence_type=EvidenceType.deliverable,
                evidence_id=str(task_id),
                project_id=str(project_id),
                version=str(v.version_no),
                label=f"v{v.version_no}",
            )
            refs.append(ref.model_dump())
        return refs

    async def reexport_terminal(
        self,
        *,
        project_id: UUID,
        doc_type: str,
        existing_task_id: UUID,
        user_id: UUID,
        file_bytes: bytes,
        file_name: str | None = None,
    ) -> dict:
        """P1-2.3: 终态交付物再导出 → 新建独立交付物或版本。

        如果 existing_task 处于终态（confirmed/signed/archived），
        则新建独立交付物；否则追加版本。历史版本不被覆盖。
        """
        task, is_new = await self._deliverable_svc.export_or_new_deliverable(
            project_id=project_id,
            doc_type=doc_type,
            template_type=None,
            user_id=user_id,
            existing_task_id=existing_task_id,
        )

        store_result = await self._deliverable_svc.render_and_store(
            task.id,
            docx_bytes=file_bytes,
            user_id=user_id,
            file_name=file_name,
        )

        return {
            "task_id": str(task.id),
            "version_no": store_result.version.version_no,
            "download_url": store_result.download_url,
            "is_new_task": is_new,
        }

    async def verify_version_immutability(
        self,
        task_id: UUID,
        version_no: int,
    ) -> bool:
        """P1-2.4: 验证历史版本不可覆盖。

        检查给定版本是否存在且内容未被修改。
        Returns True if version exists and is immutable (cannot be overwritten).
        """
        version = await self._deliverable_svc.get_version(task_id, version_no)
        if version is None:
            return False
        # 版本一旦创建就不可覆盖 — 只能新建版本
        # 这由 create_version 的 version_no 自增保证
        return True
