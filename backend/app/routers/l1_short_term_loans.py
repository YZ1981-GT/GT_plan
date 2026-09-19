"""L1 短期借款 — 导入导出三级端点 + 利息测算API

3个导入导出端点：
- GET  /api/workpapers/{wp_id}/l1/export-template?sheet={sheet_code}  空白模板xlsx
- GET  /api/workpapers/{wp_id}/l1/export-data?sheet={sheet_code}      数据xlsx
- POST /api/workpapers/{wp_id}/l1/import-data?sheet={sheet_code}      解析xlsx写入

支持sheets: L1-2/L1-4/L1-5/L1-6/L1-7/L1-8
科目编码: 2001短期借款（贷方/负债类）
RFC5987 Content-Disposition header with Chinese filename encoding

Requirements: 4.1, 11.2
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
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["l1-short-term-loans"])

# ═══════════════════════════════════════════════════════════════════════════════
# Sheet 配置
# ═══════════════════════════════════════════════════════════════════════════════

_ROW_LIMIT = 500

_SUPPORTED_SHEETS: set[str] = {
    "L1-2", "L1-4", "L1-5", "L1-6", "L1-7", "L1-8",
}

_SHEET_HEADERS: dict[str, list[str]] = {
    "L1-2": [
        "借款银行", "借款合同号", "借款类型", "起始日", "到期日",
        "年利率", "币种", "期初余额", "本期借入", "本期归还",
        "期末余额", "担保方式", "担保物", "备注",
    ],
    "L1-4": [
        "授信银行", "授信额度", "已用额度", "征信借款余额",
        "账面借款余额", "差异", "差异说明", "核对日期", "备注",
    ],
    "L1-5": [
        "借款合同号", "借款银行", "本金", "年利率",
        "计息起始日", "计息终止日", "计息天数",
        "测算利息", "账载利息", "差异", "备注",
    ],
    "L1-6": [
        "借款合同号", "借款银行", "借款金额", "借款日期", "到期日",
        "年利率", "还款方式", "担保方式", "担保物描述",
        "担保物权属", "担保金额", "违约条款", "备注",
    ],
    "L1-7": [
        "借款合同号", "借款银行", "借款金额", "到期日",
        "报告日", "逾期天数", "逾期金额", "是否展期",
        "展期到期日", "风险评价", "备注",
    ],
    "L1-8": [
        "抵质押资产名称", "资产类型", "账面价值", "评估价值",
        "担保借款金额", "担保比例", "权属证明", "是否受限",
        "登记日期", "备注",
    ],
}

# 中文列名 → JSON 字段名 映射表
_FIELD_MAPS: dict[str, dict[str, str]] = {
    "L1-2": {
        "借款银行": "bankName", "借款合同号": "contractNo",
        "借款类型": "loanType", "起始日": "startDate",
        "到期日": "dueDate", "年利率": "annualRate",
        "币种": "currency", "期初余额": "openingBalance",
        "本期借入": "borrowed", "本期归还": "repaid",
        "期末余额": "endingBalance", "担保方式": "guaranteeType",
        "担保物": "collateral", "备注": "remark",
    },
    "L1-4": {
        "授信银行": "bankName", "授信额度": "creditLimit",
        "已用额度": "usedCredit", "征信借款余额": "creditBalance",
        "账面借款余额": "bookBalance", "差异": "difference",
        "差异说明": "explanation", "核对日期": "checkDate",
        "备注": "remark",
    },
    "L1-5": {
        "借款合同号": "contractNo", "借款银行": "bankName",
        "本金": "principal", "年利率": "annualRate",
        "计息起始日": "interestStartDate", "计息终止日": "interestEndDate",
        "计息天数": "days", "测算利息": "calculatedInterest",
        "账载利息": "bookedInterest", "差异": "difference",
        "备注": "remark",
    },
    "L1-6": {
        "借款合同号": "contractNo", "借款银行": "bankName",
        "借款金额": "loanAmount", "借款日期": "loanDate",
        "到期日": "dueDate", "年利率": "annualRate",
        "还款方式": "repaymentMethod", "担保方式": "guaranteeType",
        "担保物描述": "collateralDesc", "担保物权属": "collateralOwnership",
        "担保金额": "guaranteeAmount", "违约条款": "defaultClause",
        "备注": "remark",
    },
    "L1-7": {
        "借款合同号": "contractNo", "借款银行": "bankName",
        "借款金额": "loanAmount", "到期日": "dueDate",
        "报告日": "reportDate", "逾期天数": "overdueDays",
        "逾期金额": "overdueAmount", "是否展期": "isExtended",
        "展期到期日": "extendedDueDate", "风险评价": "riskAssessment",
        "备注": "remark",
    },
    "L1-8": {
        "抵质押资产名称": "assetName", "资产类型": "assetType",
        "账面价值": "bookValue", "评估价值": "appraisalValue",
        "担保借款金额": "guaranteedLoan", "担保比例": "pledgeRatio",
        "权属证明": "ownershipProof", "是否受限": "isRestricted",
        "登记日期": "registrationDate", "备注": "remark",
    },
}

# 各sheet中应解析为数值的字段
_NUMERIC_FIELDS: dict[str, set[str]] = {
    "L1-2": {"openingBalance", "borrowed", "repaid", "endingBalance", "annualRate"},
    "L1-4": {"creditLimit", "usedCredit", "creditBalance", "bookBalance", "difference"},
    "L1-5": {"principal", "annualRate", "days", "calculatedInterest", "bookedInterest", "difference"},
    "L1-6": {"loanAmount", "annualRate", "guaranteeAmount"},
    "L1-7": {"loanAmount", "overdueDays", "overdueAmount"},
    "L1-8": {"bookValue", "appraisalValue", "guaranteedLoan", "pledgeRatio"},
}

# checklist_responses item_id 映射
_SHEET_ITEM_ID: dict[str, str] = {
    "L1-2": "L1-detail-rows",
    "L1-4": "L1-credit-check-rows",
    "L1-5": "L1-interest-calc-rows",
    "L1-6": "L1-contract-check-rows",
    "L1-7": "L1-overdue-check-rows",
    "L1-8": "L1-pledge-check-rows",
}


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


# ═══════════════════════════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/api/workpapers/{wp_id}/l1/export-template")
async def l1_export_template(
    wp_id: str,
    sheet: str = Query(..., description="Sheet编码: L1-2/L1-4/L1-5/L1-6/L1-7/L1-8"),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出空白xlsx模板（含表头+格式，无数据行）

    Requirements: 11.2
    """
    _validate_sheet(sheet)

    wb = _create_template_wb(sheet)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"L1短期借款_{sheet}_模板.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.get("/api/workpapers/{wp_id}/l1/export-data")
async def l1_export_data(
    wp_id: str,
    sheet: str = Query(..., description="Sheet编码: L1-2/L1-4/L1-5/L1-6/L1-7/L1-8"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出含当前数据的xlsx

    Requirements: 11.2
    """
    _validate_sheet(sheet)
    import sqlalchemy as sa  # noqa: F811 — re-import within function for clarity

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

    filename = f"L1短期借款_{sheet}_数据.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.post("/api/workpapers/{wp_id}/l1/import-data")
async def l1_import_data(
    wp_id: str,
    sheet: str = Query(..., description="Sheet编码: L1-2/L1-4/L1-5/L1-6/L1-7/L1-8"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """导入xlsx解析写入checklist_responses

    Requirements: 11.2
    """
    _validate_sheet(sheet)
    import sqlalchemy as sa  # noqa: F811

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
