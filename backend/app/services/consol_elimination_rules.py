"""Sprint B.0.3 — 内部往来抵销规则注册器.

4 种预设规则:
- internal_ar: 内部应收账款抵销（按公司对匹配）
- internal_revenue: 内部收入抵销
- internal_inventory_unrealized: 内部存货未实现利润
- internal_dividend: 内部股利抵销

主要 API:
- get_elimination_rules() -> dict[str, dict]
- apply_elimination(aggregated_value, rule_type, wp_data) -> Decimal
- calculate_elimination_amount(rule_type, child_projects, ctx) -> Decimal
- validate_wp_code_exists(rule_type) -> bool  (CI-17)

Validates: Requirements D12, CI-17
"""

from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 预设抵销规则注册表
# ---------------------------------------------------------------------------

ELIMINATION_RULES: dict[str, dict[str, Any]] = {
    "internal_ar": {
        "name": "内部应收账款抵销",
        "description": "按公司对匹配内部应收/应付，抵销后净额为零",
        "wp_code": "consol_internal_ar",
        "match_logic": "by_company_pair",
        "affects_columns": ["col_amount_end", "col_amount_start"],
        "category": "balance_sheet",
    },
    "internal_revenue": {
        "name": "内部收入抵销",
        "description": "内部销售收入与对应成本抵销",
        "wp_code": "consol_internal_revenue",
        "match_logic": "by_company_pair",
        "affects_columns": ["col_amount_current", "col_amount_prior"],
        "category": "income_statement",
    },
    "internal_inventory_unrealized": {
        "name": "内部存货未实现利润",
        "description": "内部交易存货中未实现利润的抵销",
        "wp_code": "consol_internal_inventory",
        "match_logic": "by_inventory_margin",
        "affects_columns": ["col_amount_end"],
        "category": "balance_sheet",
    },
    "internal_dividend": {
        "name": "内部股利抵销",
        "description": "子公司向母公司分配的股利抵销",
        "wp_code": "consol_internal_dividend",
        "match_logic": "by_dividend_declaration",
        "affects_columns": ["col_amount_current"],
        "category": "equity",
    },
}

# 所有合法的 wp_code 集合（CI-17 校验用）
VALID_WP_CODES: set[str] = {
    rule["wp_code"] for rule in ELIMINATION_RULES.values()
}


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


def get_elimination_rules() -> dict[str, dict[str, Any]]:
    """获取所有预设抵销规则.

    Returns:
        dict[rule_type -> rule_config]
    """
    return dict(ELIMINATION_RULES)


def get_rule(rule_type: str) -> dict[str, Any] | None:
    """获取单个抵销规则配置."""
    return ELIMINATION_RULES.get(rule_type)


def apply_elimination(
    aggregated_value: Decimal | float | int,
    rule_type: str,
    wp_data: dict | None = None,
) -> Decimal:
    """对聚合值应用抵销规则.

    Args:
        aggregated_value: 聚合后的原始值
        rule_type: 抵销规则类型
        wp_data: 底稿数据（含抵销金额明细）

    Returns:
        抵销后的值（Decimal）
    """
    rule = ELIMINATION_RULES.get(rule_type)
    if rule is None:
        logger.warning("Unknown elimination rule_type: %s", rule_type)
        return Decimal(str(aggregated_value))

    elimination_amount = _extract_elimination_amount(rule, wp_data)
    result = Decimal(str(aggregated_value)) - elimination_amount
    return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def calculate_elimination_amount(
    rule_type: str,
    child_projects: list[dict] | None = None,
    ctx: dict | None = None,
) -> Decimal:
    """计算指定规则的抵销金额.

    Args:
        rule_type: 抵销规则类型
        child_projects: 子公司项目列表（含内部交易数据）
        ctx: 上下文（含 wp_cache 等）

    Returns:
        抵销金额（Decimal，非负）
    """
    rule = ELIMINATION_RULES.get(rule_type)
    if rule is None:
        return Decimal("0")

    ctx = ctx or {}
    child_projects = child_projects or []
    wp_code = rule["wp_code"]
    match_logic = rule["match_logic"]

    # 从 wp_cache 获取抵销底稿数据
    wp_cache = ctx.get("_wp_cache") or {}
    wp_entry = wp_cache.get(wp_code)

    if wp_entry is not None:
        return _extract_elimination_amount(rule, wp_entry)

    # 无底稿数据时，按 match_logic 从子公司数据推算
    if match_logic == "by_company_pair":
        return _calc_by_company_pair(child_projects, rule)
    elif match_logic == "by_inventory_margin":
        return _calc_by_inventory_margin(child_projects, rule)
    elif match_logic == "by_dividend_declaration":
        return _calc_by_dividend(child_projects, rule)

    return Decimal("0")


def validate_wp_code_exists(rule_type: str) -> bool:
    """校验抵销规则引用的 wp_code 是否存在于注册表中（CI-17）.

    Returns:
        True if wp_code is valid, False otherwise.
    """
    rule = ELIMINATION_RULES.get(rule_type)
    if rule is None:
        return False
    return rule.get("wp_code") in VALID_WP_CODES


def validate_all_rules_wp_codes() -> list[str]:
    """校验所有规则的 wp_code 是否合法.

    Returns:
        list of invalid rule_types (empty = all valid)
    """
    invalid: list[str] = []
    for rule_type, rule_config in ELIMINATION_RULES.items():
        wp_code = rule_config.get("wp_code")
        if not wp_code or not isinstance(wp_code, str):
            invalid.append(rule_type)
    return invalid


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


def _extract_elimination_amount(
    rule: dict[str, Any],
    wp_data: dict | None,
) -> Decimal:
    """从底稿数据中提取抵销金额."""
    if not wp_data:
        return Decimal("0")

    # 支持多种数据格式
    if isinstance(wp_data, dict):
        # 直接金额字段
        amount = wp_data.get("elimination_amount") or wp_data.get("amount") or 0
        try:
            return abs(Decimal(str(amount)))
        except Exception:
            pass

        # parsed_data 路径
        parsed = wp_data.get("parsed_data") or {}
        if isinstance(parsed, dict):
            # 查找抵销汇总行
            for sheet_data in parsed.values():
                if isinstance(sheet_data, dict):
                    total = sheet_data.get("elimination_total")
                    if total is not None:
                        try:
                            return abs(Decimal(str(total)))
                        except Exception:
                            pass

    return Decimal("0")


def _calc_by_company_pair(
    child_projects: list[dict],
    rule: dict[str, Any],  # noqa: ARG001
) -> Decimal:
    """按公司对匹配计算内部往来抵销.

    简化逻辑：查找子公司间的内部交易金额。
    """
    total = Decimal("0")
    for project in child_projects:
        internal_amount = project.get("internal_balance") or 0
        try:
            total += abs(Decimal(str(internal_amount)))
        except Exception:
            pass
    # 内部往来是双向的，实际抵销金额是单边
    return (total / 2).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) if total else Decimal("0")


def _calc_by_inventory_margin(
    child_projects: list[dict],
    rule: dict[str, Any],  # noqa: ARG001
) -> Decimal:
    """按存货未实现利润计算抵销."""
    total = Decimal("0")
    for project in child_projects:
        unrealized = project.get("unrealized_profit") or 0
        try:
            total += abs(Decimal(str(unrealized)))
        except Exception:
            pass
    return total


def _calc_by_dividend(
    child_projects: list[dict],
    rule: dict[str, Any],  # noqa: ARG001
) -> Decimal:
    """按股利声明计算抵销."""
    total = Decimal("0")
    for project in child_projects:
        dividend = project.get("internal_dividend") or 0
        try:
            total += abs(Decimal(str(dividend)))
        except Exception:
            pass
    return total
