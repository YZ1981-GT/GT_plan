"""N4 税金及附加 — 导入导出三级端点

3个端点（POST，body/form接收wpId+sheet）：
- POST /api/n4/export-template   空白模板xlsx（N4-2明细表）
- POST /api/n4/export-data       当前数据xlsx
- POST /api/n4/import-data       解析xlsx写入checklist_responses（multipart）

科目编码: 6403税金及附加（**损益类**！取本期发生额）
导入导出目标: N4-2明细表（动态行，各税种计税依据×税率）
前端匹配: useN4ImportExport.ts (POST + body/form，非GET+path参数)
RFC5987 Content-Disposition header with Chinese filename encoding

Requirements: 3.4
"""

from __future__ import annotations

import io
import json
import logging
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import sqlalchemy as sa
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/n4",
    tags=["N4 税金及附加"],
)

# ═══════════════════════════════════════════════════════════════════════════════
# Sheet 配置
# ═══════════════════════════════════════════════════════════════════════════════

_ROW_LIMIT = 500

# 支持导入导出的sheet（动态行表格）
_SUPPORTED_SHEETS: set[str] = {"N4-2"}

# N4-2 明细表列头（10列：序号/税种/计税依据/税率/本期税额/上期税额/同比变动/N2计提额/差异/结论）
_SHEET_HEADERS: dict[str, list[str]] = {
    "N4-2": [
        "序号", "税种", "计税依据", "税率",
        "本期税额", "上期税额", "同比变动",
        "N2计提额", "差异", "结论",
    ],
}

# 中文列名 → JSON 字段名映射（对应 N4DetailRow 接口）
_FIELD_MAPS: dict[str, dict[str, str]] = {
    "N4-2": {
        "序号": "seq",
        "税种": "taxType",
        "计税依据": "taxBasis",
        "税率": "taxRate",
        "本期税额": "periodAmount",
        "上期税额": "priorAmount",
        "同比变动": "yoyChange",
        "N2计提额": "n2Accrual",
        "差异": "diff",
        "结论": "conclusion",
    },
}

# 数值类型字段（用于导入时安全转float）
_NUMERIC_FIELDS: dict[str, set[str]] = {
    "N4-2": {
        "seq", "taxBasis", "taxRate", "periodAmount",
        "priorAmount", "yoyChange", "n2Accrual", "diff",
    },
}

# checklist_responses 存储 item_id
_SHEET_ITEM_ID: dict[str, str] = {
    "N4-2": "N4-2-detail-rows",
}


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic 请求模型
# ═══════════════════════════════════════════════════════════════════════════════


class N4ExportRequest(BaseModel):
    """导出请求体"""
    wpId: str = Field(..., description="底稿ID")
    sheet: str = Field("N4-2", description="Sheet编码")


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════


def _validate_sheet(sheet_code: str) -> None:
    """校验sheet编码"""
    if sheet_code not in _SUPPORTED_SHEETS:
        raise HTTPException(
            400,
            f"不支持的sheet: {sheet_code}。支持: {sorted(_SUPPORTED_SHEETS)}",
        )


def _safe_float(val: Any) -> float:
    """安全转float"""
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _safe_str(val: Any) -> str:
    """安全转str"""
    if val is None:
        return ""
    return str(val).strip()


def _create_template_wb(sheet_code: str) -> Workbook:
    """创建空白模板xlsx（含表头+格式+编制说明，无数据行）"""
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_code

    headers = _SHEET_HEADERS[sheet_code]
    header_font = Font(bold=True, size=11)
    header_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for col_idx, col_name in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=col_name)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        ws.column_dimensions[get_column_letter(col_idx)].width = max(len(col_name) * 2 + 4, 12)

    ws.freeze_panes = "A2"

    # 编制说明sheet
    ws_guide = wb.create_sheet("编制说明")
    ws_guide.append(["N4-2 税金及附加明细表 编制说明"])
    ws_guide.append([])
    guidance_lines = [
        "按税种逐项填列本期税金及附加发生情况。",
        "科目6403税金及附加为损益类借方科目：",
        "  - 借方发生=费用确认，贷方发生=冲减/转回",
        "  - 本期税额=计税依据×适用税率",
        "",
        "税种类别：",
        "  - 消费税",
        "  - 城市维护建设税 = (增值税+消费税)×税率(7%/5%/1%)",
        "  - 教育费附加 = (增值税+消费税)×3%",
        "  - 地方教育附加 = (增值税+消费税)×2%",
        "  - 房产税（从价=原值×(1-扣除比例)×1.2%；从租=租金×12%）",
        "  - 城镇土地使用税 = 占地面积×单位税额",
        "  - 车船税（按法定计税方式）",
        "  - 印花税 = 计税金额×适用税率",
        "  - 资源税",
        "  - 其他",
        "",
        "关键核对：",
        "  - 各税种税额须与N2应交税费各税种本期计提额一致",
        "  - 合计行须与审定表N4-1发生额合计一致",
        "  - 差异=本期税额-N2计提额，非零需说明原因",
        "",
        f"最大{_ROW_LIMIT}行，超出截断。",
    ]
    for line in guidance_lines:
        ws_guide.append([line])
    ws_guide.column_dimensions["A"].width = 80

    return wb


def _get_actual_headers(ws: Any) -> list[str]:
    """获取worksheet实际列头"""
    headers: list[str] = []
    for cell in next(ws.iter_rows(min_row=1, max_row=1)):
        if cell.value is not None:
            headers.append(str(cell.value).strip())
    return headers


def _validate_columns(ws: Any, sheet_code: str) -> list[str]:
    """校验列头，返回不匹配的列名列表"""
    expected = set(_SHEET_HEADERS[sheet_code])
    actual = set(_get_actual_headers(ws))
    missing = [h for h in expected if h not in actual]
    return missing


def _export_row(sheet_code: str, data: dict) -> list:
    """将JSON dict按列头顺序转为导出行"""
    headers = _SHEET_HEADERS[sheet_code]
    field_map = _FIELD_MAPS.get(sheet_code, {})
    result = []
    for col_name in headers:
        field = field_map.get(col_name, col_name)
        val = data.get(field, "")
        result.append(val if val is not None else "")
    return result


def _parse_row(sheet_code: str, row: tuple, actual_headers: list[str]) -> dict:
    """将xlsx行数据按列名映射为JSON dict"""
    field_map = _FIELD_MAPS.get(sheet_code, {})
    numeric = _NUMERIC_FIELDS.get(sheet_code, set())
    result: dict[str, Any] = {"rowKey": str(uuid4())}

    for col_name, field_name in field_map.items():
        try:
            idx = actual_headers.index(col_name)
            raw = row[idx] if idx < len(row) else None
        except (ValueError, IndexError):
            raw = None

        if field_name in numeric:
            result[field_name] = _safe_float(raw)
        else:
            result[field_name] = _safe_str(raw)

    # 默认可编辑 + 空备注
    result["isEditable"] = True
    result["remark"] = ""
    return result


async def _load_rows_data(wp_id: str, sheet_code: str, db: AsyncSession) -> list[dict]:
    """从checklist_responses加载动态行数据（JSON打包存储）"""
    item_id = _SHEET_ITEM_ID[sheet_code]
    result = await db.execute(
        sa.text(
            "SELECT conclusion FROM checklist_responses "
            "WHERE wp_id = :wp_id AND item_id = :item_id LIMIT 1"
        ),
        {"wp_id": wp_id, "item_id": item_id},
    )
    row = result.fetchone()
    if row and row.conclusion:
        try:
            parsed = json.loads(row.conclusion)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            pass
    return []


async def _upsert_rows_data(
    wp_id: str, sheet_code: str, rows_data: list[dict], db: AsyncSession
) -> None:
    """写入/更新checklist_responses（JSON打包）"""
    item_id = _SHEET_ITEM_ID[sheet_code]
    payload = json.dumps(rows_data, ensure_ascii=False)

    # 获取 project_id
    proj = await db.execute(
        sa.text(
            "SELECT project_id FROM working_paper WHERE id = :wp_id AND is_deleted = false"
        ),
        {"wp_id": wp_id},
    )
    project_id = proj.scalar_one_or_none()
    if not project_id:
        raise HTTPException(404, f"底稿不存在: {wp_id}")

    await db.execute(
        sa.text("""
            INSERT INTO checklist_responses (id, project_id, wp_id, item_id, conclusion, updated_at, created_at)
            VALUES (:id, :project_id, :wp_id, :item_id, :payload, NOW(), NOW())
            ON CONFLICT (wp_id, item_id)
            DO UPDATE SET conclusion = :payload, updated_at = NOW()
        """),
        {
            "id": str(uuid4()),
            "project_id": str(project_id),
            "wp_id": wp_id,
            "item_id": item_id,
            "payload": payload,
        },
    )
    await db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# 导出模板
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/export-template")
async def n4_export_template(
    body: N4ExportRequest,
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出空白xlsx模板（含表头+格式+编制说明）

    Body:
        wpId: 底稿ID
        sheet: 指定导出sheet（默认N4-2）

    Returns: StreamingResponse (xlsx, RFC5987 encoded Chinese filename)

    Requirements: 3.4
    """
    _validate_sheet(body.sheet)

    wb = _create_template_wb(body.sheet)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"N4税金及附加_{body.sheet}_模板.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 导出数据
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/export-data")
async def n4_export_data(
    body: N4ExportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出含当前数据的xlsx

    Body:
        wpId: 底稿ID
        sheet: 指定导出sheet（默认N4-2）

    Returns: StreamingResponse (xlsx, RFC5987 encoded Chinese filename)

    Requirements: 3.4
    """
    _validate_sheet(body.sheet)

    rows_data = await _load_rows_data(body.wpId, body.sheet, db)

    wb = _create_template_wb(body.sheet)
    ws = wb[body.sheet]

    # 写入数据行（从第2行开始，第1行是表头）
    for row_idx, row_data in enumerate(rows_data, start=2):
        values = _export_row(body.sheet, row_data)
        for col_idx, val in enumerate(values, 1):
            ws.cell(row=row_idx, column=col_idx, value=val)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"N4税金及附加_{body.sheet}_数据.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 导入数据
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/import-data")
async def n4_import_data(
    file: UploadFile = File(...),
    wpId: str = Form(...),
    sheet: str = Form("N4-2"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """导入xlsx解析写入checklist_responses

    Multipart form:
        file: xlsx文件
        wpId: 底稿ID
        sheet: 目标sheet编码（默认N4-2）

    验证：文件扩展名(.xlsx)、列头匹配、行数限制

    Returns:
        { imported_count: int, message: str, warning?: str }

    Requirements: 3.4
    """
    _validate_sheet(sheet)

    # 文件扩展名校验
    filename = file.filename or ""
    if not filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "不支持的文件类型，仅支持 .xlsx/.xls")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "文件大小不能超过10MB")

    try:
        wb = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    except Exception:
        raise HTTPException(400, "无法解析xlsx文件，请检查文件格式")

    ws = wb.active
    if ws is None:
        wb.close()
        raise HTTPException(400, "xlsx文件中无活动工作表")

    actual_headers = _get_actual_headers(ws)
    missing = _validate_columns(ws, sheet)
    if missing:
        wb.close()
        raise HTTPException(400, f"列头不匹配，缺少: {missing}")

    # 解析数据行
    all_rows: list[dict] = []
    warning: str | None = None

    for row_data in ws.iter_rows(min_row=2, values_only=True):
        # 跳过全空行
        if not any(cell is not None and str(cell).strip() for cell in row_data):
            continue
        parsed = _parse_row(sheet, row_data, actual_headers)
        all_rows.append(parsed)
        if len(all_rows) >= _ROW_LIMIT:
            warning = f"数据行数超过{_ROW_LIMIT}行限制，已截断"
            break

    wb.close()

    if not all_rows:
        raise HTTPException(400, "未从文件中解析到有效数据行")

    # 写入 checklist_responses
    await _upsert_rows_data(wpId, sheet, all_rows, db)

    result: dict[str, Any] = {
        "imported_count": len(all_rows),
        "message": f"成功导入 {len(all_rows)} 行到 {sheet}",
    }
    if warning:
        result["warning"] = warning

    return result
