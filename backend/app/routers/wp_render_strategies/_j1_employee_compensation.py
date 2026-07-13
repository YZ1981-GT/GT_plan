"""J1 应付职工薪酬 — 专属渲染策略.

科目：2211应付职工薪酬（贷方/负债类）
公式：期末=期初+贷方-借方
核心：薪酬测算(人数×均薪×月数) + 社保(基数×比例×月数) + 分配闭合 + K8/K9联动

Spec: .kiro/specs/j1-employee-compensation/
Requirements: 1.1, 5.1
"""
from __future__ import annotations
import json
import logging
import sqlalchemy as sa
from ._context import RenderContext

logger = logging.getLogger(__name__)

J1_SHEETS = [
    {"sheet_name": "底稿目录", "component_type": "j1-employee-compensation"},
    {"sheet_name": "应付职工薪酬实质性程序表 J1A", "component_type": "j1-employee-compensation"},
    {"sheet_name": "审定表J1-1", "component_type": "j1-employee-compensation"},
    {"sheet_name": "附注披露信息（上市公司）", "component_type": "j1-employee-compensation"},
    {"sheet_name": "附注披露信息（国有企业）", "component_type": "j1-employee-compensation"},
    {"sheet_name": "明细表J1-2", "component_type": "j1-employee-compensation"},
    {"sheet_name": "调整分录汇总表J1-3", "component_type": "j1-employee-compensation"},
    {"sheet_name": "月度分析表J1-4", "component_type": "j1-employee-compensation"},
    {"sheet_name": "与同行业对比分析表J1-5", "component_type": "j1-employee-compensation"},
    {"sheet_name": "计提情况检查表J1-6", "component_type": "j1-employee-compensation"},
    {"sheet_name": "分配情况检查表J1-7", "component_type": "j1-employee-compensation"},
    {"sheet_name": "检查表J1-8", "component_type": "j1-employee-compensation"},
    {"sheet_name": "非货币性福利检查表J1-9", "component_type": "j1-employee-compensation"},
    {"sheet_name": "辞退福利检查表J1-10", "component_type": "j1-employee-compensation"},
]

ACCOUNT_CODE = "2211"


async def render(ctx: RenderContext) -> dict | None:
    """渲染 J1 应付职工薪酬底稿数据.

    负债类贷方：从 trial_balance 读取 2211 余额，
    从 checklist_responses 读取薪酬明细、月度数据、检查表数据。
    """
    responses_snapshot: dict = {}
    tb_data: dict = {}

    # ─── 读取 trial_balance 2211 余额 ─────────────────────────────────────
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
        logger.warning("J1 render TB read failed: %s", e)

    # ─── 读取 checklist_responses ──────────────────────────────────────────
    try:
        result = await ctx.db.execute(
            sa.text(
                "SELECT item_id, conclusion, remark FROM checklist_responses "
                "WHERE wp_id = :wp_id AND item_id LIKE :pfx LIMIT 10000"
            ),
            {"wp_id": str(ctx.wp_id), "pfx": "J1-%"},
        )
        for row in result.fetchall():
            responses_snapshot[row.item_id] = {
                "conclusion": row.conclusion or "",
                "remark": row.remark or "",
            }
    except Exception as e:  # noqa: BLE001
        logger.warning("J1 render checklist read failed: %s", e)

    # ─── 解析审定表数据 ───────────────────────────────────────────────────
    adjudication_rows = _extract_json(responses_snapshot, "J1-adjudication-data", [])

    # ─── 解析明细表数据 ───────────────────────────────────────────────────
    detail_rows = _extract_json(responses_snapshot, "J1-detail-data", [])

    # ─── 解析月度分析 ─────────────────────────────────────────────────────
    monthly_rows = _extract_json(responses_snapshot, "J1-monthly-data", [])

    # ─── 解析行业对比 ─────────────────────────────────────────────────────
    industry_compare_rows = _extract_json(responses_snapshot, "J1-industry-data", [])
    company_info = _extract_json(responses_snapshot, "J1-company-info", {})

    # ─── 解析5类检查表 ────────────────────────────────────────────────────
    accrual_check_rows = _extract_json(responses_snapshot, "J1-accrual-check", [])
    allocation_check_rows = _extract_json(responses_snapshot, "J1-allocation-check", [])
    general_check_rows = _extract_json(responses_snapshot, "J1-general-check", [])
    non_monetary_rows = _extract_json(responses_snapshot, "J1-non-monetary", [])
    severance_check_rows = _extract_json(responses_snapshot, "J1-severance-check", [])
    cas9_conditions = _extract_json(responses_snapshot, "J1-cas9-conditions", [])

    # ─── 解析附注数据 ─────────────────────────────────────────────────────
    disclosure_listed_rows = _extract_json(responses_snapshot, "J1-disclosure-listed", [])
    disclosure_soe_rows = _extract_json(responses_snapshot, "J1-disclosure-soe", [])

    return {
        "component_type": "j1-employee-compensation",
        "account_code": ACCOUNT_CODE,
        "direction": "credit",
        "liability_formula": "end = begin + credit - debit",
        "tb_data": tb_data,
        "adjudication_rows": adjudication_rows,
        "detail_rows": detail_rows,
        "monthly_rows": monthly_rows,
        "industry_compare_rows": industry_compare_rows,
        "company_info": company_info,
        "accrual_check_rows": accrual_check_rows,
        "allocation_check_rows": allocation_check_rows,
        "general_check_rows": general_check_rows,
        "non_monetary_rows": non_monetary_rows,
        "severance_check_rows": severance_check_rows,
        "cas9_conditions": cas9_conditions,
        "disclosure_listed_rows": disclosure_listed_rows,
        "disclosure_soe_rows": disclosure_soe_rows,
        "responses": responses_snapshot,
        "sheets": J1_SHEETS,
    }


def _extract_json(responses: dict, key: str, default):
    """从 responses 中解析 JSON 数据."""
    raw = responses.get(key, {})
    if raw and raw.get("content"):
        try:
            return json.loads(raw["content"])
        except (json.JSONDecodeError, TypeError):
            pass
    return default


# ─── 负债类公式验证（后端校验） ─────────────────────────────────────────────

def validate_liability_balance(begin: float, credit: float, debit: float, expected_end: float) -> bool:
    """验证负债类期末余额: end = begin + credit - debit."""
    calculated = begin + credit - debit
    return abs(calculated - expected_end) < 0.01


def validate_salary_estimate(headcount: int, avg_salary: float, months: int, expected: float) -> bool:
    """验证工资测算: 人数×均薪×月数."""
    calculated = headcount * avg_salary * months
    return abs(calculated - expected) < 0.01


def validate_allocation_closure(allocated: list[float], total: float) -> tuple[bool, float]:
    """验证分配闭合: Σ各科目 = 薪酬总额."""
    allocated_total = sum(allocated)
    diff = allocated_total - total
    return abs(diff) < 0.01, diff
