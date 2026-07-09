"""M9 其他综合收益 — 专属渲染策略.

component_type = "m9-other-comprehensive-income"

M9 前端组件 GtM9OtherComprehensiveIncome 为自加载组件（子组件各自拉取 checklist-responses），
按 sheetName 分发到各子组件（审定表/明细/OCI核对/调整/附注等）。
因此本渲染策略只需返回轻量 html_data（project_context + responses_snapshot），
关键作用是：让 component_type 在 RENDERER_DISPATCH 中命中，避免多 sheet dispatch
循环把 M9 各 sheet 误判为非白名单而重写成 onlyoffice-sheet。

科目4103其他综合收益（**贷方/权益类！**）：期末=期初+贷方-借方
M股东权益循环中的权益类科目。OCI增加时贷方增加，重分类进损益/减少时借方减少。
OCI汇聚多来源：G8其他权益工具投资公允价值变动（不可重分类）、J2设定受益计划重计量
（不可重分类）、其他债权投资公允变动/现金流量套期/外币折算差额（可重分类）。
各项目按税后净额列示（税前发生-所得税影响=税后净额）。
数据持久化在 checklist_responses 表，item_id 前缀为 "M9-*"。

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

_M9_ACCOUNT_CODE = "4103"
_ADJUDICATED_ITEM_ID = "M9-1-adjudicated-amount"

M9_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "m9-other-comprehensive-income"},
    {"sheet_name": "其他综合收益实质性程序表M9A", "component_type": "m9-other-comprehensive-income"},
    {"sheet_name": "审定表M9-1", "component_type": "m9-other-comprehensive-income"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "m9-other-comprehensive-income"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "m9-other-comprehensive-income"},
    {"sheet_name": "明细表M9-2", "component_type": "m9-other-comprehensive-income"},
    {"sheet_name": "调整分录汇总M9-3", "component_type": "m9-other-comprehensive-income"},
    {"sheet_name": "其他综合收益核对表M9-4", "component_type": "m9-other-comprehensive-income"},
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


def validate_after_tax_net(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """校验OCI税后净额公式：税后净额=税前发生-所得税影响.

    每行应含 pre_tax/tax_effect/after_tax_net 字段。
    返回校验失败的行列表。
    """
    errors: list[dict[str, Any]] = []
    for row in rows:
        pre_tax = _parse_num(row.get("pre_tax") or row.get("pre_tax_amount"))
        tax_effect = _parse_num(row.get("tax_effect") or row.get("income_tax_effect"))
        after_tax = _parse_num(row.get("after_tax_net") or row.get("net_of_tax"))
        expected = pre_tax - tax_effect
        if abs(after_tax - expected) > TOLERANCE:
            errors.append({
                "row_key": row.get("row_key", ""),
                "pre_tax": pre_tax,
                "tax_effect": tax_effect,
                "actual_after_tax": after_tax,
                "expected_after_tax": expected,
                "diff": round(after_tax - expected, 2),
            })
    return errors


# ─── TB 取数 ─────────────────────────────────────────────────────────────────


async def _fetch_tb_data(ctx: RenderContext) -> dict[str, Any]:
    """从 tb_balance 取科目4103其他综合收益余额数据."""
    result: dict[str, Any] = {
        "account_code": _M9_ACCOUNT_CODE,
        "account_name": "其他综合收益",
        "direction": "credit",
        "begin_balance": 0,
        "debit_amount": 0,
        "credit_amount": 0,
        "end_balance": 0,
    }
    try:
        active_filter = get_active_filter(ctx.project_id)
        stmt = (
            sa.select(
                TbBalance.begin_balance,
                TbBalance.debit_amount,
                TbBalance.credit_amount,
                TbBalance.end_balance,
            )
            .where(
                TbBalance.project_id == str(ctx.project_id),
                TbBalance.standard_account_code == _M9_ACCOUNT_CODE,
                active_filter,
            )
            .limit(1)
        )
        row = (await ctx.db.execute(stmt)).fetchone()
        if row:
            result["begin_balance"] = _parse_num(row.begin_balance)
            result["debit_amount"] = _parse_num(row.debit_amount)
            result["credit_amount"] = _parse_num(row.credit_amount)
            result["end_balance"] = _parse_num(row.end_balance)
    except Exception as e:  # noqa: BLE001
        logger.warning("M9 render: TB 取数失败: %s", e)
    return result


# ─── 主渲染函数 ───────────────────────────────────────────────────────────────


async def render(ctx: RenderContext) -> dict[str, Any]:
    """M9 其他综合收益专属渲染策略.

    轻量返回：project_context + responses_snapshot + TB数据 + 公式校验。
    前端 GtM9OtherComprehensiveIncome 为自加载组件（各子组件独立拉取 checklist_responses）。
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
                {"wid": str(ctx.workpaper_id)},
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
        logger.warning("M9 render: checklist_responses 查询失败: %s", e)

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
        logger.warning("M9 render: project context 查询失败: %s", e)

    # ─── TB 取数（科目4103其他综合收益）─────────────────────────────────
    tb = await _fetch_tb_data(ctx)

    # ─── 公式校验（从快照提取结构化数据行）────────────────────────────────
    formula_errors: list[dict[str, Any]] = []
    formula_rows: list[dict[str, Any]] = []
    after_tax_errors: list[dict[str, Any]] = []
    after_tax_rows: list[dict[str, Any]] = []

    for item_id, data in responses_snapshot.items():
        if not item_id.startswith("M9-"):
            continue
        raw = data.get("conclusion", "")
        if raw and isinstance(raw, str) and raw.startswith("{"):
            try:
                parsed = json.loads(raw)
                if not isinstance(parsed, dict):
                    continue
                # 权益类余额公式校验（审定表M9-1行）
                if item_id.startswith("M9-1-") and any(
                    k in parsed for k in ("begin", "opening", "period_begin", "end_balance")
                ):
                    parsed["row_key"] = item_id
                    formula_rows.append(parsed)
                # OCI税后净额校验（明细表M9-2行）
                if item_id.startswith("M9-2-") and any(
                    k in parsed for k in ("pre_tax", "pre_tax_amount", "after_tax_net", "net_of_tax")
                ):
                    parsed["row_key"] = item_id
                    after_tax_rows.append(parsed)
            except (json.JSONDecodeError, TypeError):
                pass

    if formula_rows:
        formula_errors = validate_equity_formula(formula_rows)
    if after_tax_rows:
        after_tax_errors = validate_after_tax_net(after_tax_rows)

    return {
        "account_code": _M9_ACCOUNT_CODE,
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "adjudicated_amount": adjudicated_amount,
        # TB 余额数据（科目4103，贷方/权益类）
        "trial_balance": tb,
        # 权益类公式方向元数据（前端可用于初始化校验）
        "formula_direction": {
            "account_code": "4103",
            "account_name": "其他综合收益",
            "direction": "credit",  # 贷方/权益类！
            "end_balance_formula": "begin + credit - debit",  # 期末=期初+贷方-借方
            "note": (
                "权益类贷方科目：OCI增加（公允变动/重计量）在贷方增加，"
                "重分类进损益/减少在借方减少。"
                "按税后净额列示，分两大类（不可重分类+可重分类进损益）"
            ),
        },
        # OCI 特有元数据
        "oci_metadata": {
            "categories": ["non_reclassifiable", "reclassifiable"],
            "sources": [
                {"code": "G8", "name": "其他权益工具投资公允价值变动", "category": "non_reclassifiable"},
                {"code": "J2", "name": "设定受益计划重计量", "category": "non_reclassifiable"},
                {"code": "G6", "name": "其他债权投资公允价值变动", "category": "reclassifiable"},
                {"code": "hedge", "name": "现金流量套期损益", "category": "reclassifiable"},
                {"code": "fx", "name": "外币财务报表折算差额", "category": "reclassifiable"},
            ],
            "after_tax_formula": "pre_tax - tax_effect",
            "reconcile_formula": "source_amount - booked_oci",
        },
        # 跨底稿引用（G8→M9 OCI核对, J2→M9 OCI核对）
        "cross_wp_references": [
            {
                "ref_id": "CW-403",
                "source_wp": "G8",
                "target_wp": "M9",
                "direction": "from",
                "label": "G8其他权益工具投资公允价值变动→M9 OCI核对(不可重分类)",
                "event": "g8:fair-value-changed",
            },
            {
                "ref_id": "CW-404",
                "source_wp": "J2",
                "target_wp": "M9",
                "direction": "from",
                "label": "J2设定受益计划重计量→M9 OCI核对(不可重分类)",
                "event": "j2:remeasured",
            },
        ],
        # 公式校验错误（前端可展示红色提示）
        "formula_errors": formula_errors,
        # OCI税后净额校验错误
        "after_tax_errors": after_tax_errors,
        # sheet 列表元数据
        "sheets": M9_SHEETS,
        "component_type": "m9-other-comprehensive-income",
    }
