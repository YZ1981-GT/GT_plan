"""L6 专项应付款 — 专属渲染策略.

component_type = "l6-special-payables"

L6 前端组件 GtL6SpecialPayables 为自加载组件（子组件各自拉取 checklist-responses），
按 sheetName 分发到各子组件（审定表/明细/调整分录/检查表/附注等）。因此本渲染策略只需
返回轻量 html_data（project_context + responses_snapshot），关键作用是：让 component_type
在 RENDERER_DISPATCH 中命中，避免多 sheet dispatch 循环把 L6 各 sheet 误判为非白名单
而重写成 onlyoffice-sheet。

科目2601专项应付款（贷方/负债类！）：期末=期初+贷方-借方
L筹资循环标准负债底稿，专款专用核查为核心程序。
数据持久化在 checklist_responses 表，item_id 前缀为 "L6-*"。

负债类公式验证逻辑：
- 期末 = 期初 + 贷方 - 借方（负债类标准公式）
- 期末不应为负（专项应付款余额异常检测）

Requirements: 1.6
"""

from __future__ import annotations

import json
import logging
from typing import Any

import sqlalchemy as sa

from ._context import RenderContext
from ._lmn_tb_helper import fetch_tb_for_balance

logger = logging.getLogger(__name__)

# ─── 负债类公式验证（纯函数，可独立测试）─────────────────────────────────

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


def calc_liability_end_balance(begin: float, credit: float, debit: float) -> float:
    """负债类期末余额公式：期末 = 期初 + 贷方 - 借方."""
    return begin + credit - debit


def validate_liability_formula(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """校验一组行的负债类公式：期末 = 期初 + 贷方 - 借方.

    每行 dict 需含: begin/opening, credit, debit, end/closing 字段。
    返回 [{row_key, field, message, variance}] 错误列表。
    """
    errors: list[dict[str, Any]] = []
    for row in rows:
        row_key = str(row.get("row_key") or row.get("rowKey") or row.get("item_id") or "")
        begin = _parse_num(row.get("begin") or row.get("opening") or row.get("period_begin"))
        credit = _parse_num(row.get("credit") or row.get("period_credit") or row.get("increase"))
        debit = _parse_num(row.get("debit") or row.get("period_debit") or row.get("decrease"))
        end = _parse_num(row.get("end") or row.get("closing") or row.get("end_balance"))

        if end == 0.0 and begin == 0.0 and credit == 0.0 and debit == 0.0:
            continue  # 全零行跳过

        expected = calc_liability_end_balance(begin, credit, debit)
        variance = expected - end
        if abs(variance) > TOLERANCE:
            errors.append({
                "row_key": row_key,
                "field": "end_balance",
                "message": f"负债类公式不平衡: 期末应为 {expected:.2f}, 实际 {end:.2f}",
                "variance": round(variance, 2),
            })
    return errors


def detect_negative_balances(
    responses_snapshot: dict[str, Any],
) -> list[dict[str, str]]:
    """检测 L6-* response 中 end_balance < 0 的条目，返回警告列表."""
    warnings: list[dict[str, str]] = []
    for item_id, data in responses_snapshot.items():
        if not item_id.startswith("L6-"):
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
                        "message": f"专项应付款余额异常：{item_id} 期末为负({end_bal:.2f})",
                    })
    return warnings


async def render(ctx: RenderContext) -> dict | None:
    """L6 专项应付款渲染策略 — 返回轻量 html_data。

    返回 dict（非 grid cells），确保前端 GtWpRenderer 走 rendererEntry 分发到
    GtL6SpecialPayables，而非 grid 兜底或 OnlyOffice。

    包含负债类公式验证元数据 + 负余额警告，供前端初始化时校验方向正确性。
    """
    wp_id = ctx.wp_id
    db = ctx.db

    # ─── 从 checklist_responses 加载 L6-* 数据快照 ───────────────────────
    responses_snapshot: dict = {}
    try:
        result = await db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark "
                "FROM checklist_responses WHERE wp_id = :wp_id "
                "AND item_id LIKE 'L6-%' "
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
        logger.warning("L6 render: checklist_responses 查询失败 wp_id=%s: %s", wp_id, e)

    # ─── 项目上下文 ──────────────────────────────────────────────────────
    project_context: dict = {
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
        logger.warning("L6 render: project context 查询失败: %s", e)

    # ─── 负余额检测 ─────────────────────────────────────────────────────
    negative_balance_warnings = detect_negative_balances(responses_snapshot)

    # ─── TB 取数（L 循环四表取数 spec） ─────────────────────────────────────
    tb = await fetch_tb_for_balance(ctx, "2601")

    return {
        "sheet_name": ctx.classification.sheet_name if ctx.classification else "",
        "project_context": project_context,
        "responses_snapshot": responses_snapshot,
        # 负债类公式方向元数据（前端可用于初始化校验）
        "formula_direction": {
            "account_code": "2601",
            "account_name": "专项应付款",
            "direction": "credit",  # 贷方/负债类
            "end_balance_formula": "begin + credit - debit",  # 期末=期初+贷方-借方
        },
        # 负余额警告（前端可展示黄色提示）
        "negative_balance_warnings": negative_balance_warnings,
        "trial_balance": tb,
    }
