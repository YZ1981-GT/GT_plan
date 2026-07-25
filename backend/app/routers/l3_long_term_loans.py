"""L3 长期借款 — 导入导出三级端点 + 利息测算API + 一年内到期重分类API

5个端点：
- GET  /api/workpapers/{wp_id}/l3/export-template?sheet={sheet_code}  空白模板xlsx
- GET  /api/workpapers/{wp_id}/l3/export-data?sheet={sheet_code}      数据xlsx
- POST /api/workpapers/{wp_id}/l3/import-data?sheet={sheet_code}      解析xlsx写入
- POST /api/workpapers/{wp_id}/l3/calculate-interest                  利息测算API
- POST /api/workpapers/{wp_id}/l3/reclass-current-portion             一年内到期重分类API

支持sheets: L3-2/L3-4/L3-5/L3-6/L3-7/L3-8
科目编码: 2501长期借款（贷方/负债类）
RFC5987 Content-Disposition header with Chinese filename encoding

Requirements: 4.1, 5.2, 11.3
"""

from __future__ import annotations

import io
import json
import logging
from datetime import date, datetime
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workpapers/{wp_id}/l3", tags=["L3 长期借款"])

# ═══════════════════════════════════════════════════════════════════════════════
# Sheet 配置
# ═══════════════════════════════════════════════════════════════════════════════

_ROW_LIMIT = 500

_SUPPORTED_SHEETS: set[str] = {
    "L3-2", "L3-4", "L3-5", "L3-6", "L3-7", "L3-8",
}

_SHEET_HEADERS: dict[str, list[str]] = {
    "L3-2": [
        "借款银行", "借款合同号", "借款类型", "起始日", "到期日",
        "年利率", "币种", "期初余额", "本期借入", "本期归还",
        "期末余额", "一年内到期金额", "担保方式", "担保物", "担保价值", "用途", "备注",
    ],
    "L3-4": [
        "授信银行", "授信额度", "已用额度", "征信借款余额",
        "账面借款余额", "差异", "差异说明", "核对日期", "备注",
    ],
    "L3-5": [
        "借款合同号", "借款银行", "本金", "年利率",
        "计息起始日", "计息终止日", "账载利息", "备注",
    ],
    "L3-6": [
        "借款合同号", "借款单位", "贷款银行", "借款金额", "起始日期", "到期日期",
        "借款期限(月)", "币种", "利率类型", "年利率", "调整方式", "计息基础",
        "还款计划", "担保方式", "保证人", "抵质押物", "担保金额",
        "提前还款条件", "逾期罚则", "交叉违约", "财务承诺",
    ],
    "L3-7": [
        "借款合同号", "借款银行", "借款金额", "到期日",
        "报告日", "逾期天数", "逾期金额", "是否展期",
        "展期到期日", "风险评价", "备注",
    ],
    "L3-8": [
        "抵质押资产名称", "资产类型", "账面价值", "评估价值",
        "担保借款金额", "担保比例", "权属证明", "是否受限",
        "登记日期", "备注",
    ],
}

# 中文列名 → JSON 字段名 映射表
_FIELD_MAPS: dict[str, dict[str, str]] = {
    "L3-2": {
        "借款银行": "bank", "借款合同号": "contractNo",
        "借款类型": "loanType", "起始日": "startDate",
        "到期日": "dueDate", "年利率": "annualRate",
        "币种": "currency", "期初余额": "beginning",
        "本期借入": "borrowed", "本期归还": "repaid",
        "期末余额": "endBalance", "一年内到期金额": "currentPortion",
        "担保方式": "guaranteeType", "担保物": "pledgeAsset",
        "担保价值": "pledgeValue", "用途": "purpose",
        "备注": "remark",
    },
    "L3-4": {
        "授信银行": "bankName", "授信额度": "creditLimit",
        "已用额度": "usedCredit", "征信借款余额": "creditBalance",
        "账面借款余额": "bookBalance", "差异": "difference",
        "差异说明": "explanation", "核对日期": "checkDate",
        "备注": "remark",
    },
    "L3-5": {
        "借款合同号": "contractNo", "借款银行": "bank",
        "本金": "principal", "年利率": "annualRate",
        "计息起始日": "loanStart", "计息终止日": "loanEnd",
        "账载利息": "bookedInterest", "备注": "remark",
    },
    "L3-6": {
        "借款合同号": "contractNo", "借款单位": "borrower",
        "贷款银行": "lender", "借款金额": "loanAmount",
        "起始日期": "startDate", "到期日期": "endDate",
        "借款期限(月)": "term", "币种": "currency",
        "利率类型": "rateType", "年利率": "annualRate",
        "调整方式": "adjustMethod", "计息基础": "interestBasis",
        "还款计划": "repaymentPlan", "担保方式": "guaranteeType",
        "保证人": "guarantor", "抵质押物": "pledgeAsset",
        "担保金额": "guaranteeAmount", "提前还款条件": "prepaymentCondition",
        "逾期罚则": "overduePenalty", "交叉违约": "crossDefault",
        "财务承诺": "financialCovenant",
    },
    "L3-7": {
        "借款合同号": "contractNo", "借款银行": "bankName",
        "借款金额": "loanAmount", "到期日": "dueDate",
        "报告日": "reportDate", "逾期天数": "overdueDays",
        "逾期金额": "overdueAmount", "是否展期": "isExtended",
        "展期到期日": "extendedDueDate", "风险评价": "riskAssessment",
        "备注": "remark",
    },
    "L3-8": {
        "抵质押资产名称": "assetName", "资产类型": "assetType",
        "账面价值": "bookValue", "评估价值": "appraisalValue",
        "担保借款金额": "guaranteedLoan", "担保比例": "pledgeRatio",
        "权属证明": "ownershipProof", "是否受限": "isRestricted",
        "登记日期": "registrationDate", "备注": "remark",
    },
}

# 各sheet中应解析为数值的字段
_NUMERIC_FIELDS: dict[str, set[str]] = {
    "L3-2": {"beginning", "borrowed", "repaid", "endBalance", "currentPortion", "annualRate", "pledgeValue"},
    "L3-4": {"creditLimit", "usedCredit", "creditBalance", "bookBalance", "difference"},
    "L3-5": {"principal", "annualRate", "bookedInterest"},
    "L3-6": {"loanAmount", "term", "annualRate", "guaranteeAmount"},
    "L3-7": {"loanAmount", "overdueDays", "overdueAmount"},
    "L3-8": {"bookValue", "appraisalValue", "guaranteedLoan", "pledgeRatio"},
}

# checklist_responses item_id 映射
_SHEET_ITEM_ID: dict[str, str] = {
    "L3-2": "L3-L3-2-rows",
    "L3-4": "L3-credit-check-rows",
    "L3-5": "L3-L3-5-rows",
    "L3-6": "L3-L3-6-rows",
    "L3-7": "L3-overdue-check-rows",
    "L3-8": "L3-pledge-check-rows",
}


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic模型
# ═══════════════════════════════════════════════════════════════════════════════


class InterestCalcItem(BaseModel):
    """单笔利息测算请求"""
    contractNo: str
    principal: float
    annualRate: float
    loanStart: str
    loanEnd: str


class InterestCalcRequest(BaseModel):
    """利息测算批量请求"""
    items: list[InterestCalcItem]
    reportDate: str | None = None


class ReclassRequest(BaseModel):
    """一年内到期重分类请求"""
    dueDate: str
    reportDate: str
    amount: float


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


def _parse_date(val: str) -> date | None:
    """解析日期字符串，支持多种格式"""
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(val.strip(), fmt).date()
        except (ValueError, AttributeError):
            continue
    return None


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


def _calc_interest(principal: float, annual_rate: float, days: int) -> float:
    """利息=本金×年利率×计息天数/365"""
    if days <= 0 or annual_rate <= 0 or principal <= 0:
        return 0.0
    return round(principal * annual_rate * days / 365, 2)


def _calc_days_between(start_str: str, end_str: str) -> int:
    """计算两个日期之间的天数"""
    start = _parse_date(start_str)
    end = _parse_date(end_str)
    if not start or not end:
        return 0
    delta = (end - start).days
    return max(delta, 0)


def _calc_current_portion(due_date_str: str, report_date_str: str, amount: float) -> float:
    """一年内到期金额：报告日起一年内到期的部分"""
    due = _parse_date(due_date_str)
    report = _parse_date(report_date_str)
    if not due or not report or amount <= 0:
        return 0.0
    from dateutil.relativedelta import relativedelta
    one_year_later = report + relativedelta(years=1)
    if due <= one_year_later:
        return amount
    return 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/export-template")
async def l3_export_template(
    wp_id: str,
    sheet: str = Query(..., description="Sheet编码: L3-2/L3-4/L3-5/L3-6/L3-7/L3-8"),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出空白xlsx模板（含表头+格式，无数据行）

    Requirements: 11.3
    """
    _validate_sheet(sheet)

    wb = _create_template_wb(sheet)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"L3长期借款_{sheet}_模板.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.get("/export-data")
async def l3_export_data(
    wp_id: str,
    sheet: str = Query(..., description="Sheet编码: L3-2/L3-4/L3-5/L3-6/L3-7/L3-8"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出含当前数据的xlsx

    Requirements: 11.3
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

    filename = f"L3长期借款_{sheet}_数据.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.post("/import-data")
async def l3_import_data(
    wp_id: str,
    sheet: str = Query(..., description="Sheet编码: L3-2/L3-4/L3-5/L3-6/L3-7/L3-8"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """导入xlsx解析写入checklist_responses

    Requirements: 11.3
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
    warning: str | None = None
    if missing:
        raise HTTPException(400, f"列名不匹配，缺少: {missing}")

    actual_headers = _get_actual_headers(ws)

    # 解析数据行
    parsed_rows: list[dict] = []
    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if row_idx > _ROW_LIMIT + 1:
            warning = f"数据行超过{_ROW_LIMIT}行限制，已截断"
            break
        # 跳过全空行
        if all(cell is None or str(cell).strip() == "" for cell in row):
            continue
        parsed_rows.append(_parse_row(sheet, row, actual_headers))

    # 写入 checklist_responses
    item_id = _SHEET_ITEM_ID[sheet]
    json_str = json.dumps(parsed_rows, ensure_ascii=False)

    # project_id 为 NOT NULL：即使命中 ON CONFLICT 也会在 INSERT 阶段校验 NOT NULL，
    # 故必须提供 project_id（从 working_paper 反查），否则导入恒 500。
    pid_result = await db.execute(
        sa.text("SELECT project_id FROM working_paper WHERE id = :wp_id LIMIT 1"),
        {"wp_id": wp_id},
    )
    pid_row = pid_result.fetchone()
    project_id = str(pid_row.project_id) if pid_row and pid_row.project_id else None

    await db.execute(
        sa.text(
            "INSERT INTO checklist_responses (id, project_id, wp_id, item_id, remark) "
            "VALUES (:id, :project_id, :wp_id, :item_id, :remark) "
            "ON CONFLICT (wp_id, item_id) DO UPDATE SET remark = :remark"
        ),
        {
            "id": str(uuid4()),
            "project_id": project_id,
            "wp_id": wp_id,
            "item_id": item_id,
            "remark": json_str,
        },
    )
    await db.commit()

    field_count = len(_FIELD_MAPS.get(sheet, {}))
    result: dict[str, Any] = {
        "imported_count": len(parsed_rows),
        "field_count": field_count,
    }
    if warning:
        result["warning"] = warning
    return result


@router.post("/calculate-interest")
async def l3_calculate_interest(
    wp_id: str,
    request: InterestCalcRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    """利息测算API：批量计算各合同利息

    输入：合同号、本金、年利率、计息起始日、计息终止日
    输出：各合同测算利息 + 合计

    Requirements: 4.1, 10.1
    """
    results: list[dict] = []
    total_interest = 0.0

    for item in request.items:
        days = _calc_days_between(item.loanStart, item.loanEnd)
        interest = _calc_interest(item.principal, item.annualRate, days)
        total_interest += interest
        results.append({
            "contractNo": item.contractNo,
            "principal": item.principal,
            "annualRate": item.annualRate,
            "days": days,
            "calculatedInterest": interest,
        })

    return {
        "items": results,
        "totalInterest": round(total_interest, 2),
        "count": len(results),
    }


@router.post("/reclass-current-portion")
async def l3_reclass_current_portion(
    wp_id: str,
    request: ReclassRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    """一年内到期重分类API

    判定一年内到期金额并生成重分类分录建议

    Requirements: 5.2, 10.3
    """
    current_portion = _calc_current_portion(
        request.dueDate, request.reportDate, request.amount
    )

    reclass_entry: dict | None = None
    if current_portion > 0:
        reclass_entry = {
            "type": "RJE",
            "description": "一年内到期的长期借款重分类",
            "debit": {
                "account": "2501 长期借款",
                "amount": current_portion,
            },
            "credit": {
                "account": "2801 一年内到期的非流动负债",
                "amount": current_portion,
            },
        }

    return {
        "currentPortion": current_portion,
        "dueDate": request.dueDate,
        "reportDate": request.reportDate,
        "originalAmount": request.amount,
        "reclassEntry": reclass_entry,
    }
