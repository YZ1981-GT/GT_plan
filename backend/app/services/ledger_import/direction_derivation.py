"""方向推导规则 — 纯函数模块。

根据余额行数据和科目元数据推导方向（debit/credit/unknown）及方向来源。
优先级：explicit > split_columns > category_inferred > unknown。

Requirements: 1.1, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Optional

from .sign_convention_types import DirectionSource

__all__ = [
    "derive_balance_direction",
    "DerivationResult",
    "DEBIT_KEYWORDS",
    "CREDIT_KEYWORDS",
    "NORMAL_DIRECTION_BY_CATEGORY",
    "CONTRA_ASSET_PATTERNS",
]


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

DEBIT_KEYWORDS = frozenset(["借", "借方", "D", "d", "debit", "Debit", "DEBIT"])
CREDIT_KEYWORDS = frozenset(["贷", "贷方", "C", "c", "credit", "Credit", "CREDIT"])

# 科目类别 → 正常方向
NORMAL_DIRECTION_BY_CATEGORY: dict[str, str] = {
    "asset": "debit",
    "liability": "credit",
    "equity": "credit",
    "revenue": "credit",
    "income": "credit",
    "cost": "debit",
    "expense": "debit",
}

# 资产备抵科目名称正则（方向为贷方）
CONTRA_ASSET_PATTERNS = re.compile(
    r"(累计折旧|累计摊销|坏账准备|减值准备|跌价准备|折耗)",
    re.UNICODE,
)

# 科目编码前缀 → 低置信类别
_PREFIX_CATEGORY_MAP: dict[str, str] = {
    "1": "asset",
    "2": "liability",
    "3": "equity",
    "5": "cost",
    "6": "expense",
}


# ---------------------------------------------------------------------------
# 结果类型
# ---------------------------------------------------------------------------


class DerivationResult:
    """方向推导结果。"""

    __slots__ = ("direction", "direction_source", "warning")

    def __init__(
        self,
        direction: str,
        direction_source: str,
        warning: Optional[str] = None,
    ):
        self.direction: str = direction
        self.direction_source: str = direction_source
        self.warning: Optional[str] = warning

    def __repr__(self) -> str:
        return f"DerivationResult({self.direction!r}, {self.direction_source!r})"


# ---------------------------------------------------------------------------
# 核心推导函数
# ---------------------------------------------------------------------------


def derive_balance_direction(
    row: dict[str, Any],
    metadata: Optional[dict[str, Any]] = None,
) -> DerivationResult:
    """推导余额行的方向和方向来源。

    Args:
        row: 标准化余额行 dict，可含 direction/opening_direction/closing_direction、
             opening_debit/opening_credit/closing_debit/closing_credit、
             closing_balance 等字段。
        metadata: 科目元数据 dict，可含 account_category、is_contra_asset、
                  account_name、account_code 等。

    Returns:
        DerivationResult(direction, direction_source, warning?)

    优先级：
    1. 显式方向列 → explicit_direction
    2. 借贷分列 → split_columns
    3. 类别推断 → account_category_inferred / account_category_inferred_low_confidence
    4. 缺失 → unknown
    """
    # ── 1. 显式方向列 ──
    result = _try_explicit_direction(row)
    if result is not None:
        return result

    # ── 2. 借贷分列 ──
    result = _try_split_columns(row)
    if result is not None:
        return result

    # ── 3. 类别推断 ──
    result = _try_category_inferred(row, metadata)
    if result is not None:
        return result

    # ── 4. unknown ──
    return DerivationResult("unknown", "unknown")


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


def _try_explicit_direction(row: dict[str, Any]) -> Optional[DerivationResult]:
    """检查显式方向列。"""
    for key in ("direction", "closing_direction", "opening_direction"):
        val = row.get(key)
        if val is None:
            continue
        s = str(val).strip()
        if s in DEBIT_KEYWORDS:
            return DerivationResult("debit", "explicit_direction")
        if s in CREDIT_KEYWORDS:
            return DerivationResult("credit", "explicit_direction")
    return None


def _try_split_columns(row: dict[str, Any]) -> Optional[DerivationResult]:
    """检查借贷分列。

    源分列字段保持绝对值，仅净额字段带符号。
    借贷两方同时非零 → 按净额符号判定方向并记录 warning。
    """
    # 优先看期末分列
    cd = _to_decimal(row.get("closing_debit"))
    cc = _to_decimal(row.get("closing_credit"))

    # 备选期初分列
    if cd is None and cc is None:
        cd = _to_decimal(row.get("opening_debit"))
        cc = _to_decimal(row.get("opening_credit"))

    if cd is None and cc is None:
        return None

    cd = cd or Decimal(0)
    cc = cc or Decimal(0)

    # 两方同时非零
    if cd != 0 and cc != 0:
        net = cd - cc
        if net > 0:
            direction = "debit"
        elif net < 0:
            direction = "credit"
        else:
            direction = "unknown"
        return DerivationResult(
            direction,
            "split_columns",
            warning="both_debit_credit_nonzero",
        )

    # 仅一方非零
    if cd != 0:
        return DerivationResult("debit", "split_columns")
    if cc != 0:
        return DerivationResult("credit", "split_columns")

    # 两方均为 0
    return DerivationResult("unknown", "split_columns")


def _try_category_inferred(
    row: dict[str, Any],
    metadata: Optional[dict[str, Any]],
) -> Optional[DerivationResult]:
    """按 Account_Category / Contra_Asset 推断方向。"""
    if metadata is None:
        metadata = {}

    category = metadata.get("account_category")
    is_contra = metadata.get("is_contra_asset", False)
    account_name = metadata.get("account_name") or row.get("account_name") or ""
    account_code = metadata.get("account_code") or row.get("account_code") or ""

    # 资产备抵检测
    if is_contra or CONTRA_ASSET_PATTERNS.search(str(account_name)):
        return DerivationResult("credit", "account_category_inferred")

    # 高置信类别
    if category and category in NORMAL_DIRECTION_BY_CATEGORY:
        direction = NORMAL_DIRECTION_BY_CATEGORY[category]
        return DerivationResult(direction, "account_category_inferred")

    # 低置信前缀推断
    code = str(account_code).strip()
    if code:
        prefix = code[0]
        if prefix in _PREFIX_CATEGORY_MAP:
            cat = _PREFIX_CATEGORY_MAP[prefix]
            direction = NORMAL_DIRECTION_BY_CATEGORY[cat]
            return DerivationResult(direction, "account_category_inferred_low_confidence")

    return None


def _to_decimal(val: Any) -> Optional[Decimal]:
    """安全转 Decimal。"""
    if val is None:
        return None
    try:
        s = str(val).strip().replace(",", "")
        if not s or s == "None":
            return None
        return Decimal(s)
    except Exception:
        return None
