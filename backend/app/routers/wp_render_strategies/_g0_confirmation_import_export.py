"""G0 投资循环函证 — 导入导出（3 端点）.

与 F0 pattern 差异：G0-3S(证券差异)/G0-6(替代程序) 是 confirmation 精细组件，
数据持久化在 working_paper.parsed_data.html_data[sheet]（非 checklist_responses），
因此不能复用 _cycle_import_export_common 的 checklist 存储工厂，需自建 parsed_data 读写。

端点（RFC5987 中文文件名由 workbook_to_response 处理 → filename*=UTF-8''）：
- POST /api/workpapers/{wp_id}/g0/export-template?sheet=G0-3S|G0-6
- POST /api/workpapers/{wp_id}/g0/export-data?sheet=G0-3S|G0-6
- POST /api/workpapers/{wp_id}/g0/import-data?sheet=G0-3S|G0-6

导出结构：
- G0-3S：单 sheet（17 列证券差异明细）
- G0-6：4 区块分 4 个 sheet（①持仓证明/②股利收入/③处置收益/④公允价值佐证），
  每 sheet 首列「被函证单位」用于导入时按投资项目归组。
"""
from __future__ import annotations

import json
import logging
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

from ._cycle_import_export_common import safe_float, safe_str, workbook_to_response

logger = logging.getLogger(__name__)

router = APIRouter(tags=["g0-import-export"])

ROW_LIMIT = 500

# ── sheet 编码 → parsed_data.html_data 中的 sheet 名 ──────────────────────────
_SHEET_NAME_MAP: dict[str, str] = {
    "G0-3S": "函证差异核对表G0-3（证券投资）",
    "G0-6": "替代程序检查表G0-6",
}

# ── G0-3S 证券差异明细 17 列（header, field_key, 是否数值列）──────────────────
_G03S_COLUMNS: list[tuple[str, str, bool]] = [
    ("序号", "seq", True),
    ("证券名称", "security_name", False),
    ("证券代码", "security_code", False),
    ("证券类型", "security_type", False),
    ("回函持仓数量", "confirmed_qty", True),
    ("账面持仓数量", "booked_qty", True),
    ("数量差异", "qty_diff", True),
    ("回函单位公允价值", "confirmed_unit_fv", True),
    ("账面单位公允价值", "booked_unit_fv", True),
    ("公允价值差异", "fv_diff", True),
    ("回函总市值", "confirmed_market_value", True),
    ("账面总市值", "booked_market_value", True),
    ("市值差异", "market_value_diff", True),
    ("差异原因", "diff_reason", False),
    ("调节事项", "adjustment_note", False),
    ("核实结论", "verify_conclusion", False),
    ("备注", "remark", False),
]

# ── G0-6 四区块列定义（与前端 blockColumnConfigsG06.ts 对齐；首列被函证单位用于归组）─
_VOUCHER_COLS: list[tuple[str, str, bool]] = [
    ("日期", "voucher_date", False),
    ("凭证编号", "voucher_no", False),
    ("业务内容", "business_desc", False),
    ("对方科目", "counter_account", False),
    ("金额", "voucher_amount", True),
]

_G06_BLOCKS: dict[str, dict[str, Any]] = {
    "block1": {
        "sheet_title": "①持仓证明检查",
        "columns": [
            ("被函证单位", "_entity", False),
            ("序号", "seq", True),
            *_VOUCHER_COLS,
            ("对账单日期", "stmt_date", False),
            ("持仓品种", "holding_variety", False),
            ("数量", "holding_qty", True),
            ("市值", "market_value", True),
            ("托管确认函", "custody_confirm", False),
            ("确认日期", "custody_date", False),
            ("中登查询日", "csd_query_date", False),
            ("持仓一致性", "holding_consistent", False),
            ("索引号", "ref_index", False),
        ],
    },
    "block2": {
        "sheet_title": "②投资收益股利收入证据",
        "columns": [
            ("被函证单位", "_entity", False),
            ("序号", "seq", True),
            *_VOUCHER_COLS,
            ("分红公告日期", "dividend_announce_date", False),
            ("每股股利", "dividend_per_share", True),
            ("应收股利金额", "dividend_receivable", True),
            ("银行回单日期", "bank_receipt_date", False),
            ("到账金额", "received_amount", True),
            ("红利税扣缴", "dividend_tax", True),
            ("实收金额", "net_received", True),
            ("差异", "dividend_diff", True),
            ("索引号", "ref_index", False),
        ],
    },
    "block3": {
        "sheet_title": "③投资处置收益证据",
        "columns": [
            ("被函证单位", "_entity", False),
            ("序号", "seq", True),
            *_VOUCHER_COLS,
            ("交易确认单日期", "trade_confirm_date", False),
            ("卖出数量", "sell_qty", True),
            ("成交价", "trade_price", True),
            ("成交金额", "trade_amount", True),
            ("原始成本", "original_cost", True),
            ("处置损益", "disposal_gain", True),
            ("手续费", "fee", True),
            ("净收入", "net_income", True),
            ("银行到账", "bank_received", True),
            ("索引号", "ref_index", False),
        ],
    },
    "block4": {
        "sheet_title": "④公允价值佐证",
        "columns": [
            ("被函证单位", "_entity", False),
            ("序号", "seq", True),
            *_VOUCHER_COLS,
            ("报价来源", "quote_source", False),
            ("报价日期", "quote_date", False),
            ("报价值", "quote_value", True),
            ("估值模型", "valuation_model", False),
            ("估值假设", "valuation_assumption", False),
            ("Level层级", "fv_level", False),
            ("账面vs报价差异", "book_vs_quote_diff", True),
            ("合理性判断", "reasonableness", False),
            ("索引号", "ref_index", False),
        ],
    },
}

_G06_GUIDANCE = [
    "G0-6 投资循环替代程序 导入说明",
    "",
    "本工作簿含 4 个区块 sheet（持仓证明/股利收入/处置收益/公允价值佐证）。",
    "「被函证单位」列用于将行归入对应投资项目；同名单位的行会合并到同一项目下。",
    "处置损益、股利差异等公式列导入后由前端自动重算。",
]


def _validate_sheet(sheet: str) -> None:
    if sheet not in _SHEET_NAME_MAP:
        raise HTTPException(400, f"不支持的sheet: {sheet}。支持: {sorted(_SHEET_NAME_MAP)}")


async def _load_html_data(db: AsyncSession, wp_id: str, sheet_name: str) -> dict:
    """读取 parsed_data.html_data[sheet_name]。"""
    result = await db.execute(
        sa.text(
            "SELECT parsed_data FROM working_paper WHERE id = :wp_id AND is_deleted = false"
        ),
        {"wp_id": wp_id},
    )
    row = result.fetchone()
    if not row or not row.parsed_data:
        return {}
    parsed = row.parsed_data
    if isinstance(parsed, str):
        try:
            parsed = json.loads(parsed)
        except (json.JSONDecodeError, TypeError):
            return {}
    html_data = (parsed or {}).get("html_data", {}) if isinstance(parsed, dict) else {}
    sheet_data = html_data.get(sheet_name)
    return sheet_data if isinstance(sheet_data, dict) else {}


async def _save_html_data(db: AsyncSession, wp_id: str, sheet_name: str, payload: dict) -> None:
    """将 payload 写回 parsed_data.html_data[sheet_name]（只 flush 不 commit 由端点统一 commit）。"""
    result = await db.execute(
        sa.text(
            "SELECT parsed_data FROM working_paper WHERE id = :wp_id AND is_deleted = false"
        ),
        {"wp_id": wp_id},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(404, f"底稿不存在: {wp_id}")
    parsed = row.parsed_data or {}
    if isinstance(parsed, str):
        try:
            parsed = json.loads(parsed)
        except (json.JSONDecodeError, TypeError):
            parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}
    parsed.setdefault("html_data", {})
    parsed["html_data"][sheet_name] = payload
    await db.execute(
        sa.text(
            "UPDATE working_paper SET parsed_data = CAST(:pd AS jsonb), updated_at = NOW() "
            "WHERE id = :wp_id"
        ),
        {"pd": json.dumps(parsed, ensure_ascii=False), "wp_id": wp_id},
    )
    await db.commit()


# ── workbook 构建工具 ─────────────────────────────────────────────────────────

def _append_header_sheet(
    ws, columns: list[tuple[str, str, bool]], *, title: str | None = None
) -> int:
    """写标题 + 表头，返回表头所在行号。"""
    header_row = 1
    headers = [c[0] for c in columns]
    if title:
        ws.append([title])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(len(headers), 1))
        ws["A1"].font = Font(bold=True, size=12)
        header_row = 2
    ws.append(headers)
    for h in ws[header_row]:
        h.font = Font(bold=True)
    ws.freeze_panes = f"A{header_row + 1}"
    for idx in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(idx)].width = 14
    return header_row


def _add_guidance(wb: Workbook, lines: list[str]) -> None:
    ws = wb.create_sheet("编制说明")
    for line in lines:
        ws.append([line])
    ws.column_dimensions["A"].width = 80


def _build_g03s_workbook(rows: list[dict] | None) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = "G0-3证券差异核对"
    _append_header_sheet(ws, _G03S_COLUMNS, title="G0-3(证券) 函证差异核对表-证券投资")
    for d in rows or []:
        ws.append([d.get(key, "") if not is_num else safe_float(d.get(key)) for _, key, is_num in _G03S_COLUMNS])
    return wb


def _build_g06_workbook(companies: list[dict] | None) -> Workbook:
    wb = Workbook()
    wb.remove(wb.active)
    for block_key, cfg in _G06_BLOCKS.items():
        ws = wb.create_sheet(cfg["sheet_title"])
        columns = cfg["columns"]
        _append_header_sheet(ws, columns)
        for company in companies or []:
            entity = safe_str(company.get("entity_name"))
            for r in company.get(f"{block_key}_rows", []) or []:
                out_row = []
                for header, key, is_num in columns:
                    if key == "_entity":
                        out_row.append(entity)
                    elif is_num:
                        out_row.append(safe_float(r.get(key)))
                    else:
                        out_row.append(safe_str(r.get(key)))
                ws.append(out_row)
    _add_guidance(wb, _G06_GUIDANCE)
    return wb


# ── xlsx 解析工具 ─────────────────────────────────────────────────────────────

def _parse_sheet_rows(
    content: bytes, ws_title: str | None, columns: list[tuple[str, str, bool]], header_row: int
) -> list[dict]:
    """按列头解析指定 sheet 的数据行；ws_title=None 取活动 sheet。"""
    wb = load_workbook(content_io(content), read_only=True, data_only=True)
    try:
        ws = wb[ws_title] if ws_title and ws_title in wb.sheetnames else wb.active
        if ws is None:
            return []
        header_cells = next(ws.iter_rows(min_row=header_row, max_row=header_row))
        actual = [str(c.value).strip() if c.value is not None else "" for c in header_cells]
        expected = [c[0] for c in columns]
        missing = [h for h in expected if h not in actual]
        if missing:
            raise ValueError(f"sheet「{ws.title}」缺少列: {', '.join(missing)}")
        rows: list[dict] = []
        for values in ws.iter_rows(min_row=header_row + 1, values_only=True):
            if values is None or all(v is None for v in values):
                continue
            if len(rows) >= ROW_LIMIT:
                break
            vals = list(values) + [None] * max(0, len(actual) - len(values))
            out: dict[str, Any] = {"_row_id": uuid4().hex[:12]}
            for header, key, is_num in columns:
                idx = actual.index(header)
                raw = vals[idx] if idx < len(vals) else None
                out[key] = safe_float(raw) if is_num else safe_str(raw)
            rows.append(out)
        return rows
    finally:
        wb.close()


def content_io(content: bytes):
    import io

    return io.BytesIO(content)


# ── 端点 ──────────────────────────────────────────────────────────────────────

@router.post("/api/workpapers/{wp_id}/g0/export-template")
async def export_template(
    wp_id: str,
    sheet: str = Query(...),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _validate_sheet(sheet)
    if sheet == "G0-3S":
        wb = _build_g03s_workbook(None)
        return workbook_to_response(wb, "G0-3证券差异核对_模板.xlsx")
    wb = _build_g06_workbook(None)
    return workbook_to_response(wb, "G0-6替代程序_模板.xlsx")


@router.post("/api/workpapers/{wp_id}/g0/export-data")
async def export_data(
    wp_id: str,
    sheet: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    _validate_sheet(sheet)
    sheet_name = _SHEET_NAME_MAP[sheet]
    data = await _load_html_data(db, wp_id, sheet_name)
    if sheet == "G0-3S":
        rows = data.get("rows") if isinstance(data.get("rows"), list) else []
        wb = _build_g03s_workbook(rows)
        return workbook_to_response(wb, "G0-3证券差异核对_数据.xlsx")
    companies = data.get("companies") if isinstance(data.get("companies"), list) else []
    wb = _build_g06_workbook(companies)
    return workbook_to_response(wb, "G0-6替代程序_数据.xlsx")


@router.post("/api/workpapers/{wp_id}/g0/import-data")
async def import_data(
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

    sheet_name = _SHEET_NAME_MAP[sheet]

    if sheet == "G0-3S":
        try:
            rows = _parse_sheet_rows(content, None, _G03S_COLUMNS, header_row=2)
        except ValueError as e:
            return {"ok": False, "errors": [str(e)], "imported_count": 0}
        except Exception:
            raise HTTPException(400, "无法解析xlsx文件")
        payload = {
            "_format": "diff-securities-v1",
            "rows": rows,
            "conclusion": "",
            "audit_note": "",
        }
        # 保留已有结论/说明
        existing = await _load_html_data(db, wp_id, sheet_name)
        if existing.get("_format") == "diff-securities-v1":
            payload["conclusion"] = existing.get("conclusion", "")
            payload["audit_note"] = existing.get("audit_note", "")
        await _save_html_data(db, wp_id, sheet_name, payload)
        return {"ok": True, "imported_count": len(rows), "errors": []}

    # G0-6：4 区块分 sheet，按被函证单位归组为 companies
    errors: list[str] = []
    entity_map: dict[str, dict[str, Any]] = {}
    total = 0
    for block_key, cfg in _G06_BLOCKS.items():
        try:
            rows = _parse_sheet_rows(content, cfg["sheet_title"], cfg["columns"], header_row=1)
        except ValueError as e:
            errors.append(str(e))
            continue
        except Exception:
            raise HTTPException(400, "无法解析xlsx文件")
        for r in rows:
            entity = safe_str(r.pop("_entity", "")) or "未命名投资项目"
            company = entity_map.setdefault(
                entity,
                {
                    "_company_id": uuid4().hex[:12],
                    "entity_name": entity,
                    "_source": "import",
                    "sampling": {},
                    "balance": {"item_name": "交易性金融资产", "investment_type": "交易性金融资产"},
                    "block1_rows": [],
                    "block2_rows": [],
                    "block3_rows": [],
                    "block4_rows": [],
                    "conclusion": {},
                },
            )
            company[f"{block_key}_rows"].append(r)
            total += 1

    if errors and not entity_map:
        return {"ok": False, "errors": errors, "imported_count": 0}

    companies = list(entity_map.values())
    for i, c in enumerate(companies, start=1):
        c["seq"] = i
    payload = {"_format": "alternative-g06-v1", "companies": companies}
    await _save_html_data(db, wp_id, sheet_name, payload)
    out: dict[str, Any] = {"ok": True, "imported_count": total, "errors": errors}
    return out
