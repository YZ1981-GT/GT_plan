"""G7 长期股权投资(子公司组) — 导入导出（6张表×3端点=18端点）.

支持 6 张动态行表格：
  G7-8  同控初始计量(9列) / G7-9  非同控初始计量(9列)
  G7-10 后续计量(9列) / G7-11 处置非一揽子(14列) / G7-12 处置一揽子(14列)
  G7-18 凭证检查(19列→3区段Tab)

G7-18 导出特殊处理：19列按3区段分3 worksheet 导出（多区块分sheet导出）。
其余5张表单sheet导出。

字段键与前端 composable（useG7SubImportExport 的行接口）严格对齐，保证 round-trip。
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

router = APIRouter(tags=["g7-sub-import-export"])


# ═══════════════════════════════════════════════════════════════════════════════
# G7-8 同控初始计量（9列，单sheet）
# ═══════════════════════════════════════════════════════════════════════════════

_G7_8_HEADERS = [
    "被投资单位", "合并日", "合并方式", "被合并方账面净资产",
    "持股比例", "享有份额", "初始投资成本", "支付对价", "差额处理",
]
_G7_8_KEYS = [
    "investeeName", "mergerDate", "mergerType", "acquireeNetAssets",
    "shareholdingRatio", "shareOfNetAssets", "initialCost", "consideration", "differenceHandling",
]

# ═══════════════════════════════════════════════════════════════════════════════
# G7-9 非同控初始计量（9列，单sheet）
# ═══════════════════════════════════════════════════════════════════════════════

_G7_9_HEADERS = [
    "被投资单位", "购买日", "合并方式", "支付对价",
    "直接费用", "初始投资成本", "被购买方净资产FV", "享有份额", "商誉",
]
_G7_9_KEYS = [
    "investeeName", "acquisitionDate", "mergerType", "consideration",
    "directFees", "initialCost", "acquireeNetAssetsFV", "shareOfFV", "goodwill",
]

# ═══════════════════════════════════════════════════════════════════════════════
# G7-10 后续计量（9列，单sheet）
# ═══════════════════════════════════════════════════════════════════════════════

_G7_10_HEADERS = [
    "被投资单位", "期初账面", "本期增加", "本期减值",
    "被投资方宣告股利", "持股比例", "应确认投资收益", "期末账面", "企业期末数",
]
_G7_10_KEYS = [
    "investeeName", "openingBalance", "additionInvestment", "impairmentLoss",
    "declaredDividend", "shareholdingRatio", "investmentIncome", "closingBalance", "companyEndingBalance",
]

# ═══════════════════════════════════════════════════════════════════════════════
# G7-11 处置非一揽子（14列，单sheet）
# ═══════════════════════════════════════════════════════════════════════════════

_G7_11_HEADERS = [
    "被投资单位", "处置日", "处置比例", "处置对价",
    "处置日长投账面", "处置日应收股利", "处置前OCI累计", "可转损益OCI",
    "个别报表处置损益", "合并报表调整", "合并层面净资产份额", "合并处置损益",
    "审计结论", "索引",
]
_G7_11_KEYS = [
    "investeeName", "disposalDate", "disposalRatio", "disposalPrice",
    "disposalDateBookValue", "disposalDateDividend", "priorOCICumulative", "transferableOCI",
    "individualGain", "consolidationAdjustment", "consolidatedNetAssetShare", "consolidatedGain",
    "auditConclusion", "indexRef",
]

# ═══════════════════════════════════════════════════════════════════════════════
# G7-12 处置一揽子（14列，单sheet）
# ═══════════════════════════════════════════════════════════════════════════════

_G7_12_HEADERS = [
    "被投资单位", "各次交易日期", "各次交易对价", "各次交易持股变动",
    "累计对价", "累计持股变动", "丧失控制权日", "丧失日长投账面",
    "丧失日剩余投资FV", "追溯调整金额", "合并处置损益", "一揽子判断依据",
    "审计结论", "索引",
]
_G7_12_KEYS = [
    "investeeName", "transactionDate", "transactionPrice", "transactionShareChange",
    "cumulativePrice", "cumulativeShareChange", "lossOfControlDate", "lossDateBookValue",
    "lossDateResidualFV", "retrospectiveAdjustment", "consolidatedGain", "packageJudgmentBasis",
    "auditConclusion", "indexRef",
]


# ═══════════════════════════════════════════════════════════════════════════════
# G7-18 凭证检查（19列→3区段Tab）— 多sheet导出
# ═══════════════════════════════════════════════════════════════════════════════

# 区段1: 凭证基础(7列)
_G7_18_SEG1_HEADERS = [
    "日期", "凭证号", "业务内容", "对方科目", "借方", "贷方", "附件",
]
_G7_18_SEG1_KEYS = [
    "voucherDate", "voucherNo", "businessContent", "counterAccount", "debitAmount", "creditAmount", "attachment",
]

# 区段2: 核对检查(7列)
_G7_18_SEG2_HEADERS = [
    "支持性文件", "核对1-原始凭证", "核对2-授权", "核对3-账务",
    "核对4-金额", "核对5-分类", "核对6-投资收益",
]
_G7_18_SEG2_KEYS = [
    "supportingDoc", "check1Original", "check2Authorization", "check3Accounting",
    "check4Amount", "check5Classification", "check6InvestmentIncome",
]

# 区段3: 结论(5列)
_G7_18_SEG3_HEADERS = [
    "索引", "是否异常", "异常说明", "风险等级", "备注",
]
_G7_18_SEG3_KEYS = [
    "indexRef", "isAbnormal", "abnormalNote", "riskLevel", "remark",
]

# 全19列合并（用于导入解析 - 宽表模式）
_G7_18_ALL_HEADERS = _G7_18_SEG1_HEADERS + _G7_18_SEG2_HEADERS + _G7_18_SEG3_HEADERS
_G7_18_ALL_KEYS = _G7_18_SEG1_KEYS + _G7_18_SEG2_KEYS + _G7_18_SEG3_KEYS

# 3 区段名与对应列
_G7_18_SEGMENTS = [
    ("凭证基础", _G7_18_SEG1_HEADERS, _G7_18_SEG1_KEYS),
    ("核对检查", _G7_18_SEG2_HEADERS, _G7_18_SEG2_KEYS),
    ("结论", _G7_18_SEG3_HEADERS, _G7_18_SEG3_KEYS),
]


# ═══════════════════════════════════════════════════════════════════════════════
# 通用辅助
# ═══════════════════════════════════════════════════════════════════════════════

_ITEM_IDS = {
    "G7-8": "G7-8-rows",
    "G7-9": "G7-9-rows",
    "G7-10": "G7-10-rows",
    "G7-11": "G7-11-rows",
    "G7-12": "G7-12-rows",
    "G7-18": "G7-18-rows",
}

_SUPPORTED_SHEETS = set(_ITEM_IDS.keys())

# 单sheet规格（G7-8/G7-9/G7-10/G7-11/G7-12）
_SINGLE_SHEET_SPECS: dict[str, dict[str, Any]] = {
    "G7-8": {
        "headers": _G7_8_HEADERS,
        "field_keys": _G7_8_KEYS,
        "title": "G7-8 同控初始计量",
        "guidance": [
            "G7-8 同控企业合并初始计量 编制说明",
            "",
            "合并方式填：吸收合并 / 控股合并 / 新设合并。",
            "持股比例以小数填写（如 0.51 表示 51%）。",
            "享有份额 = 被合并方账面净资产 × 持股比例（公式列导入后前端自动重算）。",
            "初始投资成本 = 享有份额（同控下以账面价值计量）。",
            "差额处理填写：调整资本公积 / 调整留存收益。",
        ],
    },
    "G7-9": {
        "headers": _G7_9_HEADERS,
        "field_keys": _G7_9_KEYS,
        "title": "G7-9 非同控初始计量",
        "guidance": [
            "G7-9 非同控企业合并初始计量 编制说明",
            "",
            "合并方式填：吸收合并 / 控股合并 / 新设合并。",
            "初始投资成本 = 支付对价 + 直接费用（公式列导入后前端自动重算）。",
            "享有份额 = 被购买方净资产FV × 持股比例。",
            "商誉 = 初始投资成本 - 享有份额（正=商誉资产，负=廉价购买利得）。",
        ],
    },
    "G7-10": {
        "headers": _G7_10_HEADERS,
        "field_keys": _G7_10_KEYS,
        "title": "G7-10 后续计量（成本法）",
        "guidance": [
            "G7-10 成本法后续计量 编制说明",
            "",
            "应确认投资收益 = 被投资方宣告股利 × 持股比例（公式列导入后前端自动重算）。",
            "期末账面 = 期初账面 + 本期增加 - 本期减值（公式列导入后前端自动重算）。",
            "持股比例以小数填写（如 0.60 表示 60%）。",
            "企业期末数从试算表自动填充。",
        ],
    },
    "G7-11": {
        "headers": _G7_11_HEADERS,
        "field_keys": _G7_11_KEYS,
        "title": "G7-11 处置测试（非一揽子）",
        "guidance": [
            "G7-11 非一揽子处置测试 编制说明",
            "",
            "处置比例以小数填写（如 0.30 表示处置30%股权）。",
            "个别报表处置损益 = 处置对价 - 处置日长投账面 - 处置日应收股利 + 可转损益OCI。",
            "合并处置损益需考虑合并报表调整及合并层面净资产份额。",
            "审计结论填写处置定价公允性、关联方交易判断。",
        ],
    },
    "G7-12": {
        "headers": _G7_12_HEADERS,
        "field_keys": _G7_12_KEYS,
        "title": "G7-12 处置测试（一揽子交易）",
        "guidance": [
            "G7-12 一揽子交易处置测试 编制说明",
            "",
            "一揽子交易：多次交易实质上构成一项整体安排。",
            "累计对价/累计持股变动为前序交易累加值。",
            "丧失控制权日统一确认全部处置损益。",
            "追溯调整金额 = 丧失日剩余投资FV - 丧失日长投账面。",
            "一揽子判断依据为必填项，需说明判断理由。",
        ],
    },
}


def _validate_sheet(sheet: str) -> None:
    if sheet not in _SUPPORTED_SHEETS:
        raise HTTPException(400, f"不支持的sheet: {sheet}。支持: {sorted(_SUPPORTED_SHEETS)}")



# ═══════════════════════════════════════════════════════════════════════════════
# G7-18 多sheet导出（3区段→3 worksheet）
# ═══════════════════════════════════════════════════════════════════════════════

def _build_g7_18_multi_sheet_workbook(rows: list[dict], *, template_only: bool = False) -> Workbook:
    """G7-18 按3区段分sheet导出，每个区段一个worksheet。"""
    wb = Workbook()
    wb.remove(wb.active)  # type: ignore[arg-type]

    for seg_name, seg_headers, seg_keys in _G7_18_SEGMENTS:
        ws = wb.create_sheet(title=seg_name)
        # 标题行
        ws.append([f"G7-18 凭证检查 — {seg_name}"])
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
    ws_guide.append(["G7-18 长期股权投资凭证检查 编制说明"])
    ws_guide.append([])
    guidance_lines = [
        "19列拆为3区段Tab：凭证基础(7) / 核对检查(7) / 结论(5)。",
        "凭证基础：日期/凭证号/业务内容/对方科目/借方/贷方/附件。",
        "核对检查：支持性文件+6项核对（true/false或是/否）。",
        "结论：索引/是否异常/异常说明/风险等级/备注。",
        "核对1~6任一为否→自动标记为异常。",
        "借方贷方汇总差额≠0时前端红色告警。",
        "附件列支持上传后OCR自动识别。",
    ]
    for line in guidance_lines:
        ws_guide.append([line])
    ws_guide.column_dimensions["A"].width = 80
    return wb


def _parse_g7_18_import(content: bytes) -> tuple[list[dict], list[str]]:
    """解析G7-18导入文件，支持多sheet或单sheet宽表两种格式。"""
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    errors: list[str] = []
    rows_dict: dict[int, dict] = {}

    # 策略1: 多sheet格式（3区段分sheet）
    multi_sheet = len(wb.sheetnames) >= 3 and any("凭证基础" in s for s in wb.sheetnames)

    if multi_sheet:
        for seg_name, seg_headers, seg_keys in _G7_18_SEGMENTS:
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
        # 策略2: 单sheet宽表（19列合并）
        ws = wb.active
        if ws is None:
            wb.close()
            return [], ["xlsx文件中无活动工作表"]
        # 自动检测表头行
        header_row_idx = 1
        for r in range(1, 5):
            test_row = [str(c.value).strip() if c.value else "" for c in next(ws.iter_rows(min_row=r, max_row=r))]
            if "日期" in test_row or "凭证号" in test_row:
                header_row_idx = r
                break
        actual_headers = [
            str(c.value).strip() if c.value else ""
            for c in next(ws.iter_rows(min_row=header_row_idx, max_row=header_row_idx))
        ]
        if "凭证号" not in actual_headers and "日期" not in actual_headers:
            errors.append("无法识别表头，缺少'日期'或'凭证号'列")
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
                if h in _G7_18_ALL_HEADERS:
                    key_idx = _G7_18_ALL_HEADERS.index(h)
                    key = _G7_18_ALL_KEYS[key_idx]
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

@router.post("/api/workpapers/{wp_id}/g7-sub/export-template")
async def g7_sub_export_template(
    wp_id: str,
    sheet: str = Query(...),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出空模板：G7-8~G7-12(单sheet) / G7-18(3区段多sheet)。"""
    _validate_sheet(sheet)

    if sheet == "G7-18":
        wb = _build_g7_18_multi_sheet_workbook([], template_only=True)
        return workbook_to_response(wb, "G7-18_凭证检查_模板.xlsx")
    else:
        spec = _SINGLE_SHEET_SPECS[sheet]
        wb = build_workbook_template(
            sheet,
            spec["headers"],
            title=spec.get("title"),
            guidance=spec.get("guidance"),
        )
        return workbook_to_response(wb, f"{sheet}_模板.xlsx")


@router.post("/api/workpapers/{wp_id}/g7-sub/export-data")
async def g7_sub_export_data(
    wp_id: str,
    sheet: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """导出数据：G7-8~G7-12(单sheet含数据) / G7-18(3区段多sheet含数据)。"""
    _validate_sheet(sheet)
    item_id = _ITEM_IDS[sheet]
    rows = await load_json_rows(db, wp_id, item_id, field="conclusion")

    if sheet == "G7-18":
        wb = _build_g7_18_multi_sheet_workbook(rows, template_only=False)
        return workbook_to_response(wb, "G7-18_凭证检查_数据.xlsx")
    else:
        spec = _SINGLE_SHEET_SPECS[sheet]
        wb = build_workbook_template(
            sheet,
            spec["headers"],
            title=spec.get("title"),
            guidance=spec.get("guidance"),
        )
        ws = wb[sheet]
        for d in rows:
            ws.append(export_row_by_keys(d, spec["field_keys"]))
        return workbook_to_response(wb, f"{sheet}_数据.xlsx")


@router.post("/api/workpapers/{wp_id}/g7-sub/import-data")
async def g7_sub_import_data(
    wp_id: str,
    sheet: str = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """导入数据：G7-8~G7-12(单sheet) / G7-18(支持多sheet或宽表)。"""
    _validate_sheet(sheet)
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(400, "请上传 .xlsx 格式文件")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "文件大小不能超过10MB")

    item_id = _ITEM_IDS[sheet]
    errors: list[str] = []
    rows: list[dict] = []

    if sheet == "G7-18":
        rows, errors = _parse_g7_18_import(content)
    else:
        spec = _SINGLE_SHEET_SPECS[sheet]
        try:
            actual, raw = parse_upload_xlsx(content, spec["headers"], header_row=2)
        except ValueError as e:
            return {"ok": False, "errors": [str(e)], "imported_count": 0}
        except Exception:
            raise HTTPException(400, "无法解析xlsx文件")
        keys = spec["field_keys"]
        for i, r in enumerate(raw, start=1):
            if i > ROW_LIMIT:
                errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
                break
            rows.append(parse_row_by_headers(r, actual, keys))

    if errors and not rows:
        return {"ok": False, "errors": errors, "imported_count": 0}

    await upsert_json_rows(db, wp_id, item_id, rows, field="conclusion")
    out: dict[str, Any] = {"ok": True, "imported_count": len(rows), "errors": errors}
    if len(rows) >= ROW_LIMIT:
        out["warning"] = f"数据行数超过{ROW_LIMIT}行限制，已截断"
    return out
