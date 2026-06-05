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
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import DisclosureNote

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
            stmt_update = (
                update(DisclosureNote)
                .where(
                    DisclosureNote.project_id == str(project_id),
                    DisclosureNote.note_section.in_(section_codes),
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
            logger.error("mark_sections_stale_by_wp failed: %s", e, exc_info=True)

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
                stmt_update = (
                    update(DisclosureNote)
                    .where(
                        DisclosureNote.project_id == str(project_id),
                        DisclosureNote.note_section.in_(section_codes),
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
            logger.error("mark_sections_stale_by_report failed: %s", e, exc_info=True)

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
        """增量刷新：查 stale 章节 → refill_sections 真实重算 → 按结果分别清/留 stale。

        复用 DisclosureEngine.refill_sections 填充链真实重算，
        对成功重算的章节清 is_stale，纯文本/失败章节保留 is_stale=True。
        只 flush 不 commit。

        Args:
            project_id: 项目 ID
            year: 年度
            section_codes: 指定刷新的章节（None 表示所有 stale 章节）
        """
        from app.services.disclosure_engine import DisclosureEngine

        refresh_result = RefreshResult()

        if not self.db:
            return refresh_result

        # 1. 查找 stale 章节
        stmt = select(DisclosureNote).where(
            DisclosureNote.project_id == str(project_id),
            DisclosureNote.year == year,
            DisclosureNote.is_stale == True,  # noqa: E712
        )
        if section_codes:
            stmt = stmt.where(DisclosureNote.note_section.in_(section_codes))

        result = await self.db.execute(stmt)
        stale_notes = list(result.scalars().all())

        if not stale_notes:
            return refresh_result

        # 2. 收集 stale 章节的 note_section 列表
        stale_section_codes = list({note.note_section for note in stale_notes})

        # 3. 调 DisclosureEngine.refill_sections 真实重算
        engine = DisclosureEngine(self.db)
        try:
            report = await engine.refill_sections(
                project_id if isinstance(project_id, UUID) else UUID(str(project_id)),
                year,
                stale_section_codes,
                skip_manual=True,
            )
        except Exception as e:
            logger.error(
                "refresh_stale_sections: refill_sections failed: %s", e, exc_info=True
            )
            refresh_result.errors.append(f"重算失败: {e}")
            return refresh_result

        # 4. 只对 report.sections_recomputed 清 is_stale
        if report.sections_recomputed:
            stmt_clear = (
                update(DisclosureNote)
                .where(
                    DisclosureNote.project_id == str(project_id),
                    DisclosureNote.year == year,
                    DisclosureNote.note_section.in_(report.sections_recomputed),
                )
                .values(is_stale=False)
            )
            await self.db.execute(stmt_clear)

        # 5. text_only_sections 与取数失败章节保留 is_stale=True（不动）

        # 6. 填充 result
        refresh_result.sections_refreshed = len(report.sections_recomputed)
        refresh_result.cells_updated = report.cells_updated
        refresh_result.errors = list(report.errors)

        # 7. 只 flush 不 commit
        await self.db.flush()

        logger.info(
            "Refreshed %d stale sections (real recompute): "
            "%d cells updated, %d text_only, %d errors for project=%s year=%d",
            refresh_result.sections_refreshed,
            refresh_result.cells_updated,
            len(report.text_only_sections),
            len(refresh_result.errors),
            project_id,
            year,
        )

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

        复用 DisclosureEngine.refill_sections 填充链真实重算，
        对成功重算的章节清 is_stale，纯文本/失败章节保留 is_stale=True。
        只 flush 不 commit。

        Args:
            project_id: 项目 ID
            year: 年度
            wp_code: 底稿编码
        """
        refresh_result = RefreshResult()

        if not self.db:
            return refresh_result

        # 1. 用 NoteAccountMapping 求出受 wp_code 影响的 note_section 列表
        from app.models.note_account_mapping import NoteAccountMapping
        from app.services.disclosure_engine import DisclosureEngine
        from app.services.note_wp_mapping_service import DEFAULT_WP_MAPPING

        section_codes: set[str] = set()

        # 1a. 从 NoteAccountMapping 查精确匹配
        stmt = select(NoteAccountMapping.note_section_code).where(
            NoteAccountMapping.wp_code == wp_code
        )
        result = await self.db.execute(stmt)
        for row in result.all():
            if row[0]:
                section_codes.add(row[0])

        # 1b. 从 DEFAULT_WP_MAPPING 查前缀匹配
        for note_section, wp_prefix in DEFAULT_WP_MAPPING.items():
            if wp_code.startswith(wp_prefix):
                section_codes.add(note_section)

        if not section_codes:
            logger.debug(
                "refresh_from_workpaper: no sections mapped for wp_code=%s", wp_code
            )
            return refresh_result

        sections = list(section_codes)

        # 2. 调 DisclosureEngine.refill_sections 真实重算
        engine = DisclosureEngine(self.db)
        try:
            report = await engine.refill_sections(
                project_id if isinstance(project_id, UUID) else UUID(str(project_id)),
                year,
                sections,
                skip_manual=True,
            )
        except Exception as e:
            logger.error(
                "refresh_from_workpaper: refill_sections failed: %s", e, exc_info=True
            )
            refresh_result.errors.append(f"重算失败: {e}")
            return refresh_result

        # 3. 对 report.sections_recomputed 清 is_stale
        if report.sections_recomputed:
            stmt_clear = (
                update(DisclosureNote)
                .where(
                    DisclosureNote.project_id == str(project_id),
                    DisclosureNote.year == year,
                    DisclosureNote.note_section.in_(report.sections_recomputed),
                )
                .values(is_stale=False)
            )
            await self.db.execute(stmt_clear)

        # text_only_sections 与取数失败章节保留 is_stale=True（不动）

        # 4. 填充 result
        refresh_result.cells_updated = report.cells_updated
        refresh_result.sections_refreshed = len(report.sections_recomputed)
        refresh_result.errors = list(report.errors)

        # 5. 只 flush 不 commit
        await self.db.flush()

        logger.info(
            "Refreshed from workpaper %s: %d sections recomputed, "
            "%d cells updated, %d text_only, %d errors for project=%s",
            wp_code,
            refresh_result.sections_refreshed,
            refresh_result.cells_updated,
            len(report.text_only_sections),
            len(refresh_result.errors),
            project_id,
        )

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
            stmt = select(DisclosureNote.note_section).where(
                DisclosureNote.project_id == str(project_id),
                DisclosureNote.year == year,
                DisclosureNote.is_stale == True,  # noqa: E712
            )
            result = await self.db.execute(stmt)
            return [row[0] for row in result.all()]
        except Exception as e:
            logger.error("get_stale_sections failed: %s", e, exc_info=True)
            return []
