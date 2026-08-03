"""M3 库存股 — 专属渲染策略.

component_type = "m3-treasury-stock"

M3 前端组件 GtM3TreasuryStock 为自加载组件（子组件各自拉取 checklist-responses），
按 sheetName 分发到各子组件（审定表/明细(回购批次)/外币折算/检查表/调整/附注等）。
因此本渲染策略只需返回轻量 html_data（project_context + responses_snapshot），
关键作用是：让 component_type 在 RENDERER_DISPATCH 中命中，避免多 sheet dispatch
循环把 M3 各 sheet 误判为非白名单而重写成 onlyoffice-sheet。

科目4002库存股（**借方/权益备抵类！**）：期末=期初+借方-贷方
M股东权益循环中唯一的备抵科目。回购在借方增加，注销/再售在贷方减少。
数据持久化在 checklist_responses 表，item_id 前缀为 "M3-*"。

权益备抵类公式验证逻辑（铁律！）：
- 期末 = 期初 + 借方 - 贷方（权益备抵类/借方科目）
- 回购股份（借记库存股，贷记银行存款）→ 借方增加
- 注销/再出售（贷记库存股）→ 贷方减少
- 方向与 M2/M4/M5/M6 等权益类（贷方增加）完全相反！

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
from app.services.four_table.m_cycle_specs import M3_SPEC

logger = logging.getLogger(__name__)

_M3_ACCOUNT_CODE = "4201"
_ADJUDICATED_ITEM_ID = "M3-1-adjudicated-amount"

M3_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "m3-treasury-stock"},
    {"sheet_name": "库存股实质性程序表M3A", "component_type": "m3-treasury-stock"},
    {"sheet_name": "审定表M3-1", "component_type": "m3-treasury-stock"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "m3-treasury-stock"},
    {"sheet_name": "明细表M3-2", "component_type": "m3-treasury-stock"},
    {"sheet_name": "调整分录汇总M3-3", "component_type": "m3-treasury-stock"},
    {"sheet_name": "外币投资汇率测算表M3-4", "component_type": "m3-treasury-stock"},
    {"sheet_name": "库存股检查表M3-5", "component_type": "m3-treasury-stock"},
]

# ─── 权益备抵类公式验证（纯函数，可独立测试）─────────────────────────────────

TOLERANCE = 0.01


def _parse_num(v: Any) -> float:
    """安全解析数值，None/空/NaN→0.0."""
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        n = float(v)
        return n if n == n else 0.0  # noqa: PLR0124 — NaN check
    try:
        n = float(str(v).strip())
        return n if n == n else 0.0  # noqa: PLR0124
    except (TypeError, ValueError):
        return 0.0


def calc_contra_equity_end_balance(begin: float, debit: float, credit: float) -> float:
    """权益备抵类期末余额公式：期末 = 期初 + 借方 - 贷方（借方科目！）.

    库存股（4002）是所有者权益的备抵科目：
    - 回购股份 → 借方增加
    - 注销/再出售 → 贷方减少
    - 与 M2/M4/M5/M6 等权益类（贷方增加）方向完全相反！
    """
    return begin + debit - credit


def validate_contra_equity_formula(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """校验一组行的权益备抵类公式：期末 = 期初 + 借方 - 贷方.

    每行 dict 需含: begin/opening, debit, credit, end/closing 字段。
    返回 [{row_key, field, message, variance}] 错误列表。
    """
    errors: list[dict[str, Any]] = []
    for row in rows:
        row_key = str(row.get("row_key") or row.get("rowKey") or row.get("item_id") or "")
        begin = _parse_num(row.get("begin") or row.get("opening") or row.get("period_begin"))
        debit = _parse_num(row.get("debit") or row.get("period_debit") or row.get("increase"))
        credit = _parse_num(row.get("credit") or row.get("period_credit") or row.get("decrease"))
        end = _parse_num(row.get("end") or row.get("closing") or row.get("end_balance"))

        if end == 0.0 and begin == 0.0 and debit == 0.0 and credit == 0.0:
            continue  # 全零行跳过

        expected = calc_contra_equity_end_balance(begin, debit, credit)
        variance = expected - end
        if abs(variance) > TOLERANCE:
            errors.append({
                "row_key": row_key,
                "field": "end_balance",
                "message": f"权益备抵类公式不平衡: 期末应为 {expected:.2f}, 实际 {end:.2f}"
                f"（公式: 期初{begin:.2f}+借方{debit:.2f}-贷方{credit:.2f}）",
                "variance": round(variance, 2),
            })
    return errors


def detect_negative_balances(
    responses_snapshot: dict[str, Any],
) -> list[dict[str, str]]:
    """检测 M3-* response 中 end_balance < 0 的条目.

    注意：库存股为借方余额（正数），期末为负通常表示注销超出回购——异常！
    返回警告列表。
    """
    warnings: list[dict[str, str]] = []
    for item_id, data in responses_snapshot.items():
        if not item_id.startswith("M3-"):
            continue
        for field_name in ("conclusion", "remark"):
            raw = data.get(field_name, "")
            if not raw:
                continue
            try:
                parsed = json.loads(raw) if isinstance(raw, str) and raw.startswith("{") else None
            except (json.JSONDecodeError, TypeError):
                parsed = None
            if isinstance(parsed, dict):
                end_bal = _parse_num(parsed.get("end_balance") or parsed.get("closing") or 0)
                if end_bal < -TOLERANCE:
                    warnings.append({
                        "item_id": item_id,
                        "end_balance": f"{end_bal:.2f}",
                        "message": f"库存股余额异常：{item_id} 期末为负({end_bal:.2f})，"
                        "注销可能超出回购，请核查",
                    })
    return warnings


# ─── TB 取数 ─────────────────────────────────────────────────────────────


async def _fetch_tb_data(ctx: RenderContext) -> dict[str, Any]:
    """查 tb_balance 科目 4201 的期初/借方/贷方余额.

    库存股为权益备抵借方科目：
    - debit_amount → 本期借方发生额（回购增加）
    - credit_amount → 本期贷方发生额（注销/再售减少）
    - 期末余额 = 期初 + 借方 - 贷方
    """

    # 科目定位（语义驱动）
    try:
        _sem_accounts = await resolve_semantic_accounts(ctx, M3_SPEC)
    except Exception:  # noqa: BLE001
        _sem_accounts = None

    tb: dict[str, Any] = {}
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        result = await ctx.db.execute(
            sa.select(
                TbBalance.account_code,
                TbBalance.debit_amount,
                TbBalance.credit_amount,
            ).where(
                active_filter,
                TbBalance.account_code.like(_M3_ACCOUNT_CODE + "%"),
            )
        )
        total_debit = 0.0
        total_credit = 0.0
        matched = False
        for row in result.fetchall():
            total_debit += float(row.debit_amount or 0)
            total_credit += float(row.credit_amount or 0)
            matched = True

        if matched:
            # 权益备抵类借方：current_amount = debit - credit（借方净额）
            tb = {
                "debit_amount": total_debit,
                "credit_amount": total_credit,
                "current_amount": total_debit - total_credit,
                "direction": "debit",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("M3 TB fetch failed for account %s: %s", _M3_ACCOUNT_CODE, e)
    return tb


# ─── 渲染主入口 ─────────────────────────────────────────────────────────────


async def render(ctx: RenderContext) -> dict | None:
    """M3 库存股渲染策略 — 返回轻量 html_data。

    返回 dict（非 grid cells），确保前端 GtWpRenderer 走 rendererEntry 分发到
    GtM3TreasuryStock，而非 grid 兜底或 OnlyOffice。

    包含：
    - project_context: 项目基础信息
    - responses_snapshot: M3-* 已有 checklist_responses 快照
    - trial_balance: 科目4002的TB余额数据（借方/贷方/净额）
    - formula_direction: 权益备抵类公式方向元数据
    - formula_errors: 公式校验错误列表（如果快照中有结构化数据）
    - negative_balance_warnings: 负余额异常警告
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 从 checklist_responses 加载 M3-* 数据快照 ───────────────────────
    responses_snapshot: dict = {}
    adjudicated_amount: str = ""
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'M3-%' "
                "LIMIT 3000"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
            if row.item_id == _ADJUDICATED_ITEM_ID:
                adjudicated_amount = row.conclusion or ""
    except Exception as e:  # noqa: BLE001
        logger.warning("M3 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 项目上下文 ──────────────────────────────────────────────────────
    project_context: dict[str, Any] = {
        "client_name": "",
        "audit_year": "",
        "business_category": ctx.business_category or "",
    }
    try:
        proj_row = (
            await db.execute(
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
        logger.warning("M3 render: project context 查询失败: %s", e)

    # ─── TB 取数（科目4002库存股）─────────────────────────────────────────
    tb = await _fetch_tb_data(ctx)

    # ─── 公式校验（从快照提取结构化数据行）────────────────────────────────
    formula_errors: list[dict[str, Any]] = []
    formula_rows: list[dict[str, Any]] = []
    for item_id, data in responses_snapshot.items():
        if not item_id.startswith("M3-1-"):
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
        formula_errors = validate_contra_equity_formula(formula_rows)

    # ─── 负余额检测 ─────────────────────────────────────────────────────
    negative_balance_warnings = detect_negative_balances(responses_snapshot)

    return {
        "account_code": _M3_ACCOUNT_CODE,
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        "adjudicated_amount": adjudicated_amount,
        # TB 余额数据（科目4002，借方/贷方/净额）
        "trial_balance": tb,
        # 权益备抵类公式方向元数据（前端可用于初始化校验）
        "formula_direction": {
            "account_code": "4002",
            "account_name": "库存股",
            "direction": "debit",  # 借方/权益备抵类！
            "end_balance_formula": "begin + debit - credit",  # 期末=期初+借方-贷方
            "note": "权益备抵类：回购在借方增加，注销在贷方减少，与M2/M4/M5/M6方向相反",
        },
        # 公式校验错误（前端可展示红色提示）
        "formula_errors": formula_errors,
        # 负余额警告（前端可展示黄色提示）
        "negative_balance_warnings": negative_balance_warnings,
        # sheet 列表元数据
        "sheets": M3_SHEETS,
        "component_type": "m3-treasury-stock",
    }
