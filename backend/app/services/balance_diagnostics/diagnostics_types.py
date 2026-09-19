"""统一诊断 DTO 类型定义。

定义 BalanceDiagnosticsResult、DiagnosticCause、DiagnosticJumpTarget、
UnmatchedAccount 等核心类型，前后端共享枚举值。

Requirements: 1.1, 1.3, 1.4, 1.5, 6.5
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Caliber 枚举 — 平衡口径
# ---------------------------------------------------------------------------

Caliber = Literal[
    "ledger_debit_credit",          # 序时账凭证借贷合计
    "trial_balance_debit_credit",   # 试算表全科目借方合计 vs 贷方合计
    "balance_vs_ledger",            # 余额表期末 vs 序时账累计
    "balance_sheet_equation",       # 资产 = 负债 + 权益（仅报表生成后 BS 勾稽）
]

CALIBER_VALUES: list[str] = [
    "ledger_debit_credit",
    "trial_balance_debit_credit",
    "balance_vs_ledger",
    "balance_sheet_equation",
]

# 中文展示文案
CALIBER_LABELS: dict[str, str] = {
    "ledger_debit_credit": "序时账凭证借贷合计",
    "trial_balance_debit_credit": "试算表全科目借方合计 vs 贷方合计",
    "balance_vs_ledger": "余额表期末 vs 序时账累计",
    "balance_sheet_equation": "资产 = 负债 + 权益（报表生成后 BS 勾稽）",
}

# ---------------------------------------------------------------------------
# Caliber 数据源定义
# ---------------------------------------------------------------------------

CALIBER_DATA_SOURCES: dict[str, dict] = {
    "ledger_debit_credit": {
        "table_name": "tb_ledger",
        "formula": "SUM(debit_amount) == SUM(credit_amount)",
        "description": "序时账全部凭证借方发生额合计应等于贷方发生额合计",
        "top_contributors_source": "voucher_no",
    },
    "trial_balance_debit_credit": {
        "table_name": "trial_balance",
        "formula": "按方向汇总借方余额合计 == 贷方余额合计",
        "description": "试算表按科目类别分方向，借方类（资产+费用）余额合计应等于贷方类（负债+权益+收入）余额合计",
        "top_contributors_source": "standard_account_code",
    },
    "balance_vs_ledger": {
        "table_name": "tb_balance + tb_ledger",
        "formula": "closing_balance = opening_balance + SUM(debit_amount) - SUM(credit_amount)",
        "description": "余额表期末余额应等于期初余额加借方发生额减贷方发生额",
        "top_contributors_source": "account_code",
    },
    "balance_sheet_equation": {
        "table_name": "financial_report",
        "formula": "资产合计 = 负债和所有者权益合计",
        "description": "资产负债表生成后资产合计应等于负债加所有者权益合计，仅报表生成后使用",
        "top_contributors_source": "report_line_code",
    },
}

# ---------------------------------------------------------------------------
# CauseCode 枚举 — 原因代码
# ---------------------------------------------------------------------------

CauseCode = Literal[
    "report_line_unmatched",
    "sign_convention_anomaly",
    "pnl_not_closed_or_caliber_gap",
    "source_data_unbalanced",
    "manual_review_required",
]

CAUSE_CODE_VALUES: list[str] = [
    "report_line_unmatched",
    "sign_convention_anomaly",
    "pnl_not_closed_or_caliber_gap",
    "source_data_unbalanced",
    "manual_review_required",
]

# ---------------------------------------------------------------------------
# JumpTargetType 枚举
# ---------------------------------------------------------------------------

JumpTargetType = Literal[
    "report_line_mapping",
    "sign_anomaly_review",
    "ledger_penetration",
    "data_quality",
]

JUMP_TARGET_TYPE_VALUES: list[str] = [
    "report_line_mapping",
    "sign_anomaly_review",
    "ledger_penetration",
    "data_quality",
]

# ---------------------------------------------------------------------------
# Transport 枚举 — 跳转传参方式
# ---------------------------------------------------------------------------

Transport = Literal[
    "route_query",
    "dialog_prop",
    "event_payload",
]

TRANSPORT_VALUES: list[str] = [
    "route_query",
    "dialog_prop",
    "event_payload",
]

# ---------------------------------------------------------------------------
# DiagnosticCause — 诊断原因
# ---------------------------------------------------------------------------


class DiagnosticCause(BaseModel):
    """诊断原因：描述不平衡的一个可能原因。"""

    cause_code: CauseCode
    severity: int = Field(ge=1, le=5, description="严重程度 1-5，5 最严重")
    confidence: float = Field(ge=0.0, le=1.0, description="置信度 0.0-1.0")
    description: str  # 中文解释
    evidence: dict = Field(default_factory=dict)  # 支撑证据


# ---------------------------------------------------------------------------
# DiagnosticJumpTarget — 跳转目标
# ---------------------------------------------------------------------------


class DiagnosticJumpTarget(BaseModel):
    """诊断跳转目标：前端可执行的修复入口。"""

    target_type: JumpTargetType
    label: str  # 中文按钮文案
    transport: Transport  # 传参方式
    params: dict = Field(default_factory=dict)  # 传参内容


# ---------------------------------------------------------------------------
# UnmatchedAccount — 未匹配报表行次科目
# ---------------------------------------------------------------------------


class UnmatchedAccount(BaseModel):
    """未匹配报表行次的科目记录。"""

    account_code: str
    account_name: str | None = None
    amount: float = 0.0
    mapping_status: str = "unmapped"  # unmapped | seed_missing | unconfirmed


# ---------------------------------------------------------------------------
# BalanceDiagnosticsResult — 统一诊断结果
# ---------------------------------------------------------------------------


class BalanceDiagnosticsResult(BaseModel):
    """统一借贷不平衡诊断结果 DTO。"""

    caliber: Caliber
    caliber_label: str  # 中文展示文案
    status: str = "passed"  # passed | warning | blocking
    difference: float = 0.0
    debit_total: float = 0.0
    credit_total: float = 0.0
    asset_total: float | None = None
    liability_equity_total: float | None = None
    likely_causes: list[DiagnosticCause] = Field(default_factory=list)
    unmatched_accounts: list[UnmatchedAccount] = Field(default_factory=list)
    sign_anomalies: list[dict] = Field(default_factory=list)
    sign_anomalies_unavailable: bool = False
    top_contributors: list[dict] = Field(default_factory=list)
    jump_targets: list[DiagnosticJumpTarget] = Field(default_factory=list)
    data_sources: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# 导出
# ---------------------------------------------------------------------------

__all__ = [
    "Caliber",
    "CALIBER_VALUES",
    "CALIBER_LABELS",
    "CALIBER_DATA_SOURCES",
    "CauseCode",
    "CAUSE_CODE_VALUES",
    "JumpTargetType",
    "JUMP_TARGET_TYPE_VALUES",
    "Transport",
    "TRANSPORT_VALUES",
    "DiagnosticCause",
    "DiagnosticJumpTarget",
    "UnmatchedAccount",
    "BalanceDiagnosticsResult",
]
