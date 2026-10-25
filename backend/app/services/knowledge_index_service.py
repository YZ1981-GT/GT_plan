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
import weakref
from typing import Any, Iterable
from uuid import UUID

import numpy as np
from sqlalchemy import select, update, func
from sqlalchemy import text as sa_text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

import logging

from app.models.ai_models import KnowledgeIndex, KnowledgeSourceType
from app.models.knowledge_models import KnowledgeDocument
from app.services.ai_service import AIService
from app.services.index_source import IndexSource, BusinessDataSource, KnowledgeDocSource
from app.services.knowledge_access_policy import (
    KnowledgeAccessPolicy,
    KnowledgeAccessSubject,
    KnowledgeRetrievalMode,
)
from app.services.knowledge_doc_search import (
    DocSearchRequest,
    KnowledgeDocSearch,
    escape_like,
)
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


# ─── 检索辅助（spec knowledge-base-retrieval-and-authz-closure）────────────────

_SEARCH_SCOPES = frozenset({"project_data", "knowledge_doc", "all"})

#: 引擎 → ``knowledge_index.embedding_vec`` 是否存在（进程级缓存；弱引用不阻止引擎回收）
_PGVECTOR_COLUMN_CACHE: "weakref.WeakKeyDictionary[Any, bool]" = weakref.WeakKeyDictionary()


def _scope_conditions(scope: str) -> list[Any]:
    if scope == "project_data":
        return [KnowledgeIndex.source_type != KnowledgeSourceType.knowledge_doc]
    if scope == "knowledge_doc":
        return [KnowledgeIndex.source_type == KnowledgeSourceType.knowledge_doc]
    return []


def _chunk_hit(chunk: Any, score: float, retrieval: str) -> dict[str, Any]:
    """索引分块 → 统一结果 dict（向量 / BM25 / ILIKE 共用）。"""
    st = chunk.source_type
    return {
        "source_type": st.value if hasattr(st, "value") else str(st),
        "source_id": str(chunk.source_id),
        "content": chunk.content_text,
        "score": round(float(score), 4),
        "chunk_index": chunk.chunk_index,
        "doc_version": getattr(chunk, "doc_version", None),
        "is_stale": getattr(chunk, "is_stale", False),
        "retrieval": retrieval,
    }


def _coerce_uuid_tuple(values: Iterable[Any]) -> tuple[UUID, ...]:
    out: list[UUID] = []
    for v in values or ():
        try:
            u = v if isinstance(v, UUID) else UUID(str(v))
        except (ValueError, TypeError, AttributeError):
            continue
        if u not in out:
            out.append(u)
    return tuple(out)


def _merge_hits(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同 (source_type, source_id, chunk_index) 去重保留高分；保持首次出现的相对顺序。"""
    best: dict[tuple, dict[str, Any]] = {}
    order: list[tuple] = []
    for r in results:
        key = (r.get("source_type"), str(r.get("source_id")), r.get("chunk_index"))
        prev = best.get(key)
        if prev is None:
            best[key] = r
            order.append(key)
        elif float(r.get("score") or 0.0) > float(prev.get("score") or 0.0):
            best[key] = r
    return [best[k] for k in order]


def _hit_sort_key(r: dict[str, Any]) -> float:
    """按分数降序；Python 排序稳定，同分保持来源内部顺序（词法层同分按更新时间）。"""
    return -float(r.get("score") or 0.0)


class KnowledgeIndexService:
    def __init__(self, db: AsyncSession):
        self._db = db
        self._ai_svc = AIService(db)
        # 文档正文词法检索（方案 A 权威层）；测试可替换
        self._doc_search = KnowledgeDocSearch(db)

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

    # -------------------------------------------------------------------------
    # 检索（spec knowledge-base-retrieval-and-authz-closure Req 1 / 3 / 4）
    # -------------------------------------------------------------------------

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
        restrict_to: Iterable[Any] | None = None,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """项目内知识检索主入口：向量（可选加速）+ 文档正文词法（权威）+ 业务数据兜底。

        Args:
            project_id: 当前项目（检索可见性按 project 模式与之求交）
            query: 查询文本；空查询跳过向量检索，知识文档走「按更新时间列表」模式
            top_k: 返回条数
            scope: ``project_data`` / ``knowledge_doc`` / ``all``（``cross_year`` 视为 all）
            user: 当前用户；None = 后台/系统调用 → 只返回 public 与当前项目组文档
            wp_code / account_code / audit_area: 上下文相关性加权（V119）
            restrict_to: 文档 ID 与文件夹 ID（含子树）的并集，在截断 top_k **之前**生效
            category: 预设分类，该分类子树内文档排序加分（不做硬过滤）

        流程：
          ① 向量召回（embedding 与 pgvector 均可用时）；knowledge_doc 命中经单一判定面过滤
          ② 文档正文词法检索 —— scope 含 knowledge_doc 时**始终**执行（索引缺席也成立）
          ③ 向量不可用时，业务数据（project_data）沿用 BM25 / ILIKE 兜底
          合并去重 → 上下文加权 → 排序截断 → 附 document_name / folder_path

        每条结果带 ``retrieval``（vector / lexical / bm25 / ilike）。每条读 ``knowledge_index``
        的语句都在 SAVEPOINT 内执行：失败只回滚它自己，**不会**毒化调用方会话（Req 1）。

        🔴 契约反转（design §十 C1）：``user=None`` 时 knowledge_doc 结果不再「不过滤」。
        """
        if scope == "cross_year":
            # cross_year 需要 prior_project_id（见 search_cross_year），此处按 all 处理
            scope = "all"
        if scope not in _SEARCH_SCOPES:
            raise ValueError(f"不支持的检索范围：{scope}")
        text_query = (query or "").strip()
        restrict = tuple(restrict_to or ())
        subject = await self._resolve_subject(user)

        vector_hits: list[dict[str, Any]] = []
        vector_ok = False
        if text_query:
            try:
                vector_hits = await self._vector_search(project_id, text_query, top_k, scope)
                vector_ok = True
            except Exception as exc:  # noqa: BLE001 - 向量层是可选加速，失败即降级
                logger.warning(
                    "向量召回不可用，改用文档词法检索：%s: %s", type(exc).__name__, exc
                )

        results: list[dict[str, Any]] = []
        if vector_hits:
            results.extend(
                await self._filter_by_permission(
                    vector_hits, user, project_id=project_id, subject=subject, restrict_to=restrict
                )
            )
        if scope in ("knowledge_doc", "all"):
            results.extend(
                await self._lexical_doc_hits(
                    DocSearchRequest(
                        query=text_query,
                        mode=KnowledgeRetrievalMode.project,
                        subject=subject,
                        project_id=project_id,
                        top_k=top_k,
                        restrict_to=_coerce_uuid_tuple(restrict),
                        category=category,
                    )
                )
            )
        if not vector_ok and text_query and scope in ("project_data", "all"):
            results.extend(await self._index_lexical_fallback(project_id, text_query, top_k))

        results = _merge_hits(results)
        # V119: 上下文相关性加权
        if wp_code or account_code or audit_area:
            results = _apply_context_boost(results, wp_code, account_code, audit_area)
        results.sort(key=_hit_sort_key)
        return await self._enrich_results(results[:top_k])

    async def semantic_search_strict(
        self,
        project_id: UUID,
        query: str,
        top_k: int = 10,
        *,
        scope: str = "all",
        user: Any | None = None,
    ) -> list[dict[str, Any]]:
        """**严格**语义检索 — 只走 embedding，失败即抛，绝不 BM25/ILIKE/词法伪降级。

        与 :meth:`semantic_search` 的区别是**没有任何词法兜底**：``semantic_search`` 在向量
        召回失败时照样返回词法结果，把「语义检索服务坏了」表现成「搜到了几条结果」。对 DSH
        Agent / MCP 这类**机器消费方**这是不可接受的 —— Agent 无法据此判断该不该重试，也无法
        向审计师如实说明检索没生效（dsh-agent-panel-integration Req 6.6 / Property 16）。

        Returns:
            命中列表；**空列表 = 真的没有匹配**（不是服务不可用）。命中同样经单一判定面过滤。

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

        results = await self._filter_by_permission(results, user, project_id=project_id)
        return await self._enrich_results(results)

    async def search_global_knowledge(
        self,
        query: str,
        *,
        user: Any,
        top_k: int = 10,
        restrict_to: Iterable[Any] | None = None,
    ) -> list[dict[str, Any]]:
        """无项目上下文的受限全局知识检索（global 模式，仅文档词法）。

        只返回当前用户可读、且**非** project_group 的文档 —— 没有项目上下文时不注入任何
        项目组资料（Req 3.4）；也不查向量索引（索引按项目分区，无项目即无分区可查）。
        """
        if user is None:
            raise ValueError("全局知识检索必须提供当前用户")
        subject = await self._resolve_subject(user)
        hits = await self._lexical_doc_hits(
            DocSearchRequest(
                query=(query or "").strip(),
                mode=KnowledgeRetrievalMode.global_,
                subject=subject,
                project_id=None,
                top_k=top_k,
                restrict_to=_coerce_uuid_tuple(restrict_to or ()),
            )
        )
        hits.sort(key=_hit_sort_key)
        return await self._enrich_results(hits[:top_k])

    async def load_documents(
        self,
        doc_ids: Iterable[Any],
        *,
        user: Any | None,
        project_id: UUID,
    ) -> list[dict[str, Any]]:
        """按 ID 读取检索可见的知识文档全文（project 模式；显式点名的旧版本同样可读）。

        用于「用户在界面上选定了哪几篇作参考」的场景（A17-1 等）：客户端传来的 ID **不可信**，
        每一篇都要过单一判定面；不可见 / 已删除的静默跳过（不暴露存在性）。保持入参顺序。
        """
        ids = _coerce_uuid_tuple(doc_ids)
        if not ids:
            return []
        subject = await self._resolve_subject(user)
        try:
            async with self._db.begin_nested():
                visible = await self._doc_search.visible_documents(
                    ids,
                    mode=KnowledgeRetrievalMode.project,
                    subject=subject,
                    project_id=project_id,
                    allow_superseded=ids,
                )
                contents = await self._doc_search.load_contents(list(visible))
        except Exception as exc:  # noqa: BLE001 - fail-closed：读不到就当没有
            logger.warning("按 ID 读取知识文档失败（返回空）：%s: %s", type(exc).__name__, exc)
            return []
        out: list[dict[str, Any]] = []
        for doc_id in ids:
            meta = visible.get(doc_id)
            if meta is None:
                continue
            out.append({
                "source_type": "knowledge_doc",
                "source_id": str(doc_id),
                "document_name": meta.name,
                "folder_id": str(meta.folder_id),
                "doc_version": meta.version,
                "content": contents.get(doc_id, ""),
            })
        return out

    # -------------------------------------------------------------------------
    # 检索内部实现
    # -------------------------------------------------------------------------

    async def _resolve_subject(self, user: Any | None) -> KnowledgeAccessSubject | None:
        """user → 判定主体；None 保持 None（project 模式的「无用户」语义）。

        成员关系查询包在 SAVEPOINT 里：解析失败只把项目集合判空（fail-closed），不毒化会话。
        """
        if user is None:
            return None
        try:
            async with self._db.begin_nested():
                return await KnowledgeAccessPolicy.resolve_subject(self._db, user)
        except Exception as exc:  # noqa: BLE001
            logger.warning("知识检索主体解析失败（按无项目成员处理）：%s: %s", type(exc).__name__, exc)
            raw = getattr(user, "id", None)
            try:
                uid = raw if isinstance(raw, UUID) else (UUID(str(raw)) if raw else None)
            except (ValueError, TypeError):
                uid = None
            return KnowledgeAccessSubject(user_id=uid, project_ids=frozenset())

    async def _pgvector_column_available(self) -> bool:
        """``knowledge_index.embedding_vec`` 是否真实存在（按引擎进程级缓存）。

        V119 在 pgvector 扩展缺失时跳过该列（真库即如此）。用 information_schema 确定性探测，
        而不是「先执行、失败再猜」：后者在事务里失败一次就会毒化会话（Req 1.3）。
        探测本身失败不缓存，下次重试。
        """
        try:
            bind = self._db.get_bind()
            engine = getattr(bind, "engine", bind)
            if getattr(getattr(engine, "dialect", None), "name", None) != "postgresql":
                return False
            cached = _PGVECTOR_COLUMN_CACHE.get(engine)
            if cached is not None:
                return cached
            async with self._db.begin_nested():
                row = (
                    await self._db.execute(
                        sa_text(
                            "SELECT 1 FROM information_schema.columns "
                            "WHERE table_name = 'knowledge_index' AND column_name = 'embedding_vec' "
                            "AND table_schema = ANY (current_schemas(false)) LIMIT 1"
                        )
                    )
                ).first()
            available = row is not None
            _PGVECTOR_COLUMN_CACHE[engine] = available
            return available
        except Exception as exc:  # noqa: BLE001 - 探测失败 → 本次按不可用处理
            logger.warning("pgvector 列探测失败（本次按不可用处理）：%s: %s", type(exc).__name__, exc)
            return False

    async def _vector_search(
        self,
        project_id: UUID,
        query: str,
        top_k: int,
        scope: str,
    ) -> list[dict[str, Any]]:
        """向量召回核心逻辑。embedding 不可用时抛异常，由调用方降级。

        V119：``embedding_vec``（pgvector）存在时走余弦距离 ANN；否则（真库现状）走
        ``embedding_vector`` 文本列的内存计算。同时检索项目文档与全局公共文档哨兵分区。
        两条 SQL 均在 SAVEPOINT 内执行，且非 pgvector 查询不 SELECT ``embedding_vec``。
        """
        from app.services.indexing_pipeline import GLOBAL_KB_PROJECT_ID

        query_embedding = await self._ai_svc.embedding(query)
        query_vec = np.array(query_embedding)
        query_list = query_vec.tolist()

        project_ids = [project_id, GLOBAL_KB_PROJECT_ID]
        if project_id == GLOBAL_KB_PROJECT_ID:
            project_ids = [GLOBAL_KB_PROJECT_ID]

        conditions = [
            KnowledgeIndex.project_id.in_(project_ids),
            KnowledgeIndex.is_deleted == False,  # noqa: E712
        ]
        conditions.extend(_scope_conditions(scope))

        if await self._pgvector_column_available():
            try:
                async with self._db.begin_nested():
                    distance = KnowledgeIndex.embedding_vec.cosine_distance(query_list)
                    rows = (
                        await self._db.execute(
                            select(KnowledgeIndex, (1 - distance).label("score"))
                            .options(defer(KnowledgeIndex.embedding_vec))
                            .where(*conditions)
                            .order_by(distance)
                            .limit(top_k)
                        )
                    ).all()
                return [_chunk_hit(chunk, float(score), "vector") for chunk, score in rows]
            except Exception as pgvec_err:  # noqa: BLE001 - 退到内存计算
                logger.warning("pgvector 检索失败，改用内存向量计算：%s", pgvec_err)

        async with self._db.begin_nested():
            chunks = (
                await self._db.execute(
                    select(KnowledgeIndex)
                    .options(defer(KnowledgeIndex.embedding_vec))
                    .where(*conditions)
                )
            ).scalars().all()

        scored = []
        for chunk in chunks:
            if not chunk.embedding_vector:
                continue
            chunk_vec = self._str_to_vector(chunk.embedding_vector)
            scored.append((self._cosine_similarity(query_vec, chunk_vec), chunk))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [_chunk_hit(chunk, score, "vector") for score, chunk in scored[:top_k]]

    async def _lexical_doc_hits(self, req: DocSearchRequest) -> list[dict[str, Any]]:
        """文档正文词法检索（权威层）→ 统一结果 dict。失败 fail-closed 返回空（不外抛、不毒化会话）。"""
        try:
            async with self._db.begin_nested():
                hits = await self._doc_search.search(req)
        except Exception as exc:  # noqa: BLE001
            logger.warning("知识文档词法检索失败（本次无文档命中）：%s: %s", type(exc).__name__, exc)
            return []
        return [
            {
                "source_type": KnowledgeSourceType.knowledge_doc.value,
                "source_id": str(h.meta.doc_id),
                "content": h.snippet,
                "score": h.score,
                "chunk_index": h.chunk_index,
                "doc_version": h.meta.version,
                "is_stale": False,
                "retrieval": "lexical",
                "document_name": h.meta.name,
                "folder_id": str(h.meta.folder_id),
                "matched_terms": list(h.matched_terms),
            }
            for h in hits
        ]

    async def _index_lexical_fallback(
        self, project_id: UUID, query: str, top_k: int
    ) -> list[dict[str, Any]]:
        """向量不可用时的**业务数据**兜底（知识文档已由词法层覆盖，这里只查 project_data 分块）。"""
        from app.core.config import settings as app_settings

        if app_settings.RETRIEVAL_BM25_FALLBACK_ENABLED:
            return await self._bm25_fallback(project_id, query, top_k, "project_data")
        return await self._ilike_fallback(project_id, query, top_k, "project_data")

    async def _bm25_fallback(
        self,
        project_id: UUID,
        query: str,
        top_k: int,
        scope: str,
    ) -> list[dict[str, Any]]:
        """BM25 词法检索索引分块（bm25s，纯 Python）；bm25s 缺失或建索引失败降级 ILIKE。

        带模块级缓存：key=(project_id, scope)，TTL 60s 或 incremental_update 时失效。
        """
        try:
            import bm25s
        except ImportError:
            logger.warning("bm25s 未安装，降级 ilike")
            return await self._ilike_fallback(project_id, query, top_k, scope)

        from app.services._zh_tokenize import zh_tokenize, zh_tokenize_batch

        query_tokens = zh_tokenize(query)
        if not query_tokens:
            return await self._ilike_fallback(project_id, query, top_k, scope)

        cache_key = (str(project_id), scope)
        now = time.time()
        cached = _BM25_CACHE.get(cache_key)
        if cached is not None:
            retriever, chunks, build_time = cached
            if (now - build_time) < _BM25_CACHE_TTL:
                return self._bm25_retrieve(retriever, chunks, query_tokens, top_k)
            del _BM25_CACHE[cache_key]

        conditions = [
            KnowledgeIndex.project_id == project_id,
            KnowledgeIndex.is_deleted == False,  # noqa: E712
            *_scope_conditions(scope),
        ]
        try:
            async with self._db.begin_nested():
                chunks = (
                    await self._db.execute(
                        select(KnowledgeIndex)
                        .options(defer(KnowledgeIndex.embedding_vec))
                        .where(*conditions)
                    )
                ).scalars().all()
        except Exception as exc:  # noqa: BLE001
            logger.warning("BM25 候选加载失败（本次无业务数据命中）：%s: %s", type(exc).__name__, exc)
            return []
        if not chunks:
            return []

        corpus_tokens = zh_tokenize_batch([c.content_text or "" for c in chunks])
        try:
            retriever = bm25s.BM25()
            retriever.index(corpus_tokens)
        except Exception as exc:
            logger.warning("BM25 索引构建失败，降级 ilike: %s", exc)
            return await self._ilike_fallback(project_id, query, top_k, scope)

        _BM25_CACHE[cache_key] = (retriever, chunks, now)
        return self._bm25_retrieve(retriever, chunks, query_tokens, top_k)

    @staticmethod
    def _bm25_retrieve(
        retriever: Any,
        chunks: list,
        query_tokens: list[str],
        top_k: int,
    ) -> list[dict[str, Any]]:
        """从已构建的 BM25 索引中检索 top_k 结果（缓存命中与新建索引共用）。"""
        try:
            k = min(top_k, len(chunks))
            indices, scores = retriever.retrieve([query_tokens], k=k)
            idx_list = indices[0].tolist() if hasattr(indices[0], "tolist") else list(indices[0])
            score_list = scores[0].tolist() if hasattr(scores[0], "tolist") else list(scores[0])
        except Exception:
            return []

        max_score = max(score_list) if score_list else 0.0
        out: list[dict[str, Any]] = []
        for rank, idx in enumerate(idx_list):
            if idx < 0 or idx >= len(chunks):
                continue
            raw_score = float(score_list[rank]) if rank < len(score_list) else 0.0
            normalized = (raw_score / max_score) if max_score > 0 else 0.0
            out.append(_chunk_hit(chunks[int(idx)], normalized, "bm25"))
        return out[:top_k]

    async def _ilike_fallback(
        self,
        project_id: UUID,
        query: str,
        top_k: int,
        scope: str,
    ) -> list[dict[str, Any]]:
        """ILIKE 子串匹配索引分块（最后兜底）。失败返回空，不外抛。"""
        pattern = f"%{escape_like(query)}%"
        conditions = [
            KnowledgeIndex.project_id == project_id,
            KnowledgeIndex.is_deleted == False,  # noqa: E712
            KnowledgeIndex.content_text.ilike(pattern, escape="\\"),
            *_scope_conditions(scope),
        ]
        try:
            async with self._db.begin_nested():
                chunks = (
                    await self._db.execute(
                        select(KnowledgeIndex)
                        .options(defer(KnowledgeIndex.embedding_vec))
                        .where(*conditions)
                        .limit(top_k)
                    )
                ).scalars().all()
        except Exception as exc:  # noqa: BLE001
            logger.warning("ILIKE 兜底失败（本次无业务数据命中）：%s: %s", type(exc).__name__, exc)
            return []
        return [_chunk_hit(chunk, 0.0, "ilike") for chunk in chunks]

    async def _filter_by_permission(
        self,
        results: list[dict[str, Any]],
        user: Any | None,
        *,
        project_id: UUID | None = None,
        subject: KnowledgeAccessSubject | None = None,
        restrict_to: Iterable[Any] = (),
    ) -> list[dict[str, Any]]:
        """knowledge_doc 命中（通常来自向量层）按**单一判定面**过滤（Req 3.7）。

        起点是 ``knowledge_documents``（不是 ``knowledge_index``）：已删除、所在文件夹已删除、
        被新版本取代（restrict_to 点名者除外）、不在 restrict_to 范围内的一律剔除。
        ``user=None`` → project 模式无用户判定（public + 当前项目组，private 永不）。
        非 knowledge_doc 结果原样保留（业务数据按项目分区，由路由层项目权限隔离）。
        判定失败 fail-closed：丢弃全部文档命中，只保留业务数据。
        """
        if not results:
            return results
        doc_results = [r for r in results if r.get("source_type") == KnowledgeSourceType.knowledge_doc.value]
        other = [r for r in results if r.get("source_type") != KnowledgeSourceType.knowledge_doc.value]
        if not doc_results:
            return results
        if project_id is None:
            logger.warning("知识文档命中缺少 project_id，无法做项目范围判定 → 全部丢弃（fail-closed）")
            return other
        if subject is None and user is not None:
            subject = await self._resolve_subject(user)
        restrict = _coerce_uuid_tuple(restrict_to)
        try:
            async with self._db.begin_nested():
                explicit_docs, folder_scope = await self._doc_search.resolve_restriction(restrict)
                visible = await self._doc_search.visible_documents(
                    [r.get("source_id") for r in doc_results],
                    mode=KnowledgeRetrievalMode.project,
                    subject=subject,
                    project_id=project_id,
                    allow_superseded=explicit_docs,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("知识文档权限判定失败（丢弃全部文档命中）：%s: %s", type(exc).__name__, exc)
            return other

        allowed: list[dict[str, Any]] = []
        for r in doc_results:
            try:
                doc_id = UUID(str(r.get("source_id")))
            except (ValueError, TypeError):
                continue
            meta = visible.get(doc_id)
            if meta is None:
                continue
            if restrict and doc_id not in explicit_docs and meta.folder_id not in folder_scope:
                continue
            r.setdefault("document_name", meta.name)
            r.setdefault("folder_id", str(meta.folder_id))
            if r.get("doc_version") is None:
                r["doc_version"] = meta.version
            allowed.append(r)
        return other + allowed

    async def _enrich_results(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """为 knowledge_doc 结果附加 document_name / folder_id / folder_path / folder_ancestor_ids。

        ``folder_path`` 为 ``/根/…/当前`` 完整路径（旧实现只有文件夹名）。非文档结果补 None。
        调用前结果已经过判定面（本方法不做可见性判断，只补展示元数据）。
        """
        if not results:
            return results
        doc_rows = [r for r in results if r.get("source_type") == KnowledgeSourceType.knowledge_doc.value]
        missing = [r for r in doc_rows if not r.get("document_name") or not r.get("folder_id")]
        try:
            async with self._db.begin_nested():
                if missing:
                    ids = _coerce_uuid_tuple(r.get("source_id") for r in missing)
                    rows = (
                        await self._db.execute(
                            select(KnowledgeDocument.id, KnowledgeDocument.name, KnowledgeDocument.folder_id)
                            .where(KnowledgeDocument.id.in_(list(ids)))
                        )
                    ).all() if ids else []
                    by_id = {str(i): (n, f) for i, n, f in rows}
                    for r in missing:
                        name, folder = by_id.get(str(r.get("source_id")), (None, None))
                        r.setdefault("document_name", name)
                        if folder is not None and not r.get("folder_id"):
                            r["folder_id"] = str(folder)
                paths = await self._doc_search.folder_paths(
                    r.get("folder_id") for r in doc_rows if r.get("folder_id")
                )
        except Exception as exc:  # noqa: BLE001 - 展示元数据缺失不影响检索结果本身
            logger.warning("知识检索结果补充展示信息失败：%s: %s", type(exc).__name__, exc)
            paths = {}

        for r in results:
            if r.get("source_type") != KnowledgeSourceType.knowledge_doc.value:
                r.setdefault("document_name", None)
                r.setdefault("folder_id", None)
                r.setdefault("folder_path", None)
                r.setdefault("folder_ancestor_ids", [])
                continue
            r.setdefault("document_name", None)
            fp = None
            try:
                fp = paths.get(UUID(str(r.get("folder_id")))) if r.get("folder_id") else None
            except (ValueError, TypeError):
                fp = None
            r["folder_path"] = fp.path if fp else None
            r["folder_ancestor_ids"] = [str(x) for x in fp.ancestor_ids] if fp else []
        return results

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
        # SAVEPOINT：读失败只回滚自身，异常照常上抛但调用方会话保持可用（Req 1.1）
        async with self._db.begin_nested():
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
        # SAVEPOINT：读失败只回滚自身，异常照常上抛但调用方会话保持可用（Req 1.1）
        async with self._db.begin_nested():
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
            rows = result.all()
        by_type: dict[str, int] = {}
        total = 0
        for row in rows:
            key = row.source_type.value
            by_type[key] = row.count
            total += row.count

        return {
            "project_id": str(project_id),
            "total_chunks": total,
            "by_source_type": by_type,
            "is_indexed": total > 0,
        }
