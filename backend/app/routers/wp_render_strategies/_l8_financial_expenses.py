"""L8 财务费用 — 专属渲染策略.

component_type = "l8-financial-expenses"

L8 前端组件 GtL8FinancialExpenses 为自加载组件（子组件各自拉取 checklist-responses），
按 sheetName 分发到各子组件（审定表/明细/利息测算/截止测试/检查表/调整/附注等）。
因此本渲染策略只需返回轻量 html_data（project_context + responses_snapshot），
关键作用是：让 component_type 在 RENDERER_DISPATCH 中命中，避免多 sheet dispatch
循环把 L8 各 sheet 误判为非白名单而重写成 onlyoffice-sheet。

科目6603财务费用（**损益类！取发生额**）：本期发生额=借方发生-贷方发生
L筹资循环利息汇聚终点（接收L1/L3/L4利息测算+L5摊销）。
数据持久化在 checklist_responses 表，item_id 前缀为 "L8-*"。

损益类公式验证逻辑：
- 本期发生额 = 借方发生 - 贷方发生（费用类科目）
- 净财务费用 = 利息支出 - 利息收入 + 汇兑损益 + 手续费 + 其他

Requirements: 1.6, 2.4
"""

from __future__ import annotations

import logging
from typing import Any

import sqlalchemy as sa

from app.models.audit_platform_models import TbLedger
from app.services.dataset_query import get_active_filter

from app.services.l_cycle_extraction.render_support import build_l_tb_payload

from ._context import RenderContext

logger = logging.getLogger(__name__)

# ─── 损益类发生额公式验证（纯函数，可独立测试）─────────────────────────────

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


def calc_occurrence(debit_occur: float, credit_occur: float) -> float:
    """损益类本期发生额 = 借方发生 - 贷方发生（费用类科目为借方）."""
    return debit_occur - credit_occur


def validate_occurrence_formula(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """校验一组行的损益类发生额公式：发生额 = 借方发生 - 贷方发生.

    每行 dict 需含: debit_occur, credit_occur, occurrence 字段。
    返回 [{row_key, field, message, variance}] 错误列表。
    """
    errors: list[dict[str, Any]] = []
    for row in rows:
        row_key = str(row.get("row_key") or row.get("rowKey") or row.get("item_id") or "")
        debit = _parse_num(row.get("debit_occur") or row.get("debitOccur") or row.get("period_debit"))
        credit = _parse_num(row.get("credit_occur") or row.get("creditOccur") or row.get("period_credit"))
        reported = _parse_num(row.get("occurrence") or row.get("current_amount") or row.get("amount"))

        if debit == 0.0 and credit == 0.0 and reported == 0.0:
            continue  # 全零行跳过

        expected = calc_occurrence(debit, credit)
        variance = expected - reported
        if abs(variance) > TOLERANCE:
            errors.append({
                "row_key": row_key,
                "field": "occurrence",
                "message": f"损益类发生额不平衡: 应为 {expected:.2f}, 实际 {reported:.2f}",
                "variance": round(variance, 2),
            })
    return errors


async def _get_occurrence_from_ledger(
    db: Any,
    project_id: Any,
    year: int,
    account_code: str = "6603",
) -> dict[str, float]:
    """从 tb_ledger 取指定科目的借方/贷方发生额汇总.

    损益类科目取发生额（非余额！），从序时账聚合。
    使用 account_code LIKE '{code}%' 包含所有明细科目。

    Returns:
        {"debit_total": float, "credit_total": float, "occurrence": float}
    """
    debit_total = 0.0
    credit_total = 0.0
    try:
        active_filter = await get_active_filter(
            db, TbLedger.__table__, project_id, year
        )
        tbl = TbLedger.__table__
        stmt = sa.select(
            sa.func.coalesce(sa.func.sum(tbl.c.debit_amount), 0).label("debit_total"),
            sa.func.coalesce(sa.func.sum(tbl.c.credit_amount), 0).label("credit_total"),
        ).where(
            sa.and_(
                active_filter,
                tbl.c.account_code.like(f"{account_code}%"),
            )
        )
        result = await db.execute(stmt)
        row = result.fetchone()
        if row:
            debit_total = float(row.debit_total or 0)
            credit_total = float(row.credit_total or 0)
    except Exception as e:  # noqa: BLE001
        logger.warning("L8 render: tb_ledger 发生额查询失败 account=%s: %s", account_code, e)

    return {
        "debit_total": round(debit_total, 2),
        "credit_total": round(credit_total, 2),
        "occurrence": round(debit_total - credit_total, 2),
    }


async def render(ctx: RenderContext) -> dict | None:
    """L8 财务费用渲染策略 — 返回轻量 html_data。

    返回 dict（非 grid cells），确保前端 GtWpRenderer 走 rendererEntry 分发到
    GtL8FinancialExpenses，而非 grid 兜底或 OnlyOffice。

    包含损益类发生额验证元数据，供前端初始化时校验方向正确性。
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 从 checklist_responses 加载 L8-* 数据快照 ───────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'L8-%' "
                "LIMIT 3000"
            ),
            {"wp_id": str(wp_id)},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("L8 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 项目上下文 ──────────────────────────────────────────────────────
    project_context: dict = {
        "client_name": "",
        "audit_year": "",
        "business_category": ctx.business_category or "",
    }
    audit_year: int = 2025
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
            audit_year = int(proj_row.audit_year or 2025)
    except Exception as e:  # noqa: BLE001
        logger.warning("L8 render: project context 查询失败: %s", e)

    # ─── 从 tb_ledger 取损益类发生额（6603财务费用）──────────────────────
    occurrence_data = await _get_occurrence_from_ledger(
        db, ctx.project_id, audit_year, "6603"
    )

    # ─── TB 取数（L 循环四表取数 spec） ─────────────────────────────────────
    # 🔴 改造前此处用 fetch_tb_for_income(ctx, "6603") → debit-credit 恒 0
    #    （含年末结转损益的全年账 debit == credit，DB 实证 543,020,073.49 双侧相等）。
    #    现改走 trial_balance 本期发生额权威口径。
    tb_payload = await build_l_tb_payload(ctx, "L8")
    resolved_code = "/".join(tb_payload["tb_source_codes"].get("gross_standard") or [])

    return {
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        # 损益类公式方向元数据（前端可用于初始化校验）
        "formula_direction": {
            "account_code": resolved_code,
            "account_name": "财务费用",
            "direction": "debit",  # 借方/损益类费用
            "occurrence_formula": "trial_balance.unadjusted_amount（本期发生额权威口径）",
        },
        # tb_ledger 发生额（前端审定表 seed 数据 —— 保留兼容，但已知恒 0 问题）
        "occurrence_from_ledger": occurrence_data,
        **tb_payload,
    }

