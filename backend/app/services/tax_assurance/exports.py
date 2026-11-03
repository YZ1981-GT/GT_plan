"""导出：汇算申报表 xlsx（样表裁出的模板填值）、单体财务报表 xlsx（按页面数据排版）。"""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from typing import Any
from uuid import UUID

import openpyxl
from fastapi import HTTPException
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.utils import get_column_letter
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import tax_workpaper_service as tws
from app.services.tax_assurance.common import DATA_DIR, year_text
from app.services.tax_formula_engine import XlError

TAX_RETURN_TEMPLATE = DATA_DIR / "tax_return_template.xlsx"
FORMS_CODE = "TR-FORMS"
FILED_MARK = "√"
UNFILED_MARK = "□"


def _cell_value(v: Any) -> Any:
    if isinstance(v, XlError):
        return str(v)
    if isinstance(v, Decimal):
        return float(v)
    return v


def _forms_index() -> list[dict]:
    """表单页每行：编号、标记格（与前端 taxReturnIndex.json 同源：表单 sheet 的 A / C 列）。"""
    wb = tws.load_workbook()
    sheet = wb.sheets_of(FORMS_CODE)[0]
    tax_return_codes = set(wb.model["groups"]["tax_return"])
    out = []
    for (s, row, col), v in sorted(wb.consts.items()):
        if s == sheet and col == 1 and isinstance(v, str) and v.strip() in tax_return_codes:
            out.append({"code": v.strip(), "mark_key": (sheet, row, 3)})
    return out


async def export_tax_return(db: AsyncSession, project_id: UUID, year: int) -> bytes:
    if not TAX_RETURN_TEMPLATE.is_file():
        raise HTTPException(status_code=500, detail="汇算申报表模板缺失，请运行 gen_tax_assurance_templates.py")
    wb_model = tws.load_workbook()
    codes = wb_model.model["groups"]["tax_return"]
    sheets = [s for c in codes for s in wb_model.sheets_of(c)]
    seeds = [k for s in sheets for k in wb_model.print_keys(s)]
    ev = await tws.evaluate_keys(db, project_id, year, seeds)

    book = openpyxl.load_workbook(TAX_RETURN_TEMPLATE)
    for key in seeds:
        _write(book, key, ev.value(key[0], tws.to_a1(key[1], key[2])), year)
    for key, v in ev.inputs.items():
        if key[0] in sheets and key not in wb_model.formulas:
            _write(book, key, v, year)

    for item in _forms_index():
        mark = ev.inputs.get(item["mark_key"], wb_model.consts.get(item["mark_key"]))
        filed = str(mark or "").strip() == FILED_MARK
        sheet, row, col = item["mark_key"]
        book[sheet].cell(row, col).value = FILED_MARK if filed else UNFILED_MARK
        if item["code"] in book.sheetnames:
            book[item["code"]].sheet_state = "visible" if filed else "hidden"
    book.active = 0
    buf = BytesIO()
    book.save(buf)
    return buf.getvalue()


def _write(book, key, value, year: int) -> None:
    sheet, row, col = key
    if sheet not in book.sheetnames:
        return
    cell = book[sheet].cell(row, col)
    if type(cell).__name__ == "MergedCell":
        return
    v = _cell_value(value)
    cell.value = year_text(v, year) if isinstance(v, str) else v


# ── 单体财务报表 ──
_THIN = Side(style="thin")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


def _amount(v: dict | None) -> float | None:
    if not v or "n" not in v:
        return None
    return float(Decimal(v["n"]))


def export_financial_statements(data: dict) -> bytes:
    book = openpyxl.Workbook()
    book.remove(book.active)
    year = data["year"]
    for stmt in data["statements"]:
        ws = book.create_sheet(stmt["title"][:31].replace("/", "-"))
        width = 2 + len(stmt["columns"])
        row = 1
        if stmt.get("attachment"):
            ws.cell(row, 1, stmt["attachment"])
            row += 1
        ws.cell(row, 1, stmt["title"]).font = Font(bold=True, size=14)
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=width)
        ws.cell(row, 1).alignment = Alignment(horizontal="center")
        row += 1
        period = f"{year}年12月31日" if stmt["columns"][0].startswith("期末") else f"{year}年度"
        ws.cell(row, 1, period).alignment = Alignment(horizontal="center")
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=width)
        row += 1
        ws.cell(row, 1, f"编制单位：{data.get('entity_name') or ''}")
        ws.cell(row, width, "单位：人民币元").alignment = Alignment(horizontal="right")
        row += 1
        header_row = row
        for c, title in enumerate(["项    目", "附注", *stmt["columns"]], start=1):
            cell = ws.cell(row, c, title)
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center")
        row += 1
        for line in stmt["rows"]:
            label = ws.cell(row, 1, "  " * int(line.get("indent") or 0) + line["label"])
            if line.get("total") or line.get("heading"):
                label.font = Font(bold=True)
            for c, key in ((3, "current"), (4, "prior")):
                v = _amount(line.get(key))
                if v is not None:
                    cell = ws.cell(row, c, v)
                    cell.number_format = "#,##0.00"
                    if line.get("total"):
                        cell.font = Font(bold=True)
            row += 1
        for r in range(header_row, row):
            for c in range(1, width + 1):
                ws.cell(r, c).border = _BORDER
        ws.column_dimensions["A"].width = 46
        ws.column_dimensions["B"].width = 8
        for c in range(3, width + 1):
            ws.column_dimensions[get_column_letter(c)].width = 20
    if not book.sheetnames:
        book.create_sheet("单体财务报表")
    buf = BytesIO()
    book.save(buf)
    return buf.getvalue()
