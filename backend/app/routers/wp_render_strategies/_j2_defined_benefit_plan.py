"""J2 设定受益计划 — 专属渲染策略.

科目：2221长期应付职工薪酬（贷方/负债类）
公式：期末=期初+贷方-借方
精算核心：DBO六要素分解 + ISA620专家利用

Spec: .kiro/specs/j2-defined-benefit-plan/
Requirements: 1.1, 5.1
"""
from __future__ import annotations
import json
import logging
import sqlalchemy as sa

from app.models.audit_platform_models import TbBalance
from app.services.dataset_query import get_active_filter

from ._context import RenderContext

logger = logging.getLogger(__name__)

J2_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "j2-defined-benefit-plan"},
    {"sheet_name": "长期应付职工薪酬实质性程序表 J2A", "component_type": "j2-defined-benefit-plan"},
    {"sheet_name": "审定表J2-1", "component_type": "j2-defined-benefit-plan"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "j2-defined-benefit-plan"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "j2-defined-benefit-plan"},
    {"sheet_name": "明细表J2-2", "component_type": "j2-defined-benefit-plan"},
    {"sheet_name": "调整分录汇总表J2-3", "component_type": "j2-defined-benefit-plan"},
    {"sheet_name": "计提情况检查表J2-4", "component_type": "j2-defined-benefit-plan"},
]

ACCOUNT_CODE = "2221"

_J2_ACCOUNT_PREFIX = "2221"


async def _build_adjudication_prefill(ctx: RenderContext) -> list[dict]:
    """从 tb_balance 2221 明细子科目预填 J2-1 审定表行（负债类取余额）.

    2221 长期应付职工薪酬为负债/贷方科目：
    期初未审 = ABS(opening_balance)
    期末未审 = ABS(closing_balance)
    返回 [{name, code, opening_balance, closing_balance}]，前端在无持久化行时据此建行。
    """
    rows: list[dict] = []
    try:
        active_filter = await get_active_filter(
            ctx.db, TbBalance.__table__, ctx.project_id, ctx.year
        )
        result = await ctx.db.execute(
            sa.select(
                TbBalance.account_code.label("code"),
                TbBalance.account_name.label("name"),
                sa.func.sum(TbBalance.opening_balance).label("opening"),
                sa.func.sum(TbBalance.closing_balance).label("closing"),
            )
            .where(
                active_filter,
                TbBalance.account_code.startswith(_J2_ACCOUNT_PREFIX),
                TbBalance.account_code != _J2_ACCOUNT_PREFIX,
            )
            .group_by(TbBalance.account_code, TbBalance.account_name)
        )
        raw = [
            {
                "code": (r.code or "").strip(),
                "name": (r.name or "").strip(),
                "opening": float(r.opening or 0),
                "closing": float(r.closing or 0),
            }
            for r in result.fetchall()
        ]
        all_codes = [x["code"] for x in raw if x["code"]]

        def _is_leaf(code: str) -> bool:
            if not code:
                return True
            return not any(c != code and c.startswith(code) for c in all_codes)

        leaves = [x for x in raw if _is_leaf(x["code"])]
        leaves.sort(key=lambda x: abs(x["closing"]), reverse=True)
        for x in leaves:
            name = x["name"]
            opening = x["opening"]
            closing = x["closing"]
            if not name or (abs(opening) < 0.005 and abs(closing) < 0.005):
                continue
            rows.append({
                "name": name,
                "code": x["code"],
                "opening_balance": abs(opening),
                "closing_balance": abs(closing),
            })
    except Exception as e:  # noqa: BLE001
        logger.warning("J2 adjudication prefill build failed: %s", e)
    return rows


async def render(ctx: RenderContext) -> dict | None:
    """渲染 J2 设定受益计划底稿数据.

    负债类贷方：从 trial_balance 读取 2221 余额，
    从 checklist_responses 读取精算假设、ISA620评估、审定表数据。
    """
    responses_snapshot: dict = {}
    tb_data: dict = {}

    # ─── 读取 trial_balance 2221 余额 ─────────────────────────────────────
    try:
        tb_result = await ctx.db.execute(
            sa.text(
                "SELECT unadjusted_amount, aje_adjustment, audited_amount "
                "FROM trial_balance "
                "WHERE project_id = :pid AND year = :year "
                "AND standard_account_code = :code LIMIT 1"
            ),
            {"pid": str(ctx.project_id), "year": ctx.year, "code": ACCOUNT_CODE},
        )
        tb_row = tb_result.fetchone()
        if tb_row:
            tb_data = {
                "unadjusted_amount": float(tb_row.unadjusted_amount or 0),
                "aje_adjustment": float(tb_row.aje_adjustment or 0),
                "audited_amount": float(tb_row.audited_amount or 0),
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("J2 render TB read failed: %s", e)

    # ─── 读取 checklist_responses ──────────────────────────────────────────
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 5000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "J2-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("J2 render checklist read failed: %s", e)

    # ─── 解析精算假设 ──────────────────────────────────────────────────────
    assumptions = _extract_json(responses_snapshot, "J2-actuarial-assumptions", {
        "discountRate": 0.04,
        "salaryGrowthRate": 0.08,
        "mortalityRate": 0.005,
        "turnoverRate": 0.10,
    })

    # ─── 解析 ISA620 数据 ─────────────────────────────────────────────────
    isa620 = _extract_json(responses_snapshot, "J2-isa620-evaluation", {})

    # ─── 解析审定表三区块 ─────────────────────────────────────────────────
    adjudication = _extract_json(responses_snapshot, "J2-adjudication-data", {})

    # ─── 解析明细表 ───────────────────────────────────────────────────────
    detail = _extract_json(responses_snapshot, "J2-detail-data", [])

    # ─── 预填审定表行 ─────────────────────────────────────────────────────
    adjudication_prefill = await _build_adjudication_prefill(ctx)

    return {
        "component_type": "j2-defined-benefit-plan",
        "account_code": ACCOUNT_CODE,
        "direction": "credit",
        "liability_formula": "end = begin + credit - debit",
        "tb_data": tb_data,
        "assumptions": assumptions,
        "isa620": isa620,
        "adjudication": adjudication,
        "detail": detail,
        "adjudication_prefill": adjudication_prefill,
        "responses": responses_snapshot,
        "sheets": J2_SHEETS,
    }


def _extract_json(responses: dict, key: str, default):
    """从 responses 中解析 JSON 数据（存于 remark 字段，对齐前端持久化）."""
    raw = responses.get(key, {})
    if raw and raw.get("remark"):
        try:
            return json.loads(raw["remark"])
        except (json.JSONDecodeError, TypeError):
            pass
    return default


# ─── 负债类公式验证（后端校验） ─────────────────────────────────────────────

def validate_liability_balance(begin: float, credit: float, debit: float, expected_end: float) -> bool:
    """验证负债类期末余额: end = begin + credit - debit."""
    calculated = begin + credit - debit
    return abs(calculated - expected_end) < 0.01


def validate_dbo_decomposition(
    begin_dbo: float,
    service_cost: float,
    interest_cost: float,
    actuarial_loss: float,
    actuarial_gain: float,
    benefits_paid: float,
    expected_end: float,
) -> bool:
    """验证DBO期末完整公式: end = begin + service + interest + loss - gain - paid."""
    calculated = begin_dbo + service_cost + interest_cost + actuarial_loss - actuarial_gain - benefits_paid
    return abs(calculated - expected_end) < 0.01
