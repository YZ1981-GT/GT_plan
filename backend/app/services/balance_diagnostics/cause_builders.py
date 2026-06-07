"""诊断原因构建器和排序逻辑。

定义各类原因的构建函数、排序规则和 top_contributors 结构。

Requirements: 2.1, 2.5, 2.7
"""

from __future__ import annotations

from backend.app.services.balance_diagnostics.diagnostics_types import (
    DiagnosticCause,
)


# ---------------------------------------------------------------------------
# 3.1 report_line_unmatched 原因
# ---------------------------------------------------------------------------


def build_report_line_unmatched_cause(
    unmatched_count: int,
    total_unmatched_amount: float = 0.0,
    sample_accounts: list[str] | None = None,
) -> DiagnosticCause:
    """构建「报表行次未匹配」原因。

    当存在有余额但 seed/mapping 中查不到报表行次的科目时触发。
    severity=3, confidence 根据未匹配科目数量动态计算。
    """
    confidence = min(0.9, 0.5 + unmatched_count * 0.05)
    evidence: dict = {
        "unmatched_count": unmatched_count,
        "total_unmatched_amount": total_unmatched_amount,
    }
    if sample_accounts:
        evidence["sample_accounts"] = sample_accounts[:5]

    return DiagnosticCause(
        cause_code="report_line_unmatched",
        severity=3,
        confidence=round(confidence, 2),
        description=f"存在 {unmatched_count} 个有余额但未映射报表行次的科目，"
                    f"涉及金额 {total_unmatched_amount:,.2f} 元",
        evidence=evidence,
    )


# ---------------------------------------------------------------------------
# 3.2 sign_convention_anomaly 原因
# ---------------------------------------------------------------------------


def build_sign_convention_anomaly_cause(
    anomaly_count: int,
    sample_anomalies: list[dict] | None = None,
) -> DiagnosticCause:
    """构建「方向/符号异常」原因。

    当科目余额方向与 Account_Category 预期方向不一致时触发。
    severity=4, confidence 根据异常数量计算。
    """
    confidence = min(0.85, 0.4 + anomaly_count * 0.1)
    evidence: dict = {"anomaly_count": anomaly_count}
    if sample_anomalies:
        evidence["samples"] = sample_anomalies[:5]

    return DiagnosticCause(
        cause_code="sign_convention_anomaly",
        severity=4,
        confidence=round(confidence, 2),
        description=f"发现 {anomaly_count} 个科目余额方向异常，"
                    "可能导致借贷分类汇总错误",
        evidence=evidence,
    )


# ---------------------------------------------------------------------------
# 3.3 pnl_not_closed_or_caliber_gap 原因
# ---------------------------------------------------------------------------


def build_pnl_not_closed_cause(
    pnl_balance: float = 0.0,
    caliber_mismatch: bool = False,
) -> DiagnosticCause:
    """构建「损益未结转或口径差异」原因。

    当使用 balance_sheet_equation 但损益尚未结转到未分配利润时触发，
    或当混用不同口径比较时触发。
    severity=4, confidence 固定 0.7（需人工确认）。
    """
    if caliber_mismatch:
        desc = "不同平衡口径之间存在差异，请确认使用的平衡公式是否一致"
    else:
        desc = (
            f"损益类科目余额 {pnl_balance:,.2f} 元尚未结转到未分配利润，"
            "不宜使用「资产=负债+权益」作为通用试算平衡公式"
        )

    return DiagnosticCause(
        cause_code="pnl_not_closed_or_caliber_gap",
        severity=4,
        confidence=0.7,
        description=desc,
        evidence={
            "pnl_balance": pnl_balance,
            "caliber_mismatch": caliber_mismatch,
        },
    )


# ---------------------------------------------------------------------------
# 3.4 source_data_unbalanced 原因
# ---------------------------------------------------------------------------


def build_source_data_unbalanced_cause(
    difference: float,
    caliber: str,
    top_vouchers: list[str] | None = None,
) -> DiagnosticCause:
    """构建「源数据本身不平」原因。

    当序时账凭证借贷不等或余额表与序时账累计不一致时触发。
    severity=5（最严重）, confidence=0.95。
    """
    evidence: dict = {"difference": difference, "caliber": caliber}
    if top_vouchers:
        evidence["top_vouchers"] = top_vouchers[:10]

    return DiagnosticCause(
        cause_code="source_data_unbalanced",
        severity=5,
        confidence=0.95,
        description=f"源数据存在不平衡，差异 {difference:,.2f} 元（口径：{caliber}）",
        evidence=evidence,
    )


# ---------------------------------------------------------------------------
# 3.5 manual_review_required 原因
# ---------------------------------------------------------------------------


def build_manual_review_required_cause(
    reason: str = "自动判断不足",
) -> DiagnosticCause:
    """构建「需人工复核」原因。

    当自动诊断无法给出确定性结论时加入。
    severity=2, confidence=0.0（表示无法自动判断）。
    """
    return DiagnosticCause(
        cause_code="manual_review_required",
        severity=2,
        confidence=0.0,
        description=f"系统自动判断不足以确定根因，建议人工复核：{reason}",
        evidence={"reason": reason},
    )


# ---------------------------------------------------------------------------
# 3.6 top_contributors 结构定义
# ---------------------------------------------------------------------------


def build_ledger_debit_credit_contributors(
    voucher_data: list[dict],
) -> list[dict]:
    """ledger_debit_credit caliber: 按凭证号聚合差额最大的前 10 条。

    输入格式: [{voucher_no, debit_total, credit_total}]
    输出格式: [{voucher_no, debit_total, credit_total, difference}]
    """
    contributors = []
    for v in voucher_data:
        debit = float(v.get("debit_total", 0))
        credit = float(v.get("credit_total", 0))
        contributors.append({
            "voucher_no": v.get("voucher_no", ""),
            "debit_total": debit,
            "credit_total": credit,
            "difference": debit - credit,
        })
    # 按 |difference| 降序排列
    contributors.sort(key=lambda x: abs(x["difference"]), reverse=True)
    return contributors[:10]


def build_balance_vs_ledger_contributors(
    account_data: list[dict],
) -> list[dict]:
    """balance_vs_ledger caliber: 差额最大的前 10 个科目。

    输入格式: [{account_code, opening_balance, ledger_debit, ledger_credit, closing_balance}]
    输出格式: 同上 + expected_closing + difference
    """
    contributors = []
    for a in account_data:
        opening = float(a.get("opening_balance", 0))
        debit = float(a.get("ledger_debit", 0))
        credit = float(a.get("ledger_credit", 0))
        closing = float(a.get("closing_balance", 0))
        expected = opening + debit - credit
        contributors.append({
            "account_code": a.get("account_code", ""),
            "opening_balance": opening,
            "ledger_debit": debit,
            "ledger_credit": credit,
            "closing_balance": closing,
            "expected_closing": expected,
            "difference": closing - expected,
        })
    contributors.sort(key=lambda x: abs(x["difference"]), reverse=True)
    return contributors[:10]


def build_trial_balance_debit_credit_contributors(
    account_data: list[dict],
) -> list[dict]:
    """trial_balance_debit_credit caliber: 差额贡献最大的前 10 个科目。

    输入格式: [{standard_account_code, direction, amount, direction_source}]
    输出格式: 同上 + difference_contribution
    """
    contributors = []
    for a in account_data:
        contributors.append({
            "standard_account_code": a.get("standard_account_code", ""),
            "direction": a.get("direction", ""),
            "amount": float(a.get("amount", 0)),
            "direction_source": a.get("direction_source", "unknown"),
            "difference_contribution": float(a.get("difference_contribution", 0)),
        })
    contributors.sort(key=lambda x: abs(x["difference_contribution"]), reverse=True)
    return contributors[:10]


def build_balance_sheet_equation_contributors(
    report_line_data: list[dict],
) -> list[dict]:
    """balance_sheet_equation caliber: 差额相关的报表行次。

    输入格式: [{report_line_code, row_name, amount}]
    输出格式: 同上
    """
    return report_line_data[:10]


# ---------------------------------------------------------------------------
# 排序：severity DESC, confidence DESC
# ---------------------------------------------------------------------------


def sort_causes(causes: list[DiagnosticCause]) -> list[DiagnosticCause]:
    """按 severity 降序、confidence 降序排列原因列表。"""
    return sorted(causes, key=lambda c: (-c.severity, -c.confidence))


# ---------------------------------------------------------------------------
# 导出
# ---------------------------------------------------------------------------

__all__ = [
    "build_report_line_unmatched_cause",
    "build_sign_convention_anomaly_cause",
    "build_pnl_not_closed_cause",
    "build_source_data_unbalanced_cause",
    "build_manual_review_required_cause",
    "build_ledger_debit_credit_contributors",
    "build_balance_vs_ledger_contributors",
    "build_trial_balance_debit_credit_contributors",
    "build_balance_sheet_equation_contributors",
    "sort_causes",
]
