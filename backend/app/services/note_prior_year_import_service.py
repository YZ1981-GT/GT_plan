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

import copy
import io
import logging
import re
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.note_edit_stamp import stamp_note_edit

logger = logging.getLogger(__name__)

#: 本年表的期初列 / 上年表的期末列（表头包含其一即算）
_OPENING_HEADERS = ("期初", "年初", "上年末", "上期末")
_CLOSING_HEADERS = ("期末", "年末", "本期末")
_WS = re.compile(r"[\s\u3000]+")


def _norm_label(value: Any) -> str:
    return _WS.sub("", str(value or ""))


def _header_index(headers: list[Any], keys: tuple[str, ...]) -> int | None:
    """第一个（跳过标签列）表头含任一关键字的列号。"""
    for i, h in enumerate(headers):
        if i and any(k in str(h or "") for k in keys):
            return i
    return None


def _parse_amount(text: Any) -> float | None:
    """Word 表格里的金额文字 → 数值：去千分位，（）/ () 表负数，空 / - / — 视为无值。"""
    s = str(text or "").replace(",", "").replace("，", "").strip()
    negative = s[:1] in ("(", "（") and s[-1:] in (")", "）")
    s = s.strip("()（）").strip()
    if s in ("", "-", "—", "--"):
        return None
    try:
        value = float(s)
    except ValueError:
        return None
    return -value if negative else value


def _extract_to_opening_balance(table: dict[str, Any], prior_rows: list[list[str]]) -> int:
    """把上年表「期末」列按行标签填进本年表「期初」列，只填空格（不覆盖已有值）；返回填入格数。

    ``table`` 是附注表（``headers`` + ``rows[{label, values}]``，``values`` 不含标签列 ⇒ 下标 = 表头列号 - 1）；
    ``prior_rows`` 是 Word 表格（首行表头，首列行标签）。
    """
    if len(prior_rows) < 2:
        return 0
    open_col = _header_index(list(table.get("headers") or []), _OPENING_HEADERS)
    close_col = _header_index(list(prior_rows[0]), _CLOSING_HEADERS)
    if open_col is None or close_col is None:
        return 0
    closing: dict[str, float] = {}
    for row in prior_rows[1:]:
        if len(row) > close_col and _norm_label(row[0]):
            value = _parse_amount(row[close_col])
            if value is not None:
                closing.setdefault(_norm_label(row[0]), value)
    filled = 0
    for row in table.get("rows") or []:
        if not isinstance(row, dict) or not isinstance(row.get("values"), list):
            continue
        value = closing.get(_norm_label(row.get("label")))
        if value is None:
            continue
        values = row["values"]
        while len(values) < open_col:
            values.append(None)
        if values[open_col - 1] in (None, ""):
            values[open_col - 1] = value
            filled += 1
    return filled


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
        *,
        user_id: UUID | None = None,
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
                DisclosureNote.is_deleted == sa.false(),
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

        # Build title → note mapping for current year（标题列是 section_title；原来读不存在的 note.title ⇒ 整个导入必 500）
        title_to_note: dict[str, Any] = {}
        for note in current_notes:
            title_key = self._normalize_title(note.section_title or "")
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
                if self._fill_prior_year_content(note, prior_section):
                    stamp_note_edit(note, user_id)
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
        *,
        user_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Inherit notes from prior year database (continuous audit).

        For projects with prior year data in the same database,
        automatically copy text content and mark as "待更新".

        Requirements: 51.7, 51.8
        """
        from app.models.report_models import DisclosureNote

        prior_year = year - 1

        # Check if prior year notes exist（回收站里的不算）
        result = await self.db.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == prior_year,
                DisclosureNote.is_deleted == sa.false(),
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
                DisclosureNote.is_deleted == sa.false(),
            )
        )
        current_notes = result.scalars().all()

        if not current_notes:
            return {
                "status": "error",
                "message": "本年附注尚未生成，请先生成附注",
                "inherited": 0,
            }

        # Build mapping by note_section (DisclosureNote 无 section_code 列，
        # 用 note_section 作为跨年匹配键，如 "五、1 存货")
        prior_by_section: dict[str, Any] = {}
        for pn in prior_notes:
            if pn.note_section:
                prior_by_section[pn.note_section] = pn

        inherited = 0
        for note in current_notes:
            if not note.note_section:
                continue
            prior = prior_by_section.get(note.note_section)
            if prior and prior.text_content:
                # 跳过 is_local_override 的章节：用户已通过内容模板写入自定义正文，
                # 上年继承不得覆盖（与 disclosure_engine / wp_disclosure_sync_service 同口径）
                if note.is_local_override or note.text_content == prior.text_content:
                    continue
                # Copy text content, mark as pending update
                note.text_content = prior.text_content
                # 在 template_lineage（JSONB）中记录继承来源（新字典赋值：原地改 JSONB 不会被识别为改动）
                lineage = dict(note.template_lineage) if isinstance(note.template_lineage, dict) else {}
                lineage["prior_year_inherited"] = True
                lineage["prior_year_status"] = "pending_update"
                lineage["prior_year_source"] = prior_year
                note.template_lineage = lineage
                stamp_note_edit(note, user_id)
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

    def _fill_prior_year_content(
        self,
        note: Any,
        prior_section: dict[str, Any],
    ) -> bool:
        """把上年 Word 一节填进本年章节：正文（内容模板写过的不覆盖）+ 表格期初列；有改动返回 True。

        表格按表序配对（多表取 ``_tables``，顶层是第一张表的镜像、一并填）；改的是副本再整体赋值，
        原地改 JSONB 不会被识别为改动、不落库。
        """
        changed = False
        text = prior_section.get("text_content") or ""
        if text.strip() and not note.is_local_override and note.text_content != text:
            note.text_content = text
            changed = True

        prior_tables = prior_section.get("tables") or []
        if prior_tables and isinstance(note.table_data, dict) and note.table_data:
            td = copy.deepcopy(note.table_data)
            tables = td.get("_tables") if isinstance(td.get("_tables"), list) else []
            pairs = list(zip([t for t in tables if isinstance(t, dict)] or [td], prior_tables))
            if tables and isinstance(td.get("rows"), list):
                pairs.append((td, prior_tables[0]))  # 顶层镜像第一张表
            if sum(_extract_to_opening_balance(t, p) for t, p in pairs):
                note.table_data = td
                changed = True

        if changed:
            lineage = dict(note.template_lineage) if isinstance(note.template_lineage, dict) else {}
            lineage["prior_year_imported"] = True
            lineage["prior_year_status"] = "pending_update"
            note.template_lineage = lineage
        return changed
