"""资产负债类审定表族的纯计算函数（无 IO / ORM / async）。

泛化 ``k1_calc`` 的 ``_row_audited`` 模式，支持任意 ``wp_code / prefix / row_keys``。
审定合计 = Σ(unadj + aje + rje) 按组合行，舍入 ``Math.round(n*100)/100``。

spec: formula-push-balance-adj-batch-c · design §一 · 需求 C1, C3
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _num(entries: Mapping[str, Any], item_id: str) -> float:
    """从条目快照读数值（与前端 ``num()`` / ``k1_calc._num`` 同口径）。"""
    raw = entries.get(item_id)
    if raw is None or raw == "":
        return 0.0
    try:
        return float(raw)
    except (ValueError, TypeError):
        return 0.0


def _round2(n: float) -> float:
    """``Math.round(n*100)/100`` —— JS 精度范围内与 Python ``round(n, 2)`` 等价。"""
    return round(n * 100) / 100


def row_audited(
    entries: Mapping[str, Any],
    sheet_code: str,
    prefix: str,
    row_key: str,
) -> float:
    """单行审定数 = unadj + aje + rje。

    键模式：``{sheet_code}-{prefix}-{row_key}-{suffix}``

    与 ``k1_calc._row_audited`` 同口径，只是把 ``K1-1`` 泛化为 ``sheet_code``。
    """
    base = f"{sheet_code}-{prefix}-{row_key}"
    unadj = _num(entries, f"{base}-unadj")
    aje = _num(entries, f"{base}-aje")
    rje = _num(entries, f"{base}-rje")
    return _round2(unadj + aje + rje)


def audited_total(
    entries: Mapping[str, Any],
    sheet_code: str,
    prefix: str,
    row_keys: tuple[str, ...],
) -> float:
    """组合行审定合计 = Σ row_audited，再 round2。

    ``prefix`` 典型值为 ``"receivable"`` / ``"baddebt"``。
    ``row_keys`` 典型值为 ``("r0",)`` 或 ``("r0", "r1", "r2", "r3")``。
    """
    return _round2(sum(
        row_audited(entries, sheet_code, prefix, rk) for rk in row_keys
    ))


def audited_net(
    entries: Mapping[str, Any],
    sheet_code: str,
    receivable_prefix: str,
    baddebt_prefix: str,
    row_keys: tuple[str, ...],
    *,
    has_provision: bool = True,
) -> float:
    """净值审定合计 = 原值合计 − 坏账合计。

    ``has_provision=False`` 时坏账恒 0，净值 = 原值合计。
    """
    recv = audited_total(entries, sheet_code, receivable_prefix, row_keys)
    if not has_provision:
        return recv
    bd = audited_total(entries, sheet_code, baddebt_prefix, row_keys)
    return _round2(recv - bd)
