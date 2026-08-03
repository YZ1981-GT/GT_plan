"""M10 其他权益工具 — 专属渲染策略.

component_type = "m10-other-equity-instruments"

M10 前端组件 GtM10OtherEquityInstruments 为自加载组件（子组件各自拉取 checklist-responses），
按 sheetName 分发到各子组件（审定表/明细/负债权益区分检查/工具检查/调整/附注等）。
因此本渲染策略只需返回轻量 html_data（project_context + responses_snapshot），
关键作用是：让 component_type 在 RENDERER_DISPATCH 中命中，避免多 sheet dispatch
循环把 M10 各 sheet 误判为非白名单而重写成 onlyoffice-sheet。

科目4003其他权益工具（**贷方/权益类！**）：期末=期初+贷方-借方
M股东权益循环中的权益类科目。发行时贷方增加，赎回/转换时借方减少。
核心特殊：①贷方权益类科目 ②负债与权益区分（CAS37）：永续债/优先股等金融工具
需按CAS37《金融工具列报》判定是否分类为权益工具（是否存在交付现金/金融资产的合同义务），
归入权益的部分计入M10(4003)，归入负债的计入负债科目。
数据持久化在 checklist_responses 表，item_id 前缀为 "M10-*"。

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
from app.services.four_table import resolve_semantic_accounts
from app.services.four_table.m_cycle_specs import M10_SPEC

logger = logging.getLogger(__name__)

_M10_ACCOUNT_CODE = "4401"
_ADJUDICATED_ITEM_ID = "M10-1-adjudicated-amount"

M10_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "m10-other-equity-instruments"},
    {"sheet_name": "其他权益工具实质性程序表M10A", "component_type": "m10-other-equity-instruments"},
    {"sheet_name": "审定表M10-1", "component_type": "m10-other-equity-instruments"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "m10-other-equity-instruments"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "m10-other-equity-instruments"},
    {"sheet_name": "明细表M10-2", "component_type": "m10-other-equity-instruments"},
    {"sheet_name": "调整分录汇总M10-3", "component_type": "m10-other-equity-instruments"},
    {"sheet_name": "负债与权益区分检查表M10-4", "component_type": "m10-other-equity-instruments"},
    {"sheet_name": "其他权益工具检查表M10-5", "component_type": "m10-other-equity-instruments"},
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


# ─── TB 取数 ─────────────────────────────────────────────────────────────────


async def _fetch_tb_data(ctx: RenderContext) -> dict[str, Any]:
    """从 tb_balance 取科目4401其他权益工具余额数据."""

    # 科目定位（语义驱动）
    try:
        _sem_accounts = await resolve_semantic_accounts(ctx, M10_SPEC)
    except Exception:  # noqa: BLE001
        _sem_accounts = None

    result: dict[str, Any] = {
        "account_code": _M10_ACCOUNT_CODE,
        "account_name": "其他权益工具",
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
        stmt = (
            sa.select(
                TbBalance.opening_balance.label("begin_balance"),
                TbBalance.debit_amount,
                TbBalance.credit_amount,
                TbBalance.closing_balance.label("end_balance"),
            )
            .where(
                TbBalance.project_id == str(ctx.project_id),
                TbBalance.account_code.like(_M10_ACCOUNT_CODE + "%"),
                active_filter,
            )
        )
        rows = (await ctx.db.execute(stmt)).fetchall()
        for row in rows:
            result["begin_balance"] += _parse_num(row.begin_balance)
            result["debit_amount"] += _parse_num(row.debit_amount)
            result["credit_amount"] += _parse_num(row.credit_amount)
            result["end_balance"] += _parse_num(row.end_balance)
    except Exception as e:  # noqa: BLE001
        logger.warning("M10 render: TB 取数失败: %s", e)
        if _sem_accounts:

            result['tb_source_codes'] = _sem_accounts.as_dict()

    return result


# ─── 主渲染函数 ───────────────────────────────────────────────────────────────


async def render(ctx: RenderContext) -> dict[str, Any]:
    """M10 其他权益工具专属渲染策略.

    轻量返回：project_context + responses_snapshot + TB数据 + 公式校验。
    前端 GtM10OtherEquityInstruments 为自加载组件（各子组件独立拉取 checklist_responses）。
    """
    # ─── 读取 checklist_responses 快照 ─────────────────────────────────
    responses_snapshot: dict[str, Any] = {}
    adjudicated_amount: float | None = None
    try:
        rows = (
            await ctx.db.execute(
                sa.text(
                    "SELECT item_id, conclusion, remark "
                    "FROM checklist_responses "
                    "WHERE wp_id = :wid"
                ),
                {"wid": str(ctx.wp_id)},
            )
        ).fetchall()
        for r in rows:
            responses_snapshot[r.item_id] = {
                "conclusion": r.conclusion,
                "remark": r.remark,
            }
        # 提取审定数
        if _ADJUDICATED_ITEM_ID in responses_snapshot:
            raw_adj = responses_snapshot[_ADJUDICATED_ITEM_ID].get("conclusion")
            if raw_adj is not None:
                adjudicated_amount = _parse_num(raw_adj)
    except Exception as e:  # noqa: BLE001
        logger.warning("M10 render: checklist_responses 查询失败: %s", e)

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
        logger.warning("M10 render: project context 查询失败: %s", e)

    # ─── TB 取数（科目4003其他权益工具）─────────────────────────────────
    tb = await _fetch_tb_data(ctx)

    # ─── 公式校验（从快照提取结构化数据行）────────────────────────────────
    formula_errors: list[dict[str, Any]] = []
    formula_rows: list[dict[str, Any]] = []
    for item_id, data in responses_snapshot.items():
        if not item_id.startswith("M10-1-"):
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

    return {
        "account_code": _M10_ACCOUNT_CODE,
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "adjudicated_amount": adjudicated_amount,
        # TB 余额数据（科目4003，贷方/权益类）
        "trial_balance": tb,
        # 权益类公式方向元数据（前端可用于初始化校验）
        "formula_direction": {
            "account_code": "4401",
            "account_name": "其他权益工具",
            "direction": "credit",  # 贷方/权益类！
            "end_balance_formula": "begin + credit - debit",  # 期末=期初+贷方-借方
            "note": "权益类贷方科目：发行（永续债/优先股）在贷方增加，赎回/转换在借方减少。CAS37负债权益区分后归入权益的部分计入4003",
        },
        # 公式校验错误（前端可展示红色提示）
        "formula_errors": formula_errors,
        # sheet 列表元数据
        "sheets": M10_SHEETS,
        "component_type": "m10-other-equity-instruments",
    }
