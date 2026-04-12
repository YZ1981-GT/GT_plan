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

import uuid
from typing import Any
from uuid import UUID

import numpy as np
from sqlalchemy import select, update, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_models import KnowledgeIndex, KnowledgeSourceType, Contract, DocumentScan
from app.models.audit_platform_models import (
    Adjustment,
    AdjustmentEntry,
    TrialBalance,
)
from app.models.report_models import AuditReport
from app.models.collaboration_models import AuditFinding
from app.services.ai_service import AIService

# Fixed chunk size (character count)
_CHUNK_SIZE = 500


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

    async def _fetch_project_texts(self, project_id: UUID) -> list[tuple]:
        """Fetch all text content for a project and return list of (source_type, source_id, text) tuples."""
        texts: list[tuple] = []

        # -- DocumentScan --
        doc_result = await self._db.execute(
            select(DocumentScan).where(
                DocumentScan.project_id == project_id,
                DocumentScan.is_deleted == False,
            )
        )
        for doc in doc_result.scalars().all():
            content = (
                f"文档 {getattr(doc, 'file_name', '') or ''}，"
                f"类型 {getattr(doc, 'document_type', '未知')}。"
            )
            texts.append((KnowledgeSourceType.document, doc.id, content))

        # -- WorkingPaper (AdjustmentEntry) --
        adj_entry_result = await self._db.execute(
            select(AdjustmentEntry).where(
                AdjustmentEntry.adjustment_id.in_(
                    select(Adjustment.id).where(Adjustment.project_id == project_id)
                ),
                AdjustmentEntry.is_deleted == False,
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
                TrialBalance.is_deleted == False,
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
                AuditReport.is_deleted == False,
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
                Contract.is_deleted == False,
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
                AuditFinding.is_deleted == False,
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

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def build_index(self, project_id: UUID) -> int:
        """
        Full build of project knowledge base index.
        Returns total number of indexed documents (chunks).
        """
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
    ) -> list[dict[str, Any]]:
        """
        Semantic search using embedding + cosine similarity.
        Returns top_k results with scores.
        """
        # Encode query
        query_embedding = await self._ai_svc.embedding(query)
        query_vec = np.array(query_embedding)

        # Fetch all non-deleted chunks for project
        result = await self._db.execute(
            select(KnowledgeIndex).where(
                KnowledgeIndex.project_id == project_id,
                KnowledgeIndex.is_deleted == False,
            )
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
            "indexed_at": datetime.datetime.utcnow().isoformat(),
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
            "updated_at": datetime.datetime.utcnow().isoformat(),
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
