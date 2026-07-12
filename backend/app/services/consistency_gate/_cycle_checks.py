"""一致性门控 — F/H/I/G/J/K/L/M/N 循环三角勾稽规则

各循环按审定表↔试算表↔报表三角关系验证勾稽。
"""
from __future__ import annotations

from app.services.consistency_gate._impl import ConsistencyGate as _Impl


class CycleChecksMixin:
    """D~N 循环三角勾稽"""

    # F 循环: F5/F2 三角勾稽 (VR-F5-01/02 + VR-F2-01/02)
    check_f5_f2_triangle_reconciliation = _Impl.check_f5_f2_triangle_reconciliation

    # H 循环: H1/H8 三角勾稽 (VR-H1-01/02/03 + VR-H8-01)
    check_h_cycle_triangle_reconciliation = _Impl.check_h_cycle_triangle_reconciliation

    # I 循环: I1/I3/I6 三角勾稽
    check_i_cycle_triangle_reconciliation = _Impl.check_i_cycle_triangle_reconciliation

    # G 循环: G7/G11/G1/G14 三角勾稽
    check_g_cycle_triangle_reconciliation = _Impl.check_g_cycle_triangle_reconciliation

    # J 循环: J1 三角勾稽
    check_j_cycle_triangle_reconciliation = _Impl.check_j_cycle_triangle_reconciliation

    # K 循环: K8/K9/K11 三角勾稽
    check_k_cycle_triangle_reconciliation = _Impl.check_k_cycle_triangle_reconciliation

    # L 循环: L1/L3/L8 三角勾稽
    check_l_cycle_triangle_reconciliation = _Impl.check_l_cycle_triangle_reconciliation

    # M 循环: M6/M2 三角勾稽
    check_m_cycle_triangle_reconciliation = _Impl.check_m_cycle_triangle_reconciliation

    # N 循环: N2/N5 三角勾稽
    check_n_cycle_triangle_reconciliation = _Impl.check_n_cycle_triangle_reconciliation
