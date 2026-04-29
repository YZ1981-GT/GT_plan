"""附注生成引擎 — 模版驱动生成 + 数值自动填充 + 增量更新

核心功能：
- generate_notes: 根据附注模版种子数据生成附注初稿
- populate_table_data: 从试算表取数填充附注表格
- update_note_values: 增量更新受影响附注数值
- on_reports_updated: EventBus 事件处理器

Validates: Requirements 4.2, 4.3, 4.4, 4.7, 4.8, 4.9, 4.10, 8.1
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TrialBalance
from app.models.audit_platform_schemas import EventPayload
from app.models.core import Project
from app.models.report_models import (
    ContentType,
    DisclosureNote,
    FinancialReport,
    FinancialReportType,
    NoteStatus,
    SourceTemplate,
)
from app.services.note_template_service import NoteTemplateService

logger = logging.getLogger(__name__)

SEED_DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "note_templates_seed.json"


def _load_seed_data() -> dict:
    """加载附注模版种子数据"""
    with open(SEED_DATA_PATH, encoding="utf-8-sig") as f:
        return json.load(f)


def _extract_basic_info(wizard_state: dict | None) -> dict:
    state = wizard_state or {}
    return (
        state.get("steps", {}).get("basic_info", {}).get("data")
        or state.get("basic_info", {}).get("data")
        or {}
    )


class DisclosureEngine:
    """附注生成引擎"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_project_basic_info(self, project_id: UUID) -> dict:
        result = await self.db.execute(
            sa.select(Project).where(
                Project.id == project_id,
                Project.is_deleted == sa.false(),
            )
        )
        project = result.scalar_one_or_none()
        if project is None:
            return {}

        template_service = NoteTemplateService()
        wizard_state, _, changed = template_service.backfill_locked_template_snapshot(project.wizard_state)
        if changed:
            project.wizard_state = wizard_state
            await self.db.flush()
        return _extract_basic_info(project.wizard_state)

    async def _get_custom_template_sections(self, project_id: UUID) -> list[dict]:
        basic_info = await self._get_project_basic_info(project_id)
        template_service = NoteTemplateService()
        locked_snapshot = template_service.get_locked_template_snapshot(basic_info)
        if locked_snapshot is not None:
            return locked_snapshot.get("sections", [])

        template_id = basic_info.get("custom_template_id")
        if not template_id:
            logger.warning("project %s has no custom_template_id in wizard_state", project_id)
            raise HTTPException(status_code=400, detail="当前项目未绑定有效的自定义附注模板，请先在项目基本信息中选择")

        template = template_service.get_template(template_id)
        if template is None:
            logger.warning("custom note template %s not found for project %s", template_id, project_id)
            raise HTTPException(status_code=400, detail="当前项目绑定的自定义附注模板不存在或已失效，请重新选择")
        return template.get("sections", [])

    async def _load_templates(self, project_id: UUID, template_type: str) -> list[dict]:
        if template_type != "custom":
            seed = _load_seed_data()
            return seed.get("account_mapping_template", [])

        sections = await self._get_custom_template_sections(project_id)
        return [
            {
                "note_section": section.get("section_number", f"五、{idx + 1}"),
                "section_title": section.get("section_title", ""),
                "account_name": section.get("account_name") or section.get("section_title", ""),
                "content_type": section.get("content_type")
                or (
                    "mixed"
                    if section.get("table_template") and section.get("text_template")
                    else "table"
                    if section.get("table_template")
                    else "text"
                ),
                "sort_order": idx * 10,
                "table_template": section.get("table_template") or {},
                "text_template": section.get("text_template"),
            }
            for idx, section in enumerate(sections)
        ]

    async def _get_active_template_type(self, project_id: UUID) -> str:
        basic_info = await self._get_project_basic_info(project_id)
        template_type = basic_info.get("template_type")
        return template_type if isinstance(template_type, str) and template_type else "soe"

    @staticmethod
    def _persist_source_template(template_type: str) -> SourceTemplate | None:
        if template_type == SourceTemplate.soe.value:
            return SourceTemplate.soe
        if template_type == SourceTemplate.listed.value:
            return SourceTemplate.listed
        return None

    # ------------------------------------------------------------------
    # 生成附注
    # ------------------------------------------------------------------
    async def generate_notes(
        self,
        project_id: UUID,
        year: int,
        template_type: str = "soe",
    ) -> list[dict]:
        """根据模版生成附注初稿，写入 disclosure_notes 表。

        Validates: Requirements 4.2, 4.3, 4.8, 4.9
        """
        templates = await self._load_templates(project_id, template_type)
        source_template = self._persist_source_template(template_type)
        results = []

        for tmpl in templates:
            note_section = tmpl["note_section"]
            section_title = tmpl["section_title"]
            account_name = tmpl.get("account_name") or section_title
            content_type_str = tmpl.get("content_type", "table")
            sort_order = tmpl.get("sort_order", 0)
            text_content = tmpl.get("text_template") if content_type_str in ("text", "mixed") else None

            # Build table_data from template + trial balance
            table_data = None
            if content_type_str in ("table", "mixed"):
                table_data = await self._build_table_data(
                    project_id, year, tmpl.get("table_template", {}),
                )

            # Upsert into disclosure_notes
            existing = await self.db.execute(
                sa.select(DisclosureNote).where(
                    DisclosureNote.project_id == project_id,
                    DisclosureNote.year == year,
                    DisclosureNote.note_section == note_section,
                    DisclosureNote.is_deleted == sa.false(),
                )
            )
            note = existing.scalar_one_or_none()

            if note:
                note.section_title = section_title
                note.account_name = account_name
                note.content_type = ContentType(content_type_str)
                note.table_data = table_data
                note.text_content = text_content
                note.source_template = source_template
                note.sort_order = sort_order
            else:
                note = DisclosureNote(
                    project_id=project_id,
                    year=year,
                    note_section=note_section,
                    section_title=section_title,
                    account_name=account_name,
                    content_type=ContentType(content_type_str),
                    table_data=table_data,
                    text_content=text_content,
                    source_template=source_template,
                    status=NoteStatus.draft,
                    sort_order=sort_order,
                )
                self.db.add(note)

            results.append({
                "note_section": note_section,
                "section_title": section_title,
                "account_name": account_name,
                "content_type": content_type_str,
            })

        await self.db.flush()

        # ── Phase 16: 版本链写入 ──
        try:
            from app.services.version_line_service import version_line_service
            latest = await version_line_service.get_latest_version(
                self.db, project_id, "note", project_id
            )
            await version_line_service.write_stamp(
                db=self.db,
                project_id=project_id,
                object_type="note",
                object_id=project_id,
                version_no=latest + 1,
            )
        except Exception as _vl_err:
            import logging
            logging.getLogger(__name__).warning(f"[VERSION_LINE] note write_stamp failed: {_vl_err}")

        return results

    # ------------------------------------------------------------------
    # 增量更新
    # ------------------------------------------------------------------
    async def update_note_values(
        self,
        project_id: UUID,
        year: int,
        changed_accounts: list[str] | None = None,
    ) -> int:
        """增量更新受影响附注的数值。

        简单实现：重新生成所有附注的 table_data。
        Validates: Requirements 8.1
        """
        template_type = await self._get_active_template_type(project_id)
        templates = await self._load_templates(project_id, template_type)
        updated = 0

        for tmpl in templates:
            content_type_str = tmpl.get("content_type", "table")
            if content_type_str not in ("table", "mixed"):
                continue

            note_section = tmpl["note_section"]
            table_template = tmpl.get("table_template", {})

            if changed_accounts:
                referenced_codes = set()
                for row in table_template.get("rows", []):
                    referenced_codes.update(row.get("account_codes", []))
                if referenced_codes and not referenced_codes.intersection(set(changed_accounts)):
                    continue

            table_data = await self._build_table_data(
                project_id, year, table_template,
            )

            existing = await self.db.execute(
                sa.select(DisclosureNote).where(
                    DisclosureNote.project_id == project_id,
                    DisclosureNote.year == year,
                    DisclosureNote.note_section == note_section,
                    DisclosureNote.is_deleted == sa.false(),
                )
            )
            note = existing.scalar_one_or_none()
            if note:
                note.table_data = table_data
                updated += 1

        await self.db.flush()
        return updated

    # ------------------------------------------------------------------
    # 获取附注
    # ------------------------------------------------------------------
    async def get_notes_tree(
        self,
        project_id: UUID,
        year: int,
    ) -> list[dict]:
        """获取附注目录树"""
        result = await self.db.execute(
            sa.select(DisclosureNote)
            .where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
                DisclosureNote.is_deleted == sa.false(),
            )
            .order_by(DisclosureNote.sort_order)
        )
        notes = result.scalars().all()
        return [
            {
                "note_section": n.note_section,
                "section_title": n.section_title,
                "account_name": n.account_name,
                "content_type": n.content_type.value if n.content_type else None,
                "status": n.status.value if n.status else "draft",
                "sort_order": n.sort_order,
            }
            for n in notes
        ]

    async def get_note_detail(
        self,
        project_id: UUID,
        year: int,
        note_section: str,
    ) -> DisclosureNote | None:
        """获取指定附注章节详情"""
        result = await self.db.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
                DisclosureNote.note_section == note_section,
                DisclosureNote.is_deleted == sa.false(),
            )
        )
        return result.scalar_one_or_none()

    async def update_note(
        self,
        note_id: UUID,
        table_data: dict | None = None,
        text_content: str | None = None,
        status: NoteStatus | None = None,
    ) -> DisclosureNote | None:
        """更新附注章节内容。

        Validates: Requirements 4.10
        """
        result = await self.db.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.id == note_id,
                DisclosureNote.is_deleted == sa.false(),
            )
        )
        note = result.scalar_one_or_none()
        if note is None:
            return None

        if table_data is not None:
            note.table_data = table_data
        if text_content is not None:
            note.text_content = text_content
        if status is not None:
            note.status = status

        await self.db.flush()
        return note

    # ------------------------------------------------------------------
    # 事件处理器
    # ------------------------------------------------------------------
    async def on_reports_updated(self, payload: EventPayload) -> None:
        """监听 reports_updated 事件，触发附注增量更新。

        Validates: Requirements 8.1
        """
        logger.info(
            "on_reports_updated: project=%s, accounts=%s",
            payload.project_id, payload.account_codes,
        )
        year = payload.year
        if not year:
            logger.warning("on_reports_updated: missing year, skipping")
            return

        await self.update_note_values(
            payload.project_id, year, payload.account_codes,
        )
        await self.db.flush()

    # ------------------------------------------------------------------
    # 上年数据查询（Phase 11 Task 5.1 / 5.2）
    # ------------------------------------------------------------------
    async def get_prior_year_data(
        self, project_id: UUID, year: int, note_section: str,
    ) -> dict | None:
        """查询上年（year-1）同一附注章节的 table_data，用于前端双列对比。"""
        prior_year = year - 1
        result = await self.db.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == prior_year,
                DisclosureNote.note_section == note_section,
                DisclosureNote.is_deleted == sa.false(),
            )
        )
        note = result.scalar_one_or_none()
        if note:
            return {
                "year": prior_year,
                "table_data": note.table_data,
                "text_content": note.text_content,
            }
        # 兜底：从上年试算表取审定数
        return await self._get_prior_from_trial_balance(project_id, prior_year, note_section)

    async def _get_prior_from_trial_balance(
        self, project_id: UUID, year: int, note_section: str,
    ) -> dict | None:
        """从上年试算表取审定数，构造简化的上年数据。"""
        # 通过 note_section 找到关联的科目编码（从种子数据映射）
        seed = _load_seed_data()
        account_codes: list[str] = []
        for section in seed.get("sections", []):
            if section.get("note_section") == note_section:
                account_codes = section.get("account_codes", [])
                break
        if not account_codes:
            return None

        result = await self.db.execute(
            sa.select(
                TrialBalance.standard_account_code,
                TrialBalance.audited_amount,
            ).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.standard_account_code.in_(account_codes),
                TrialBalance.is_deleted == sa.false(),
            )
        )
        rows = result.all()
        if not rows:
            return None
        amounts = {r.standard_account_code: float(r.audited_amount or 0) for r in rows}
        return {"year": year, "table_data": None, "amounts": amounts}
