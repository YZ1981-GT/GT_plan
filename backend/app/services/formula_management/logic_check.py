"""logic_check 收编 useReportCrossCheck 7 条硬编码勾稽（Task 4.1 / Req 6.4）。

本模块把前端 ``useReportCrossCheck.ts`` 的 ``computeCrossCheckResults`` 中 7 条
**硬编码不可编辑**的报表勾稽（资产=负债+权益、利润总额−所得税=净利润、有效
税率≈25% 等）落库为 7 条 **可编辑的 ``logic_check`` 公式**（种子数据）：

- 表达式引用经 ACNR **REPORT 域** row_code（``ROW('...')`` 形态，经
  ``full_resolve`` 归属 report 域，见 ``resolver._detect_non_wp_domain``）。
- 问题描述（``issue_description``）**沿用原 ``description``**（勾稽不通过时即
  作为 Issue_List 的问题项文案）。
- 语义**保持不变**：每条勾稽的 passed 判定逐条移植自前端 ``check()``——
  ``tolerance > 0`` 时 ``|round(diff, 2)| <= tolerance``，否则 ``|round(diff, 2)| < 0.01``。
  只是从"硬编码不可编辑"变为"可编辑 logic_check 公式"。

执行路径统一走 ``formula_management.engine.execute_formula``（logic_check 分派）：
条件表达式求值为真（!=0，即勾稽通过）→ 不产 Issue；求值为 0（勾稽不通过）→
向 Issue_List 追加一条以 ``description`` 为文案的问题项，**绝不修改任何数据值**。

Requirements: 6.4
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Optional

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import FinancialReport, FinancialReportType
from app.services.formula_engine import FormulaContext
from app.services.formula_management.engine import (
    FormulaRecord,
    IssueItem,
    execute_formula,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 引用键（ACNR REPORT 域 row_code）与候选解析键
# ─────────────────────────────────────────────────────────────────────────────
# 逻辑变量 → (row_cache 引用键[即表达式中 ROW('...') 的编码], 候选解析键列表)
# 候选键与前端 computeCrossCheckResults 的 get(map, ...keys) 逐一对齐，保持语义不变。
_BS_VARIABLES: dict[str, tuple[str, tuple[str, ...]]] = {
    # 资产总计
    "assets_total": ("assets_total", ("assets_total", "资产总计", "资产合计")),
    # 负债合计
    "liabilities_total": ("liabilities_total", ("liabilities_total", "负债合计", "负债总计")),
    # 所有者权益合计
    "equity_total": (
        "equity_total",
        ("equity_total", "所有者权益合计", "股东权益合计", "权益合计"),
    ),
    # 货币资金
    "cash": ("BS-001", ("BS-001", "货币资金")),
}
_IS_VARIABLES: dict[str, tuple[str, tuple[str, ...]]] = {
    "net_profit": ("IS-019", ("IS-019", "净利润")),
    "revenue": ("IS-001", ("IS-001", "营业收入")),
    "cost": ("IS-002", ("IS-002", "营业成本")),
    "profit_before_tax": ("IS-017", ("IS-017", "利润总额")),
    "income_tax": ("IS-018", ("IS-018", "所得税费用", "所得税")),
}


# ─────────────────────────────────────────────────────────────────────────────
# 7 条勾稽种子（logic_check 公式定义）
# ─────────────────────────────────────────────────────────────────────────────
# 每条表达式在勾稽**通过**时求值为 1（!=0），**不通过**时求值为 0；
# 与前端 check() 的 passed 判定逐条等价（见模块 docstring）。
# refs：表达式引用的 REPORT 域 row_code（ROW 形态 formula_ref），经 full_resolve 归属 report 域。
_CROSS_CHECK_SEEDS: list[dict[str, Any]] = [
    {
        "id": "report-cross-check-1",
        "description": "资产合计 = 负债合计 + 所有者权益合计",
        # tol=1: |round(assets - (liab + equity), 2)| <= 1
        "expression": (
            "ABS(ROUND(ROW('assets_total') - "
            "(ROW('liabilities_total') + ROW('equity_total')), 2)) <= 1"
        ),
        "refs": ["assets_total", "liabilities_total", "equity_total"],
    },
    {
        "id": "report-cross-check-2",
        "description": "营业收入 − 营业成本 = 毛利",
        # tol=0: 左右恒等（毛利定义），|round(0, 2)| < 0.01 → 恒通过
        "expression": (
            "ABS(ROUND((ROW('IS-001') - ROW('IS-002')) - "
            "(ROW('IS-001') - ROW('IS-002')), 2)) < 0.01"
        ),
        "refs": ["IS-001", "IS-002"],
    },
    {
        "id": "report-cross-check-3",
        "description": "利润总额 − 所得税 = 净利润",
        # tol=1: |round((pbt - tax) - net_profit, 2)| <= 1
        "expression": (
            "ABS(ROUND((ROW('IS-017') - ROW('IS-018')) - ROW('IS-019'), 2)) <= 1"
        ),
        "refs": ["IS-017", "IS-018", "IS-019"],
    },
    {
        "id": "report-cross-check-4",
        "description": "资产 − 负债 = 权益",
        # tol=1: |round((assets - liab) - equity, 2)| <= 1
        "expression": (
            "ABS(ROUND((ROW('assets_total') - ROW('liabilities_total')) - "
            "ROW('equity_total'), 2)) <= 1"
        ),
        "refs": ["assets_total", "liabilities_total", "equity_total"],
    },
    {
        "id": "report-cross-check-5",
        "description": "所有者权益变动表期末 = 资产负债表权益",
        # tol=0: 左右恒等，|round(0, 2)| < 0.01 → 恒通过
        "expression": "ABS(ROUND(ROW('equity_total') - ROW('equity_total'), 2)) < 0.01",
        "refs": ["equity_total"],
    },
    {
        "id": "report-cross-check-6",
        "description": "有效税率 ≈ 25%",
        # pbt>0: |round(tax - pbt*0.25, 2)| <= pbt*0.05；否则 |round(tax, 2)| < 0.01
        # （等价于前端：right = pbt>0 ? pbt*0.25 : 0，tolerance = pbt*0.05，
        #   tolerance>0 ⟺ pbt>0）
        "expression": (
            "IF(ROW('IS-017') > 0, "
            "ABS(ROUND(ROW('IS-018') - ROW('IS-017') * 0.25, 2)) <= ROW('IS-017') * 0.05, "
            "ABS(ROUND(ROW('IS-018'), 2)) < 0.01)"
        ),
        "refs": ["IS-017", "IS-018"],
    },
    {
        "id": "report-cross-check-7",
        "description": "货币资金 ≥ 0（负值异常）",
        # left=cash, right=0, tolerance=|cash|：cash!=0 时 |round(cash,2)| <= |cash|，
        # cash==0 时 |round(0,2)| < 0.01（前端此条 tolerance=abs(cash) 恒使其通过）
        "expression": (
            "IF(ABS(ROW('BS-001')) > 0, "
            "ABS(ROUND(ROW('BS-001'), 2)) <= ABS(ROW('BS-001')), "
            "ABS(ROUND(ROW('BS-001'), 2)) < 0.01)"
        ),
        "refs": ["BS-001"],
    },
]


def build_cross_check_formulas() -> list[FormulaRecord]:
    """把 7 条勾稽种子构建为 ``FormulaRecord``（logic_check 公式）。

    可编辑语义：这些 FormulaRecord 即公式管理库中可在 Formula_Edit_Dialog
    查看/编辑的 7 条 logic_check 规则（问题描述沿用原 description）。
    """
    formulas: list[FormulaRecord] = []
    for seed in _CROSS_CHECK_SEEDS:
        formulas.append(
            FormulaRecord(
                id=seed["id"],
                formula_type="logic_check",
                target_cell=f"report:cross_check:{seed['id']}",
                expression=seed["expression"],
                issue_description=seed["description"],
                # REPORT 域 row_code → ROW 形态 formula_ref（full_resolve 归属 report 域）
                refs=[{"formula_ref": f"ROW('{code}')"} for code in seed["refs"]],
                addr_id=None,
            )
        )
    return formulas


# ─────────────────────────────────────────────────────────────────────────────
# 报表取值：构建 row_cache（与前端 buildMap + get() 语义对齐）
# ─────────────────────────────────────────────────────────────────────────────
def _to_decimal(value: Any) -> Decimal:
    """把报表金额安全转 Decimal（None/非法 → 0）。"""
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def _build_report_map(rows: Iterable[Any]) -> dict[str, Decimal]:
    """按 row_code / row_name 建索引（合计行覆盖同名非合计行）。

    与前端 ``buildMap`` 逐一对齐：先填非合计行（仅当键未出现），再填合计行
    （覆盖同名键）。行对象需含 ``row_code`` / ``row_name`` /
    ``current_period_amount`` / ``is_total_row`` 属性或键。
    """
    rows = list(rows)
    result: dict[str, Decimal] = {}

    def _get(row: Any, attr: str) -> Any:
        if isinstance(row, dict):
            return row.get(attr)
        return getattr(row, attr, None)

    # 非合计行优先（仅当键未出现）
    for row in rows:
        amt = _to_decimal(_get(row, "current_period_amount"))
        if _get(row, "is_total_row"):
            continue
        code = _get(row, "row_code")
        name = _get(row, "row_name")
        if code and code not in result:
            result[code] = amt
        if name and name not in result:
            result[name] = amt
    # 合计行覆盖同名
    for row in rows:
        if not _get(row, "is_total_row"):
            continue
        amt = _to_decimal(_get(row, "current_period_amount"))
        code = _get(row, "row_code")
        name = _get(row, "row_name")
        if code:
            result[code] = amt
        if name:
            result[name] = amt
    return result


def _resolve_value(report_map: dict[str, Decimal], candidate_keys: tuple[str, ...]) -> Decimal:
    """从报表 map 解析逻辑变量值（与前端 ``get(map, ...keys)`` 语义对齐）。

    ① 精确匹配候选键（非 0 优先）→ ② 子串模糊匹配（键包含候选键，非 0）→ ③ 0。
    （前端②的 canonical row_code 解析在后端已由候选键含 row_code 覆盖。）
    """
    # ① 精确匹配
    for key in candidate_keys:
        val = report_map.get(key)
        if val is not None and val != 0:
            return val
    # ② 子串模糊匹配
    for key in candidate_keys:
        for map_key, map_val in report_map.items():
            if map_val != 0 and key in map_key:
                return map_val
    return Decimal("0")


def build_report_row_cache(
    bs_rows: Iterable[Any], is_rows: Iterable[Any]
) -> dict[str, Decimal]:
    """从资产负债表 / 利润表行构建 logic_check 公式的 row_cache。

    row_cache 的键即表达式中 ``ROW('...')`` 的 REPORT 域 row_code。
    """
    bs_map = _build_report_map(bs_rows)
    is_map = _build_report_map(is_rows)

    row_cache: dict[str, Decimal] = {}
    for _var, (ref_code, candidates) in _BS_VARIABLES.items():
        row_cache[ref_code] = _resolve_value(bs_map, candidates)
    for _var, (ref_code, candidates) in _IS_VARIABLES.items():
        row_cache[ref_code] = _resolve_value(is_map, candidates)
    return row_cache


# ─────────────────────────────────────────────────────────────────────────────
# 执行：产 Issue_List（logic_check 分派，绝不改值）
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class CrossCheckOutcome:
    """单条勾稽的执行结果（供前端逐条展示 passed / 描述）。"""

    formula_id: str
    description: str
    expression: str
    passed: bool


@dataclass
class CrossCheckResult:
    """报表勾稽执行聚合结果。"""

    issues: list[IssueItem]
    outcomes: list[CrossCheckOutcome]
    last_computed_at: Optional[datetime] = None


async def run_cross_checks(
    row_cache: dict[str, Decimal],
    *,
    db: AsyncSession | None = None,
    project_id: str | None = None,
    resolve_refs: bool = True,
) -> CrossCheckResult:
    """在给定 row_cache 上执行 7 条 logic_check 勾稽，聚合 Issue_List。

    统一走 ``execute_formula``（logic_check 分派）：勾稽不通过 → 追加 Issue，
    **绝不修改任何数据值**。``resolve_refs=True`` 时逐条引用经 ACNR
    ``full_resolve`` 解析（fail-open，不影响取值）。
    """
    ctx = FormulaContext(row_cache=dict(row_cache))
    issues: list[IssueItem] = []
    outcomes: list[CrossCheckOutcome] = []
    last_computed_at: Optional[datetime] = None

    for formula in build_cross_check_formulas():
        result = await execute_formula(
            db,
            formula=formula,
            ctx=ctx,
            project_id=project_id,
            resolve_refs=resolve_refs,
        )
        passed = len(result.issues) == 0
        issues.extend(result.issues)
        outcomes.append(
            CrossCheckOutcome(
                formula_id=formula.id,
                description=formula.issue_description or "",
                expression=formula.expression,
                passed=passed,
            )
        )
        if result.last_computed_at is not None:
            last_computed_at = result.last_computed_at

    return CrossCheckResult(
        issues=issues, outcomes=outcomes, last_computed_at=last_computed_at
    )


async def _fetch_report_rows(
    db: AsyncSession,
    *,
    project_id: Any,
    year: int,
    report_type: FinancialReportType,
) -> list[FinancialReport]:
    """取某项目某年某类报表的行（未删除）。"""
    stmt = sa.select(FinancialReport).where(
        FinancialReport.project_id == project_id,
        FinancialReport.year == year,
        FinancialReport.report_type == report_type,
        FinancialReport.is_deleted == sa.false(),
    )
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


async def execute_report_cross_checks(
    db: AsyncSession,
    *,
    project_id: Any,
    year: int,
) -> CrossCheckResult:
    """执行报表勾稽（logic_check）→ 返回 Issue_List。

    从 ``financial_report`` 取资产负债表 / 利润表行 → 构建 row_cache →
    经 ``execute_formula``（logic_check 分派）执行 7 条勾稽 → 聚合 Issue_List。
    **绝不修改任何数据单元值**（Req 6.3 语义由 logic_check 分派保证）。

    Requirements: 6.4
    """
    bs_rows = await _fetch_report_rows(
        db, project_id=project_id, year=year,
        report_type=FinancialReportType.balance_sheet,
    )
    is_rows = await _fetch_report_rows(
        db, project_id=project_id, year=year,
        report_type=FinancialReportType.income_statement,
    )
    row_cache = build_report_row_cache(bs_rows, is_rows)
    return await run_cross_checks(
        row_cache, db=db, project_id=str(project_id), resolve_refs=True
    )
