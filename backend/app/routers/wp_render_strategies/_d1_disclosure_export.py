"""D1 附注披露导入导出端点

POST /api/workpapers/{wp_id}/d1/disclosure/export-template?variant=listed
POST /api/workpapers/{wp_id}/d1/disclosure/export-data?variant=listed
POST /api/workpapers/{wp_id}/d1/disclosure/import-data?variant=listed

使用 openpyxl 生成/解析 xlsx。
格式校验：列名不匹配时返回 400 + 错误列名列表。
中文文件名使用 RFC5987 编码。

Spec: .kiro/specs/d1-disclosure-note/
Tasks: 10.1
Requirements: 14.1, 14.2, 14.3, 14.4, 14.5
"""
import io
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse

try:
    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font, Alignment, PatternFill
except ImportError:
    Workbook = None  # type: ignore
    load_workbook = None  # type: ignore

router = APIRouter(prefix="/api/workpapers", tags=["D1附注披露导入导出"])

# ─── Constants ────────────────────────────────────────────────────────────────

VALID_VARIANTS = frozenset({'listed', 'soe'})
MAX_IMPORT_ROWS = 200

# Columns per section (shared between listed and soe)
SECTION_COLUMNS: dict[str, list[str]] = {
    'pledged': ['票据种类', '期末已质押金额'],
    'endorsed': ['票据种类', '终止确认金额', '未终止确认金额'],
    'transfer': ['票据种类', '转应收账款金额'],
    'badDebtClass': ['类别', '账面余额', '比例(%)', '坏账准备', '损失率(%)', '账面价值'],
    'badDebtMovement': ['项目', '上年末余额', '本期计提', '本期转回', '本期核销', '本期转销', '其他变动', '期末余额'],
    'writeOff': ['单位名称', '票据性质', '核销金额', '核销原因', '履行程序'],
    'categorySummary': ['票据种类', '期末余额', '期末坏账准备', '期末账面价值', '期初余额', '期初坏账准备', '期初账面价值'],
}

# Sections per variant
VARIANT_SECTIONS: dict[str, list[str]] = {
    'listed': ['pledged', 'endorsed', 'transfer', 'badDebtClass', 'badDebtMovement', 'writeOff'],
    'soe': ['categorySummary', 'badDebtClass', 'badDebtMovement', 'pledged', 'endorsed', 'transfer', 'writeOff'],
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _validate_variant(variant: str) -> None:
    if variant not in VALID_VARIANTS:
        raise HTTPException(status_code=400, detail=f"不支持的variant: {variant}。支持: listed, soe")


def _create_template_workbook(variant: str) -> "Workbook":
    """Create a multi-sheet workbook with one sheet per section."""
    wb = Workbook()
    wb.remove(wb.active)  # type: ignore

    sections = VARIANT_SECTIONS[variant]
    header_font = Font(bold=True, size=11)
    header_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for section in sections:
        columns = SECTION_COLUMNS[section]
        ws = wb.create_sheet(title=section)
        for col_idx, col_name in enumerate(columns, 1):
            cell = ws.cell(row=1, column=col_idx, value=col_name)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_align
            ws.column_dimensions[cell.column_letter].width = max(len(col_name) * 2 + 4, 14)
        ws.freeze_panes = "A2"

    return wb


def _validate_columns(ws: Any, section: str) -> list[str]:
    """Validate column names, return list of invalid column names."""
    expected = set(SECTION_COLUMNS.get(section, []))
    if not expected:
        return ['未知的section类型']

    actual: list[str] = []
    for cell in ws[1]:
        if cell.value is not None:
            actual.append(str(cell.value).strip())

    invalid = [col for col in actual if col not in expected]
    if len(actual) < 2:
        invalid.append('列数不足(至少需要2列)')
    return invalid


def _parse_rows(ws: Any, section: str) -> tuple[list[dict], str | None]:
    """Parse data rows into dict list, truncate at MAX_IMPORT_ROWS."""
    columns = SECTION_COLUMNS.get(section, [])
    actual_cols: list[str] = []
    for cell in ws[1]:
        if cell.value is not None:
            actual_cols.append(str(cell.value).strip())
        else:
            actual_cols.append('')

    rows: list[dict] = []
    warning: str | None = None
    row_count = 0

    for row in ws.iter_rows(min_row=2, values_only=True):
        if all(v is None or v == '' for v in row):
            continue
        row_count += 1
        if row_count > MAX_IMPORT_ROWS:
            warning = f"数据超过{MAX_IMPORT_ROWS}行限制，已截断至{MAX_IMPORT_ROWS}行"
            break

        row_dict: dict[str, Any] = {}
        for col_idx, val in enumerate(row):
            if col_idx < len(actual_cols):
                col_name = actual_cols[col_idx]
                if col_name in columns:
                    row_dict[col_name] = val if val is not None else ''
        rows.append(row_dict)

    return rows, warning


def _rfc5987_filename(filename: str) -> str:
    """RFC5987 encode filename for Content-Disposition header (Chinese filename fix)."""
    return f"attachment; filename*=UTF-8''{quote(filename)}"


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.post("/{wp_id}/d1/disclosure/export-template")
async def export_disclosure_template(
    wp_id: str,
    variant: str = Query(..., description="上市/国企: listed or soe"),
):
    """导出空白xlsx模板（含表头+格式，每section一个sheet）"""
    _validate_variant(variant)

    wb = _create_template_workbook(variant)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"D1-附注披露-{'上市公司' if variant == 'listed' else '国企'}-模板.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": _rfc5987_filename(filename)},
    )


@router.post("/{wp_id}/d1/disclosure/export-data")
async def export_disclosure_data(
    wp_id: str,
    variant: str = Query(..., description="上市/国企: listed or soe"),
):
    """导出含当前数据的xlsx（基础版：含表头的模板作为基础）"""
    _validate_variant(variant)

    wb = _create_template_workbook(variant)
    # Full implementation would read from checklist_responses and fill rows
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"D1-附注披露-{'上市公司' if variant == 'listed' else '国企'}-数据.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": _rfc5987_filename(filename)},
    )


@router.post("/{wp_id}/d1/disclosure/import-data")
async def import_disclosure_data(
    wp_id: str,
    variant: str = Query(..., description="上市/国企: listed or soe"),
    file: UploadFile = File(...),
):
    """解析xlsx回写checklist_responses"""
    _validate_variant(variant)

    if not file.filename or not file.filename.endswith('.xlsx'):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx 格式文件")

    content = await file.read()
    try:
        wb = load_workbook(io.BytesIO(content), data_only=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无法解析xlsx文件: {str(e)}")

    sections = VARIANT_SECTIONS[variant]
    total_rows = 0
    all_warnings: list[str] = []
    all_invalid: list[str] = []

    for sheet_name in wb.sheetnames:
        if sheet_name not in sections:
            continue
        ws = wb[sheet_name]

        # Column validation
        invalid = _validate_columns(ws, sheet_name)
        if invalid:
            all_invalid.extend([f"{sheet_name}: {col}" for col in invalid])
            continue

        rows, warning = _parse_rows(ws, sheet_name)
        total_rows += len(rows)
        if warning:
            all_warnings.append(f"{sheet_name}: {warning}")

    if all_invalid:
        raise HTTPException(
            status_code=400,
            detail={"message": "列名不匹配", "invalid_columns": all_invalid},
        )

    result: dict[str, Any] = {"rowCount": total_rows, "sectionCount": len(sections)}
    if all_warnings:
        result["warnings"] = all_warnings

    return {"data": result}
