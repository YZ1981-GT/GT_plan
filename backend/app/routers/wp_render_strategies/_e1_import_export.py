"""E1 货币资金 — 导入导出三级端点

3个端点：
- POST /api/workpapers/{wp_id}/e1/export-template?sheet={sheet_code}  空白模板xlsx
- POST /api/workpapers/{wp_id}/e1/export-data?sheet={sheet_code}      数据xlsx
- POST /api/workpapers/{wp_id}/e1/import-data?sheet={sheet_code}      解析xlsx写入

支持sheets: E1-2/E1-3/E1-5/E1-6/E1-7/E1-8/E1-9/E1-10/E1-20/E1-21/E1-22
科目编码白名单: 1001/1002/1012
RFC5987 Content-Disposition header with Chinese filename encoding

Requirements: 13.2
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

router = APIRouter(tags=["e1-import-export"])

# ═══════════════════════════════════════════════════════════════════════════════
# Sheet 配置
# ═══════════════════════════════════════════════════════════════════════════════

_ROW_LIMIT = 500

_ACCOUNT_CODE_WHITELIST: set[str] = {"1001", "1002", "1012"}

_SUPPORTED_SHEETS: set[str] = {
    "E1-2", "E1-3", "E1-5", "E1-6", "E1-7", "E1-8", "E1-9",
    "E1-10", "E1-20", "E1-21", "E1-22",
}

_SHEET_HEADERS: dict[str, list[str]] = {
    "E1-2": [
        "币种", "期初余额", "本期增加", "本期减少", "期末余额",
        "汇率", "折算人民币", "账项调整", "审定数",
    ],
    "E1-3": [
        "开户银行", "账号", "账户性质", "币种", "期初余额",
        "本期增加", "本期减少", "期末余额", "账项调整", "审定数",
        "对账单余额", "差异", "回函确认金额", "询证函索引号",
    ],
    "E1-5": [
        "调整事项说明", "类别", "报表项目", "科目名称",
        "附注项目", "借方金额", "贷方金额", "索引号", "备注",
    ],
    "E1-6": [
        "开户银行", "账号", "企业账面余额", "银行已收企业未收",
        "银行已付企业未付", "调节后企业余额",
        "银行对账单余额", "企业已收银行未收",
        "企业已付银行未付", "调节后银行余额", "差异",
    ],
    "E1-7": [
        "面值", "张数", "金额", "备注",
    ],
    "E1-8": [
        "币种", "面值", "张数", "金额", "汇率", "折算人民币", "备注",
    ],
    "E1-9": [
        "存单编号", "存入银行", "存入日期", "到期日", "币种",
        "金额", "利率", "备注",
    ],
    "E1-10": [
        "开户银行", "账号", "账户性质", "开户日期",
        "是否征信核实", "是否审定表一致", "核对结果",
    ],
    "E1-20": [
        "账户名称", "开户银行", "币种", "本金金额",
        "起息日", "到期日", "天数", "日利率",
        "应计利息原币", "汇率", "应计利息人民币", "备注",
    ],
    "E1-21": [
        "日期", "摘要", "收入金额", "支出金额", "余额",
        "是否跨期", "备注",
    ],
    "E1-22": [
        "日期", "摘要", "收入金额", "支出金额", "余额",
        "是否跨期", "备注",
    ],
}

# checklist_responses item_id 映射
_SHEET_ITEM_ID: dict[str, str] = {
    "E1-2": "E1-cash-detail-rows",
    "E1-3": "E1-bank-detail-rows",
    "E1-5": "E1-adjustment-rows",
    "E1-6": "E1-reconciliation-rows",
    "E1-7": "E1-cash-count-rmb-rows",
    "E1-8": "E1-cash-count-fx-rows",
    "E1-9": "E1-cert-count-rows",
    "E1-10": "E1-account-list-rows",
    "E1-20": "E1-accrued-interest-rows",
    "E1-21": "E1-cutoff-bank-rows",
    "E1-22": "E1-cutoff-other-rows",
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


# ═══════════════════════════════════════════════════════════════════════════════
# 导出行转换
# ═══════════════════════════════════════════════════════════════════════════════

def _export_row(sheet_code: str, data: dict) -> list:
    """通用导出行转换——根据sheet_code按列头顺序提取字段"""
    headers = _SHEET_HEADERS[sheet_code]
    # 字段名映射: 中文列名 → JSON字段名
    field_map = _FIELD_MAPS.get(sheet_code, {})
    result = []
    for col_name in headers:
        field = field_map.get(col_name, col_name)
        val = data.get(field, "")
        result.append(val if val is not None else "")
    return result


# 中文列名 → JSON 字段名 映射表
_FIELD_MAPS: dict[str, dict[str, str]] = {
    "E1-2": {
        "币种": "currency", "期初余额": "openingBalance",
        "本期增加": "increase", "本期减少": "decrease",
        "期末余额": "endingBalance", "汇率": "exchangeRate",
        "折算人民币": "convertedRmb", "账项调整": "adjustment",
        "审定数": "audited",
    },
    "E1-3": {
        "开户银行": "bankName", "账号": "accountNo",
        "账户性质": "accountType", "币种": "currency",
        "期初余额": "openingBalance", "本期增加": "increase",
        "本期减少": "decrease", "期末余额": "endingBalance",
        "账项调整": "adjustment", "审定数": "audited",
        "对账单余额": "statementBalance", "差异": "difference",
        "回函确认金额": "confirmAmount", "询证函索引号": "confirmIndexRef",
    },
    "E1-5": {
        "调整事项说明": "description", "类别": "category",
        "报表项目": "reportItem", "科目名称": "accountName",
        "附注项目": "noteItem", "借方金额": "debitAmount",
        "贷方金额": "creditAmount", "索引号": "indexRef", "备注": "remark",
    },
    "E1-6": {
        "开户银行": "bankName", "账号": "accountNo",
        "企业账面余额": "bookBalance",
        "银行已收企业未收": "bankReceivedNotBooked",
        "银行已付企业未付": "bankPaidNotBooked",
        "调节后企业余额": "reconciledBook",
        "银行对账单余额": "statementBalance",
        "企业已收银行未收": "bookReceivedNotBank",
        "企业已付银行未付": "bookPaidNotBank",
        "调节后银行余额": "reconciledStatement",
        "差异": "difference",
    },
    "E1-7": {
        "面值": "denomination", "张数": "quantity",
        "金额": "amount", "备注": "remark",
    },
    "E1-8": {
        "币种": "currency", "面值": "denomination",
        "张数": "quantity", "金额": "amount",
        "汇率": "exchangeRate", "折算人民币": "convertedRmb",
        "备注": "remark",
    },
    "E1-9": {
        "存单编号": "certNo", "存入银行": "bankName",
        "存入日期": "depositDate", "到期日": "maturityDate",
        "币种": "currency", "金额": "amount",
        "利率": "interestRate", "备注": "remark",
    },
    "E1-10": {
        "开户银行": "bankName", "账号": "accountNo",
        "账户性质": "accountType", "开户日期": "openDate",
        "是否征信核实": "creditChecked", "是否审定表一致": "consistent",
        "核对结果": "checkResult",
    },
    "E1-20": {
        "账户名称": "accountName", "开户银行": "bankName",
        "币种": "currency", "本金金额": "principalAmount",
        "起息日": "startDate", "到期日": "maturityDate",
        "天数": "days", "日利率": "dailyRate",
        "应计利息原币": "accruedInterestFc", "汇率": "exchangeRate",
        "应计利息人民币": "accruedInterestRmb", "备注": "remark",
    },
    "E1-21": {
        "日期": "date", "摘要": "summary",
        "收入金额": "receiptAmount", "支出金额": "paymentAmount",
        "余额": "balance", "是否跨期": "isCrossperiod", "备注": "remark",
    },
    "E1-22": {
        "日期": "date", "摘要": "summary",
        "收入金额": "receiptAmount", "支出金额": "paymentAmount",
        "余额": "balance", "是否跨期": "isCrossperiod", "备注": "remark",
    },
}


def _parse_row(sheet_code: str, row: tuple, actual_headers: list[str]) -> dict:
    """通用导入行解析——根据sheet_code按列名映射回JSON字段"""
    field_map = _FIELD_MAPS.get(sheet_code, {})
    # 反转映射: JSON字段名 → 中文列名
    reverse_map = {v: k for k, v in field_map.items()}
    result: dict[str, Any] = {"rowId": str(uuid4())}
    for field_name, col_name in field_map.items():
        # field_map key=中文列名, value=JSON字段名
        raw = _col_val(row, actual_headers, field_name)
        # 判断是否应为数值字段
        if col_name in _NUMERIC_FIELDS.get(sheet_code, set()):
            result[col_name] = _safe_float(raw)
        else:
            result[col_name] = _safe_str(raw)
    return result


# 各sheet中应解析为数值的字段
_NUMERIC_FIELDS: dict[str, set[str]] = {
    "E1-2": {"openingBalance", "increase", "decrease", "endingBalance", "exchangeRate", "convertedRmb", "adjustment", "audited"},
    "E1-3": {"openingBalance", "increase", "decrease", "endingBalance", "adjustment", "audited", "statementBalance", "difference", "confirmAmount"},
    "E1-5": {"debitAmount", "creditAmount"},
    "E1-6": {"bookBalance", "bankReceivedNotBooked", "bankPaidNotBooked", "reconciledBook", "statementBalance", "bookReceivedNotBank", "bookPaidNotBank", "reconciledStatement", "difference"},
    "E1-7": {"denomination", "quantity", "amount"},
    "E1-8": {"denomination", "quantity", "amount", "exchangeRate", "convertedRmb"},
    "E1-9": {"amount", "interestRate"},
    "E1-10": set(),
    "E1-20": {"principalAmount", "days", "dailyRate", "accruedInterestFc", "exchangeRate", "accruedInterestRmb"},
    "E1-21": {"receiptAmount", "paymentAmount", "balance"},
    "E1-22": {"receiptAmount", "paymentAmount", "balance"},
}


# ═══════════════════════════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════════════════════════


@router.post("/api/workpapers/{wp_id}/e1/export-template")
async def e1_export_template(
    wp_id: str,
    sheet: str = Query(..., description="Sheet编码: E1-2/E1-3/E1-5/E1-6/E1-7/E1-8/E1-9/E1-10/E1-20/E1-21/E1-22"),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出空白xlsx模板（含表头+格式，无数据行）"""
    _validate_sheet(sheet)

    wb = _create_template_wb(sheet)
    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    filename = f"{sheet}_模板.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.post("/api/workpapers/{wp_id}/e1/export-data")
async def e1_export_data(
    wp_id: str,
    sheet: str = Query(..., description="Sheet编码: E1-2/E1-3/E1-5/E1-6/E1-7/E1-8/E1-9/E1-10/E1-20/E1-21/E1-22"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出含当前数据的xlsx"""
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

    filename = f"{sheet}_数据.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.post("/api/workpapers/{wp_id}/e1/import-data")
async def e1_import_data(
    wp_id: str,
    sheet: str = Query(..., description="Sheet编码: E1-2/E1-3/E1-5/E1-6/E1-7/E1-8/E1-9/E1-10/E1-20/E1-21/E1-22"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """导入xlsx解析写入checklist_responses"""
    _validate_sheet(sheet)
    import sqlalchemy as sa

    # 读取上传文件
    content = await file.read()
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
