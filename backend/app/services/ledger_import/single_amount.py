"""序时账只有一列金额（SAP「公司代码货币价值」等）时拆成借贷两列。

spec citar-case-chain-fetch-fixes R3：SAP 行项目导出只有一列带符号金额 + 「借/贷标识」（S 借 / H 贷），
原转换只认借贷分列 ⇒ 借贷全空、整份序时账没有金额。
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Optional

# 显式方向列 token（借/贷/D/C），与 direction_derivation 口径一致；
# SAP 行项目的「借/贷标识」用 S（Soll，借）/ H（Haben，贷）
DEBIT_DIR_TOKENS = frozenset(["借", "借方", "D", "d", "debit", "Debit", "DEBIT", "DR", "Dr", "dr", "S", "s"])
CREDIT_DIR_TOKENS = frozenset(["贷", "贷方", "C", "c", "credit", "Credit", "CREDIT", "CR", "Cr", "cr", "H", "h"])


def _decimal(val) -> Optional[Decimal]:
    if val is None:
        return None
    try:
        s = str(val).strip().replace(",", "")
        return Decimal(s) if s and s != "None" else None
    except (InvalidOperation, ValueError):
        return None


def credit_amounts_negated(rows: list[dict]) -> bool:
    """单金额列 + 方向列时，贷方行的金额是否带负号（SAP 借正贷负）。

    按本批贷方行多数判断：多数为负 ⇒ 贷方金额 = -金额；否则金额本身就是贷方发生额（红字照带符号）。
    """
    neg = pos = 0
    for row in rows:
        if row.get("debit_amount") not in (None, "") or row.get("credit_amount") not in (None, ""):
            continue
        token = str(row.get("direction") or row.get("entry_direction") or "").strip()
        if token not in CREDIT_DIR_TOKENS:
            continue
        amount = _decimal(row.get("amount"))
        if amount is None or amount == 0:
            continue
        if amount < 0:
            neg += 1
        else:
            pos += 1
    return neg > pos


def split_single_amount(
    amount: Optional[Decimal], direction_raw, credit_negated: bool,
) -> tuple[Optional[Decimal], Optional[Decimal]]:
    """一列金额 → (借方, 贷方)。

    有方向列：借 → 借方 = 金额；贷 → 贷方 = ``-金额``（``credit_negated``）或金额。
    无方向列：正数记借方、负数记贷方（取反）。
    """
    if amount is None:
        return None, None
    token = str(direction_raw).strip() if direction_raw is not None else ""
    if token in DEBIT_DIR_TOKENS:
        return amount, None
    if token in CREDIT_DIR_TOKENS:
        return None, (-amount if credit_negated else amount)
    if amount >= 0:
        return amount, None
    return None, -amount
