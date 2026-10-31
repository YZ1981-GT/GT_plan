"""一致性门控 — 分支 ID 清单

ADR-FHIC-14 第 4 点。每个非比较出口都有一个唯一 ID，与源码出口一一对应。
AST 守卫验证双射。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


BranchKind = Literal[
    "missing", "unsaved", "partial", "not_applicable", "exception"
]


@dataclass(frozen=True, slots=True)
class BranchSpec:
    """分支规格"""
    check: str
    kind: BranchKind
    fixture: str = ""  # 任务 38 填入


BRANCHES: dict[str, BranchSpec] = {
    "bs_balance.1.missing": BranchSpec(check="bs_balance", kind="missing"),
    "bs_balance.2.exception": BranchSpec(check="bs_balance", kind="exception"),
    "bs_balance.exception": BranchSpec(check="bs_balance", kind="exception"),
    "d4_revenue_reconciliation.1.missing": BranchSpec(check="d4_revenue_reconciliation", kind="missing"),
    "d4_revenue_reconciliation.2.exception": BranchSpec(check="d4_revenue_reconciliation", kind="exception"),
    "d4_revenue_reconciliation.3.missing": BranchSpec(check="d4_revenue_reconciliation", kind="missing"),
    "d4_revenue_reconciliation.4.exception": BranchSpec(check="d4_revenue_reconciliation", kind="exception"),
    "d4_revenue_reconciliation.5.missing": BranchSpec(check="d4_revenue_reconciliation", kind="missing"),
    "d4_revenue_reconciliation.6.exception": BranchSpec(check="d4_revenue_reconciliation", kind="exception"),
    "d4_revenue_reconciliation.7.missing": BranchSpec(check="d4_revenue_reconciliation", kind="missing"),
    "d4_revenue_reconciliation.8.exception": BranchSpec(check="d4_revenue_reconciliation", kind="exception"),
    "d4_revenue_reconciliation.exception": BranchSpec(check="d4_revenue_reconciliation", kind="exception"),
    "data_freshness.1.exception": BranchSpec(check="data_freshness", kind="exception"),
    "data_freshness.exception": BranchSpec(check="data_freshness", kind="exception"),
    "e1_cfs_reconciliation.1.missing": BranchSpec(check="e1_cfs_reconciliation", kind="missing"),
    "e1_cfs_reconciliation.2.exception": BranchSpec(check="e1_cfs_reconciliation", kind="exception"),
    "e1_cfs_reconciliation.3.missing": BranchSpec(check="e1_cfs_reconciliation", kind="missing"),
    "e1_cfs_reconciliation.4.exception": BranchSpec(check="e1_cfs_reconciliation", kind="exception"),
    "e1_cfs_reconciliation.5.missing": BranchSpec(check="e1_cfs_reconciliation", kind="missing"),
    "e1_cfs_reconciliation.6.exception": BranchSpec(check="e1_cfs_reconciliation", kind="exception"),
    "e1_cfs_reconciliation.exception": BranchSpec(check="e1_cfs_reconciliation", kind="exception"),
    "f5_f2_triangle_reconciliation.1.missing": BranchSpec(check="f5_f2_triangle_reconciliation", kind="missing"),
    "f5_f2_triangle_reconciliation.2.exception": BranchSpec(check="f5_f2_triangle_reconciliation", kind="exception"),
    "f5_f2_triangle_reconciliation.3.missing": BranchSpec(check="f5_f2_triangle_reconciliation", kind="missing"),
    "f5_f2_triangle_reconciliation.4.exception": BranchSpec(check="f5_f2_triangle_reconciliation", kind="exception"),
    "f5_f2_triangle_reconciliation.5.missing": BranchSpec(check="f5_f2_triangle_reconciliation", kind="missing"),
    "f5_f2_triangle_reconciliation.6.exception": BranchSpec(check="f5_f2_triangle_reconciliation", kind="exception"),
    "f5_f2_triangle_reconciliation.7.missing": BranchSpec(check="f5_f2_triangle_reconciliation", kind="missing"),
    "f5_f2_triangle_reconciliation.8.exception": BranchSpec(check="f5_f2_triangle_reconciliation", kind="exception"),
    "f5_f2_triangle_reconciliation.exception": BranchSpec(check="f5_f2_triangle_reconciliation", kind="exception"),
    "g_cycle_triangle_reconciliation.1.missing": BranchSpec(check="g_cycle_triangle_reconciliation", kind="missing"),
    "g_cycle_triangle_reconciliation.2.missing": BranchSpec(check="g_cycle_triangle_reconciliation", kind="missing"),
    "g_cycle_triangle_reconciliation.3.exception": BranchSpec(check="g_cycle_triangle_reconciliation", kind="exception"),
    "g_cycle_triangle_reconciliation.4.missing": BranchSpec(check="g_cycle_triangle_reconciliation", kind="missing"),
    "g_cycle_triangle_reconciliation.5.exception": BranchSpec(check="g_cycle_triangle_reconciliation", kind="exception"),
    "g_cycle_triangle_reconciliation.6.missing": BranchSpec(check="g_cycle_triangle_reconciliation", kind="missing"),
    "g_cycle_triangle_reconciliation.7.exception": BranchSpec(check="g_cycle_triangle_reconciliation", kind="exception"),
    "g_cycle_triangle_reconciliation.8.missing": BranchSpec(check="g_cycle_triangle_reconciliation", kind="missing"),
    "g_cycle_triangle_reconciliation.9.exception": BranchSpec(check="g_cycle_triangle_reconciliation", kind="exception"),
    "g_cycle_triangle_reconciliation.exception": BranchSpec(check="g_cycle_triangle_reconciliation", kind="exception"),
    "h_cycle_triangle_reconciliation.1.missing": BranchSpec(check="h_cycle_triangle_reconciliation", kind="missing"),
    "h_cycle_triangle_reconciliation.2.exception": BranchSpec(check="h_cycle_triangle_reconciliation", kind="exception"),
    "h_cycle_triangle_reconciliation.3.missing": BranchSpec(check="h_cycle_triangle_reconciliation", kind="missing"),
    "h_cycle_triangle_reconciliation.4.exception": BranchSpec(check="h_cycle_triangle_reconciliation", kind="exception"),
    "h_cycle_triangle_reconciliation.5.missing": BranchSpec(check="h_cycle_triangle_reconciliation", kind="missing"),
    "h_cycle_triangle_reconciliation.6.exception": BranchSpec(check="h_cycle_triangle_reconciliation", kind="exception"),
    "h_cycle_triangle_reconciliation.7.missing": BranchSpec(check="h_cycle_triangle_reconciliation", kind="missing"),
    "h_cycle_triangle_reconciliation.8.exception": BranchSpec(check="h_cycle_triangle_reconciliation", kind="exception"),
    "h_cycle_triangle_reconciliation.exception": BranchSpec(check="h_cycle_triangle_reconciliation", kind="exception"),
    "i_cycle_triangle_reconciliation.1.missing": BranchSpec(check="i_cycle_triangle_reconciliation", kind="missing"),
    "i_cycle_triangle_reconciliation.2.exception": BranchSpec(check="i_cycle_triangle_reconciliation", kind="exception"),
    "i_cycle_triangle_reconciliation.3.missing": BranchSpec(check="i_cycle_triangle_reconciliation", kind="missing"),
    "i_cycle_triangle_reconciliation.4.exception": BranchSpec(check="i_cycle_triangle_reconciliation", kind="exception"),
    "i_cycle_triangle_reconciliation.5.missing": BranchSpec(check="i_cycle_triangle_reconciliation", kind="missing"),
    "i_cycle_triangle_reconciliation.6.exception": BranchSpec(check="i_cycle_triangle_reconciliation", kind="exception"),
    "i_cycle_triangle_reconciliation.exception": BranchSpec(check="i_cycle_triangle_reconciliation", kind="exception"),
    "is_reconciliation.1.missing": BranchSpec(check="is_reconciliation", kind="missing"),
    "is_reconciliation.2.missing": BranchSpec(check="is_reconciliation", kind="missing"),
    "is_reconciliation.3.exception": BranchSpec(check="is_reconciliation", kind="exception"),
    "is_reconciliation.exception": BranchSpec(check="is_reconciliation", kind="exception"),
    "j_cycle_triangle_reconciliation.1.missing": BranchSpec(check="j_cycle_triangle_reconciliation", kind="missing"),
    "j_cycle_triangle_reconciliation.2.exception": BranchSpec(check="j_cycle_triangle_reconciliation", kind="exception"),
    "j_cycle_triangle_reconciliation.3.missing": BranchSpec(check="j_cycle_triangle_reconciliation", kind="missing"),
    "j_cycle_triangle_reconciliation.4.exception": BranchSpec(check="j_cycle_triangle_reconciliation", kind="exception"),
    "j_cycle_triangle_reconciliation.5.missing": BranchSpec(check="j_cycle_triangle_reconciliation", kind="missing"),
    "j_cycle_triangle_reconciliation.6.exception": BranchSpec(check="j_cycle_triangle_reconciliation", kind="exception"),
    "j_cycle_triangle_reconciliation.exception": BranchSpec(check="j_cycle_triangle_reconciliation", kind="exception"),
    "k_cycle_triangle_reconciliation.1.missing": BranchSpec(check="k_cycle_triangle_reconciliation", kind="missing"),
    "k_cycle_triangle_reconciliation.2.exception": BranchSpec(check="k_cycle_triangle_reconciliation", kind="exception"),
    "k_cycle_triangle_reconciliation.3.missing": BranchSpec(check="k_cycle_triangle_reconciliation", kind="missing"),
    "k_cycle_triangle_reconciliation.4.exception": BranchSpec(check="k_cycle_triangle_reconciliation", kind="exception"),
    "k_cycle_triangle_reconciliation.5.missing": BranchSpec(check="k_cycle_triangle_reconciliation", kind="missing"),
    "k_cycle_triangle_reconciliation.6.exception": BranchSpec(check="k_cycle_triangle_reconciliation", kind="exception"),
    "k_cycle_triangle_reconciliation.exception": BranchSpec(check="k_cycle_triangle_reconciliation", kind="exception"),
    "l_cycle_triangle_reconciliation.1.missing": BranchSpec(check="l_cycle_triangle_reconciliation", kind="missing"),
    "l_cycle_triangle_reconciliation.2.exception": BranchSpec(check="l_cycle_triangle_reconciliation", kind="exception"),
    "l_cycle_triangle_reconciliation.3.missing": BranchSpec(check="l_cycle_triangle_reconciliation", kind="missing"),
    "l_cycle_triangle_reconciliation.4.exception": BranchSpec(check="l_cycle_triangle_reconciliation", kind="exception"),
    "l_cycle_triangle_reconciliation.5.missing": BranchSpec(check="l_cycle_triangle_reconciliation", kind="missing"),
    "l_cycle_triangle_reconciliation.6.exception": BranchSpec(check="l_cycle_triangle_reconciliation", kind="exception"),
    "l_cycle_triangle_reconciliation.exception": BranchSpec(check="l_cycle_triangle_reconciliation", kind="exception"),
    "m_cycle_triangle_reconciliation.1.missing": BranchSpec(check="m_cycle_triangle_reconciliation", kind="missing"),
    "m_cycle_triangle_reconciliation.2.exception": BranchSpec(check="m_cycle_triangle_reconciliation", kind="exception"),
    "m_cycle_triangle_reconciliation.3.missing": BranchSpec(check="m_cycle_triangle_reconciliation", kind="missing"),
    "m_cycle_triangle_reconciliation.4.exception": BranchSpec(check="m_cycle_triangle_reconciliation", kind="exception"),
    "m_cycle_triangle_reconciliation.exception": BranchSpec(check="m_cycle_triangle_reconciliation", kind="exception"),
    "n_cycle_triangle_reconciliation.1.missing": BranchSpec(check="n_cycle_triangle_reconciliation", kind="missing"),
    "n_cycle_triangle_reconciliation.2.exception": BranchSpec(check="n_cycle_triangle_reconciliation", kind="exception"),
    "n_cycle_triangle_reconciliation.3.missing": BranchSpec(check="n_cycle_triangle_reconciliation", kind="missing"),
    "n_cycle_triangle_reconciliation.4.exception": BranchSpec(check="n_cycle_triangle_reconciliation", kind="exception"),
    "n_cycle_triangle_reconciliation.exception": BranchSpec(check="n_cycle_triangle_reconciliation", kind="exception"),
    "notes_completeness.1.missing": BranchSpec(check="notes_completeness", kind="missing"),
    "notes_completeness.3.exception": BranchSpec(check="notes_completeness", kind="exception"),
    "notes_completeness.exception": BranchSpec(check="notes_completeness", kind="exception"),
    "tb_balance.1.missing": BranchSpec(check="tb_balance", kind="missing"),
    "tb_balance.unknown_category": BranchSpec(check="tb_balance", kind="missing"),
    "tb_balance.sign_unknown": BranchSpec(check="tb_balance", kind="missing"),
    "tb_balance.exception": BranchSpec(check="tb_balance", kind="exception"),
}
