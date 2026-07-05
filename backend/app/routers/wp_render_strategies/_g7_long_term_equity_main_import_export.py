"""G7 长期股权投资(main组) — 导入导出（G7-2 明细表 / G7-3 调整分录）.

支持 2 张动态行表格：
  G7-2 明细表(54列/5区段Tab) / G7-3 调整分录(10列)

G7-2 导出特殊处理：54列按5区段分5 worksheet 导出（多区块分sheet导出）。
G7-3 单sheet导出。

字段键与前端 composable（useG7ImportExport 的行接口）严格对齐，保证 round-trip。
"""

from __future__ import annotations

import io
import json
from typing import Any
from uuid import uuid4

import sqlalchemy as sa
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from sqlalchemy.ext.asyncio import AsyncSession
from urllib.parse import quote

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

from ._cycle_import_export_common import (
    ROW_LIMIT,
    build_workbook_template,
    export_row_by_keys,
    is_numeric_field_key,
    load_json_rows,
    parse_row_by_headers,
    parse_upload_xlsx,
    safe_float,
    safe_str,
    upsert_json_rows,
    workbook_to_response,
)

router = APIRouter(tags=["g7-main-import-export"])

# ═══════════════════════════════════════════════════════════════════════════════
# G7-2 明细表（54列，5区段Tab）— 多sheet导出
# ═══════════════════════════════════════════════════════════════════════════════

# 区段1: 基础信息(8列)
_G7_2_SEG1_HEADERS = [
    "被投资单位名称", "控制类型", "持股比例(%)", "投票权比例(%)",
    "行业", "注册地", "主营业务", "是否关联方",
]
_G7_2_SEG1_KEYS = [
    "investeeName", "controlType", "holdingRatio", "votingRatio",
    "industry", "registeredPlace", "mainBusiness", "isRelatedParty",
]

# 区段2: 期初余额(10列)
_G7_2_SEG2_HEADERS = [
    "期初投资成本", "期初权益法调整", "期初减值准备", "期初账面价值",
    "期初审定成本", "期初审定权益法", "期初审定减值",
    "期初审定净值", "期初余额备注", "序号",
]
_G7_2_SEG2_KEYS = [
    "openingInvestCost", "openingEquityAdj", "openingImpairment", "openingBookValue",
    "openingAuditedCost", "openingAuditedEquity", "openingAuditedImpairment",
    "openingAuditedNetValue", "openingRemark", "seq",
]

# 区段3: 本期变动(12列)
_G7_2_SEG3_HEADERS = [
    "本期增加(新增投资)", "本期增加(权益法)", "本期减少(处置)",
    "本期减少(权益法调整)", "本期减值计提", "本期减值转回",
    "被投资单位净利润", "持股比例调整", "其他综合收益",
    "其他权益变动", "利润分配", "变动备注",
]
_G7_2_SEG3_KEYS = [
    "increaseNewInvest", "increaseEquityMethod", "decreaseDisposal",
    "decreaseEquityAdj", "impairmentProvision", "impairmentReversal",
    "investeeNetProfit", "holdingRatioChange", "otherComprehensiveIncome",
    "otherEquityChange", "profitDistribution", "changeRemark",
]

# 区段4: 期末+减值(12列)
_G7_2_SEG4_HEADERS = [
    "期末投资成本", "期末权益法调整", "期末小计",
    "期末减值准备", "期末账面价值", "审定调整",
    "审定数", "可收回金额", "减值测试结论",
    "发函情况", "索引", "期末备注",
]
_G7_2_SEG4_KEYS = [
    "closingInvestCost", "closingEquityAdj", "closingSubtotal",
    "closingImpairment", "closingBookValue", "auditAdjustment",
    "auditedAmount", "recoverableAmount", "impairmentTestConclusion",
    "confirmationStatus", "indexRef", "closingRemark",
]

# 区段5: 权益法详情(12列)
_G7_2_SEG5_HEADERS = [
    "被投资方净资产", "享有份额", "商誉",
    "内部交易抵销", "未确认损失", "权益法投资收益",
    "本期OCI", "股利收入", "计量方法确认",
    "处置损益", "权益法备注", "权益法序号",
]
_G7_2_SEG5_KEYS = [
    "investeeNetAssets", "shareOfNetAssets", "goodwill",
    "internalTransElim", "unrecognizedLoss", "equityMethodIncome",
    "currentOCI", "dividendIncome", "measurementConfirm",
    "disposalGainLoss", "equityRemark", "equitySeq",
]

# 全54列合并（用于导入解析 - 宽表模式）
_G7_2_ALL_HEADERS = (
    _G7_2_SEG1_HEADERS + _G7_2_SEG2_HEADERS + _G7_2_SEG3_HEADERS
    + _G7_2_SEG4_HEADERS + _G7_2_SEG5_HEADERS
)
_G7_2_ALL_KEYS = (
    _G7_2_SEG1_KEYS + _G7_2_SEG2_KEYS + _G7_2_SEG3_KEYS
    + _G7_2_SEG4_KEYS + _G7_2_SEG5_KEYS
)

# 5 区段名与对应列
_G7_2_SEGMENTS = [
    ("基础信息", _G7_2_SEG1_HEADERS, _G7_2_SEG1_KEYS),
    ("期初余额", _G7_2_SEG2_HEADERS, _G7_2_SEG2_KEYS),
    ("本期变动", _G7_2_SEG3_HEADERS, _G7_2_SEG3_KEYS),
    ("期末+减值", _G7_2_SEG4_HEADERS, _G7_2_SEG4_KEYS),
    ("权益法详情", _G7_2_SEG5_HEADERS, _G7_2_SEG5_KEYS),
]

# ═══════════════════════════════════════════════════════════════════════════════
# G7-3 调整分录汇总（10列）
# ═══════════════════════════════════════════════════════════════════════════════

_G7_3_HEADERS = [
    "序号", "分录类型", "日期", "摘要", "科目代码", "科目名称",
    "借方金额", "贷方金额", "编制人", "备注",
]
_G7_3_KEYS = [
    "seq", "entryType", "date", "summary", "accountCode", "accountName",
    "debitAmount", "creditAmount", "preparedBy", "remark",
]

# ═══════════════════════════════════════════════════════════════════════════════
# 通用辅助
# ═══════════════════════════════════════════════════════════════════════════════

_ITEM_IDS = {
    "G7-2": "G7-2-rows",
    "G7-3": "G7-3-rows",
}

_SUPPORTED_SHEETS = set(_ITEM_IDS.keys())


def _validate_sheet(sheet: str) -> None:
    if sheet not in _SUPPORTED_SHEETS:
        raise HTTPException(400, f"不支持的sheet: {sheet}。支持: {sorted(_SUPPORTED_SHEETS)}")


# ═══════════════════════════════════════════════════════════════════════════════
# G7-2 多sheet导出（5区段→5 worksheet）
# ═══════════════════════════════════════════════════════════════════════════════

def _build_g7_2_multi_sheet_workbook(rows: list[dict], *, template_only: bool = False) -> Workbook:
    """G7-2 按5区段分sheet导出，每个区段一个worksheet。"""
    wb = Workbook()
    wb.remove(wb.active)  # type: ignore[arg-type]

    for seg_name, seg_headers, seg_keys in _G7_2_SEGMENTS:
        ws = wb.create_sheet(title=seg_name)
        # 标题行
        ws.append([f"G7-2 明细表 — {seg_name}"])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(seg_headers), 1))
        ws["A1"].font = Font(bold=True, size=12)
        # 表头行
        ws.append(seg_headers)
        ws.freeze_panes = "A3"
        for col_idx in range(1, len(seg_headers) + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = 14

        if not template_only:
            for row_data in rows:
                ws.append(export_row_by_keys(row_data, seg_keys))

    # 编制说明
    ws_guide = wb.create_sheet("编制说明")
    ws_guide.append(["G7-2 长期股权投资明细表 编制说明"])
    ws_guide.append([])
    guidance_lines = [
        "54列拆为5区段Tab：基础信息(8) / 期初余额(10) / 本期变动(12) / 期末+减值(12) / 权益法详情(12)。",
        "公式列导入后前端自动重算（期初账面价值/期末投资成本/期末权益法调整/期末小计/期末减值/期末账面价值/审定数/享有份额）。",
        "期末投资成本 = 期初投资成本 + 新增投资 - 处置减少。",
        "期末权益法调整 = 期初权益法调整 + 权益法增加 - 权益法减少。",
        "期末小计 = 期末投资成本 + 期末权益法调整。",
        "期末减值准备 = 期初减值 + 计提 - 转回。",
        "期末账面价值 = 期末小计 - 期末减值准备。",
        "审定数 = 期末账面价值 + 审定调整。",
        "享有份额 = 被投资方净资产 × 持股比例。",
        "控制类型填：子公司 / 合营 / 联营。",
        "持股比例/投票权比例以百分数填写（如 51.00 表示 51%）。",
        "是否关联方填：是 / 否。",
    ]
    for line in guidance_lines:
        ws_guide.append([line])
    ws_guide.column_dimensions["A"].width = 80
    return wb


def _parse_g7_2_import(content: bytes) -> tuple[list[dict], list[str]]:
    """解析G7-2导入文件，支持多sheet或单sheet宽表两种格式。"""
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    errors: list[str] = []
    rows_dict: dict[int, dict] = {}

    # 策略1: 多sheet格式（5区段分sheet）
    multi_sheet = len(wb.sheetnames) >= 5 and any("基础信息" in s for s in wb.sheetnames)

    if multi_sheet:
        for seg_name, seg_headers, seg_keys in _G7_2_SEGMENTS:
            ws = None
            for name in wb.sheetnames:
                if seg_name in name:
                    ws = wb[name]
                    break
            if ws is None:
                errors.append(f"缺少工作表: {seg_name}")
                continue
            # 表头在第2行（第1行是标题）
            header_row_idx = 2
            actual_headers = [
                str(c.value).strip() if c.value else ""
                for c in next(ws.iter_rows(min_row=header_row_idx, max_row=header_row_idx))
            ]
            missing = [h for h in seg_headers if h not in actual_headers]
            if missing:
                errors.append(f"工作表[{seg_name}]缺少列: {', '.join(missing)}")
                continue
            for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
                if all(v is None for v in row):
                    continue
                if row_idx >= ROW_LIMIT:
                    errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
                    break
                if row_idx not in rows_dict:
                    rows_dict[row_idx] = {"id": str(uuid4())}
                values = list(row) + [None] * max(0, len(seg_headers) - len(row))
                for col_i, key in enumerate(seg_keys):
                    raw = values[col_i] if col_i < len(values) else None
                    if is_numeric_field_key(key):
                        rows_dict[row_idx][key] = safe_float(raw)
                    else:
                        rows_dict[row_idx][key] = safe_str(raw)
    else:
        # 策略2: 单sheet宽表（54列合并）
        ws = wb.active
        if ws is None:
            wb.close()
            return [], ["xlsx文件中无活动工作表"]
        # 自动检测表头行
        header_row_idx = 1
        for r in range(1, 5):
            test_row = [str(c.value).strip() if c.value else "" for c in next(ws.iter_rows(min_row=r, max_row=r))]
            if "被投资单位名称" in test_row:
                header_row_idx = r
                break
        actual_headers = [
            str(c.value).strip() if c.value else ""
            for c in next(ws.iter_rows(min_row=header_row_idx, max_row=header_row_idx))
        ]
        if "被投资单位名称" not in actual_headers:
            errors.append("无法识别表头，缺少'被投资单位名称'列")
            wb.close()
            return [], errors
        for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
            if all(v is None for v in row):
                continue
            if row_idx >= ROW_LIMIT:
                errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
                break
            parsed: dict[str, Any] = {"id": str(uuid4())}
            values = list(row) + [None] * max(0, len(actual_headers) - len(row))
            for col_i, h in enumerate(actual_headers):
                if h in _G7_2_ALL_HEADERS:
                    key_idx = _G7_2_ALL_HEADERS.index(h)
                    key = _G7_2_ALL_KEYS[key_idx]
                    raw = values[col_i] if col_i < len(values) else None
                    if is_numeric_field_key(key):
                        parsed[key] = safe_float(raw)
                    else:
                        parsed[key] = safe_str(raw)
            rows_dict[row_idx] = parsed

    wb.close()
    result = list(rows_dict.values())
    if len(result) > ROW_LIMIT:
        result = result[:ROW_LIMIT]
        errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
    return result, errors


# ═══════════════════════════════════════════════════════════════════════════════
# 端点
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/api/workpapers/{wp_id}/g7-main/export-template")
async def g7_main_export_template(
    wp_id: str,
    sheet: str = Query(...),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出空模板：G7-2(5区段多sheet) / G7-3(单sheet)。"""
    _validate_sheet(sheet)

    if sheet == "G7-2":
        wb = _build_g7_2_multi_sheet_workbook([], template_only=True)
        return workbook_to_response(wb, "G7-2_明细表_模板.xlsx")
    else:  # G7-3
        wb = build_workbook_template(
            "G7-3",
            _G7_3_HEADERS,
            title="G7-3 调整分录汇总",
            guidance=[
                "G7-3 调整分录 编制说明",
                "",
                "分录类型填 AJE 或 RJE；每张凭证借贷方金额必须相等。",
                "科目代码填完整编码（如 1511）。",
                "保存后自动回写 G7-1 审定表 AJE/RJE 列。",
            ],
        )
        return workbook_to_response(wb, "G7-3_调整分录_模板.xlsx")


@router.post("/api/workpapers/{wp_id}/g7-main/export-data")
async def g7_main_export_data(
    wp_id: str,
    sheet: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出数据：G7-2(5区段多sheet含数据) / G7-3(单sheet含数据)。"""
    _validate_sheet(sheet)
    item_id = _ITEM_IDS[sheet]
    rows = await load_json_rows(db, wp_id, item_id, field="conclusion")

    if sheet == "G7-2":
        wb = _build_g7_2_multi_sheet_workbook(rows, template_only=False)
        return workbook_to_response(wb, "G7-2_明细表_数据.xlsx")
    else:  # G7-3
        wb = build_workbook_template(
            "G7-3",
            _G7_3_HEADERS,
            title="G7-3 调整分录汇总",
            guidance=["分录类型填 AJE 或 RJE；每张凭证借贷方金额必须相等。"],
        )
        ws = wb["G7-3"]
        for d in rows:
            ws.append(export_row_by_keys(d, _G7_3_KEYS))
        return workbook_to_response(wb, "G7-3_调整分录_数据.xlsx")


@router.post("/api/workpapers/{wp_id}/g7-main/import-data")
async def g7_main_import_data(
    wp_id: str,
    sheet: str = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """导入数据：G7-2(支持多sheet或宽表) / G7-3(单sheet)。"""
    _validate_sheet(sheet)
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(400, "请上传 .xlsx 格式文件")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "文件大小不能超过10MB")

    item_id = _ITEM_IDS[sheet]
    errors: list[str] = []
    rows: list[dict] = []

    if sheet == "G7-2":
        rows, errors = _parse_g7_2_import(content)
    else:  # G7-3
        try:
            actual, raw = parse_upload_xlsx(content, _G7_3_HEADERS, header_row=2)
        except ValueError as e:
            return {"ok": False, "errors": [str(e)], "imported_count": 0}
        except Exception:
            raise HTTPException(400, "无法解析xlsx文件")
        for i, r in enumerate(raw, start=1):
            if i > ROW_LIMIT:
                errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
                break
            rows.append(parse_row_by_headers(r, actual, _G7_3_KEYS))

    if errors and not rows:
        return {"ok": False, "errors": errors, "imported_count": 0}

    await upsert_json_rows(db, wp_id, item_id, rows, field="conclusion")
    out: dict[str, Any] = {"ok": True, "imported_count": len(rows), "errors": errors}
    if len(rows) >= ROW_LIMIT:
        out["warning"] = f"数据行数超过{ROW_LIMIT}行限制，已截断"
    return out
