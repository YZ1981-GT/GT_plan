"""鉴证报告共用：样表年度文字替换、金额文字、Word 段落文字替换、下载响应。"""

from __future__ import annotations

import re
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi.responses import StreamingResponse

from app.services.tax_formula_engine import XlError

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "tax_assurance"

#: 样表与案例文件里写死的审核年度（报告落款年 = 审核年度 + 1）
SAMPLE_YEAR = 2025
_YEAR_TEXT_RE = re.compile(rf"{SAMPLE_YEAR}(\s*)年度")
_REPORT_YEAR_RE = re.compile(rf"(日期：\s*){SAMPLE_YEAR + 1}年")

XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX_MEDIA = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def year_text(text: str, year: int) -> str:
    """样表常量里的「2025年度」换成审核年度；法规文号（「2025年第 N 号」）不带「度」，不受影响。"""
    out = _YEAR_TEXT_RE.sub(lambda m: f"{year}{m.group(1)}年度", text)
    return _REPORT_YEAR_RE.sub(lambda m: f"{m.group(1)}{year + 1}年", out)


def money_text(v: Any) -> str:
    """金额文字：#,##0.00；舍入后为 0 的微小负数写「0.00」不写「-0.00」；非数字原样。"""
    if isinstance(v, Decimal):
        q = v.quantize(Decimal("0.01"))
        return f"{(q if q != 0 else abs(q)):,.2f}"
    if v is None:
        return ""
    return str(v)


def value_text(v: Any) -> str:
    """单元格值 → 显示文字（错误值显示错误码）。"""
    if v is None:
        return ""
    if isinstance(v, XlError):
        return str(v)
    if isinstance(v, bool):
        return "是" if v else "否"
    if isinstance(v, Decimal):
        return money_text(v)
    return str(v)


def is_zero(v: Any) -> bool:
    return v is None or (isinstance(v, Decimal) and abs(v) < Decimal("0.005"))


def download(content: bytes, filename: str, media_type: str) -> StreamingResponse:
    ascii_name = filename.encode("ascii", "ignore").decode() or "download"
    return StreamingResponse(
        BytesIO(content),
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename, safe='')}"},
    )


# ── Word：按段替换文字（Word 会把一句话拆成多个 run，先合并再替换） ──
def _iter_paragraphs(doc):
    """正文、表格、页眉页脚里的全部段落（含嵌套表格）。"""
    def walk(container):
        for p in container.paragraphs:
            yield p
        for table in getattr(container, "tables", []):
            for row in table.rows:
                for cell in row.cells:
                    yield from walk(cell)

    yield from walk(doc)
    for section in doc.sections:
        for part in (section.header, section.footer, section.first_page_header, section.first_page_footer):
            # 没有自己定义的页眉页脚（沿用上一节）不碰：访问 paragraphs 会凭空新建页眉部件
            if not part.is_linked_to_previous:
                yield from walk(part)


def replace_in_paragraph(paragraph, replacements: dict[str, str]) -> bool:
    """段内文字按 ``replacements`` 替换；有改动时全段文字放进第一个 run（保留其格式），其余 run 清空。"""
    runs = paragraph.runs
    if not runs:
        return False
    text = "".join(r.text for r in runs)
    new = text
    for old, rep in replacements.items():
        new = new.replace(old, rep)
    if new == text:
        return False
    runs[0].text = new
    for r in runs[1:]:
        r.text = ""
    return True


def replace_in_document(doc, replacements: dict[str, str]) -> int:
    """全文替换，返回改动的段落数。"""
    return sum(1 for p in _iter_paragraphs(doc) if replace_in_paragraph(p, replacements))


def save_docx(doc) -> bytes:
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()
