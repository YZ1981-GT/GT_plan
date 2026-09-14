"""K13 营业外支出 — Python 公式引擎镜像（用于 PBT 测试）

镜像 useK13FormulaEngine.ts 中的纯函数，方便 Hypothesis PBT 直接测试。
科目：6711营业外支出（损益类/借方科目），取发生额非余额。
"""
from __future__ import annotations

from typing import Optional


def calc_audited_amount(unadj: float, aje: float, rje: float) -> float:
    """CP-K13-01: 审定数 = 未审数 + AJE + RJE"""
    return unadj + aje + rje


def calc_income_statement_occurrence(debit_occ: float, credit_occ: float) -> float:
    """CP-K13-02: 支出类发生额 = 借方发生 - 贷方发生（6711借方科目）"""
    return debit_occ - credit_occ


def calc_yoy_change(current: float, prior: float) -> Optional[float]:
    """CP-K13-03: 同比变动率 = (本期 - 上期) / 上期；上期为0返回None"""
    if prior == 0:
        return None
    return (current - prior) / prior


def calc_proportion(item: float, total: float) -> Optional[float]:
    """CP-K13-04: 占比 = 单项 / 合计；合计为0返回None"""
    if total == 0:
        return None
    return item / total


def calc_subtotal(arr: list[float]) -> float:
    """CP-K13-05: 合计行 = SUM(数组元素)"""
    return sum(arr)
