"""报告正文：底稿 1-01（报告封面 + 报告正文）的计算结果按文书版式给出，导出 Word。

- 摘录表 25 行金额取申报主表 A100000（1-01报告正文 F17~F41 公式）；0 值留空（与案例报告一致）。
  可在本页手工修改（存底稿 1-01 的手工值，与税审底稿页同一处，spec citar-table-manual-edit R9）。
- 报告号取「填写参数」B15（1-01报告正文 E3 公式）；报告日期存 ``tax_workpaper_inputs``（``__assurance__``）。
- 样表文字里写死的「2025年度」按审核年度替换（``common.year_text``）。
- 网页预览：导出的 Word 经 OnlyOffice 转 PDF（``preview_pdf``，``services/onlyoffice_pdf``）。
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from decimal import Decimal
from typing import Any
from uuid import UUID

from docx import Document
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tax_workpaper_models import ASSURANCE_SHEET_CODE
from app.services import onlyoffice_pdf
from app.services import tax_workpaper_service as tws
from app.services.tax_assurance.common import DATA_DIR, is_zero, money_text, replace_in_document, save_docx, value_text, year_text

COVER_SHEET = "1-01报告封面"
BODY_SHEET = "1-01报告正文"
TEMPLATE = DATA_DIR / "report_body.docx"

#: 正文各段所在格（样表 1-01报告正文）
INTRO_REFS = ["A6", "A8", "A10", "A12", "A14"]
CLOSING_REFS = ["A42", "A47"]
SIGN_REFS = ["A51", "A53"]
FIRM_REFS = ["A55", "A57", "A58"]
ATTACH_TITLE_REF = "A61"
ATTACH_REFS = ["A62", "A63", "A64", "A65", "A66"]
#: 摘录表：第 17~41 行，A 序号 / B 项目 / F 金额
TABLE_ROWS = range(17, 42)
AMOUNT_COL = 6  # F
RATE_ROW = 28
#: 摘录表金额的手工值存在底稿 1-01 那一行（与税审底稿页改 1-01 同一处）
AMOUNTS_CODE = "1-01"
DATE_KEY = "report_date"
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _amount_text(row: int, v: Any) -> str:
    if row == RATE_ROW and isinstance(v, Decimal):
        return f"{(v * 100).normalize():f}%"
    return "" if is_zero(v) else money_text(v)


def _date_text(date: str | None, year: int) -> str:
    if date and _DATE_RE.match(date):
        d = dt.date.fromisoformat(date)
        return f"{d.year}年{d.month}月{d.day}日"
    return f"{year + 1}年  月  日"


async def _assurance_row(db: AsyncSession, project_id: UUID, year: int):
    return (await tws._rows(db, project_id, year)).get(ASSURANCE_SHEET_CODE)


async def build(db: AsyncSession, project_id: UUID, year: int) -> dict:
    wb = tws.load_workbook()
    seeds = [k for s in (COVER_SHEET, BODY_SHEET) for k in wb.print_keys(s)]
    rows = await tws._rows(db, project_id, year)
    # 版本与报告日期立即取成普通值（之后取数查询失败时会话里的 ORM 对象会过期）
    assurance = rows.get(ASSURANCE_SHEET_CODE)
    version = assurance.version if assurance else 0
    date = ((assurance.inputs or {}).get(ASSURANCE_SHEET_CODE, {}) if assurance else {}).get(DATE_KEY)
    amounts_version = rows[AMOUNTS_CODE].version if AMOUNTS_CODE in rows else 0
    ev = await tws.evaluate_keys(db, project_id, year, seeds, rows)
    auto_values = getattr(ev.computed, "auto", {})

    def text(sheet: str, ref: str) -> str:
        return year_text(value_text(ev.value(sheet, ref)), year).strip()

    lines = []
    for r in TABLE_ROWS:
        v = ev.value(BODY_SHEET, f"F{r}")
        key = (BODY_SHEET, r, AMOUNT_COL)
        manual = key in ev.inputs
        # 公式格的原值 = 公式结果；税率行（第 28 行）是样表常量，原值 = 样表值
        auto = auto_values.get(key) if key in wb.formulas else wb.consts.get(key)
        lines.append({
            "row": r,
            "no": value_text(ev.value(BODY_SHEET, f"A{r}")),
            "item": text(BODY_SHEET, f"B{r}"),
            "amount": encode_amount(v),
            "amount_text": _amount_text(r, v),
            "is_rate": r == RATE_ROW,
            # 本页或底稿 1-01 手工改过的金额：auto = 按公式取自申报表的值（spec citar-table-manual-edit R9）
            "manual": manual,
            "auto": encode_amount(auto) if manual else None,
        })
    client = text(COVER_SHEET, "A4")
    return {
        "year": year,
        "version": version,
        "amounts_version": amounts_version,
        "cover": {
            "client": client,
            "title": text(COVER_SHEET, "A6"),
            "period": text(COVER_SHEET, "A8"),
            "firm": text(COVER_SHEET, "A17"),
        },
        "title": text(BODY_SHEET, "A2"),
        "report_no": text(BODY_SHEET, "E3"),
        "addressee": text(BODY_SHEET, "A4"),
        "intro": [text(BODY_SHEET, r) for r in INTRO_REFS],
        "lines": lines,
        "closing": [text(BODY_SHEET, r) for r in CLOSING_REFS],
        "signatures": [text(BODY_SHEET, r) for r in SIGN_REFS],
        "firm": [text(BODY_SHEET, r) for r in FIRM_REFS],
        "report_date": date,
        "report_date_text": f"日期：{_date_text(date, year)}",
        "attachments_title": text(BODY_SHEET, ATTACH_TITLE_REF),
        "attachments": [t for t in (text(BODY_SHEET, r) for r in ATTACH_REFS) if t],
        "notices": ev.notices,
    }


def encode_amount(v: Any) -> dict | None:
    return tws.encode_value(v)


async def save_report_date(db: AsyncSession, project_id: UUID, year: int, version: int, date: str | None, user_id: UUID) -> None:
    if date not in (None, "") and not (_DATE_RE.match(date) and _valid_date(date)):
        raise HTTPException(status_code=422, detail="报告日期格式应为 YYYY-MM-DD")
    await tws._project(db, project_id)
    row = await _assurance_row(db, project_id, year)
    values = dict((row.inputs or {}).get(ASSURANCE_SHEET_CODE, {})) if row else {}
    values[DATE_KEY] = date or None
    await tws._upsert(db, project_id, year, ASSURANCE_SHEET_CODE, version, {ASSURANCE_SHEET_CODE: values}, user_id)


async def save_amounts(
    db: AsyncSession, project_id: UUID, year: int, version: int, values: dict[str, Any], user_id: UUID,
) -> None:
    """摘录表 25 行金额的手工值：``values`` = {行号: 数字 | null(空白)}，整份替换这 25 格，
    不在里面的行恢复为公式值；1-01 的其他手工值不动。版本取底稿 1-01 那一行。"""
    await tws._project(db, project_id)
    allowed = {str(r) for r in TABLE_ROWS}
    rows = await tws._rows(db, project_id, year)
    row = rows.get(AMOUNTS_CODE)
    inputs = {sheet: dict(cells) for sheet, cells in ((row.inputs or {}) if row else {}).items()}
    body = inputs.setdefault(BODY_SHEET, {})
    for r in TABLE_ROWS:
        body.pop(f"F{r}", None)
    for key, raw in (values or {}).items():
        if str(key) not in allowed:
            raise HTTPException(status_code=422, detail=f"摘录表没有第 {key} 行")
        v = tws._validate_value(raw)
        if isinstance(v, (bool, str)):
            raise HTTPException(status_code=422, detail="金额只能填数字")
        body[f"F{key}"] = v
    if not body:
        inputs.pop(BODY_SHEET)
    await tws._upsert(db, project_id, year, AMOUNTS_CODE, version, inputs, user_id)


def _valid_date(date: str) -> bool:
    try:
        dt.date.fromisoformat(date)
    except ValueError:
        return False
    return True


# ── Word ──
def template_replacements(data: dict) -> dict[str, str]:
    """模板占位 → 文字（占位由 gen_tax_assurance_templates.py 写进模板）。"""
    out = {
        "{{client}}": data["cover"]["client"],
        "{{year}}": str(data["year"]),
        "{{report_no}}": data["report_no"],
        "{{report_date}}": data["report_date_text"],
    }
    for i, line in enumerate(data["lines"], start=1):
        out[f"{{{{amt_{i}}}}}"] = line["amount_text"]
    return out


def export_docx(data: dict) -> bytes:
    if not TEMPLATE.is_file():
        raise HTTPException(status_code=500, detail="报告正文模板缺失，请运行 gen_tax_assurance_templates.py")
    doc = Document(str(TEMPLATE))
    replace_in_document(doc, template_replacements(data))
    return save_docx(doc)


#: 模板用到的字体（显示名 → PDF 里可接受的字体名）；OnlyOffice 缺任一个，版式就与 Word 不同
PREVIEW_FONTS: dict[str, tuple[str, ...]] = {
    "仿宋": ("FangSong", "仿宋"),
    "黑体": ("SimHei", "黑体"),
    "Arial Narrow": ("ArialNarrow",),
}


async def preview_pdf(data: dict) -> onlyoffice_pdf.PdfResult:
    """网页预览：导出的同一份 Word 交给 OnlyOffice 转 PDF（docx-preview 排不准这份模板的版式）。

    缓存键 = 模板摘要 + 替换内容（金额、日期、报告号或模板变了都会重新转换）。
    🔴 不能用导出的字节做键：python-docx 保存时 zip 条目带当前时间，同一内容每次导出字节都不同。
    """
    replacements = template_replacements(data)
    template_sha = hashlib.sha256(TEMPLATE.read_bytes()).hexdigest() if TEMPLATE.is_file() else ""
    key = f"report-body:{template_sha}:{json.dumps(replacements, ensure_ascii=False, sort_keys=True)}"
    return await onlyoffice_pdf.docx_to_pdf(export_docx(data), key, "报告正文.docx", PREVIEW_FONTS)
