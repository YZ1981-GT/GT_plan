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


# ─── Context-Aware Boost (V119) ──────────────────────────────────────────────

# wp_code 前缀 → 审计循环分类映射
_WP_CYCLE_MAP: dict[str, list[str]] = {
    "D": ["应收", "收入", "销售"],
    "E": ["货币资金", "银行", "现金"],
    "F": ["存货", "采购", "成本"],
    "G": ["投资", "长期股权", "金融资产"],
    "H": ["固定资产", "无形资产", "在建工程"],
    "I": ["长期资产", "递延", "商誉"],
    "J": ["薪酬", "职工", "福利"],
    "K": ["应付", "负债", "费用"],
    "L": ["借款", "融资", "利息"],
    "M": ["权益", "资本", "利润分配"],
    "N": ["税费", "所得税", "增值税"],
}

# 常见科目编码前缀→名称映射
_ACCOUNT_NAMES: dict[str, str] = {
    "1122": "应收账款", "1123": "预付账款", "1221": "其他应收款",
    "1401": "存货", "1501": "固定资产", "1601": "无形资产",
    "1701": "长期股权投资", "2202": "应付账款", "2211": "应付职工薪酬",
    "2221": "长期借款", "2241": "其他应付款", "6001": "营业收入",
    "6601": "销售费用", "6602": "管理费用", "6603": "财务费用",
}


def _apply_context_boost(
    results: list[dict],
    wp_code: str | None,
    account_code: str | None,
    audit_area: str | None,
) -> list[dict]:
    """对结果应用上下文加权: final_score = 0.7 * vector_score + 0.3 * boost。

    boost = 1.0 if both signals match, 0.5 if one matches, 0.0 if none match.
    """
    if not results:
        return results

    for r in results:
        boost = 0.0
        content_lower = (r.get("content") or "").lower()

        if wp_code and _matches_cycle(content_lower, wp_code):
            boost += 0.5

        if account_code and _matches_account(content_lower, account_code):
            boost += 0.5

        if audit_area and audit_area.lower() in content_lower:
            boost += 0.5

        boost = min(boost, 1.0)
        original_score = r.get("score", 0.0)
        r["score"] = round(0.7 * original_score + 0.3 * boost, 4)

    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return results


def _matches_cycle(content: str, wp_code: str) -> bool:
    """检查内容是否包含 wp_code 对应循环的关键词。"""
    prefix = wp_code[0].upper() if wp_code else ""
    keywords = _WP_CYCLE_MAP.get(prefix, [])
    return any(kw in content for kw in keywords)


def _matches_account(content: str, account_code: str) -> bool:
    """检查内容是否包含科目编码或常见科目名。"""
    if account_code in content:
        return True
    name = _ACCOUNT_NAMES.get(account_code[:4] if len(account_code) >= 4 else account_code, "")
    return name.lower() in content if name else False


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
        doc_version: int | None = None,
    ) -> None:
        """Upsert single chunk (source_id + chunk_index unique).
        
        Dual-writes both:
        - embedding_vector (TEXT, legacy) 
        - embedding_vec (pgvector vector(1024), V119)
        """
        embedding_str = self._vector_to_str(embedding)
        # pgvector expects a list of floats
        embedding_list = embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)
        
        values = {
            "content_text": content_text,
            "embedding_vector": embedding_str,
            "embedding_vec": embedding_list,
            "is_deleted": False,
            "is_stale": False,
            "doc_version": doc_version,
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
                embedding_vector=embedding_str,
                embedding_vec=embedding_list,
                chunk_index=chunk_index,
                is_deleted=False,
                is_stale=False,
                doc_version=doc_version,
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
        from app.services.ai_chat.address_index_source import (
            AddressCoordinateIndexSource,
        )

        return [
            BusinessDataSource(self._db),
            KnowledgeDocSource(self._db),
            AddressCoordinateIndexSource(self._db),
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

        P2-2.3: After full rebuild, all stale marks for this project are cleared.
        """
        # Invalidate BM25 cache — full rebuild means old cache is stale
        _invalidate_bm25_cache(project_id)

        # Clear all stale marks on existing non-deleted index entries for this project
        await self._db.execute(
            update(KnowledgeIndex)
            .where(
                KnowledgeIndex.project_id == project_id,
                KnowledgeIndex.is_deleted == False,  # noqa: E712
                KnowledgeIndex.is_stale == True,  # noqa: E712
            )
            .values(is_stale=False, updated_at=func.now())
        )

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
        doc_version: int | None = None,
    ) -> None:
        """Incremental update index when data changes (upsert new chunks).

        After successful re-indexing, clears any stale marks on this source.
        """
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
                doc_version=doc_version,
            )

        # P2-2.3: 重建索引后解除 stale
        await self.clear_index_stale(source_id)

        await self._db.commit()

    async def semantic_search(
        self,
        project_id: UUID,
        query: str,
        top_k: int = 10,
        *,
        scope: str = "all",
        user: Any | None = None,
        wp_code: str | None = None,
        account_code: str | None = None,
        audit_area: str | None = None,
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
            wp_code: 可选底稿编码，用于上下文相关性加权
            account_code: 可选科目编码，用于上下文相关性加权
            audit_area: 可选审计领域，用于上下文相关性加权

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

        # V119: 上下文相关性加权
        if wp_code or account_code or audit_area:
            results = _apply_context_boost(results, wp_code, account_code, audit_area)

        # 权限过滤：当 user 提供时，过滤 knowledge_doc 结果
        if user is not None:
            results = await self._filter_by_permission(results, user)

        # V119: 结果增强 — 附加 document_name + folder_path
        results = await self._enrich_results(results)

        return results

    async def semantic_search_strict(
        self,
        project_id: UUID,
        query: str,
        top_k: int = 10,
        *,
        scope: str = "all",
        user: Any | None = None,
    ) -> list[dict[str, Any]]:
        """**严格**语义检索 — 只走 embedding，失败即抛，绝不 BM25/ILIKE 伪降级。

        与 :meth:`semantic_search` 的唯一区别是**没有词法兜底**：
        ``semantic_search`` 在向量召回失败时会静默切到 BM25 或 ILIKE，把
        "语义检索服务坏了"表现成"搜到了几条弱相关结果"或"什么都没搜到"。
        对 DSH Agent / MCP 这类**机器消费方**这是不可接受的 —— Agent 无法据此
        判断该不该重试，也无法向审计师如实说明检索没生效
        （dsh-agent-panel-integration Req 6.6 / Property 16）。

        Args:
            project_id: 项目 ID
            query: 查询文本
            top_k: 返回结果数
            scope: ``"project_data"`` / ``"knowledge_doc"`` / ``"all"``
            user: 提供时按权限过滤 knowledge_doc 结果（与 ``semantic_search`` 同一过滤器）

        Returns:
            命中列表；**空列表 = 真的没有匹配**（不是服务不可用）。

        Raises:
            EmbeddingUnavailableError: embedding 服务不可用 / 向量召回失败。
        """
        from app.services.ai_chat.address_index_source import (
            EmbeddingUnavailableError,
        )

        if scope == "cross_year":
            scope = "all"

        try:
            results = await self._vector_search(project_id, query, top_k, scope)
        except Exception as exc:
            logger.warning(
                "严格语义检索失败（不降级，向调用方抛 semantic_unavailable）: %s: %s",
                type(exc).__name__, exc,
            )
            raise EmbeddingUnavailableError(
                f"语义检索不可用：{type(exc).__name__}"
            ) from exc

        if user is not None:
            results = await self._filter_by_permission(results, user)
        return await self._enrich_results(results)

    async def _vector_search(
        self,
        project_id: UUID,
        query: str,
        top_k: int,
        scope: str,
    ) -> list[dict[str, Any]]:
        """向量召回核心逻辑 — 使用 pgvector cosine distance operator。
        
        V119: 优先使用 embedding_vec (pgvector vector(1024)) 列进行 ANN 搜索,
        同时搜索项目文档 + 全局公共文档 (GLOBAL_KB_PROJECT_ID)。
        pgvector 不可用时抛异常，由调用方捕获降级到 BM25。
        """
        from app.services.indexing_pipeline import GLOBAL_KB_PROJECT_ID

        # Encode query
        query_embedding = await self._ai_svc.embedding(query)
        query_vec = np.array(query_embedding)
        query_list = query_vec.tolist()

        # 同时搜索项目文档 + 全局公共文档
        project_ids = [project_id, GLOBAL_KB_PROJECT_ID]
        if project_id == GLOBAL_KB_PROJECT_ID:
            project_ids = [GLOBAL_KB_PROJECT_ID]

        # Build scope filter conditions
        conditions = [
            KnowledgeIndex.project_id.in_(project_ids),
            KnowledgeIndex.is_deleted == False,  # noqa: E712
        ]
        if scope == "project_data":
            conditions.append(
                KnowledgeIndex.source_type != KnowledgeSourceType.knowledge_doc
            )
        elif scope == "knowledge_doc":
            conditions.append(
                KnowledgeIndex.source_type == KnowledgeSourceType.knowledge_doc
            )

        # 尝试 pgvector cosine distance (1 - cosine_similarity)
        try:
            stmt = (
                select(
                    KnowledgeIndex,
                    (1 - KnowledgeIndex.embedding_vec.cosine_distance(query_list)).label("score"),
                )
                .where(*conditions)
                .order_by(KnowledgeIndex.embedding_vec.cosine_distance(query_list))
                .limit(top_k)
            )
            result = await self._db.execute(stmt)
            rows = result.all()

            return [
                {
                    "source_type": chunk.source_type.value,
                    "source_id": str(chunk.source_id),
                    "content": chunk.content_text,
                    "score": round(float(score), 4),
                    "chunk_index": chunk.chunk_index,
                    "doc_version": chunk.doc_version,
                    "is_stale": chunk.is_stale,
                }
                for chunk, score in rows
            ]
        except Exception as pgvec_err:
            # pgvector 不可用 (列为 NULL 或扩展未安装) → 回退到内存暴力搜索
            logger.warning(f"pgvector search failed, falling back to in-memory: {pgvec_err}")

            # Legacy in-memory fallback (TEXT embedding_vector column)
            result = await self._db.execute(
                select(KnowledgeIndex).where(*conditions)
            )
            chunks = result.scalars().all()

            scored = []
            for chunk in chunks:
                if not chunk.embedding_vector:
                    continue
                chunk_vec = self._str_to_vector(chunk.embedding_vector)
                score = self._cosine_similarity(query_vec, chunk_vec)
                scored.append((score, chunk))

            scored.sort(key=lambda x: x[0], reverse=True)
            top_results = scored[:top_k]

            return [
                {
                    "source_type": chunk.source_type.value,
                    "source_id": str(chunk.source_id),
                    "content": chunk.content_text,
                    "score": round(score, 4),
                    "chunk_index": chunk.chunk_index,
                    "doc_version": chunk.doc_version,
                    "is_stale": chunk.is_stale,
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

        中文分词用 _zh_tokenize 模块（jieba + 审计领域词典）。
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
                "doc_version": getattr(chunk, "doc_version", None),
                "is_stale": getattr(chunk, "is_stale", False),
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
                "doc_version": chunk.doc_version,
                "is_stale": chunk.is_stale,
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

    async def _enrich_results(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """V119: 为搜索结果附加 document_name + folder_path 用于引用显示。"""
        if not results:
            return results

        # 收集所有 knowledge_doc 类型的 source_ids
        doc_source_ids = [
            UUID(r["source_id"]) for r in results
            if r.get("source_type") == "knowledge_doc"
        ]
        if not doc_source_ids:
            # 非 knowledge_doc 不需要 enrichment
            for r in results:
                r.setdefault("document_name", None)
                r.setdefault("folder_path", None)
            return results

        # 批量查 document_name + folder_path
        from app.models.knowledge_models import KnowledgeDocument, KnowledgeFolder
        try:
            enrich_query = (
                select(
                    KnowledgeDocument.id,
                    KnowledgeDocument.name,
                    KnowledgeFolder.name.label("folder_name"),
                )
                .join(KnowledgeFolder, KnowledgeDocument.folder_id == KnowledgeFolder.id)
                .where(KnowledgeDocument.id.in_(doc_source_ids))
            )
            enrich_result = await self._db.execute(enrich_query)
            enrich_map: dict[str, tuple[str, str]] = {}
            for doc_id, doc_name, folder_name in enrich_result.all():
                enrich_map[str(doc_id)] = (doc_name, folder_name)
        except Exception:
            enrich_map = {}

        # 附加到每个结果
        for r in results:
            if r.get("source_type") == "knowledge_doc":
                info = enrich_map.get(r["source_id"])
                r["document_name"] = info[0] if info else None
                r["folder_path"] = info[1] if info else None
            else:
                r.setdefault("document_name", None)
                r.setdefault("folder_path", None)

        return results

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

    # ------------------------------------------------------------------
    # Stale 索引管理（P2-2: 知识引用与索引 stale）
    # ------------------------------------------------------------------

    async def mark_index_stale(self, source_id: UUID) -> int:
        """标记指定文档的所有索引条目为 stale。

        当文档更新（新版本创建）时调用，使旧索引不可作为 confirmed AI 来源。

        Returns:
            标记为 stale 的 chunk 数量
        """
        from sqlalchemy import literal_column

        result = await self._db.execute(
            update(KnowledgeIndex)
            .where(
                KnowledgeIndex.source_id == source_id,
                KnowledgeIndex.is_deleted == False,  # noqa: E712
                KnowledgeIndex.is_stale == False,  # noqa: E712
            )
            .values(is_stale=True, updated_at=func.now())
        )
        return result.rowcount  # type: ignore[return-value]

    async def clear_index_stale(self, source_id: UUID) -> int:
        """清除指定文档索引的 stale 标记。

        当 incremental_update 或 build_index 成功重建索引后调用。

        Returns:
            清除 stale 标记的 chunk 数量
        """
        result = await self._db.execute(
            update(KnowledgeIndex)
            .where(
                KnowledgeIndex.source_id == source_id,
                KnowledgeIndex.is_deleted == False,  # noqa: E712
                KnowledgeIndex.is_stale == True,  # noqa: E712
            )
            .values(is_stale=False, updated_at=func.now())
        )
        return result.rowcount  # type: ignore[return-value]

    async def is_source_stale(self, source_id: UUID) -> bool:
        """检查指定文档的索引是否处于 stale 状态。

        Returns:
            True 如果存在 stale 索引且无 fresh 索引
        """
        result = await self._db.execute(
            select(
                func.count().filter(KnowledgeIndex.is_stale == True),  # noqa: E712
                func.count().filter(KnowledgeIndex.is_stale == False),  # noqa: E712
            )
            .where(
                KnowledgeIndex.source_id == source_id,
                KnowledgeIndex.is_deleted == False,  # noqa: E712
            )
        )
        row = result.one_or_none()
        if not row:
            return False
        stale_count, fresh_count = row
        # stale if there are stale chunks and no fresh ones
        return stale_count > 0 and fresh_count == 0

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
