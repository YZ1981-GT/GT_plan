"""DataQualityService 口径统一适配器。

不修改 DataQualityService 内部实现，而是在外层适配其输出：
- 4.1 拆分 ledger_debit_credit_balance 与 trial_balance_debit_credit
- 4.2 明确 report_balance 只表示 BS 勾稽
- 4.3 debit_credit_balance 兼容旧入口，映射到新口径
- 4.4 返回 details 可转换为 BalanceDiagnosticsResult

Requirements: 4.1, 4.2, 4.3, 4.4
"""

from __future__ import annotations

from typing import Any

from backend.app.services.balance_diagnostics.diagnostics_types import (
    CALIBER_DATA_SOURCES,
    CALIBER_LABELS,
    BalanceDiagnosticsResult,
)


# ---------------------------------------------------------------------------
# 口径映射
# ---------------------------------------------------------------------------

# 旧 DataQualityService check_name → 新统一 caliber
CHECK_NAME_TO_CALIBER: dict[str, str] = {
    "debit_credit_balance": "trial_balance_debit_credit",
    "ledger_debit_credit_balance": "ledger_debit_credit",
    "balance_vs_ledger": "balance_vs_ledger",
    "report_balance": "balance_sheet_equation",
}

# 旧口径提示
CALIBER_HINT: dict[str, str] = {
    "debit_credit_balance": (
        "此检查实际使用 trial_balance 按科目类别方向分组汇总，"
        "口径为「试算表全科目借方合计 vs 贷方合计」"
    ),
}


# ---------------------------------------------------------------------------
# 4.1 拆分 ledger_debit_credit_balance 与 trial_balance_debit_credit
# ---------------------------------------------------------------------------


def get_caliber_for_check(check_name: str) -> str:
    """将 DataQualityService 检查名称映射到统一 caliber。

    - debit_credit_balance (旧)  → trial_balance_debit_credit
    - ledger_debit_credit_balance → ledger_debit_credit
    - balance_vs_ledger → balance_vs_ledger
    - report_balance → balance_sheet_equation
    """
    return CHECK_NAME_TO_CALIBER.get(check_name, check_name)


# ---------------------------------------------------------------------------
# 4.2 report_balance 只表示 BS 勾稽
# ---------------------------------------------------------------------------


def is_report_balance_applicable(has_generated_report: bool) -> bool:
    """report_balance 口径仅在报表生成后才适用。

    如果报表尚未生成，不应执行此检查或将其标为 N/A。
    """
    return has_generated_report


# ---------------------------------------------------------------------------
# 4.3 兼容旧入口
# ---------------------------------------------------------------------------


def adapt_legacy_check_name(check_name: str) -> tuple[str, str | None]:
    """兼容旧入口，返回 (新 caliber, 口径提示)。

    旧 debit_credit_balance 映射到 trial_balance_debit_credit 并附提示。
    """
    caliber = get_caliber_for_check(check_name)
    hint = CALIBER_HINT.get(check_name)
    return caliber, hint


# ---------------------------------------------------------------------------
# 4.4 转换为 BalanceDiagnosticsResult
# ---------------------------------------------------------------------------


def adapt_check_result_to_diagnostics(
    check_name: str,
    result: dict[str, Any],
) -> BalanceDiagnosticsResult:
    """将 DataQualityService 单项检查结果适配为 BalanceDiagnosticsResult。

    Args:
        check_name: 原始检查名称（debit_credit_balance / balance_vs_ledger / report_balance）
        result: DataQualityService 返回的 {status, message, details}

    Returns:
        统一 BalanceDiagnosticsResult
    """
    caliber, hint = adapt_legacy_check_name(check_name)
    details = result.get("details", {})
    status = result.get("status", "passed")

    # 构建基础字段
    debit_total = float(details.get("debit_total", 0) or 0)
    credit_total = float(details.get("credit_total", 0) or 0)
    asset_total = _safe_float(details.get("asset_total"))
    liability_equity_total = _safe_float(details.get("liability_equity_total"))
    difference = float(details.get("difference", 0) or 0)

    # 如果没有显式 difference，自行计算
    if difference == 0 and status != "passed":
        if caliber == "balance_sheet_equation" and asset_total is not None:
            difference = abs((asset_total or 0) - (liability_equity_total or 0))
        elif debit_total or credit_total:
            difference = abs(debit_total - credit_total)

    # top_contributors from differences list
    top_contributors: list[dict] = []
    differences_list = details.get("differences", [])
    if differences_list and caliber == "balance_vs_ledger":
        for d in differences_list[:10]:
            top_contributors.append({
                "account_code": d.get("account_code", ""),
                "opening_balance": float(d.get("opening_balance", 0) or 0),
                "ledger_debit": float(d.get("debit_amount", 0) or 0),
                "ledger_credit": float(d.get("credit_amount", 0) or 0),
                "closing_balance": float(d.get("closing_balance", 0) or 0),
                "expected_closing": float(d.get("expected_closing", 0) or 0),
                "difference": float(d.get("difference", 0) or 0),
            })

    # data_sources
    data_sources = CALIBER_DATA_SOURCES.get(caliber, {})

    # 附加口径提示
    adapted_data_sources = dict(data_sources)
    if hint:
        adapted_data_sources["caliber_hint"] = hint

    return BalanceDiagnosticsResult(
        caliber=caliber,
        caliber_label=CALIBER_LABELS.get(caliber, caliber),
        status=status,
        difference=difference,
        debit_total=debit_total,
        credit_total=credit_total,
        asset_total=asset_total,
        liability_equity_total=liability_equity_total,
        top_contributors=top_contributors,
        data_sources=adapted_data_sources,
    )


def adapt_all_results_to_diagnostics(
    results: dict[str, dict[str, Any]],
) -> list[BalanceDiagnosticsResult]:
    """将 DataQualityService.run_checks 的全部结果适配为诊断列表。

    只适配平衡类检查（排除 mapping_completeness, profit_reconciliation）。
    """
    balance_checks = {"debit_credit_balance", "balance_vs_ledger", "report_balance"}
    diagnostics = []
    for check_name, result in results.items():
        if check_name in balance_checks:
            diagnostics.append(adapt_check_result_to_diagnostics(check_name, result))
    return diagnostics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_float(value: Any) -> float | None:
    """安全转换为 float，None/空字符串返回 None。"""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# 导出
# ---------------------------------------------------------------------------

__all__ = [
    "CHECK_NAME_TO_CALIBER",
    "get_caliber_for_check",
    "is_report_balance_applicable",
    "adapt_legacy_check_name",
    "adapt_check_result_to_diagnostics",
    "adapt_all_results_to_diagnostics",
]
