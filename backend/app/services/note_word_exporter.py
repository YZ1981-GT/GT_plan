"""附注 Word 导出引擎 — 致同标准格式

Sprint 6 Task 6.1 + 6.2: 重写 NoteWordExporter
致同标准格式：
  - 页面设置：A4、左 3cm/右 3.18cm/上 3.2cm/下 2.54cm、页眉 1.3cm/页脚 1.3cm
  - 字体：中文仿宋_GB2312 小四(12pt)、数字 Arial Narrow
  - 标题层级：一级"一、二、三..."加粗、二级"（一）（二）..."、三级"1. 2. 3."
  - 表格样式：上下边框 1 磅、标题行下边框 1/2 磅、标题行加粗居中、数据行金额右对齐
  - 段落格式：段前 0 行/段后 0.9 行、单倍行距

Requirements: 4.2-4.10, 27.1-27.10
"""

from __future__ import annotations

import logging
import re
from io import BytesIO
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn, nsdecls
from docx.oxml.parser import parse_xml
from docx.shared import Cm, Pt, RGBColor, Emu
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import DisclosureNote

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 致同标准格式常量
# ---------------------------------------------------------------------------

PAGE_MARGINS = {"top": Cm(3.2), "bottom": Cm(2.54), "left": Cm(3), "right": Cm(3.18)}
HEADER_MARGIN = Cm(1.3)
FOOTER_MARGIN = Cm(1.3)
BODY_FONT = "仿宋_GB2312"
BODY_SIZE = Pt(12)  # 小四
NUMBER_FONT = "Arial Narrow"
HEADING1_FONT_SIZE = Pt(12)
HEADING2_FONT_SIZE = Pt(12)
HEADING3_FONT_SIZE = Pt(12)

# 中文数字序列
_CN_NUMBERS = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
               "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
               "二十一", "二十二", "二十三", "二十四", "二十五", "二十六", "二十七", "二十八", "二十九", "三十"]

_CN_NUMBERS_PAREN = ["（一）", "（二）", "（三）", "（四）", "（五）", "（六）", "（七）", "（八）", "（九）", "（十）",
                     "（十一）", "（十二）", "（十三）", "（十四）", "（十五）", "（十六）", "（十七）", "（十八）", "（十九）", "（二十）"]


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _set_cell_border(cell, **kwargs):
    """Set cell border. Usage: _set_cell_border(cell, top={"sz": 12, "val": "single"})"""
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = OxmlElement("w:tcBorders")
    for edge in ("start", "top", "end", "bottom", "insideH", "insideV"):
        edge_data = kwargs.get(edge)
        if edge_data:
            element = OxmlElement(f"w:{edge}")
            for attr, val in edge_data.items():
                element.set(qn(f"w:{attr}"), str(val))
            tcBorders.append(element)
    tcPr.append(tcBorders)


def _set_table_borders(table, top_sz=8, bottom_sz=8, header_bottom_sz=4):
    """Set 致同 standard table borders: top/bottom 1pt, header bottom 0.5pt."""
    tbl = table._tbl
    tblPr = tbl.tblPr if tbl.tblPr is not None else OxmlElement("w:tblPr")

    borders = OxmlElement("w:tblBorders")
    for edge_name, sz in [("top", top_sz), ("bottom", bottom_sz)]:
        edge = OxmlElement(f"w:{edge_name}")
        edge.set(qn("w:val"), "single")
        edge.set(qn("w:sz"), str(sz))
        edge.set(qn("w:space"), "0")
        edge.set(qn("w:color"), "000000")
        borders.append(edge)

    # Remove left/right/insideV borders (致同 style = only top/bottom)
    for edge_name in ("left", "right", "insideV"):
        edge = OxmlElement(f"w:{edge_name}")
        edge.set(qn("w:val"), "none")
        edge.set(qn("w:sz"), "0")
        edge.set(qn("w:space"), "0")
        borders.append(edge)

    # insideH = none (we'll set header row bottom separately)
    insideH = OxmlElement("w:insideH")
    insideH.set(qn("w:val"), "none")
    insideH.set(qn("w:sz"), "0")
    insideH.set(qn("w:space"), "0")
    borders.append(insideH)

    tblPr.append(borders)
    if tbl.tblPr is None:
        tbl.append(tblPr)


def _set_row_bottom_border(row, sz=4):
    """Set bottom border on a specific row (for header row 0.5pt line)."""
    for cell in row.cells:
        tc = cell._tc
        tcPr = tc.get_or_add_tcPr()
        tcBorders = OxmlElement("w:tcBorders")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), str(sz))
        bottom.set(qn("w:space"), "0")
        bottom.set(qn("w:color"), "000000")
        tcBorders.append(bottom)
        tcPr.append(tcBorders)


def _format_amount(value) -> str:
    """Format amount with thousands separator."""
    if value is None or value == "" or value == 0:
        return "-"
    try:
        num = float(value)
        if num == 0:
            return "-"
        return f"{num:,.2f}"
    except (ValueError, TypeError):
        return str(value)


def _is_amount(value) -> bool:
    """Check if a value looks like a numeric amount."""
    if value is None or value == "" or value == "-":
        return False
    try:
        float(value)
        return True
    except (ValueError, TypeError):
        return False


def _add_toc(doc):
    """Add TOC field code that auto-updates on open."""
    paragraph = doc.add_paragraph()
    run = paragraph.add_run()
    fldChar = OxmlElement("w:fldChar")
    fldChar.set(qn("w:fldCharType"), "begin")
    run._r.append(fldChar)

    run2 = paragraph.add_run()
    instrText = OxmlElement("w:instrText")
    instrText.set(qn("xml:space"), "preserve")
    instrText.text = ' TOC \\o "1-3" \\h \\z \\u '
    run2._r.append(instrText)

    run3 = paragraph.add_run()
    fldChar2 = OxmlElement("w:fldChar")
    fldChar2.set(qn("w:fldCharType"), "separate")
    run3._r.append(fldChar2)

    run4 = paragraph.add_run("目录将在打开文档时自动更新")
    run4.font.color.rgb = RGBColor(128, 128, 128)

    run5 = paragraph.add_run()
    fldChar3 = OxmlElement("w:fldChar")
    fldChar3.set(qn("w:fldCharType"), "end")
    run5._r.append(fldChar3)

    return paragraph


def _add_page_number_footer(section):
    """Add footer with '第 X 页 共 Y 页' format."""
    footer = section.footer
    footer.is_linked_to_previous = False
    paragraph = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # "第 "
    run1 = paragraph.add_run("第 ")
    run1.font.name = BODY_FONT
    run1.font.size = Pt(9)

    # PAGE field
    run2 = paragraph.add_run()
    fldChar = OxmlElement("w:fldChar")
    fldChar.set(qn("w:fldCharType"), "begin")
    run2._r.append(fldChar)

    run3 = paragraph.add_run()
    instrText = OxmlElement("w:instrText")
    instrText.set(qn("xml:space"), "preserve")
    instrText.text = " PAGE "
    run3._r.append(instrText)

    run4 = paragraph.add_run()
    fldChar2 = OxmlElement("w:fldChar")
    fldChar2.set(qn("w:fldCharType"), "end")
    run4._r.append(fldChar2)

    # " 页 共 "
    run5 = paragraph.add_run(" 页 共 ")
    run5.font.name = BODY_FONT
    run5.font.size = Pt(9)

    # NUMPAGES field
    run6 = paragraph.add_run()
    fldChar3 = OxmlElement("w:fldChar")
    fldChar3.set(qn("w:fldCharType"), "begin")
    run6._r.append(fldChar3)

    run7 = paragraph.add_run()
    instrText2 = OxmlElement("w:instrText")
    instrText2.set(qn("xml:space"), "preserve")
    instrText2.text = " NUMPAGES "
    run7._r.append(instrText2)

    run8 = paragraph.add_run()
    fldChar4 = OxmlElement("w:fldChar")
    fldChar4.set(qn("w:fldCharType"), "end")
    run8._r.append(fldChar4)

    # " 页"
    run9 = paragraph.add_run(" 页")
    run9.font.name = BODY_FONT
    run9.font.size = Pt(9)


def _set_paragraph_format(paragraph, space_before=0, space_after=Pt(12), line_spacing=1.0):
    """Set 致同 standard paragraph format."""
    pf = paragraph.paragraph_format
    pf.space_before = space_before
    pf.space_after = space_after  # 段后 0.9 行 ≈ 12pt
    pf.line_spacing = line_spacing


def _set_run_font(run, font_name=BODY_FONT, size=BODY_SIZE, bold=False):
    """Set run font properties."""
    run.font.name = font_name
    run.font.size = size
    run.bold = bold
    # Set East Asian font
    rPr = run._r.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    rFonts.set(qn("w:eastAsia"), font_name)


def _add_bookmark(paragraph, bookmark_name: str):
    """Add a bookmark to a paragraph for cross-reference."""
    import random
    bookmark_id = str(random.randint(1000, 99999))
    bookmarkStart = OxmlElement("w:bookmarkStart")
    bookmarkStart.set(qn("w:id"), bookmark_id)
    bookmarkStart.set(qn("w:name"), bookmark_name)
    paragraph._p.append(bookmarkStart)

    bookmarkEnd = OxmlElement("w:bookmarkEnd")
    bookmarkEnd.set(qn("w:id"), bookmark_id)
    paragraph._p.append(bookmarkEnd)


# ---------------------------------------------------------------------------
# NoteWordExporter class
# ---------------------------------------------------------------------------


class NoteWordExporter:
    """附注 Word 导出引擎 — 致同标准格式

    Requirements: 4.2-4.10, 27.1-27.10
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def export(
        self,
        project_id: UUID,
        year: int,
        template_type: str = "soe",
        sections: list[str] | None = None,
        skip_empty: bool = False,
    ) -> BytesIO:
        """导出附注为 Word 文档（致同标准格式）

        Args:
            project_id: 项目 ID
            year: 年度
            template_type: 模板类型 (soe/listed)
            sections: 指定导出章节列表（None=全部）
            skip_empty: 是否跳过空章节

        Returns:
            BytesIO containing the docx file
        """
        # Load notes data
        notes = await self._load_notes(project_id, year, sections)

        # Filter empty sections if requested
        if skip_empty:
            notes = [n for n in notes if self._has_content(n)]

        # Build document
        doc = Document()
        self._setup_page(doc)
        self._add_title(doc, year)
        _add_toc(doc)
        doc.add_page_break()

        # Render sections
        level1_idx = 0
        level2_idx = 0
        level3_idx = 0
        current_level1 = ""

        for note in notes:
            section_code = note.note_section or ""
            level = self._detect_level(section_code)

            if level == 1:
                level1_idx += 1
                level2_idx = 0
                level3_idx = 0
                current_level1 = section_code
                self._add_heading1(doc, level1_idx, note.section_title or section_code, section_code)
            elif level == 2:
                level2_idx += 1
                level3_idx = 0
                self._add_heading2(doc, level2_idx, note.section_title or section_code, section_code)
            else:
                level3_idx += 1
                self._add_heading3(doc, level3_idx, note.section_title or section_code, section_code)

            # Content
            if self._has_content(note):
                self._render_note_content(doc, note)
            else:
                # Empty section placeholder
                p = doc.add_paragraph()
                run = p.add_run("本期无此项业务。")
                _set_run_font(run)
                _set_paragraph_format(p)

        # Save
        output = BytesIO()
        doc.save(output)
        output.seek(0)
        return output

    async def preview_html(self, project_id: UUID, year: int) -> str:
        """Generate HTML preview of notes.

        Requirements: 4.10, 27.10
        """
        notes = await self._load_notes(project_id, year)

        html_parts = ['<div class="note-preview" style="font-family: 仿宋_GB2312, FangSong; font-size: 12pt;">']
        html_parts.append(f'<h1 style="text-align:center;">财务报表附注</h1>')
        html_parts.append(f'<p style="text-align:center;">（{year}年度）</p>')

        level1_idx = 0
        level2_idx = 0
        level3_idx = 0

        for note in notes:
            level = self._detect_level(note.note_section or "")
            title = note.section_title or note.note_section or ""

            if level == 1:
                level1_idx += 1
                level2_idx = 0
                level3_idx = 0
                prefix = f"{_CN_NUMBERS[level1_idx - 1]}、" if level1_idx <= len(_CN_NUMBERS) else f"{level1_idx}、"
                html_parts.append(f'<h2 style="font-weight:bold;">{prefix}{title}</h2>')
            elif level == 2:
                level2_idx += 1
                level3_idx = 0
                prefix = _CN_NUMBERS_PAREN[level2_idx - 1] if level2_idx <= len(_CN_NUMBERS_PAREN) else f"（{level2_idx}）"
                html_parts.append(f'<h3>{prefix}{title}</h3>')
            else:
                level3_idx += 1
                html_parts.append(f'<h4>{level3_idx}. {title}</h4>')

            if self._has_content(note):
                if note.text_content:
                    html_parts.append(f'<p>{note.text_content}</p>')
                if note.table_data:
                    html_parts.append(self._table_to_html(note.table_data))
            else:
                html_parts.append('<p style="color:#999;">本期无此项业务。</p>')

        html_parts.append('</div>')
        return "\n".join(html_parts)

    # -----------------------------------------------------------------------
    # Private methods
    # -----------------------------------------------------------------------

    async def _load_notes(
        self, project_id: UUID, year: int, sections: list[str] | None = None
    ) -> list[DisclosureNote]:
        """Load notes from database."""
        q = sa.select(DisclosureNote).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
        ).order_by(DisclosureNote.note_section)

        result = await self.db.execute(q)
        notes = list(result.scalars().all())

        if sections:
            notes = [n for n in notes if n.note_section in sections]

        return notes

    def _has_content(self, note: DisclosureNote) -> bool:
        """Check if a note section has any content."""
        if note.text_content and note.text_content.strip():
            return True
        if note.table_data and isinstance(note.table_data, dict):
            rows = note.table_data.get("rows", [])
            if rows:
                # Check if any row has non-zero values
                for row in rows:
                    values = row.get("values", [])
                    cells = row.get("cells", values)
                    for cell in cells:
                        if isinstance(cell, dict):
                            val = cell.get("value", cell.get("manual_value", 0))
                        else:
                            val = cell
                        if val and val != 0 and val != "0" and val != "-":
                            return True
            return False
        return False

    def _detect_level(self, section_code: str) -> int:
        """Detect heading level from section code pattern."""
        if not section_code:
            return 3
        # Pattern: "5" or "V" = level 1, "5.1" or "V.1" = level 2, "5.1.1" = level 3
        parts = section_code.split(".")
        if len(parts) == 1:
            return 1
        elif len(parts) == 2:
            return 2
        else:
            return 3

    def _setup_page(self, doc: Document):
        """Set up page margins and orientation per 致同 standard."""
        section = doc.sections[0]
        section.page_width = Cm(21)  # A4
        section.page_height = Cm(29.7)
        section.orientation = WD_ORIENT.PORTRAIT
        section.top_margin = PAGE_MARGINS["top"]
        section.bottom_margin = PAGE_MARGINS["bottom"]
        section.left_margin = PAGE_MARGINS["left"]
        section.right_margin = PAGE_MARGINS["right"]
        section.header_distance = HEADER_MARGIN
        section.footer_distance = FOOTER_MARGIN

        # Add page number footer
        _add_page_number_footer(section)

    def _add_title(self, doc: Document, year: int):
        """Add document title."""
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run("财务报表附注")
        run.font.name = BODY_FONT
        run.font.size = Pt(16)
        run.bold = True
        # East Asian font
        rPr = run._r.get_or_add_rPr()
        rFonts = rPr.find(qn("w:rFonts"))
        if rFonts is None:
            rFonts = OxmlElement("w:rFonts")
            rPr.insert(0, rFonts)
        rFonts.set(qn("w:eastAsia"), BODY_FONT)

        p2 = doc.add_paragraph()
        p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run2 = p2.add_run(f"（{year}年度）")
        _set_run_font(run2, size=Pt(14))

    def _add_heading1(self, doc: Document, idx: int, title: str, section_code: str):
        """Add level 1 heading: 一、二、三... (bold)"""
        prefix = f"{_CN_NUMBERS[idx - 1]}、" if idx <= len(_CN_NUMBERS) else f"{idx}、"
        p = doc.add_paragraph()
        run = p.add_run(f"{prefix}{title}")
        _set_run_font(run, bold=True, size=HEADING1_FONT_SIZE)
        _set_paragraph_format(p, space_before=Pt(6))
        _add_bookmark(p, f"note_section_{section_code}")

    def _add_heading2(self, doc: Document, idx: int, title: str, section_code: str):
        """Add level 2 heading: （一）（二）..."""
        prefix = _CN_NUMBERS_PAREN[idx - 1] if idx <= len(_CN_NUMBERS_PAREN) else f"（{idx}）"
        p = doc.add_paragraph()
        run = p.add_run(f"{prefix}{title}")
        _set_run_font(run, size=HEADING2_FONT_SIZE)
        _set_paragraph_format(p)
        _add_bookmark(p, f"note_section_{section_code}")

    def _add_heading3(self, doc: Document, idx: int, title: str, section_code: str):
        """Add level 3 heading: 1. 2. 3."""
        p = doc.add_paragraph()
        run = p.add_run(f"{idx}. {title}")
        _set_run_font(run, size=HEADING3_FONT_SIZE)
        _set_paragraph_format(p)
        _add_bookmark(p, f"note_section_{section_code}")

    def _render_note_content(self, doc: Document, note: DisclosureNote):
        """Render note content (text + tables)."""
        # Text content
        if note.text_content and note.text_content.strip():
            p = doc.add_paragraph()
            run = p.add_run(note.text_content.strip())
            _set_run_font(run)
            _set_paragraph_format(p)

        # Table data
        if note.table_data and isinstance(note.table_data, dict):
            self._render_table(doc, note.table_data)

    def _render_table(self, doc: Document, table_data: dict):
        """Render a table with 致同 standard formatting."""
        headers = table_data.get("headers", [])
        rows = table_data.get("rows", [])

        if not headers or not rows:
            return

        num_cols = len(headers)
        num_rows = len(rows) + 1  # +1 for header row

        table = doc.add_table(rows=num_rows, cols=num_cols)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER

        # Set 致同 table borders
        _set_table_borders(table)

        # Header row
        header_row = table.rows[0]
        for i, h in enumerate(headers):
            cell = header_row.cells[i]
            cell.text = ""
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(str(h))
            _set_run_font(run, bold=True)

        # Header row bottom border (0.5pt = 4 half-points)
        _set_row_bottom_border(header_row, sz=4)

        # Data rows
        for r_idx, row in enumerate(rows):
            label = row.get("label", "")
            values = row.get("values", [])
            cells_data = row.get("cells", values)

            # First column: label
            cell0 = table.rows[r_idx + 1].cells[0]
            cell0.text = ""
            p0 = cell0.paragraphs[0]
            run0 = p0.add_run(str(label))
            _set_run_font(run0)

            # Data columns: amounts right-aligned with Arial Narrow
            for c_idx, val in enumerate(cells_data):
                if c_idx + 1 >= num_cols:
                    break
                cell = table.rows[r_idx + 1].cells[c_idx + 1]
                cell.text = ""
                p = cell.paragraphs[0]
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT

                # Extract value
                if isinstance(val, dict):
                    cell_val = val.get("value", val.get("manual_value", 0))
                else:
                    cell_val = val

                formatted = _format_amount(cell_val)
                run = p.add_run(formatted)
                # Use Arial Narrow for numbers
                if _is_amount(cell_val):
                    _set_run_font(run, font_name=NUMBER_FONT)
                else:
                    _set_run_font(run)

        # Add spacing after table
        doc.add_paragraph()

    def _table_to_html(self, table_data: dict) -> str:
        """Convert table data to HTML for preview."""
        headers = table_data.get("headers", [])
        rows = table_data.get("rows", [])

        if not headers:
            return ""

        html = ['<table style="border-collapse:collapse; width:100%; margin:8px 0; border-top:1px solid #000; border-bottom:1px solid #000;">']
        # Header
        html.append('<tr style="border-bottom:0.5px solid #000;">')
        for h in headers:
            html.append(f'<th style="padding:4px 8px; text-align:center; font-weight:bold;">{h}</th>')
        html.append('</tr>')

        # Rows
        for row in rows:
            html.append('<tr>')
            label = row.get("label", "")
            html.append(f'<td style="padding:4px 8px;">{label}</td>')
            values = row.get("values", [])
            cells_data = row.get("cells", values)
            for val in cells_data:
                if isinstance(val, dict):
                    cell_val = val.get("value", val.get("manual_value", 0))
                else:
                    cell_val = val
                formatted = _format_amount(cell_val)
                html.append(f'<td style="padding:4px 8px; text-align:right; font-family:Arial Narrow;">{formatted}</td>')
            html.append('</tr>')

        html.append('</table>')
        return "\n".join(html)
