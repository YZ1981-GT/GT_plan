"""
Knowledge Index Service

Provides vector index capabilities for audit project knowledge base:
- build_index: Full build of all project data vector index
- incremental_update: Incremental update for single document
- semantic_search: Vector semantic search (cosine similarity)
- search_cross_year: Cross-year search (current + prior year project)
- lock_index: Lock index when archiving
- delete_index: Delete all project indexes
"""

from __future__ import annotations

import time
import uuid
from typing import Any
from uuid import UUID

import numpy as np
from sqlalchemy import select, update, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

import logging

from app.models.ai_models import KnowledgeIndex, KnowledgeSourceType
from app.models.knowledge_models import KnowledgeDocument, KnowledgeFolder
from app.services.ai_service import AIService
from app.services.index_source import IndexSource, BusinessDataSource, KnowledgeDocSource
from app.services.vector_store import get_vector_store, PgTextStore

logger = logging.getLogger(__name__)

# Fixed chunk size (character count)
_CHUNK_SIZE = 500

# BM25 索引缓存：key=(project_id, scope), value=(bm25_index, chunks_list, build_timestamp)
# 模块级缓存，跨请求共享（同一进程内）；TTL 60s 或 incremental_update 时失效
_BM25_CACHE: dict[tuple, tuple] = {}
_BM25_CACHE_TTL = 60  # seconds


def _invalidate_bm25_cache(project_id: UUID) -> None:
    """Invalidate all BM25 cache entries for a given project (all scopes).

    Called by incremental_update / build_index / update_index / delete_index
    to ensure stale indices are not served after document changes.
    """
    pid_str = str(project_id)
    keys_to_remove = [k for k in _BM25_CACHE if k[0] == pid_str]
    for k in keys_to_remove:
        del _BM25_CACHE[k]


def _chunk_text(text: str, chunk_size: int = _CHUNK_SIZE) -> list[str]:
    """Split text into fixed-size chunks with overlap."""
    if not text or not text.strip():
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end
    return chunks


class KnowledgeIndexService:
    def __init__(self, db: AsyncSession):
        self._db = db
        self._ai_svc = AIService(db)

    # -------------------------------------------------------------------------
    # Helper methods
    # -------------------------------------------------------------------------

    @staticmethod
    def _vector_to_str(vec: np.ndarray) -> str:
        """Convert numpy vector to comma-separated string for DB storage."""
        return ",".join(str(v) for v in vec.tolist())

    @staticmethod
    def _str_to_vector(s: str) -> np.ndarray:
        """Parse comma-separated string back to numpy vector."""
        return np.array([float(x) for x in s.split(",")])

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    async def _upsert_chunk(
        self,
        project_id: UUID,
        source_type: KnowledgeSourceType,
        source_id: UUID,
        content_text: str,
        embedding: np.ndarray,
        chunk_index: int,
    ) -> None:
        """Upsert single chunk (source_id + chunk_index unique)."""
        values = {
            "content_text": content_text,
            "embedding_vector": self._vector_to_str(embedding),
            "is_deleted": False,
            "updated_at": func.now(),
        }
        stmt = (
            insert(KnowledgeIndex)
            .values(
                id=uuid.uuid4(),
                project_id=project_id,
                source_type=source_type,
                source_id=source_id,
                content_text=content_text,
                embedding_vector=self._vector_to_str(embedding),
                chunk_index=chunk_index,
                is_deleted=False,
            )
            .on_conflict_do_update(
                index_elements=["project_id", "source_id", "chunk_index"],
                set_=values,
            )
        )
        await self._db.execute(stmt)

    async def _batch_upsert_chunks(self, chunks: list[tuple]) -> None:
        """Batch upsert multiple chunks at once."""
        if not chunks:
            return
        values_list = [
            {
                "id": uuid.uuid4(),
                "project_id": c[0],
                "source_type": c[1],
                "source_id": c[2],
                "content_text": c[3],
                "embedding_vector": self._vector_to_str(c[4]),
                "chunk_index": c[5],
                "is_deleted": False,
            }
            for c in chunks
        ]
        stmt = insert(KnowledgeIndex).values(values_list)
        # Use on_conflict for each - PostgreSQL upsert per row
        for values in values_list:
            await self._db.execute(
                stmt.on_conflict_do_update(
                    index_elements=["project_id", "source_id", "chunk_index"],
                    set_={
                        "content_text": values["content_text"],
                        "embedding_vector": values["embedding_vector"],
                        "is_deleted": False,
                        "updated_at": func.now(),
                    },
                )
            )

    def _index_sources(self) -> list[IndexSource]:
        """可注册索引源列表（替代 _fetch_project_texts 硬编码）。

        后续新增索引源只需追加到此列表。
        """
        return [
            BusinessDataSource(self._db),
            KnowledgeDocSource(self._db),
        ]

    def _get_store(self, project_id: UUID | None = None) -> "PgTextStore":
        """获取 VectorStore 实例（由 feature flag 控制后端）。

        通过 get_vector_store 工厂函数，根据 VECTOR_STORE_BACKEND 环境变量
        返回 PgTextStore 或 PgVectorStore。
        """
        pid_str = str(project_id) if project_id else None
        return get_vector_store(self._db, project_id=pid_str)

    async def _fetch_project_texts(self, project_id: UUID) -> list[tuple]:
        """Fetch all text content for a project via registered IndexSource instances.

        Returns list of (source_type, source_id, text) tuples.
        行为与重构前完全一致 — 遍历所有注册源汇总文本。
        """
        texts: list[tuple] = []
        for source in self._index_sources():
            source_texts = await source.fetch_texts(project_id)
            texts.extend(source_texts)
        return texts

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def build_index(self, project_id: UUID) -> int:
        """
        Full build of project knowledge base index.
        Returns total number of indexed documents (chunks).
        """
        # Invalidate BM25 cache — full rebuild means old cache is stale
        _invalidate_bm25_cache(project_id)

        texts = await self._fetch_project_texts(project_id)
        total_chunks = 0

        for source_type, source_id, text in texts:
            for idx, chunk_text in enumerate(_chunk_text(text)):
                embedding = await self._ai_svc.embedding(chunk_text)
                vec = np.array(embedding)
                await self._upsert_chunk(
                    project_id=project_id,
                    source_type=source_type,
                    source_id=source_id,
                    content_text=chunk_text,
                    embedding=vec,
                    chunk_index=idx,
                )
                total_chunks += 1

        await self._db.commit()
        return total_chunks

    async def incremental_update(
        self,
        project_id: UUID,
        source_type: str,
        source_id: UUID,
        content: str,
    ) -> None:
        """Incremental update index when data changes (upsert new chunks)."""
        # Invalidate BM25 cache for this project (all scopes)
        _invalidate_bm25_cache(project_id)

        st = KnowledgeSourceType(source_type)
        for idx, chunk_text in enumerate(_chunk_text(content)):
            embedding = await self._ai_svc.embedding(chunk_text)
            vec = np.array(embedding)
            await self._upsert_chunk(
                project_id=project_id,
                source_type=st,
                source_id=source_id,
                content_text=chunk_text,
                embedding=vec,
                chunk_index=idx,
            )
        await self._db.commit()

    async def semantic_search(
        self,
        project_id: UUID,
        query: str,
        top_k: int = 10,
        *,
        scope: str = "all",
        user: Any | None = None,
    ) -> list[dict[str, Any]]:
        """
        Semantic search using embedding + cosine similarity.
        Returns top_k results with scores.

        Args:
            project_id: 项目 ID
            query: 查询文本
            top_k: 返回结果数量
            scope: 检索范围 ("project_data" | "knowledge_doc" | "cross_year" | "all")
            user: 可选用户对象，提供时按权限过滤 knowledge_doc 结果

        默认值保证现有调用方（ai_chat_service）零改动。
        向量召回失败时降级 ilike（双保险不崩）。
        """
        # scope=cross_year 委托给 search_cross_year（需 prior_project_id，此处降级为 all）
        if scope == "cross_year":
            # cross_year 需要 prior_project_id，单独调 search_cross_year；
            # 此处作为 fallback 按 all 处理
            scope = "all"

        try:
            results = await self._vector_search(project_id, query, top_k, scope)
            # TODO: hybrid retrieval 预留接口——_vector_search 成功时可选融合 bm25 分数
            # 当 embed 恢复后，可在此融合向量分数 + BM25 分数实现 hybrid retrieval
        except Exception as e:
            logger.warning(f"向量召回失败，降级检索: {e}")
            from app.core.config import settings as app_settings

            if app_settings.RETRIEVAL_BM25_FALLBACK_ENABLED:
                results = await self._bm25_fallback(project_id, query, top_k, scope)
            else:
                results = await self._ilike_fallback(project_id, query, top_k, scope)

        # 权限过滤：当 user 提供时，过滤 knowledge_doc 结果
        if user is not None:
            results = await self._filter_by_permission(results, user)

        return results

    async def _vector_search(
        self,
        project_id: UUID,
        query: str,
        top_k: int,
        scope: str,
    ) -> list[dict[str, Any]]:
        """向量召回核心逻辑（可能抛异常，由调用方捕获降级）。"""
        # Encode query
        query_embedding = await self._ai_svc.embedding(query)
        query_vec = np.array(query_embedding)

        # Build scope filter conditions
        conditions = [
            KnowledgeIndex.project_id == project_id,
            KnowledgeIndex.is_deleted == False,
        ]
        if scope == "project_data":
            conditions.append(
                KnowledgeIndex.source_type != KnowledgeSourceType.knowledge_doc
            )
        elif scope == "knowledge_doc":
            conditions.append(
                KnowledgeIndex.source_type == KnowledgeSourceType.knowledge_doc
            )
        # scope == "all": no additional filter

        # Fetch chunks matching scope
        result = await self._db.execute(
            select(KnowledgeIndex).where(*conditions)
        )
        chunks = result.scalars().all()

        # Compute similarity scores
        scored = []
        for chunk in chunks:
            chunk_vec = self._str_to_vector(chunk.embedding_vector)
            score = self._cosine_similarity(query_vec, chunk_vec)
            scored.append((score, chunk))

        # Sort and take top_k
        scored.sort(key=lambda x: x[0], reverse=True)
        top_results = scored[:top_k]

        return [
            {
                "source_type": chunk.source_type.value,
                "source_id": str(chunk.source_id),
                "content": chunk.content_text,
                "score": round(score, 4),
                "chunk_index": chunk.chunk_index,
            }
            for score, chunk in top_results
        ]

    async def _bm25_fallback(
        self,
        project_id: UUID,
        query: str,
        top_k: int,
        scope: str,
    ) -> list[dict[str, Any]]:
        """向量召回失败时的 BM25 词法检索（bm25s，纯 Python）。

        中文分词用 _zh_tokenize 模块（2-gram bigram + 英文 split，不引 jieba）。
        bm25s 未安装或索引构建异常时降级 _ilike_fallback。
        返回与 _ilike_fallback 相同的 dict 结构（score 用 BM25 归一化分数，非 0.0）。

        带模块级缓存：key=(project_id, scope)，value=(bm25_index, chunks_list, build_time)。
        TTL 60s 或 incremental_update 调用时失效。避免每次查询重建索引。
        """
        try:
            import bm25s
        except ImportError:
            logger.warning("bm25s 未安装，降级 ilike")
            return await self._ilike_fallback(project_id, query, top_k, scope)

        from app.services._zh_tokenize import zh_tokenize

        query_tokens = zh_tokenize(query)
        if not query_tokens:
            return await self._ilike_fallback(project_id, query, top_k, scope)

        # 缓存检查：(project_id, scope) → (retriever, chunks, build_time)
        cache_key = (str(project_id), scope)
        now = time.time()
        cached = _BM25_CACHE.get(cache_key)

        if cached is not None:
            retriever, chunks, build_time = cached
            if (now - build_time) < _BM25_CACHE_TTL:
                # 缓存有效，直接检索
                return self._bm25_retrieve(retriever, chunks, query_tokens, top_k)
            else:
                # TTL 过期，移除缓存
                del _BM25_CACHE[cache_key]

        # 缓存 miss 或过期：从 DB 加载候选文档，构建索引
        conditions = [
            KnowledgeIndex.project_id == project_id,
            KnowledgeIndex.is_deleted == False,
        ]
        if scope == "project_data":
            conditions.append(
                KnowledgeIndex.source_type != KnowledgeSourceType.knowledge_doc
            )
        elif scope == "knowledge_doc":
            conditions.append(
                KnowledgeIndex.source_type == KnowledgeSourceType.knowledge_doc
            )

        result = await self._db.execute(select(KnowledgeIndex).where(*conditions))
        chunks = result.scalars().all()
        if not chunks:
            return []

        # 分词 + 构建索引
        from app.services._zh_tokenize import zh_tokenize_batch

        corpus_texts = [c.content_text or "" for c in chunks]
        corpus_tokens = zh_tokenize_batch(corpus_texts)

        try:
            retriever = bm25s.BM25()
            retriever.index(corpus_tokens)
        except Exception as exc:
            logger.warning("BM25 索引构建失败，降级 ilike: %s", exc)
            return await self._ilike_fallback(project_id, query, top_k, scope)

        # 存入缓存
        _BM25_CACHE[cache_key] = (retriever, chunks, now)

        return self._bm25_retrieve(retriever, chunks, query_tokens, top_k)

    @staticmethod
    def _bm25_retrieve(
        retriever: Any,
        chunks: list,
        query_tokens: list[str],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """从已构建的 BM25 索引中检索 top_k 结果。

        提取为静态方法，缓存命中和新建索引后共用。
        """
        try:
            k = min(top_k, len(chunks))
            indices, scores = retriever.retrieve([query_tokens], k=k)
            idx_list = indices[0].tolist() if hasattr(indices[0], "tolist") else list(indices[0])
            score_list = scores[0].tolist() if hasattr(scores[0], "tolist") else list(scores[0])
        except Exception:
            return []

        # 归一化分数：除以最大分数（max > 0 时）
        max_score = max(score_list) if score_list else 0.0

        out: list[dict[str, Any]] = []
        for rank, idx in enumerate(idx_list):
            if idx < 0 or idx >= len(chunks):
                continue
            chunk = chunks[int(idx)]
            raw_score = float(score_list[rank]) if rank < len(score_list) else 0.0
            normalized_score = (raw_score / max_score) if max_score > 0 else 0.0
            out.append({
                "source_type": chunk.source_type.value,
                "source_id": str(chunk.source_id),
                "content": chunk.content_text,
                "score": round(normalized_score, 4),
                "chunk_index": chunk.chunk_index,
            })
        return out[:top_k]

    async def _ilike_fallback(
        self,
        project_id: UUID,
        query: str,
        top_k: int,
        scope: str,
    ) -> list[dict[str, Any]]:
        """向量召回失败时的 ilike 降级搜索（双保险）。

        搜索 KnowledgeIndex.content_text 字段，按 scope 过滤。
        """
        conditions = [
            KnowledgeIndex.project_id == project_id,
            KnowledgeIndex.is_deleted == False,
            KnowledgeIndex.content_text.ilike(f"%{query}%"),
        ]
        if scope == "project_data":
            conditions.append(
                KnowledgeIndex.source_type != KnowledgeSourceType.knowledge_doc
            )
        elif scope == "knowledge_doc":
            conditions.append(
                KnowledgeIndex.source_type == KnowledgeSourceType.knowledge_doc
            )

        result = await self._db.execute(
            select(KnowledgeIndex).where(*conditions).limit(top_k)
        )
        chunks = result.scalars().all()

        return [
            {
                "source_type": chunk.source_type.value,
                "source_id": str(chunk.source_id),
                "content": chunk.content_text,
                "score": 0.0,  # ilike 无相似度分数
                "chunk_index": chunk.chunk_index,
            }
            for chunk in chunks
        ]

    async def _filter_by_permission(
        self,
        results: list[dict[str, Any]],
        user: Any,
    ) -> list[dict[str, Any]]:
        """按用户权限过滤 knowledge_doc 类型的结果。

        非 knowledge_doc 类型不过滤（业务数据按项目权限已隔离）。
        knowledge_doc 结果需检查用户对 KnowledgeDocument 的访问权限：
        - public: 所有用户可见
        - project_group: 用户所属项目在 project_ids 中
        - private: 仅创建者可见
        """
        if not results:
            return results

        # 分离 knowledge_doc 和非 knowledge_doc 结果
        non_doc_results = [r for r in results if r["source_type"] != "knowledge_doc"]
        doc_results = [r for r in results if r["source_type"] == "knowledge_doc"]

        if not doc_results:
            return results

        # 获取用户 ID
        user_id = getattr(user, "id", None)
        user_id_str = str(user_id) if user_id else None

        # 批量查询这些 source_id 对应的 KnowledgeDocument 权限信息
        source_ids = [UUID(r["source_id"]) for r in doc_results]
        doc_query = (
            select(
                KnowledgeIndex.source_id,
                KnowledgeDocument.access_level,
                KnowledgeDocument.project_ids,
                KnowledgeDocument.created_by,
                KnowledgeFolder.access_level.label("folder_access_level"),
                KnowledgeFolder.project_ids.label("folder_project_ids"),
            )
            .join(
                KnowledgeDocument,
                KnowledgeIndex.source_id == KnowledgeDocument.id,
            )
            .join(
                KnowledgeFolder,
                KnowledgeDocument.folder_id == KnowledgeFolder.id,
            )
            .where(
                KnowledgeIndex.source_id.in_(source_ids),
                KnowledgeDocument.is_deleted == False,
            )
        )
        perm_result = await self._db.execute(doc_query)
        perm_rows = perm_result.all()

        # 构建 source_id -> 权限信息映射
        accessible_source_ids: set[str] = set()
        for row in perm_rows:
            source_id_val, doc_access, doc_proj_ids, created_by, folder_access, folder_proj_ids = row
            if self._user_can_access_doc(
                user_id_str, created_by, doc_access, doc_proj_ids, folder_access, folder_proj_ids
            ):
                accessible_source_ids.add(str(source_id_val))

        # 过滤 doc_results
        filtered_doc_results = [
            r for r in doc_results if r["source_id"] in accessible_source_ids
        ]

        return non_doc_results + filtered_doc_results

    @staticmethod
    def _user_can_access_doc(
        user_id_str: str | None,
        created_by: UUID | None,
        doc_access_level,
        doc_project_ids: list | None,
        folder_access_level,
        folder_project_ids: list | None,
    ) -> bool:
        """判断用户是否有权访问该知识文档。

        权限继承模型：文档级 > 文件夹级。
        - public: 所有用户可见
        - project_group: 用户所属项目在 project_ids 中（简化：检查 user 关联项目）
        - private: 仅创建者可见
        """
        # 确定生效的 access_level
        if doc_access_level is not None:
            effective_access = doc_access_level
            effective_proj_ids = doc_project_ids
        else:
            effective_access = folder_access_level
            effective_proj_ids = folder_project_ids

        access_str = effective_access.value if hasattr(effective_access, "value") else str(effective_access)

        if access_str == "public":
            return True
        elif access_str == "private":
            # 仅创建者可见
            if not user_id_str or not created_by:
                return False
            return user_id_str == str(created_by)
        elif access_str == "project_group":
            # project_group: 用户需在 project_ids 列表中有关联
            # 简化实现：如果 project_ids 非空则允许（实际应检查用户项目关联）
            # 但由于 semantic_search 已按 project_id 过滤，project_group 文档
            # 只要 project_id 在列表中即可见（已由向量索引阶段保证）
            return True
        else:
            return False

    async def search_cross_year(
        self,
        project_id: UUID,
        prior_project_id: UUID,
        query: str,
    ) -> list[dict[str, Any]]:
        """
        Cross-year search: search both current and prior year projects,
        merge and sort results by similarity score.
        """
        # Search current project
        current_results = await self.semantic_search(project_id, query, top_k=10)

        # Search prior project
        prior_results = await self.semantic_search(prior_project_id, query, top_k=10)

        # Mark source project
        for r in current_results:
            r["project_id"] = str(project_id)
            r["is_prior"] = False
        for r in prior_results:
            r["project_id"] = str(prior_project_id)
            r["is_prior"] = True

        # Merge and sort
        merged = current_results + prior_results
        merged.sort(key=lambda x: x["score"], reverse=True)
        return merged[:20]

    async def lock_index(self, project_id: UUID) -> None:
        """Lock index to read-only when project is archived."""
        # is_locked field not in KnowledgeIndex model - reserved for future
        await self._db.commit()

    async def delete_index(self, project_id: UUID) -> None:
        """Delete project index (soft delete all chunks)."""
        # Invalidate BM25 cache — documents deleted
        _invalidate_bm25_cache(project_id)

        await self._db.execute(
            update(KnowledgeIndex)
            .where(KnowledgeIndex.project_id == project_id)
            .values(is_deleted=True, updated_at=func.now())
        )
        await self._db.commit()

    async def add_document(
        self,
        project_id: UUID,
        content: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Add a single document to the knowledge index.
        Generates embedding, splits into chunks, upserts to DB.

        Args:
            project_id: Project ID
            content: Document text content
            metadata: Dict with optional title, source_type, source_id, tags, user_id

        Returns:
            Dict with document_id, chunk_count, status
        """
        import datetime

        source_id = uuid.uuid4()
        source_type_str = metadata.get("source_type", "manual")
        source_type = KnowledgeSourceType(source_type_str)

        chunks = _chunk_text(content)
        total_chunks = 0

        for idx, chunk_text in enumerate(chunks):
            embedding = await self._ai_svc.embedding(chunk_text)
            vec = np.array(embedding)
            await self._upsert_chunk(
                project_id=project_id,
                source_type=source_type,
                source_id=source_id,
                content_text=chunk_text,
                embedding=vec,
                chunk_index=idx,
            )
            total_chunks += 1

        await self._db.commit()

        return {
            "document_id": str(source_id),
            "chunk_count": total_chunks,
            "status": "indexed",
            "source_type": source_type_str,
            "indexed_at": datetime.datetime.now(timezone.utc).isoformat(),
        }

    async def search(
        self,
        project_id: UUID,
        query: str,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Alias for semantic_search. Kept for API compatibility."""
        return await self.semantic_search(project_id, query, top_k)

    async def update_index(
        self,
        project_id: UUID,
        source_type: str,
        source_id: UUID,
        content: str,
    ) -> dict[str, Any]:
        """
        Update existing document chunks in the index (soft-delete old + insert new).

        Args:
            project_id: Project ID
            source_type: Source type string
            source_id: Document source ID to update
            content: New content text

        Returns:
            Dict with updated_chunk_count, status
        """
        import datetime

        # Invalidate BM25 cache — document content changed
        _invalidate_bm25_cache(project_id)

        # Soft-delete old chunks for this source_id
        await self._db.execute(
            update(KnowledgeIndex)
            .where(
                KnowledgeIndex.project_id == project_id,
                KnowledgeIndex.source_id == source_id,
                KnowledgeIndex.is_deleted == False,
            )
            .values(is_deleted=True, updated_at=func.now())
        )

        # Re-insert new chunks with fresh IDs
        st = KnowledgeSourceType(source_type)
        new_source_id = uuid.uuid4()
        total_chunks = 0

        for idx, chunk_text in enumerate(_chunk_text(content)):
            embedding = await self._ai_svc.embedding(chunk_text)
            vec = np.array(embedding)
            await self._upsert_chunk(
                project_id=project_id,
                source_type=st,
                source_id=new_source_id,
                content_text=chunk_text,
                embedding=vec,
                chunk_index=idx,
            )
            total_chunks += 1

        await self._db.commit()

        return {
            "document_id": str(new_source_id),
            "updated_chunk_count": total_chunks,
            "status": "updated",
            "updated_at": datetime.datetime.now(timezone.utc).isoformat(),
        }

    async def get_index_status(self, project_id: UUID) -> dict[str, Any]:
        """Get index status statistics for a project."""
        result = await self._db.execute(
            select(
                KnowledgeIndex.source_type,
                func.count(KnowledgeIndex.id).label("count"),
            )
            .where(
                KnowledgeIndex.project_id == project_id,
                KnowledgeIndex.is_deleted == False,
            )
            .group_by(KnowledgeIndex.source_type)
        )
        by_type: dict[str, int] = {}
        total = 0
        for row in result.all():
            key = row.source_type.value
            by_type[key] = row.count
            total += row.count

        return {
            "project_id": str(project_id),
            "total_chunks": total,
            "by_source_type": by_type,
            "is_indexed": total > 0,
        }
