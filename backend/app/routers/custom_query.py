"""自定义查询 API — 支持多维度跨模块数据查询

支持查询维度：
  - report: 报表数据（report_config）
  - trial_balance: 试算表数据（trial_balance_entries）
  - disclosure: 附注数据（consol_note_data）
  - adjustment: 调整分录（adjustments）
  - worksheet: 工作底稿数据（consol_worksheet_data）

支持过滤：
  - project_id: 项目
  - year: 年度
  - company_code: 单位
  - report_type: 报表类型
  - account_name: 科目名
  - section_id: 附注章节

API:
  POST /api/custom-query/execute  — 执行查询
  GET  /api/custom-query/indicators — 获取可查询指标库（树形）
"""

import json
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

router = APIRouter(prefix="/api/custom-query", tags=["custom-query"])


class QueryRequest(BaseModel):
    project_id: str
    year: int
    source: str  # report | trial_balance | disclosure | adjustment | worksheet
    filters: dict = {}  # report_type, account_name, section_id, company_code, etc.
    columns: list[str] = []  # 要查询的列（空=全部）
    limit: int = 500
    offset: int = 0


@router.get("/indicators")
async def get_indicators():
    """获取可查询指标库（树形结构）"""
    return [
        {
            "key": "report", "label": "📊 报表", "icon": "📊",
            "children": [
                {"key": "report_balance_sheet", "label": "资产负债表", "columns": ["row_code", "row_name", "current_period_amount", "prior_period_amount"]},
                {"key": "report_income_statement", "label": "利润表", "columns": ["row_code", "row_name", "current_period_amount", "prior_period_amount"]},
                {"key": "report_cash_flow_statement", "label": "现金流量表", "columns": ["row_code", "row_name", "current_period_amount", "prior_period_amount"]},
                {"key": "report_equity_statement", "label": "所有者权益变动表", "columns": ["row_code", "row_name", "current_period_amount", "prior_period_amount"]},
            ],
        },
        {
            "key": "trial_balance", "label": "📋 试算表", "icon": "📋",
            "children": [
                {"key": "tb_detail", "label": "科目明细", "columns": ["account_code", "account_name", "opening_balance", "closing_balance", "debit_amount", "credit_amount"]},
                {"key": "tb_summary", "label": "试算平衡表", "columns": ["row_code", "row_name", "unadjusted", "aje_dr", "aje_cr", "rcl_dr", "rcl_cr", "audited"]},
            ],
        },
        {
            "key": "disclosure", "label": "📝 附注", "icon": "📝",
            "children": [
                {"key": "disclosure_note", "label": "附注章节数据", "columns": ["section_id", "headers", "rows"]},
            ],
        },
        {
            "key": "adjustment", "label": "📐 调整分录", "icon": "📐",
            "children": [
                {"key": "adj_aje", "label": "审计调整分录(AJE)", "columns": ["entry_number", "account_name", "debit_amount", "credit_amount", "description"]},
                {"key": "adj_rcl", "label": "重分类调整(RCL)", "columns": ["entry_number", "account_name", "debit_amount", "credit_amount", "description"]},
            ],
        },
        {
            "key": "worksheet", "label": "📑 工作底稿", "icon": "📑",
            "children": [
                {"key": "ws_info", "label": "基本信息表", "columns": ["company_name", "company_code", "holding_type", "non_common_ratio"]},
                {"key": "ws_elimination", "label": "抵消分录", "columns": ["direction", "subject", "amount", "desc"]},
                {"key": "ws_consol_tb", "label": "合并试算平衡表", "columns": ["row_code", "row_name", "summary", "equity_dr", "equity_cr", "audited"]},
            ],
        },
    ]


@router.post("/execute")
async def execute_query(
    body: QueryRequest,
    db: AsyncSession = Depends(get_db),
):
    """执行自定义查询"""
    source = body.source
    pid = body.project_id
    year = body.year
    filters = body.filters
    limit = min(body.limit, 2000)

    try:
        if source == 'report' or source.startswith('report_'):
            return await _query_report(db, pid, year, filters, limit)
        elif source == 'trial_balance' or source == 'tb_detail':
            return await _query_trial_balance(db, pid, year, filters, limit)
        elif source == 'tb_summary':
            return await _query_tb_summary(db, pid, year, filters, limit)
        elif source == 'disclosure' or source == 'disclosure_note':
            return await _query_disclosure(db, pid, year, filters, limit)
        elif source.startswith('adj_') or source == 'adjustment':
            return await _query_adjustments(db, pid, year, filters, limit)
        elif source.startswith('ws_') or source == 'worksheet':
            return await _query_worksheet(db, pid, year, filters, limit)
        else:
            return {"rows": [], "columns": [], "total": 0, "error": f"未知数据源: {source}"}
    except Exception as e:
        return {"rows": [], "columns": [], "total": 0, "error": str(e)}


async def _query_report(db, pid, year, filters, limit):
    report_type = filters.get("report_type", "balance_sheet")
    standard = filters.get("standard", "soe_standalone")
    # 优先查项目级数据，降级查全局模板
    query = "SELECT row_code, row_name, current_period_amount, prior_period_amount, indent_level, is_total_row FROM report_config WHERE report_type = :rt AND applicable_standard = :std AND is_deleted = false"
    params: dict = {"rt": report_type, "std": standard, "lim": limit}
    if pid:
        query += " AND (project_id = :pid OR project_id IS NULL)"
        params["pid"] = pid
    query += " ORDER BY row_number LIMIT :lim"
    result = await db.execute(text(query), params)
    rows = [{"row_code": r[0], "row_name": r[1], "current_period_amount": float(r[2]) if r[2] else None, "prior_period_amount": float(r[3]) if r[3] else None, "indent": r[4], "is_total": r[5]} for r in result.fetchall()]
    return {"rows": rows, "columns": ["row_code", "row_name", "current_period_amount", "prior_period_amount"], "total": len(rows)}


async def _query_trial_balance(db, pid, year, filters, limit):
    query = "SELECT account_code, account_name, opening_balance, closing_balance, debit_amount, credit_amount FROM trial_balance_entries WHERE project_id = :pid AND year = :y"
    params: dict = {"pid": pid, "y": year, "lim": limit}
    if filters.get("account_name"):
        query += " AND account_name LIKE :an"
        params["an"] = f"%{filters['account_name']}%"
    if filters.get("company_code"):
        query += " AND company_code = :cc"
        params["cc"] = filters["company_code"]
    query += " ORDER BY account_code LIMIT :lim"
    result = await db.execute(text(query), params)
    rows = [{"account_code": r[0], "account_name": r[1], "opening_balance": float(r[2]) if r[2] else None, "closing_balance": float(r[3]) if r[3] else None, "debit_amount": float(r[4]) if r[4] else None, "credit_amount": float(r[5]) if r[5] else None} for r in result.fetchall()]
    return {"rows": rows, "columns": ["account_code", "account_name", "opening_balance", "closing_balance", "debit_amount", "credit_amount"], "total": len(rows)}


async def _query_tb_summary(db, pid, year, filters, limit):
    sheet_type = filters.get("report_type", "balance_sheet")
    result = await db.execute(
        text("SELECT data FROM consol_worksheet_data WHERE project_id = :pid AND year = :y AND sheet_key = :sk"),
        {"pid": pid, "y": year, "sk": f"tb_summary_{sheet_type}"},
    )
    row = result.fetchone()
    if row and isinstance(row[0], dict):
        rows = row[0].get("rows", [])[:limit]
        return {"rows": rows, "columns": ["row_code", "row_name", "unadjusted", "aje_dr", "aje_cr", "rcl_dr", "rcl_cr", "audited"], "total": len(rows)}
    return {"rows": [], "columns": [], "total": 0}


async def _query_disclosure(db, pid, year, filters, limit):
    section_id = filters.get("section_id", "")
    if section_id:
        result = await db.execute(
            text("SELECT section_id, data FROM consol_note_data WHERE project_id = :pid AND year = :y AND section_id = :sid"),
            {"pid": pid, "y": year, "sid": section_id},
        )
    else:
        result = await db.execute(
            text("SELECT section_id, data FROM consol_note_data WHERE project_id = :pid AND year = :y LIMIT :lim"),
            {"pid": pid, "y": year, "lim": limit},
        )
    # 将附注数据展平为表格行（每个章节的每行数据变成一条记录）
    flat_rows = []
    all_headers: list[str] = []
    for r in result.fetchall():
        data = r[1] if isinstance(r[1], dict) else {}
        headers = data.get("headers", [])
        rows = data.get("rows", [])
        if headers and not all_headers:
            all_headers = ["section_id"] + headers
        for row_data in rows[:100]:  # 每章节最多100行
            obj: dict = {"section_id": r[0]}
            for hi, h in enumerate(headers):
                obj[h] = row_data[hi] if hi < len(row_data) else ''
            flat_rows.append(obj)
    columns = all_headers if all_headers else ["section_id"]
    return {"rows": flat_rows[:limit], "columns": columns, "total": len(flat_rows)}


async def _query_adjustments(db, pid, year, filters, limit):
    adj_type = filters.get("adjustment_type", "AJE")
    result = await db.execute(
        text("SELECT entry_number, account_name, debit_amount, credit_amount, description, status FROM adjustments WHERE project_id = :pid AND year = :y AND adjustment_type = :at AND is_deleted = false ORDER BY entry_number LIMIT :lim"),
        {"pid": pid, "y": year, "at": adj_type, "lim": limit},
    )
    rows = [{"entry_number": r[0], "account_name": r[1], "debit_amount": float(r[2]) if r[2] else None, "credit_amount": float(r[3]) if r[3] else None, "description": r[4], "status": r[5]} for r in result.fetchall()]
    return {"rows": rows, "columns": ["entry_number", "account_name", "debit_amount", "credit_amount", "description", "status"], "total": len(rows)}


async def _query_worksheet(db, pid, year, filters, limit):
    sheet_key = filters.get("sheet_key", "info")
    result = await db.execute(
        text("SELECT data, updated_at FROM consol_worksheet_data WHERE project_id = :pid AND year = :y AND sheet_key = :sk"),
        {"pid": pid, "y": year, "sk": sheet_key},
    )
    row = result.fetchone()
    if row and isinstance(row[0], dict):
        data = row[0]
        rows = data.get("rows", [])[:limit]
        columns = list(rows[0].keys()) if rows else []
        return {"rows": rows, "columns": columns, "total": len(rows), "updated_at": str(row[1]) if row[1] else None}
    return {"rows": [], "columns": [], "total": 0}
