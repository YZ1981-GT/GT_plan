"""G8 其他权益工具投资 — 导入导出（G8-2 / G8-3 / G8-4 / G8-6 × 3 端点 = 12）.

G8-2(2区段) / G8-4(2区段) / G8-6(3区段) 宽表按 worksheet 分 sheet 导出。
"""

from __future__ import annotations

import io
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from sqlalchemy.ext.asyncio import AsyncSession

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

router = APIRouter(tags=["g8-import-export"])

# ═══════════════════════════════════════════════════════════════════════════════
# G8-2 明细表（24列 → 2区段）
# ═══════════════════════════════════════════════════════════════════════════════

_G8_2_SEG1_HEADERS = [
    "序号", "被投资单位名称", "投资比例", "期初余额", "期初调整数", "期初审定数",
    "本期增加", "本期减少", "公允价值变动", "期末余额", "期末调整数", "期末审定数",
    "指定为OCI的原因",
]
_G8_2_SEG1_KEYS = [
    "seq", "investeeName", "investmentRatio", "openingBalance", "openingAdjustment",
    "openingAdjusted", "increaseAmount", "decreaseAmount", "fvChangeAmount",
    "closingBalance", "closingAdjustment", "closingAdjusted", "designationReason",
]

_G8_2_SEG2_HEADERS = [
    "序号", "被投资单位名称", "OCI累计变动", "本期OCI变动", "OCI转入留存收益",
    "转入原因", "发函情况", "公允价值层次", "估值方法", "持股数量",
    "每股公允价值", "公允价值合计", "备注",
]
_G8_2_SEG2_KEYS = [
    "seq", "investeeName", "ociCumulativeChange", "ociCurrentChange", "ociToRetainedEarnings",
    "transferReason", "confirmationStatus", "fairValueLevel", "valuationMethod", "sharesHeld",
    "pricePerShare", "fairValueTotal", "remark",
]

_G8_2_SEGMENTS = [
    ("被投资单位基础", _G8_2_SEG1_HEADERS, _G8_2_SEG1_KEYS),
    ("公允价值+OCI", _G8_2_SEG2_HEADERS, _G8_2_SEG2_KEYS),
]

_G8_2_ALL_HEADERS = _G8_2_SEG1_HEADERS[2:] + _G8_2_SEG2_HEADERS[2:]
_G8_2_ALL_KEYS = _G8_2_SEG1_KEYS[2:] + _G8_2_SEG2_KEYS[2:]

# ═══════════════════════════════════════════════════════════════════════════════
# G8-3 调整分录
# ═══════════════════════════════════════════════════════════════════════════════

_G8_3_HEADERS = [
    "序号", "分录类型", "日期", "摘要", "科目代码", "科目名称", "借方", "贷方", "编制人", "备注",
]
_G8_3_KEYS = [
    "seq", "entryType", "date", "summary", "accountCode", "accountName",
    "debitAmount", "creditAmount", "preparedBy", "remark",
]

# ═══════════════════════════════════════════════════════════════════════════════
# G8-4 公允价值测试（19列 → 2区段）
# ═══════════════════════════════════════════════════════════════════════════════

_G8_4_SEG1_HEADERS = [
    "序号", "被投资单位名称", "初始投资日期", "期末未审-数量", "期末未审-单价", "期末未审-公允价值",
    "期末审定-数量", "期末审定-单价", "期末审定-公允价值", "差异", "公允价值层次",
]
_G8_4_SEG1_KEYS = [
    "seq", "investeeName", "initialInvestDate", "closingUnadjustedQty", "closingUnadjustedPrice",
    "closingUnadjustedFV", "closingAuditedQty", "closingAuditedPrice", "closingAuditedFV",
    "fairValueDiff", "fairValueLevel",
]

_G8_4_SEG2_HEADERS = [
    "序号", "被投资单位名称", "估值方法", "与上期一致", "公允价值来源机构",
    "输入值来源及调整", "估值技术", "不可观察输入值描述", "数值", "估值文件索引号",
]
_G8_4_SEG2_KEYS = [
    "seq", "investeeName", "valuationMethod", "methodConsistentWithPrior", "valuationSource",
    "inputSourceAndAdjustment", "valuationTechnique", "unobservableInputDesc",
    "unobservableInputValue", "valuationDocIndex",
]

_G8_4_SEGMENTS = [
    ("基础信息+审定", _G8_4_SEG1_HEADERS, _G8_4_SEG1_KEYS),
    ("估值详情", _G8_4_SEG2_HEADERS, _G8_4_SEG2_KEYS),
]

_G8_4_ALL_HEADERS = _G8_4_SEG1_HEADERS[2:] + _G8_4_SEG2_HEADERS[2:]
_G8_4_ALL_KEYS = _G8_4_SEG1_KEYS[2:] + _G8_4_SEG2_KEYS[2:]

# ═══════════════════════════════════════════════════════════════════════════════
# G8-6 凭证检查（18列 → 3区段）
# ═══════════════════════════════════════════════════════════════════════════════

_G8_6_SEG1_HEADERS = [
    "序号", "日期", "凭证编号", "业务内容", "对方科目", "借方金额", "贷方金额", "附件",
]
_G8_6_SEG1_KEYS = [
    "seq", "voucherDate", "voucherNo", "businessContent", "counterAccount",
    "debitAmount", "creditAmount", "attachment",
]

_G8_6_SEG2_HEADERS = [
    "序号", "支持性文件描述", "核对1-原始凭证完整", "核对2-授权批准", "核对3-账务处理正确",
    "核对4-公允价值计量正确", "核对5-OCI计入正确",
]
_G8_6_SEG2_KEYS = [
    "seq", "supportingDocDesc", "check1OriginalComplete", "check2Authorization",
    "check3Accounting", "check4FairValueCorrect", "check5OCICorrect",
]

_G8_6_SEG3_HEADERS = ["序号", "索引号", "是否异常", "异常说明", "风险等级", "备注"]
_G8_6_SEG3_KEYS = ["seq", "indexNo", "isAbnormal", "abnormalDesc", "riskLevel", "remark"]

_G8_6_SEGMENTS = [
    ("凭证基础", _G8_6_SEG1_HEADERS, _G8_6_SEG1_KEYS),
    ("核对内容", _G8_6_SEG2_HEADERS, _G8_6_SEG2_KEYS),
    ("结论", _G8_6_SEG3_HEADERS, _G8_6_SEG3_KEYS),
]

_G8_6_ALL_HEADERS = (
    _G8_6_SEG1_HEADERS[1:] + _G8_6_SEG2_HEADERS[1:] + _G8_6_SEG3_HEADERS[1:]
)
_G8_6_ALL_KEYS = _G8_6_SEG1_KEYS[1:] + _G8_6_SEG2_KEYS[1:] + _G8_6_SEG3_KEYS[1:]

# ═══════════════════════════════════════════════════════════════════════════════
# 规格表（供测试与路由校验）
# ═══════════════════════════════════════════════════════════════════════════════

_G8_SPECS: dict[str, dict[str, Any]] = {
    "G8-2": {
        "item_id": "G8-detail-rows",
        "title": "G8-2 明细表",
        "segments": _G8_2_SEGMENTS,
        "guidance": [
            "G8-2 明细表编制说明",
            "",
            "24列拆为2区段：被投资单位基础(13) / 公允价值+OCI(13)。",
            "期末余额=期初审定+增加-减少+公允价值变动；期末审定=期末余额+调整数。",
        ],
    },
    "G8-3": {
        "item_id": "G8-adjustment-rows",
        "title": "G8-3 调整分录",
        "headers": _G8_3_HEADERS,
        "field_keys": _G8_3_KEYS,
        "guidance": ["G8-3 调整分录编制说明", "", "借贷须平衡；AJE/RJE 汇总回写 G8-1。"],
    },
    "G8-4": {
        "item_id": "G8-fv-test-rows",
        "title": "G8-4 公允价值测试",
        "segments": _G8_4_SEGMENTS,
        "guidance": [
            "G8-4 公允价值测试编制说明",
            "",
            "19列拆为2区段：基础信息+审定(11) / 估值详情(10)。",
            "Level3 时估值技术与不可观察输入值必填。",
        ],
    },
    "G8-6": {
        "item_id": "G8-voucher-rows",
        "title": "G8-6 凭证检查",
        "segments": _G8_6_SEGMENTS,
        "guidance": [
            "G8-6 凭证检查编制说明",
            "",
            "18列拆为3区段：凭证基础(8) / 核对内容(7) / 结论(6)。",
            "核对项任一✗则是否异常=是。",
        ],
    },
}

_SUPPORTED_SHEETS = set(_G8_SPECS.keys())


def _validate_sheet(sheet: str) -> None:
    if sheet not in _SUPPORTED_SHEETS:
        raise HTTPException(400, f"不支持的sheet: {sheet}。支持: {sorted(_SUPPORTED_SHEETS)}")


def _bool_to_str(val: Any) -> str:
    if val is True or val == "true" or val == "True":
        return "是"
    if val is False or val == "false" or val == "False":
        return "否"
    return safe_str(val)


def _str_to_bool(val: Any) -> bool:
    if val is None:
        return False
    s = str(val).strip().lower()
    return s in ("是", "true", "1", "yes")


def _export_cell_value(key: str, val: Any) -> Any:
    if key in {
        "check1OriginalComplete", "check2Authorization", "check3Accounting",
        "check4FairValueCorrect", "check5OCICorrect", "isAbnormal",
    }:
        return _bool_to_str(val)
    if isinstance(val, float) or isinstance(val, int):
        return val
    if val is None:
        return ""
    return val


def _export_row(keys: list[str], data: dict) -> list[Any]:
    return [_export_cell_value(k, data.get(k)) for k in keys]


def _build_multi_segment_workbook(
    sheet_code: str,
    title: str,
    segments: list[tuple[str, list[str], list[str]]],
    rows: list[dict],
    *,
    template_only: bool = False,
    guidance: list[str] | None = None,
) -> Workbook:
    wb = Workbook()
    wb.remove(wb.active)
    for seg_name, seg_headers, seg_keys in segments:
        ws = wb.create_sheet(title=seg_name[:31])
        ws.append([f"{sheet_code} — {seg_name}"])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(seg_headers), 1))
        ws["A1"].font = Font(bold=True, size=12)
        ws.append(seg_headers)
        ws.freeze_panes = "A3"
        for col_idx in range(1, len(seg_headers) + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = 14
        if not template_only:
            for row_data in rows:
                ws.append(_export_row(seg_keys, row_data))
    if guidance:
        ws_guide = wb.create_sheet("编制说明")
        ws_guide.append([title])
        ws_guide.append([])
        for line in guidance:
            ws_guide.append([line])
        ws_guide.column_dimensions["A"].width = 80
    return wb


def _parse_multi_segment_import(
    content: bytes,
    segments: list[tuple[str, list[str], list[str]]],
    all_headers: list[str],
    all_keys: list[str],
    *,
    match_key: str = "被投资单位名称",
) -> tuple[list[dict], list[str]]:
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    errors: list[str] = []
    rows_dict: dict[int, dict] = {}

    multi_sheet = len(wb.sheetnames) >= len(segments) and any(
        seg[0] in name for seg in segments for name in wb.sheetnames
    )

    if multi_sheet:
        for seg_name, seg_headers, seg_keys in segments:
            ws = None
            for name in wb.sheetnames:
                if seg_name in name:
                    ws = wb[name]
                    break
            if ws is None:
                errors.append(f"缺少工作表: {seg_name}")
                continue
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
                    rows_dict[row_idx] = {"id": str(uuid4()), "seq": row_idx + 1}
                values = list(row) + [None] * max(0, len(seg_headers) - len(row))
                for col_i, key in enumerate(seg_keys):
                    raw = values[col_i] if col_i < len(values) else None
                    if key in {
                        "check1OriginalComplete", "check2Authorization", "check3Accounting",
                        "check4FairValueCorrect", "check5OCICorrect", "isAbnormal",
                    }:
                        rows_dict[row_idx][key] = _str_to_bool(raw)
                    elif is_numeric_field_key(key):
                        rows_dict[row_idx][key] = safe_float(raw)
                    else:
                        rows_dict[row_idx][key] = safe_str(raw)
    else:
        ws = wb.active
        if ws is None:
            wb.close()
            return [], ["xlsx文件中无活动工作表"]
        header_row_idx = 1
        for r in range(1, 5):
            test_row = [
                str(c.value).strip() if c.value else ""
                for c in next(ws.iter_rows(min_row=r, max_row=r))
            ]
            if match_key in test_row or "序号" in test_row:
                header_row_idx = r
                break
        actual_headers = [
            str(c.value).strip() if c.value else ""
            for c in next(ws.iter_rows(min_row=header_row_idx, max_row=header_row_idx))
        ]
        if "序号" not in actual_headers and match_key not in actual_headers:
            errors.append(f"无法识别表头，缺少'{match_key}'或'序号'列")
            wb.close()
            return [], errors
        for row_idx, row in enumerate(ws.iter_rows(min_row=header_row_idx + 1, values_only=True)):
            if all(v is None for v in row):
                continue
            if row_idx >= ROW_LIMIT:
                errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
                break
            parsed: dict[str, Any] = {"id": str(uuid4()), "seq": row_idx + 1}
            values = list(row) + [None] * max(0, len(actual_headers) - len(row))
            for col_i, h in enumerate(actual_headers):
                if h in all_headers:
                    key_idx = all_headers.index(h)
                    key = all_keys[key_idx]
                    raw = values[col_i] if col_i < len(values) else None
                    if key in {
                        "check1OriginalComplete", "check2Authorization", "check3Accounting",
                        "check4FairValueCorrect", "check5OCICorrect", "isAbnormal",
                    }:
                        parsed[key] = _str_to_bool(raw)
                    elif is_numeric_field_key(key):
                        parsed[key] = safe_float(raw)
                    else:
                        parsed[key] = safe_str(raw)
            rows_dict[row_idx] = parsed

    wb.close()
    return list(rows_dict.values()), errors


@router.post("/api/workpapers/{wp_id}/g8/export-template")
async def g8_export_template(
    wp_id: str,
    sheet: str = Query(...),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _validate_sheet(sheet)
    sp = _G8_SPECS[sheet]

    if sheet == "G8-3":
        wb = build_workbook_template(
            sheet,
            sp["headers"],
            title=sp["title"],
            guidance=sp.get("guidance"),
        )
        return workbook_to_response(wb, f"{sheet}_模板.xlsx")

    wb = _build_multi_segment_workbook(
        sheet,
        sp["title"],
        sp["segments"],
        [],
        template_only=True,
        guidance=sp.get("guidance"),
    )
    return workbook_to_response(wb, f"{sheet}_模板.xlsx")


@router.post("/api/workpapers/{wp_id}/g8/export-data")
async def g8_export_data(
    wp_id: str,
    sheet: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _validate_sheet(sheet)
    sp = _G8_SPECS[sheet]
    rows = await load_json_rows(db, wp_id, sp["item_id"], field="remark")

    if sheet == "G8-3":
        wb = build_workbook_template(sheet, sp["headers"], title=sp["title"], guidance=sp.get("guidance"))
        ws = wb[sheet]
        for d in rows:
            ws.append(export_row_by_keys(d, sp["field_keys"]))
        return workbook_to_response(wb, f"{sheet}_数据.xlsx")

    wb = _build_multi_segment_workbook(
        sheet,
        sp["title"],
        sp["segments"],
        rows,
        template_only=False,
        guidance=sp.get("guidance"),
    )
    return workbook_to_response(wb, f"{sheet}_数据.xlsx")


@router.post("/api/workpapers/{wp_id}/g8/import-data")
async def g8_import_data(
    wp_id: str,
    sheet: str = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _validate_sheet(sheet)
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(400, "请上传 .xlsx 格式文件")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "文件大小不能超过10MB")

    sp = _G8_SPECS[sheet]
    errors: list[str] = []

    if sheet == "G8-3":
        try:
            actual, raw = parse_upload_xlsx(content, sp["headers"], header_row=2)
        except ValueError as e:
            return {"ok": False, "errors": [str(e)], "imported_count": 0}
        except Exception:
            raise HTTPException(400, "无法解析xlsx文件") from None
        keys = sp["field_keys"]
        rows = [parse_row_by_headers(r, actual, keys) for r in raw[:ROW_LIMIT]]
        if len(raw) > ROW_LIMIT:
            errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
    elif sheet == "G8-2":
        rows, errors = _parse_multi_segment_import(
            content, _G8_2_SEGMENTS, _G8_2_ALL_HEADERS, _G8_2_ALL_KEYS,
        )
    elif sheet == "G8-4":
        rows, errors = _parse_multi_segment_import(
            content, _G8_4_SEGMENTS, _G8_4_ALL_HEADERS, _G8_4_ALL_KEYS,
        )
    else:  # G8-6
        rows, errors = _parse_multi_segment_import(
            content,
            _G8_6_SEGMENTS,
            _G8_6_ALL_HEADERS,
            _G8_6_ALL_KEYS,
            match_key="凭证编号",
        )

    if errors and not rows:
        return {"ok": False, "errors": errors, "imported_count": 0}

    await upsert_json_rows(db, wp_id, sp["item_id"], rows, field="remark")
    out: dict[str, Any] = {"ok": True, "imported_count": len(rows), "errors": errors}
    if errors:
        out["warning"] = "; ".join(errors)
    return out
