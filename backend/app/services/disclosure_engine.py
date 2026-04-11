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

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import TrialBalance
from app.models.audit_platform_schemas import EventPayload
from app.models.report_models import (
    ContentType,
    DisclosureNote,
    FinancialReport,
    FinancialReportType,
    NoteStatus,
    SourceTemplate,
)

logger = logging.getLogger(__name__)

SEED_DATA_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "note_templates_seed.json"


def _load_seed_data() -> dict:
    """加载附注模版种子数据"""
    with open(SEED_DATA_PATH, encoding="utf-8-sig") as f:
        return json.load(f)


class DisclosureEngine:
    """附注生成引擎"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # 生成附注
    # ------------------------------------------------------------------
    async def generate_notes(
        self,
        project_id: UUID,
        year: int,
        template_type: SourceTemplate = SourceTemplate.soe,
    ) -> list[dict]:
        """根据模版生成附注初稿，写入 disclosure_notes 表。

        Validates: Requirements 4.2, 4.3, 4.8, 4.9
        """
        seed = _load_seed_data()
        templates = seed.get("account_mapping_template", [])
        results = []

        for tmpl in templates:
            note_section = tmpl["note_section"]
            section_title = tmpl["section_title"]
            account_name = tmpl["account_name"]
            content_type_str = tmpl.get("content_type", "table")
            sort_order = tmpl.get("sort_order", 0)

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
                note.source_template = template_type
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
                    text_content=None,
                    source_template=template_type,
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
        return results

    async def _build_table_data(
        self,
        project_id: UUID,
        year: int,
        table_template: dict,
    ) -> dict:
        """从试算表取数构建 table_data。

        Validates: Requirements 4.4, 4.8
        """
        headers = table_template.get("headers", ["项目", "期末余额", "期初余额"])
        template_rows = table_template.get("rows", [])
        result_rows = []
        running_total_current = Decimal("0")
        running_total_prior = Decimal("0")

        for tmpl_row in template_rows:
            label = tmpl_row.get("label", "")
            account_codes = tmpl_row.get("account_codes", [])
            is_total = tmpl_row.get("is_total", False)

            if is_total:
                # Total row: sum of all previous non-total rows
                result_rows.append({
                    "label": label,
                    "values": [
                        float(running_total_current),
                        float(running_total_prior),
                    ],
                    "is_total": True,
                })
            elif account_codes:
                # Fetch from trial balance
                current_val = Decimal("0")
                prior_val = Decimal("0")
                for code in account_codes:
                    tb_current = await self._get_tb_amount(project_id, year, code)
                    tb_prior = await self._get_tb_amount(project_id, year, code, field="opening_balance")
                    current_val += tb_current
                    prior_val += tb_prior

                running_total_current += current_val
                running_total_prior += prior_val
                result_rows.append({
                    "label": label,
                    "values": [float(current_val), float(prior_val)],
                    "is_total": False,
                })
            else:
                # No account codes — placeholder row (e.g. "减：坏账准备")
                result_rows.append({
                    "label": label,
                    "values": [0.0, 0.0],
                    "is_total": False,
                })

        return {
            "headers": headers,
            "rows": result_rows,
            "check_roles": [],
        }

    async def _get_tb_amount(
        self,
        project_id: UUID,
        year: int,
        account_code: str,
        field: str = "audited_amount",
    ) -> Decimal:
        """从试算表获取指定科目的金额"""
        result = await self.db.execute(
            sa.select(TrialBalance).where(
                TrialBalance.project_id == project_id,
                TrialBalance.year == year,
                TrialBalance.standard_account_code == account_code,
                TrialBalance.is_deleted == sa.false(),
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return Decimal("0")
        val = getattr(row, field, None)
        return val if val is not None else Decimal("0")

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
        seed = _load_seed_data()
        templates = seed.get("account_mapping_template", [])
        updated = 0

        for tmpl in templates:
            note_section = tmpl["note_section"]
            table_template = tmpl.get("table_template", {})

            # Check if any of the changed accounts are referenced
            if changed_accounts:
                referenced_codes = set()
                for row in table_template.get("rows", []):
                    referenced_codes.update(row.get("account_codes", []))
                if not referenced_codes.intersection(set(changed_accounts)):
                    continue

            # Re-build table_data
            table_data = await self._build_table_data(
                project_id, year, table_template,
            )

            # Update in DB
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
