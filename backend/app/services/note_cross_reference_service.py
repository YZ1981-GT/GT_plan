"""NoteCrossReferenceService — 交叉引用自动生成

Requirements: 42.1, 42.2, 42.3, 42.4, 42.5

功能：
- 报表行次"附注编号"列自动填入对应章节序号
- 附注文本中 {ref:BS-001} 占位符替换为"详见附注五、（一）1"
- 章节顺序调整后自动更新所有交叉引用
- Word 导出时生成 Word 书签+REF 域
- Excel 导出时填入附注编号列
"""
from __future__ import annotations

import logging
import re
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Chinese numbering for different levels
_CHINESE_NUMBERS = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十',
                    '十一', '十二', '十三', '十四', '十五', '十六', '十七', '十八', '十九', '二十',
                    '二十一', '二十二', '二十三', '二十四', '二十五', '二十六', '二十七', '二十八', '二十九', '三十']


def _to_chinese_number(n: int) -> str:
    """Convert integer to Chinese number string (1-based)."""
    if 1 <= n <= len(_CHINESE_NUMBERS):
        return _CHINESE_NUMBERS[n - 1]
    return str(n)


class NoteCrossReferenceService:
    """Service for generating and managing cross-references between reports and notes."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_cross_references(
        self,
        project_id: UUID,
        year: int,
    ) -> dict[str, Any]:
        """Generate cross-reference mappings.

        Returns a mapping of report row_code → note section number string.

        Requirements: 42.1, 42.2, 42.3
        """
        from app.models.report_models import DisclosureNote

        # Load all notes ordered by sort_order/section_code
        result = await self.db.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
            ).order_by(
                DisclosureNote.sort_order.asc(),
                DisclosureNote.section_code.asc(),
            )
        )
        notes = result.scalars().all()

        if not notes:
            return {"references": {}, "note_numbers": {}}

        # Build section numbering based on current order
        note_numbers = self._build_section_numbers(notes)

        # Build row_code → note number mapping
        references: dict[str, str] = {}
        for note in notes:
            if not note.section_code:
                continue
            # Extract row_code from section_code mapping
            row_codes = self._get_linked_row_codes(note)
            number_str = note_numbers.get(note.section_code, "")
            for rc in row_codes:
                if number_str:
                    references[rc] = number_str

        return {
            "references": references,
            "note_numbers": note_numbers,
            "total_notes": len(notes),
            "total_references": len(references),
        }

    async def resolve_ref_placeholders(
        self,
        project_id: UUID,
        year: int,
        text: str,
    ) -> str:
        """Resolve {ref:BS-001} placeholders in text to readable references.

        Example: {ref:BS-001} → "详见附注五、（一）1"

        Requirements: 42.2
        """
        if '{ref:' not in text:
            return text

        # Get cross-reference data
        xref_data = await self.generate_cross_references(project_id, year)
        references = xref_data["references"]

        def replace_ref(match: re.Match) -> str:
            row_code = match.group(1)
            number_str = references.get(row_code, "")
            if number_str:
                return f"详见附注{number_str}"
            return match.group(0)  # Keep original if not found

        return re.sub(r'\{ref:([A-Z]+-\d+)\}', replace_ref, text)

    async def get_report_note_numbers(
        self,
        project_id: UUID,
        year: int,
    ) -> dict[str, str]:
        """Get mapping of report row_code → note number for Excel export.

        Requirements: 42.5
        """
        xref_data = await self.generate_cross_references(project_id, year)
        return xref_data["references"]

    async def update_all_references(
        self,
        project_id: UUID,
        year: int,
    ) -> dict[str, Any]:
        """Update all cross-references after section reordering.

        Requirements: 42.3
        """
        from app.models.report_models import DisclosureNote

        # Regenerate numbering
        xref_data = await self.generate_cross_references(project_id, year)
        note_numbers = xref_data["note_numbers"]

        # Update text content in notes that contain {ref:} placeholders
        result = await self.db.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
            )
        )
        notes = result.scalars().all()

        updated_count = 0
        for note in notes:
            if note.text_content and '{ref:' in note.text_content:
                resolved = await self.resolve_ref_placeholders(
                    project_id, year, note.text_content
                )
                if resolved != note.text_content:
                    note.text_content = resolved
                    updated_count += 1

        await self.db.flush()

        return {
            "status": "success",
            "note_numbers": note_numbers,
            "updated_notes": updated_count,
            "total_references": xref_data["total_references"],
        }

    def generate_word_bookmarks(
        self,
        notes: list[Any],
    ) -> dict[str, str]:
        """Generate Word bookmark names for each note section.

        Used by NoteWordExporter for REF field generation.

        Requirements: 42.4
        """
        bookmarks: dict[str, str] = {}
        note_numbers = self._build_section_numbers(notes)

        for note in notes:
            if note.section_code:
                # Bookmark name: _Note_<section_code>
                bookmark_name = f"_Note_{note.section_code.replace('-', '_')}"
                bookmarks[note.section_code] = bookmark_name

        return bookmarks

    # ---------------------------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------------------------

    def _build_section_numbers(self, notes: list[Any]) -> dict[str, str]:
        """Build hierarchical section numbers based on note order and level.

        Returns: {section_code: "五、（一）1"} style numbering.
        """
        numbers: dict[str, str] = {}
        level1_counter = 0
        level2_counter = 0
        level3_counter = 0
        current_level1 = ""
        current_level2 = ""

        for note in notes:
            level = getattr(note, 'level', 1) or 1
            section_code = note.section_code or ""

            if level == 1:
                level1_counter += 1
                level2_counter = 0
                level3_counter = 0
                current_level1 = _to_chinese_number(level1_counter)
                number_str = f"{current_level1}"
                numbers[section_code] = number_str
            elif level == 2:
                level2_counter += 1
                level3_counter = 0
                current_level2 = f"（{_to_chinese_number(level2_counter)}）"
                number_str = f"{current_level1}、{current_level2}"
                numbers[section_code] = number_str
            elif level == 3:
                level3_counter += 1
                number_str = f"{current_level1}、{current_level2}{level3_counter}"
                numbers[section_code] = number_str
            else:
                # Default: use level 1 numbering
                level1_counter += 1
                current_level1 = _to_chinese_number(level1_counter)
                numbers[section_code] = current_level1

        return numbers

    def _get_linked_row_codes(self, note: Any) -> list[str]:
        """Get report row_codes linked to this note section."""
        # Try to extract from section_code pattern
        # Common pattern: section_code like "NOTE-BS-001" or metadata
        row_codes: list[str] = []

        section_code = note.section_code or ""

        # Check if section_code contains a report row reference
        match = re.search(r'(BS|IS|CFS|EQ)-\d+', section_code)
        if match:
            row_codes.append(match.group(0))

        # Check metadata for linked row_codes
        meta = getattr(note, 'metadata_', None) or {}
        if isinstance(meta, dict):
            linked = meta.get('linked_row_codes', [])
            if isinstance(linked, list):
                row_codes.extend(linked)

        return row_codes
