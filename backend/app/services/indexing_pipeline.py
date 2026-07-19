"""
IndexingPipeline: 文档上传后触发的异步处理流水线
提取 → 分块 → 嵌入 → 入库

作为 background_task 运行，不阻塞上传响应。
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select, update

from app.core.database import async_session
from app.models.ai_models import KnowledgeIndex
from app.models.knowledge_models import KnowledgeDocument
from app.services.content_extractor import ContentExtractor
from app.services.knowledge_index_service import KnowledgeIndexService

logger = logging.getLogger(__name__)

# 全局公共文档哨兵 UUID
GLOBAL_KB_PROJECT_ID = UUID("00000000-0000-0000-0000-000000000000")


async def run_indexing_pipeline(doc_id: UUID) -> None:
    """
    完整索引流水线（作为 background task 运行）。

    Steps:
    1. Content Extraction (如果 content_text 为空)
    2. Semantic Chunking (由 incremental_update 内部处理)
    3. Embedding + Upsert (由 incremental_update 处理)
    """
    async with async_session() as db:
        try:
            # Eager load folder for access_level resolution
            from sqlalchemy.orm import joinedload
            from sqlalchemy import select as sa_select

            result = await db.execute(
                sa_select(KnowledgeDocument)
                .options(joinedload(KnowledgeDocument.folder))
                .where(KnowledgeDocument.id == doc_id)
            )
            doc = result.scalar_one_or_none()
            if not doc or doc.is_deleted:
                logger.warning(f"[IndexingPipeline] doc_id={doc_id} not found or deleted, skip")
                return

            # Step 1: Content Extraction
            if not doc.content_text and doc.storage_path:
                extract_result = await ContentExtractor.extract(doc.storage_path)
                doc.content_text = extract_result.content_text
                doc.index_status = extract_result.status
                doc.index_error = extract_result.error
                if extract_result.status != "extracted":
                    await db.commit()
                    logger.info(
                        f"[IndexingPipeline] doc_id={doc_id} extraction failed: "
                        f"status={extract_result.status}, error={extract_result.error}"
                    )
                    return

            if not doc.content_text:
                doc.index_status = "extraction_failed"
                doc.index_error = "no content_text and no storage_path"
                await db.commit()
                return

            # Step 2+3: Chunking + Embedding + Upsert
            svc = KnowledgeIndexService(db)
            project_id = _resolve_index_project_id(doc)

            await svc.incremental_update(
                project_id=project_id,
                source_type="knowledge_doc",
                source_id=doc.id,
                content=doc.content_text,
                doc_version=doc.version,
            )

            doc.index_status = "indexed"
            doc.index_error = None
            await db.commit()
            logger.info(f"[IndexingPipeline] doc_id={doc_id} indexed successfully")

        except Exception as e:
            logger.error(f"[IndexingPipeline] doc_id={doc_id} failed: {e}", exc_info=True)
            try:
                # 尝试记录失败状态
                doc = await db.get(KnowledgeDocument, doc_id)
                if doc:
                    doc.index_status = "failed"
                    doc.index_error = str(e)[:500]
                    await db.commit()
            except Exception:
                pass


def _resolve_index_project_id(doc: KnowledgeDocument) -> UUID:
    """确定文档应索引到哪个 project_id。

    - public 文档 → GLOBAL_KB_PROJECT_ID (哨兵)
    - project_group → 第一个 project_id
    - private → GLOBAL_KB_PROJECT_ID (fallback)
    """
    # 尝试从 folder 关联获取 access_level
    effective_access = getattr(doc, "access_level", None)
    if not effective_access and hasattr(doc, "folder") and doc.folder:
        effective_access = doc.folder.access_level

    if effective_access == "project_group" and getattr(doc, "project_ids", None):
        project_ids = doc.project_ids
        if project_ids:
            return UUID(str(project_ids[0]))

    return GLOBAL_KB_PROJECT_ID


async def mark_previous_version_stale(doc_id: UUID) -> None:
    """标记文档前一版本的索引 chunks 为 stale。"""
    async with async_session() as db:
        doc = await db.get(KnowledgeDocument, doc_id)
        if not doc or not doc.previous_version_id:
            return

        stmt = (
            update(KnowledgeIndex)
            .where(KnowledgeIndex.source_id == doc.previous_version_id)
            .where(KnowledgeIndex.is_deleted == False)  # noqa: E712
            .values(is_stale=True)
        )
        await db.execute(stmt)
        await db.commit()
        logger.info(
            f"[IndexingPipeline] marked chunks stale for previous version "
            f"{doc.previous_version_id} of doc {doc_id}"
        )


async def mark_chunks_deleted(doc_id: UUID) -> None:
    """软删除文档时，标记所有相关 chunks 为 deleted。"""
    async with async_session() as db:
        stmt = (
            update(KnowledgeIndex)
            .where(KnowledgeIndex.source_id == doc_id)
            .where(KnowledgeIndex.is_deleted == False)  # noqa: E712
            .values(is_deleted=True)
        )
        await db.execute(stmt)
        await db.commit()
        logger.info(f"[IndexingPipeline] marked chunks deleted for doc {doc_id}")
