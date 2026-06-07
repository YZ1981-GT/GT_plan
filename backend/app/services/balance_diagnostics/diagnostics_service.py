"""BalanceDiagnosticsService — 统一借贷不平衡诊断服务。

职责：
1. 从 validator.py findings 转换诊断结果
2. 从 DataQualityService 检查结果生成诊断结果
3. 查询未匹配报表行次科目
4. 查询符号异常（graceful degrade）
5. 生成前端跳转目标

Requirements: 1.2, 2.1, 2.2, 2.3, 2.4, 2.6
"""

from __future__ import annotations

from typing import Any

from backend.app.services.balance_diagnostics.diagnostics_types import (
    CALIBER_DATA_SOURCES,
    CALIBER_LABELS,
    BalanceDiagnosticsResult,
    DiagnosticCause,
    DiagnosticJumpTarget,
    UnmatchedAccount,
)


# ---------------------------------------------------------------------------
# 2.1 validator findings → 诊断 DTO
# ---------------------------------------------------------------------------


def convert_validator_finding_to_diagnostics(finding: dict) -> BalanceDiagnosticsResult | None:
    """将 validator.py 的 BALANCE_UNBALANCED / BALANCE_LEDGER_MISMATCH finding 转为诊断 DTO。

    Args:
        finding: validator 产出的 finding dict，需包含 code、message、explanation 等字段。

    Returns:
        BalanceDiagnosticsResult 或 None（非平衡类 finding 返回 None）。
    """
    code = finding.get("code", "")

    if code == "BALANCE_UNBALANCED":
        return _convert_balance_unbalanced(finding)
    elif code == "BALANCE_LEDGER_MISMATCH":
        return _convert_balance_ledger_mismatch(finding)
    return None


def _convert_balance_unbalanced(finding: dict) -> BalanceDiagnosticsResult:
    """BALANCE_UNBALANCED → ledger_debit_credit caliber。"""
    explanation = finding.get("explanation", {})
    if hasattr(explanation, "model_dump"):
        explanation = explanation.model_dump()

    inputs = explanation.get("inputs", {})
    computed = explanation.get("computed", {})

    debit_total = float(inputs.get("sum_debit", 0) or computed.get("sum_debit", 0))
    credit_total = float(inputs.get("sum_credit", 0) or computed.get("sum_credit", 0))
    difference = abs(debit_total - credit_total)

    # top_contributors: 差额最大的凭证
    sample_voucher_ids = explanation.get("sample_voucher_ids", [])
    top_contributors = [
        {"voucher_no": vid, "contribution": "unknown"} for vid in sample_voucher_ids[:10]
    ]

    causes = [
        DiagnosticCause(
            cause_code="source_data_unbalanced",
            severity=5,
            confidence=0.95,
            description=f"序时账凭证借贷发生额不平，差异 {difference:,.2f} 元",
            evidence={"sample_voucher_ids": sample_voucher_ids[:10]},
        )
    ]

    caliber = "ledger_debit_credit"
    return BalanceDiagnosticsResult(
        caliber=caliber,
        caliber_label=CALIBER_LABELS[caliber],
        status="blocking",
        difference=difference,
        debit_total=debit_total,
        credit_total=credit_total,
        likely_causes=causes,
        top_contributors=top_contributors,
        data_sources=CALIBER_DATA_SOURCES[caliber],
        jump_targets=_build_jump_targets_for_caliber(caliber),
    )


def _convert_balance_ledger_mismatch(finding: dict) -> BalanceDiagnosticsResult:
    """BALANCE_LEDGER_MISMATCH → balance_vs_ledger caliber。"""
    explanation = finding.get("explanation", {})
    if hasattr(explanation, "model_dump"):
        explanation = explanation.model_dump()

    diff_breakdown = explanation.get("diff_breakdown", {})
    opening = float(diff_breakdown.get("opening", 0))
    sum_debit = float(diff_breakdown.get("sum_debit", 0))
    sum_credit = float(diff_breakdown.get("sum_credit", 0))
    actual_closing = float(diff_breakdown.get("actual_closing", 0))
    expected_closing = opening + sum_debit - sum_credit
    difference = abs(actual_closing - expected_closing)

    # top_contributors: 差额科目
    account_code = explanation.get("account_code", "")
    top_contributors = []
    if account_code:
        top_contributors.append({
            "account_code": account_code,
            "opening_balance": opening,
            "ledger_debit": sum_debit,
            "ledger_credit": sum_credit,
            "closing_balance": actual_closing,
            "expected_closing": expected_closing,
            "difference": difference,
        })

    causes = [
        DiagnosticCause(
            cause_code="source_data_unbalanced",
            severity=4,
            confidence=0.85,
            description=f"余额表期末余额与序时账累计不一致，差异 {difference:,.2f} 元",
            evidence={"diff_breakdown": diff_breakdown},
        )
    ]

    caliber = "balance_vs_ledger"
    return BalanceDiagnosticsResult(
        caliber=caliber,
        caliber_label=CALIBER_LABELS[caliber],
        status="blocking",
        difference=difference,
        debit_total=sum_debit,
        credit_total=sum_credit,
        likely_causes=causes,
        top_contributors=top_contributors,
        data_sources=CALIBER_DATA_SOURCES[caliber],
        jump_targets=_build_jump_targets_for_caliber(caliber),
    )


# ---------------------------------------------------------------------------
# 2.2 DataQualityService 检查结果 → 诊断 DTO
# ---------------------------------------------------------------------------


def convert_data_quality_result_to_diagnostics(
    check_name: str, result: dict
) -> BalanceDiagnosticsResult | None:
    """将 DataQualityService 单项检查结果转为诊断 DTO。

    Args:
        check_name: 检查名称（如 debit_credit_balance、balance_vs_ledger、report_balance）
        result: DataQualityService 返回的单项 {status, message, details}

    Returns:
        BalanceDiagnosticsResult 或 None（mapping_completeness 等非平衡类返回 None）
    """
    caliber_map = {
        "debit_credit_balance": "trial_balance_debit_credit",
        "balance_vs_ledger": "balance_vs_ledger",
        "report_balance": "balance_sheet_equation",
    }

    caliber = caliber_map.get(check_name)
    if caliber is None:
        return None

    details = result.get("details", {})
    status = result.get("status", "passed")

    if caliber == "trial_balance_debit_credit":
        debit_total = float(details.get("debit_total", 0))
        credit_total = float(details.get("credit_total", 0))
        difference = float(details.get("difference", abs(debit_total - credit_total)))
        return BalanceDiagnosticsResult(
            caliber=caliber,
            caliber_label=CALIBER_LABELS[caliber],
            status=status,
            difference=difference,
            debit_total=debit_total,
            credit_total=credit_total,
            data_sources=CALIBER_DATA_SOURCES[caliber],
            jump_targets=_build_jump_targets_for_caliber(caliber) if status != "passed" else [],
        )

    elif caliber == "balance_vs_ledger":
        differences = details.get("differences", [])
        # 汇总差异
        total_diff = sum(float(d.get("difference", 0)) for d in differences)
        top_contributors = [
            {
                "account_code": d.get("account_code", ""),
                "opening_balance": float(d.get("opening_balance", 0)),
                "ledger_debit": float(d.get("debit_amount", 0)),
                "ledger_credit": float(d.get("credit_amount", 0)),
                "closing_balance": float(d.get("closing_balance", 0)),
                "expected_closing": float(d.get("expected_closing", 0)),
                "difference": float(d.get("difference", 0)),
            }
            for d in differences[:10]
        ]
        return BalanceDiagnosticsResult(
            caliber=caliber,
            caliber_label=CALIBER_LABELS[caliber],
            status=status,
            difference=total_diff,
            top_contributors=top_contributors,
            data_sources=CALIBER_DATA_SOURCES[caliber],
            jump_targets=_build_jump_targets_for_caliber(caliber) if status != "passed" else [],
        )

    elif caliber == "balance_sheet_equation":
        asset_total = float(details.get("asset_total", 0))
        liability_equity_total = float(details.get("liability_equity_total", 0))
        difference = float(details.get("difference", abs(asset_total - liability_equity_total)))
        return BalanceDiagnosticsResult(
            caliber=caliber,
            caliber_label=CALIBER_LABELS[caliber],
            status=status,
            difference=difference,
            asset_total=asset_total,
            liability_equity_total=liability_equity_total,
            data_sources=CALIBER_DATA_SOURCES[caliber],
            jump_targets=_build_jump_targets_for_caliber(caliber) if status != "passed" else [],
        )

    return None


# ---------------------------------------------------------------------------
# 2.3 查询未匹配报表行次科目
# ---------------------------------------------------------------------------


def build_unmatched_accounts(
    accounts_with_balance: list[dict],
    mapped_account_codes: set[str],
) -> list[UnmatchedAccount]:
    """识别有余额但无报表行次映射的科目。

    Args:
        accounts_with_balance: 有余额的科目列表 [{account_code, account_name, amount}]
        mapped_account_codes: 已有映射的科目编码集合

    Returns:
        未匹配科目清单
    """
    unmatched = []
    for acc in accounts_with_balance:
        code = acc.get("account_code", "")
        if code and code not in mapped_account_codes:
            unmatched.append(UnmatchedAccount(
                account_code=code,
                account_name=acc.get("account_name"),
                amount=float(acc.get("amount", 0)),
                mapping_status="unmapped",
            ))
    return unmatched


# ---------------------------------------------------------------------------
# 2.4 查询符号异常
# ---------------------------------------------------------------------------


def build_sign_anomalies(
    sign_anomaly_flags: list[Any] | None,
) -> tuple[list[dict], bool]:
    """从 sign_anomaly_flags 构建符号异常清单。

    Args:
        sign_anomaly_flags: 符号异常标记列表，可能为 None（字段未上线）

    Returns:
        (sign_anomalies 列表, sign_anomalies_unavailable 标志)
    """
    if sign_anomaly_flags is None:
        return [], True

    anomalies = []
    for flag in sign_anomaly_flags:
        if hasattr(flag, "model_dump"):
            anomalies.append(flag.model_dump())
        elif isinstance(flag, dict):
            anomalies.append(flag)
        else:
            anomalies.append({"raw": str(flag)})

    return anomalies, False


# ---------------------------------------------------------------------------
# 2.5 生成跳转目标
# ---------------------------------------------------------------------------


def _build_jump_targets_for_caliber(caliber: str) -> list[DiagnosticJumpTarget]:
    """根据 caliber 生成推荐跳转目标。"""
    targets = []

    # 所有口径都可跳转到 ledger_penetration
    targets.append(DiagnosticJumpTarget(
        target_type="ledger_penetration",
        label="查看序时账穿透",
        transport="route_query",
        params={"caliber": caliber},
    ))

    return targets


def build_jump_targets(
    caliber: str,
    has_unmatched_accounts: bool = False,
    has_sign_anomalies: bool = False,
    unmatched_account_codes: list[str] | None = None,
) -> list[DiagnosticJumpTarget]:
    """根据诊断结果生成完整跳转目标列表。

    Args:
        caliber: 当前口径
        has_unmatched_accounts: 是否存在未匹配科目
        has_sign_anomalies: 是否存在符号异常
        unmatched_account_codes: 未匹配科目编码列表（用于跳转参数）

    Returns:
        跳转目标列表
    """
    targets: list[DiagnosticJumpTarget] = []

    # report_line_mapping 跳转
    if has_unmatched_accounts:
        params: dict[str, str] = {"highlight": "true"}
        if unmatched_account_codes:
            params["account_code"] = unmatched_account_codes[0]
            if len(unmatched_account_codes) > 1:
                params["account_codes"] = ",".join(unmatched_account_codes[:5])
        targets.append(DiagnosticJumpTarget(
            target_type="report_line_mapping",
            label="查看报表行次映射",
            transport="dialog_prop",
            params=params,
        ))

    # sign_anomaly_review 跳转
    if has_sign_anomalies:
        targets.append(DiagnosticJumpTarget(
            target_type="sign_anomaly_review",
            label="查看方向异常",
            transport="event_payload",
            params={"caliber": caliber},
        ))

    # ledger_penetration 跳转
    targets.append(DiagnosticJumpTarget(
        target_type="ledger_penetration",
        label="查看序时账穿透",
        transport="route_query",
        params={"caliber": caliber},
    ))

    return targets


# ---------------------------------------------------------------------------
# 2.6 Graceful degrade
# ---------------------------------------------------------------------------


def build_sign_anomaly_unavailable_cause() -> DiagnosticCause:
    """生成符号异常不可用的提示性原因（不阻断其他诊断）。"""
    return DiagnosticCause(
        cause_code="manual_review_required",
        severity=1,
        confidence=0.0,
        description="方向异常字段尚不可用，本次诊断未纳入符号异常原因",
        evidence={"reason": "sign_anomaly_flags_unavailable"},
    )


# ---------------------------------------------------------------------------
# 组合入口
# ---------------------------------------------------------------------------


def build_full_diagnostics(
    caliber: str,
    status: str,
    difference: float,
    debit_total: float = 0.0,
    credit_total: float = 0.0,
    asset_total: float | None = None,
    liability_equity_total: float | None = None,
    likely_causes: list[DiagnosticCause] | None = None,
    unmatched_accounts: list[UnmatchedAccount] | None = None,
    sign_anomaly_flags: list[Any] | None = None,
    top_contributors: list[dict] | None = None,
) -> BalanceDiagnosticsResult:
    """组合完整诊断结果。

    处理 sign_anomaly_flags 的 graceful degrade。
    """
    sign_anomalies, sign_unavailable = build_sign_anomalies(sign_anomaly_flags)

    causes = list(likely_causes or [])
    if sign_unavailable:
        causes.append(build_sign_anomaly_unavailable_cause())

    unmatched = unmatched_accounts or []
    has_unmatched = len(unmatched) > 0
    has_sign = len(sign_anomalies) > 0
    unmatched_codes = [a.account_code for a in unmatched]

    jump_targets = build_jump_targets(
        caliber=caliber,
        has_unmatched_accounts=has_unmatched,
        has_sign_anomalies=has_sign,
        unmatched_account_codes=unmatched_codes,
    )

    return BalanceDiagnosticsResult(
        caliber=caliber,
        caliber_label=CALIBER_LABELS.get(caliber, caliber),
        status=status,
        difference=difference,
        debit_total=debit_total,
        credit_total=credit_total,
        asset_total=asset_total,
        liability_equity_total=liability_equity_total,
        likely_causes=causes,
        unmatched_accounts=unmatched,
        sign_anomalies=sign_anomalies,
        sign_anomalies_unavailable=sign_unavailable,
        top_contributors=top_contributors or [],
        jump_targets=jump_targets,
        data_sources=CALIBER_DATA_SOURCES.get(caliber, {}),
    )
