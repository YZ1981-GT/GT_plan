"""符号异常检测 — 纯函数模块。

识别与 Account_Category 正常方向冲突的余额行，输出 SignAnomaly 列表。
不修改原始数据，不直接访问 DB。

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from .direction_derivation import (
    CONTRA_ASSET_PATTERNS,
    NORMAL_DIRECTION_BY_CATEGORY,
)
from .sign_convention_types import SignAnomaly

__all__ = [
    "detect_sign_anomalies",
]


def detect_sign_anomalies(
    rows: list[dict[str, Any]],
    category_map: Optional[dict[str, dict[str, Any]]] = None,
) -> list[SignAnomaly]:
    """检测余额行中的符号异常。

    Args:
        rows: 标准化余额行列表，每行含 account_code、account_name、
              closing_balance (或 opening_balance)。
        category_map: 科目编码 → 元数据 dict 映射。
            元数据可含: account_category, is_contra_asset, account_name。
            若 None，跳过无法推断的行。

    Returns:
        符号异常列表。每条异常记录科目编码、期望方向、实际方向、余额和原因。
    """
    if category_map is None:
        category_map = {}

    anomalies: list[SignAnomaly] = []

    for row in rows:
        account_code = str(row.get("account_code", "")).strip()
        if not account_code:
            continue

        meta = category_map.get(account_code, {})
        category = meta.get("account_category")
        is_contra = meta.get("is_contra_asset", False)
        account_name = (
            meta.get("account_name")
            or row.get("account_name")
            or ""
        )

        # 确定期望方向
        expected_direction = _get_expected_direction(
            category, is_contra, account_name
        )
        if expected_direction is None:
            continue  # 无法判断类别，跳过

        # 确定实际余额方向（由净额符号决定）
        balance = _get_balance(row)
        if balance is None or balance == 0:
            continue  # 余额为零或缺失，无异常可检测

        actual_direction = "debit" if balance > 0 else "credit"

        # 对比
        if actual_direction != expected_direction:
            reason = _build_reason(
                category, is_contra, account_name,
                expected_direction, actual_direction,
            )
            anomalies.append(SignAnomaly(
                account_code=account_code,
                account_name=account_name or None,
                expected_direction=expected_direction,
                actual_direction=actual_direction,
                balance_amount=float(balance),
                category=category or "contra_asset",
                reason=reason,
            ))

    return anomalies


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


def _get_expected_direction(
    category: Optional[str],
    is_contra: bool,
    account_name: str,
) -> Optional[str]:
    """确定科目的期望正常方向。"""
    # 资产备抵优先
    if is_contra or CONTRA_ASSET_PATTERNS.search(str(account_name)):
        return "credit"

    if category and category in NORMAL_DIRECTION_BY_CATEGORY:
        return NORMAL_DIRECTION_BY_CATEGORY[category]

    return None


def _get_balance(row: dict[str, Any]) -> Optional[Decimal]:
    """获取余额净额（优先期末，其次期初）。"""
    for key in ("closing_balance", "opening_balance"):
        val = row.get(key)
        if val is not None:
            try:
                return Decimal(str(val))
            except Exception:
                continue
    return None


def _build_reason(
    category: Optional[str],
    is_contra: bool,
    account_name: str,
    expected: str,
    actual: str,
) -> str:
    """构建异常原因描述字符串。"""
    if is_contra or CONTRA_ASSET_PATTERNS.search(str(account_name)):
        return "contra_asset_debit_balance"

    reason_map = {
        "liability": "liability_debit_net_balance",
        "equity": "equity_debit_net_balance",
        "revenue": "revenue_debit_net_balance",
        "income": "revenue_debit_net_balance",
        "asset": "asset_credit_net_balance",
        "cost": "cost_credit_net_balance",
        "expense": "expense_credit_net_balance",
    }
    return reason_map.get(category or "", f"{category}_{actual}_anomaly")
