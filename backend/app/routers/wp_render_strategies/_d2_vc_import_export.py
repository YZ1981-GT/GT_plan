"""D2-7 凭证检查表（双区）导入导出 —— 工作表名与表头常量。

Spec: .kiro/specs/d2-voucher-check-import-export-endpoints/（design §1-01、§2）

D2-7「导入导出▾」的三个端点（``vc-export-template`` / ``vc-export-data`` /
``vc-import-data``，路径前缀 ``/api/workpapers/{wp_id}/d2/``）由本模块提供。导入端点只解析 xlsx，
将双区二维数组交还前端合并并经宿主严格 CAS 保存，绝不在本模块直接写入 checklist。

常量必须与前端 ``audit-platform/frontend/src/components/workpaper/composables/useD2VcImportExport.ts``
同值、同顺序：

- ``SHEET_CURRENT`` ↔ ``SHEET_NAME_CURRENT``（本期增减变动检查区）
- ``SHEET_POST`` ↔ ``SHEET_NAME_POST``（期后收款调整检查区）
- ``COLUMN_HEADERS`` ↔ ``COLUMN_HEADERS``（17 列，顺序即导出顺序）

前端导入时按工作表名找区、按表头认列（``HEADER_TO_FIELD_MAP``），导出的表名表头由后端写，两边差一个字
就会让导入「未找到工作表」或整列被跳过。**改任一侧必须在同一次提交里改另一侧。**

守卫 = ``backend/tests/test_d2_vc_import_export_constants.py``（design §2）：用 ``ast`` 读本模块的模块级
常量、用 TS 字面量分词器读 ``useD2VcImportExport.ts`` 的 ``SHEET_NAME_CURRENT`` / ``SHEET_NAME_POST`` /
``COLUMN_HEADERS``，两侧**按顺序**逐值对拍（任一侧改名、改顺序即红），并断言两侧表头恰 17 项、
``HEADER_TO_FIELD_MAP`` 键集合与表头集合相等（防「两边都解析成空、差集恒空而恒绿」）。
下面三个常量因此必须保持为**纯字面量**：改成动态表达式（拼接、f-string 等）会让静态对拍失效，
``test_backend_constants_are_plain_literals`` 会打红。
"""

from __future__ import annotations

import io
from datetime import date, datetime
from typing import Annotated, TypeAlias
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.worksheet import Worksheet
from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.routers._wp_gate import enforce_wp_gate

SHEET_CURRENT: str = "本期增减变动检查"
SHEET_POST: str = "期后收款调整检查"

#: 17 列表头（顺序为标准导出顺序）；tuple 防止被就地改写。
COLUMN_HEADERS: tuple[str, ...] = (
    "客户名称",
    "日期",
    "凭证编号",
    "业务内容",
    "对方科目",
    "对方明细科目",
    "借方金额",
    "贷方金额",
    "支持性文件",
    "核对内容1",
    "核对内容2",
    "核对内容3",
    "核对内容4",
    "核对内容5",
    "索引号",
    "是否异常",
    "备注说明",
)


XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_EXPORT_ROWS = 2_000
MAX_EXPORT_COLUMNS = 17
MAX_IMPORT_FILE_BYTES = 10 * 1024 * 1024
MAX_IMPORT_ROWS = 5_000
_DANGEROUS_FORMULA_PREFIXES = ("=", "+", "-", "@")
_RECOGNIZED_IMPORT_SHEETS = (SHEET_CURRENT, SHEET_POST)

router = APIRouter(prefix="/api/workpapers", tags=["D2凭证检查表导入导出"])

CellValue: TypeAlias = StrictStr | StrictInt | StrictFloat | None
SheetRow: TypeAlias = Annotated[
    list[CellValue],
    Field(max_length=MAX_EXPORT_COLUMNS),
]


class VoucherCheckExportDataRequest(BaseModel):
    """D2-7 双区导出载荷，保留前端当前表格（包括尚未保存的编辑）。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    currentRows: Annotated[list[SheetRow], Field(max_length=MAX_EXPORT_ROWS)]
    postRows: Annotated[list[SheetRow], Field(max_length=MAX_EXPORT_ROWS)]


__all__ = [
    "COLUMN_HEADERS",
    "MAX_EXPORT_COLUMNS",
    "MAX_EXPORT_ROWS",
    "MAX_IMPORT_FILE_BYTES",
    "MAX_IMPORT_ROWS",
    "SHEET_CURRENT",
    "SHEET_POST",
    "VoucherCheckExportDataRequest",
    "router",
]


# ---------------------------------------------------------------------------
# Workbook construction
# ---------------------------------------------------------------------------


def _new_workbook() -> tuple[Workbook, Worksheet, Worksheet]:
    """创建仅含本期和期后两个数据工作表的工作簿。"""
    workbook = Workbook()
    current_sheet = workbook.active
    current_sheet.title = SHEET_CURRENT
    post_sheet = workbook.create_sheet(SHEET_POST)
    return workbook, current_sheet, post_sheet


def _write_template_header(sheet: Worksheet) -> None:
    """写入标准 17 列表头及可读的模板格式。"""
    header_font = Font(bold=True)
    header_fill = PatternFill("solid", fgColor="D9EAF7")
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for column_index, header in enumerate(COLUMN_HEADERS, start=1):
        cell = sheet.cell(row=1, column=column_index, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        sheet.column_dimensions[cell.column_letter].width = max(14, len(header) * 2 + 2)

    sheet.freeze_panes = "A2"


def _write_cell(sheet: Worksheet, row_index: int, column_index: int, value: CellValue) -> None:
    """写入一个单元格，并将公式形态的文本明确存为字符串。"""
    cell = sheet.cell(row=row_index, column=column_index)
    cell.value = value
    if isinstance(value, str) and value.startswith(_DANGEROUS_FORMULA_PREFIXES):
        # openpyxl 对 '=' 前缀默认视为公式；明确指定字符串可同时覆盖四种 Excel 公式前缀。
        cell.data_type = "s"


def _write_rows(sheet: Worksheet, rows: list[SheetRow]) -> None:
    """按请求数组的行列顺序写入，不补值、不重排。"""
    for row_index, row in enumerate(rows, start=1):
        for column_index, value in enumerate(row, start=1):
            _write_cell(sheet, row_index, column_index, value)


def _serialize_and_close(workbook: Workbook) -> bytes:
    """将工作簿序列化后立即关闭，避免请求结束后遗留 ZipFile 资源。"""
    try:
        with io.BytesIO() as stream:
            workbook.save(stream)
            return stream.getvalue()
    finally:
        workbook.close()


def _content_disposition(filename: str) -> str:
    """返回带 ASCII 回退名的 RFC 5987 中文下载文件名。"""
    return (
        'attachment; filename="D2-7_voucher_check.xlsx"; '
        f"filename*=UTF-8''{quote(filename, safe='')}"
    )


def _xlsx_response(workbook: Workbook, filename: str) -> StreamingResponse:
    """将已完成的工作簿作为 xlsx 下载响应返回。"""
    content = _serialize_and_close(workbook)
    return StreamingResponse(
        iter((content,)),
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": _content_disposition(filename)},
    )


async def _enforce_checklist_read_gate(
    db: AsyncSession,
    current_user: User,
    wp_id: UUID,
    route_name: str,
) -> None:
    """在生成任意工作簿前执行与 checklist GET 相同的底稿读门。"""
    await enforce_wp_gate(
        db,
        current_user,
        entrypoint="workpaper.checklist_read",
        action="read_checklist",
        method="GET",
        wp_id=wp_id,
        entry_family="checklist",
        route_name=route_name,
    )


async def _enforce_checklist_write_gate(
    db: AsyncSession,
    current_user: User,
    wp_id: UUID,
    route_name: str,
) -> None:
    """在读取上传内容前执行与 checklist 保存相同的底稿写门。"""
    await enforce_wp_gate(
        db,
        current_user,
        entrypoint="workpaper.checklist_save",
        action="save_checklist",
        method="PUT",
        wp_id=wp_id,
        entry_family="checklist",
        route_name=route_name,
    )


def _import_cell_value(value: object) -> str | int | float | None:
    """转换单元格为前端可直接反序列化的 JSON 标量。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return int(value) if value.is_integer() else value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return str(value)


def _import_row_values(values: tuple[object, ...]) -> list[str | int | float | None]:
    """转换一行并移除行尾空格；全空行保留为空数组供前端跳过。"""
    row = [_import_cell_value(value) for value in values]
    while row and row[-1] is None:
        row.pop()
    return row


def _parse_import_workbook(
    content: bytes,
) -> tuple[dict[str, list[list[str | int | float | None]]], list[str]]:
    """只读取两个精确命名的 D2-7 凭证检查表工作表，不持久化任何数据。"""
    workbook: Workbook | None = None
    try:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        sheets: dict[str, list[list[str | int | float | None]]] = {}
        warnings: list[str] = []

        for sheet_name in _RECOGNIZED_IMPORT_SHEETS:
            if sheet_name not in workbook.sheetnames:
                continue

            rows: list[list[str | int | float | None]] = []
            worksheet = workbook[sheet_name]
            for row_number, values in enumerate(worksheet.iter_rows(values_only=True), start=1):
                if row_number > MAX_IMPORT_ROWS:
                    warnings.append(
                        f"工作表“{sheet_name}”超过 {MAX_IMPORT_ROWS} 行，只读取前 {MAX_IMPORT_ROWS} 行"
                    )
                    break
                rows.append(_import_row_values(values))
            sheets[sheet_name] = rows

        return sheets, warnings
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail="文件无法解析，请确认上传的是未损坏的 .xlsx 文件",
        ) from exc
    finally:
        if workbook is not None:
            workbook.close()


# ---------------------------------------------------------------------------
# Export endpoints (Task 2)
# ---------------------------------------------------------------------------


@router.post("/{wp_id}/d2/vc-export-template")
async def export_voucher_check_template(
    wp_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出 D2-7 凭证检查表空白模板（两个标准工作表）。"""
    await _enforce_checklist_read_gate(
        db,
        current_user,
        wp_id,
        "/api/workpapers/{wp_id}/d2/vc-export-template",
    )

    workbook, current_sheet, post_sheet = _new_workbook()
    try:
        _write_template_header(current_sheet)
        _write_template_header(post_sheet)
    except Exception:
        workbook.close()
        raise
    return _xlsx_response(workbook, "D2-7_凭证检查表模板.xlsx")


@router.post("/{wp_id}/d2/vc-export-data")
async def export_voucher_check_data(
    wp_id: UUID,
    payload: VoucherCheckExportDataRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """按前端当前双区数组导出 D2-7 凭证检查表数据。"""
    await _enforce_checklist_read_gate(
        db,
        current_user,
        wp_id,
        "/api/workpapers/{wp_id}/d2/vc-export-data",
    )

    workbook, current_sheet, post_sheet = _new_workbook()
    try:
        _write_rows(current_sheet, payload.currentRows)
        _write_rows(post_sheet, payload.postRows)
    except Exception:
        workbook.close()
        raise
    return _xlsx_response(workbook, "D2-7_凭证检查表数据.xlsx")


# ---------------------------------------------------------------------------
# Import endpoint (Task 3)
# ---------------------------------------------------------------------------


@router.post("/{wp_id}/d2/vc-import-data")
async def import_voucher_check_data(
    wp_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, object]:
    """解析 D2-7 双区 xlsx 并返回可导入行，不直接写入 checklist。"""
    try:
        # 写门必须先于文件名、大小及内容校验，避免未授权请求借错误差异枚举资源。
        await _enforce_checklist_write_gate(
            db,
            current_user,
            wp_id,
            "/api/workpapers/{wp_id}/d2/vc-import-data",
        )

        filename = file.filename or ""
        if not filename.lower().endswith(".xlsx"):
            raise HTTPException(status_code=400, detail="仅支持 .xlsx 文件")

        content = await file.read(MAX_IMPORT_FILE_BYTES + 1)
        if len(content) > MAX_IMPORT_FILE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"文件大小超过 {MAX_IMPORT_FILE_BYTES // 1024 // 1024}MB 限制",
            )

        sheets, warnings = _parse_import_workbook(content)
        return {"sheets": sheets, "warnings": warnings}
    finally:
        await file.close()
