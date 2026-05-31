"""
VectorStore Protocol + PgTextStore 实现

可插拔向量存储抽象层：
- VectorStore: @runtime_checkable Protocol（add/query/delete）
- PgTextStore: 包装现状（KnowledgeIndex 逗号串 + numpy 全扫 O(N)），保留降级

设计文档：.kiro/specs/retrieval-kernel-unification/design.md §三 组件3
需求：3.1（VectorStore 抽象 + PgTextStore + PgVectorStore）
属性：R4（PgTextStore 与 PgVectorStore 对同一 query top_k 结果集一致）

key 格式: "{project_id}:{source_type}:{source_id}:{chunk_index}"
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

import numpy as np
from sqlalchemy import select, update, func, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_models import KnowledgeIndex, KnowledgeSourceType

logger = logging.getLogger(__name__)


@runtime_checkable
class VectorStore(Protocol):
    """可插拔向量存储协议。

    三个核心方法：
    - add: 存储向量 + 元数据
    - query: 向量相似度检索 top_k
    - delete: 删除指定 key 的向量

    key 格式: "{project_id}:{source_type}:{source_id}:{chunk_index}"
    """

    async def add(self, key: str, embedding: list[float], meta: dict) -> None:
        """存储向量。

        Args:
            key: 唯一标识，格式 "{project_id}:{source_type}:{source_id}:{chunk_index}"
            embedding: 向量（float 列表）
            meta: 元数据字典，至少包含 content_text
        """
        ...

    async def query(self, embedding: list[float], top_k: int) -> list[tuple[str, float]]:
        """向量相似度检索。

        Args:
            embedding: 查询向量
            top_k: 返回前 k 个最相似结果

        Returns:
            [(key, score)] 按相似度降序排列
        """
        ...

    async def delete(self, key: str) -> None:
        """删除指定 key 的向量（软删除）。

        Args:
            key: 唯一标识
        """
        ...


class PgTextStore:
    """PG 文本列向量存储 — 包装现状（逗号串 + numpy 全扫）。

    保留为降级/fallback 路径。行为与 KnowledgeIndexService 原有逻辑完全一致：
    - add: 存 embedding 为逗号分隔字符串到 KnowledgeIndex.embedding_vector
    - query: 加载所有向量，numpy 计算余弦相似度，返回 top_k
    - delete: 软删除 KnowledgeIndex 条目（is_deleted=True）

    性能特征：O(N) 全表扫描，适合数千条级别。
    """

    def __init__(self, db: AsyncSession, *, project_id: str | None = None):
        """初始化 PgTextStore。

        Args:
            db: SQLAlchemy AsyncSession
            project_id: 可选，限定查询范围到指定项目（query 时过滤）
        """
        self._db = db
        self._project_id = project_id

    @staticmethod
    def _vector_to_str(vec: list[float]) -> str:
        """将向量转为逗号分隔字符串。"""
        return ",".join(str(v) for v in vec)

    @staticmethod
    def _str_to_vector(s: str) -> np.ndarray:
        """将逗号分隔字符串解析为 numpy 向量。"""
        return np.array([float(x) for x in s.split(",")])

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """计算两个向量的余弦相似度。"""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    @staticmethod
    def parse_key(key: str) -> tuple[str, str, str, int]:
        """解析 key 为 (project_id, source_type, source_id, chunk_index)。"""
        parts = key.split(":")
        if len(parts) != 4:
            raise ValueError(f"Invalid key format: {key}, expected 'project_id:source_type:source_id:chunk_index'")
        return parts[0], parts[1], parts[2], int(parts[3])

    @staticmethod
    def make_key(project_id: str, source_type: str, source_id: str, chunk_index: int) -> str:
        """构造 key: "{project_id}:{source_type}:{source_id}:{chunk_index}"。"""
        return f"{project_id}:{source_type}:{source_id}:{chunk_index}"

    async def add(self, key: str, embedding: list[float], meta: dict) -> None:
        """存储向量为逗号分隔字符串到 KnowledgeIndex。

        使用 upsert（ON CONFLICT DO UPDATE）保证幂等。
        """
        import uuid

        project_id_str, source_type_str, source_id_str, chunk_index = self.parse_key(key)

        try:
            source_type_enum = KnowledgeSourceType(source_type_str)
        except ValueError:
            logger.warning(f"Unknown source_type '{source_type_str}', skipping add for key={key}")
            return

        content_text = meta.get("content_text", "")

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
                project_id=uuid.UUID(project_id_str),
                source_type=source_type_enum,
                source_id=uuid.UUID(source_id_str),
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

    async def query(self, embedding: list[float], top_k: int) -> list[tuple[str, float]]:
        """全表扫描 + numpy 余弦相似度，返回 top_k [(key, score)]。

        如果设置了 project_id，只在该项目范围内搜索。
        """
        query_vec = np.array(embedding)

        conditions = [
            KnowledgeIndex.is_deleted == False,  # noqa: E712
            KnowledgeIndex.embedding_vector.isnot(None),
            KnowledgeIndex.embedding_vector != "",
        ]

        if self._project_id:
            import uuid as uuid_mod
            conditions.append(
                KnowledgeIndex.project_id == uuid_mod.UUID(self._project_id)
            )

        result = await self._db.execute(
            select(KnowledgeIndex).where(*conditions)
        )
        chunks = result.scalars().all()

        scored: list[tuple[str, float]] = []
        for chunk in chunks:
            if not chunk.embedding_vector:
                continue
            try:
                chunk_vec = self._str_to_vector(chunk.embedding_vector)
                score = self._cosine_similarity(query_vec, chunk_vec)
                key = self.make_key(
                    str(chunk.project_id),
                    chunk.source_type.value if hasattr(chunk.source_type, "value") else str(chunk.source_type),
                    str(chunk.source_id),
                    chunk.chunk_index or 0,
                )
                scored.append((key, score))
            except (ValueError, TypeError) as e:
                logger.debug(f"Skipping chunk {chunk.id} due to parse error: {e}")
                continue

        # 按相似度降序排列，取 top_k
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    async def delete(self, key: str) -> None:
        """软删除指定 key 对应的 KnowledgeIndex 条目。"""
        import uuid as uuid_mod

        project_id_str, source_type_str, source_id_str, chunk_index = self.parse_key(key)

        await self._db.execute(
            update(KnowledgeIndex)
            .where(
                KnowledgeIndex.project_id == uuid_mod.UUID(project_id_str),
                KnowledgeIndex.source_id == uuid_mod.UUID(source_id_str),
                KnowledgeIndex.chunk_index == chunk_index,
                KnowledgeIndex.is_deleted == False,  # noqa: E712
            )
            .values(is_deleted=True, updated_at=func.now())
        )


class PgVectorStore:
    """PG pgvector 向量存储 — 使用原生 vector 列 + ivfflat 索引。

    利用 pgvector 扩展的 `<=>` 余弦距离运算符在 DB 内完成相似度计算，
    配合 ivfflat 索引实现亚线性检索（替代 PgTextStore 的 O(N) numpy 全扫）。

    行为与 PgTextStore 等价（R4 属性守护），但性能更优：
    - add: 存 embedding 到原生 vector(768) 列（同时写逗号串保持向后兼容）
    - query: `ORDER BY embedding <=> $1 LIMIT $k`（DB 内余弦距离）
    - delete: 软删除（与 PgTextStore 一致）

    需求: 3.2  属性: R4
    前置: V043 迁移（CREATE EXTENSION vector + embedding vector(768) 列 + ivfflat 索引）
    """

    def __init__(self, db: AsyncSession, *, project_id: str | None = None):
        """初始化 PgVectorStore。

        Args:
            db: SQLAlchemy AsyncSession
            project_id: 可选，限定查询范围到指定项目
        """
        self._db = db
        self._project_id = project_id

    @staticmethod
    def _vector_to_str(vec: list[float]) -> str:
        """将向量转为逗号分隔字符串（向后兼容 PgTextStore）。"""
        return ",".join(str(v) for v in vec)

    @staticmethod
    def _vector_to_pgvector(vec: list[float]) -> str:
        """将向量转为 pgvector 字面量格式 '[0.1,0.2,...]'。"""
        return "[" + ",".join(str(v) for v in vec) + "]"

    @staticmethod
    def parse_key(key: str) -> tuple[str, str, str, int]:
        """解析 key 为 (project_id, source_type, source_id, chunk_index)。"""
        parts = key.split(":")
        if len(parts) != 4:
            raise ValueError(f"Invalid key format: {key}, expected 'project_id:source_type:source_id:chunk_index'")
        return parts[0], parts[1], parts[2], int(parts[3])

    @staticmethod
    def make_key(project_id: str, source_type: str, source_id: str, chunk_index: int) -> str:
        """构造 key: "{project_id}:{source_type}:{source_id}:{chunk_index}"。"""
        return f"{project_id}:{source_type}:{source_id}:{chunk_index}"

    async def add(self, key: str, embedding: list[float], meta: dict) -> None:
        """存储向量到原生 vector 列（同时写逗号串保持向后兼容）。

        使用 upsert（ON CONFLICT DO UPDATE）保证幂等。
        """
        import uuid

        project_id_str, source_type_str, source_id_str, chunk_index = self.parse_key(key)

        try:
            source_type_enum = KnowledgeSourceType(source_type_str)
        except ValueError:
            logger.warning(f"Unknown source_type '{source_type_str}', skipping add for key={key}")
            return

        content_text = meta.get("content_text", "")
        embedding_str = self._vector_to_str(embedding)
        pgvector_literal = self._vector_to_pgvector(embedding)

        values = {
            "content_text": content_text,
            "embedding_vector": embedding_str,
            "embedding": text(f"'{pgvector_literal}'::vector"),
            "is_deleted": False,
            "updated_at": func.now(),
        }

        stmt = (
            insert(KnowledgeIndex)
            .values(
                id=uuid.uuid4(),
                project_id=uuid.UUID(project_id_str),
                source_type=source_type_enum,
                source_id=uuid.UUID(source_id_str),
                content_text=content_text,
                embedding_vector=embedding_str,
                chunk_index=chunk_index,
                is_deleted=False,
            )
            .on_conflict_do_update(
                index_elements=["project_id", "source_id", "chunk_index"],
                set_=values,
            )
        )
        await self._db.execute(stmt)

    async def query(self, embedding: list[float], top_k: int) -> list[tuple[str, float]]:
        """使用 pgvector <=> 运算符进行余弦距离检索，返回 top_k [(key, score)]。

        pgvector <=> 返回余弦距离（0=完全相同，2=完全相反），
        转换为余弦相似度: similarity = 1 - distance。
        """
        pgvector_literal = self._vector_to_pgvector(embedding)

        # 构建 WHERE 条件
        conditions = [
            "is_deleted = false",
            "embedding IS NOT NULL",
        ]

        params: dict = {"top_k": top_k}

        if self._project_id:
            conditions.append("project_id = :project_id")
            params["project_id"] = self._project_id

        where_clause = " AND ".join(conditions)

        # 使用原生 SQL：ORDER BY embedding <=> :query_vec LIMIT :top_k
        sql = text(f"""
            SELECT project_id, source_type, source_id, chunk_index,
                   (1 - (embedding <=> '{pgvector_literal}'::vector)) AS score
            FROM knowledge_index
            WHERE {where_clause}
            ORDER BY embedding <=> '{pgvector_literal}'::vector
            LIMIT :top_k
        """)

        result = await self._db.execute(sql, params)
        rows = result.fetchall()

        scored: list[tuple[str, float]] = []
        for row in rows:
            key = self.make_key(
                str(row.project_id),
                row.source_type if isinstance(row.source_type, str) else row.source_type.value,
                str(row.source_id),
                row.chunk_index or 0,
            )
            scored.append((key, float(row.score)))

        return scored

    async def delete(self, key: str) -> None:
        """软删除指定 key 对应的 KnowledgeIndex 条目（与 PgTextStore 一致）。"""
        import uuid as uuid_mod

        project_id_str, source_type_str, source_id_str, chunk_index = self.parse_key(key)

        await self._db.execute(
            update(KnowledgeIndex)
            .where(
                KnowledgeIndex.project_id == uuid_mod.UUID(project_id_str),
                KnowledgeIndex.source_id == uuid_mod.UUID(source_id_str),
                KnowledgeIndex.chunk_index == chunk_index,
                KnowledgeIndex.is_deleted == False,  # noqa: E712
            )
            .values(is_deleted=True, updated_at=func.now())
        )


# ---------------------------------------------------------------------------
# Factory: feature flag 控制 PgTextStore ↔ PgVectorStore
# ---------------------------------------------------------------------------


def get_vector_store(db: AsyncSession, *, project_id: str | None = None) -> VectorStore:
    """根据 VECTOR_STORE_BACKEND 环境变量返回对应的 VectorStore 实现。

    - "pgtext"（默认）: PgTextStore（逗号串 + numpy 全扫，保留降级）
    - "pgvector": PgVectorStore（原生 vector 列 + ivfflat 索引）

    如果选择 pgvector 但初始化失败（如扩展未安装），自动降级到 PgTextStore 并 warning。

    需求: 3.3  属性: R4
    """
    from app.core.config import settings

    backend = getattr(settings, "VECTOR_STORE_BACKEND", "pgtext").lower().strip()

    if backend == "pgvector":
        try:
            store = PgVectorStore(db, project_id=project_id)
            return store
        except Exception as e:
            logger.warning(
                f"PgVectorStore 初始化失败，降级到 PgTextStore: {e}"
            )
            return PgTextStore(db, project_id=project_id)
    else:
        # 默认 pgtext（安全路径）
        if backend != "pgtext":
            logger.warning(
                f"未知 VECTOR_STORE_BACKEND='{backend}'，使用默认 PgTextStore"
            )
        return PgTextStore(db, project_id=project_id)
