"""列映射历史服务 — 持久化 + 按软件指纹复用。"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.column_mapping_models import ImportColumnMappingHistory


# F52 / Sprint 8.34: 历史命中默认窗口（避免陈旧 mapping 被错误复用）
DEFAULT_FINGERPRINT_REUSE_WINDOW = timedelta(days=30)


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

    # ------------------------------------------------------------------
    # F52 / Sprint 8.34: 文件指纹 + 细粒度历史复用
    # ------------------------------------------------------------------

    @staticmethod
    def build_file_fingerprint(
        sheet_name: str,
        header_cells: Iterable[object],
        software_hint: str | None = None,
    ) -> str:
        """SHA1(sheet_name + "|" + "|".join(header_cells[:20]) + "|" + software_hint)。

        稳定哈希，供 detect 阶段按 (project_id, file_fingerprint) 命中历史记录。
        实现要点：
        - 只取表头前 20 单元（超过 20 会让同模板的不同文件哈希不稳定）
        - 每个单元 ``strip().lower()`` 归一化（避免大小写/空白波动）
        - None / 空串保留为空字符串占位，保持列数语义
        - ``software_hint`` None 视为空字符串

        Args:
            sheet_name: sheet 名（通常取 normalized sheet_name）
            header_cells: 表头行的单元值序列（按列顺序）
            software_hint: 可选的软件提示（如 "yonyou_U8_v13"）

        Returns:
            40 个字符的 SHA1 十六进制字符串
        """
        normalized_sheet = (sheet_name or "").strip().lower()
        header_list = list(header_cells)[:20]
        normalized_header = [
            (str(cell).strip().lower() if cell is not None else "") for cell in header_list
        ]
        hint = (software_hint or "").strip().lower()
        payload = normalized_sheet + "|" + "|".join(normalized_header) + "|" + hint
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    @staticmethod
    async def find_by_file_fingerprint(
        db: AsyncSession,
        *,
        project_id: uuid.UUID,
        file_fingerprint: str,
        window: timedelta | None = None,
        now: datetime | None = None,
    ) -> Optional[ImportColumnMappingHistory]:
        """按 (project_id, file_fingerprint) 命中最近一条（窗口内，默认 30 天）。

        Args:
            db: 异步 session
            project_id: 目标项目
            file_fingerprint: 由 ``build_file_fingerprint`` 产出
            window: 过滤窗口；None 则用 ``DEFAULT_FINGERPRINT_REUSE_WINDOW``
            now: 注入时间（测试方便），None 则用 ``datetime.now(tz=UTC)``

        Returns:
            最新一条命中记录；无命中返回 None。
        """
        if not file_fingerprint:
            return None
        effective_window = window or DEFAULT_FINGERPRINT_REUSE_WINDOW
        current = now or datetime.now(timezone.utc)
        min_created_at = current - effective_window

        stmt = (
            select(ImportColumnMappingHistory)
            .where(
                ImportColumnMappingHistory.project_id == project_id,
                ImportColumnMappingHistory.file_fingerprint == file_fingerprint,
                ImportColumnMappingHistory.created_at >= min_created_at,
            )
            .order_by(ImportColumnMappingHistory.created_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def save_with_file_fingerprint(
        db: AsyncSession,
        *,
        project_id: uuid.UUID,
        software_fingerprint: str,
        table_type: str,
        column_mapping: dict,
        file_fingerprint: str,
        override_parent_id: uuid.UUID | None = None,
    ) -> ImportColumnMappingHistory:
        """F52: 带文件指纹 + 覆盖父记录的写入。

        Detect 阶段用户确认/修改 mapping 后调用，形成历史链。
        """
        now = datetime.now(timezone.utc)
        record = ImportColumnMappingHistory(
            id=uuid.uuid4(),
            project_id=project_id,
            software_fingerprint=software_fingerprint,
            table_type=table_type,
            column_mapping=column_mapping,
            file_fingerprint=file_fingerprint,
            override_parent_id=override_parent_id,
            used_count=1,
            created_at=now,
            last_used_at=now,
        )
        db.add(record)
        await db.flush()
        return record

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
