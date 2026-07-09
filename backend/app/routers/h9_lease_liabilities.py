"""H9 租赁负债 — 导入导出三级端点 + 摊销表生成API

4个端点：
- GET  /api/h9-lease-liabilities/{wp_id}/export-template  空白模板xlsx
- GET  /api/h9-lease-liabilities/{wp_id}/export-data      数据xlsx
- POST /api/h9-lease-liabilities/{wp_id}/import-data      解析xlsx写入
- POST /api/h9-lease-liabilities/{wp_id}/generate-amortization  摊销表生成（实际利率法）

支持sheets: H9-2/H9-3/H9-4
科目编码: 2205租赁负债（贷方/负债类）+ 未确认融资费用（借方/负债备抵类）
RFC5987 Content-Disposition header with Chinese filename encoding

Requirements: 3.6, 4.7
"""

from __future__ import annotations

import io
import json
import logging
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/h9-lease-liabilities", tags=["h9-lease-liabilities"])

# ═══════════════════════════════════════════════════════════════════════════════
# Sheet 配置
# ═══════════════════════════════════════════════════════════════════════════════

_ROW_LIMIT = 500

_SUPPORTED_SHEETS: set[str] = {"H9-2", "H9-3", "H9-4"}

_SHEET_HEADERS: dict[str, list[str]] = {
    "H9-2": [
        "合同号", "出租方", "承租资产", "租赁期起", "租赁期止",
        "年租金", "利率(IBR)", "初始确认金额", "期初余额",
        "本期偿还", "本期利息", "期末余额", "备注",
    ],
    "H9-3": [
        "合同号", "出租方", "初始融资费用", "本期确认",
        "累计确认", "未确认余额", "备注",
    ],
    "H9-4": [
        "调整编号", "调整日期", "摘要", "科目编码", "科目名称",
        "借方金额", "贷方金额", "调整类型", "关联底稿", "备注",
    ],
}

# 中文列名 → JSON 字段名 映射表
_FIELD_MAPS: dict[str, dict[str, str]] = {
    "H9-2": {
        "合同号": "contractNo",
        "出租方": "lessor",
        "承租资产": "leasedAsset",
        "租赁期起": "leaseStart",
        "租赁期止": "leaseEnd",
        "年租金": "annualRent",
        "利率(IBR)": "ibrRate",
        "初始确认金额": "initialRecognition",
        "期初余额": "openingBalance",
        "本期偿还": "currentRepayment",
        "本期利息": "currentInterest",
        "期末余额": "endingBalance",
        "备注": "remark",
    },
    "H9-3": {
        "合同号": "contractNo",
        "出租方": "lessor",
        "初始融资费用": "initialFinanceCost",
        "本期确认": "currentRecognized",
        "累计确认": "cumulativeRecognized",
        "未确认余额": "unrecognizedBalance",
        "备注": "remark",
    },
    "H9-4": {
        "调整编号": "adjustNo",
        "调整日期": "adjustDate",
        "摘要": "summary",
        "科目编码": "accountCode",
        "科目名称": "accountName",
        "借方金额": "debitAmount",
        "贷方金额": "creditAmount",
        "调整类型": "adjustType",
        "关联底稿": "relatedWp",
        "备注": "remark",
    },
}

# 各sheet中应解析为数值的字段
_NUMERIC_FIELDS: dict[str, set[str]] = {
    "H9-2": {
        "annualRent", "ibrRate", "initialRecognition",
        "openingBalance", "currentRepayment", "currentInterest", "endingBalance",
    },
    "H9-3": {
        "initialFinanceCost", "currentRecognized",
        "cumulativeRecognized", "unrecognizedBalance",
    },
    "H9-4": {"debitAmount", "creditAmount"},
}

# checklist_responses item_id 映射
_SHEET_ITEM_ID: dict[str, str] = {
    "H9-2": "H9-detail-rows",
    "H9-3": "H9-finance-cost-rows",
    "H9-4": "H9-adjustment-rows",
}


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic 模型
# ═══════════════════════════════════════════════════════════════════════════════


class AmortizationRequest(BaseModel):
    """摊销表生成请求"""
    initial_balance: float = Field(..., gt=0, description="初始余额（租赁负债初始确认金额）")
    payment: float = Field(..., gt=0, description="每期付款金额")
    rate: float = Field(..., ge=0, lt=1, description="每期利率（非年化，如月利率=年利率/12）")
    periods: int = Field(..., gt=0, le=360, description="总期数")


class AmortizationRow(BaseModel):
    """摊销表单行"""
    period: int
    begin_balance: float
    payment: float
    interest: float
    principal: float
    end_balance: float


class AmortizationResponse(BaseModel):
    """摊销表生成响应"""
    schedule: list[AmortizationRow]
    validation: dict


# ═══════════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════════


def _validate_sheet(sheet_code: str) -> None:
    if sheet_code not in _SUPPORTED_SHEETS:
        raise HTTPException(
            400,
            f"不支持的sheet: {sheet_code}。支持: {sorted(_SUPPORTED_SHEETS)}",
        )


def _safe_float(val: Any) -> float:
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _safe_str(val: Any) -> str:
    if val is None:
        return ""
    return str(val).strip()


def _create_template_wb(sheet_code: str) -> Workbook:
    """创建空白模板xlsx（含表头+格式，无数据行）"""
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
        ws.column_dimensions[cell.column_letter].width = max(len(col_name) * 2 + 4, 12)

    ws.freeze_panes = "A2"
    return wb


def _validate_columns(ws: Any, sheet_code: str) -> list[str]:
    """校验列头，返回不匹配的列名列表"""
    expected = set(_SHEET_HEADERS[sheet_code])
    actual: list[str] = []
    for cell in next(ws.iter_rows(min_row=1, max_row=1)):
        if cell.value is not None:
            actual.append(str(cell.value).strip())

    missing = [h for h in expected if h not in actual]
    return missing


def _get_actual_headers(ws: Any) -> list[str]:
    """获取worksheet实际列头"""
    headers: list[str] = []
    for cell in next(ws.iter_rows(min_row=1, max_row=1)):
        if cell.value is not None:
            headers.append(str(cell.value).strip())
    return headers


def _col_val(row: tuple, actual_headers: list[str], col_name: str) -> Any:
    """从行数据中按列名取值"""
    try:
        idx = actual_headers.index(col_name)
        return row[idx] if idx < len(row) else None
    except (ValueError, IndexError):
        return None


def _export_row(sheet_code: str, data: dict) -> list:
    """通用导出行转换——根据sheet_code按列头顺序提取字段"""
    headers = _SHEET_HEADERS[sheet_code]
    field_map = _FIELD_MAPS.get(sheet_code, {})
    result = []
    for col_name in headers:
        field = field_map.get(col_name, col_name)
        val = data.get(field, "")
        result.append(val if val is not None else "")
    return result


def _parse_row(sheet_code: str, row: tuple, actual_headers: list[str]) -> dict:
    """通用导入行解析——根据sheet_code按列名映射回JSON字段"""
    field_map = _FIELD_MAPS.get(sheet_code, {})
    result: dict[str, Any] = {"rowId": str(uuid4())}
    for col_name, field_name in field_map.items():
        raw = _col_val(row, actual_headers, col_name)
        if field_name in _NUMERIC_FIELDS.get(sheet_code, set()):
            result[field_name] = _safe_float(raw)
        else:
            result[field_name] = _safe_str(raw)
    return result


def _generate_amortization_schedule(
    initial_balance: float,
    payment: float,
    rate: float,
    periods: int,
) -> list[dict]:
    """生成实际利率法摊销表

    核心逻辑：
    - 每期利息 = 期初余额 × 利率
    - 本金偿还 = 每期付款 - 利息
    - 期末余额 = 期初 - 本金偿还
    - 最后一期调整尾差确保期末=0
    """
    schedule: list[dict] = []
    balance = initial_balance

    for period in range(1, periods + 1):
        interest = round(balance * rate, 2)

        if period == periods:
            # 最后一期：调整尾差，确保期末余额=0
            principal = balance
            actual_payment = principal + interest
            end_balance = 0.0
        else:
            principal = round(payment - interest, 2)
            end_balance = round(balance - principal, 2)
            actual_payment = payment

        schedule.append({
            "period": period,
            "begin_balance": round(balance, 2),
            "payment": round(actual_payment, 2),
            "interest": interest,
            "principal": round(principal, 2),
            "end_balance": end_balance,
        })

        balance = end_balance

    return schedule


# ═══════════════════════════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/{wp_id}/export-template")
async def h9_export_template(
    wp_id: str,
    sheet: str = Query(..., description="Sheet编码: H9-2/H9-3/H9-4"),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出空白xlsx模板（含表头+格式，无数据行）

    Requirements: 3.6
    """
    _validate_sheet(sheet)

    wb = _create_template_wb(sheet)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"H9租赁负债_{sheet}_模板.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.get("/{wp_id}/export-data")
async def h9_export_data(
    wp_id: str,
    sheet: str = Query(..., description="Sheet编码: H9-2/H9-3/H9-4"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出含当前数据的xlsx

    Requirements: 3.6
    """
    _validate_sheet(sheet)
    import sqlalchemy as sa

    item_id = _SHEET_ITEM_ID[sheet]
    rows_data: list[dict] = []

    result = await db.execute(
        sa.text(
            "SELECT remark FROM checklist_responses "
            "WHERE wp_id = :wp_id AND item_id = :item_id LIMIT 1"
        ),
        {"wp_id": wp_id, "item_id": item_id},
    )
    row = result.fetchone()
    if row and row.remark:
        try:
            rows_data = json.loads(row.remark)
        except (json.JSONDecodeError, TypeError):
            pass

    # 生成 xlsx
    wb = _create_template_wb(sheet)
    ws = wb.active

    for data_row in rows_data:
        ws.append(_export_row(sheet, data_row))

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"H9租赁负债_{sheet}_数据.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.post("/{wp_id}/import-data")
async def h9_import_data(
    wp_id: str,
    sheet: str = Query(..., description="Sheet编码: H9-2/H9-3/H9-4"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """导入xlsx解析写入checklist_responses

    Requirements: 3.6
    """
    _validate_sheet(sheet)
    import sqlalchemy as sa

    # 读取上传文件
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "文件大小超过 10MB 限制")

    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception:
        raise HTTPException(400, "无法解析xlsx文件")

    ws = wb.active

    # 校验列头
    missing = _validate_columns(ws, sheet)
    if missing:
        raise HTTPException(400, f"列名不匹配，缺少: {missing}")

    actual_headers = _get_actual_headers(ws)

    # 解析数据行
    parsed_rows: list[dict] = []
    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if row_idx > _ROW_LIMIT + 1:
            break
        # 跳过全空行
        if all(cell is None or str(cell).strip() == "" for cell in row):
            continue
        parsed_rows.append(_parse_row(sheet, row, actual_headers))

    # 写入 checklist_responses
    item_id = _SHEET_ITEM_ID[sheet]
    json_str = json.dumps(parsed_rows, ensure_ascii=False)

    await db.execute(
        sa.text(
            "INSERT INTO checklist_responses (id, wp_id, item_id, remark) "
            "VALUES (:id, :wp_id, :item_id, :remark) "
            "ON CONFLICT (wp_id, item_id) DO UPDATE SET remark = :remark"
        ),
        {
            "id": str(uuid4()),
            "wp_id": wp_id,
            "item_id": item_id,
            "remark": json_str,
        },
    )
    await db.commit()

    return {"row_count": len(parsed_rows), "sheet": sheet}


@router.post("/{wp_id}/generate-amortization")
async def h9_generate_amortization(
    wp_id: str,
    body: AmortizationRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    """生成租赁负债摊销表（实际利率法）

    核心CAS21计算：
    - 每期利息 = 期初余额 × 实际利率
    - 本金偿还 = 每期付款 - 利息费用
    - 期末余额 = 期初余额 - 本金偿还
    - 最后一期调整尾差确保期末余额=0

    Requirements: 4.7
    """
    schedule = _generate_amortization_schedule(
        initial_balance=body.initial_balance,
        payment=body.payment,
        rate=body.rate,
        periods=body.periods,
    )

    # 验证：最后一期期末余额应≈0
    tail_diff = abs(schedule[-1]["end_balance"]) if schedule else 0.0
    is_valid = tail_diff < 1.0  # 允许±1元尾差

    return {
        "schedule": schedule,
        "validation": {
            "is_valid": is_valid,
            "tail_diff": tail_diff,
            "total_interest": round(sum(row["interest"] for row in schedule), 2),
            "total_principal": round(sum(row["principal"] for row in schedule), 2),
        },
    }
