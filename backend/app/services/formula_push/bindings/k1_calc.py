"""K1（其他应收款）公式推送的纯计算函数。

审定合计 = Σ(unadj + aje + rje) 按组合行（r0~r3），与前端 persistAuditedTotals 同口径。
舍入 Math.round(n*100)/100 = Python round(n, 2)（JS Number 精度范围内等价）。

spec: formula-push-all-subjects-rollout · design §八
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _num(responses: Mapping[str, Any], item_id: str) -> float:
    """从条目快照读数值（与前端 num() 同口径）。"""
    raw = responses.get(item_id)
    if raw is None or raw == "":
        return 0.0
    try:
        return float(raw)
    except (ValueError, TypeError):
        return 0.0


def _round2(n: float) -> float:
    """Math.round(n*100)/100 —— JS 精度范围内与 Python round(n, 2) 等价。"""
    return round(n * 100) / 100


def _audited(unadj: float, aje: float, rje: float) -> float:
    return _round2(unadj + aje + rje)


def _row_audited(entries: Mapping[str, Any], prefix: str, row_key: str) -> float:
    """单行审定数 = unadj + aje + rje。"""
    base = f"K1-1-{prefix}-{row_key}"
    return _audited(
        _num(entries, f"{base}-unadj"),
        _num(entries, f"{base}-aje"),
        _num(entries, f"{base}-rje"),
    )


#: 组合行 rowKey 列表（r0~r3）
PORTFOLIO_ROW_KEYS = ("r0", "r1", "r2", "r3")


def audited_receivable(entries: Mapping[str, Any]) -> float:
    """原值审定合计 = Σ receivable r0~r3 各行 audited。"""
    return _round2(sum(_row_audited(entries, "receivable", rk) for rk in PORTFOLIO_ROW_KEYS))


def audited_baddebt(entries: Mapping[str, Any]) -> float:
    """坏账审定合计 = Σ baddebt r0~r3 各行 audited。"""
    return _round2(sum(_row_audited(entries, "baddebt", rk) for rk in PORTFOLIO_ROW_KEYS))


def audited_net(entries: Mapping[str, Any]) -> float:
    """净值审定合计 = 原值合计 − 坏账合计。"""
    return _round2(audited_receivable(entries) - audited_baddebt(entries))
