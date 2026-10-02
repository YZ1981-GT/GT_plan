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
from app.models.knowledge_models import KnowledgeAccessLevel, KnowledgeDocument, KnowledgeFolder
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
            # 🔴 旧实现 joinedload(KnowledgeDocument.folder) —— 模型没有 folder 关系，
            #    每次都在第一行 AttributeError，流水线从未跑通过（spec
            #    knowledge-base-retrieval-and-authz-closure 5.11）。文件夹按 folder_id 单独取。
            doc = await db.get(KnowledgeDocument, doc_id)
            if not doc or doc.is_deleted:
                logger.warning(f"[IndexingPipeline] doc_id={doc_id} not found or deleted, skip")
                return
            folder = await db.get(KnowledgeFolder, doc.folder_id) if doc.folder_id else None
            effective = _effective_access(doc, folder)
            if effective is None or effective == KnowledgeAccessLevel.private:
                # 私有文档不进任何项目分区 / 全局哨兵分区：索引是按项目检索的共享层，
                # 私有内容一旦入索引，任何能查该分区的调用方都能召回它。
                # 文档正文词法检索仍按「创建者本人可读」照常召回，不依赖索引。
                doc.index_status = "skipped"
                doc.index_error = "private document is not indexed (served by lexical retrieval)"
                await db.commit()
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
            project_id = _resolve_index_project_id(doc, folder)

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


def _effective_access(doc: KnowledgeDocument, folder: KnowledgeFolder | None):
    """生效级别：文档级非空取文档，否则继承文件夹（与 KnowledgeAccessPolicy 同一继承语义）。"""
    if doc.access_level is not None:
        return doc.access_level
    return folder.access_level if folder is not None else None


def _resolve_index_project_id(doc: KnowledgeDocument, folder: KnowledgeFolder | None = None) -> UUID:
    """确定文档应索引到哪个 project_id。

    - public → GLOBAL_KB_PROJECT_ID（哨兵分区）
    - project_group → 生效 project_ids 的第一个（文档级非空取文档，否则继承文件夹）
    - private → 调用方已跳过，不会走到这里

    旧实现把 project_ids 固定取文档自身的（继承文件夹时恒为空）⇒ 项目组文件夹里的文档全被
    索引进**全局**分区，任何项目都能召回。
    """
    effective = _effective_access(doc, folder)
    if effective == KnowledgeAccessLevel.project_group:
        pids = doc.project_ids if doc.access_level is not None else (folder.project_ids if folder else None)
        for raw in pids or []:
            try:
                return UUID(str(raw))
            except (ValueError, TypeError):
                continue
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
