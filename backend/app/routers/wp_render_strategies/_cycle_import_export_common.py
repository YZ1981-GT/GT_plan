"""循环底稿导入导出 — 通用工具（D4 模式）."""

from __future__ import annotations

import io
import json
import re
from typing import Any, Callable
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

ROW_LIMIT = 500

_NUMERIC_KEY_RE = re.compile(r"^m\d+$")


def is_numeric_field_key(key: str) -> bool:
    if key in {"seq", "term", "days", "rate"}:
        return True
    if _NUMERIC_KEY_RE.match(key):
        return True
    if key.endswith(("Amt", "Qty", "Balance", "Total", "Rate", "Days", "Coef", "Share", "Pct")):
        return True
    # G1 交易性金融资产等强数值语义后缀（避免 sppiResult 之类枚举被误判，故不含 Result）
    if key.endswith(("Quantity", "Cost", "Value", "Gain", "Income", "Price", "Diff", "Fee")):
        return True
    if "Amount" in key or "Balance" in key:
        return True
    # G1 专属数值字段（后缀无法覆盖：公允变动/调整分录/审定等）
    if key in {
        "quantity", "initialCost", "unitFairValue", "fairValueChange", "cumulativeFVChange",
        "fvChangeInPL", "disposalProceeds", "unadjusted", "aje", "rje", "adjusted", "variance",
        "debit", "credit", "dividendPerShare", "dividendIncome", "margin", "notionalAmount",
        "quoteValue", "bookValue", "marketValue", "countDayQuantity", "countDayAmount",
    }:
        return True
    return key in {
        "faceValue", "termDays", "overdueDays", "concentration", "debitAmount", "creditAmount",
        "debit", "credit", "increase", "decrease", "interest", "accruedInterest", "bookInterest",
        "variance", "openingQty", "openingAmt", "increaseQty", "increaseAmt", "decreaseQty",
        "decreaseAmt", "agingLt1", "aging1to2", "aging2to3", "agingGt3", "expectedDays",
        "payableInterest", "openingAdjusted", "closingBalance", "agingTotal", "postPaymentAmt",
        "auditedBalance", "auditedAgingLt1", "auditedAging1to2", "auditedAging2to3", "auditedAgingGt3",
        "h1Total", "h1Share", "h1Avg", "h2Total", "yearTotal", "priorTotal", "changeAmt", "changeRate",
        "volCoef", "currentAmt", "priorAmt", "changeAmount", "changeRatePct", "expectedDiff",
        "hangDays", "hangAmount", "qtySold", "qtyCost", "qtyDiff", "qtyDiffRate", "openingStock",
        "production", "purchase", "availableQty", "closingStock", "theoreticalQty", "theoreticalDiff",
        "amount", "adjustAmount", "noteAmount", "discountAmount", "openingBalance", "sharePct",
        "currentRevenue", "currentCost", "currentGross", "currentMargin", "priorRevenue", "priorCost",
        "priorGross", "priorMargin", "revenueChange", "revenueChangeRate", "costChange", "costChangeRate",
        "marginChange", "relatedRevenue", "costRate",
        # G14 信用减值损失明细
        "currentUnadjusted", "currentAdjustment", "openingProvision", "currentProvision",
        "currentReversal", "currentWriteoff", "closingProvision",
        # G12 净敞口套期收益
        "instrumentOpeningFV", "instrumentClosingFV", "instrumentFVChange",
        "itemOpeningFV", "itemClosingFV", "itemFVChange",
        "hedgeRatio", "profitLossAmount", "ineffectiveness",
        "priorUnadjusted", "priorAdjustment",
        # G11 投资收益
        "currentIncome", "currentOpening", "currentClosing", "priorOpening", "priorClosing",
        "creditAmount",
    }


def safe_float(val: Any) -> float:
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def safe_str(val: Any) -> str:
    return "" if val is None else str(val).strip()


def col_val(row: tuple, headers: list[str], name: str) -> Any:
    try:
        idx = headers.index(name)
        return row[idx] if idx < len(row) else None
    except ValueError:
        return None


def parse_row_by_headers(row: tuple, headers: list[str], field_keys: list[str]) -> dict[str, Any]:
    values = list(row) + [None] * max(0, len(headers) - len(row))
    out: dict[str, Any] = {"id": str(uuid4())}
    for h, key in zip(headers, field_keys):
        idx = headers.index(h)
        raw = values[idx] if idx < len(values) else None
        if is_numeric_field_key(key):
            out[key] = safe_float(raw)
        else:
            out[key] = safe_str(raw)
    return out


def export_row_by_keys(data: dict, field_keys: list[str]) -> list:
    row: list[Any] = []
    for key in field_keys:
        val = data.get(key)
        if isinstance(val, float) or isinstance(val, int):
            row.append(val)
        elif val is None:
            row.append("")
        else:
            row.append(val)
    return row


async def load_json_rows(
    db: AsyncSession,
    wp_id: str,
    item_id: str,
    field: str = "conclusion",
) -> list[dict]:
    result = await db.execute(
        sa.text(f"SELECT {field} FROM checklist_responses WHERE wp_id = :wp_id AND item_id = :iid LIMIT 1"),
        {"wp_id": wp_id, "iid": item_id},
    )
    row = result.fetchone()
    if not row or not getattr(row, field, None):
        return []
    try:
        parsed = json.loads(getattr(row, field))
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


async def upsert_json_rows(
    db: AsyncSession,
    wp_id: str,
    item_id: str,
    rows_data: list[dict],
    field: str = "conclusion",
) -> None:
    proj = await db.execute(
        sa.text(
            "SELECT project_id FROM working_paper WHERE id = :wp_id AND is_deleted = false"
        ),
        {"wp_id": wp_id},
    )
    project_id = proj.scalar_one_or_none()
    if not project_id:
        raise ValueError(f"working_paper not found: {wp_id}")

    await db.execute(
        sa.text(f"""
            INSERT INTO checklist_responses (id, project_id, wp_id, item_id, {field}, updated_at, created_at)
            VALUES (:id, :project_id, :wp_id, :item_id, :payload, NOW(), NOW())
            ON CONFLICT (wp_id, item_id)
            DO UPDATE SET {field} = :payload, updated_at = NOW()
        """),
        {
            "id": str(uuid4()),
            "project_id": str(project_id),
            "wp_id": wp_id,
            "item_id": item_id,
            "payload": json.dumps(rows_data, ensure_ascii=False),
        },
    )
    await db.commit()


def build_workbook_template(
    sheet_code: str,
    headers: list[str],
    *,
    title: str | None = None,
    subtitle: str | None = None,
    guidance: list[str] | None = None,
    prefill_rows: list[list[Any]] | None = None,
) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_code
    header_row = 1
    if title:
        ws.append([title])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(headers), 1))
        ws["A1"].font = Font(bold=True, size=12)
        header_row += 1
    if subtitle:
        ws.append([subtitle])
        header_row += 1
    ws.append(headers)
    ws.freeze_panes = f"A{header_row + 1}"
    for col_idx in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(col_idx)].width = 14
    if prefill_rows:
        for r in prefill_rows:
            ws.append(r)
    if guidance:
        ws_guide = wb.create_sheet("编制说明")
        ws_guide.append(["编制说明"])
        ws_guide.append([])
        for line in guidance:
            ws_guide.append([line])
        ws_guide.column_dimensions["A"].width = 80
    return wb


def workbook_to_response(wb: Workbook, filename: str) -> StreamingResponse:
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    from urllib.parse import quote
    fn = quote(filename)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{fn}"},
    )


def parse_upload_xlsx(content: bytes, expected_headers: list[str], header_row: int = 1) -> tuple[list[str], list[tuple]]:
    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    if ws is None:
        wb.close()
        raise ValueError("xlsx文件中无活动工作表")
    actual = [
        str(c.value).strip() if c.value else ""
        for c in next(ws.iter_rows(min_row=header_row, max_row=header_row))
    ]
    missing = [h for h in expected_headers if h not in actual]
    if missing:
        wb.close()
        raise ValueError(f"缺少列: {', '.join(missing)}")
    rows: list[tuple] = []
    for row in ws.iter_rows(min_row=header_row + 1, values_only=True):
        if all(v is None for v in row):
            continue
        rows.append(row)
    wb.close()
    return actual, rows


def import_rows_generic(
    rows: list[tuple],
    headers: list[str],
    field_keys: list[str],
    parse_fn: Callable[[tuple, list[str]], dict] | None = None,
) -> tuple[list[dict], bool]:
    parse = parse_fn or (lambda r, h: parse_row_by_headers(r, h, field_keys))
    out: list[dict] = []
    truncated = False
    for i, row in enumerate(rows, start=1):
        if i > ROW_LIMIT:
            truncated = True
            break
        out.append(parse(row, headers))
    return out, truncated


def create_cycle_import_export_router(
    *,
    tag: str,
    api_prefix: str,
    specs: dict[str, dict[str, Any]],
    storage_field: str = "conclusion",
    header_row: int = 2,
) -> APIRouter:
    """根据 sheet 规格表生成三端点导入导出 router（D4 模式）."""
    router = APIRouter(tags=[tag])
    supported = set(specs.keys())

    def _validate(sheet: str) -> None:
        if sheet not in supported:
            raise HTTPException(400, f"不支持的sheet: {sheet}。支持: {sorted(supported)}")

    def _spec(sheet: str) -> dict[str, Any]:
        return specs[sheet]

    @router.post(f"/api/workpapers/{{wp_id}}/{api_prefix}/export-template")
    async def export_template(
        wp_id: str,
        sheet: str = Query(...),
        current_user: User = Depends(get_current_user),
    ) -> StreamingResponse:
        _validate(sheet)
        sp = _spec(sheet)
        wb = build_workbook_template(
            sheet, sp["headers"], title=sp.get("title"), subtitle=sp.get("subtitle"), guidance=sp.get("guidance"),
        )
        return workbook_to_response(wb, f"{sheet}_模板.xlsx")

    @router.post(f"/api/workpapers/{{wp_id}}/{api_prefix}/export-data")
    async def export_data(
        wp_id: str,
        sheet: str = Query(...),
        db: AsyncSession = Depends(get_db),
        current_user: User = Depends(get_current_user),
    ) -> StreamingResponse:
        _validate(sheet)
        sp = _spec(sheet)
        item_id = sp.get("item_id", f"{sheet}-rows")
        rows = await load_json_rows(db, wp_id, item_id, field=storage_field)
        wb = build_workbook_template(
            sheet, sp["headers"], title=sp.get("title"), subtitle=sp.get("subtitle"), guidance=sp.get("guidance"),
        )
        ws = wb[sheet]
        keys = sp["field_keys"]
        for d in rows:
            ws.append(export_row_by_keys(d, keys))
        return workbook_to_response(wb, f"{sheet}_数据.xlsx")

    @router.post(f"/api/workpapers/{{wp_id}}/{api_prefix}/import-data")
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
        sp = _spec(sheet)
        hr = sp.get("header_row", header_row)
        try:
            actual, raw = parse_upload_xlsx(content, sp["headers"], header_row=hr)
        except ValueError as e:
            return {"ok": False, "errors": [str(e)], "imported_count": 0}
        except Exception:
            raise HTTPException(400, "无法解析xlsx文件")
        keys = sp["field_keys"]
        rows, truncated = import_rows_generic(
            raw, actual, keys, parse_fn=lambda r, h: parse_row_by_headers(r, h, keys),
        )
        item_id = sp.get("item_id", f"{sheet}-rows")
        await upsert_json_rows(db, wp_id, item_id, rows, field=storage_field)
        out: dict[str, Any] = {"ok": True, "imported_count": len(rows), "errors": []}
        if truncated:
            out["warning"] = f"数据行数超过{ROW_LIMIT}行限制，已截断"
        return out

    return router

