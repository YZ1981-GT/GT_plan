"""附注 Word 导出引擎

Phase 9 Task 9.30: python-docx 精确控制格式
"""

from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import DisclosureNote

logger = logging.getLogger(__name__)


class NoteWordExporter:
    """附注 Word 导出"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def export(self, project_id: UUID, year: int, sections: list[str] | None = None) -> BytesIO:
        """导出附注为 Word 文档"""
        import docx
        from docx.shared import Cm, Pt
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        # 获取附注数据
        q = sa.select(DisclosureNote).where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
        ).order_by(DisclosureNote.note_section)
        notes = (await self.db.execute(q)).scalars().all()

        if sections:
            notes = [n for n in notes if n.note_section in sections]

        doc = docx.Document()

        # 页面设置
        section = doc.sections[0]
        section.top_margin = Cm(3)
        section.bottom_margin = Cm(2.54)
        section.left_margin = Cm(3.18)
        section.right_margin = Cm(3.2)

        # 标题
        title = doc.add_heading("财务报表附注", level=0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER

        for note in notes:
            # 章节标题
            heading = f"{note.note_section} {note.section_title or ''}"
            doc.add_heading(heading, level=2)

            # 表格数据
            if note.table_data and isinstance(note.table_data, dict):
                headers = note.table_data.get("headers", [])
                rows = note.table_data.get("rows", [])

                if headers and rows:
                    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
                    table.style = "Table Grid"

                    # 表头
                    for i, h in enumerate(headers):
                        cell = table.rows[0].cells[i]
                        cell.text = str(h)
                        for p in cell.paragraphs:
                            for run in p.runs:
                                run.bold = True
                                run.font.size = Pt(10)

                    # 数据行
                    for r_idx, row in enumerate(rows):
                        label = row.get("label", "")
                        values = row.get("values", [])
                        cells_data = row.get("cells", values)

                        table.rows[r_idx + 1].cells[0].text = str(label)
                        for c_idx, val in enumerate(cells_data):
                            if c_idx + 1 < len(headers):
                                cell_val = val
                                if isinstance(val, dict):
                                    cell_val = val.get("value", val.get("manual_value", 0))
                                cell = table.rows[r_idx + 1].cells[c_idx + 1]
                                cell.text = f"{float(cell_val):,.2f}" if cell_val else "-"
                                # 数字右对齐
                                for p in cell.paragraphs:
                                    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT

                    doc.add_paragraph()  # 空行

            # 文字内容
            if note.text_content:
                doc.add_paragraph(note.text_content)

        # 页脚页码
        # python-docx 页码需要 XML 操作，简化处理
        doc.add_paragraph()

        output = BytesIO()
        doc.save(output)
        output.seek(0)
        return output
