"""列映射历史服务 — 持久化 + 按软件指纹复用。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.column_mapping_models import ImportColumnMappingHistory


class ColumnMappingService:
    """CRUD + 复用逻辑 for import_column_mapping_history."""

    @staticmethod
    async def save_mapping(
        db: AsyncSession,
        *,
        project_id: uuid.UUID,
        software_fingerprint: str,
        table_type: str,
        column_mapping: dict,
    ) -> ImportColumnMappingHistory:
        """Save or update a column mapping.

        If (project_id, software_fingerprint, table_type) already exists,
        update column_mapping + increment used_count + refresh last_used_at.
        Otherwise create new.
        """
        stmt = select(ImportColumnMappingHistory).where(
            ImportColumnMappingHistory.project_id == project_id,
            ImportColumnMappingHistory.software_fingerprint == software_fingerprint,
            ImportColumnMappingHistory.table_type == table_type,
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing is not None:
            existing.column_mapping = column_mapping
            existing.used_count = existing.used_count + 1
            existing.last_used_at = datetime.now(timezone.utc)
            await db.flush()
            return existing

        record = ImportColumnMappingHistory(
            project_id=project_id,
            software_fingerprint=software_fingerprint,
            table_type=table_type,
            column_mapping=column_mapping,
        )
        db.add(record)
        await db.flush()
        return record

    @staticmethod
    async def find_mapping(
        db: AsyncSession,
        *,
        project_id: uuid.UUID,
        software_fingerprint: str,
        table_type: str,
    ) -> Optional[ImportColumnMappingHistory]:
        """Find existing mapping by (project_id, fingerprint, table_type)."""
        stmt = select(ImportColumnMappingHistory).where(
            ImportColumnMappingHistory.project_id == project_id,
            ImportColumnMappingHistory.software_fingerprint == software_fingerprint,
            ImportColumnMappingHistory.table_type == table_type,
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def find_any_mapping(
        db: AsyncSession,
        *,
        software_fingerprint: str,
        table_type: str,
    ) -> Optional[ImportColumnMappingHistory]:
        """Find mapping across ALL projects (for cross-project reuse).
        Returns the most recently used one."""
        stmt = (
            select(ImportColumnMappingHistory)
            .where(
                ImportColumnMappingHistory.software_fingerprint == software_fingerprint,
                ImportColumnMappingHistory.table_type == table_type,
            )
            .order_by(ImportColumnMappingHistory.last_used_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def delete_mapping(
        db: AsyncSession,
        *,
        project_id: uuid.UUID,
        software_fingerprint: str,
    ) -> int:
        """Delete all mappings for a project+fingerprint. Returns count deleted."""
        stmt = (
            delete(ImportColumnMappingHistory)
            .where(
                ImportColumnMappingHistory.project_id == project_id,
                ImportColumnMappingHistory.software_fingerprint == software_fingerprint,
            )
        )
        result = await db.execute(stmt)
        await db.flush()
        return result.rowcount  # type: ignore[return-value]

    @staticmethod
    async def list_mappings(
        db: AsyncSession,
        *,
        project_id: uuid.UUID,
    ) -> list[ImportColumnMappingHistory]:
        """List all mappings for a project, ordered by last_used_at desc."""
        stmt = (
            select(ImportColumnMappingHistory)
            .where(ImportColumnMappingHistory.project_id == project_id)
            .order_by(ImportColumnMappingHistory.last_used_at.desc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def build_fingerprint(adapter_id: str, table_type: str, version_hint: str = "") -> str:
        """Build software_fingerprint string.

        Format: "{adapter_id}_{table_type}" or "{adapter_id}_{version_hint}_{table_type}"
        Example: "yonyou_balance", "yonyou_U8_v13_balance"
        """
        if version_hint:
            return f"{adapter_id}_{version_hint}_{table_type}"
        return f"{adapter_id}_{table_type}"

    @staticmethod
    async def apply_history_mapping(
        db: AsyncSession,
        *,
        project_id: uuid.UUID,
        software_fingerprint: str,
        table_type: str,
    ) -> Optional[dict]:
        """Task 31: Try to find and apply historical mapping.

        Returns the column_mapping dict if found (caller uses it to pre-fill
        ColumnMatch results), or None if no history exists.

        Also increments used_count and refreshes last_used_at on hit.
        """
        # 1. Query by (project_id, software_fingerprint, table_type)
        record = await ColumnMappingService.find_mapping(
            db,
            project_id=project_id,
            software_fingerprint=software_fingerprint,
            table_type=table_type,
        )

        # 2. If not found, try cross-project (same fingerprint)
        if record is None:
            record = await ColumnMappingService.find_any_mapping(
                db,
                software_fingerprint=software_fingerprint,
                table_type=table_type,
            )

        if record is None:
            return None

        # 3. Increment used_count and update last_used_at
        record.used_count = record.used_count + 1
        record.last_used_at = datetime.now(timezone.utc)
        await db.flush()

        # 4. Return the column_mapping dict
        return record.column_mapping
