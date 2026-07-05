"""G11 投资收益 — 导入导出（G11-1 / G11-2 / G11-3 / G11-4 / G11-5 × 3 端点 = 15）."""

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

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User

from ._cycle_import_export_common import (
    ROW_LIMIT,
    build_workbook_template,
    export_row_by_keys,
    import_rows_generic,
    is_numeric_field_key,
    load_json_rows,
    parse_row_by_headers,
    parse_upload_xlsx,
    safe_float,
    safe_str,
    upsert_json_rows,
    workbook_to_response,
)

_G11_1_HEADERS = [
    "行键", "项目", "分组",
    "本期未审数", "本期调整", "上期未审数", "上期调整",
    "原因分析", "索引号",
]
_G11_1_KEYS = [
    "rowKey", "label", "group",
    "currentUnadjusted", "currentAdjustment", "priorUnadjusted", "priorAdjustment",
    "reasonAnalysis", "indexRef",
]

_G11_2_HEADERS = [
    "序号", "项目", "被投资单位",
    "本期未审数", "本期调整", "本期审定数", "本期占比",
    "上年未审数", "上期调整", "上年审定数", "上期占比",
    "变动额", "变动原因/索引号",
]
_G11_2_KEYS = [
    "seq", "itemName", "investeeName",
    "currentUnadjusted", "currentAdjustment", "currentAudited", "currentShare",
    "priorUnadjusted", "priorAdjustment", "priorAudited", "priorShare",
    "changeAmount", "reasonIndex",
]

_G11_3_HEADERS = [
    "分录类型", "日期", "摘要", "科目代码", "科目名称", "借方金额", "贷方金额", "编制人", "备注",
]
_G11_3_KEYS = [
    "entryType", "date", "summary", "accountCode", "accountName", "debitAmount", "creditAmount", "preparedBy", "remark",
]

_G11_4_HEADERS = [
    "项目名称", "本期发生额", "本期期初余额", "本期期末余额",
    "上期审定数", "上期期初余额", "上期期末余额", "异常说明",
]
_G11_4_KEYS = [
    "itemName", "currentIncome", "currentOpening", "currentClosing",
    "priorAudited", "priorOpening", "priorClosing", "abnormalNote",
]

_G11_5_SEGMENTS: list[tuple[str, list[str], list[str]]] = [
    ("凭证基础", ["序号", "日期", "凭证编号", "业务内容", "对方科目", "对方明细科目", "贷方金额", "附件"],
     ["seq", "voucherDate", "voucherNo", "businessContent", "counterAccount", "counterDetail", "creditAmount", "attachment"]),
    ("核对内容", ["序号", "支持性文件描述", "核对1完整", "核对2授权", "核对3金额正确", "核对4期间恰当", "核对5账务正确"],
     ["seq", "supportingDocDesc", "check1", "check2", "check3", "check4", "check5"]),
    ("结论", ["序号", "索引号", "是否异常", "异常说明", "风险等级", "备注", "来源"],
     ["seq", "indexNo", "isAbnormal", "abnormalDesc", "riskLevel", "remark", "source"]),
]

_G11_5_FLAT_HEADERS = [
    "序号", "日期", "凭证编号", "业务内容", "对方科目", "对方明细科目", "贷方金额", "附件",
    "支持性文件描述", "核对1完整", "核对2授权", "核对3金额正确", "核对4期间恰当", "核对5账务正确",
    "索引号", "是否异常", "异常说明", "风险等级", "备注", "来源",
]
_G11_5_FLAT_KEYS = [
    "seq", "voucherDate", "voucherNo", "businessContent", "counterAccount", "counterDetail", "creditAmount", "attachment",
    "supportingDocDesc", "check1", "check2", "check3", "check4", "check5",
    "indexNo", "isAbnormal", "abnormalDesc", "riskLevel", "remark", "source",
]

_G11_SPECS: dict[str, dict[str, Any]] = {
    "G11-1": {
        "item_id": "G11-adj-rows",
        "title": "G11-1 投资收益审定表",
        "headers": _G11_1_HEADERS,
        "field_keys": _G11_1_KEYS,
        "guidance": [
            "G11-1 审定表 编制说明",
            "",
            "审定数=未审+调整；导入后由前端重算变动额/变动率。",
        ],
        "storage_shape": "object",
    },
    "G11-2": {
        "item_id": "G11-detail-rows",
        "title": "G11-2 投资收益明细分析表",
        "headers": _G11_2_HEADERS,
        "field_keys": _G11_2_KEYS,
        "guidance": [
            "G11-2 明细分析表 编制说明",
            "",
            "审定数=未审+调整；占比导入后由前端按合计重算。",
        ],
    },
    "G11-3": {
        "item_id": "G11-aje-rows",
        "title": "G11-3 调整分录汇总",
        "headers": _G11_3_HEADERS,
        "field_keys": _G11_3_KEYS,
        "guidance": ["G11-3 调整分录", "", "分录类型 AJE/RJE；借贷须平衡。"],
    },
    "G11-4": {
        "item_id": "G11-return-rate-rows",
        "title": "G11-4 收益率分析表",
        "headers": _G11_4_HEADERS,
        "field_keys": _G11_4_KEYS,
        "guidance": [
            "G11-4 收益率分析",
            "",
            "平均投资=(期初+期末)/2；收益率=发生额/平均投资。",
        ],
    },
    "G11-5": {
        "item_id": "G11-voucher-rows",
        "title": "G11-5 凭证检查表",
        "headers": _G11_5_FLAT_HEADERS,
        "field_keys": _G11_5_FLAT_KEYS,
        "guidance": [
            "G11-5 凭证检查",
            "",
            "导出含3区段工作表；导入支持宽表或3区段。核对列填 ✓ 或 ✗。",
        ],
    },
}

_SUPPORTED = set(_G11_SPECS.keys())
router = APIRouter(tags=["g11-import-export"])
_HEADER_ROW = 2


def _parse_g11_1_row(row: tuple, headers: list[str]) -> dict[str, Any]:
    values = list(row) + [None] * max(0, len(headers) - len(row))
    out: dict[str, Any] = {}
    for h, key in zip(_G11_1_HEADERS, _G11_1_KEYS):
        if h not in headers:
            continue
        idx = headers.index(h)
        raw = values[idx] if idx < len(values) else None
        if is_numeric_field_key(key):
            out[key] = safe_float(raw)
        else:
            out[key] = safe_str(raw)
    return out


def _rows_to_g11_1_store(rows: list[dict]) -> dict[str, dict]:
    store: dict[str, dict] = {}
    for row in rows:
        key = safe_str(row.get("rowKey"))
        if not key:
            continue
        store[key] = {
            "currentUnadjusted": safe_float(row.get("currentUnadjusted")),
            "currentAdjustment": safe_float(row.get("currentAdjustment")),
            "priorUnadjusted": safe_float(row.get("priorUnadjusted")),
            "priorAdjustment": safe_float(row.get("priorAdjustment")),
            "reasonAnalysis": safe_str(row.get("reasonAnalysis")),
            "indexRef": safe_str(row.get("indexRef")),
            "label": safe_str(row.get("label")),
            "group": safe_str(row.get("group")),
        }
    return store


async def _load_g11_adj_remark(db: AsyncSession, wp_id: str) -> dict[str, dict]:
    result = await db.execute(
        sa.text(
            "SELECT remark FROM checklist_responses WHERE wp_id = :wp_id AND item_id = :iid LIMIT 1"
        ),
        {"wp_id": wp_id, "iid": "G11-adj-rows"},
    )
    row = result.fetchone()
    if not row or not row.remark:
        return {}
    try:
        parsed = json.loads(row.remark)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list):
            return _rows_to_g11_1_store(parsed)
    except (json.JSONDecodeError, TypeError):
        pass
    return {}


async def _upsert_g11_adj_store(db: AsyncSession, wp_id: str, store: dict[str, dict]) -> None:
    proj = await db.execute(
        sa.text("SELECT project_id FROM working_paper WHERE id = :wp_id AND is_deleted = false"),
        {"wp_id": wp_id},
    )
    project_id = proj.scalar_one_or_none()
    if not project_id:
        raise ValueError(f"working_paper not found: {wp_id}")
    await db.execute(
        sa.text("""
            INSERT INTO checklist_responses (id, project_id, wp_id, item_id, remark, updated_at, created_at)
            VALUES (:id, :project_id, :wp_id, :item_id, :payload, NOW(), NOW())
            ON CONFLICT (wp_id, item_id)
            DO UPDATE SET remark = :payload, updated_at = NOW()
        """),
        {
            "id": str(uuid4()),
            "project_id": str(project_id),
            "wp_id": wp_id,
            "item_id": "G11-adj-rows",
            "payload": json.dumps(store, ensure_ascii=False),
        },
    )
    await db.commit()


def _export_g11_1_rows(store: dict[str, dict]) -> list[list[Any]]:
    out: list[list[Any]] = []
    for key, fields in store.items():
        if not isinstance(fields, dict):
            continue
        row = {
            "rowKey": key,
            "label": fields.get("label") or key,
            "group": fields.get("group") or "",
            **fields,
        }
        out.append(export_row_by_keys(row, _G11_1_KEYS))
    return out


def _validate(sheet: str) -> None:
    if sheet not in _SUPPORTED:
        raise HTTPException(400, f"不支持的sheet: {sheet}。支持: {sorted(_SUPPORTED)}")


def _parse_check_val(raw: Any) -> str:
    s = safe_str(raw).lower()
    if s in {"✓", "是", "y", "yes", "true", "1"}:
        return "✓"
    if s in {"✗", "否", "n", "no", "false", "0"}:
        return "✗"
    return safe_str(raw) or "✓"


def _parse_g11_5_row(row: tuple, headers: list[str]) -> dict[str, Any]:
    values = list(row) + [None] * max(0, len(headers) - len(row))
    out: dict[str, Any] = {"id": str(uuid4())}
    check_keys = {"check1", "check2", "check3", "check4", "check5"}
    for h, key in zip(_G11_5_FLAT_HEADERS, _G11_5_FLAT_KEYS):
        if h not in headers:
            continue
        idx = headers.index(h)
        raw = values[idx] if idx < len(values) else None
        if key in check_keys:
            out[key] = _parse_check_val(raw)
        elif key == "isAbnormal":
            out[key] = safe_str(raw) in {"是", "✓", "true", "1", "Y", "y"}
        elif is_numeric_field_key(key):
            out[key] = safe_float(raw)
        else:
            out[key] = safe_str(raw)
    return out


def _build_g11_5_workbook(rows: list[dict], *, template_only: bool = False) -> Workbook:
    wb = Workbook()
    wb.remove(wb.active)
    for seg_name, seg_headers, seg_keys in _G11_5_SEGMENTS:
        ws = wb.create_sheet(title=seg_name)
        ws.append([f"G11-5 凭证检查 — {seg_name}"])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(seg_headers), 1))
        ws["A1"].font = Font(bold=True, size=12)
        ws.append(seg_headers)
        ws.freeze_panes = "A3"
        for col_idx in range(1, len(seg_headers) + 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = 14
        if not template_only:
            for i, row_data in enumerate(rows, start=1):
                merged = {**row_data, "seq": row_data.get("seq", i)}
                row_out = export_row_by_keys(merged, seg_keys)
                if seg_name == "核对内容":
                    for j, k in enumerate(seg_keys):
                        if k.startswith("check") and isinstance(row_out[j], bool):
                            row_out[j] = "✓" if row_out[j] else "✗"
                if seg_name == "结论" and "isAbnormal" in seg_keys:
                    idx = seg_keys.index("isAbnormal")
                    val = merged.get("isAbnormal")
                    row_out[idx] = "是" if val in (True, "是", "✓") else "否"
                ws.append(row_out)
    ws_guide = wb.create_sheet("编制说明")
    for line in _G11_SPECS["G11-5"]["guidance"]:
        ws_guide.append([line])
    ws_guide.column_dimensions["A"].width = 80
    return wb


def _parse_g11_5_upload(content: bytes) -> tuple[list[dict], list[str]]:
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    errors: list[str] = []
    rows_dict: dict[int, dict] = {}

    if any(seg in n for n in wb.sheetnames for seg in ("凭证基础", "核对内容", "结论")):
        for seg_name, seg_headers, seg_keys in _G11_5_SEGMENTS:
            ws = next((wb[n] for n in wb.sheetnames if seg_name in n), None)
            if ws is None:
                errors.append(f"缺少工作表: {seg_name}")
                continue
            for row_idx, row in enumerate(ws.iter_rows(min_row=3, values_only=True)):
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
                    if key in {"check1", "check2", "check3", "check4", "check5"}:
                        rows_dict[row_idx][key] = _parse_check_val(raw)
                    elif key == "isAbnormal":
                        rows_dict[row_idx][key] = safe_str(raw) in {"是", "✓", "true", "1"}
                    elif is_numeric_field_key(key):
                        rows_dict[row_idx][key] = safe_float(raw)
                    else:
                        rows_dict[row_idx][key] = safe_str(raw)
        wb.close()
        return list(rows_dict.values()), errors

    actual, raw = parse_upload_xlsx(content, _G11_5_FLAT_HEADERS, header_row=_HEADER_ROW)
    rows, truncated = import_rows_generic(
        raw, actual, _G11_5_FLAT_KEYS,
        parse_fn=lambda r, h: _parse_g11_5_row(r, h),
    )
    wb.close()
    if truncated:
        errors.append(f"数据行超过{ROW_LIMIT}行限制，已截断")
    return rows, errors


@router.post("/api/workpapers/{wp_id}/g11/export-template")
async def export_template(
    wp_id: str,
    sheet: str = Query(...),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _validate(sheet)
    sp = _G11_SPECS[sheet]
    if sheet == "G11-5":
        wb = _build_g11_5_workbook([], template_only=True)
        return workbook_to_response(wb, "G11-5_模板.xlsx")
    wb = build_workbook_template(
        sheet, sp["headers"], title=sp.get("title"), guidance=sp.get("guidance"),
    )
    return workbook_to_response(wb, f"{sheet}_模板.xlsx")


@router.post("/api/workpapers/{wp_id}/g11/export-data")
async def export_data(
    wp_id: str,
    sheet: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _validate(sheet)
    sp = _G11_SPECS[sheet]
    if sheet == "G11-1":
        store = await _load_g11_adj_remark(db, wp_id)
        wb = build_workbook_template(
            sheet, sp["headers"], title=sp.get("title"), guidance=sp.get("guidance"),
        )
        ws = wb[sheet]
        for row_vals in _export_g11_1_rows(store):
            ws.append(row_vals)
        return workbook_to_response(wb, f"{sheet}_数据.xlsx")
    if sheet == "G11-5":
        item_id = sp["item_id"]
        rows = await load_json_rows(db, wp_id, item_id, field="remark")
        wb = _build_g11_5_workbook(rows, template_only=False)
        return workbook_to_response(wb, "G11-5_数据.xlsx")
    item_id = sp["item_id"]
    rows = await load_json_rows(db, wp_id, item_id, field="remark")
    wb = build_workbook_template(
        sheet, sp["headers"], title=sp.get("title"), guidance=sp.get("guidance"),
    )
    ws = wb[sheet]
    for d in rows:
        ws.append(export_row_by_keys(d, sp["field_keys"]))
    return workbook_to_response(wb, f"{sheet}_数据.xlsx")


@router.post("/api/workpapers/{wp_id}/g11/import-data")
async def import_data(
    wp_id: str,
    sheet: str = Query(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _validate(sheet)
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(400, "请上传 .xlsx 格式文件")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "文件大小不能超过10MB")

    sp = _G11_SPECS[sheet]
    if sheet == "G11-1":
        try:
            actual, raw = parse_upload_xlsx(content, sp["headers"], header_row=_HEADER_ROW)
        except ValueError as e:
            return {"ok": False, "errors": [str(e)], "imported_count": 0}
        parsed_rows: list[dict] = []
        for row_idx, row in enumerate(raw):
            if row_idx >= ROW_LIMIT:
                break
            parsed_rows.append(_parse_g11_1_row(row, actual))
        store = _rows_to_g11_1_store(parsed_rows)
        await _upsert_g11_adj_store(db, wp_id, store)
        return {"ok": True, "imported_count": len(store), "errors": []}

    if sheet == "G11-5":
        rows, errors = _parse_g11_5_upload(content)
        if errors and not rows:
            return {"ok": False, "errors": errors, "imported_count": 0}
        await upsert_json_rows(db, wp_id, sp["item_id"], rows, field="remark")
        return {"ok": True, "imported_count": len(rows), "errors": errors}

    try:
        actual, raw = parse_upload_xlsx(content, sp["headers"], header_row=_HEADER_ROW)
    except ValueError as e:
        return {"ok": False, "errors": [str(e)], "imported_count": 0}
    keys = sp["field_keys"]
    rows, truncated = import_rows_generic(
        raw, actual, keys, parse_fn=lambda r, h: parse_row_by_headers(r, h, keys),
    )
    await upsert_json_rows(db, wp_id, sp["item_id"], rows, field="remark")
    out: dict[str, Any] = {"ok": True, "imported_count": len(rows), "errors": []}
    if truncated:
        out["warning"] = f"数据行数超过{ROW_LIMIT}行限制，已截断"
    return out
