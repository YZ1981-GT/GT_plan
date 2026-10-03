"""
IndexSource Protocol + BusinessDataSource + KnowledgeDocSource

可扩展索引源注册表：替代 KnowledgeIndexService._fetch_project_texts 硬编码。
每个 IndexSource 实现一种数据源的文本提取逻辑，注册后由内核统一调度。

设计：
- IndexSource 是 @runtime_checkable Protocol，source_type + fetch_texts
- BusinessDataSource 包装现有 11 类 KnowledgeSourceType 业务数据（行为不变）
- KnowledgeDocSource 读 KnowledgeDocument.content_text 建向量索引
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_models import KnowledgeSourceType, Contract, DocumentScan
from app.models.audit_platform_models import (
    Adjustment,
    AdjustmentEntry,
    TrialBalance,
)
from app.models.report_models import AuditReport
from app.models.collaboration_models import AuditFinding
from app.models.knowledge_models import KnowledgeDocument, KnowledgeFolder


@runtime_checkable
class IndexSource(Protocol):
    """可扩展索引源协议。

    每个实现提供一种数据源的文本提取能力：
    - source_type: 标识源类型的字符串
    - fetch_texts: 异步获取项目下该源的所有文本条目
    """

    source_type: str

    async def fetch_texts(self, project_id: UUID) -> list[tuple[str, str, str]]:
        """返回 [(item_type, item_id, text)]。

        item_type: KnowledgeSourceType 枚举值字符串
        item_id: 源记录 ID（字符串化 UUID）
        text: 待索引的文本内容
        """
        ...


class BusinessDataSource:
    """业务数据索引源 — 包装现有 11 类 KnowledgeSourceType 成员。

    行为与原 _fetch_project_texts 完全一致，仅从硬编码提取为注册式。
    实际索引 6 类已实现的业务数据（DocumentScan/AdjustmentEntry/TrialBalance/
    AuditReport/Contract/AuditFinding），其余 5 类枚举成员暂无对应查询。
    """

    source_type: str = "business_data"

    def __init__(self, db: AsyncSession):
        self._db = db

    async def fetch_texts(self, project_id: UUID) -> list[tuple[str, str, str]]:
        """提取项目下所有业务数据文本，返回 [(source_type_enum, source_id, text)]。

        注意：返回的 tuple 第一个元素是 KnowledgeSourceType 枚举实例（非字符串），
        与原 _fetch_project_texts 行为一致，供 build_index 直接使用。
        """
        texts: list[tuple] = []

        # -- DocumentScan --
        doc_result = await self._db.execute(
            select(DocumentScan).where(
                DocumentScan.project_id == project_id,
                DocumentScan.is_deleted == False,  # noqa: E712
            )
        )
        for doc in doc_result.scalars().all():
            content = (
                f"文档 {getattr(doc, 'file_name', '') or ''}，"
                f"类型 {getattr(doc, 'document_type', '未知')}。"
            )
            texts.append((KnowledgeSourceType.document_scan, doc.id, content))

        # -- WorkingPaper (AdjustmentEntry) --
        adj_entry_result = await self._db.execute(
            select(AdjustmentEntry).where(
                AdjustmentEntry.adjustment_id.in_(
                    select(Adjustment.id).where(Adjustment.project_id == project_id)
                ),
                AdjustmentEntry.is_deleted == False,  # noqa: E712
            )
        )
        for entry in adj_entry_result.scalars().all():
            content = (
                f"调整分录 {entry.entry_description or ''}，"
                f"科目 {entry.account_code or ''} {entry.account_name or ''}，"
                f"借方 {entry.debit_amount or 0}，贷方 {entry.credit_amount or 0}。"
            )
            texts.append((KnowledgeSourceType.workpaper, entry.id, content))

        # -- TrialBalance --
        tb_result = await self._db.execute(
            select(TrialBalance).where(
                TrialBalance.project_id == project_id,
                TrialBalance.is_deleted == False,  # noqa: E712
            )
        )
        for tb in tb_result.scalars().all():
            content = (
                f"试算表 {getattr(tb, 'period', '') or ''}，"
                f"科目 {tb.account_code or ''} {tb.account_name or ''}，"
                f"期初余额 {tb.opening_balance or 0}，"
                f"期末余额 {tb.closing_balance or 0}。"
            )
            texts.append((KnowledgeSourceType.trial_balance, tb.id, content))

        # -- AuditReport --
        report_result = await self._db.execute(
            select(AuditReport).where(
                AuditReport.project_id == project_id,
                AuditReport.is_deleted == False,  # noqa: E712
            )
        )
        for report in report_result.scalars().all():
            content = (
                f"审计报告 {getattr(report, 'title', '') or ''}，"
                f"类型 {getattr(report, 'report_type', '')}。"
            )
            texts.append((KnowledgeSourceType.report, report.id, content))

        # -- Contract --
        contract_result = await self._db.execute(
            select(Contract).where(
                Contract.project_id == project_id,
                Contract.is_deleted == False,  # noqa: E712
            )
        )
        for contract in contract_result.scalars().all():
            content = (
                f"合同 {getattr(contract, 'contract_no', '') or ''}，"
                f"甲方 {contract.party_a or ''}，乙方 {contract.party_b or ''}，"
                f"金额 {getattr(contract, 'contract_amount', '')}，"
                f"类型 {getattr(contract, 'contract_type', '未知')}。"
            )
            texts.append((KnowledgeSourceType.contract, contract.id, content))

        # -- AuditFinding --
        finding_result = await self._db.execute(
            select(AuditFinding).where(
                AuditFinding.project_id == project_id,
                AuditFinding.is_deleted == False,  # noqa: E712
            )
        )
        for finding in finding_result.scalars().all():
            content = (
                f"审计发现 {finding.finding_code}，"
                f"严重程度 {finding.severity}，"
                f"描述 {finding.finding_description or ''}，"
                f"影响科目 {finding.affected_account or ''}。"
            )
            texts.append((KnowledgeSourceType.finding, finding.id, content))

        return texts


class KnowledgeDocSource:
    """知识文件索引源 — 读 KnowledgeDocument.content_text 建向量。

    source_type=knowledge_doc，接入 KnowledgeIndexService 内核后，
    用户上传的知识文件即可享受向量语义检索。

    项目关联逻辑：
    - KnowledgeDocument 通过 KnowledgeFolder.project_ids (JSONB) 关联项目
    - 文件夹 access_level=public 的文档对所有项目可见
    - 文件夹 access_level=project_group 的文档仅对 project_ids 中的项目可见
    - 文档级 access_level 可覆盖文件夹级（None 表示继承文件夹）
    """

    source_type: str = "knowledge_doc"

    def __init__(self, db: AsyncSession):
        self._db = db

    async def fetch_texts(self, project_id: UUID) -> list[tuple[str, str, str]]:
        """提取项目可访问的知识文件文本，返回 [(source_type_enum, doc_id, text)]。

        查询逻辑：
        1. 文件夹 access_level=public → 所有文档对该项目可见
        2. 文件夹 access_level=project_group 且 project_ids 包含 project_id → 可见
        3. 文档级 access_level 覆盖文件夹级（public 直接可见，project_group 检查 doc.project_ids）
        4. 只取有 content_text 且未删除的文档
        """
        import sqlalchemy as sa
        from sqlalchemy.orm import aliased

        from app.services.knowledge_access_policy import (
            KnowledgeAccessPolicy,
            KnowledgeResource,
            KnowledgeRetrievalMode,
        )

        texts: list[tuple] = []
        successor = aliased(KnowledgeDocument)

        # 未删除、有内容、所在文件夹未删除、且是版本链最新版的知识文档（join folder 取判权三元组）
        result = await self._db.execute(
            select(
                KnowledgeDocument.id,
                KnowledgeDocument.content_text,
                KnowledgeDocument.access_level,
                KnowledgeDocument.project_ids,
                KnowledgeDocument.created_by,
                KnowledgeFolder.access_level.label("folder_access_level"),
                KnowledgeFolder.project_ids.label("folder_project_ids"),
                KnowledgeFolder.created_by.label("folder_created_by"),
            )
            .join(KnowledgeFolder, KnowledgeDocument.folder_id == KnowledgeFolder.id)
            .where(
                KnowledgeDocument.is_deleted == False,  # noqa: E712
                KnowledgeFolder.is_deleted == False,  # noqa: E712
                KnowledgeDocument.content_text.isnot(None),
                KnowledgeDocument.content_text != "",
                ~sa.exists().where(
                    successor.previous_version_id == KnowledgeDocument.id,
                    successor.is_deleted == sa.false(),
                ),
            )
        )

        for row in result.all():
            # 可见性唯一走单一判定面：project 模式、无用户（索引按项目分区建，不含私有文档）
            if not KnowledgeAccessPolicy.can_retrieve(
                KnowledgeRetrievalMode.project,
                None,
                project_id,
                KnowledgeResource.of_row(row.access_level, row.project_ids, row.created_by),
                KnowledgeResource.of_row(
                    row.folder_access_level, row.folder_project_ids, row.folder_created_by
                ),
            ):
                continue

            texts.append((
                KnowledgeSourceType.knowledge_doc,
                row.id,
                row.content_text,
            ))

        return texts
