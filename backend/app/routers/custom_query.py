"""自定义查询 API — 支持多维度跨模块数据查询

支持查询维度：
  - report: 报表数据（report_config）
  - trial_balance: 试算表数据（trial_balance_entries）
  - disclosure: 附注数据（consol_note_data）
  - adjustment: 调整分录（adjustments）
  - worksheet: 工作底稿数据（consol_worksheet_data）
  - workpaper: 底稿列表（working_paper）— Sprint 6 新增
  - account_balance: 科目余额（tb_balance）— Sprint 6 新增
  - ledger_entries: 序时账（tb_ledger）— Sprint 6 新增
  - report_lines: 报表行次（report_config / financial_report）— Sprint 6 新增
  - workhours: 工时记录（work_hours）— Sprint 6 新增

支持过滤：
  - project_id: 项目
  - year: 年度
  - company_code: 单位
  - report_type: 报表类型
  - account_name: 科目名
  - section_id: 附注章节

API:
  POST   /api/custom-query/execute              — 执行查询
  GET    /api/custom-query/indicators           — 获取可查询指标库（树形）
  GET    /api/custom-query/templates            — 列出查询模板（私有 + 全局）
  POST   /api/custom-query/templates            — 创建查询模板
  GET    /api/custom-query/templates/{id}       — 获取模板详情
  PUT    /api/custom-query/templates/{id}       — 更新模板
  DELETE /api/custom-query/templates/{id}       — 删除模板（仅创建者或 admin）
"""

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.deps import get_current_user
from app.models.core import User
from app.models.custom_query_models import CustomQueryTemplate

router = APIRouter(prefix="/api/custom-query", tags=["custom-query"])


class QueryRequest(BaseModel):
    project_id: str
    year: int
    source: str  # report | trial_balance | disclosure | adjustment | worksheet | workpaper | account_balance | ledger_entries | report_lines | workhours
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
        # Sprint 6 新增数据源
        {
            "key": "workpaper", "label": "📄 底稿列表", "icon": "📄",
            "children": [
                {"key": "workpaper", "label": "底稿列表", "columns": ["wp_code", "wp_name", "status", "review_status", "preparer_id"]},
            ],
        },
        {
            "key": "account_balance", "label": "💰 科目余额", "icon": "💰",
            "children": [
                {"key": "account_balance", "label": "科目余额表", "columns": ["account_code", "account_name", "opening_balance", "closing_balance", "debit_amount", "credit_amount"]},
            ],
        },
        {
            "key": "ledger_entries", "label": "📜 序时账", "icon": "📜",
            "children": [
                {"key": "ledger_entries", "label": "序时账明细", "columns": ["voucher_date", "voucher_no", "account_code", "account_name", "debit_amount", "credit_amount", "summary"]},
            ],
        },
        {
            "key": "report_lines", "label": "📈 报表行次", "icon": "📈",
            "children": [
                {"key": "report_lines", "label": "报表行次配置", "columns": ["row_code", "row_name", "report_type", "applicable_standard", "indent_level", "is_total_row", "formula"]},
            ],
        },
        {
            "key": "workhours", "label": "⏱️ 工时记录", "icon": "⏱️",
            "children": [
                {"key": "workhours", "label": "工时记录", "columns": ["work_date", "hours", "description", "status", "staff_id"]},
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
        elif source == 'workpaper':
            return await _query_workpaper(db, pid, year, filters, limit)
        elif source == 'account_balance':
            return await _query_account_balance(db, pid, year, filters, limit)
        elif source == 'ledger_entries':
            return await _query_ledger_entries(db, pid, year, filters, limit)
        elif source == 'report_lines':
            return await _query_report_lines(db, pid, year, filters, limit)
        elif source == 'workhours':
            return await _query_workhours(db, pid, year, filters, limit)
        else:
            return {"rows": [], "columns": [], "total": 0, "error": f"未知数据源: {source}"}
    except Exception as e:
        # 失败时回滚事务（防止 asyncpg session 污染影响后续请求）
        try:
            await db.rollback()
        except Exception:
            pass
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



# ──────────────────────────────────────────────────────────────────────────
# Sprint 6 Task 6.4 — 新增 5 个数据源查询函数
# ──────────────────────────────────────────────────────────────────────────


async def _query_workpaper(db, pid, year, filters, limit):
    """底稿列表（working_paper）"""
    sql = """
        SELECT wi.wp_code, wi.wp_name, wi.cycle, wp.status, wp.review_status,
               wp.preparer_id, wp.created_at, wp.updated_at
        FROM working_paper wp
        LEFT JOIN wp_index wi ON wi.id = wp.wp_index_id
        WHERE wp.project_id = :pid AND wp.year = :y AND wp.is_deleted = false
    """
    params: dict = {"pid": pid, "y": year, "lim": limit}
    if filters.get("status"):
        sql += " AND wp.status = :st"
        params["st"] = filters["status"]
    if filters.get("review_status"):
        sql += " AND wp.review_status = :rs"
        params["rs"] = filters["review_status"]
    if filters.get("cycle"):
        sql += " AND wi.cycle = :cy"
        params["cy"] = filters["cycle"]
    sql += " ORDER BY wi.wp_code LIMIT :lim"
    result = await db.execute(text(sql), params)
    rows = [
        {
            "wp_code": r[0],
            "wp_name": r[1],
            "cycle": r[2],
            "status": r[3],
            "review_status": r[4],
            "preparer_id": str(r[5]) if r[5] else None,
            "created_at": str(r[6]) if r[6] else None,
            "updated_at": str(r[7]) if r[7] else None,
        }
        for r in result.fetchall()
    ]
    return {
        "rows": rows,
        "columns": ["wp_code", "wp_name", "cycle", "status", "review_status", "preparer_id"],
        "total": len(rows),
    }


async def _query_account_balance(db, pid, year, filters, limit):
    """科目余额表（tb_balance）— B' 视图架构按 is_deleted=false 过滤"""
    sql = """
        SELECT account_code, account_name, opening_balance, closing_balance,
               debit_amount, credit_amount, currency_code
        FROM tb_balance
        WHERE project_id = :pid AND year = :y AND is_deleted = false
    """
    params: dict = {"pid": pid, "y": year, "lim": limit}
    if filters.get("account_code"):
        sql += " AND account_code LIKE :ac"
        params["ac"] = f"{filters['account_code']}%"
    if filters.get("account_name"):
        sql += " AND account_name LIKE :an"
        params["an"] = f"%{filters['account_name']}%"
    if filters.get("company_code"):
        sql += " AND company_code = :cc"
        params["cc"] = filters["company_code"]
    sql += " ORDER BY account_code LIMIT :lim"
    result = await db.execute(text(sql), params)
    rows = [
        {
            "account_code": r[0],
            "account_name": r[1],
            "opening_balance": float(r[2]) if r[2] is not None else None,
            "closing_balance": float(r[3]) if r[3] is not None else None,
            "debit_amount": float(r[4]) if r[4] is not None else None,
            "credit_amount": float(r[5]) if r[5] is not None else None,
            "currency_code": r[6],
        }
        for r in result.fetchall()
    ]
    return {
        "rows": rows,
        "columns": ["account_code", "account_name", "opening_balance", "closing_balance", "debit_amount", "credit_amount", "currency_code"],
        "total": len(rows),
    }


async def _query_ledger_entries(db, pid, year, filters, limit):
    """序时账（tb_ledger）"""
    sql = """
        SELECT voucher_date, voucher_no, account_code, account_name,
               debit_amount, credit_amount, summary
        FROM tb_ledger
        WHERE project_id = :pid AND year = :y AND is_deleted = false
    """
    params: dict = {"pid": pid, "y": year, "lim": limit}
    if filters.get("account_code"):
        sql += " AND account_code LIKE :ac"
        params["ac"] = f"{filters['account_code']}%"
    if filters.get("voucher_no"):
        sql += " AND voucher_no LIKE :vn"
        params["vn"] = f"%{filters['voucher_no']}%"
    if filters.get("summary"):
        sql += " AND summary LIKE :sm"
        params["sm"] = f"%{filters['summary']}%"
    if filters.get("date_from"):
        sql += " AND voucher_date >= :df"
        params["df"] = filters["date_from"]
    if filters.get("date_to"):
        sql += " AND voucher_date <= :dt"
        params["dt"] = filters["date_to"]
    sql += " ORDER BY voucher_date DESC, voucher_no LIMIT :lim"
    result = await db.execute(text(sql), params)
    rows = [
        {
            "voucher_date": str(r[0]) if r[0] else None,
            "voucher_no": r[1],
            "account_code": r[2],
            "account_name": r[3],
            "debit_amount": float(r[4]) if r[4] is not None else None,
            "credit_amount": float(r[5]) if r[5] is not None else None,
            "summary": r[6],
        }
        for r in result.fetchall()
    ]
    return {
        "rows": rows,
        "columns": ["voucher_date", "voucher_no", "account_code", "account_name", "debit_amount", "credit_amount", "summary"],
        "total": len(rows),
    }


async def _query_report_lines(db, pid, year, filters, limit):
    """报表行次配置（report_config）"""
    sql = """
        SELECT row_code, row_name, report_type, applicable_standard,
               indent_level, is_total_row, formula, sort_order
        FROM report_config
        WHERE is_deleted = false
    """
    params: dict = {"lim": limit}
    if filters.get("report_type"):
        sql += " AND report_type = :rt"
        params["rt"] = filters["report_type"]
    if filters.get("applicable_standard"):
        sql += " AND applicable_standard = :std"
        params["std"] = filters["applicable_standard"]
    if filters.get("has_formula") is True:
        sql += " AND formula IS NOT NULL AND formula != ''"
    elif filters.get("has_formula") is False:
        sql += " AND (formula IS NULL OR formula = '')"
    if filters.get("row_name"):
        sql += " AND row_name LIKE :rn"
        params["rn"] = f"%{filters['row_name']}%"
    sql += " ORDER BY applicable_standard, report_type, sort_order LIMIT :lim"
    result = await db.execute(text(sql), params)
    rows = [
        {
            "row_code": r[0],
            "row_name": r[1],
            "report_type": r[2],
            "applicable_standard": r[3],
            "indent_level": r[4],
            "is_total_row": r[5],
            "formula": r[6],
            "sort_order": r[7],
        }
        for r in result.fetchall()
    ]
    return {
        "rows": rows,
        "columns": ["row_code", "row_name", "report_type", "applicable_standard", "indent_level", "is_total_row", "formula", "sort_order"],
        "total": len(rows),
    }


async def _query_workhours(db, pid, year, filters, limit):
    """工时记录（work_hours）"""
    sql = """
        SELECT work_date, hours, description, status, staff_id, project_id, created_at
        FROM work_hours
        WHERE is_deleted = false
    """
    params: dict = {"lim": limit}
    # 可选项目过滤（pid 可能为空字符串）
    if pid:
        sql += " AND project_id = :pid"
        params["pid"] = pid
    if year:
        sql += " AND EXTRACT(YEAR FROM work_date) = :y"
        params["y"] = year
    if filters.get("staff_id"):
        sql += " AND staff_id = :sid"
        params["sid"] = filters["staff_id"]
    if filters.get("status"):
        sql += " AND status = :st"
        params["st"] = filters["status"]
    if filters.get("date_from"):
        sql += " AND work_date >= :df"
        params["df"] = filters["date_from"]
    if filters.get("date_to"):
        sql += " AND work_date <= :dt"
        params["dt"] = filters["date_to"]
    sql += " ORDER BY work_date DESC LIMIT :lim"
    result = await db.execute(text(sql), params)
    rows = [
        {
            "work_date": str(r[0]) if r[0] else None,
            "hours": float(r[1]) if r[1] is not None else 0,
            "description": r[2],
            "status": r[3],
            "staff_id": str(r[4]) if r[4] else None,
            "project_id": str(r[5]) if r[5] else None,
            "created_at": str(r[6]) if r[6] else None,
        }
        for r in result.fetchall()
    ]
    return {
        "rows": rows,
        "columns": ["work_date", "hours", "description", "status", "staff_id"],
        "total": len(rows),
    }


# ──────────────────────────────────────────────────────────────────────────
# Sprint 6 Task 6.6 — 自定义查询模板 CRUD 端点
# ──────────────────────────────────────────────────────────────────────────


class TemplateCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    data_source: str = Field(..., min_length=1, max_length=50)
    config: dict
    scope: Literal["private", "global"] = "private"


class TemplateUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    data_source: str | None = None
    config: dict | None = None
    scope: Literal["private", "global"] | None = None


class TemplateResponse(BaseModel):
    id: str
    name: str
    description: str | None
    data_source: str
    config: dict
    scope: str
    created_by: str
    is_owner: bool
    created_at: str
    updated_at: str


def _serialize_template(tpl: CustomQueryTemplate, current_user_id: uuid.UUID) -> dict:
    return {
        "id": str(tpl.id),
        "name": tpl.name,
        "description": tpl.description,
        "data_source": tpl.data_source,
        "config": tpl.config or {},
        "scope": tpl.scope,
        "created_by": str(tpl.created_by),
        "is_owner": tpl.created_by == current_user_id,
        "created_at": tpl.created_at.isoformat() if tpl.created_at else None,
        "updated_at": tpl.updated_at.isoformat() if tpl.updated_at else None,
    }


@router.get("/templates")
async def list_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """列出可见模板：本人创建的所有 + 全局共享。

    按 updated_at 倒序排列（最近编辑置顶）。
    """
    stmt = (
        select(CustomQueryTemplate)
        .where(
            or_(
                CustomQueryTemplate.created_by == current_user.id,
                CustomQueryTemplate.scope == "global",
            )
        )
        .order_by(CustomQueryTemplate.updated_at.desc())
    )
    result = await db.execute(stmt)
    templates = result.scalars().all()
    return {
        "templates": [_serialize_template(t, current_user.id) for t in templates],
        "total": len(templates),
    }


@router.post("/templates", status_code=201)
async def create_template(
    body: TemplateCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建查询模板。"""
    tpl = CustomQueryTemplate(
        id=uuid.uuid4(),
        name=body.name,
        description=body.description,
        data_source=body.data_source,
        config=body.config,
        scope=body.scope,
        created_by=current_user.id,
    )
    db.add(tpl)
    await db.commit()
    await db.refresh(tpl)
    return _serialize_template(tpl, current_user.id)


@router.get("/templates/{template_id}")
async def get_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取模板详情。"""
    try:
        tpl_uuid = uuid.UUID(template_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail={"error_code": "INVALID_TEMPLATE_ID"})
    tpl = await db.get(CustomQueryTemplate, tpl_uuid)
    if not tpl:
        raise HTTPException(status_code=404, detail={"error_code": "TEMPLATE_NOT_FOUND"})
    # 权限：本人 or 全局可见
    if tpl.scope != "global" and tpl.created_by != current_user.id:
        raise HTTPException(status_code=403, detail={"error_code": "TEMPLATE_NOT_VISIBLE"})
    return _serialize_template(tpl, current_user.id)


@router.put("/templates/{template_id}")
async def update_template(
    template_id: str,
    body: TemplateUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新模板（仅创建者）。"""
    try:
        tpl_uuid = uuid.UUID(template_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail={"error_code": "INVALID_TEMPLATE_ID"})
    tpl = await db.get(CustomQueryTemplate, tpl_uuid)
    if not tpl:
        raise HTTPException(status_code=404, detail={"error_code": "TEMPLATE_NOT_FOUND"})
    user_role = getattr(current_user, "role", "")
    if tpl.created_by != current_user.id and user_role != "admin":
        raise HTTPException(status_code=403, detail={"error_code": "ONLY_OWNER_CAN_UPDATE"})

    if body.name is not None:
        tpl.name = body.name
    if body.description is not None:
        tpl.description = body.description
    if body.data_source is not None:
        tpl.data_source = body.data_source
    if body.config is not None:
        tpl.config = body.config
    if body.scope is not None:
        tpl.scope = body.scope
    tpl.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(tpl)
    return _serialize_template(tpl, current_user.id)


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除模板（仅创建者或 admin）。"""
    try:
        tpl_uuid = uuid.UUID(template_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail={"error_code": "INVALID_TEMPLATE_ID"})
    tpl = await db.get(CustomQueryTemplate, tpl_uuid)
    if not tpl:
        raise HTTPException(status_code=404, detail={"error_code": "TEMPLATE_NOT_FOUND"})
    user_role = getattr(current_user, "role", "")
    if tpl.created_by != current_user.id and user_role != "admin":
        raise HTTPException(status_code=403, detail={"error_code": "ONLY_OWNER_OR_ADMIN_CAN_DELETE"})
    await db.delete(tpl)
    await db.commit()
    return None
