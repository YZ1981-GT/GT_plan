"""报表「审核」里按配置执行的勾稽 / 合理性公式（spec formula-governance-coverage-closure R1.6）。

旧实现（``ReportEngine.run_audit_checks`` 第 2 段）两处问题：
* 从不求值公式：勾稽类「有公式就判通过」（``passed=True  # 需要公式引擎执行后才能判断``），
  合理性类只看该行有没有值 —— 用户在公式管理里配的审核公式写什么都「通过」；
* 读准则行（``list_configs``），本项目适配的审核公式不生效（与其他消费方口径不一）。

现在：读本项目有效配置，公式经与表间审核**同一个**严格求值入口（取不到数报原因，不代入 0）；
判定口径与公式管理执行器一致 —— 勾稽类「表达式非 0 = 通过」，合理性类「表达式非 0 = 触发提醒」。
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

AUDIT_CATEGORIES = ("logic_check", "reasonability")
_LABELS = {"logic_check": "🔍 逻辑审核", "reasonability": "💡 提示性审核"}


async def run_report_audit(db: AsyncSession, project_id: uuid.UUID, year: int, standard: str) -> list[dict[str, Any]]:
    """报表「审核」全部结果 = 内置平衡校验 + 本项目有效配置里的勾稽 / 合理性公式。

    取代 ``ReportEngine.run_audit_checks``（其第 2 段不求值公式，见模块说明）。
    """
    from app.services.report_engine import ReportEngine

    results = [{
        "name": c["check_name"], "category": "logic_check", "category_label": _LABELS["logic_check"],
        "passed": c["passed"], "expected": c["expected_value"], "actual": c["actual_value"],
        "diff": c["difference"], "formula": None, "source": "内置校验",
    } for c in await ReportEngine(db).check_balance(project_id, year)]
    results.extend(await config_audit_checks(db, project_id, year, standard))
    return results


async def config_audit_checks(db: AsyncSession, project_id: uuid.UUID, year: int,
                              standard: str) -> list[dict[str, Any]]:
    """执行本项目有效配置里类别为勾稽 / 合理性的公式，返回与内置平衡校验同形的结果行。"""
    from app.models.report_models import FinancialReport
    from app.services.amount_resolver import TrialBalanceResolver
    from app.services.formula_settings.cross_check_rules import evaluate_strict
    from app.services.formula_settings.effective_report import load_effective_report_configs

    configs = await load_effective_report_configs(db, standard=standard, project_id=project_id)
    rows = [c for c in configs if c.formula_category in AUDIT_CATEGORIES and (c.formula or "").strip()]
    if not rows:
        return []
    reports = (await db.execute(sa.select(FinancialReport.row_code, FinancialReport.current_period_amount).where(
        FinancialReport.project_id == project_id, FinancialReport.year == year,
        FinancialReport.is_deleted == sa.false()))).all()
    row_cache = {code: Decimal(str(amount or 0)) for code, amount in reports if code}
    resolver = TrialBalanceResolver(db, project_id, year)
    out: list[dict[str, Any]] = []
    for row in rows:
        category = row.formula_category
        value, err = await evaluate_strict(row.formula, resolver, row_cache)
        desc = row.formula_description or ("逻辑校验" if category == "logic_check" else "合理性检查")
        if value is None:
            passed, actual = False, f"无法取数（{err}）"
        elif category == "logic_check":
            passed, actual = value != Decimal("0"), str(value)
        else:  # 合理性：表达式成立（非 0）即触发提醒 ⇒ 判为「未通过」以便看见
            passed, actual = value == Decimal("0"), str(value)
        out.append({
            "name": f"{row.row_name}（{desc}）",
            "category": category,
            "category_label": _LABELS[category],
            "passed": passed,
            "expected": desc,
            "actual": actual,
            "diff": None,
            "formula": row.formula,
            "source": f"{row.row_code} {row.formula_source or ''}".strip(),
        })
    return out
