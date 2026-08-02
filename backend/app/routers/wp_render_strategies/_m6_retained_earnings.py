"""M6 未分配利润 — 专属渲染策略.

component_type = "m6-retained-earnings"

M6 前端组件 GtM6RetainedEarnings 为自加载组件（子组件各自拉取 checklist-responses），
按 sheetName 分发到各子组件（审定表/明细/调整/检查表/附注等）。
因此本渲染策略只需返回轻量 html_data（project_context + responses_snapshot），
关键作用是：让 component_type 在 RENDERER_DISPATCH 中命中，避免多 sheet dispatch
循环把 M6 各 sheet 误判为非白名单而重写成 onlyoffice-sheet。

科目4104利润分配-未分配利润（**贷方/权益类！**）：期末=期初+贷方-借方
M股东权益循环中的利润分配结转核心枢纽。
核心公式链：期末未分配利润=期初+本年净利润-提取盈余公积(M5)-分配股利(M1)
数据持久化在 checklist_responses 表，item_id 前缀为 "M6-*"。

Requirements: 1.6
"""

from __future__ import annotations

import json
import logging
from typing import Any

import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

# 科目编码：4104 利润分配-未分配利润
M6_ACCOUNT_CODE = "4104"
_ADJUDICATED_ITEM_ID = "M6-1-adjudicated-amount"

M6_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "m6-retained-earnings"},
    {"sheet_name": "未分配利润实质性程序表M6A", "component_type": "m6-retained-earnings"},
    {"sheet_name": "审定表M6-1", "component_type": "m6-retained-earnings"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "m6-retained-earnings"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "m6-retained-earnings"},
    {"sheet_name": "明细表M6-2", "component_type": "m6-retained-earnings"},
    {"sheet_name": "调整分录汇总M6-3", "component_type": "m6-retained-earnings"},
    {"sheet_name": "未分配利润检查表M6-4", "component_type": "m6-retained-earnings"},
]


# ─── 权益类公式验证（纯函数，可独立测试）─────────────────────────────────────

TOLERANCE = 0.01


def _parse_num(v: Any) -> float:
    """安全解析数值，None/空/NaN→0.0."""
    if v is None or v == "":
        return 0.0
    try:
        f = float(v)
        return 0.0 if f != f else f  # NaN→0.0
    except (ValueError, TypeError):
        return 0.0


def validate_equity_formula(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """校验权益类公式：期末=期初+贷方-借方.

    每行应含 begin/credit/debit/end_balance 字段。
    返回校验失败的行列表。
    """
    errors: list[dict[str, Any]] = []
    for row in rows:
        begin = _parse_num(row.get("begin") or row.get("opening") or row.get("period_begin"))
        credit = _parse_num(row.get("credit") or row.get("credit_amount"))
        debit = _parse_num(row.get("debit") or row.get("debit_amount"))
        end = _parse_num(row.get("end_balance") or row.get("ending") or row.get("period_end"))
        expected = begin + credit - debit
        if abs(end - expected) > TOLERANCE:
            errors.append({
                "row_key": row.get("row_key", ""),
                "begin": begin,
                "credit": credit,
                "debit": debit,
                "actual_end": end,
                "expected_end": expected,
                "diff": round(end - expected, 2),
            })
    return errors


def validate_distribution_formula(data: dict[str, Any]) -> list[dict[str, Any]]:
    """校验利润分配结转公式链：期末=期初+本年净利润-提取盈余公积-分配股利.

    返回校验失败的条目列表。
    """
    errors: list[dict[str, Any]] = []
    begin = _parse_num(data.get("begin_retained"))
    net_profit = _parse_num(data.get("net_profit"))
    surplus_accrual = _parse_num(data.get("surplus_accrual"))
    dividend = _parse_num(data.get("dividend"))
    end = _parse_num(data.get("end_retained"))

    expected = begin + net_profit - surplus_accrual - dividend
    if abs(end - expected) > TOLERANCE:
        errors.append({
            "check": "distribution_chain",
            "begin": begin,
            "net_profit": net_profit,
            "surplus_accrual": surplus_accrual,
            "dividend": dividend,
            "actual_end": end,
            "expected_end": expected,
            "diff": round(end - expected, 2),
        })
    return errors


# ─── TB 取数 ─────────────────────────────────────────────────────────────────


async def _fetch_tb_data(ctx: RenderContext) -> dict[str, Any]:
    """从 tb_balance 取科目4104利润分配-未分配利润余额数据."""
    result: dict[str, Any] = {
        "account_code": M6_ACCOUNT_CODE,
        "account_name": "利润分配-未分配利润",
        "direction": "credit",
        "begin_balance": 0,
        "debit_amount": 0,
        "credit_amount": 0,
        "end_balance": 0,
    }
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year or 0
        )
        stmt = sa.select(
            TbBalance.opening_balance.label("begin_balance"),
            TbBalance.debit_amount,
            TbBalance.credit_amount,
            TbBalance.closing_balance.label("end_balance"),
        ).where(
            TbBalance.project_id == str(ctx.project_id),
            TbBalance.account_code.like(M6_ACCOUNT_CODE + "%"),
            active_filter,
        )
        rows = (await ctx.db.execute(stmt)).fetchall()
        for row in rows:
            result["begin_balance"] += _parse_num(row.begin_balance)
            result["debit_amount"] += _parse_num(row.debit_amount)
            result["credit_amount"] += _parse_num(row.credit_amount)
            result["end_balance"] += _parse_num(row.end_balance)
    except Exception as e:  # noqa: BLE001
        logger.warning("M6 render: TB 取数失败: %s", e)
    return result


# ─── 主渲染函数 ───────────────────────────────────────────────────────────────


async def render(ctx: RenderContext) -> dict[str, Any]:
    """M6 未分配利润专属渲染策略.

    轻量返回：project_context + responses_snapshot + TB数据 + 公式校验。
    前端 GtM6RetainedEarnings 为自加载组件（各子组件独立拉取 checklist_responses）。
    """
    # ─── 读取 checklist_responses 快照 ─────────────────────────────────
    responses_snapshot: dict[str, Any] = {}
    adjudicated_amount: float | None = None
    try:
        rows = (
            await ctx.db.execute(
                sa.text(
                    "SELECT item_id, conclusion, evidence, status "
                    "FROM checklist_responses "
                    "WHERE workpaper_id = :wid"
                ),
                {"wid": str(ctx.wp_id)},
            )
        ).fetchall()
        for r in rows:
            responses_snapshot[r.item_id] = {
                "conclusion": r.conclusion,
                "evidence": r.evidence,
                "status": r.status,
            }
        # 提取审定数
        if _ADJUDICATED_ITEM_ID in responses_snapshot:
            raw_adj = responses_snapshot[_ADJUDICATED_ITEM_ID].get("conclusion")
            if raw_adj is not None:
                adjudicated_amount = _parse_num(raw_adj)
    except Exception as e:  # noqa: BLE001
        logger.warning("M6 render: checklist_responses 查询失败: %s", e)

    # ─── 项目上下文 ────────────────────────────────────────────────────
    project_context: dict[str, str] = {
        "client_name": "",
        "audit_year": "",
        "business_category": ctx.business_category or "",
    }
    try:
        proj_row = (
            await ctx.db.execute(
                sa.text(
                    "SELECT client_name, audit_year, business_category "
                    "FROM projects WHERE id = :pid"
                ),
                {"pid": str(ctx.project_id)},
            )
        ).fetchone()
        if proj_row:
            project_context["client_name"] = proj_row.client_name or ""
            project_context["audit_year"] = str(proj_row.audit_year or "")
            project_context["business_category"] = (
                proj_row.business_category or ctx.business_category or ""
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("M6 render: project context 查询失败: %s", e)

    # ─── TB 取数（科目4104利润分配-未分配利润）────────────────────────────
    tb = await _fetch_tb_data(ctx)

    # ─── 公式校验（从快照提取结构化数据行）────────────────────────────────
    formula_errors: list[dict[str, Any]] = []
    formula_rows: list[dict[str, Any]] = []
    distribution_errors: list[dict[str, Any]] = []

    for item_id, data in responses_snapshot.items():
        if not item_id.startswith("M6-1-"):
            continue
        raw = data.get("conclusion", "")
        if raw and isinstance(raw, str) and raw.startswith("{"):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict) and any(
                    k in parsed for k in ("begin", "opening", "period_begin", "end_balance")
                ):
                    parsed["row_key"] = item_id
                    formula_rows.append(parsed)
            except (json.JSONDecodeError, TypeError):
                pass

    if formula_rows:
        formula_errors = validate_equity_formula(formula_rows)

    # 利润分配结转公式链校验（从M6-2明细数据提取）
    for item_id, data in responses_snapshot.items():
        if item_id != "M6-2-distribution-summary":
            continue
        raw = data.get("conclusion", "")
        if raw and isinstance(raw, str) and raw.startswith("{"):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    distribution_errors = validate_distribution_formula(parsed)
            except (json.JSONDecodeError, TypeError):
                pass

    return {
        "account_code": M6_ACCOUNT_CODE,
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "adjudicated_amount": adjudicated_amount,
        # TB 余额数据（科目4104，贷方/权益类）
        "trial_balance": tb,
        # 权益类公式方向元数据（前端可用于初始化校验）
        "formula_direction": {
            "account_code": "4104",
            "account_name": "利润分配-未分配利润",
            "direction": "credit",  # 贷方/权益类！
            "end_balance_formula": "begin + credit - debit",  # 期末=期初+贷方-借方
            "distribution_formula": "begin + net_profit - surplus_accrual - dividend",
            "note": "权益类贷方科目：本年利润结转贷方增加，提取盈余公积/宣告股利借方减少。"
                    "利润分配结转核心：期末=期初+净利润-提取盈余公积-分配股利",
        },
        # 权益类公式校验错误（前端可展示红色提示）
        "formula_errors": formula_errors,
        # 利润分配结转公式链校验错误
        "distribution_errors": distribution_errors,
        # sheet 列表元数据
        "sheets": M6_SHEETS,
        "component_type": "m6-retained-earnings",
    }
