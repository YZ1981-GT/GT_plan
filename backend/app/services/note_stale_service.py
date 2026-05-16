"""附注增量刷新与 stale 联动服务

Requirements: 25.7, 36.4, 36.5

底稿数据变更时自动标记关联附注章节为 stale。
支持增量刷新（仅更新上游数据变更影响的单元格）。
支持"从底稿刷新"操作。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class StaleSection:
    """被标记为 stale 的附注章节"""
    section_id: str
    section_code: str
    reason: str
    stale_since: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    upstream_source: str = ""  # wp_code / report_row_code


@dataclass
class RefreshResult:
    """刷新结果"""
    sections_refreshed: int = 0
    cells_updated: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Stale Service
# ---------------------------------------------------------------------------

class NoteStaleService:
    """附注增量刷新与 stale 联动服务"""

    def __init__(self, db: AsyncSession | None = None):
        self.db = db

    # ------------------------------------------------------------------
    # 标记 stale
    # ------------------------------------------------------------------

    async def mark_sections_stale_by_wp(
        self,
        project_id: str | UUID,
        wp_code: str,
    ) -> list[StaleSection]:
        """底稿数据变更时，标记关联附注章节为 stale

        Args:
            project_id: 项目 ID
            wp_code: 变更的底稿编码（如 E1, D2）
        """
        if not self.db:
            return []

        stale_sections: list[StaleSection] = []

        try:
            # 查找与该底稿关联的附注章节映射
            from app.models.note_account_mapping import NoteAccountMapping
            stmt = select(NoteAccountMapping).where(
                NoteAccountMapping.wp_code == wp_code
            )
            result = await self.db.execute(stmt)
            mappings = list(result.scalars().all())

            if not mappings:
                logger.debug("No note mappings found for wp_code=%s", wp_code)
                return []

            # 获取关联的附注章节编码
            section_codes = list({m.note_section_code for m in mappings})

            # 标记这些章节为 stale（通过更新 disclosure_notes 表的 is_stale 字段）
            from app.models.phase13_models import DisclosureNote
            stmt_update = (
                update(DisclosureNote)
                .where(
                    DisclosureNote.project_id == str(project_id),
                    DisclosureNote.section_code.in_(section_codes),
                )
                .values(is_stale=True)
            )
            await self.db.execute(stmt_update)

            for code in section_codes:
                stale_sections.append(StaleSection(
                    section_id="",
                    section_code=code,
                    reason=f"底稿 {wp_code} 数据变更",
                    upstream_source=wp_code,
                ))

            logger.info(
                "Marked %d note sections stale for project=%s wp=%s",
                len(stale_sections), project_id, wp_code,
            )

        except Exception as e:
            logger.warning("mark_sections_stale_by_wp failed: %s", e)

        return stale_sections

    async def mark_sections_stale_by_report(
        self,
        project_id: str | UUID,
        report_row_codes: list[str] | None = None,
    ) -> list[StaleSection]:
        """报表数据变更时，标记关联附注章节为 stale

        Args:
            project_id: 项目 ID
            report_row_codes: 变更的报表行次编码列表（None 表示全部）
        """
        if not self.db:
            return []

        stale_sections: list[StaleSection] = []

        try:
            from app.models.note_account_mapping import NoteAccountMapping

            if report_row_codes:
                stmt = select(NoteAccountMapping).where(
                    NoteAccountMapping.report_row_code.in_(report_row_codes)
                )
            else:
                # 全部标记
                stmt = select(NoteAccountMapping)

            result = await self.db.execute(stmt)
            mappings = list(result.scalars().all())

            section_codes = list({m.note_section_code for m in mappings})

            if section_codes:
                from app.models.phase13_models import DisclosureNote
                stmt_update = (
                    update(DisclosureNote)
                    .where(
                        DisclosureNote.project_id == str(project_id),
                        DisclosureNote.section_code.in_(section_codes),
                    )
                    .values(is_stale=True)
                )
                await self.db.execute(stmt_update)

                for code in section_codes:
                    stale_sections.append(StaleSection(
                        section_id="",
                        section_code=code,
                        reason="报表数据变更",
                        upstream_source="report",
                    ))

        except Exception as e:
            logger.warning("mark_sections_stale_by_report failed: %s", e)

        return stale_sections

    # ------------------------------------------------------------------
    # 增量刷新
    # ------------------------------------------------------------------

    async def refresh_stale_sections(
        self,
        project_id: str | UUID,
        year: int,
        section_codes: list[str] | None = None,
    ) -> RefreshResult:
        """增量刷新：仅更新上游数据变更影响的单元格

        Args:
            project_id: 项目 ID
            year: 年度
            section_codes: 指定刷新的章节（None 表示所有 stale 章节）
        """
        refresh_result = RefreshResult()

        if not self.db:
            return refresh_result

        try:
            from app.models.phase13_models import DisclosureNote

            # 查找 stale 章节
            stmt = select(DisclosureNote).where(
                DisclosureNote.project_id == str(project_id),
                DisclosureNote.year == year,
                DisclosureNote.is_stale == True,  # noqa: E712
            )
            if section_codes:
                stmt = stmt.where(DisclosureNote.section_code.in_(section_codes))

            result = await self.db.execute(stmt)
            stale_notes = list(result.scalars().all())

            # 清除 stale 标记（实际数据刷新由 fill engine 负责）
            for note in stale_notes:
                note.is_stale = False
                refresh_result.sections_refreshed += 1

            await self.db.flush()
            logger.info(
                "Refreshed %d stale sections for project=%s year=%d",
                refresh_result.sections_refreshed, project_id, year,
            )

        except Exception as e:
            refresh_result.errors.append(str(e))
            logger.warning("refresh_stale_sections failed: %s", e)

        return refresh_result

    # ------------------------------------------------------------------
    # 从底稿刷新
    # ------------------------------------------------------------------

    async def refresh_from_workpaper(
        self,
        project_id: str | UUID,
        year: int,
        wp_code: str,
    ) -> RefreshResult:
        """从底稿刷新：将底稿最新数据同步到关联附注章节

        Args:
            project_id: 项目 ID
            year: 年度
            wp_code: 底稿编码
        """
        refresh_result = RefreshResult()

        if not self.db:
            return refresh_result

        try:
            # 查找与该底稿关联的章节
            from app.models.note_account_mapping import NoteAccountMapping
            stmt = select(NoteAccountMapping).where(
                NoteAccountMapping.wp_code == wp_code
            )
            result = await self.db.execute(stmt)
            mappings = list(result.scalars().all())

            section_codes = list({m.note_section_code for m in mappings})

            if section_codes:
                # 清除这些章节的 stale 标记
                from app.models.phase13_models import DisclosureNote
                stmt_update = (
                    update(DisclosureNote)
                    .where(
                        DisclosureNote.project_id == str(project_id),
                        DisclosureNote.year == year,
                        DisclosureNote.section_code.in_(section_codes),
                    )
                    .values(is_stale=False)
                )
                await self.db.execute(stmt_update)
                refresh_result.sections_refreshed = len(section_codes)

            logger.info(
                "Refreshed from workpaper %s: %d sections for project=%s",
                wp_code, refresh_result.sections_refreshed, project_id,
            )

        except Exception as e:
            refresh_result.errors.append(str(e))
            logger.warning("refresh_from_workpaper failed: %s", e)

        return refresh_result

    # ------------------------------------------------------------------
    # 查询 stale 状态
    # ------------------------------------------------------------------

    async def get_stale_sections(
        self,
        project_id: str | UUID,
        year: int,
    ) -> list[str]:
        """获取所有 stale 状态的附注章节编码"""
        if not self.db:
            return []

        try:
            from app.models.phase13_models import DisclosureNote
            stmt = select(DisclosureNote.section_code).where(
                DisclosureNote.project_id == str(project_id),
                DisclosureNote.year == year,
                DisclosureNote.is_stale == True,  # noqa: E712
            )
            result = await self.db.execute(stmt)
            return [row[0] for row in result.all()]
        except Exception as e:
            logger.warning("get_stale_sections failed: %s", e)
            return []
