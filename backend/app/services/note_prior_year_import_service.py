"""NotePriorYearImportService — 上年附注导入与继承

Requirements: 51.1, 51.2, 51.3, 51.4, 51.5, 51.7, 51.8

功能：
- 接受 .docx 上传，解析 Word 章节结构（按标题层级拆分）
- 上年文字内容填入本年对应章节（按标题匹配）
- 上年数据标记为"待更新"（黄色高亮）
- 上年表格数据提取到"期初余额"列
- 连续审计项目自动从上年数据库继承
"""
from __future__ import annotations

import io
import logging
import re
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Word Document Parser
# ---------------------------------------------------------------------------


class DocxSectionParser:
    """Parse a .docx file into sections by heading level."""

    # Chinese numbering patterns for heading detection
    HEADING_PATTERNS = [
        # Level 1: 一、二、三、...
        (1, re.compile(r'^[一二三四五六七八九十]+、')),
        # Level 2: （一）（二）（三）...
        (2, re.compile(r'^（[一二三四五六七八九十]+）')),
        # Level 3: 1. 2. 3. or 1、2、3、
        (3, re.compile(r'^\d+[.、]')),
    ]

    def parse(self, file_bytes: bytes) -> list[dict[str, Any]]:
        """Parse docx bytes into a list of sections.

        Each section: {
            "title": str,
            "level": int (1-3),
            "text_content": str,
            "tables": list[list[list[str]]],  # table -> rows -> cells
        }
        """
        try:
            from docx import Document
        except ImportError:
            logger.warning("python-docx not installed, cannot parse docx")
            return []

        doc = Document(io.BytesIO(file_bytes))
        sections: list[dict[str, Any]] = []
        current_section: dict[str, Any] | None = None

        for element in doc.element.body:
            tag = element.tag.split('}')[-1] if '}' in element.tag else element.tag

            if tag == 'p':
                # Process paragraph
                from docx.oxml.ns import qn
                paragraph = element
                text = ''.join(
                    node.text or ''
                    for node in paragraph.iter(qn('w:t'))
                )
                text = text.strip()

                if not text:
                    if current_section:
                        current_section["text_content"] += "\n"
                    continue

                # Check if this is a heading
                heading_level = self._detect_heading_level(paragraph, text)

                if heading_level:
                    # Start new section
                    if current_section:
                        sections.append(current_section)
                    current_section = {
                        "title": text,
                        "level": heading_level,
                        "text_content": "",
                        "tables": [],
                    }
                else:
                    # Add to current section text
                    if current_section:
                        if current_section["text_content"]:
                            current_section["text_content"] += "\n"
                        current_section["text_content"] += text
                    else:
                        # Text before first heading - create implicit section
                        current_section = {
                            "title": "前言",
                            "level": 0,
                            "text_content": text,
                            "tables": [],
                        }

            elif tag == 'tbl':
                # Process table
                if current_section:
                    table_data = self._parse_table_element(element)
                    if table_data:
                        current_section["tables"].append(table_data)

        # Don't forget the last section
        if current_section:
            sections.append(current_section)

        return sections

    def _detect_heading_level(self, paragraph_element, text: str) -> int | None:
        """Detect heading level from paragraph style or text pattern."""
        from docx.oxml.ns import qn

        # Check Word heading style
        pPr = paragraph_element.find(qn('w:pPr'))
        if pPr is not None:
            pStyle = pPr.find(qn('w:pStyle'))
            if pStyle is not None:
                style_val = pStyle.get(qn('w:val'), '')
                if 'Heading' in style_val or '标题' in style_val:
                    # Extract level from style name
                    level_match = re.search(r'(\d+)', style_val)
                    if level_match:
                        return min(int(level_match.group(1)), 3)
                    return 1

        # Check text patterns
        for level, pattern in self.HEADING_PATTERNS:
            if pattern.match(text):
                return level

        return None

    def _parse_table_element(self, tbl_element) -> list[list[str]]:
        """Parse a table XML element into rows of cells."""
        from docx.oxml.ns import qn

        rows: list[list[str]] = []
        for tr in tbl_element.iter(qn('w:tr')):
            cells: list[str] = []
            for tc in tr.iter(qn('w:tc')):
                cell_text = ''.join(
                    node.text or ''
                    for node in tc.iter(qn('w:t'))
                )
                cells.append(cell_text.strip())
            if cells:
                rows.append(cells)
        return rows


# ---------------------------------------------------------------------------
# NotePriorYearImportService
# ---------------------------------------------------------------------------


class NotePriorYearImportService:
    """Service for importing prior year notes from .docx or database."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def import_from_docx(
        self,
        project_id: UUID,
        year: int,
        file_bytes: bytes,
    ) -> dict[str, Any]:
        """Import prior year notes from a .docx file.

        Steps:
        1. Parse docx into sections
        2. Match sections to current year note structure by title
        3. Fill matched text content (marked as "待更新")
        4. Extract table data to "期初余额" column

        Requirements: 51.1, 51.2, 51.3, 51.4, 51.5
        """
        parser = DocxSectionParser()
        prior_sections = parser.parse(file_bytes)

        if not prior_sections:
            return {
                "status": "error",
                "message": "无法解析文档内容，请确认文件格式正确",
                "matched": 0,
                "unmatched": 0,
            }

        # Load current year notes
        from app.models.report_models import DisclosureNote

        result = await self.db.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
            )
        )
        current_notes = result.scalars().all()

        if not current_notes:
            return {
                "status": "error",
                "message": "本年附注尚未生成，请先生成附注再导入上年数据",
                "matched": 0,
                "unmatched": len(prior_sections),
            }

        # Build title → note mapping for current year
        title_to_note: dict[str, Any] = {}
        for note in current_notes:
            # Normalize title for matching
            title_key = self._normalize_title(note.title or "")
            if title_key:
                title_to_note[title_key] = note

        # Match and fill
        matched = 0
        unmatched = 0
        matched_sections: list[str] = []
        unmatched_sections: list[str] = []

        for prior_section in prior_sections:
            prior_title_key = self._normalize_title(prior_section["title"])
            if not prior_title_key:
                continue

            note = title_to_note.get(prior_title_key)
            if note:
                # Fill text content with prior year data
                await self._fill_prior_year_content(
                    note, prior_section
                )
                matched += 1
                matched_sections.append(prior_section["title"])
            else:
                unmatched += 1
                unmatched_sections.append(prior_section["title"])

        await self.db.flush()

        return {
            "status": "success",
            "matched": matched,
            "unmatched": unmatched,
            "matched_sections": matched_sections[:20],
            "unmatched_sections": unmatched_sections[:20],
            "total_prior_sections": len(prior_sections),
        }

    async def inherit_from_prior_year(
        self,
        project_id: UUID,
        year: int,
    ) -> dict[str, Any]:
        """Inherit notes from prior year database (continuous audit).

        For projects with prior year data in the same database,
        automatically copy text content and mark as "待更新".

        Requirements: 51.7, 51.8
        """
        from app.models.report_models import DisclosureNote

        prior_year = year - 1

        # Check if prior year notes exist
        result = await self.db.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == prior_year,
            )
        )
        prior_notes = result.scalars().all()

        if not prior_notes:
            return {
                "status": "no_prior_data",
                "message": f"未找到 {prior_year} 年度附注数据",
                "inherited": 0,
            }

        # Load current year notes
        result = await self.db.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
            )
        )
        current_notes = result.scalars().all()

        if not current_notes:
            return {
                "status": "error",
                "message": "本年附注尚未生成，请先生成附注",
                "inherited": 0,
            }

        # Build mapping by section_code
        prior_by_code: dict[str, Any] = {}
        for pn in prior_notes:
            if pn.section_code:
                prior_by_code[pn.section_code] = pn

        inherited = 0
        for note in current_notes:
            if not note.section_code:
                continue
            prior = prior_by_code.get(note.section_code)
            if prior and prior.text_content:
                # Copy text content, mark as pending update
                note.text_content = prior.text_content
                # Mark in metadata that this is inherited data
                meta = note.metadata_ if hasattr(note, 'metadata_') else {}
                if meta is None:
                    meta = {}
                meta["prior_year_inherited"] = True
                meta["prior_year_status"] = "pending_update"
                if hasattr(note, 'metadata_'):
                    note.metadata_ = meta
                inherited += 1

        await self.db.flush()

        return {
            "status": "success",
            "inherited": inherited,
            "total_prior_notes": len(prior_notes),
            "total_current_notes": len(current_notes),
        }

    # ---------------------------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------------------------

    def _normalize_title(self, title: str) -> str:
        """Normalize title for matching (remove numbering, whitespace)."""
        # Remove leading numbering patterns
        title = re.sub(r'^[一二三四五六七八九十]+、\s*', '', title)
        title = re.sub(r'^（[一二三四五六七八九十]+）\s*', '', title)
        title = re.sub(r'^\d+[.、]\s*', '', title)
        # Remove whitespace
        title = title.strip()
        return title

    async def _fill_prior_year_content(
        self,
        note: Any,
        prior_section: dict[str, Any],
    ) -> None:
        """Fill a note with prior year content."""
        # Fill text content
        if prior_section["text_content"]:
            note.text_content = prior_section["text_content"]

        # Extract table data to period_start column if tables exist
        if prior_section["tables"] and hasattr(note, 'table_data'):
            table_data = note.table_data or []
            for i, prior_table in enumerate(prior_section["tables"]):
                if i < len(table_data):
                    # Try to fill "期初余额" column from prior year data
                    self._extract_to_opening_balance(table_data[i], prior_table)
